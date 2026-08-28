"""Shared dashboard helpers and labeling."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from config import DISCLAIMER


def banner() -> None:
    st.caption(DISCLAIMER)


def data_layer_caption() -> None:
    st.markdown(
        """
**How to read this dashboard**

| Layer | Meaning |
| --- | --- |
| RAW DATA | Public conversations collected from live sources |
| ANALYZED DATA | Per-conversation OpenRouter labels |
| INFERRED INSIGHT | Themes, scores, and hypotheses — not Myntra analytics |

Percentages are of the analyzed public corpus, not of Myntra's customer population.
"""
    )


def parse_json_col(value: object, default: list | dict | None = None):
    if default is None:
        default = []
    if isinstance(value, (list, dict)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def filter_analysis(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    source = filters.get("source") or []
    segment = filters.get("segment") or []
    category = filters.get("category") or []
    intent = filters.get("intent") or []
    status = filters.get("status") or []
    blocker = filters.get("blocker") or []
    if source:
        out = out[out["source"].isin(source)]
    if segment:
        out = out[out["user_segment"].isin(segment)]
    if category:
        out = out[out["fashion_category"].isin(category)]
    if intent:
        out = out[out["purchase_intent"].isin(intent)]
    if status:
        out = out[out["purchase_status"].isin(status)]
    if blocker:
        def has_blocker(items: object) -> bool:
            bag = items if isinstance(items, list) else [items]
            return any(b in bag for b in blocker)

        out = out[out["blockers"].apply(has_blocker)]
    date_range = filters.get("date_range")
    ts_col = "published_at" if "published_at" in out.columns else "timestamp"
    if date_range and len(date_range) == 2 and ts_col in out.columns:
        start, end = date_range
        ts = pd.to_datetime(out[ts_col], utc=True, errors="coerce")
        out = out[(ts.dt.date >= start) & (ts.dt.date <= end)]
    return out


def empty_state(message: str = "Run Collection Now to populate this view with live public data.") -> None:
    st.info(message)
