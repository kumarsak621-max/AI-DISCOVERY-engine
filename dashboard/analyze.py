"""Analyze Reviews — themes, trends, source comparison, audit trail."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.quantify import source_comparison, source_counts, theme_quantification
from analytics.records import analysis_period_label, build_review_records, month_period_label
from analytics.trends import monthly_signal_trends, monthly_volume_frame
from config import WINDOW_PRESETS
from dashboard.ui import empty_state
from processing.dates import days_covering_months, window_bounds_months


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    *,
    last_collection=None,
    last_ai=None,
    last_stats: dict | None = None,
    audit: dict | None = None,
    default_preset: str = "Last 30 days",
) -> dict:
    st.subheader("Analyze")
    st.markdown(
        "Themes, intent, uncertainty, and segments are **AI labels on real collected records**. "
        "Percentages are of relevant analyzed public conversations — not of Myntra users. "
        "Default analysis window is **last 30 days** because the business metric is purchase within 30 days of wishlist add."
    )

    presets = list(WINDOW_PRESETS.keys()) + ["Custom date range"]
    idx = presets.index(default_preset) if default_preset in presets else 0
    preset = st.selectbox("Analysis period", presets, index=idx)
    range_start = range_end = None
    window_days = 30
    window_months = None
    if preset == "Custom date range":
        hist_start, hist_end = window_bounds_months(30)
        picked = st.date_input(
            "Custom range (publication date)",
            value=(hist_end.date(), hist_end.date()),
        )
        if isinstance(picked, (tuple, list)) and len(picked) == 2:
            range_start, range_end = picked[0], picked[1]
            period_label = f"Analysis period: {range_start} – {range_end}"
        else:
            period_label = analysis_period_label(30)
    else:
        spec = WINDOW_PRESETS[preset]
        if "months" in spec:
            window_months = int(spec["months"])
            window_days = days_covering_months(window_months)
            period_label = month_period_label(window_months)
        else:
            window_days = int(spec["days"])
            period_label = analysis_period_label(window_days)
    st.caption(period_label)

    records = build_review_records(conversations, analysis)
    counts = source_counts(records)
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Last collection", str(last_collection or "Never"))
    f2.metric("Last analysis", str(last_ai or "Never"))
    f3.metric("Records in view", counts.get("Total", 0))
    f4.metric("New records (last run)", (last_stats or {}).get("new", "—"))

    analyze = st.button("Analyze Reviews", type="primary", key="analyze_page_run")
    st.caption("Loads stored records in the selected publication-date range and batches them to the selected AI provider.")

    audit = audit or (last_stats or {}).get("analysis_audit") or {}
    if audit:
        st.markdown("#### AI analysis audit")
        a1, a2, a3, a4, a5 = st.columns(5)
        a1.metric("AI Provider", audit.get("ai_provider") or "—")
        a2.metric("AI Model", audit.get("ai_model") or "—")
        a3.caption(f"Analysis date: {audit.get('analysis_date') or '—'}")
        a4.caption(
            f"Dataset: {audit.get('dataset_start') or '—'} → {audit.get('dataset_end') or '—'}"
        )
        a5.metric("Records analyzed", audit.get("records_analyzed", audit.get("analyzed", "—")))

    if records.empty:
        empty_state("No real records were collected from this source during the selected period.")
        return {
            "analyze": bool(analyze),
            "window_days": window_days,
            "window_months": window_months,
            "range_start": range_start,
            "range_end": range_end,
        }

    st.markdown("#### Source mix (database)")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Google Play", counts.get("Google Play Store", 0))
    c2.metric("YouTube", counts.get("YouTube", 0))
    c3.metric("Reddit", counts.get("Reddit", 0))
    c4.metric("Web communities", counts.get("Web/Fashion Communities", 0))
    c5.metric("Apple App Store", counts.get("Apple App Store", 0))

    themes = theme_quantification(records)
    st.markdown("#### Quantified themes")
    if themes.empty:
        st.info("No analyzed themes yet. Use **Analyze Reviews** after collection. Numbers are not invented.")
    else:
        st.dataframe(themes, use_container_width=True, hide_index=True)
        st.caption("Share of relevant records uses only rows labeled relevant_to_wishlist when that set is non-empty.")

    st.markdown("#### Source comparison (Google Play vs YouTube and others)")
    compare = source_comparison(records)
    if compare.empty:
        empty_state("No real records were collected from this source during the selected period.")
    else:
        st.dataframe(compare, use_container_width=True, hide_index=True)
        play_n = int(compare.loc[compare["Source"] == "Google Play Store", "Records"].sum()) if not compare.empty else 0
        yt_n = int(compare.loc[compare["Source"] == "YouTube", "Records"].sum()) if not compare.empty else 0
        if play_n == 0:
            st.caption("Google Play individual reviews were not stored for this window (source may be unavailable).")
        if yt_n == 0:
            st.caption("YouTube comments were not stored for this window (key missing or no matching public comments).")

    st.markdown("#### Monthly trends (publication date)")
    volume = monthly_volume_frame(conversations)
    if volume.empty:
        st.info("Insufficient evidence in the collected dataset.")
    else:
        st.dataframe(volume, use_container_width=True, hide_index=True)
        st.bar_chart(volume.set_index("month")["records"])
    signals = monthly_signal_trends(conversations, analysis)
    if signals.empty:
        st.info("Insufficient evidence in the collected dataset.")
    else:
        st.dataframe(signals, use_container_width=True, hide_index=True)
        st.caption("Trend labels use stored record counts only. Insufficient Evidence means too few dated records to compare halves of the window.")

    return {
        "analyze": bool(analyze),
        "window_days": window_days,
        "window_months": window_months,
        "range_start": range_start,
        "range_end": range_end,
    }
