"""AI Insights hub — existing discovery views, not a new model stack."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import brief as brief_page
from dashboard import executive as executive_page
from dashboard import part1 as part1_page


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    opportunities: pd.DataFrame,
    summary: dict | None,
    brief_md: str,
) -> None:
    st.subheader("AI Insights")
    st.caption("Insights are labeled from collected public conversations. They are not Myntra conversion analytics.")
    tab1, tab2, tab3 = st.tabs(["Executive", "Part 1 answers", "Research brief"])
    with tab1:
        executive_page.render(conversations, analysis, opportunities, summary)
    with tab2:
        part1_page.render(analysis, opportunities)
    with tab3:
        brief_page.render(brief_md)
