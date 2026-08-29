"""Live collection controls and last-run stats."""

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
) -> bool:
    """Returns True if the user clicked Collect Latest Reviews."""
    st.subheader("Live Collection")
    st.caption(
        "This fetches newly published public records from configured sources. "
        "Streamlit hosting does **not** run a continuous background worker unless you add an external cron."
    )
    st.info(interval_note)

    stats = last_stats or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last collection time", str(last_collection or "Never"))
    c2.metric("Records fetched", stats.get("fetched", stats.get("collected", "—")))
    c3.metric("New records", stats.get("new", "—"))
    c4.metric("Duplicates ignored", stats.get("duplicates", "—"))

    d1, d2, d3 = st.columns(3)
    d1.metric("Collection errors", stats.get("errors", "—"))
    d2.metric("Successfully analyzed", stats.get("analyzed", "—"))
    d3.metric("Last run status", stats.get("status") or "—")

    sources_ok = stats.get("sources_ok") or []
    if sources_ok:
        st.success("Sources successfully collected: " + ", ".join(sources_ok))
    for detail in stats.get("error_details") or []:
        st.warning(
            f"{detail.get('source')}: {detail.get('error') or detail.get('status') or 'unavailable'}"
        )
    if stats.get("error"):
        st.error(stats["error"])

    clicked = st.button("Collect Latest Reviews", type="primary", use_container_width=True)
    st.caption("If a source has no new public items, the count will be zero. Fake reviews are never generated.")

    st.markdown("#### Source health")
    if health:
        st.dataframe(pd.DataFrame(health), use_container_width=True, hide_index=True)
    else:
        empty_state("No collection has run yet.")
    return clicked
