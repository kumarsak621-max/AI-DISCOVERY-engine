"""Overview — freshness, period, source health. Not a substitute for record inspection."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.metrics import kpi_counts
from analytics.records import analysis_period_label, source_summary
from dashboard.ui import data_layer_caption, empty_state


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    health: list[dict],
    *,
    last_collection,
    last_ai,
    pending_ai: int,
    failed_ai: int,
    analyzed: int,
    last_stats: dict | None,
    window_days: int,
) -> bool:
    st.subheader("Overview")
    st.markdown("**Last 30 Days** of public conversations (by publication date).")
    st.caption(analysis_period_label(int(window_days)))
    data_layer_caption()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last successful collection", str(last_collection or "Never"))
    c2.metric("Total records in window", 0 if conversations.empty else int(len(conversations)))
    new_n = (last_stats or {}).get("new")
    dup_n = (last_stats or {}).get("duplicates")
    c3.metric("New records (last run)", new_n if new_n is not None else "—")
    c4.metric("Duplicates ignored (last run)", dup_n if dup_n is not None else "—")

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Analysis status — complete", analyzed)
    a2.metric("Pending analysis", pending_ai)
    a3.metric("Failed analysis", failed_ai)
    a4.metric("Last AI analysis", str(last_ai or "Never"))

    errors = (last_stats or {}).get("errors")
    fetched = (last_stats or {}).get("fetched")
    f1, f2 = st.columns(2)
    f1.metric("Records fetched (last run)", fetched if fetched is not None else "—")
    f2.metric("Source errors (last run)", errors if errors is not None else "—")
    sources_ok = (last_stats or {}).get("sources_ok") or []
    if sources_ok:
        st.caption("Sources successfully collected: " + ", ".join(sources_ok))
    for detail in (last_stats or {}).get("error_details") or []:
        st.warning(f"{detail.get('source')}: {detail.get('error') or detail.get('status')}")

    clicked = st.button("Collect Latest Reviews", type="primary", use_container_width=True)
    st.caption("Fetches newly published public records. Fake or demo reviews are never generated.")

    if conversations.empty:
        empty_state("No real reviews were collected for this period.")
    else:
        kpis = kpi_counts(conversations, analysis)
        st.markdown("#### Corpus snapshot (analyzed public conversations, not Myntra users)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Relevant", kpis["relevant"])
        k2.metric("Wishlist-related", kpis["wishlist_related"])
        k3.metric("High-intent friction", kpis["high_intent"])
        k4.metric("Blocker mentions", kpis["purchase_blocker"])

    st.markdown("#### Source summary")
    st.caption("Counts come from collected records in the current research window. Zeros mean none were stored — not estimates.")
    st.dataframe(source_summary(conversations), use_container_width=True, hide_index=True)

    st.markdown("#### Source health")
    st.dataframe(pd.DataFrame(health), use_container_width=True, hide_index=True)
    st.caption("Unavailable or errored sources are not filled with fake reviews.")

    st.markdown("Inspect underlying records in **Review Explorer** or **Last 30 Days**. Do not infer from this summary alone.")
    return bool(clicked)
