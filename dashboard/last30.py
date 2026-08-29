"""Last 30 Days — every collected record in the publication-date window."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.records import analysis_period_label, build_review_records, filter_review_records
from dashboard.review_cards import render_review_card
from dashboard.ui import empty_state


def render(conversations: pd.DataFrame, analysis: pd.DataFrame) -> None:
    st.subheader("Last 30 Days")
    st.markdown("**Last 30 Days** of real public reviews and conversations by **publication date**, not collection date.")
    st.caption(analysis_period_label(30))

    records = build_review_records(conversations, analysis)
    view = filter_review_records(records, preset="last_30_days")
    st.metric("Records published in the last 30 days", int(len(view)))
    if view.empty:
        empty_state("No real reviews were collected for this period.")
        return

    show = view.sort_values("published_at", ascending=False, na_position="last")
    total = int(len(show))
    page_size = 20
    pages = max((total + page_size - 1) // page_size, 1)
    page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key="last30_page")
    start = (int(page) - 1) * page_size
    st.caption(f"Showing {start + 1}–{min(start + page_size, total)} of {total}")
    for _, row in show.iloc[start : start + page_size].iterrows():
        render_review_card(row)
