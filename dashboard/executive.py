"""Executive discovery page."""

from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.metrics import funnel_summary, kpi_counts
from analytics.trends import theme_trend_frame
from dashboard.ui import data_layer_caption, empty_state


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    opportunities: pd.DataFrame,
    summary: dict | None,
) -> None:
    st.subheader("Executive Discovery")
    data_layer_caption()

    if conversations.empty:
        empty_state()
        return

    kpis = kpi_counts(conversations, analysis)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Public conversations", kpis["total_conversations"])
    c2.metric("Relevant", kpis["relevant"])
    c3.metric("Wishlist-related", kpis["wishlist_related"])
    c4.metric("High-intent friction", kpis["high_intent"])
    c5.metric("Purchase-blocker mentions", kpis["purchase_blocker"])
    c6.metric("Unique sources", kpis.get("unique_sources") or 0)

    st.markdown("## Top Opportunity Areas")
    st.caption("Research-Based Opportunity Score — not causal evidence.")
    if opportunities.empty:
        empty_state("No opportunities scored yet. Collect and analyze live conversations.")
        return

    top = opportunities.head(10).copy()
    display = pd.DataFrame(
        {
            "Rank": list(range(1, len(top) + 1)),
            "Opportunity": top["opportunity_name"],
            "Segment": top["user_segment"],
            "Evidence Count": top["evidence_count"],
            "High-Intent %": top["conversion_relevance_score"],
            "Conversion Relevance": top["conversion_relevance_score"],
            "Opportunity Score": top["opportunity_score"],
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)

    lead = top.iloc[0]
    st.markdown(
        f"""
Among the analyzed public conversations, **{lead['opportunity_name']}** appears frequently,
particularly among **{lead['user_segment']}**. Several high-intent conversations explicitly
describe related friction while considering, postponing, waiting, or abandoning. This makes it a
high-priority **hypothesis** to validate through primary research. Research-Based Opportunity Score:
**{lead['opportunity_score']}**.
"""
    )

    evidence = []
    try:
        evidence = json.loads(lead["supporting_evidence"] or "[]")
    except json.JSONDecodeError:
        evidence = []
    if evidence:
        st.markdown("#### Supporting quotes (must appear in original text)")
        for item in evidence[:3]:
            url = item.get("url") or ""
            link = f"[Open Original Source]({url})" if url else ""
            st.markdown(f"- “{item.get('quote')}” — `{item.get('source')}` · {link}")

    st.markdown("### 30-day theme trend (publication date)")
    trends = theme_trend_frame(analysis)
    if trends.empty:
        st.caption("Not enough dated conversations to plot a trend.")
    else:
        fig = px.line(trends, x="day", y="mentions", color="theme", title="Daily theme mentions")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Conceptual wishlist funnel (INFERRED from conversation labels)")
    funnel = funnel_summary(analysis)
    if not funnel.empty:
        st.dataframe(funnel, use_container_width=True, hide_index=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Explore Evidence", use_container_width=True):
            st.session_state["nav_page"] = "Evidence Explorer"
            st.rerun()
    with col_b:
        if st.button("Generate Research Brief", use_container_width=True):
            st.session_state["nav_page"] = "AI Research Brief"
            st.rerun()
