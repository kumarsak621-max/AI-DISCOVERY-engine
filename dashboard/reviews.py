"""Review Explorer — browse real collected records."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.records import SOURCE_LABELS, analysis_period_label, build_review_records, filter_review_records
from dashboard.review_cards import render_review_card
from dashboard.ui import empty_state


def render(conversations: pd.DataFrame, analysis: pd.DataFrame, window_days: int) -> None:
    st.subheader("Review Explorer")
    st.markdown("These are **real collected public records**, not demo or synthetic reviews.")
    st.caption(analysis_period_label(int(window_days)))

    records = build_review_records(conversations, analysis)
    if records.empty:
        empty_state("No real reviews were collected for this period.")
        return

    label_to_key = {label: key for key, label in SOURCE_LABELS}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        preset = st.selectbox(
            "Date preset",
            ["last_30_days", "today", "all_in_window"],
            format_func=lambda x: {
                "last_30_days": "Last 30 days",
                "today": "Today",
                "all_in_window": "All in research window",
            }[x],
        )
    with c2:
        source_labels = [label for _, label in SOURCE_LABELS]
        selected_labels = st.multiselect("Source", source_labels)
        source = [label_to_key[label] for label in selected_labels if label in label_to_key]
    with c3:
        sentiments = sorted(records["sentiment"].dropna().unique().tolist()) if "sentiment" in records.columns else []
        sentiment = st.multiselect("Sentiment", [s for s in sentiments if s])
    with c4:
        intents = sorted(records["purchase_intent"].dropna().unique().tolist()) if "purchase_intent" in records.columns else []
        intent = st.multiselect("Purchase intent", [s for s in intents if s])

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        cats = sorted(records["fashion_category"].dropna().unique().tolist()) if "fashion_category" in records.columns else []
        category = st.multiselect("Product / category", [s for s in cats if s and s != "unknown"])
    with c6:
        themes = ["All"]
        if "primary_problem" in records.columns:
            themes += sorted({str(x) for x in records["primary_problem"].dropna().tolist() if str(x).strip()})[:40]
        theme = st.selectbox("Theme / pain point", themes)
    with c7:
        rating_opts = []
        if "rating" in records.columns:
            for value in records["rating"].dropna().tolist():
                try:
                    rating_opts.append(int(float(value)))
                except (TypeError, ValueError):
                    continue
        rating = st.multiselect("Rating", sorted(set(rating_opts)))
    with c8:
        langs = sorted({str(x) for x in records["language"].dropna().tolist() if str(x).strip()}) if "language" in records.columns else []
        language = st.multiselect("Language", langs)

    view = filter_review_records(
        records,
        preset=preset,
        source=source or None,
        sentiment=sentiment or None,
        intent=intent or None,
        category=category or None,
        theme=theme,
        rating=rating or None,
        language=language or None,
    )
    st.metric("Matching real records", int(len(view)))
    if view.empty:
        empty_state("No real reviews were collected for this period.")
        return

    show = view.sort_values("published_at", ascending=False, na_position="last") if "published_at" in view.columns else view
    st.caption("Open a row to see full text, URL, and AI labels.")
    for _, row in show.head(100).iterrows():
        render_review_card(row)
