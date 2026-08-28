"""Wishlist behavior distributions."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import empty_state, filter_analysis

BEHAVIOR_LABELS = {
    "explicit_wishlist": "Genuine / explicit wishlist",
    "save_for_later": "Save for later / bookmarking",
    "cart_as_bookmark": "Cart as bookmark",
    "price_watch": "Price watch",
    "comparison_shortlist": "Comparison shortlist",
    "occasion_planning": "Occasion planning",
    "browsing_only": "Browsing only",
    "unclear": "Unclear",
}


def render(analysis: pd.DataFrame, filters: dict) -> None:
    st.subheader("Wishlist Behavior")
    st.caption("ANALYZED DATA — labels from conversation text, not Myntra event logs.")
    df = filter_analysis(analysis, filters)
    relevant = df[df["relevant_to_wishlist"] == True] if not df.empty else df  # noqa: E712
    if relevant.empty:
        empty_state()
        return

    relevant = relevant.copy()
    relevant["behavior_label"] = relevant["wishlist_behavior"].map(BEHAVIOR_LABELS).fillna(
        relevant["wishlist_behavior"]
    )
    counts = relevant["behavior_label"].value_counts().reset_index()
    counts.columns = ["Wishlist behavior", "Conversations"]
    fig = px.bar(counts, x="Wishlist behavior", y="Conversations", color="Wishlist behavior")
    fig.update_layout(showlegend=False, height=380)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Wishlist behavior × purchase status")
    cross = pd.crosstab(relevant["behavior_label"], relevant["purchase_status"])
    st.dataframe(cross, use_container_width=True)
    heat = px.imshow(
        cross,
        aspect="auto",
        color_continuous_scale="RdPu",
        title="Behavior × status (counts, not conversion rates)",
    )
    st.plotly_chart(heat, use_container_width=True)

    intent = relevant["purchase_intent"].value_counts().reset_index()
    intent.columns = ["Purchase intent", "Conversations"]
    st.plotly_chart(
        px.pie(intent, names="Purchase intent", values="Conversations", title="Purchase intent (labeled)"),
        use_container_width=True,
    )
