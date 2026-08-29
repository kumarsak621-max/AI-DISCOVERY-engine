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
    total_records: int = 0,
    play_count: int = 0,
    youtube_count: int = 0,
    reddit_count: int = 0,
    hist_label: str = "Last 30 Months",
    ai_provider_label: str = "—",
) -> dict:
    st.subheader("Myntra AI Discovery Engine")
    st.markdown(f"**Historical data:** {hist_label} (publication date, dynamic from today).")
    st.caption(analysis_period_label(int(window_days)))
    data_layer_caption()

    st.markdown("#### TOTAL USER FEEDBACK")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Google Play", int(play_count))
    c2.metric("YouTube", int(youtube_count))
    c3.metric("Reddit", int(reddit_count))
    c4.metric("Total records", int(total_records))

    n30 = 0 if conversations.empty else int(len(conversations))
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Last 30 days", n30)
    new_n = (last_stats or {}).get("new")
    dup_n = (last_stats or {}).get("duplicates")
    a2.metric("New records (last run)", new_n if new_n is not None else "—")
    a3.metric("Duplicates (last run)", dup_n if dup_n is not None else "—")
    a4.metric("Latest collection", str(last_collection or "Never"))

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Analysis complete", analyzed)
    b2.metric("Pending analysis", pending_ai)
    b3.metric("Failed analysis", failed_ai)
    b4.metric("Last AI analysis", str(last_ai or "Never"))

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
    for item in (last_stats or {}).get("source_coverage") or []:
        if str(item.get("source")) not in {"apify_reddit", "reddit"}:
            continue
        st.caption(
            f"**{item.get('source')}** — requested: {item.get('requested_start') or '—'} → {item.get('requested_end') or '—'} · "
            f"earliest collected: {item.get('earliest_record') or 'none'} · "
            f"latest collected: {item.get('latest_record') or 'none'} · "
            f"records: {item.get('found', 0)}"
        )
        if item.get("limitation"):
            st.caption(str(item.get("limitation")))

    b1, b2 = st.columns(2)
    with b1:
        clicked = st.button("Collect Latest Reviews", type="primary", use_container_width=True, key="dash_collect_latest")
    with b2:
        analyze = st.button("Analyze Reviews", use_container_width=True, key="dash_analyze_reviews")
    st.caption(
        "Collect Latest Reviews fetches newly published public records when the job runs — not a continuous live stream. "
        "Fake or demo reviews are never generated."
    )

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
    return {"collect": bool(clicked), "analyze": bool(analyze)}
