"""Myntra AI Wishlist Conversion Discovery Engine — live public data only."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone as tz
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

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
    DEFAULT_APIFY_REDDIT_ACTOR_ID,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_MODEL,
    HISTORICAL_WINDOW_MONTHS,
    SCHEDULER_INTERVALS,
)
from dashboard import ask as ask_page
from dashboard import collection as collection_page
from dashboard import insights as insights_page
from dashboard import opportunities_ui as opportunities_page
from dashboard import reviews as reviews_page
from dashboard import settings_page
from dashboard.ui import banner, hero, inject_theme
from database.db import init_db, session_scope
from database.models import AppSetting, CollectionRun, Conversation
from pipeline.discovery import analyze_window, run_discovery
from processing.dates import days_covering_months, utcnow, window_bounds, window_bounds_months

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("myntra_discovery")

PAGES = [
    "Data Collection Status",
    "Customer Insights",
    "Opportunity Explorer",
    "Feedback Explorer",
    "AI Product Manager Chatbot",
    "Settings",
]


def _secret(name: str, default: str = "") -> str:
    env_val = os.getenv(name, "")
    if env_val:
        return env_val
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _apply_secrets_to_env() -> None:
    """Collectors read os.environ; copy Streamlit secrets when env vars are empty."""
    for name in (
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "YOUTUBE_API_KEY",
        "APIFY_API_TOKEN",
        "APIFY_REDDIT_ACTOR_ID",
        "APIFY_REDDIT_SUBREDDITS",
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USER_AGENT",
        "CRON_SECRET",
        "PLAY_STORE_APP_ID",
        "APP_STORE_APP_ID",
        "APP_STORE_COUNTRY",
    ):
        val = _secret(name)
        if val and not os.getenv(name, "").strip():
            os.environ[name] = val


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


def _ensure_runtime_config(
    *,
    default_key: str,
    default_gemini: str,
    default_model: str,
    default_gemini_model: str,
) -> None:
    st.session_state.setdefault(
        "enabled_sources",
        ["apify_reddit", "youtube", "google_play", "app_store", "reddit", "web"],
    )
    st.session_state.setdefault("max_records", 200)
    st.session_state.setdefault("ai_provider_label", "OpenRouter")
    st.session_state.setdefault("openrouter_model", default_model)
    st.session_state.setdefault("gemini_model", default_gemini_model)
    st.session_state.setdefault("temperature", 0.1)
    st.session_state.setdefault("openrouter_key", default_key)
    st.session_state.setdefault("gemini_key", default_gemini)
    st.session_state.setdefault("extra_queries_text", "")
    st.session_state.setdefault("extra_queries", [])
    st.session_state.setdefault("interval_label", "Every 24 hours")
    st.session_state.setdefault("interval_hours", 24)


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
    provider: str = "openrouter",
    gemini_key: str = "",
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
            provider=provider,
            gemini_key=gemini_key,
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
        "source_coverage": list(getattr(run, "source_results", None) or []),
    }
    st.success(
        f"Collection {run.status}. Found {run.conversations_collected}, "
        f"new {run.conversations_new}, duplicates {getattr(run, 'conversations_duplicate', 0)}, "
        f"analyzed {run.conversations_analyzed}."
    )
    if not api_key.strip() and str(provider).lower() != "gemini":
        st.warning("OpenRouter API key is not configured. Records were stored; AI analysis remains pending.")
    elif str(provider).lower() == "gemini" and not gemini_key.strip():
        st.warning("Gemini API key is not configured. Records were stored; AI analysis remains pending.")
    return run


def _run_analysis(
    *,
    model: str,
    temperature: float,
    api_key: str,
    window_days: int,
    progress_bar,
    provider: str = "openrouter",
    gemini_key: str = "",
    window_months: int | None = None,
    range_start=None,
    range_end=None,
) -> dict:
    def on_progress(message: str, fraction: float) -> None:
        progress_bar.progress(min(max(fraction, 0.0), 1.0), text=message)

    with session_scope() as session:
        result = analyze_window(
            session,
            api_key=api_key.strip(),
            model=model.strip() or (DEFAULT_GEMINI_MODEL if str(provider).lower() == "gemini" else DEFAULT_MODEL),
            temperature=float(temperature),
            window_days=window_days,
            window_months=window_months,
            range_start=range_start,
            range_end=range_end,
            provider=provider,
            gemini_key=gemini_key.strip(),
            progress=on_progress,
        )
    st.session_state["last_analysis_stats"] = result
    if result.get("status") == "error":
        st.error(result.get("error") or "Analysis failed")
    else:
        st.success(
            f"Analyzed {result.get('analyzed', 0)} new/pending records "
            f"({result.get('already_labeled', 0)} already labeled in window) using "
            f"{result.get('ai_provider') or provider}. Failed: {result.get('failed', 0)}."
        )
    if result.get("error") and "not configured" in str(result.get("error")).lower():
        st.warning(result.get("error"))
    return result


def main() -> None:
    st.set_page_config(
        page_title="Myntra AI Discovery Engine",
        page_icon="🛍️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    _init()
    _apply_secrets_to_env()

    hero(
        "Myntra AI Discovery Engine",
        "AI-powered customer intelligence for Product Managers — "
        "automatically collect, analyze and discover insights from real user feedback.",
    )
    st.markdown(f"**Business Goal:** {BUSINESS_GOAL}")
    banner()

    default_key = _secret("OPENROUTER_API_KEY")
    default_gemini = _secret("GEMINI_API_KEY")
    default_model = _secret("OPENROUTER_MODEL", DEFAULT_MODEL)
    default_gemini_model = _secret("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    youtube_configured = bool(_secret("YOUTUBE_API_KEY"))
    apify_configured = bool(
        _secret("APIFY_API_TOKEN")
        and (_secret("APIFY_REDDIT_ACTOR_ID") or DEFAULT_APIFY_REDDIT_ACTOR_ID)
    )
    reddit_oauth = bool(_secret("REDDIT_CLIENT_ID") and _secret("REDDIT_CLIENT_SECRET"))
    cron_secret = _secret("CRON_SECRET")
    _ensure_runtime_config(
        default_key=default_key,
        default_gemini=default_gemini,
        default_model=default_model,
        default_gemini_model=default_gemini_model,
    )

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
                enabled=["reddit", "apify_reddit", "youtube", "web", "app_store", "google_play"],
                max_records=200,
                model=default_model,
                temperature=0.1,
                api_key=default_key,
                window_days=days_covering_months(HISTORICAL_WINDOW_MONTHS),
                full_refresh=False,
                extra_queries=[],
                progress_bar=bar,
                provider="openrouter",
                gemini_key=default_gemini,
            )
        except Exception as exc:
            logger.exception("Cron-triggered collection failed")
            st.error(f"Cron-triggered collection failed: {exc}")
        st.stop()

    hist_start, hist_end = window_bounds_months(HISTORICAL_WINDOW_MONTHS)
    hist_days = days_covering_months(HISTORICAL_WINDOW_MONTHS)
    window_days = 30

    with st.sidebar:
        st.markdown("**Myntra AI Discovery Engine**")
        st.caption("Customer intelligence for Product Managers")
        if "nav_page" not in st.session_state:
            st.session_state["nav_page"] = PAGES[0]
        page = st.radio("Navigation", PAGES, key="nav_page")
        st.divider()
        st.caption(f"Historical window: last {HISTORICAL_WINDOW_MONTHS} months ({hist_start.date()} → {hist_end.date()})")
        st.caption(BUSINESS_GOAL)

    enabled = list(st.session_state.get("enabled_sources") or ["apify_reddit", "youtube", "google_play"])
    max_records = int(st.session_state.get("max_records", 200))
    ai_provider_label = st.session_state.get("ai_provider_label", "OpenRouter")
    provider = "gemini" if ai_provider_label == "Gemini" else "openrouter"
    openrouter_model = str(st.session_state.get("openrouter_model") or default_model)
    gemini_model = str(st.session_state.get("gemini_model") or default_gemini_model)
    model = gemini_model.strip() if provider == "gemini" else openrouter_model.strip()
    temperature = float(st.session_state.get("temperature", 0.1))
    api_key = str(st.session_state.get("openrouter_key") or "")
    gemini_key = str(st.session_state.get("gemini_key") or "")
    extra_queries = list(st.session_state.get("extra_queries") or [])
    interval_hours = int(
        SCHEDULER_INTERVALS.get(
            st.session_state.get("interval_label"),
            st.session_state.get("interval_hours") or 0,
        )
        or 0
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
        total_records = session.query(Conversation).count()
        health = source_health_rows(session, openrouter_configured=bool(api_key.strip()))
        play_count = session.query(Conversation).filter(Conversation.source == "google_play").count()
        youtube_count = session.query(Conversation).filter(Conversation.source == "youtube").count()
        reddit_count = session.query(Conversation).filter(Conversation.source == "reddit").count()

    needs_first_run = collection_count == 0
    skip_auto = os.getenv("SKIP_AUTO_COLLECTION", "").strip().lower() in {"1", "true", "yes"}
    if needs_first_run and skip_auto:
        st.info("SKIP_AUTO_COLLECTION is set. First-run collection will not start automatically.")
    elif needs_first_run and not st.session_state.get("first_run_started"):
        st.info("Initializing 30-month historical collection...")
        st.session_state["first_run_started"] = True
        bar = st.progress(0.0, text="Initializing 30-month historical collection...")
        try:
            _run_collection(
                enabled=enabled,
                max_records=int(max_records),
                model=model,
                temperature=temperature,
                api_key=api_key,
                window_days=int(hist_days),
                full_refresh=True,
                extra_queries=extra_queries,
                progress_bar=bar,
                provider=provider,
                gemini_key=gemini_key,
            )
            st.rerun()
        except Exception as exc:
            logger.exception("First-run collection failed")
            st.error(f"First-run collection failed: {exc}")

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
                    window_days=int(hist_days),
                    full_refresh=False,
                    extra_queries=extra_queries,
                    progress_bar=bar,
                    provider=provider,
                    gemini_key=gemini_key,
                )
            except Exception as exc:
                logger.exception("Interval collection failed")
                st.warning(f"Interval collection failed: {exc}")

    with session_scope() as session:
        conversations_all = load_conversations_frame(session)
        analysis_all = load_analysis_frame(session)
        conversations_hist = load_conversations_frame(session, window_days=int(hist_days))
        analysis_hist = load_analysis_frame(session, window_days=int(hist_days))
        conversations_30 = load_conversations_frame(session, window_days=30)
        analysis_30 = load_analysis_frame(session, window_days=30)
        conversations = conversations_all
        analysis = analysis_all
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

    filters: dict = {}
    collect_latest = False
    collect_historical = False
    analyze_now = False
    if page == "Customer Insights" and not analysis.empty:
        with st.expander("Filters", expanded=False):
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
            "source_coverage": list(getattr(run, "source_results", None) or []),
        }
    analysis_audit = st.session_state.get("last_analysis_stats") or {}
    if summary and isinstance(summary, dict) and summary.get("audit"):
        analysis_audit = {**analysis_audit, **summary["audit"]}
    interval_note = (
        "Automatic collection is not a background daemon on Streamlit. "
        "Use Collect Latest Feedback, keep the dashboard open with a visit interval, "
        "or run `python -m scheduler.jobs` / the HTTP cron endpoint."
    )
    if interval_hours == 0:
        interval_note = "Scheduled collection is off (manual only). " + interval_note
    else:
        interval_note = (
            f"Visit-based incremental collection every {interval_hours}h is enabled when this app is open. "
            + interval_note
        )

    analyze_kwargs = {"window_days": 30, "window_months": None, "range_start": None, "range_end": None}

    if page == "Data Collection Status":
        actions = collection_page.render(
            conversations_all,
            analysis_all,
            health,
            last_collection=last_collection,
            last_ai=last_ai,
            last_stats=last_stats,
            interval_note=interval_note,
            interval_hours=interval_hours,
            hist_months=HISTORICAL_WINDOW_MONTHS,
            gemini_configured=bool(gemini_key.strip()),
            openrouter_configured=bool(api_key.strip()),
            youtube_configured=youtube_configured,
            apify_configured=apify_configured,
            play_ready=True,
            db_ready=True,
        ) or {}
        collect_latest = bool(actions.get("collect"))
        collect_historical = bool(actions.get("collect_historical"))
        analyze_now = bool(actions.get("analyze"))
    elif page == "Customer Insights":
        result = insights_page.render(
            conversations_hist,
            analysis_hist,
            opportunities,
            summary,
            brief_md,
            last_collection=last_collection,
            last_ai=last_ai,
            last_stats=last_stats,
            audit=analysis_audit,
            filters=filters,
        ) or {}
        analyze_now = bool(result.get("analyze"))
        analyze_kwargs = {
            "window_days": int(result.get("window_days") or 30),
            "window_months": result.get("window_months"),
            "range_start": result.get("range_start"),
            "range_end": result.get("range_end"),
        }
    elif page == "Opportunity Explorer":
        opportunities_page.render(conversations_30, analysis_30, opportunities)
    elif page == "Feedback Explorer":
        reviews_page.render(conversations_all, analysis_all, window_days=int(hist_days))
    elif page == "AI Product Manager Chatbot":
        ask_page.render(
            conversations_hist,
            analysis_hist,
            api_key=api_key,
            model=model,
            window_days=int(hist_days),
            provider=provider,
            gemini_key=gemini_key,
        )
    elif page == "Settings":
        settings_page.render(
            default_openrouter_model=default_model,
            default_gemini_model=default_gemini_model,
            youtube_configured=youtube_configured,
            apify_configured=apify_configured,
            reddit_oauth=reddit_oauth,
            openrouter_configured=bool(api_key.strip()),
            gemini_configured=bool(gemini_key.strip()),
        )

    if collect_latest:
        bar = st.progress(0.0, text="Collecting latest public records…")
        try:
            _run_collection(
                enabled=enabled,
                max_records=int(max_records),
                model=model,
                temperature=temperature,
                api_key=api_key,
                window_days=int(hist_days),
                full_refresh=False,
                extra_queries=extra_queries,
                progress_bar=bar,
                provider=provider,
                gemini_key=gemini_key,
            )
            st.rerun()
        except Exception as exc:
            logger.exception("Collect Latest Reviews failed")
            st.error(f"Collect Latest Feedback failed: {exc}")

    if collect_historical:
        bar = st.progress(0.0, text="Collecting historical public records…")
        try:
            _run_collection(
                enabled=enabled,
                max_records=int(max_records),
                model=model,
                temperature=temperature,
                api_key=api_key,
                window_days=int(hist_days),
                full_refresh=True,
                extra_queries=extra_queries,
                progress_bar=bar,
                provider=provider,
                gemini_key=gemini_key,
            )
            st.rerun()
        except Exception as exc:
            logger.exception("Collect Historical Feedback failed")
            st.error(f"Collect Historical Feedback failed: {exc}")

    if analyze_now:
        bar = st.progress(0.0, text="Analyzing stored records…")
        try:
            range_start = analyze_kwargs.get("range_start")
            range_end = analyze_kwargs.get("range_end")
            start_dt = end_dt = None
            if isinstance(range_start, date) and isinstance(range_end, date):
                start_dt = datetime(range_start.year, range_start.month, range_start.day, tzinfo=tz.utc)
                end_dt = datetime(range_end.year, range_end.month, range_end.day, 23, 59, 59, tzinfo=tz.utc)
            _run_analysis(
                model=model,
                temperature=temperature,
                api_key=api_key,
                window_days=int(analyze_kwargs.get("window_days") or 30),
                progress_bar=bar,
                provider=provider,
                gemini_key=gemini_key,
                window_months=analyze_kwargs.get("window_months"),
                range_start=start_dt,
                range_end=end_dt,
            )
            st.rerun()
        except Exception as exc:
            logger.exception("Analyze Reviews failed")
            st.error(f"Analyze Reviews failed: {exc}")

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
