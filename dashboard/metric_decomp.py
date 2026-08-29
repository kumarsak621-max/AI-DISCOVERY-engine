"""Metric Decomposition — wishlist → purchase as a hypothesis framework."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.metric_decomp import decompose_metric
from analytics.records import analysis_period_label, build_review_records
from dashboard.ui import empty_state


def render(conversations: pd.DataFrame, analysis: pd.DataFrame, window_days: int = 30) -> None:
    st.subheader("Metric Decomposition")
    st.markdown("**WISHLIST → PURCHASE CONVERSION**")
    st.caption(analysis_period_label(int(window_days)))
    st.markdown(
        "This breaks the business metric into user/product stages. "
        "Counts are **public conversation evidence**, not Myntra internal funnel analytics. "
        "Links from feedback → problem → behavior → product outcome are **hypotheses** unless causal data exists."
    )
    st.markdown(
        """
Product discovered → Product liked → Product wishlisted → Wishlist revisited →
Purchase consideration → Uncertainty resolved → Add to cart → Checkout → Purchase
"""
    )

    records = build_review_records(conversations, analysis)
    table = decompose_metric(records)
    if records.empty:
        empty_state("No real reviews were collected for this period.")
        st.dataframe(table, use_container_width=True, hide_index=True)
        return

    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption(
        "The collected evidence suggests where public conversations cluster. "
        "This may indicate research priorities. It does not prove what causes users not to purchase."
    )

    st.markdown("#### Discovery → business metric connection (hypothesis)")
    st.markdown(
        """
**USER FEEDBACK** → **USER PROBLEM** → **USER BEHAVIOR** → **PRODUCT OUTCOME** → **WISHLIST → PURCHASE CONVERSION**

Example (only if fit/size evidence exists in the table above):

- Evidence: Users frequently mention fit or size uncertainty.
- Potential problem: Users like products but lack confidence that the product will fit.
- Behavior: Users postpone purchase or keep the item bookmarked/wishlisted.
- Potential product outcome: Lower wishlist-to-cart/purchase conversion.

Treat this chain as a **hypothesis** to validate with interviews and internal analytics.
"""
    )
