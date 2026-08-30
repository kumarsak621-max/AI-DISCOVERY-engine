"""Settings — AI providers, collection sources, and scheduler. Keys are never displayed."""

from __future__ import annotations

import streamlit as st

from config import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_MODEL,
    HISTORICAL_WINDOW_MONTHS,
    SCHEDULER_INTERVALS,
)
from dashboard.ui import section_label
from processing.dates import days_covering_months


SOURCE_OPTIONS = ["google_play", "youtube"]


def render(
    *,
    default_openrouter_model: str,
    default_gemini_model: str,
    youtube_configured: bool,
    openrouter_configured: bool,
    gemini_configured: bool,
) -> None:
    st.subheader("Settings")
    st.caption(
        "API keys are read from environment variables or Streamlit Secrets. "
        "This page never prints secret values."
    )
    st.session_state.setdefault("openrouter_model", default_openrouter_model or DEFAULT_MODEL)
    st.session_state.setdefault("gemini_model", default_gemini_model or DEFAULT_GEMINI_MODEL)
    current = [s for s in (st.session_state.get("enabled_sources") or []) if s in SOURCE_OPTIONS]
    st.session_state["enabled_sources"] = current or list(SOURCE_OPTIONS)

    section_label("AI provider")
    st.radio("AI Provider", ["OpenRouter", "Gemini"], horizontal=True, key="ai_provider_label")
    st.text_input("OpenRouter model", key="openrouter_model")
    st.text_input("Gemini model", key="gemini_model")
    st.slider("Temperature", 0.0, 1.0, 0.1, 0.05, key="temperature")
    st.text_input("OpenRouter API key", type="password", key="openrouter_key")
    st.text_input("Gemini API key", type="password", key="gemini_key")
    if not (st.session_state.get("openrouter_key") or "").strip():
        st.warning("OpenRouter API key is not configured.")
    if not (st.session_state.get("gemini_key") or "").strip():
        st.warning("Gemini API key is not configured.")

    section_label("Collection sources")
    st.multiselect("Sources", SOURCE_OPTIONS, key="enabled_sources")
    st.selectbox("Max records per source", [100, 200, 500, 1000], key="max_records")
    extra = st.text_area(
        "Additional search queries (one per line)",
        key="extra_queries_text",
        height=90,
    )
    st.session_state["extra_queries"] = [q.strip() for q in (extra or "").splitlines() if q.strip()]

    section_label("Automatic collection")
    st.selectbox("Interval", list(SCHEDULER_INTERVALS.keys()), key="interval_label")
    hours = SCHEDULER_INTERVALS.get(st.session_state.get("interval_label"), 0)
    st.session_state["interval_hours"] = hours
    hist_days = days_covering_months(HISTORICAL_WINDOW_MONTHS)
    if hours == 0:
        st.info("Automatic collection is not active (manual only).")
    else:
        st.info(
            f"Visit-based incremental collection every {hours}h runs when the dashboard is open. "
            f"For true cron, run `python -m scheduler.jobs --window-days {hist_days}`."
        )
    st.caption(f"YouTube key: {'configured' if youtube_configured else 'not configured'}")
    st.caption("Required secrets: GEMINI_API_KEY, OPENROUTER_API_KEY, YOUTUBE_API_KEY.")
    _ = openrouter_configured
    _ = gemini_configured
