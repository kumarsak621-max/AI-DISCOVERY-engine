"""Theme trends over the research window (publication date)."""

from __future__ import annotations

import pandas as pd


def theme_trend_frame(analysis: pd.DataFrame) -> pd.DataFrame:
    if analysis.empty:
        return pd.DataFrame()
    relevant = analysis[analysis["relevant_to_wishlist"] == True].copy()  # noqa: E712
    if relevant.empty:
        return pd.DataFrame()
    relevant["published_at"] = pd.to_datetime(relevant["published_at"], utc=True, errors="coerce")
    relevant = relevant.dropna(subset=["published_at"])
    if relevant.empty:
        return pd.DataFrame()

    def theme_name(row: pd.Series) -> str:
        blocker = row.get("purchase_blocker") or "unknown"
        mapping = {
            "size_uncertainty": "FIT CONFIDENCE",
            "fit_uncertainty": "FIT CONFIDENCE",
            "appearance_uncertainty": "FIT CONFIDENCE",
            "price_uncertainty": "PRICE TIMING / PURCHASE DELAY",
            "waiting_for_price_drop": "PRICE TIMING / PURCHASE DELAY",
            "budget_constraint": "PRICE TIMING / PURCHASE DELAY",
            "quality_uncertainty": "QUALITY / FABRIC CONFIDENCE",
            "fabric_uncertainty": "QUALITY / FABRIC CONFIDENCE",
            "review_uncertainty": "REVIEW TRUST GAP",
            "trust_uncertainty": "REVIEW TRUST GAP",
            "styling_uncertainty": "STYLING / OCCASION FIT",
            "occasion_uncertainty": "STYLING / OCCASION FIT",
            "comparison_uncertainty": "COMPARISON PARALYSIS",
            "return_uncertainty": "RETURNS FRICTION",
            "delivery_uncertainty": "DELIVERY UNCERTAINTY",
            "social_validation": "SOCIAL VALIDATION GAP",
            "availability_uncertainty": "AVAILABILITY / SIZE STOCK",
            "indecision": "LOW URGENCY / INDECISION",
            "low_urgency": "LOW URGENCY / INDECISION",
            "discovered_better_alternative": "ALTERNATIVE LEAKAGE",
            "better_alternative": "ALTERNATIVE LEAKAGE",
        }
        return mapping.get(str(blocker), str(blocker).replace("_", " ").upper())

    relevant["theme"] = relevant.apply(theme_name, axis=1)
    relevant["day"] = relevant["published_at"].dt.floor("D")
    relevant["week"] = relevant["published_at"].dt.to_period("W").astype(str)
    daily = (
        relevant.groupby(["theme", "day"])
        .agg(
            mentions=("id", "count"),
            high_intent=("high_intent_friction", "sum"),
            blocker_mentions=("purchase_blocker", lambda s: int((~s.isin(["no_blocker", "unknown", ""])).sum())),
        )
        .reset_index()
    )
    return daily


def weekly_theme_summary(analysis: pd.DataFrame) -> pd.DataFrame:
    daily = theme_trend_frame(analysis)
    if daily.empty:
        return daily
    daily["week"] = pd.to_datetime(daily["day"], utc=True).dt.to_period("W").astype(str)
    return (
        daily.groupby(["theme", "week"], as_index=False)
        .agg(
            weekly_mentions=("mentions", "sum"),
            high_intent_mentions=("high_intent", "sum"),
            purchase_blocker_mentions=("blocker_mentions", "sum"),
        )
    )


KEYWORD_SERIES = {
    "fit": ("fit", "fitting", "too tight", "too loose"),
    "size": ("size", "sizing", "size chart", "wrong size"),
    "price": ("price", "expensive", "sale", "discount", "costly"),
    "quality": ("quality", "fabric", "cheap", "material"),
    "delivery": ("delivery", "late", "shipping", "courier"),
    "returns": ("return", "refund", "exchange"),
    "trust": ("fake review", "trust", "scam", "genuine"),
    "wishlist": ("wishlist", "wish list", "saved", "bookmark"),
    "purchase_intent": None,
}


def classify_trend(recent: float, previous: float, min_n: int = 8) -> str:
    if recent + previous < min_n:
        return "Insufficient Evidence"
    if previous == 0:
        return "Increasing" if recent >= min_n else "Insufficient Evidence"
    change = (recent - previous) / previous
    if change >= 0.15:
        return "Increasing"
    if change <= -0.15:
        return "Decreasing"
    return "Stable"


def monthly_volume_frame(conversations: pd.DataFrame) -> pd.DataFrame:
    if conversations.empty:
        return pd.DataFrame()
    frame = conversations.copy()
    frame["published_at"] = pd.to_datetime(frame["published_at"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["published_at"])
    if frame.empty:
        return pd.DataFrame()
    frame["month"] = frame["published_at"].dt.to_period("M").astype(str)
    return frame.groupby("month", as_index=False).size().rename(columns={"size": "records"})


def monthly_signal_trends(conversations: pd.DataFrame, analysis: pd.DataFrame) -> pd.DataFrame:
    """Keyword/label monthly counts from stored records only. Empty → no invented trend."""
    if conversations.empty:
        return pd.DataFrame()
    merged = conversations.copy()
    if not analysis.empty and "conversation_id" in analysis.columns:
        keep = [c for c in ("conversation_id", "purchase_intent", "purchase_blocker", "primary_problem") if c in analysis.columns]
        merged = merged.merge(analysis[keep], left_on="id", right_on="conversation_id", how="left")
    merged["published_at"] = pd.to_datetime(merged["published_at"], utc=True, errors="coerce")
    merged = merged.dropna(subset=["published_at"])
    if merged.empty:
        return pd.DataFrame()
    blob = (
        merged.get("original_text", pd.Series("", index=merged.index)).fillna("").astype(str)
        + " "
        + merged.get("text", pd.Series("", index=merged.index)).fillna("").astype(str)
        + " "
        + merged.get("primary_problem", pd.Series("", index=merged.index)).fillna("").astype(str)
        + " "
        + merged.get("purchase_blocker", pd.Series("", index=merged.index)).fillna("").astype(str)
    ).str.lower()
    merged["month"] = merged["published_at"].dt.to_period("M").astype(str)
    months = sorted(merged["month"].unique())
    if len(months) < 2:
        mid = months
        recent_months, previous_months = months, []
    else:
        split = max(1, len(months) // 2)
        previous_months, recent_months = months[:split], months[split:]
    rows = []
    volume = merged.groupby("month").size()
    recent_vol = int(sum(int(volume.get(m, 0)) for m in recent_months))
    prev_vol = int(sum(int(volume.get(m, 0)) for m in previous_months))
    rows.append(
        {
            "Signal": "review volume",
            "Recent records": recent_vol,
            "Earlier records": prev_vol,
            "Trend": classify_trend(recent_vol, prev_vol),
        }
    )
    for name, terms in KEYWORD_SERIES.items():
        if name == "purchase_intent":
            if "purchase_intent" not in merged.columns:
                count_recent = count_prev = 0
            else:
                high = merged["purchase_intent"].fillna("").astype(str).str.lower().eq("high")
                count_recent = int(merged.loc[high & merged["month"].isin(recent_months)].shape[0])
                count_prev = int(merged.loc[high & merged["month"].isin(previous_months)].shape[0])
        else:
            mask = False
            for term in terms or ():
                part = blob.str.contains(term, regex=False)
                mask = part if mask is False else (mask | part)
            if mask is False:
                count_recent = count_prev = 0
            else:
                count_recent = int(merged.loc[mask & merged["month"].isin(recent_months)].shape[0])
                count_prev = int(merged.loc[mask & merged["month"].isin(previous_months)].shape[0])
        rows.append(
            {
                "Signal": name,
                "Recent records": count_recent,
                "Earlier records": count_prev,
                "Trend": classify_trend(count_recent, count_prev),
            }
        )
    return pd.DataFrame(rows)
