"""Dashboard metrics, funnel, and discovery summary (observation vs hypothesis)."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from config import HIGH_INTENT_STATUSES
from database.models import Analysis, CollectionRun, Conversation, DiscoveryRun, Opportunity, SourceState, Theme
from processing.dates import in_research_window

CAUSAL_CAVEAT = (
    "Among the analyzed public conversations, this pattern appears frequently. "
    "It is a high-priority hypothesis to validate through primary research — "
    "not a claim that public social conversations represent the entire Myntra user population."
)


def load_conversations_frame(session: Session, window_days: int | None = None) -> pd.DataFrame:
    rows = session.query(Conversation).all()
    records = []
    for row in rows:
        if window_days is not None and row.published_at is not None:
            if not in_research_window(row.published_at, window_days):
                continue
        elif window_days is not None and row.published_at is None:
            continue
        records.append(
            {
                "id": row.id,
                "source": row.source,
                "source_item_id": row.source_item_id,
                "source_url": row.source_url,
                "author_id_hash": row.author_id_hash,
                "published_at": row.published_at,
                "timestamp": row.published_at,
                "title": row.title,
                "text": row.text,
                "original_text": row.original_text,
                "language": row.language,
                "query_used": row.query_used,
                "engagement_count": row.engagement_count,
                "collected_at": row.collected_at,
                "content_hash": row.content_hash,
                "is_syndicated": row.is_syndicated,
                "analysis_status": row.analysis_status,
            }
        )
    return pd.DataFrame.from_records(records)


def load_analysis_frame(session: Session, window_days: int | None = None) -> pd.DataFrame:
    rows = (
        session.query(Analysis)
        .options(joinedload(Analysis.conversation))
        .all()
    )
    records = []
    for row in rows:
        conv = row.conversation
        published = conv.published_at if conv else None
        if window_days is not None:
            if published is None or not in_research_window(published, window_days):
                continue
        blockers = []
        raw_blockers = getattr(row, "purchase_blockers", None) or getattr(row, "blockers", None)
        try:
            blockers = json.loads(raw_blockers or "[]")
        except json.JSONDecodeError:
            blockers = [row.purchase_blocker] if row.purchase_blocker else []
        info = []
        try:
            info = json.loads(row.information_sought or "[]")
        except json.JSONDecodeError:
            info = []
        secondary = []
        try:
            secondary = json.loads(row.secondary_problems or "[]")
        except json.JSONDecodeError:
            secondary = []
        high_intent_filter = (
            row.purchase_intent == "high" and row.purchase_status in HIGH_INTENT_STATUSES
        )
        records.append(
            {
                "id": row.id,
                "conversation_id": row.conversation_id,
                "source": conv.source if conv else "",
                "source_url": conv.source_url if conv else "",
                "published_at": conv.published_at if conv else None,
                "timestamp": conv.published_at if conv else None,
                "title": conv.title if conv else "",
                "text": conv.text if conv else "",
                "original_text": conv.original_text if conv else "",
                "language": conv.language if conv else "",
                "relevant_to_wishlist": row.relevant_to_wishlist,
                "relevance_reason": row.relevance_reason,
                "wishlist_behavior": row.wishlist_behavior,
                "purchase_intent": row.purchase_intent,
                "purchase_status": row.purchase_status,
                "primary_problem": row.primary_problem,
                "secondary_problems": secondary,
                "uncertainty": row.uncertainty,
                "uncertainty_type": row.uncertainty_type,
                "uncertainty_text": row.uncertainty_text,
                "purchase_blocker": row.purchase_blocker,
                "blockers": blockers,
                "motivation": row.motivation,
                "workaround": row.workaround,
                "information_sought": info,
                "leaves_myntra": row.leaves_myntra,
                "external_information_source": row.external_information_source,
                "alternative_considered": row.alternative_considered,
                "user_segment": row.user_segment,
                "segment_evidence": row.segment_evidence,
                "fashion_category": row.fashion_category,
                "occasion": row.occasion,
                "sentiment": row.sentiment,
                "evidence_quote": row.evidence_quote,
                "confidence": row.confidence,
                "needs_human_validation": row.needs_human_validation,
                "funnel_stage": row.funnel_stage,
                "analyzed_at": row.analyzed_at,
                "high_intent_friction": high_intent_filter,
            }
        )
    return pd.DataFrame.from_records(records)


def load_themes_frame(session: Session) -> pd.DataFrame:
    rows = session.query(Theme).all()
    return pd.DataFrame(
        [
            {
                "id": r.id,
                "theme_name": r.theme_name,
                "description": r.description,
                "frequency": r.frequency,
                "unique_users": r.unique_users,
                "high_intent_mentions": r.high_intent_mentions,
                "blocker_mentions": r.blocker_mentions,
                "purchase_mentions": r.purchase_mentions,
                "average_confidence": r.average_confidence,
                "conversion_relevance": r.conversion_relevance,
                "opportunity_score": r.opportunity_score,
                "representative_evidence": r.representative_evidence,
                "segment_distribution": r.segment_distribution,
                "pct_of_relevant": r.percentage_of_relevant_conversations,
                "percentage_of_relevant_conversations": r.percentage_of_relevant_conversations,
            }
            for r in rows
        ]
    )


def load_opportunities_frame(session: Session) -> pd.DataFrame:
    rows = session.query(Opportunity).order_by(Opportunity.opportunity_score.desc()).all()
    return pd.DataFrame(
        [
            {
                "id": r.id,
                "opportunity_name": r.opportunity_name,
                "user_segment": r.user_segment,
                "problem_statement": r.problem_statement,
                "evidence_count": r.evidence_count,
                "frequency_score": r.frequency_score,
                "severity_score": r.severity_score,
                "conversion_relevance_score": r.conversion_relevance_score,
                "workaround_score": r.workaround_score,
                "segment_score": r.segment_score,
                "confidence_score": r.confidence_score,
                "opportunity_score": r.opportunity_score,
                "supporting_evidence": r.supporting_evidence,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    )


def kpi_counts(conversations: pd.DataFrame, analysis: pd.DataFrame) -> dict[str, int]:
    relevant = analysis[analysis["relevant_to_wishlist"] == True] if not analysis.empty else analysis  # noqa: E712
    wishlist_behaviors = {
        "explicit_wishlist",
        "save_for_later",
        "cart_as_bookmark",
        "comparison_shortlist",
        "price_watch",
        "occasion_planning",
    }
    return {
        "total_conversations": int(len(conversations)),
        "relevant": int(len(relevant)),
        "wishlist_related": int(
            relevant["wishlist_behavior"].isin(wishlist_behaviors).sum() if not relevant.empty else 0
        ),
        "high_intent": int(
            relevant["high_intent_friction"].sum() if not relevant.empty else 0
        ),
        "purchase_blocker": int(
            (
                relevant["purchase_blocker"].isin(["no_blocker", "unknown", ""]) == False  # noqa: E712
            ).sum()
            if not relevant.empty
            else 0
        ),
        "needs_validation": int(
            analysis["needs_human_validation"].sum() if not analysis.empty else 0
        ),
        "unique_sources": int(conversations["source"].nunique()) if not conversations.empty else 0,
    }


def funnel_summary(analysis: pd.DataFrame) -> pd.DataFrame:
    if analysis.empty:
        return pd.DataFrame()
    relevant = analysis[analysis["relevant_to_wishlist"] == True]  # noqa: E712
    stages = [
        "Discovery",
        "Product Evaluation",
        "Wishlist",
        "High Purchase Intent",
        "Purchase",
        "Wishlist Purchase Within 30 Days",
    ]

    def stage_mask(name: str) -> pd.Series:
        if name == "Discovery":
            return relevant["funnel_stage"].eq("Discovery") | relevant["wishlist_behavior"].eq(
                "browsing_only"
            )
        if name == "Product Evaluation":
            return relevant["funnel_stage"].eq("Product Evaluation") | relevant[
                "wishlist_behavior"
            ].isin(["comparison_shortlist", "browsing_only"])
        if name == "Wishlist":
            return relevant["wishlist_behavior"].isin(
                [
                    "explicit_wishlist",
                    "save_for_later",
                    "cart_as_bookmark",
                    "price_watch",
                    "occasion_planning",
                    "comparison_shortlist",
                ]
            )
        if name == "High Purchase Intent":
            return relevant["high_intent_friction"] == True  # noqa: E712
        if name == "Purchase":
            return relevant["purchase_status"].eq("purchased")
        return relevant["funnel_stage"].eq("Wishlist Purchase Within 30 Days")

    rows = []
    for stage in stages:
        subset = relevant[stage_mask(stage)]
        blockers = Counter()
        for items in subset["blockers"]:
            if isinstance(items, list):
                blockers.update(items)
            elif items:
                blockers.update([items])
        uncertainties = Counter(subset["uncertainty_type"].fillna("unknown"))
        segments = Counter(subset["user_segment"].fillna("unknown"))
        workarounds = Counter(subset["external_information_source"].fillna("unknown"))
        rows.append(
            {
                "stage": stage,
                "evidence_items": int(len(subset)),
                "major_blockers": ", ".join(k for k, _ in blockers.most_common(3)) or "—",
                "major_uncertainties": ", ".join(k for k, _ in uncertainties.most_common(3)) or "—",
                "user_segments": ", ".join(k for k, _ in segments.most_common(3)) or "—",
                "external_workarounds": ", ".join(k for k, _ in workarounds.most_common(3)) or "—",
            }
        )
    return pd.DataFrame(rows)


def _top_n(series: pd.Series, n: int = 10) -> list[dict[str, Any]]:
    counts = series.fillna("unknown").replace("", "unknown").value_counts().head(n)
    return [{"name": str(idx), "count": int(val)} for idx, val in counts.items()]


def explode_blockers(analysis: pd.DataFrame) -> pd.Series:
    if analysis.empty:
        return pd.Series(dtype=str)
    values: list[str] = []
    for items in analysis["blockers"]:
        if isinstance(items, list):
            values.extend(str(x) for x in items if x)
        elif items:
            values.append(str(items))
    return pd.Series(values, dtype=str)


def build_discovery_summary(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> dict[str, Any]:
    relevant = (
        analysis[analysis["relevant_to_wishlist"] == True]  # noqa: E712
        if not analysis.empty
        else analysis
    )
    high = (
        relevant[relevant["high_intent_friction"] == True]  # noqa: E712
        if not relevant.empty
        else relevant
    )
    opp_list = []
    if not opportunities.empty:
        for _, row in opportunities.head(10).iterrows():
            evidence = []
            try:
                evidence = json.loads(row["supporting_evidence"] or "[]")
            except json.JSONDecodeError:
                evidence = []
            opp_list.append(
                {
                    "opportunity_name": row["opportunity_name"],
                    "user_segment": row["user_segment"],
                    "problem_statement": row["problem_statement"],
                    "evidence_count": int(row["evidence_count"]),
                    "frequency_score": float(row["frequency_score"]),
                    "severity_score": float(row["severity_score"]),
                    "conversion_relevance_score": float(row["conversion_relevance_score"]),
                    "opportunity_score": float(row["opportunity_score"]),
                    "supporting_evidence": evidence[:5],
                }
            )

    contradictory = []
    if not relevant.empty:
        purchased = relevant[relevant["purchase_status"] == "purchased"]
        for blocker, count in explode_blockers(relevant).value_counts().head(5).items():
            bought_with = 0
            for items in purchased["blockers"]:
                bag = items if isinstance(items, list) else [items]
                if blocker in bag:
                    bought_with += 1
            if bought_with:
                contradictory.append(
                    {
                        "topic": str(blocker),
                        "note": (
                            f"OBSERVATION: {int(count)} relevant conversations mention {blocker}, "
                            f"but {bought_with} conversations with this blocker still report a purchase. "
                            "Do not treat frequency as proof of non-conversion."
                        ),
                    }
                )

    gaps = []
    if relevant.empty:
        gaps.append("No relevant conversations analyzed yet.")
    else:
        unknown_intent = int((relevant["purchase_intent"] == "unknown").sum())
        no_quote = int((relevant["evidence_quote"] == "no direct evidence").sum())
        low_conf = int((relevant["confidence"] < 0.7).sum())
        if unknown_intent:
            gaps.append(f"{unknown_intent} relevant conversations have unknown purchase intent.")
        if no_quote:
            gaps.append(f"{no_quote} analyses have no grounded evidence quote.")
        if low_conf:
            gaps.append(f"{low_conf} analyses are below the 0.70 confidence threshold (needs human validation).")
        rare_segments = relevant["user_segment"].value_counts()
        if rare_segments.min() <= 2:
            gaps.append("Some segments have very few mentions; segment differences are directional only.")

    hypotheses = [
        "H1: Fit/size uncertainty is a conversion blocker specifically among high-intent wishlisters, not merely a general complaint.",
        "H2: A meaningful share of wishlist adds are price-watch bookmarks, so 30-day conversion is gated by sale timing rather than product rejection.",
        "H3: Users leave Myntra to resolve appearance/fit uncertainty (Instagram, YouTube, friends), indicating an in-journey information gap.",
        "H4: Comparison shortlists stall because listings do not support side-by-side decision criteria (fabric, measurements, real-body photos).",
        "H5: Return-policy effort increases the cost of 'buying to try', amplifying size uncertainty for some segments.",
        "H6: Review distrust (fake/incentivized reviews) reduces the usefulness of existing social proof on the product page.",
        "H7: Occasion-driven wishlists convert only when the event date is near; otherwise they age out.",
        "H8: Quality/fabric uncertainty is more acute for ethnic wear and higher AOV items than for basics.",
    ]

    top_problem = opp_list[0]["opportunity_name"] if opp_list else "insufficient evidence"
    top_segment = opp_list[0]["user_segment"] if opp_list else "unknown"
    recommendation_problem = top_problem
    recommendation_why = (
        f"WHY THIS PROBLEM IS MORE PROMISING: Among analyzed public conversations, "
        f"'{top_problem}' ranks highest on research-based opportunity prioritization "
        f"(frequency + severity + high-intent conversion relevance + existing workarounds + segment concentration + confidence). "
        f"It is concentrated among '{top_segment}'. Several high-intent users describe related friction while still considering, postponing, waiting, or abandoning. "
        f"This does not prove causality. It is the strongest candidate to take into user interviews — not a product solution."
        if opp_list
        else "Insufficient analyzed evidence to recommend a problem."
    )

    return {
        "kpis": kpi_counts(conversations, analysis),
        "top_problems": _top_n(relevant["primary_problem"], 10) if not relevant.empty else [],
        "top_blockers": _top_n(explode_blockers(relevant), 10) if not relevant.empty else [],
        "top_uncertainties": _top_n(relevant["uncertainty_type"], 10) if not relevant.empty else [],
        "top_segments": _top_n(relevant["user_segment"], 10) if not relevant.empty else [],
        "top_workarounds": _top_n(relevant["external_information_source"], 10)
        if not relevant.empty
        else [],
        "top_opportunities": opp_list[:5],
        "all_opportunities": opp_list,
        "contradictory_evidence": contradictory,
        "evidence_gaps": gaps,
        "hypotheses": hypotheses,
        "recommended_segment": top_segment,
        "recommended_problem": recommendation_problem,
        "recommendation_why": recommendation_why,
        "causal_caveat": CAUSAL_CAVEAT,
        "high_intent_top_problems": _top_n(high["primary_problem"], 8) if not high.empty else [],
        "motivations": _top_n(relevant["motivation"], 8) if not relevant.empty else [],
    }


def latest_run(session: Session) -> DiscoveryRun | None:
    return session.query(DiscoveryRun).order_by(DiscoveryRun.id.desc()).first()


def source_health_rows(session: Session, openrouter_configured: bool | None = None) -> list[dict[str, Any]]:
    states = session.query(SourceState).all()
    latest_by_source: dict[str, CollectionRun] = {}
    runs = session.query(CollectionRun).order_by(CollectionRun.id.desc()).all()
    for run in runs:
        if run.source not in latest_by_source:
            latest_by_source[run.source] = run
    names = ["reddit", "youtube", "web", "google_play", "app_store"]
    by_state = {s.source: s for s in states}
    rows = []
    for name in names:
        state = by_state.get(name)
        last = latest_by_source.get(name)
        status = state.status if state else "unknown"
        if name == "youtube" and not os.getenv("YOUTUBE_API_KEY", "").strip() and status in {"unknown", ""}:
            status = "not configured"
        rows.append(
            {
                "Source": name,
                "Status": status,
                "Last successful collection": (
                    str(state.last_successful_collection_time) if state and state.last_successful_collection_time else "—"
                ),
                "Records found": last.records_found if last else 0,
                "New records": last.records_new if last else 0,
                "Failed records": last.records_failed if last else 0,
                "Last error": (state.last_error if state and state.last_error else "")[:200],
            }
        )
    or_configured = (
        openrouter_configured
        if openrouter_configured is not None
        else bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    )
    last_ai = latest_run(session)
    rows.append(
        {
            "Source": "OpenRouter",
            "Status": "configured" if or_configured else "not configured",
            "Last successful collection": str(last_ai.last_ai_success_at) if last_ai and last_ai.last_ai_success_at else "—",
            "Records found": 0,
            "New records": last_ai.conversations_analyzed if last_ai else 0,
            "Failed records": 0,
            "Last error": "" if or_configured else "OPENROUTER_API_KEY is not set",
        }
    )
    return rows
