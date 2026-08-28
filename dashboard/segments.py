"""Segment explorer."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import empty_state, filter_analysis


def render(analysis: pd.DataFrame, opportunities: pd.DataFrame, filters: dict) -> None:
    st.subheader("Segment Explorer")
    st.caption("Behavioral segments inferred from text. Insufficient evidence → unknown.")
    df = filter_analysis(analysis, filters)
    relevant = df[df["relevant_to_wishlist"] == True] if not df.empty else df  # noqa: E712
    if relevant.empty:
        empty_state()
        return

    segments = sorted(relevant["user_segment"].dropna().unique().tolist())
    chosen = st.selectbox("Segment", segments)
    subset = relevant[relevant["user_segment"] == chosen]

    c1, c2, c3 = st.columns(3)
    c1.metric("Conversations", len(subset))
    c2.metric("High-intent friction", int(subset["high_intent_friction"].sum()))
    c3.metric("Avg confidence", f"{subset['confidence'].mean():.2f}")

    col1, col2 = st.columns(2)
    with col1:
        b = subset["wishlist_behavior"].value_counts().reset_index()
        b.columns = ["Wishlist behavior", "n"]
        st.plotly_chart(px.bar(b, x="Wishlist behavior", y="n", title="Wishlist behavior"), use_container_width=True)
        i = subset["purchase_intent"].value_counts().reset_index()
        i.columns = ["Intent", "n"]
        st.plotly_chart(px.pie(i, names="Intent", values="n", title="Purchase intent"), use_container_width=True)
    with col2:
        blk = subset["purchase_blocker"].value_counts().reset_index()
        blk.columns = ["Blocker", "n"]
        st.plotly_chart(px.bar(blk, x="Blocker", y="n", title="Blockers"), use_container_width=True)
        u = subset["uncertainty_type"].value_counts().reset_index()
        u.columns = ["Uncertainty", "n"]
        st.plotly_chart(px.bar(u, x="Uncertainty", y="n", title="Uncertainties"), use_container_width=True)

    st.markdown("#### Workarounds")
    w = subset["external_information_source"].value_counts().reset_index()
    w.columns = ["External source", "n"]
    st.dataframe(w, hide_index=True, use_container_width=True)

    st.markdown("#### Top opportunities overlapping this segment")
    if not opportunities.empty:
        overlap = opportunities[opportunities["user_segment"] == chosen]
        if overlap.empty:
            st.write("No opportunity is concentrated in this segment; see global ranking.")
            st.dataframe(
                opportunities[["opportunity_name", "user_segment", "opportunity_score"]].head(5),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.dataframe(
                overlap[
                    [
                        "opportunity_name",
                        "evidence_count",
                        "conversion_relevance_score",
                        "opportunity_score",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )

    st.markdown("#### Segment evidence quotes")
    for _, row in subset.head(15).iterrows():
        st.markdown(f"- {row['segment_evidence']} — “{row['evidence_quote']}”")
