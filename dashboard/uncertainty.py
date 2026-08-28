"""Uncertainty map."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import empty_state, filter_analysis

UNCERTAINTY_ORDER = [
    "fit",
    "size",
    "quality",
    "price",
    "styling",
    "reviews",
    "returns",
    "occasion",
    "comparison",
    "availability",
    "trust",
]


def render(analysis: pd.DataFrame, filters: dict) -> None:
    st.subheader("Uncertainty Map")
    st.caption("What users do not know before purchasing — from stated text, not inferred silently.")
    df = filter_analysis(analysis, filters)
    relevant = df[df["relevant_to_wishlist"] == True] if not df.empty else df  # noqa: E712
    if relevant.empty:
        empty_state()
        return

    relevant = relevant.copy()
    relevant["u"] = relevant["uncertainty_type"].fillna("unknown").replace("", "unknown")
    grouped = []
    for utype, subset in relevant.groupby("u"):
        external = subset[
            subset["leaves_myntra"].eq(True)
            | subset["external_information_source"].isin(
                ["Reddit", "Instagram", "YouTube", "Google", "friends", "influencers",
                 "other shopping apps", "brand website", "physical store"]
            )
        ]
        grouped.append(
            {
                "Uncertainty": utype,
                "frequency": int(len(subset)),
                "high_intent_frequency": int(subset["high_intent_friction"].sum()),
                "external_workaround_frequency": int(len(external)),
            }
        )
    table = pd.DataFrame(grouped).sort_values("frequency", ascending=False)
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.plotly_chart(
        px.bar(
            table,
            x="Uncertainty",
            y=["frequency", "high_intent_frequency", "external_workaround_frequency"],
            barmode="group",
            title="Uncertainty types",
        ),
        use_container_width=True,
    )

    st.markdown("#### Example uncertainty statements")
    samples = relevant[relevant["uncertainty_text"].astype(str).str.len() > 5].head(12)
    for _, row in samples.iterrows():
        st.markdown(
            f"- **{row['uncertainty_type']}** — {row['uncertainty_text']} "
            f"({row['source']}, intent={row['purchase_intent']})"
        )
