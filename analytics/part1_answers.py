"""Part 1 research-question answer engine.

All percentages are of analyzed public conversations in the current dataset.
They are never percentages of Myntra users.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

import pandas as pd

from config import HIGH_INTENT_STATUSES

PCT_LABEL = "Percentage of analyzed public conversations"

WANTED_STATUSES = {
    "considering",
    "postponed",
    "abandoned",
    "waiting",
    "rejected",
    "alternative_purchased",
}
DELAY_STATUSES = {"postponed", "waiting"}
ABANDON_STATUSES = {"abandoned", "rejected", "alternative_purchased"}
EXTERNAL = {
    "Reddit",
    "Instagram",
    "YouTube",
    "Google",
    "friends",
    "influencers",
    "other shopping apps",
    "brand website",
    "physical store",
}

# Display labels required by the Part 1 research questions (mapped from analyzer enums).
EXTERNAL_SOURCE_ROWS = [
    ("Google", "Google"),
    ("YouTube", "YouTube"),
    ("Instagram", "Instagram"),
    ("Reddit", "Reddit"),
    ("influencers", "influencers"),
    ("friends/family", "friends"),
    ("other marketplaces", "other shopping apps"),
    ("brand websites", "brand website"),
    ("physical stores", "physical store"),
]

SOCIAL_SOURCES = {"Instagram", "YouTube", "Reddit", "friends", "influencers"}

MOTIVATION_ORDER = [
    "genuine purchase intent",
    "save for later",
    "price monitoring",
    "comparison",
    "occasion planning",
    "inspiration",
    "bookmarking",
    "waiting for information",
    "waiting for availability",
    "waiting for sale",
    "uncertain purchase",
    "gift planning",
    "trend monitoring",
    "other",
]

UNCERTAINTY_TYPES = [
    "fit",
    "size",
    "quality",
    "material/fabric",
    "appearance",
    "styling",
    "price",
    "reviews",
    "returns",
    "occasion",
    "comparison",
    "availability",
]

FACTOR_KEYS = {
    "FIT": {"fit_uncertainty", "fit"},
    "SIZE": {"size_uncertainty", "size"},
    "STYLING": {"styling_uncertainty", "styling"},
    "PRICE": {"price_uncertainty", "waiting_for_price_drop", "budget_constraint", "price"},
    "REVIEWS": {"review_uncertainty", "trust_uncertainty", "reviews", "trust"},
    "OCCASION": {"occasion_uncertainty", "occasion"},
    "SOCIAL VALIDATION": {"social_validation"},
}

BLOCKER_TO_THEME = {
    "fit_uncertainty": "fit",
    "size_uncertainty": "size",
    "quality_uncertainty": "quality",
    "fabric_uncertainty": "quality",
    "appearance_uncertainty": "appearance",
    "price_uncertainty": "price",
    "waiting_for_price_drop": "price",
    "budget_constraint": "price",
    "review_uncertainty": "reviews",
    "trust_uncertainty": "trust",
    "styling_uncertainty": "styling",
    "occasion_uncertainty": "occasion",
    "availability_uncertainty": "availability",
    "return_uncertainty": "returns",
    "delivery_uncertainty": "delivery",
    "comparison_uncertainty": "comparison",
    "discovered_better_alternative": "alternatives",
    "better_alternative": "alternatives",
    "low_urgency": "low urgency",
    "indecision": "indecision",
    "social_validation": "trust",
}

COMPARISON_DIMENSIONS = [
    "price",
    "size",
    "fit",
    "material",
    "quality",
    "reviews",
    "ratings",
    "appearance",
    "brand",
    "styling",
    "occasion",
    "delivery",
    "returns",
    "availability",
    "value for money",
]


def _relevant(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["relevant_to_wishlist"] == True].copy()  # noqa: E712


def _high(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "high_intent_friction" not in df.columns:
        return df.iloc[0:0]
    return df[df["high_intent_friction"] == True]  # noqa: E712


def _pct(n: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return round(100.0 * n / denom, 1)


def _blockers_of(row: pd.Series) -> list[str]:
    items = row.get("blockers")
    if isinstance(items, list):
        return [str(x) for x in items if x]
    value = row.get("purchase_blocker")
    return [str(value)] if value else []


def _has_blocker(row: pd.Series, names: set[str]) -> bool:
    bag = set(_blockers_of(row))
    bag.add(str(row.get("purchase_blocker") or ""))
    bag.add(str(row.get("uncertainty_type") or "").lower())
    return bool(bag & names)


def _is_external(row: pd.Series) -> bool:
    if bool(row.get("leaves_myntra")):
        return True
    src = str(row.get("external_information_source") or "")
    return src in EXTERNAL


def _is_social_validation(row: pd.Series) -> bool:
    if _has_blocker(row, {"social_validation"}):
        return True
    src = str(row.get("external_information_source") or "")
    if src in SOCIAL_SOURCES:
        return True
    blob = " ".join(
        [
            str(row.get("workaround") or ""),
            str(row.get("uncertainty_text") or ""),
            " ".join(row.get("information_sought") or [])
            if isinstance(row.get("information_sought"), list)
            else str(row.get("information_sought") or ""),
        ]
    ).lower()
    return any(
        token in blob
        for token in ("instagram", "youtube", "reddit", "influencer", "friend", "outfit inspo")
    )


def _mode_or(series: pd.Series, default: str = "not stated") -> str:
    cleaned = series.replace("", pd.NA).dropna()
    cleaned = cleaned[cleaned.astype(str).str.len() > 2]
    if cleaned.empty:
        return default
    return str(cleaned.mode().iloc[0])


def _confidence_label(subset: pd.DataFrame) -> str:
    if subset.empty:
        return "Low"
    mean = float(subset["confidence"].mean()) if "confidence" in subset.columns else 0.0
    n = len(subset)
    quotes = 0
    if "evidence_quote" in subset.columns:
        quotes = int((subset["evidence_quote"].fillna("") != "no direct evidence").sum())
    if mean >= 0.75 and n >= 5 and quotes >= 3:
        return "High"
    if mean >= 0.5 and n >= 3:
        return "Medium"
    return "Low"


def _quotes(subset: pd.DataFrame, limit: int = 4) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if subset.empty:
        return out
    for _, row in subset.iterrows():
        quote = str(row.get("evidence_quote") or "").strip()
        if not quote or quote == "no direct evidence":
            continue
        original = str(row.get("original_text") or row.get("text") or "")
        if quote.lower() not in original.lower() and quote.lower() not in str(row.get("text") or "").lower():
            continue
        out.append(
            {
                "quote": quote,
                "source": str(row.get("source") or ""),
                "url": str(row.get("source_url") or ""),
                "published_at": str(row.get("published_at") or ""),
                "segment": str(row.get("user_segment") or "unknown"),
                "intent": str(row.get("purchase_intent") or "unknown"),
            }
        )
        if len(out) >= limit:
            break
    return out


def _trend(subset: pd.DataFrame) -> dict[str, Any]:
    if subset.empty or "published_at" not in subset.columns:
        return {"direction": "insufficient dated evidence", "weekly": []}
    ts = pd.to_datetime(subset["published_at"], utc=True, errors="coerce").dropna()
    if ts.empty:
        return {"direction": "insufficient dated evidence", "weekly": []}
    weekly = ts.dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("W").value_counts().sort_index()
    points = [{"week": str(idx), "mentions": int(val)} for idx, val in weekly.items()]
    if len(points) < 2:
        return {"direction": "insufficient weeks to call a trend", "weekly": points}
    first = points[0]["mentions"]
    last = points[-1]["mentions"]
    if last > first:
        direction = "increasing among dated public conversations"
    elif last < first:
        direction = "declining among dated public conversations"
    else:
        direction = "stable among dated public conversations"
    return {"direction": direction, "weekly": points}


def _segments(subset: pd.DataFrame, n: int = 4) -> list[dict[str, Any]]:
    if subset.empty:
        return []
    counts = subset["user_segment"].fillna("unknown").replace("", "unknown").value_counts().head(n)
    denom = len(subset)
    return [{"segment": str(k), "count": int(v), "pct_of_subset": _pct(int(v), denom)} for k, v in counts.items()]


def _gaps(subset: pd.DataFrame, n_relevant: int, topic: str) -> list[str]:
    gaps: list[str] = []
    if subset.empty:
        gaps.append(f"No analyzed public conversations currently support {topic}.")
        return gaps
    if len(subset) < 5:
        gaps.append(f"Only {len(subset)} conversations support {topic}; treat as directional.")
    no_quote = int((subset["evidence_quote"].fillna("no direct evidence") == "no direct evidence").sum())
    if no_quote:
        gaps.append(f"{no_quote} labeled rows lack a grounded evidence quote.")
    if "published_at" in subset.columns:
        undated = int(pd.to_datetime(subset["published_at"], utc=True, errors="coerce").isna().sum())
        if undated:
            gaps.append(f"{undated} rows lack a usable publication date for trend.")
    unknown_seg = int((subset["user_segment"].fillna("unknown").isin(["unknown", ""])).sum())
    if unknown_seg:
        gaps.append(f"{unknown_seg} rows have unknown segment.")
    gaps.append("Public conversations cannot measure actual Myntra 30-day wishlist conversion.")
    return gaps


def _direct_answer(lead: str, n: int, n_rel: int, extra: str = "") -> str:
    base = (
        f"OBSERVATION (analyzed public conversations only): {lead} "
        f"Evidence count = {n} "
        f"({_pct(n, n_rel)}% {PCT_LABEL.lower()} that are relevant). "
        "This is not a percentage of Myntra users."
    )
    if extra:
        return base + " " + extra
    return base


def classify_motivation(row: pd.Series) -> str:
    behavior = str(row.get("wishlist_behavior") or "")
    intent = str(row.get("purchase_intent") or "")
    occasion = str(row.get("occasion") or "").lower()
    motivation = str(row.get("motivation") or "").lower()
    segment = str(row.get("user_segment") or "").lower()
    blockers = set(_blockers_of(row))
    text = f"{motivation} {occasion} {row.get('uncertainty_text') or ''}".lower()

    if "gift" in text or "gift" in occasion:
        return "gift planning"
    if behavior == "price_watch" or "waiting_for_price_drop" in blockers:
        return "waiting for sale" if "waiting_for_price_drop" in blockers else "price monitoring"
    if "availability_uncertainty" in blockers:
        return "waiting for availability"
    if behavior == "comparison_shortlist":
        return "comparison"
    if behavior == "occasion_planning":
        return "occasion planning"
    if behavior == "cart_as_bookmark":
        return "bookmarking"
    if behavior == "save_for_later":
        return "save for later"
    if behavior == "browsing_only":
        if "trend" in segment:
            return "trend monitoring"
        return "inspiration"
    if any(b in blockers for b in {"review_uncertainty", "quality_uncertainty", "fabric_uncertainty"}):
        if str(row.get("purchase_status")) in DELAY_STATUSES:
            return "waiting for information"
    if behavior == "explicit_wishlist" and intent == "high":
        return "genuine purchase intent"
    if behavior == "explicit_wishlist" and intent in {"unknown", "medium", "low"}:
        return "uncertain purchase"
    if "trend" in segment:
        return "trend monitoring"
    return "other"


def classify_intent_bucket(row: pd.Series) -> str:
    behavior = str(row.get("wishlist_behavior") or "")
    intent = str(row.get("purchase_intent") or "")
    if behavior == "price_watch":
        return "PRICE WATCH"
    if behavior == "comparison_shortlist":
        return "COMPARISON"
    if behavior == "occasion_planning":
        return "OCCASION PLANNING"
    if behavior in {"browsing_only"}:
        return "INSPIRATION"
    if behavior in {"cart_as_bookmark", "save_for_later"} and intent in {"low", "unknown"}:
        return "BOOKMARKING"
    if intent == "high":
        return "HIGH PURCHASE INTENT"
    if intent == "medium":
        return "MEDIUM PURCHASE INTENT"
    if intent == "low":
        return "LOW PURCHASE INTENT"
    return "UNKNOWN"


def postpone_reason(row: pd.Series) -> str:
    blockers = _blockers_of(row)
    mapping = [
        ("waiting_for_price_drop", "waiting for price drop"),
        ("budget_constraint", "waiting for salary/payday"),
        ("occasion_uncertainty", "waiting for occasion"),
        ("review_uncertainty", "waiting for reviews"),
        ("availability_uncertainty", "waiting for size availability"),
        ("comparison_uncertainty", "comparing alternatives"),
        ("fit_uncertainty", "uncertain about fit"),
        ("size_uncertainty", "uncertain about fit"),
        ("quality_uncertainty", "uncertain about quality"),
        ("fabric_uncertainty", "uncertain about quality"),
        ("styling_uncertainty", "uncertain about styling"),
        ("low_urgency", "low urgency"),
        ("indecision", "waiting for decision"),
        ("discovered_better_alternative", "comparing alternatives"),
    ]
    for key, label in mapping:
        if key in blockers or str(row.get("purchase_blocker")) == key:
            return label
    alt = str(row.get("alternative_considered") or "").strip()
    if alt:
        return "waiting for another product"
    ut = str(row.get("uncertainty_type") or "").lower()
    ut_map = {
        "fit": "uncertain about fit",
        "size": "uncertain about fit",
        "quality": "uncertain about quality",
        "fabric": "uncertain about quality",
        "styling": "uncertain about styling",
        "price": "waiting for price drop",
        "reviews": "waiting for reviews",
        "occasion": "waiting for occasion",
        "comparison": "comparing alternatives",
        "availability": "waiting for size availability",
    }
    if ut in ut_map:
        return ut_map[ut]
    return "waiting for decision"


def comparison_dimensions_from_row(row: pd.Series) -> list[str]:
    blob = " ".join(
        [
            str(row.get("text") or ""),
            str(row.get("uncertainty_text") or ""),
            str(row.get("primary_problem") or ""),
            str(row.get("workaround") or ""),
            " ".join(row.get("information_sought") or [])
            if isinstance(row.get("information_sought"), list)
            else str(row.get("information_sought") or ""),
        ]
    ).lower()
    found: list[str] = []
    aliases = {
        "price": ["price", "cost", "expensive", "sale", "₹"],
        "size": ["size", "sizing"],
        "fit": ["fit", "fitting"],
        "material": ["material", "fabric", "gsm"],
        "quality": ["quality", "stitch"],
        "reviews": ["review"],
        "ratings": ["rating", "stars"],
        "appearance": ["look", "colour", "color", "photo"],
        "brand": ["brand"],
        "styling": ["style", "outfit"],
        "occasion": ["occasion", "wedding", "office"],
        "delivery": ["deliver"],
        "returns": ["return", "exchange"],
        "availability": ["stock", "available"],
        "value for money": ["value for money", "worth"],
    }
    for dim, keys in aliases.items():
        if any(k in blob for k in keys):
            found.append(dim)
    return found


def alternative_count_stated(text: str) -> int | None:
    """Return a count only if the source states a number. Never invent."""
    match = re.search(r"\b(\d{1,2})\s+(options|dresses|items|products|alternatives|versions)\b", text.lower())
    if match:
        return int(match.group(1))
    return None


def empty_question(title: str, question: str) -> dict[str, Any]:
    return {
        "title": title,
        "question": question,
        "direct_answer": (
            "Insufficient analyzed public conversations to answer this question yet. "
            "Run collection and OpenRouter analysis. "
            "No percentage of Myntra users can be computed from this dataset."
        ),
        "evidence_count": 0,
        "pct_of_relevant": 0.0,
        "pct_label": PCT_LABEL,
        "high_intent_evidence": 0,
        "segments": [],
        "trend": {"direction": "no data", "weekly": []},
        "quotes": [],
        "source_links": [],
        "confidence": "Low",
        "evidence_gaps": [
            "No relevant conversations in the current research window.",
            "Public conversations cannot measure actual Myntra 30-day conversion.",
        ],
        "tables": {},
    }


def _finish(
    title: str,
    question: str,
    subset: pd.DataFrame,
    relevant: pd.DataFrame,
    lead: str,
    tables: dict[str, Any],
    extra: str = "",
) -> dict[str, Any]:
    n_rel = len(relevant)
    quotes = _quotes(subset)
    links = [{"source": q["source"], "url": q["url"]} for q in quotes if q.get("url")]
    return {
        "title": title,
        "question": question,
        "direct_answer": _direct_answer(lead, len(subset), n_rel, extra),
        "evidence_count": int(len(subset)),
        "pct_of_relevant": _pct(len(subset), n_rel),
        "pct_label": PCT_LABEL,
        "high_intent_evidence": int(len(_high(subset))),
        "segments": _segments(subset),
        "trend": _trend(subset),
        "quotes": quotes,
        "source_links": links,
        "confidence": _confidence_label(subset),
        "evidence_gaps": _gaps(subset, n_rel, question),
        "tables": tables,
    }


def answer_q1(relevant: pd.DataFrame) -> dict[str, Any]:
    q = "Why do users add fashion products to their wishlist?"
    if relevant.empty:
        return empty_question("Q1 — Wishlist motivations", q)
    labeled = relevant.copy()
    labeled["motivation_class"] = labeled.apply(classify_motivation, axis=1)
    n_rel = len(relevant)
    rows = []
    for name in MOTIVATION_ORDER:
        sub = labeled[labeled["motivation_class"] == name]
        if sub.empty:
            continue
        hi = _high(sub)
        rows.append(
            {
                "motivation": name,
                "frequency": int(len(sub)),
                "pct_of_relevant": _pct(len(sub), n_rel),
                "high_intent_count": int(len(hi)),
                "high_intent_pct_of_motivation": _pct(len(hi), len(sub)),
                "top_segment": (_segments(sub, 1)[0]["segment"] if _segments(sub, 1) else "unknown"),
            }
        )
    top = rows[0]["motivation"] if rows else "other"
    lead = (
        f"Among relevant public conversations, the most frequent wishlist motivation label is '{top}'. "
        "Motivations are inferred from stated wishlist behavior, blockers, and occasion — not from Myntra event logs."
    )
    return _finish("Q1 — Wishlist motivations", q, labeled, relevant, lead, {"motivations": rows})


def answer_q2(relevant: pd.DataFrame) -> dict[str, Any]:
    q = "What prevents wishlisted products from eventually being purchased?"
    if relevant.empty:
        return empty_question("Q2 — Purchase blockers", q)
    wanted = relevant[
        relevant["purchase_intent"].isin(["high", "medium"])
        & relevant["purchase_status"].isin(WANTED_STATUSES)
    ]
    never = relevant[
        (relevant["purchase_intent"].eq("low"))
        | (relevant["wishlist_behavior"].isin(["browsing_only", "cart_as_bookmark"]))
    ]
    n_rel = len(relevant)
    theme_counts: Counter[str] = Counter()
    hi_counts: Counter[str] = Counter()
    for _, row in wanted.iterrows():
        themes = {BLOCKER_TO_THEME.get(b, b) for b in _blockers_of(row) if b not in {"no_blocker", "unknown", ""}}
        if not themes and row.get("uncertainty_type") not in {"", "none", "unknown", None}:
            themes = {str(row.get("uncertainty_type"))}
        for t in themes:
            theme_counts[t] += 1
            if row.get("high_intent_friction"):
                hi_counts[t] += 1
    table = []
    for theme, count in theme_counts.most_common():
        table.append(
            {
                "blocker_theme": theme,
                "wanted_but_did_not_purchase": int(count),
                "pct_of_relevant": _pct(count, n_rel),
                "high_intent_count": int(hi_counts.get(theme, 0)),
            }
        )
    lead = (
        f"{len(wanted)} relevant conversations look like 'wanted the product but did not (yet) purchase' "
        f"(intent high/medium and status in considering/postponed/abandoned/waiting/rejected/alternative). "
        f"{len(never)} look closer to 'never intended to purchase' (low intent or browsing/bookmarking). "
        "Do not mix these groups."
    )
    extra = "Highest-frequency blocker among the 'wanted' group is not proof it causes non-conversion."
    return _finish(
        "Q2 — Purchase blockers",
        q,
        wanted if not wanted.empty else relevant.iloc[0:0],
        relevant,
        lead,
        {
            "wanted_vs_never": {
                "wanted_but_did_not_purchase": int(len(wanted)),
                "wanted_pct_of_relevant": _pct(len(wanted), n_rel),
                "never_intended": int(len(never)),
                "never_intended_pct_of_relevant": _pct(len(never), n_rel),
            },
            "blockers_among_wanted": table,
        },
        extra,
    )


def answer_q3(relevant: pd.DataFrame) -> dict[str, Any]:
    q = "What uncertainties remain after users have identified a product they like?"
    if relevant.empty:
        return empty_question("Q3 — Uncertainty map", q)
    liked = relevant[relevant["wishlist_behavior"].isin(
        ["explicit_wishlist", "save_for_later", "comparison_shortlist", "price_watch", "occasion_planning"]
    )]
    n_rel = len(relevant)
    alias = {
        "fit": "fit",
        "size": "size",
        "quality": "quality",
        "fabric": "material/fabric",
        "material": "material/fabric",
        "appearance": "appearance",
        "styling": "styling",
        "price": "price",
        "reviews": "reviews",
        "returns": "returns",
        "occasion": "occasion",
        "comparison": "comparison",
        "availability": "availability",
    }
    rows = []
    for utype in UNCERTAINTY_TYPES:
        mask = liked["uncertainty_type"].fillna("").str.lower().isin(
            [k for k, v in alias.items() if v == utype]
        )
        extra_idx = []
        for idx, row in liked.iterrows():
            mapped = {BLOCKER_TO_THEME.get(b, "") for b in _blockers_of(row)}
            if utype == "material/fabric":
                if "fabric_uncertainty" in _blockers_of(row) or str(row.get("uncertainty_type")).lower() in {
                    "fabric",
                    "material",
                }:
                    extra_idx.append(idx)
            elif utype in mapped:
                extra_idx.append(idx)
        sub = liked[mask | liked.index.isin(extra_idx)]
        rows.append(
            {
                "uncertainty": utype,
                "total_evidence": int(len(sub)),
                "pct_of_relevant": _pct(len(sub), n_rel),
                "high_intent_evidence": int(len(_high(sub))),
                "purchase_delay_evidence": int(sub["purchase_status"].isin(DELAY_STATUSES).sum()) if not sub.empty else 0,
                "external_information_seeking_evidence": int(sub.apply(_is_external, axis=1).sum()) if not sub.empty else 0,
                "top_affected_segment": (_segments(sub, 1)[0]["segment"] if not sub.empty and _segments(sub, 1) else "—"),
            }
        )
    nonempty = [r for r in rows if r["total_evidence"] > 0]
    top = nonempty[0]["uncertainty"] if nonempty else "none labeled"
    lead = (
        f"After users have a product they like (wishlist/save/compare/price-watch/occasion labels), "
        f"the most frequent uncertainty type in this corpus is '{top}'. "
        "Uncertainties are labeled only when the conversation supports them."
    )
    known_unc = set(UNCERTAINTY_TYPES) | {"fabric", "material", "trust"}
    union = liked[liked["uncertainty_type"].fillna("").str.lower().isin(known_unc)]
    return _finish("Q3 — Uncertainty map", q, union if not union.empty else liked.iloc[0:0], relevant, lead, {"uncertainty_map": rows})


def answer_q4(relevant: pd.DataFrame) -> dict[str, Any]:
    q = "What causes users to postpone a purchase?"
    if relevant.empty:
        return empty_question("Q4 — Purchase delay", q)
    delayed = relevant[relevant["purchase_status"].isin(DELAY_STATUSES)].copy()
    n_rel = len(relevant)
    if delayed.empty:
        return _finish(
            "Q4 — Purchase delay",
            q,
            delayed,
            relevant,
            "No conversations in this window are labeled postponed or waiting.",
            {"postponement_reasons": []},
        )
    delayed["reason"] = delayed.apply(postpone_reason, axis=1)
    table = []
    for reason, sub in delayed.groupby("reason"):
        table.append(
            {
                "postponement_reason": reason,
                "evidence_count": int(len(sub)),
                "pct_of_relevant": _pct(len(sub), n_rel),
                "high_intent_count": int(len(_high(sub))),
                "affected_segment": (_segments(sub, 1)[0]["segment"] if _segments(sub, 1) else "unknown"),
                "typical_workaround": _mode_or(sub["workaround"]),
            }
        )
    table.sort(key=lambda r: r["evidence_count"], reverse=True)
    top = table[0]["postponement_reason"] if table else "not stated"
    lead = (
        f"{len(delayed)} relevant conversations are labeled postponed or waiting. "
        f"The most frequent explicit postponement reason in this corpus is '{top}'."
    )
    return _finish("Q4 — Purchase delay", q, delayed, relevant, lead, {"postponement_reasons": table})


def answer_q5(relevant: pd.DataFrame) -> dict[str, Any]:
    q = "How do users compare multiple shortlisted products?"
    if relevant.empty:
        return empty_question("Q5 — Comparison behavior", q)
    cmp_df = relevant[
        relevant["wishlist_behavior"].eq("comparison_shortlist")
        | relevant["purchase_blocker"].eq("comparison_uncertainty")
        | relevant["uncertainty_type"].fillna("").str.lower().eq("comparison")
        | relevant["blockers"].apply(
            lambda xs: "comparison_uncertainty" in (xs if isinstance(xs, list) else [xs])
        )
    ].copy()
    n_rel = len(relevant)
    dim_counts: Counter[str] = Counter()
    stated_counts: list[int] = []
    other_platform = 0
    delays = 0
    alt_purchase = 0
    where: Counter[str] = Counter()
    for _, row in cmp_df.iterrows():
        for dim in comparison_dimensions_from_row(row):
            dim_counts[dim] += 1
        n_alt = alternative_count_stated(str(row.get("original_text") or row.get("text") or ""))
        if n_alt is not None:
            stated_counts.append(n_alt)
        src = str(row.get("external_information_source") or "")
        if src in {"other shopping apps", "brand website", "physical store"}:
            other_platform += 1
        if str(row.get("purchase_status")) in DELAY_STATUSES | ABANDON_STATUSES | {"considering"}:
            delays += 1
        if str(row.get("purchase_status")) == "alternative_purchased":
            alt_purchase += 1
        if src in EXTERNAL:
            where[src] += 1
        else:
            where["not stated / appears on-platform"] += 1
    typical = None
    if stated_counts:
        typical = {
            "n_conversations_stating_a_count": len(stated_counts),
            "median_stated_alternatives": float(pd.Series(stated_counts).median()),
            "note": "Only conversations that stated a number. No invented count.",
        }
    else:
        typical = {
            "n_conversations_stating_a_count": 0,
            "median_stated_alternatives": None,
            "note": "No source in this corpus stated how many alternatives were considered. No number is invented.",
        }
    lead = (
        f"{len(cmp_df)} relevant conversations show comparison/shortlist behavior. "
        "Comparison dimensions are extracted from stated text, not assumed."
    )
    return _finish(
        "Q5 — Comparison behavior",
        q,
        cmp_df,
        relevant,
        lead,
        {
            "stated_alternative_counts": typical,
            "attributes_compared": [{"dimension": k, "evidence_count": int(v)} for k, v in dim_counts.most_common()],
            "where_they_compare": [{"place": k, "evidence_count": int(v)} for k, v in where.most_common()],
            "other_shopping_platform_evidence": other_platform,
            "comparison_associated_with_delay_or_open_decision": delays,
            "alternative_purchased_evidence": alt_purchase,
            "pct_of_relevant": _pct(len(cmp_df), n_rel),
        },
    )


def answer_q6(relevant: pd.DataFrame) -> dict[str, Any]:
    q = "What information do users seek outside Myntra before purchasing?"
    if relevant.empty:
        return empty_question("Q6 — External information seeking", q)
    external = relevant[relevant.apply(_is_external, axis=1)].copy()
    n_rel = len(relevant)
    rows = []
    for display, enum_value in EXTERNAL_SOURCE_ROWS:
        sub = relevant[relevant["external_information_source"].fillna("") == enum_value]
        sought: Counter[str] = Counter()
        for items in sub["information_sought"] if not sub.empty else []:
            if isinstance(items, list):
                sought.update(str(x) for x in items if x)
        rows.append(
            {
                "source": display,
                "evidence_count": int(len(sub)),
                "pct_of_relevant": _pct(len(sub), n_rel),
                "information_sought": ", ".join(k for k, _ in sought.most_common(4))
                or ("not stated" if not sub.empty else "no evidence in corpus"),
                "user_segment": (_segments(sub, 1)[0]["segment"] if not sub.empty and _segments(sub, 1) else "—"),
                "purchase_stage": _mode_or(sub["purchase_status"], "—") if not sub.empty else "—",
                "reason_for_leaving": _mode_or(sub["uncertainty_type"], "—") if not sub.empty else "—",
            }
        )
    rows.sort(key=lambda r: r["evidence_count"], reverse=True)
    gaps = []
    for items in external["information_sought"]:
        if isinstance(items, list):
            gaps.extend(str(x) for x in items if x)
    gap_counts = Counter(gaps).most_common(8)
    lead = (
        f"{len(external)} relevant conversations report leaving Myntra or using an external source. "
        "These are information-seeking workarounds, not proof that Myntra lacks a feature."
    )
    return _finish(
        "Q6 — External information seeking",
        q,
        external,
        relevant,
        lead,
        {
            "by_source": rows,
            "information_gaps": [
                {"information_sought": k, "evidence_count": int(v)} for k, v in gap_counts
            ],
        },
    )


def answer_q7(relevant: pd.DataFrame) -> dict[str, Any]:
    q = "What role do fit, size, styling, price, reviews, occasion and social validation play?"
    if relevant.empty:
        return empty_question("Q7 — Purchase decision factors", q)
    n_rel = len(relevant)
    factor_rows = []
    union_idx: set[Any] = set()
    factor_say = {
        "FIT": "What users say about fit uncertainty.",
        "SIZE": "What users say about sizing.",
        "STYLING": "Whether users know how to style the item.",
        "PRICE": "Whether price causes waiting or abandonment.",
        "REVIEWS": "Whether reviews increase or decrease confidence.",
        "OCCASION": "Whether purchase depends on a specific event/use case.",
        "SOCIAL VALIDATION": (
            "Whether users seek influencers, Instagram, friends, Reddit, YouTube, or other people's outfits."
        ),
    }
    for factor, keys in FACTOR_KEYS.items():
        mask = []
        for idx, row in relevant.iterrows():
            if factor == "SOCIAL VALIDATION":
                hit = _is_social_validation(row)
            else:
                hit = _has_blocker(row, keys) or str(row.get("uncertainty_type") or "").lower() in keys
            mask.append(bool(hit))
            if hit:
                union_idx.add(idx)
        sub = relevant[pd.Series(mask, index=relevant.index)]
        postponement = int(sub["purchase_status"].isin(DELAY_STATUSES).sum()) if not sub.empty else 0
        abandonment = int(sub["purchase_status"].isin(ABANDON_STATUSES).sum()) if not sub.empty else 0
        external_n = int(sub.apply(_is_external, axis=1).sum()) if not sub.empty else 0
        factor_rows.append(
            {
                "factor": factor,
                "what_users_say": factor_say[factor],
                "evidence_frequency": int(len(sub)),
                "pct_of_relevant": _pct(len(sub), n_rel),
                "high_intent_frequency": int(len(_high(sub))),
                "postponement_association": postponement,
                "abandonment_association": abandonment,
                "external_workaround_association": external_n,
                "affected_segments": ", ".join(s["segment"] for s in _segments(sub, 3)) or "—",
                "evidence_strength": _confidence_label(sub) if not sub.empty else "Low",
                "quotes": _quotes(sub, 3),
            }
        )
    factor_rows.sort(key=lambda r: r["evidence_frequency"], reverse=True)
    top = factor_rows[0]["factor"] if factor_rows else "none"
    lead = (
        f"Among relevant public conversations, '{top}' has the highest evidence frequency in this corpus. "
        "That is evidence strength, not a finding that this factor causes wishlist conversion failure."
    )
    union = relevant.loc[list(union_idx)] if union_idx else relevant.iloc[0:0]
    return _finish("Q7 — Purchase decision factors", q, union, relevant, lead, {"factors": factor_rows})


def answer_q8(relevant: pd.DataFrame) -> dict[str, Any]:
    q = "When is wishlist behavior genuine purchase intent versus simply bookmarking?"
    if relevant.empty:
        return empty_question("Q8 — Wishlist intent", q)
    labeled = relevant.copy()
    labeled["intent_bucket"] = labeled.apply(classify_intent_bucket, axis=1)
    n_rel = len(relevant)
    table = []
    for bucket, sub in labeled.groupby("intent_bucket"):
        table.append(
            {
                "category": bucket,
                "evidence_count": int(len(sub)),
                "pct_of_relevant": _pct(len(sub), n_rel),
                "typical_purchase_status": str(sub["purchase_status"].mode().iloc[0]) if not sub.empty else "unknown",
                "typical_blocker": str(sub["purchase_blocker"].mode().iloc[0]) if not sub.empty else "unknown",
                "external_research_pct_of_category": _pct(int(sub.apply(_is_external, axis=1).sum()), len(sub)),
                "alternative_mentioned": int(sub["alternative_considered"].fillna("").astype(str).str.len().gt(3).sum()),
            }
        )
    table.sort(key=lambda r: r["evidence_count"], reverse=True)
    high_n = int((labeled["intent_bucket"] == "HIGH PURCHASE INTENT").sum())
    book_n = int((labeled["intent_bucket"] == "BOOKMARKING").sum())
    lead = (
        f"{high_n} conversations are labeled HIGH PURCHASE INTENT and {book_n} BOOKMARKING "
        "based on stated behavior + intent labels. These are signals associated with purchase intent, "
        "not actual 30-day conversion rates. Public conversations cannot establish actual conversion without transaction data."
    )
    return _finish("Q8 — Wishlist intent", q, labeled, relevant, lead, {"intent_categories": table})


def answer_q9(relevant: pd.DataFrame, opportunities: pd.DataFrame) -> dict[str, Any]:
    q = "How do these behaviors differ across user segments?"
    if relevant.empty:
        return empty_question("Q9 — Behavioral segments", q)
    n_rel = len(relevant)
    known = relevant[~relevant["user_segment"].fillna("unknown").isin(["unknown", ""])]
    segment_rows = []
    factors = ["fit", "price", "reviews", "styling", "comparison"]
    matrix: list[dict[str, Any]] = []
    for seg, sub in known.groupby("user_segment"):
        opp_name = "—"
        if not opportunities.empty:
            hit = opportunities[opportunities["user_segment"] == seg]
            if not hit.empty:
                opp_name = str(hit.iloc[0]["opportunity_name"])
        segment_rows.append(
            {
                "segment": str(seg),
                "evidence_count": int(len(sub)),
                "pct_of_relevant": _pct(len(sub), n_rel),
                "wishlist_motivation": classify_motivation(sub.iloc[0]) if not sub.empty else "unknown",
                "typical_purchase_intent": str(sub["purchase_intent"].mode().iloc[0]),
                "typical_blocker": str(sub["purchase_blocker"].mode().iloc[0]),
                "typical_uncertainty": str(sub["uncertainty_type"].mode().iloc[0]),
                "comparison_share_of_segment": _pct(
                    int((sub["wishlist_behavior"] == "comparison_shortlist").sum()), len(sub)
                ),
                "external_research_share_of_segment": _pct(int(sub.apply(_is_external, axis=1).sum()), len(sub)),
                "typical_workaround": _mode_or(sub["workaround"]),
                "top_opportunity": opp_name,
            }
        )
        cell: dict[str, Any] = {"segment": str(seg)}
        for f in factors:
            keys = {
                "fit": {"fit_uncertainty", "size_uncertainty", "fit", "size"},
                "price": {"price_uncertainty", "waiting_for_price_drop", "budget_constraint", "price"},
                "reviews": {"review_uncertainty", "trust_uncertainty", "reviews"},
                "styling": {"styling_uncertainty", "styling"},
                "comparison": {"comparison_uncertainty", "comparison"},
            }[f]
            n = int(sub.apply(lambda r, k=keys: _has_blocker(r, k), axis=1).sum())
            share = n / len(sub) if len(sub) else 0
            if n == 0:
                cell[f] = "None in corpus"
            elif share >= 0.4:
                cell[f] = "High"
            elif share >= 0.2:
                cell[f] = "Medium"
            else:
                cell[f] = "Low"
        matrix.append(cell)
    lead = (
        f"{len(known)} relevant conversations have an evidence-supported segment label "
        f"({_pct(len(known), n_rel)} {PCT_LABEL.lower()}). "
        "Cells in the segment × problem matrix are High/Medium/Low only from this corpus, not from Myntra users."
    )
    return _finish("Q9 — Behavioral segments", q, known, relevant, lead, {"segments": segment_rows, "matrix": matrix})


def answer_q10(relevant: pd.DataFrame, opportunities: pd.DataFrame) -> dict[str, Any]:
    q = "What unmet needs emerge consistently across user conversations?"
    if relevant.empty:
        return empty_question("Q10 — Unmet needs", q)
    n_rel = len(relevant)
    needs = []
    if not opportunities.empty:
        for _, opp in opportunities.head(8).iterrows():
            name = str(opp["opportunity_name"])
            token = name.split()[0].lower()
            sub = relevant[
                relevant["purchase_blocker"].fillna("").str.contains(token[:4], case=False, regex=False)
                | relevant["uncertainty_type"].fillna("").str.contains(token[:4], case=False, regex=False)
                | relevant["primary_problem"].fillna("").str.contains(token[:4], case=False, regex=False)
            ]
            if sub.empty:
                continue
            repeated_problem = len(sub) >= 3
            repeated_unc = int(sub["uncertainty_type"].fillna("").ne("").sum()) >= 3
            repeated_work = int(sub["workaround"].fillna("").str.len().gt(3).sum()) >= 3
            repeated_ext = int(sub.apply(_is_external, axis=1).sum()) >= 3
            repeated_delay = int(sub["purchase_status"].isin(DELAY_STATUSES).sum()) >= 3
            repeated_abn = int(sub["purchase_status"].isin(ABANDON_STATUSES).sum()) >= 2
            repeated_cmp = int((sub["wishlist_behavior"] == "comparison_shortlist").sum()) >= 3
            if not any(
                [
                    repeated_problem,
                    repeated_unc,
                    repeated_work,
                    repeated_ext,
                    repeated_delay,
                    repeated_abn,
                    repeated_cmp,
                ]
            ):
                continue
            strength = _confidence_label(sub)
            needs.append(
                {
                    "user_need": f"Decide whether to purchase a liked/wishlisted item despite '{name}' friction",
                    "current_problem": str(opp.get("problem_statement") or name),
                    "current_workaround": _mode_or(sub["workaround"], "not stated in corpus"),
                    "evidence_count": int(len(sub)),
                    "pct_of_relevant": _pct(len(sub), n_rel),
                    "affected_segment": str(opp.get("user_segment") or (_segments(sub, 1)[0]["segment"] if _segments(sub, 1) else "unknown")),
                    "wishlist_purchase_relevance": (
                        "May affect wishlist → purchase if high-intent users postpone or abandon while this need is unmet. "
                        "Hypothesis, not proven conversion impact."
                    ),
                    "evidence_strength": strength,
                    "quotes": _quotes(sub, 2),
                }
            )
    lead = (
        f"{len(needs)} unmet-need candidates met the repetition rule "
        "(problem, uncertainty, workaround, external search, postponement, abandonment, or comparison friction)."
    )
    union = relevant if needs else relevant.iloc[0:0]
    return _finish("Q10 — Unmet needs", q, union, relevant, lead, {"unmet_needs": needs})


def behavioral_chains(relevant: pd.DataFrame) -> list[dict[str, Any]]:
    if relevant.empty:
        return []
    # Count rows that contain a supported mini-sequence of labels.
    candidates = [
        {
            "chain": "likes product → wishlist → fit/size uncertainty → external search → postpone",
            "mask": lambda r: r["wishlist_behavior"]
            in {"explicit_wishlist", "save_for_later"}
            and str(r.get("uncertainty_type")).lower() in {"fit", "size"}
            and _is_external(r)
            and str(r.get("purchase_status")) in DELAY_STATUSES,
        },
        {
            "chain": "likes product → price watch / waiting for sale → postpone",
            "mask": lambda r: (
                str(r.get("wishlist_behavior")) == "price_watch"
                or "waiting_for_price_drop" in _blockers_of(r)
            )
            and str(r.get("purchase_status")) in DELAY_STATUSES,
        },
        {
            "chain": "shortlist → comparison uncertainty → delay or alternative",
            "mask": lambda r: str(r.get("wishlist_behavior")) == "comparison_shortlist"
            and str(r.get("purchase_status")) in DELAY_STATUSES | {"alternative_purchased", "considering"},
        },
        {
            "chain": "wishlist → review/trust uncertainty → external search",
            "mask": lambda r: str(r.get("uncertainty_type")).lower() in {"reviews", "trust"}
            and _is_external(r),
        },
    ]
    out = []
    for item in candidates:
        hits = relevant[relevant.apply(item["mask"], axis=1)]
        if len(hits) >= 3:
            out.append(
                {
                    "chain": item["chain"],
                    "supporting_conversations": int(len(hits)),
                    "pct_of_relevant": _pct(len(hits), len(relevant)),
                    "quotes": _quotes(hits, 2),
                }
            )
    return out


def synthesize(answers: dict[str, dict[str, Any]], relevant: pd.DataFrame) -> dict[str, str]:
    def lead(key: str) -> str:
        return str(answers.get(key, {}).get("direct_answer") or "Insufficient evidence.")

    return {
        "why_wishlist": lead("q1"),
        "closest_to_purchase": lead("q8"),
        "high_intent_blockers": lead("q2"),
        "biggest_uncertainties": lead("q3"),
        "how_they_compare": lead("q5"),
        "external_information": lead("q6"),
        "factors_that_matter": lead("q7"),
        "segment_differences": lead("q9"),
        "workarounds": lead("q6"),
        "unmet_needs": lead("q10"),
    }


def rank_opportunities(relevant: pd.DataFrame, opportunities: pd.DataFrame) -> list[dict[str, Any]]:
    ranked = []
    if opportunities.empty or relevant.empty:
        return ranked
    n_rel = len(relevant)
    for _, opp in opportunities.head(5).iterrows():
        name = str(opp["opportunity_name"])
        token = name.split()[0].lower()[:4]
        sub = relevant[
            relevant["purchase_blocker"].fillna("").str.contains(token, case=False, regex=False)
            | relevant["uncertainty_type"].fillna("").str.contains(token, case=False, regex=False)
            | relevant["primary_problem"].fillna("").str.contains(token, case=False, regex=False)
        ]
        ranked.append(
            {
                "problem": name,
                "segment": str(opp.get("user_segment") or "unknown"),
                "evidence_count": int(opp.get("evidence_count") or len(sub)),
                "high_intent_evidence": int(len(_high(sub))),
                "purchase_delay_evidence": int(sub["purchase_status"].isin(DELAY_STATUSES).sum()) if not sub.empty else 0,
                "external_workaround_evidence": int(sub.apply(_is_external, axis=1).sum()) if not sub.empty else 0,
                "frequency": float(opp.get("frequency_score") or 0),
                "severity": float(opp.get("severity_score") or 0),
                "conversion_relevance": float(opp.get("conversion_relevance_score") or 0),
                "evidence_confidence": float(opp.get("confidence_score") or 0),
                "opportunity_score": float(opp.get("opportunity_score") or 0),
                "pct_of_relevant": _pct(len(sub), n_rel),
            }
        )
    return ranked


def why_top_opportunity(ranked: list[dict[str, Any]]) -> str:
    if not ranked:
        return "Insufficient evidence to rank opportunities."
    top = ranked[0]
    others = ", ".join(r["problem"] for r in ranked[1:3]) or "the remaining candidates"
    return (
        f"HYPOTHESIS (not a product recommendation): '{top['problem']}' ranks highest on the "
        f"Research-Based Opportunity Score ({top['opportunity_score']}) because it combines "
        f"frequency, severity among delayed/abandoned statuses, high-intent friction, and "
        f"existing workarounds. Relative to {others}, it has more high-intent evidence "
        f"({top['high_intent_evidence']}) and purchase-delay evidence ({top['purchase_delay_evidence']}) "
        f"in this public corpus. This does not prove it causes Myntra wishlist non-conversion. "
        f"It is the strongest opportunity hypothesis to take into user interviews."
    )


def interview_handoff(answers: dict[str, Any], ranked: list[dict[str, Any]], relevant: pd.DataFrame) -> dict[str, Any]:
    segment = ranked[0]["segment"] if ranked else "unknown"
    problem = ranked[0]["problem"] if ranked else "insufficient evidence"
    q8 = answers.get("q8", {}).get("tables", {}).get("intent_categories") or []
    high = next((r for r in q8 if r.get("category") == "HIGH PURCHASE INTENT"), None)
    hypotheses = [
        f"H1: Among people who already like a product, '{problem}' is a reason they postpone rather than a general complaint (trace: Q2/Q4).",
        "H2: High-intent wishlisters are a different population from browsers/bookmarking users (trace: Q2 wanted vs never intended, Q8).",
        "H3: Fit/size uncertainty persists after product identification and drives external photo-seeking (trace: Q3, Q6).",
        "H4: Price-watch wishlists convert on sale timing, so 30-day conversion is gated by calendar not rejection (trace: Q1, Q4, Q8).",
        "H5: Comparison shortlists stall without side-by-side fabric/fit/price evidence (trace: Q5).",
        "H6: Users leave Myntra because listing information does not resolve a specific uncertainty (trace: Q6 information gaps).",
        "H7: Review distrust reduces the usefulness of on-page social proof for high-intent shoppers (trace: Q7 REVIEWS).",
        "H8: Occasion-planned wishlists wait for the event date and may miss 30-day conversion by design (trace: Q1 occasion, Q4).",
        "H9: Segment differences mean one average 'wishlist user' problem will mislead roadmap priority (trace: Q9 matrix).",
        "H10: Workarounds (YouTube, Instagram, multi-size orders, other apps) indicate willingness to spend effort — a signal of unmet need intensity, not of a chosen solution (trace: Q6, Q10).",
    ]
    cannot = [
        "Actual wishlist-to-purchase conversion among Myntra users.",
        "Actual 30-day purchase behavior after a wishlist add.",
        "Actual frequency of blockers in the Myntra customer population.",
        "Whether an identified blocker causes abandonment (vs correlates in public chatter).",
        "Whether users would value a potential solution (no solution is proposed in Part 1).",
        "How public-conversation users differ from Myntra's logged-in customer base.",
        "Numeric alternative-set sizes unless a source stated a number (Q5).",
        "Causal impact of any factor on the 30-day KPI.",
    ]
    why_seg = (
        f"Interview '{segment}' first because opportunity ranking and high-intent evidence concentrate there "
        f"in this public corpus. Confirm whether they are representative of Myntra high-intent wishlisters."
        if ranked
        else "Collect more relevant conversations before selecting an interview segment."
    )
    why_prob = (
        f"Validate '{problem}' because it is the top Research-Based Opportunity Score item and appears "
        f"in high-intent postponed/waiting conversations. Part 3 interviews must test whether this is a "
        f"real conversion barrier or an artifact of public-discussion sampling."
        if ranked
        else "No problem is ready to validate."
    )
    if high:
        why_seg += f" HIGH PURCHASE INTENT n={high.get('evidence_count')} in analyzed public conversations."
    _ = relevant  # corpus size already in answers
    return {
        "recommended_interview_segment": segment,
        "why_segment": why_seg,
        "recommended_problem_to_validate": problem,
        "why_problem": why_prob,
        "interview_hypotheses": hypotheses,
        "questions_public_data_cannot_answer": cannot,
    }


def build_part1_answers(
    analysis: pd.DataFrame,
    opportunities: pd.DataFrame | None = None,
) -> dict[str, Any]:
    relevant = _relevant(analysis)
    opp = opportunities if opportunities is not None else pd.DataFrame()
    answers = {
        "q1": answer_q1(relevant),
        "q2": answer_q2(relevant),
        "q3": answer_q3(relevant),
        "q4": answer_q4(relevant),
        "q5": answer_q5(relevant),
        "q6": answer_q6(relevant),
        "q7": answer_q7(relevant),
        "q8": answer_q8(relevant),
        "q9": answer_q9(relevant, opp),
        "q10": answer_q10(relevant, opp),
    }
    ranked = rank_opportunities(relevant, opp)
    return {
        "pct_label": PCT_LABEL,
        "disclaimer": (
            "All percentages below are of analyzed public conversations in this dataset. "
            "They are not percentages of Myntra users."
        ),
        "n_relevant": int(len(relevant)),
        "n_analyzed": int(len(analysis)) if not analysis.empty else 0,
        "questions": answers,
        "chains": behavioral_chains(relevant),
        "synthesis": synthesize(answers, relevant),
        "opportunities": ranked,
        "why_top_opportunity": why_top_opportunity(ranked),
        "handoff": interview_handoff(answers, ranked, relevant),
    }


def _tables_md(tables: dict[str, Any]) -> list[str]:
    lines = ["### Supporting tables", ""]
    for name, value in tables.items():
        lines.append(f"#### {name}")
        if isinstance(value, list) and value and isinstance(value[0], dict):
            flat = [{k: v for k, v in row.items() if k != "quotes"} for row in value]
            keys = list(flat[0].keys())
            lines.append("| " + " | ".join(str(k) for k in keys) + " |")
            lines.append("| " + " | ".join("---" for _ in keys) + " |")
            for row in flat:
                lines.append(
                    "| " + " | ".join(str(row.get(k, "")).replace("|", "/") for k in keys) + " |"
                )
            lines.append("")
        else:
            lines.append("```json")
            lines.append(json.dumps(value, indent=2, default=str))
            lines.append("```")
            lines.append("")
    return lines


def part1_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Part 1 — AI Discovery Answers",
        "",
        payload.get("disclaimer", ""),
        "",
        f"Relevant conversations in window: {payload.get('n_relevant', 0)}",
        "",
    ]
    for key in [f"q{i}" for i in range(1, 11)]:
        q = payload["questions"][key]
        lines += [
            f"## {q['title']}",
            "",
            f"**Question:** {q['question']}",
            "",
            f"**Direct answer:** {q['direct_answer']}",
            "",
            f"- Evidence count: {q['evidence_count']}",
            f"- {q['pct_label']}: {q['pct_of_relevant']}%",
            f"- High-intent user evidence: {q['high_intent_evidence']}",
            f"- Confidence: {q['confidence']}",
            f"- 30-day trend (dated conversations): {q['trend'].get('direction')}",
            "",
            "### Representative quotes",
        ]
        if not q["quotes"]:
            lines.append("- no direct evidence")
        for item in q["quotes"]:
            lines.append(f"- “{item['quote']}” — {item['source']} {item.get('url') or ''}")
        lines += ["", "### Evidence gaps"]
        for g in q["evidence_gaps"]:
            lines.append(f"- {g}")
        lines.append("")
        tables = q.get("tables") or {}
        if tables:
            lines += _tables_md(tables)
    lines += ["## Cross-question behavioral chains", ""]
    if not payload.get("chains"):
        lines.append("No chain had 3+ supporting conversations.")
    for chain in payload.get("chains") or []:
        lines.append(f"- {chain['chain']} (n={chain['supporting_conversations']})")
    lines += ["", "## What we learned", ""]
    for k, v in (payload.get("synthesis") or {}).items():
        lines.append(f"- **{k}:** {v}")
    lines += ["", "## Top 5 opportunity hypotheses", ""]
    for i, opp in enumerate(payload.get("opportunities") or [], start=1):
        lines.append(
            f"{i}. {opp['problem']} — segment {opp['segment']}, score {opp['opportunity_score']}, "
            f"evidence {opp['evidence_count']}"
        )
    lines += ["", payload.get("why_top_opportunity") or "", "", "## Primary research handoff", ""]
    h = payload.get("handoff") or {}
    lines.append(f"**Interview segment:** {h.get('recommended_interview_segment')}")
    lines.append(h.get("why_segment") or "")
    lines.append(f"**Problem to validate:** {h.get('recommended_problem_to_validate')}")
    lines.append(h.get("why_problem") or "")
    lines += ["", "### Interview hypotheses"]
    for hyp in h.get("interview_hypotheses") or []:
        lines.append(f"- {hyp}")
    lines += ["", "### Questions public data cannot answer"]
    for item in h.get("questions_public_data_cannot_answer") or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Part 1 output is DISCOVERY → OPPORTUNITY HYPOTHESIS. No product solution is proposed.")
    return "\n".join(lines)
