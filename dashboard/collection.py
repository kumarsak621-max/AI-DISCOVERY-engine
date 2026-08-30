"""Data Collection Status — source metrics, readiness, collection, upload, recent feedback."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from analytics.records import (
    build_review_records,
    corpus_stats,
    display_source,
    wishlist_intent_label,
)
from config import HISTORICAL_WINDOW_MONTHS
from dashboard import collection_runs as collection_runs_page
from dashboard.ui import empty_state, overall_collection_status, readiness_state, section_label, status_pill
from dashboard.upload import parse_upload_bytes, persist_upload
from database.db import session_scope
from processing.dates import window_bounds_months


def _fmt_dt(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    text = str(value)
    return text if text and text.lower() not in {"nan", "nat", "none"} else "—"


def _recent_table(conversations: pd.DataFrame, analysis: pd.DataFrame, limit: int = 40) -> pd.DataFrame:
    records = build_review_records(conversations, analysis)
    if records.empty:
        return pd.DataFrame()
    view = records.copy()
    if "source" in view.columns:
        view = view[view["source"].isin(["google_play", "youtube", "manual"])]
    if "published_at" in view.columns:
        view = view.sort_values("published_at", ascending=False, na_position="last")
    rows = []
    for _, row in view.head(limit).iterrows():
        rating = row.get("rating")
        rating_out = rating if pd.notna(rating) and str(rating) not in {"", "None", "nan"} else "—"
        theme = row.get("primary_problem")
        sentiment = row.get("sentiment")
        segment = row.get("user_segment")
        intent = row.get("purchase_intent")
        rows.append(
            {
                "Date": _fmt_dt(row.get("published_at")),
                "Source": display_source(row.get("source")),
                "Rating": rating_out,
                "Theme": theme if theme and str(theme).strip() not in {"", "None", "nan"} else "Not analyzed",
                "Sentiment": sentiment if sentiment and str(sentiment).strip() not in {"", "None", "nan"} else "Not analyzed",
                "User Segment": segment if segment and str(segment).strip() not in {"", "None", "nan", "unknown"} else "Not analyzed",
                "Purchase Intent": intent if intent and str(intent).strip() not in {"", "None", "nan", "unknown"} else "Not analyzed",
                "Wishlist Intent": wishlist_intent_label(row.get("wishlist_behavior")),
                "Text": str(row.get("original_text") or row.get("text") or "")[:280],
            }
        )
    return pd.DataFrame(rows)


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    health: list[dict],
    *,
    last_collection,
    last_ai,
    last_stats: dict | None,
    interval_note: str,
    interval_hours: int,
    hist_months: int = HISTORICAL_WINDOW_MONTHS,
    gemini_configured: bool,
    openrouter_configured: bool,
    youtube_configured: bool,
    play_ready: bool = True,
    db_ready: bool = True,
) -> dict:
    st.subheader("Data Collection Status")
    st.caption(
        "Every count on this page is computed from stored public records. "
        "If a source returned nothing, the card shows 0 — not an estimate."
    )

    stats = corpus_stats(conversations)
    section_label("Source Metrics")
    c1, c2, c3 = st.columns(3)
    c1.metric("Google Play Reviews", int(stats["google_play"]))
    c2.metric("YouTube Comments", int(stats["youtube"]))
    c3.metric("Total Feedback", int(stats["google_play"]) + int(stats["youtube"]))
    if stats["google_play"] == 0:
        st.caption("No Google Play reviews collected.")
    if int(stats["google_play"]) + int(stats["youtube"]) == 0:
        empty_state("No data collected.")

    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric("Earliest Feedback", _fmt_dt(stats["earliest"]))
    e2.metric("Latest Feedback", _fmt_dt(stats["latest"]))
    avg = stats["average_rating"]
    e3.metric("Average Rating", avg if avg is not None else "—")
    if avg is None:
        e3.caption("No ratings stored.")
    e4.metric("Records in Database", int(stats["total"]))
    e5.metric("Sources Active", int(stats["sources_active"]))

    section_label("System Readiness")
    r1, r2, r3, r4, r5 = st.columns(5)
    with r1:
        status_pill("Gemini", readiness_state(configured=gemini_configured))
    with r2:
        status_pill("OpenRouter", readiness_state(configured=openrouter_configured))
    with r3:
        status_pill("Google Play", "READY" if play_ready else "NOT CONFIGURED")
    with r4:
        status_pill("YouTube", "READY" if youtube_configured else "NOT CONFIGURED")
    with r5:
        status_pill("Database", "READY" if db_ready else "ERROR")

    section_label("Data Collection")
    hist_start, hist_end = window_bounds_months(hist_months)
    st.markdown(f"**Historical Range:** {hist_months} Months")
    st.caption(
        f"Requested date range: **{hist_start.date()} → {hist_end.date()}** "
        "(calculated as today minus 30 months — not a hardcoded date)."
    )
    st.caption(
        f"Actual earliest collected record: **{_fmt_dt(stats['earliest'])}** · "
        f"Actual latest collected record: **{_fmt_dt(stats['latest'])}** · "
        f"Total records collected: **{stats['total']}**"
    )
    if stats["earliest"] is not None:
        try:
            span = hist_end - pd.Timestamp(stats["earliest"]).to_pydatetime().replace(tzinfo=hist_end.tzinfo)
            collected_months = max(0, int(span.days / 30.44))
        except Exception:
            collected_months = 0
        if collected_months < hist_months and stats["total"]:
            st.info(
                f"Requested: {hist_months} months. Actually collected span is about "
                f"{collected_months} months. Reason: source historical availability limitation. "
                "This app does not fabricate missing history."
            )

    b1, b2, b3 = st.columns(3)
    with b1:
        collect_hist = st.button(
            "Collect Historical Feedback",
            type="primary",
            use_container_width=True,
            key="collect_historical_feedback",
        )
    with b2:
        collect_latest = st.button(
            "Collect Latest Feedback",
            use_container_width=True,
            key="collect_latest_feedback",
        )
    with b3:
        analyze = st.button(
            "Analyze Feedback",
            use_container_width=True,
            key="collection_analyze_feedback",
        )

    run_stats = last_stats or {}
    source_results = run_stats.get("source_coverage") or run_stats.get("error_details") or []
    if run_stats.get("sources_ok") or run_stats.get("error_details") or run_stats.get("source_coverage"):
        st.markdown(f"**Last run overall:** {overall_collection_status(run_stats.get('source_coverage') or [])}")
    for item in run_stats.get("source_coverage") or []:
        src = display_source(item.get("source"))
        status = str(item.get("status") or "—").upper()
        found = item.get("found", 0)
        if status == "OK":
            if str(item.get("source")) == "google_play" and int(found or 0) == 0:
                st.success("Google Play: SUCCESS — 0 new reviews")
                st.caption("No new Google Play reviews found.")
            else:
                st.success(f"{src}: SUCCESS — {found} records in window")
        elif status in {"ERROR", "UNAVAILABLE"}:
            st.warning(f"{src}: FAILED — {item.get('error') or 'No data collected.'}")
        else:
            st.warning(f"{src}: {status} — {item.get('error') or 'No data collected.'}")
        st.caption(
            f"Requested: {item.get('requested_start') or '—'} → {item.get('requested_end') or '—'} · "
            f"Earliest: {item.get('earliest_record') or 'none'} · "
            f"Latest: {item.get('latest_record') or 'none'} · "
            f"Records: {found}"
        )
        if item.get("limitation"):
            st.caption(f"Limitation: {item.get('limitation')}")

    next_run = "—"
    if last_collection and interval_hours:
        last = last_collection
        if getattr(last, "tzinfo", None) is None:
            from datetime import timezone as _tz

            last = last.replace(tzinfo=_tz.utc)
        next_run = str(last + timedelta(hours=interval_hours))
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Last Collection", str(last_collection or "Never"))
    d2.metric("Next scheduled", next_run if interval_hours else "Manual only")
    d3.metric("Records fetched", run_stats.get("fetched", run_stats.get("collected", "—")))
    d4.metric("New records", run_stats.get("new", "—"))
    d5.metric("Duplicates", run_stats.get("duplicates", "—"))
    st.caption(interval_note)
    if run_stats.get("error"):
        st.error(run_stats["error"])

    section_label("Manual Upload")
    st.caption("Upload your own real customer feedback. This does not generate reviews.")
    uploaded = st.file_uploader("Upload CSV, XLSX, or TXT", type=["csv", "xlsx", "xls", "txt"])
    source_name = st.selectbox("Source", ["Manual Upload"], index=0)
    if uploaded is not None and st.button("Load uploaded feedback", key="load_manual_upload"):
        try:
            frame = parse_upload_bytes(uploaded.name, uploaded.getvalue())
        except Exception as exc:
            st.error(f"Upload failed: {exc}")
        else:
            if frame.empty:
                empty_state("No data collected.")
            else:
                with session_scope() as session:
                    result = persist_upload(session, frame, source="manual")
                st.success(
                    f"Upload: {source_name}. Records loaded: {result['new']} new, "
                    f"{result['duplicates']} duplicates, {result['parsed']} parsed."
                )
                st.session_state["last_upload_stats"] = result
                st.rerun()
    upload_stats = st.session_state.get("last_upload_stats")
    if upload_stats:
        st.caption(
            f"Last upload — Records loaded: {upload_stats.get('new', 0)} · "
            f"Source: Manual Upload · Collected at: {upload_stats.get('collected_at') or '—'}"
        )

    section_label("Recent Collected Feedback")
    recent = _recent_table(conversations, analysis)
    if recent.empty:
        empty_state("No data collected.")
    else:
        q1, q2, q3 = st.columns(3)
        with q1:
            search = st.text_input("Search text", key="recent_search")
        with q2:
            sources = ["All"] + sorted(recent["Source"].dropna().unique().tolist())
            source_f = st.selectbox("Source filter", sources, key="recent_source")
        with q3:
            themes = ["All"] + sorted({str(x) for x in recent["Theme"].dropna().tolist() if str(x).strip() and str(x) != "—"})
            theme_f = st.selectbox("Theme filter", themes, key="recent_theme")
        q4, q5 = st.columns(2)
        with q4:
            intents = ["All"] + sorted({str(x) for x in recent["Purchase Intent"].dropna().tolist() if str(x).strip()})
            intent_f = st.selectbox("Intent filter", intents, key="recent_intent")
        with q5:
            view = recent
            if search.strip():
                view = view[view["Text"].str.contains(search.strip(), case=False, na=False)]
            if source_f != "All":
                view = view[view["Source"] == source_f]
            if theme_f != "All":
                view = view[view["Theme"] == theme_f]
            if intent_f != "All":
                view = view[view["Purchase Intent"] == intent_f]
        if view.empty:
            empty_state("No data collected.")
        else:
            st.dataframe(view, use_container_width=True, hide_index=True)

    with st.expander("Collection run history", expanded=False):
        st.caption("Last collection time, records fetched, new records, duplicates, and errors.")
        with session_scope() as session:
            collection_runs_page.render(session)
        st.dataframe(pd.DataFrame(health), use_container_width=True, hide_index=True)

    st.caption(f"Last AI analysis: {last_ai or 'Never'}")
    return {
        "collect": bool(collect_latest),
        "collect_historical": bool(collect_hist),
        "analyze": bool(analyze),
    }
