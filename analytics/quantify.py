"""Quantify themes and source mix from real collected/analyzed records only."""

from __future__ import annotations

import pandas as pd

from analytics.records import SOURCE_LABELS


def relevant_subset(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return records
    if "relevant_to_wishlist" not in records.columns:
        return records
    rel = records[records["relevant_to_wishlist"] == True]  # noqa: E712
    return rel if not rel.empty else records


def source_counts(records: pd.DataFrame) -> dict[str, int]:
    labels = dict(SOURCE_LABELS)
    counts = {label: 0 for label in labels.values()}
    if records.empty or "source" not in records.columns:
        counts["Total"] = 0
        return counts
    raw = records["source"].fillna("").value_counts().to_dict()
    for key, label in SOURCE_LABELS:
        counts[label] = int(raw.get(key, 0))
    other = int(sum(v for k, v in raw.items() if k not in labels))
    if other:
        counts["Other"] = other
    counts["Total"] = int(len(records))
    return counts


def _theme_series(records: pd.DataFrame) -> pd.Series | None:
    if records.empty:
        return None
    if "theme" in records.columns:
        theme = records["theme"].fillna("").astype(str).str.strip()
        if theme.replace({"": None, "nan": None, "Unclear": None, "unknown": None}).notna().any():
            fallback = (
                records["primary_problem"].fillna("").astype(str).str.strip()
                if "primary_problem" in records.columns
                else pd.Series("", index=records.index)
            )
            return theme.where(theme.isin(["", "nan", "Unclear", "unknown"]) == False, fallback)  # noqa: E712
    if "primary_problem" in records.columns:
        return records["primary_problem"].fillna("").astype(str).str.strip()
    return None


def theme_quantification(records: pd.DataFrame) -> pd.DataFrame:
    """One row per theme with counts and % of relevant records. Empty if none analyzed."""
    relevant = relevant_subset(records)
    theme = _theme_series(relevant)
    if relevant.empty or theme is None:
        return pd.DataFrame()
    n = len(relevant)
    theme = theme.replace({"": "unspecified", "nan": "unspecified"})
    rows = []
    for name, group in relevant.groupby(theme, dropna=False):
        label = str(name or "unspecified")
        if label.lower() in {"unknown", "none", "nan", "unspecified"}:
            continue
        count = int(len(group))
        src = group["source"].value_counts().to_dict() if "source" in group.columns else {}
        sent = group["sentiment"].value_counts().to_dict() if "sentiment" in group.columns else {}
        seg = group["user_segment"].value_counts().to_dict() if "user_segment" in group.columns else {}
        rating_dist = {}
        if "rating" in group.columns:
            for value in group["rating"].dropna().tolist():
                try:
                    key = str(int(float(value)))
                except (TypeError, ValueError):
                    continue
                rating_dist[key] = rating_dist.get(key, 0) + 1
        rows.append(
            {
                "Theme": label,
                "Records": count,
                "Share of relevant records %": round(100.0 * count / n, 1) if n else 0.0,
                "Google Play Store": int(src.get("google_play", 0)),
                "YouTube": int(src.get("youtube", 0)),
                "Sentiment mix": ", ".join(f"{k}:{v}" for k, v in sent.items()) or "—",
                "Top segment": (max(seg, key=seg.get) if seg else "—"),
                "Rating mix": ", ".join(f"{k}★:{v}" for k, v in sorted(rating_dist.items())) or "—",
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Records", ascending=False).reset_index(drop=True)


def source_comparison(records: pd.DataFrame) -> pd.DataFrame:
    """Compare sources on themes, sentiment, intent, uncertainty, wishlist — from stored labels only."""
    if records.empty or "source" not in records.columns:
        return pd.DataFrame()
    rows = []
    for key, label in SOURCE_LABELS:
        part = records[records["source"] == key]
        n = int(len(part))
        if n == 0:
            rows.append(
                {
                    "Source": label,
                    "Records": 0,
                    "Relevant": 0,
                    "Top theme": "—",
                    "Top sentiment": "—",
                    "Top purchase intent": "—",
                    "Top uncertainty": "—",
                    "Top wishlist behavior": "—",
                }
            )
            continue
        relevant_n = 0
        if "relevant_to_wishlist" in part.columns:
            relevant_n = int((part["relevant_to_wishlist"] == True).sum())  # noqa: E712

        def _top(col: str) -> str:
            if col not in part.columns:
                return "—"
            series = part[col].dropna().astype(str)
            series = series[series.str.lower().isin(["", "unknown", "none", "nan"]) == False]  # noqa: E712
            if series.empty:
                return "—"
            return str(series.value_counts().index[0])

        rows.append(
            {
                "Source": label,
                "Records": n,
                "Relevant": relevant_n,
                "Top theme": _top("theme") if "theme" in part.columns and part["theme"].astype(str).str.strip().ne("").any() else _top("primary_problem"),
                "Top sentiment": _top("sentiment"),
                "Top purchase intent": _top("purchase_intent"),
                "Top uncertainty": _top("uncertainty_level") if "uncertainty_level" in part.columns else _top("uncertainty_type"),
                "Top wishlist behavior": _top("wishlist_intent") if "wishlist_intent" in part.columns else _top("wishlist_behavior"),
            }
        )
    return pd.DataFrame(rows)


def retrieved_quantification(retrieved: pd.DataFrame) -> dict:
    """Counts for chatbot answers — only the retrieved stored rows."""
    if retrieved.empty:
        return {"n": 0, "sources": {}, "themes": {}, "intents": {}}
    sources = retrieved["source"].fillna("").value_counts().to_dict() if "source" in retrieved.columns else {}
    themes = {}
    series = _theme_series(retrieved)
    if series is not None:
        themes = series.replace({"": None, "nan": None}).dropna().astype(str).value_counts().head(5).to_dict()
    intents = {}
    if "purchase_intent" in retrieved.columns:
        intents = retrieved["purchase_intent"].fillna("").astype(str).value_counts().to_dict()
    return {
        "n": int(len(retrieved)),
        "sources": {str(k): int(v) for k, v in sources.items() if str(k)},
        "themes": {str(k): int(v) for k, v in themes.items() if str(k).strip()},
        "intents": {str(k): int(v) for k, v in intents.items() if str(k).strip()},
    }


def signal_quantification(records: pd.DataFrame) -> pd.DataFrame:
    """Counts of observed signals among analyzed records only. Empty if none."""
    if records.empty:
        return pd.DataFrame()
    analyzed = records
    if "analysis_status" in records.columns:
        analyzed = records[records["analysis_status"].astype(str).str.lower() == "complete"]
    elif "sentiment" in records.columns:
        analyzed = records[records["sentiment"].notna()]
    n = int(len(analyzed))
    if n == 0:
        return pd.DataFrame()
    theme = _theme_series(analyzed)
    theme = theme.fillna("").astype(str).str.lower() if theme is not None else pd.Series("", index=analyzed.index)
    pain = analyzed["pain_point"].fillna("").astype(str) if "pain_point" in analyzed.columns else pd.Series("", index=analyzed.index)
    wish = (
        analyzed["wishlist_intent"].fillna("").astype(str).str.lower()
        if "wishlist_intent" in analyzed.columns
        else pd.Series("", index=analyzed.index)
    )
    intent = (
        analyzed["purchase_intent"].fillna("").astype(str).str.lower()
        if "purchase_intent" in analyzed.columns
        else pd.Series("", index=analyzed.index)
    )
    unc = (
        analyzed["uncertainty_level"].fillna("").astype(str).str.lower()
        if "uncertainty_level" in analyzed.columns
        else pd.Series("", index=analyzed.index)
    )
    unc_type = (
        analyzed["uncertainty_type"].fillna("").astype(str).str.lower()
        if "uncertainty_type" in analyzed.columns
        else pd.Series("", index=analyzed.index)
    )
    blob = (theme + " " + pain.str.lower() + " " + unc_type).fillna("")

    def _count(mask) -> tuple[int, float]:
        count = int(mask.sum())
        return count, round(100.0 * count / n, 1) if n else 0.0

    rows = []
    size_n, size_p = _count(blob.str.contains(r"size|fit", regex=True))
    rows.append({"Signal": "Size/Fit", "Records": size_n, "Share of analyzed records %": size_p})
    hes_n, hes_p = _count(
        intent.isin(["low", "medium"]) | blob.str.contains("hesitat|wait|later|not sure|uncertain", regex=True)
    )
    rows.append({"Signal": "Purchase hesitation", "Records": hes_n, "Share of analyzed records %": hes_p})
    wish_n, wish_p = _count(wish.isin(["high", "medium", "low"]))
    rows.append({"Signal": "Wishlist behavior", "Records": wish_n, "Share of analyzed records %": wish_p})
    unc_n, unc_p = _count(unc.isin(["high", "medium", "low"]))
    rows.append({"Signal": "Uncertainty", "Records": unc_n, "Share of analyzed records %": unc_p})
    if all(row["Records"] == 0 for row in rows):
        return pd.DataFrame()
    return pd.DataFrame(rows)
