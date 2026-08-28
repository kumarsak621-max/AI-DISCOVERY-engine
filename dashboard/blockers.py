"""Purchase blockers."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.metrics import explode_blockers
from dashboard.ui import empty_state, filter_analysis


def render(analysis: pd.DataFrame, filters: dict) -> None:
    st.subheader("Purchase Blockers")
    st.caption("Do not infer a blocker unless the evidence supports it. These are labeled mentions.")
    df = filter_analysis(analysis, filters)
    relevant = df[df["relevant_to_wishlist"] == True] if not df.empty else df  # noqa: E712
    if relevant.empty:
        empty_state()
        return

    exploded = explode_blockers(relevant)
    freq = exploded.value_counts().reset_index()
    freq.columns = ["Blocker", "Frequency"]
    st.plotly_chart(px.bar(freq, x="Blocker", y="Frequency"), use_container_width=True)

    rows = []
    for _, row in relevant.iterrows():
        blockers = row["blockers"] if isinstance(row["blockers"], list) else [row["purchase_blocker"]]
        for b in blockers:
            rows.append(
                {
                    "blocker": b,
                    "segment": row["user_segment"],
                    "category": row["fashion_category"],
                    "high_intent": bool(row["high_intent_friction"]),
                }
            )
    long = pd.DataFrame(rows)
    if long.empty:
        return

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Blocker by segment")
        seg = pd.crosstab(long["blocker"], long["segment"])
        st.dataframe(seg, use_container_width=True)
    with c2:
        st.markdown("#### Blocker by fashion category")
        cat = pd.crosstab(long["blocker"], long["category"])
        st.dataframe(cat, use_container_width=True)

    st.markdown("#### Blockers among high-intent friction users")
    hi = long[long["high_intent"] == True]  # noqa: E712
    if hi.empty:
        st.info("No high-intent friction conversations in the current filter.")
    else:
        hi_counts = hi["blocker"].value_counts().reset_index()
        hi_counts.columns = ["Blocker", "High-intent mentions"]
        st.plotly_chart(px.bar(hi_counts, x="Blocker", y="High-intent mentions"), use_container_width=True)
