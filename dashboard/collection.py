"""Data Collection — last-run stats and Collect Latest Reviews."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.ui import empty_state


def render(
    health: list[dict],
    *,
    last_collection,
    last_stats: dict | None,
    interval_note: str,
    records_30: int = 0,
) -> dict:
    """Returns collect/analyze click flags."""
    st.subheader("Data Collection")
    st.caption(
        "This fetches newly published public records from configured sources. "
        "Streamlit hosting does **not** run a continuous background worker unless you add an external cron."
    )
    st.info(interval_note)

    stats = last_stats or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last successful collection", str(last_collection or "Never"))
    c2.metric("Records fetched", stats.get("fetched", stats.get("collected", "—")))
    c3.metric("New records", stats.get("new", "—"))
    c4.metric("Duplicates ignored", stats.get("duplicates", "—"))

    d1, d2, d3 = st.columns(3)
    d1.metric("Failed sources", stats.get("errors", "—"))
    d2.metric("Last 30-day records", records_30)
    d3.metric("Successfully analyzed", stats.get("analyzed", "—"))

    sources_ok = stats.get("sources_ok") or []
    if sources_ok:
        st.success("Sources successfully collected: " + ", ".join(sources_ok))
    for detail in stats.get("error_details") or []:
        source = detail.get("source") or "source"
        status = str(detail.get("status") or "Unavailable / No new data")
        reason = detail.get("error") or status
        st.warning(f"**{source}** — Status: {status}\n\nReason: {reason}")
    if stats.get("error"):
        st.error(stats["error"])

    b1, b2 = st.columns(2)
    with b1:
        collect = st.button("Collect Latest Reviews", type="primary", use_container_width=True, key="collection_collect_latest")
    with b2:
        analyze = st.button("Analyze Reviews", use_container_width=True, key="collection_analyze_reviews")
    st.caption("If a source has no new public items, the count will be zero. Fake reviews are never generated.")

    st.markdown("#### Source health")
    if health:
        st.dataframe(pd.DataFrame(health), use_container_width=True, hide_index=True)
    else:
        empty_state("No collection has run yet.")
    return {"collect": bool(collect), "analyze": bool(analyze)}
