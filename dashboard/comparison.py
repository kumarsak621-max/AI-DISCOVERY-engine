"""Comparison Behavior — how users shortlist and compare products."""

from __future__ import annotations

from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.part1_answers import alternative_count_stated, comparison_dimensions_from_row
from dashboard.ui import empty_state, filter_analysis

DELAY = {"postponed", "waiting", "considering"}
ALT_PURCHASE = {"alternative_purchased"}


def render(analysis: pd.DataFrame, filters: dict) -> None:
    st.subheader("Comparison Behavior")
    st.caption(
        "Where users compare shortlisted products, which attributes they mention, and whether "
        "comparison sits next to delay or an alternative purchase. Numeric alternative counts "
        "appear only when a source stated a number."
    )
    df = filter_analysis(analysis, filters)
    relevant = df[df["relevant_to_wishlist"] == True] if not df.empty else df  # noqa: E712
    if relevant.empty:
        empty_state()
        return

    cmp_df = relevant[
        relevant["wishlist_behavior"].eq("comparison_shortlist")
        | relevant["purchase_blocker"].eq("comparison_uncertainty")
        | relevant["uncertainty_type"].fillna("").str.lower().eq("comparison")
    ]
    st.metric("Comparison / shortlist conversations", int(len(cmp_df)))
    st.caption("Percentage of analyzed public conversations, not of Myntra users.")

    if cmp_df.empty:
        st.info("No comparison/shortlist labels in the current analyzed corpus.")
        return

    dim_counts: Counter[str] = Counter()
    stated: list[int] = []
    where: Counter[str] = Counter()
    delayed = 0
    alt_bought = 0
    for _, row in cmp_df.iterrows():
        for dim in comparison_dimensions_from_row(row):
            dim_counts[dim] += 1
        n_alt = alternative_count_stated(str(row.get("original_text") or row.get("text") or ""))
        if n_alt is not None:
            stated.append(n_alt)
        src = str(row.get("external_information_source") or "")
        if src and src not in {"none", "unknown", ""}:
            where[src] += 1
        else:
            where["not stated / appears on-platform"] += 1
        status = str(row.get("purchase_status") or "")
        if status in DELAY:
            delayed += 1
        if status in ALT_PURCHASE:
            alt_bought += 1

    c1, c2, c3 = st.columns(3)
    c1.metric("Associated with delay / open decision", delayed)
    c2.metric("Alternative purchased", alt_bought)
    if stated:
        c3.metric("Median stated alternatives", float(pd.Series(stated).median()))
        st.caption(f"{len(stated)} conversation(s) stated a numeric alternative count. No other count is invented.")
    else:
        c3.metric("Median stated alternatives", "not stated")
        st.caption("No source in this corpus stated how many alternatives were considered. No number is invented.")

    if dim_counts:
        dim_df = pd.DataFrame(dim_counts.most_common(), columns=["Attribute compared", "Conversations"])
        st.plotly_chart(px.bar(dim_df, x="Attribute compared", y="Conversations"), use_container_width=True)
    if where:
        where_df = pd.DataFrame(where.most_common(), columns=["Where they compare", "Conversations"])
        st.plotly_chart(px.bar(where_df, x="Where they compare", y="Conversations"), use_container_width=True)

    st.markdown("#### Evidence")
    for _, row in cmp_df.head(20).iterrows():
        url = row.get("source_url") or ""
        link = f" — [Open Original Source]({url})" if url else ""
        st.markdown(f"- “{row.get('evidence_quote')}” `{row.get('source')}`{link}")
