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
