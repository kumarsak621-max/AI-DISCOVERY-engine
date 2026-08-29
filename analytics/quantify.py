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


def theme_quantification(records: pd.DataFrame) -> pd.DataFrame:
    """One row per theme with counts and % of relevant records. Empty if none analyzed."""
    relevant = relevant_subset(records)
    if relevant.empty or "primary_problem" not in relevant.columns:
        return pd.DataFrame()
    n = len(relevant)
    theme = relevant["primary_problem"].fillna("").astype(str).str.strip()
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
                "Reddit": int(src.get("reddit", 0)),
                "Web/Fashion Communities": int(src.get("web", 0)),
                "Apple App Store": int(src.get("app_store", 0)),
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
                "Top theme": _top("primary_problem"),
                "Top sentiment": _top("sentiment"),
                "Top purchase intent": _top("purchase_intent"),
                "Top uncertainty": _top("uncertainty_type"),
                "Top wishlist behavior": _top("wishlist_behavior"),
            }
        )
    return pd.DataFrame(rows)


def retrieved_quantification(retrieved: pd.DataFrame) -> dict:
    """Counts for chatbot answers — only the retrieved stored rows."""
    if retrieved.empty:
        return {"n": 0, "sources": {}, "themes": {}, "intents": {}}
    sources = retrieved["source"].fillna("").value_counts().to_dict() if "source" in retrieved.columns else {}
    themes = {}
    if "primary_problem" in retrieved.columns:
        themes = retrieved["primary_problem"].fillna("").astype(str).value_counts().head(5).to_dict()
    intents = {}
    if "purchase_intent" in retrieved.columns:
        intents = retrieved["purchase_intent"].fillna("").astype(str).value_counts().to_dict()
    return {
        "n": int(len(retrieved)),
        "sources": {str(k): int(v) for k, v in sources.items() if str(k)},
        "themes": {str(k): int(v) for k, v in themes.items() if str(k).strip()},
        "intents": {str(k): int(v) for k, v in intents.items() if str(k).strip()},
    }
