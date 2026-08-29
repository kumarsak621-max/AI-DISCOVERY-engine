"""Theme clustering via semantic rules plus optional LLM merge."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict

from typing import Any

from sqlalchemy.orm import Session

from ai.openrouter import OpenRouterError
from ai.prompts import CLUSTER_SYSTEM_PROMPT
from ai.provider import AIProviderError
from config import HIGH_INTENT_STATUSES
from database.models import Analysis, Theme

logger = logging.getLogger(__name__)

CANONICAL_THEMES: dict[str, tuple[str, str]] = {
    "size_uncertainty": (
        "FIT CONFIDENCE",
        "Users hesitate because they cannot tell whether a wishlisted item will fit their body or size.",
    ),
    "fit_uncertainty": (
        "FIT CONFIDENCE",
        "Users hesitate because they cannot tell whether a wishlisted item will fit their body or size.",
    ),
    "appearance_uncertainty": (
        "FIT CONFIDENCE",
        "Users hesitate because they cannot tell how the item will look on their body type.",
    ),
    "price_uncertainty": (
        "PRICE TIMING / PURCHASE DELAY",
        "Users delay purchase waiting for a better price, sale, or coupon rather than buying at listed price.",
    ),
    "waiting_for_price_drop": (
        "PRICE TIMING / PURCHASE DELAY",
        "Users delay purchase waiting for a better price, sale, or coupon rather than buying at listed price.",
    ),
    "budget_constraint": (
        "PRICE TIMING / PURCHASE DELAY",
        "Users delay purchase waiting for a better price, sale, or coupon rather than buying at listed price.",
    ),
    "quality_uncertainty": (
        "QUALITY / FABRIC CONFIDENCE",
        "Users cannot judge material, construction, or durability from listing photos and copy.",
    ),
    "fabric_uncertainty": (
        "QUALITY / FABRIC CONFIDENCE",
        "Users cannot judge material, construction, or durability from listing photos and copy.",
    ),
    "review_uncertainty": (
        "REVIEW TRUST GAP",
        "Users distrust, discount, or cannot interpret reviews (including fake-review concerns) before buying.",
    ),
    "trust_uncertainty": (
        "REVIEW TRUST GAP",
        "Users distrust, discount, or cannot interpret reviews (including fake-review concerns) before buying.",
    ),
    "styling_uncertainty": (
        "STYLING / OCCASION FIT",
        "Users are unsure how to style the item or whether it suits a specific occasion.",
    ),
    "occasion_uncertainty": (
        "STYLING / OCCASION FIT",
        "Users are unsure how to style the item or whether it suits a specific occasion.",
    ),
    "comparison_uncertainty": (
        "COMPARISON PARALYSIS",
        "Users shortlist multiple similar items and cannot decide which one to buy.",
    ),
    "return_uncertainty": (
        "RETURNS FRICTION",
        "Return effort, pickup, or policy uncertainty reduces willingness to buy when fit/quality is unknown.",
    ),
    "delivery_uncertainty": (
        "DELIVERY UNCERTAINTY",
        "Delivery time, reliability, or COD/logistics concerns delay or block purchase.",
    ),
    "social_validation": (
        "SOCIAL VALIDATION GAP",
        "Users wait for friends, influencers, or social proof before converting a wishlist item.",
    ),
    "availability_uncertainty": (
        "AVAILABILITY / SIZE STOCK",
        "Size or colour availability causes users to wait, watch, or abandon the wishlisted SKU.",
    ),
    "indecision": (
        "LOW URGENCY / INDECISION",
        "No acute need; the wishlist functions as a bookmark with weak conversion pressure.",
    ),
    "low_urgency": (
        "LOW URGENCY / INDECISION",
        "No acute need; the wishlist functions as a bookmark with weak conversion pressure.",
    ),
    "discovered_better_alternative": (
        "ALTERNATIVE LEAKAGE",
        "Users leave Myntra or switch products after finding a better option elsewhere or in-app.",
    ),
}


def problem_key(analysis: Analysis) -> str:
    blocker = (analysis.purchase_blocker or "unknown").strip().lower()
    if blocker in CANONICAL_THEMES:
        return blocker
    ut = (analysis.uncertainty_type or "").strip().lower()
    mapping = {
        "fit": "fit_uncertainty",
        "size": "size_uncertainty",
        "quality": "quality_uncertainty",
        "fabric": "fabric_uncertainty",
        "price": "waiting_for_price_drop",
        "styling": "styling_uncertainty",
        "reviews": "review_uncertainty",
        "returns": "return_uncertainty",
        "occasion": "occasion_uncertainty",
        "comparison": "comparison_uncertainty",
        "availability": "availability_uncertainty",
        "trust": "trust_uncertainty",
    }
    if ut in mapping:
        return mapping[ut]
    problem = (analysis.primary_problem or "").strip().lower()
    for token, key in (
        ("size", "size_uncertainty"),
        ("fit", "fit_uncertainty"),
        ("sale", "waiting_for_price_drop"),
        ("price", "waiting_for_price_drop"),
        ("quality", "quality_uncertainty"),
        ("fabric", "fabric_uncertainty"),
        ("review", "review_uncertainty"),
        ("style", "styling_uncertainty"),
        ("occasion", "occasion_uncertainty"),
        ("compar", "comparison_uncertainty"),
        ("return", "return_uncertainty"),
        ("deliver", "delivery_uncertainty"),
        ("instagram", "social_validation"),
        ("friend", "social_validation"),
    ):
        if token in problem:
            return key
    return blocker or "unknown"


def theme_for_key(key: str) -> tuple[str, str]:
    if key in CANONICAL_THEMES:
        return CANONICAL_THEMES[key]
    return (
        (key.replace("_", " ").upper() or "UNCLASSIFIED PROBLEM"),
        "Clustered from primary problem / blocker labels. Needs human validation.",
    )


def maybe_llm_merge(client: Any | None, keys: list[str]) -> dict[str, str]:
    """Optional remap of problem keys → theme names. Falls back to canonical map."""
    mapping = {key: theme_for_key(key)[0] for key in keys}
    if client is None or not client.is_configured or len(keys) < 3:
        return mapping
    try:
        payload = client.complete_json(
            CLUSTER_SYSTEM_PROMPT,
            "Problem keys to cluster:\n" + "\n".join(f"- {k}" for k in keys),
        )
        for theme in payload.get("themes", []):
            name = str(theme.get("theme_name") or "").strip()
            members = theme.get("member_problem_keys") or []
            if not name:
                continue
            for member in members:
                if member in mapping:
                    mapping[member] = name
    except (OpenRouterError, AIProviderError, Exception) as exc:  # noqa: BLE001
        logger.warning("LLM theme merge skipped: %s", exc)
    return mapping


def cluster_and_store(
    session: Session,
    analyses: list[Analysis],
    llm_client: Any | None = None,
) -> list[Theme]:
    session.query(Theme).delete()
    relevant = [a for a in analyses if a.relevant_to_wishlist]
    if not relevant:
        session.commit()
        return []

    groups: dict[str, list[Analysis]] = defaultdict(list)
    for analysis in relevant:
        groups[problem_key(analysis)].append(analysis)

    key_to_theme = maybe_llm_merge(llm_client, list(groups.keys()))
    merged: dict[str, list[Analysis]] = defaultdict(list)
    descriptions: dict[str, str] = {}
    for key, items in groups.items():
        name = key_to_theme.get(key) or theme_for_key(key)[0]
        merged[name].extend(items)
        descriptions[name] = theme_for_key(key)[1]

    n_relevant = len(relevant)
    stored: list[Theme] = []
    for name, items in merged.items():
        users = {a.conversation.author_id_hash for a in items if a.conversation}
        high_intent = sum(
            1
            for a in items
            if a.purchase_intent == "high" and a.purchase_status in HIGH_INTENT_STATUSES
        )
        blocker_mentions = sum(
            1 for a in items if a.purchase_blocker not in {"", "no_blocker", "unknown", None}
        )
        purchase_mentions = sum(1 for a in items if a.purchase_status == "purchased")
        confidences = [a.confidence or 0.0 for a in items]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        conversion = (high_intent / len(items) * 100.0) if items else 0.0
        segments = Counter((a.user_segment or "unknown") for a in items)
        quotes = []
        for a in items:
            if a.evidence_quote and a.evidence_quote != "no direct evidence":
                quotes.append(
                    {
                        "quote": a.evidence_quote,
                        "url": a.conversation.source_url if a.conversation else "",
                        "source": a.conversation.source if a.conversation else "",
                    }
                )
            if len(quotes) >= 5:
                break
        theme = Theme(
            theme_name=name,
            description=descriptions.get(name, ""),
            frequency=len(items),
            unique_users=len(users),
            high_intent_mentions=high_intent,
            blocker_mentions=blocker_mentions,
            purchase_mentions=purchase_mentions,
            average_confidence=round(avg_conf, 3),
            conversion_relevance=round(conversion, 2),
            opportunity_score=0.0,
            representative_evidence=json.dumps(quotes),
            segment_distribution=json.dumps(dict(segments)),
            percentage_of_relevant_conversations=round(len(items) / n_relevant * 100.0, 2),
        )
        session.add(theme)
        stored.append(theme)
    session.commit()
    return stored
