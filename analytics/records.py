"""Merge collected conversations with analysis for Review Explorer."""

from __future__ import annotations

import pandas as pd

from processing.dates import utcnow, window_bounds, window_bounds_months

SOURCE_LABELS = [
    ("google_play", "Google Play Store"),
    ("youtube", "YouTube"),
    ("manual", "Manual Upload"),
]

# UI labels requested by the product dashboard (DB keys stay unchanged).
DISPLAY_SOURCE = {
    "google_play": "Google Play",
    "youtube": "YouTube",
    "manual": "Manual Upload",
}

PURCHASE_WISHLIST = {
    "explicit_wishlist",
    "comparison_shortlist",
    "occasion_planning",
}
BOOKMARK_WISHLIST = {
    "save_for_later",
    "cart_as_bookmark",
    "price_watch",
    "browsing_only",
}


def display_source(source: object) -> str:
    key = str(source or "").strip()
    if not key:
        return "Unknown"
    return DISPLAY_SOURCE.get(key, key)


def wishlist_intent_label(behavior: object) -> str:
    value = str(behavior or "").strip()
    if not value or value.lower() in {"unknown", "unclear", "nan", "none"}:
        return "not analyzed"
    if value in PURCHASE_WISHLIST:
        return "purchase intent"
    if value in BOOKMARK_WISHLIST:
        return "bookmarking"
    return value


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


def month_period_label(months: int) -> str:
    start, end = window_bounds_months(months)
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


def corpus_stats(conversations: pd.DataFrame) -> dict:
    """Counts and date span from stored rows only. Never invents values."""
    empty = {
        "total": 0,
        "google_play": 0,
        "youtube": 0,
        "manual": 0,
        "sources_active": 0,
        "earliest": None,
        "latest": None,
        "average_rating": None,
        "rated_count": 0,
    }
    if conversations is None or conversations.empty:
        return empty
    src = conversations["source"].fillna("") if "source" in conversations.columns else pd.Series([], dtype=str)
    play = int((src == "google_play").sum())
    youtube = int((src == "youtube").sum())
    manual = int((src == "manual").sum())
    active = int(src[src.astype(str).str.strip() != ""].nunique()) if len(src) else 0
    ts = pd.to_datetime(conversations.get("published_at"), utc=True, errors="coerce")
    earliest = ts.min() if ts.notna().any() else None
    latest = ts.max() if ts.notna().any() else None
    rated_count = 0
    average_rating = None
    if "rating" in conversations.columns:
        ratings = pd.to_numeric(conversations["rating"], errors="coerce").dropna()
        rated_count = int(len(ratings))
        if rated_count:
            average_rating = round(float(ratings.mean()), 2)
    return {
        "total": int(len(conversations)),
        "google_play": play,
        "youtube": youtube,
        "manual": manual,
        "sources_active": active,
        "earliest": earliest,
        "latest": latest,
        "average_rating": average_rating,
        "rated_count": rated_count,
    }


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
    keyword: str = "",
    wishlist_intent: list[str] | None = None,
) -> pd.DataFrame:
    if records.empty:
        return records
    out = records.copy()
    ts = pd.to_datetime(out.get("published_at"), utc=True, errors="coerce")
    now = utcnow()
    if preset == "last_30_days":
        start, end = window_bounds(30, now=now)
        out = out[(ts >= start) & (ts <= end)]
        ts = pd.to_datetime(out.get("published_at"), utc=True, errors="coerce")
    elif preset == "last_6_months":
        start, end = window_bounds_months(6, now=now)
        out = out[(ts >= start) & (ts <= end)]
        ts = pd.to_datetime(out.get("published_at"), utc=True, errors="coerce")
    elif preset == "last_12_months":
        start, end = window_bounds_months(12, now=now)
        out = out[(ts >= start) & (ts <= end)]
        ts = pd.to_datetime(out.get("published_at"), utc=True, errors="coerce")
    elif preset in {"last_30_months", "all_in_window"}:
        start, end = window_bounds_months(30, now=now)
        out = out[(ts >= start) & (ts <= end)]
        ts = pd.to_datetime(out.get("published_at"), utc=True, errors="coerce")
    elif preset == "today":
        today = now.date()
        out = out[ts.dt.date == today]
        ts = pd.to_datetime(out.get("published_at"), utc=True, errors="coerce")
    elif preset in {"all_collected", "all"}:
        pass
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
    if wishlist_intent and "wishlist_behavior" in out.columns:
        wanted = {str(x) for x in wishlist_intent}
        labels = out["wishlist_behavior"].map(wishlist_intent_label)
        out = out[labels.isin(wanted) | out["wishlist_behavior"].isin(wanted)]
    if keyword and str(keyword).strip():
        needle = str(keyword).strip().lower()
        blob = (
            out.get("original_text", pd.Series("", index=out.index)).fillna("").astype(str)
            + " "
            + out.get("text", pd.Series("", index=out.index)).fillna("").astype(str)
            + " "
            + out.get("title", pd.Series("", index=out.index)).fillna("").astype(str)
            + " "
            + out.get("video_title", pd.Series("", index=out.index)).fillna("").astype(str)
        ).str.lower()
        out = out[blob.str.contains(needle, regex=False)]
    return out
