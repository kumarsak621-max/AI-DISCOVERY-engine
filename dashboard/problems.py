"""Problem landscape."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.ui import empty_state, filter_analysis


def render(analysis: pd.DataFrame, opportunities: pd.DataFrame, filters: dict) -> None:
    st.subheader("Problem Landscape")
    st.caption("ANALYZED DATA ranked into INFERRED INSIGHT. Rank is not ROI.")

    filtered = filter_analysis(analysis, filters)
    relevant = filtered[filtered["relevant_to_wishlist"] == True] if not filtered.empty else filtered  # noqa: E712

    if opportunities.empty or relevant.empty:
        empty_state()
        return

    table = opportunities.copy()
    table = table.sort_values("opportunity_score", ascending=False).reset_index(drop=True)
    table.insert(0, "Rank", table.index + 1)
    n = max(len(relevant), 1)
    high_intent_pct = []
    for name in table["opportunity_name"]:
        subset = relevant[relevant["primary_problem"].str.contains(str(name).split()[0], case=False, na=False)]
        if subset.empty:
            # fallback: conversion_relevance_score already stored
            high_intent_pct.append(None)
        else:
            high_intent_pct.append(round(100 * subset["high_intent_friction"].mean(), 1))
    display = pd.DataFrame(
        {
            "Rank": table["Rank"],
            "Problem": table["opportunity_name"],
            "Frequency": table["evidence_count"],
            "High Intent %": table["conversion_relevance_score"],
            "Severity": table["severity_score"],
            "Conversion Relevance": table["conversion_relevance_score"],
            "Opportunity Score": table["opportunity_score"],
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(
        f"Filtered relevant conversations in view: {len(relevant)} / {len(analysis)} analyzed. "
        "High Intent % here uses the conversion-relevance score (high-intent + friction status)."
    )
