"""Shared dashboard helpers and labeling."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from analytics.records import display_source
from config import DISCLAIMER

APP_CSS = """
<style>
    .stApp { background: #f5f7fb; }
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e6e9f0;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #1b2437 !important;
    }
    h1, h2, h3 { color: #1b2437 !important; }
    .block-container { padding-top: 1.4rem; max-width: 1280px; }
    div[data-testid="stMetricValue"] { color: #ff3f6c; font-weight: 700; }
    div[data-testid="stMetricLabel"] { color: #5b6475; }
    .hero-title { font-size: 1.85rem; font-weight: 750; color: #1b2437; margin-bottom: 0.15rem; }
    .hero-sub { color: #5b6475; font-size: 0.98rem; line-height: 1.45; margin-bottom: 0.8rem; }
    .section-label {
        font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase;
        color: #7a8494; font-weight: 700; margin: 1.1rem 0 0.55rem;
    }
    .status-pill {
        display: inline-block; padding: 0.18rem 0.55rem; border-radius: 999px;
        font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em;
    }
    .pill-ok { background: #e7f7ee; color: #147a3f; }
    .pill-ready { background: #e8eefc; color: #1f4b99; }
    .pill-off { background: #fff1d6; color: #8a5a00; }
    .pill-err { background: #fde8ea; color: #b42318; }
    .funnel-step {
        background: #fff; border: 1px solid #e6e9f0; border-radius: 10px;
        padding: 0.7rem 0.85rem; text-align: center; color: #1b2437; font-weight: 600;
    }
    .funnel-arrow { text-align: center; color: #9aa3b2; padding: 0.15rem 0; }
</style>
"""


def inject_theme() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="hero-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hero-sub">{subtitle}</div>', unsafe_allow_html=True)


def section_label(text: str) -> None:
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)


def banner() -> None:
    st.caption(DISCLAIMER)


def data_layer_caption() -> None:
    st.markdown(
        """
**How to read this dashboard**

| Layer | Meaning |
| --- | --- |
| RAW DATA | Public conversations collected from live sources |
| ANALYZED DATA | Per-conversation AI labels from the selected provider |
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


def empty_state(message: str = "No data collected.") -> None:
    st.info(message)


def status_pill(label: str, state: str) -> None:
    kind = {
        "CONNECTED": "pill-ok",
        "READY": "pill-ready",
        "NOT CONFIGURED": "pill-off",
        "ERROR": "pill-err",
        "FAILED": "pill-err",
    }.get(state, "pill-off")
    st.markdown(
        f"**{label}**<br><span class='status-pill {kind}'>{state}</span>",
        unsafe_allow_html=True,
    )


def readiness_state(*, configured: bool, ready_when_missing: bool = False, error: bool = False) -> str:
    if error:
        return "ERROR"
    if configured:
        return "CONNECTED" if not ready_when_missing else "READY"
    if ready_when_missing:
        return "READY"
    return "NOT CONFIGURED"


def format_source_series(values: pd.Series) -> pd.Series:
    return values.fillna("").map(display_source)


def overall_collection_status(source_results: list | None) -> str:
    items = source_results or []
    if not items:
        return "NO RUN"
    ok = sum(1 for item in items if str(item.get("status") or "") == "ok")
    bad = sum(1 for item in items if str(item.get("status") or "") in {"error", "unavailable"})
    if ok and bad:
        return "PARTIAL SUCCESS"
    if ok and not bad:
        return "SUCCESS"
    if bad:
        return "FAILED"
    return "NO RUN"
