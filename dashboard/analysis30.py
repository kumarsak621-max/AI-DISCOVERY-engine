"""30-Day Analysis — quantified themes and source comparison from stored records."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.quantify import source_comparison, source_counts, theme_quantification
from analytics.records import analysis_period_label, build_review_records
from dashboard.ui import empty_state


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    *,
    last_collection=None,
    last_ai=None,
    last_stats: dict | None = None,
) -> bool:
    st.subheader("30-Day Analysis")
    st.caption(analysis_period_label(30))
    st.markdown(
        "Themes, sentiment, purchase intent, and segments below are **AI labels on real collected records**. "
        "Percentages are of relevant analyzed public conversations — not of Myntra users."
    )

    records = build_review_records(conversations, analysis)
    counts = source_counts(records)
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Last collection", str(last_collection or "Never"))
    f2.metric("Last analysis", str(last_ai or "Never"))
    f3.metric("30-day records", counts.get("Total", 0))
    f4.metric("New records (last run)", (last_stats or {}).get("new", "—"))

    analyze = st.button("Analyze 30-Day Data", type="primary")
    st.caption("Loads stored last-30-day records, batches them to OpenRouter, then requantifies themes.")

    if records.empty:
        empty_state("No real records were collected from this source during the selected period.")
        return bool(analyze)

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
        st.info("No analyzed themes yet. Use **Analyze 30-Day Data** after collection. Numbers are not invented.")
    else:
        st.dataframe(themes, use_container_width=True, hide_index=True)
        st.caption("Share of relevant records uses only rows labeled relevant_to_wishlist when that set is non-empty.")

    st.markdown("#### Source comparison")
    compare = source_comparison(records)
    if compare.empty:
        empty_state("No real records were collected from this source during the selected period.")
    else:
        st.dataframe(compare, use_container_width=True, hide_index=True)
        st.caption("Top labels are the mode of stored AI fields per source. Empty sources stay at zero.")
    return bool(analyze)
