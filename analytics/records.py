"""Merge collected conversations with analysis for Review Explorer."""

from __future__ import annotations

import pandas as pd

from processing.dates import utcnow, window_bounds

SOURCE_LABELS = [
    ("google_play", "Google Play Store"),
    ("app_store", "Apple App Store"),
    ("web", "Web/Fashion Communities"),
    ("reddit", "Reddit"),
    ("youtube", "YouTube"),
]


ANALYSIS_COLS = [
    "conversation_id",
    "relevant_to_wishlist",
    "relevance_reason",
    "wishlist_behavior",
    "purchase_intent",
    "purchase_status",
    "primary_problem",
    "uncertainty_type",
    "uncertainty_text",
    "purchase_blocker",
    "motivation",
    "workaround",
    "information_sought",
    "external_information_source",
    "alternative_considered",
    "user_segment",
    "fashion_category",
    "occasion",
    "sentiment",
    "evidence_quote",
    "confidence",
    "needs_human_validation",
]


def analysis_period_label(days: int = 30) -> str:
    start, end = window_bounds(days)
    return f"Analysis period: {start.date().isoformat()} – {end.date().isoformat()}"


def build_review_records(conversations: pd.DataFrame, analysis: pd.DataFrame) -> pd.DataFrame:
    """One row per collected conversation, with analysis columns when present."""
    if conversations.empty:
        return conversations
    left = conversations.copy()
    if analysis.empty:
        for col in ANALYSIS_COLS:
            if col not in left.columns:
                left[col] = None
        return left
    keep = [c for c in ANALYSIS_COLS if c in analysis.columns]
    right = analysis[keep].drop_duplicates(subset=["conversation_id"]) if "conversation_id" in keep else analysis
    merged = left.merge(right, left_on="id", right_on="conversation_id", how="left", suffixes=("", "_an"))
    return merged


def source_summary(conversations: pd.DataFrame) -> pd.DataFrame:
    """Counts and last publication time from the real collected corpus only."""
    labels = SOURCE_LABELS
    rows = []
    if conversations.empty:
        for key, label in labels:
            rows.append({"Source": label, "Records": 0, "Last review": "—"})
        return pd.DataFrame(rows)
    ts = pd.to_datetime(conversations.get("published_at"), utc=True, errors="coerce")
    src = conversations["source"].fillna("")
    for key, label in labels:
        mask = src == key
        n = int(mask.sum())
        last = ts[mask].max() if n else pd.NaT
        rows.append(
            {
                "Source": label,
                "Records": n,
                "Last review": str(last) if pd.notna(last) else "—",
            }
        )
    other = ~src.isin([k for k, _ in labels])
    if int(other.sum()):
        last = ts[other].max()
        rows.append(
            {
                "Source": "Other",
                "Records": int(other.sum()),
                "Last review": str(last) if pd.notna(last) else "—",
            }
        )
    return pd.DataFrame(rows)


def filter_review_records(
    records: pd.DataFrame,
    *,
    preset: str = "last_30_days",
    source: list[str] | None = None,
    sentiment: list[str] | None = None,
    intent: list[str] | None = None,
    category: list[str] | None = None,
    theme: str = "",
    rating: list | None = None,
    language: list[str] | None = None,
    segment: list[str] | None = None,
) -> pd.DataFrame:
    if records.empty:
        return records
    out = records.copy()
    ts = pd.to_datetime(out.get("published_at"), utc=True, errors="coerce")
    now = utcnow()
    if preset == "last_30_days":
        start, end = window_bounds(30, now=now)
        out = out[(ts >= start) & (ts <= end)]
    elif preset == "today":
        today = now.date()
        out = out[ts.dt.date == today]
    if source:
        out = out[out["source"].isin(source)]
    if sentiment and "sentiment" in out.columns:
        out = out[out["sentiment"].isin(sentiment)]
    if intent and "purchase_intent" in out.columns:
        out = out[out["purchase_intent"].isin(intent)]
    if rating and "rating" in out.columns:
        wanted: set[int] = set()
        for value in rating:
            try:
                wanted.add(int(float(value)))
            except (TypeError, ValueError):
                continue

        def _as_int(value):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None

        out = out[out["rating"].map(_as_int).isin(wanted)]
    if language and "language" in out.columns:
        out = out[out["language"].isin(language)]
    if segment and "user_segment" in out.columns:
        out = out[out["user_segment"].isin(segment)]
    if category and "fashion_category" in out.columns:
        out = out[out["fashion_category"].isin(category)]
    if theme and theme != "All":
        needle = theme.lower()
        blob = (
            out.get("primary_problem", pd.Series("", index=out.index)).fillna("").astype(str)
            + " "
            + out.get("uncertainty_type", pd.Series("", index=out.index)).fillna("").astype(str)
            + " "
            + out.get("purchase_blocker", pd.Series("", index=out.index)).fillna("").astype(str)
        ).str.lower()
        out = out[blob.str.contains(needle, regex=False)]
    return out
