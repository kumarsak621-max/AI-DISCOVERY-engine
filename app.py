"""Myntra AI Wishlist Conversion Discovery Engine — live public data only."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from analytics.brief import brief_to_pdf_bytes
from analytics.metrics import (
    build_discovery_summary,
    latest_run,
    load_analysis_frame,
    load_conversations_frame,
    load_opportunities_frame,
    load_themes_frame,
    source_health_rows,
)
from config import (
    BUSINESS_GOAL,
    DEFAULT_MODEL,
    DEFAULT_RESEARCH_WINDOW_DAYS,
    DISCLAIMER,
    SCHEDULER_INTERVALS,
)
from dashboard import blockers as blockers_page
from dashboard import brief as brief_page
from dashboard import comparison as comparison_page
from dashboard import evidence as evidence_page
from dashboard import executive as executive_page
from dashboard import part1 as part1_page
from dashboard import problems as problems_page
from dashboard import segments as segments_page
from dashboard import uncertainty as uncertainty_page
from dashboard import wishlist as wishlist_page
from dashboard import workarounds as workarounds_page
from dashboard import ask as ask_page
from dashboard import collection as collection_page
from dashboard import insights as insights_page
from dashboard import last30 as last30_page
from dashboard import overview as overview_page
from dashboard import reviews as reviews_page
from dashboard.ui import banner
from database.db import init_db, session_scope
from database.models import AppSetting, CollectionRun, Conversation
from pipeline.discovery import run_discovery
from processing.dates import utcnow, window_bounds

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("myntra_discovery")

PAGES = [
    "Overview",
    "Review Explorer",
    "Last 30 Days",
    "Live Collection",
    "AI Insights",
    "Ask AI",
    "Part 1 — AI Discovery Answers",
    "Executive Discovery",
    "Problem Landscape",
    "Wishlist Behavior",
    "Purchase Blockers",
    "Uncertainty Map",
    "Comparison Behavior",
    "External Information Seeking",
    "Segment Explorer",
    "Evidence Explorer",
    "AI Research Brief",
]


def _secret(name: str, default: str = "") -> str:
    env_val = os.getenv(name, "")
    if env_val:
        return env_val
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _init() -> None:
    db_path = _secret("DATABASE_PATH", str(ROOT / "data" / "discovery.db"))
    init_db(db_path)


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _get_setting(session, key: str, default: str = "") -> str:
    row = session.get(AppSetting, key)
    return row.value if row else default


def _set_setting(session, key: str, value: str) -> None:
    row = session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def _run_collection(
    *,
    enabled: list[str],
    max_records: int,
    model: str,
    temperature: float,
    api_key: str,
    window_days: int,
    full_refresh: bool,
    extra_queries: list[str],
    progress_bar,
):
    def on_progress(message: str, fraction: float) -> None:
        progress_bar.progress(min(max(fraction, 0.0), 1.0), text=message)

    with session_scope() as session:
        run = run_discovery(
            session,
            enabled_sources=enabled,
            max_records=int(max_records),
            model=model.strip() or DEFAULT_MODEL,
            temperature=float(temperature),
            api_key=api_key.strip(),
            window_days=window_days,
            full_refresh=full_refresh,
            extra_queries=extra_queries,
            progress=on_progress,
        )
    st.session_state["last_collection_stats"] = {
        "new": int(getattr(run, "conversations_new", 0) or 0),
        "duplicates": int(getattr(run, "conversations_duplicate", 0) or 0),
        "analyzed": int(getattr(run, "conversations_analyzed", 0) or 0),
        "collected": int(getattr(run, "conversations_collected", 0) or 0),
        "fetched": int(getattr(run, "records_fetched", getattr(run, "conversations_collected", 0)) or 0),
        "status": run.status,
        "error": run.error or "",
        "finished_at": str(run.finished_at or ""),
        "sources_ok": [
            str(item.get("source"))
            for item in (getattr(run, "source_results", None) or [])
            if item.get("status") == "ok"
        ],
        "errors": sum(
            1
            for item in (getattr(run, "source_results", None) or [])
            if item.get("status") in {"error", "unavailable"}
        ),
        "error_details": [
            item
            for item in (getattr(run, "source_results", None) or [])
            if item.get("status") in {"error", "unavailable"}
        ],
    }
    st.success(
        f"Collection {run.status}. Found {run.conversations_collected}, "
        f"new {run.conversations_new}, duplicates {getattr(run, 'conversations_duplicate', 0)}, "
        f"analyzed {run.conversations_analyzed}."
    )
    if not api_key.strip():
        st.warning("OPENROUTER_API_KEY is missing. Records were stored; AI analysis remains pending.")
    return run


def main() -> None:
    st.set_page_config(
        page_title="Myntra AI Wishlist Conversion Discovery Engine",
        page_icon="🛍️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
<style>
    .stApp { background: #fff8f9; }
    h1, h2, h3 { color: #3e2329 !important; }
    div[data-testid="stMetricValue"] { color: #FF3F6C; }
    .block-container { padding-top: 1.2rem; }
</style>
""",
        unsafe_allow_html=True,
    )
    _init()

    st.title("Myntra AI Wishlist Conversion Discovery Engine")
    st.markdown("**Live Public Conversation Intelligence — Last 30 Days**")
    st.markdown(f"**Business Goal:** {BUSINESS_GOAL}")
    banner()

    default_key = _secret("OPENROUTER_API_KEY")
    default_model = _secret("OPENROUTER_MODEL", DEFAULT_MODEL)
    youtube_configured = bool(_secret("YOUTUBE_API_KEY"))
    reddit_oauth = bool(_secret("REDDIT_CLIENT_ID") and _secret("REDDIT_CLIENT_SECRET"))
    cron_secret = _secret("CRON_SECRET")

    collect_qp = st.query_params.get("collect", "")
    token_qp = st.query_params.get("token", "")
    if collect_qp == "1":
        if not cron_secret:
            st.error("CRON_SECRET is not configured; HTTP/query-param collection is disabled.")
            st.stop()
        if token_qp != cron_secret:
            st.error("Unauthorized collection request.")
            st.stop()
        bar = st.progress(0.0, text="Cron-triggered collection…")
        try:
            _run_collection(
                enabled=["reddit", "youtube", "web", "app_store", "google_play"],
                max_records=200,
                model=default_model,
                temperature=0.1,
                api_key=default_key,
                window_days=30,
                full_refresh=False,
                extra_queries=[],
                progress_bar=bar,
            )
        except Exception as exc:
            logger.exception("Cron-triggered collection failed")
            st.error(f"Cron-triggered collection failed: {exc}")
        st.stop()

    with st.sidebar:
        st.header("Collection")
        window_days = st.selectbox(
            "Research Window",
            [7, 30, 60, 90],
            index=1,
            format_func=lambda d: f"{d} days",
        )
        start, end = window_bounds(int(window_days))
        st.caption(f"Research period: **{start.date()}** → **{end.date()}**")
        st.caption("Window uses **publication date**, not collection date.")

        enabled = st.multiselect(
            "Sources",
            ["reddit", "youtube", "web", "app_store", "google_play"],
            default=["reddit", "youtube", "web", "app_store", "google_play"],
        )
        max_records = st.selectbox("Max records per source", [100, 200, 500, 1000], index=1)
        model = st.text_input("OpenRouter Model", value=default_model)
        temperature = st.slider("Temperature", 0.0, 1.0, 0.1, 0.05)
        api_key = st.text_input("OpenRouter API key", value=default_key, type="password")
        extra_q = st.text_area("Additional search queries (one per line)", height=70)
        extra_queries = [q.strip() for q in (extra_q or "").splitlines() if q.strip()]

        run_now = st.button("Run Collection Now", type="primary", use_container_width=True)
        full_refresh = st.button("Full 30-Day Refresh", use_container_width=True)

        st.divider()
        st.subheader("Automatic collection")
        interval_label = st.selectbox("Interval", list(SCHEDULER_INTERVALS.keys()), index=3)
        interval_hours = SCHEDULER_INTERVALS[interval_label]
        st.caption(
            "Streamlit has no persistent background worker. Interval collection runs when the "
            "dashboard is open. For true cron, run `python -m scheduler.jobs` (Render Cron Job)."
        )
        if interval_hours == 0:
            st.info("Automatic collection is **not** active (manual only).")
        else:
            st.info(
                f"Visit-based incremental collection every {interval_hours}h is enabled. "
                "It is not a background daemon."
            )

    with session_scope() as session:
        _set_setting(session, "scheduler_interval_hours", str(interval_hours))
        collection_count = session.query(CollectionRun).count()
        last = latest_run(session)
        last_ai = last.last_ai_success_at if last else None
        last_collection = last.finished_at if last else None
        pending_ai = session.query(Conversation).filter(Conversation.analysis_status == "pending").count()
        failed_ai = session.query(Conversation).filter(Conversation.analysis_status == "failed").count()
        analyzed = session.query(Conversation).filter(Conversation.analysis_status == "complete").count()
        health = source_health_rows(session, openrouter_configured=bool(api_key.strip()))

    needs_first_run = collection_count == 0
    skip_auto = os.getenv("SKIP_AUTO_COLLECTION", "").strip().lower() in {"1", "true", "yes"}
    if needs_first_run and skip_auto:
        st.info("SKIP_AUTO_COLLECTION is set. First-run collection will not start automatically.")
    elif needs_first_run and not st.session_state.get("first_run_started"):
        st.info("Initializing 30-day discovery...")
        st.session_state["first_run_started"] = True
        bar = st.progress(0.0, text="Initializing 30-day discovery...")
        try:
            _run_collection(
                enabled=enabled,
                max_records=int(max_records),
                model=model,
                temperature=temperature,
                api_key=api_key,
                window_days=int(window_days),
                full_refresh=True,
                extra_queries=extra_queries,
                progress_bar=bar,
            )
            st.rerun()
        except Exception as exc:
            logger.exception("First-run collection failed")
            st.error(f"First-run collection failed: {exc}")

    if run_now or full_refresh:
        bar = st.progress(0.0, text="Starting collection…")
        try:
            _run_collection(
                enabled=enabled,
                max_records=int(max_records),
                model=model,
                temperature=temperature,
                api_key=api_key,
                window_days=int(window_days),
                full_refresh=bool(full_refresh) or needs_first_run,
                extra_queries=extra_queries,
                progress_bar=bar,
            )
        except Exception as exc:
            logger.exception("Collection failed")
            st.error(f"Collection failed: {exc}")

    if interval_hours and last_collection:
        last = last_collection
        if last.tzinfo is None:
            from datetime import timezone as _tz

            last = last.replace(tzinfo=_tz.utc)
        due = utcnow() - last > timedelta(hours=interval_hours)
        if due and not st.session_state.get("interval_run_done"):
            st.session_state["interval_run_done"] = True
            bar = st.progress(0.0, text="Due incremental collection…")
            try:
                _run_collection(
                    enabled=enabled,
                    max_records=int(max_records),
                    model=model,
                    temperature=temperature,
                    api_key=api_key,
                    window_days=int(window_days),
                    full_refresh=False,
                    extra_queries=extra_queries,
                    progress_bar=bar,
                )
            except Exception as exc:
                logger.exception("Interval collection failed")
                st.warning(f"Interval collection failed: {exc}")

    def _status(ok: bool, detail: str) -> str:
        return f"{'Connected' if ok else 'Error'} — {detail}"

    or_status = "Connected" if api_key.strip() else "Not configured"
    yt_status = "Connected" if youtube_configured else "Not configured (YOUTUBE_API_KEY)"
    rd_status = "OAuth configured" if reddit_oauth else "Public JSON (no OAuth keys)"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Data freshness", str(last_collection or "Never"))
    m2.metric("Last collection", str(last_collection or "Never"))
    m3.metric("Last AI analysis", str(last_ai or "Never"))
    m4.metric("Research window", f"{window_days} days")

    st.caption(
        f"OpenRouter: {or_status} · Reddit: {rd_status} · YouTube: {yt_status} · "
        f"Analyzed {analyzed} · Pending {pending_ai} · Failed {failed_ai}"
    )

    with st.expander("Source health", expanded=needs_first_run):
        st.dataframe(pd.DataFrame(health), use_container_width=True, hide_index=True)
        st.caption("Unavailable sources are reported honestly — this app never fabricates reviews.")

    with session_scope() as session:
        conversations = load_conversations_frame(session, window_days=int(window_days))
        analysis = load_analysis_frame(session, window_days=int(window_days))
        conversations_30 = (
            conversations if int(window_days) == 30 else load_conversations_frame(session, window_days=30)
        )
        analysis_30 = analysis if int(window_days) == 30 else load_analysis_frame(session, window_days=30)
        themes = load_themes_frame(session)
        opportunities = load_opportunities_frame(session)
        run = latest_run(session)
        brief_md = run.brief_markdown if run else ""
        summary = None
        if run and run.summary_json:
            try:
                summary = json.loads(run.summary_json)
            except json.JSONDecodeError:
                summary = build_discovery_summary(conversations, analysis, opportunities)
        elif not analysis.empty:
            summary = build_discovery_summary(conversations, analysis, opportunities)

    if "nav_page" not in st.session_state:
        st.session_state["nav_page"] = "Overview"

    page = st.radio(
        "Pages",
        PAGES,
        horizontal=True,
        index=PAGES.index(st.session_state.get("nav_page", "Overview"))
        if st.session_state.get("nav_page") in PAGES
        else 0,
        key="page_radio",
    )
    st.session_state["nav_page"] = page

    filters: dict = {}
    collect_latest = False
    skip_filters = {
        "Overview",
        "Review Explorer",
        "Last 30 Days",
        "Live Collection",
        "AI Insights",
        "Ask AI",
        "Part 1 — AI Discovery Answers",
        "Executive Discovery",
        "AI Research Brief",
    }
    if page not in skip_filters:
        with st.expander("Filters", expanded=False):
            if not analysis.empty:
                f1, f2, f3 = st.columns(3)
                with f1:
                    filters["source"] = st.multiselect("Source", sorted(analysis["source"].dropna().unique().tolist()))
                    filters["segment"] = st.multiselect(
                        "Segment", sorted(analysis["user_segment"].dropna().unique().tolist())
                    )
                with f2:
                    filters["category"] = st.multiselect(
                        "Category", sorted(analysis["fashion_category"].dropna().unique().tolist())
                    )
                    filters["intent"] = st.multiselect(
                        "Intent", sorted(analysis["purchase_intent"].dropna().unique().tolist())
                    )
                with f3:
                    filters["status"] = st.multiselect(
                        "Purchase status", sorted(analysis["purchase_status"].dropna().unique().tolist())
                    )
                    filters["blocker"] = st.multiselect(
                        "Blocker", sorted(analysis["purchase_blocker"].dropna().unique().tolist())
                    )
                ts = pd.to_datetime(analysis.get("published_at", analysis.get("timestamp")), utc=True, errors="coerce").dropna()
                if not ts.empty:
                    dmin, dmax = ts.min().date(), ts.max().date()
                    filters["date_range"] = st.date_input("Date range", value=(dmin, dmax))

    last_stats = st.session_state.get("last_collection_stats")
    if last_stats is None and run is not None:
        last_stats = {
            "new": int(getattr(run, "conversations_new", 0) or 0),
            "duplicates": int(getattr(run, "conversations_duplicate", 0) or 0),
            "analyzed": int(getattr(run, "conversations_analyzed", 0) or 0),
            "collected": int(getattr(run, "conversations_collected", 0) or 0),
            "fetched": int(getattr(run, "records_fetched", getattr(run, "conversations_collected", 0)) or 0),
            "status": run.status,
            "error": run.error or "",
            "finished_at": str(run.finished_at or ""),
            "sources_ok": [],
            "errors": 0,
            "error_details": [],
        }
    interval_note = (
        "Automatic collection is not a background daemon on Streamlit. "
        "Use Collect Latest Reviews, keep the dashboard open with a visit interval, "
        "or run `python -m scheduler.jobs` / the HTTP cron endpoint."
    )
    if interval_hours == 0:
        interval_note = "Scheduled collection is off (manual only). " + interval_note
    else:
        interval_note = (
            f"Visit-based incremental collection every {interval_hours}h is enabled when this app is open. "
            + interval_note
        )

    if page == "Overview":
        collect_latest = bool(
            overview_page.render(
                conversations_30,
                analysis_30,
                health,
                last_collection=last_collection,
                last_ai=last_ai,
                pending_ai=pending_ai,
                failed_ai=failed_ai,
                analyzed=analyzed,
                last_stats=last_stats,
                window_days=30,
            )
        )
    elif page == "Review Explorer":
        reviews_page.render(conversations_30, analysis_30, window_days=30)
    elif page == "Last 30 Days":
        last30_page.render(conversations_30, analysis_30)
    elif page == "Live Collection":
        collect_latest = collection_page.render(
            health,
            last_collection=last_collection,
            last_stats=last_stats,
            interval_note=interval_note,
        )
    elif page == "AI Insights":
        insights_page.render(conversations, analysis, opportunities, summary, brief_md)
    elif page == "Ask AI":
        ask_page.render(
            conversations_30,
            analysis_30,
            api_key=api_key,
            model=model,
            window_days=30,
        )
    elif page == "Part 1 — AI Discovery Answers":
        part1_page.render(analysis, opportunities)
    elif page == "Executive Discovery":
        executive_page.render(conversations, analysis, opportunities, summary)
    elif page == "Problem Landscape":
        problems_page.render(analysis, opportunities, filters)
    elif page == "Wishlist Behavior":
        wishlist_page.render(analysis, filters)
    elif page == "Purchase Blockers":
        blockers_page.render(analysis, filters)
    elif page == "Uncertainty Map":
        uncertainty_page.render(analysis, filters)
    elif page == "Comparison Behavior":
        comparison_page.render(analysis, filters)
    elif page == "External Information Seeking":
        workarounds_page.render(analysis, filters)
    elif page == "Evidence Explorer":
        evidence_page.render(analysis, themes, filters)
    elif page == "Segment Explorer":
        segments_page.render(analysis, opportunities, filters)
    elif page == "AI Research Brief":
        brief_page.render(brief_md)

    if collect_latest:
        bar = st.progress(0.0, text="Collecting latest public records…")
        try:
            _run_collection(
                enabled=enabled,
                max_records=int(max_records),
                model=model,
                temperature=temperature,
                api_key=api_key,
                window_days=30,
                full_refresh=False,
                extra_queries=extra_queries,
                progress_bar=bar,
            )
            st.rerun()
        except Exception as exc:
            logger.exception("Collect Latest Reviews failed")
            st.error(f"Collect Latest Reviews failed: {exc}")

    st.divider()
    st.markdown("### Export")
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        if not conversations.empty:
            st.download_button("Raw conversations CSV", data=_csv_bytes(conversations), file_name="conversations.csv")
    with e2:
        if not analysis.empty:
            export_a = analysis.copy()
            for col in ("blockers", "secondary_problems", "information_sought"):
                if col in export_a.columns:
                    export_a[col] = export_a[col].apply(
                        lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x
                    )
            st.download_button("Analyzed conversations CSV", data=_csv_bytes(export_a), file_name="analysis.csv")
            st.download_button(
                "AI analysis JSON",
                data=export_a.to_json(orient="records", date_format="iso").encode("utf-8"),
                file_name="analysis.json",
                mime="application/json",
            )
    with e3:
        if not themes.empty:
            st.download_button("Themes CSV", data=_csv_bytes(themes), file_name="themes.csv")
    with e4:
        if not opportunities.empty:
            st.download_button("Opportunities CSV", data=_csv_bytes(opportunities), file_name="opportunities.csv")
    if brief_md:
        st.download_button("Research brief Markdown", data=brief_md.encode("utf-8"), file_name="research_brief.md")


if __name__ == "__main__":
    main()
