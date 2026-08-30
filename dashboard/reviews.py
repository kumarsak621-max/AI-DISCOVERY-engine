"""Review Explorer — browse real collected records."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.quantify import source_counts
from analytics.records import SOURCE_LABELS, analysis_period_label, build_review_records, filter_review_records
from dashboard.review_cards import render_review_card
from dashboard.ui import empty_state

PAGE_SIZE = 20


def render(conversations: pd.DataFrame, analysis: pd.DataFrame, window_days: int) -> None:
    st.subheader("Feedback Explorer")
    st.markdown("Browse the real collected dataset. These are **public records**, not demo or synthetic reviews.")
    st.caption(analysis_period_label(int(window_days)))

    records = build_review_records(conversations, analysis)
    if not records.empty and "source" in records.columns:
        records = records[records["source"].isin(["google_play", "youtube", "manual"])]
    counts = source_counts(records)
    st.markdown(f"**Records in explorer frame: {counts.get('Total', 0):,}**")
    m1, m2, m3 = st.columns(3)
    m1.metric("Google Play", counts.get("Google Play Store", 0))
    m2.metric("YouTube", counts.get("YouTube", 0))
    m3.metric("Manual Upload", counts.get("Manual Upload", 0))
    st.caption("Counts are from the database for the selected research window. Zeros mean none were stored.")

    if records.empty:
        empty_state("No real records were collected from this source during the selected period.")
        return

    label_to_key = {label: key for key, label in SOURCE_LABELS}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        preset = st.selectbox(
            "Date preset",
            ["all_collected", "last_30_days", "last_6_months", "last_12_months", "last_30_months", "today"],
            format_func=lambda x: {
                "all_collected": "All collected",
                "last_30_days": "Last 30 Days",
                "last_6_months": "Last 6 Months",
                "last_12_months": "Last 12 Months",
                "last_30_months": "Last 30 Months",
                "today": "Today",
            }[x],
        )
    with c2:
        source_labels = ["All sources"] + [label for _, label in SOURCE_LABELS]
        selected_labels = st.multiselect("Source", source_labels)
        source = []
        for label in selected_labels:
            if label == "All sources":
                continue
            if label in label_to_key:
                source.append(label_to_key[label])
    with c3:
        sentiments = sorted(records["sentiment"].dropna().unique().tolist()) if "sentiment" in records.columns else []
        sentiment = st.multiselect("Sentiment", [s for s in sentiments if s])
    with c4:
        intents = sorted(records["purchase_intent"].dropna().unique().tolist()) if "purchase_intent" in records.columns else []
        intent = st.multiselect("Purchase intent", [s for s in intents if s])
        wish_intents = st.multiselect("Wishlist intent", ["High", "Medium", "Low", "Unknown", "Not analyzed"])

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        themes = ["All"]
        theme_col = "theme" if "theme" in records.columns and records["theme"].fillna("").astype(str).str.strip().ne("").any() else "primary_problem"
        if theme_col in records.columns:
            themes += sorted({str(x) for x in records[theme_col].dropna().tolist() if str(x).strip()})[:40]
        theme = st.selectbox("Theme / pain point", themes)
    with c6:
        rating_opts = []
        if "rating" in records.columns:
            for value in records["rating"].dropna().tolist():
                try:
                    rating_opts.append(int(float(value)))
                except (TypeError, ValueError):
                    continue
        rating = st.multiselect("Rating", sorted(set(rating_opts)))
    with c7:
        segs = sorted(records["user_segment"].dropna().unique().tolist()) if "user_segment" in records.columns else []
        segment = st.multiselect("User segment", [s for s in segs if s and s != "unknown"])
    with c8:
        langs = sorted({str(x) for x in records["language"].dropna().tolist() if str(x).strip()}) if "language" in records.columns else []
        language = st.multiselect("Language", langs)

    keyword = st.text_input("Keyword search (review/comment text, title, video title)")

    view = filter_review_records(
        records,
        preset=preset,
        source=source or None,
        sentiment=sentiment or None,
        intent=intent or None,
        theme=theme,
        rating=rating or None,
        language=language or None,
        segment=segment or None,
        keyword=keyword,
        wishlist_intent=wish_intents or None,
    )
    st.metric("Matching real records", int(len(view)))
    if view.empty:
        empty_state("No real records were collected from this source during the selected period.")
        return

    show = view.sort_values("published_at", ascending=False, na_position="last") if "published_at" in view.columns else view
    total = int(len(show))
    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1)
    start = (int(page) - 1) * PAGE_SIZE
    chunk = show.iloc[start : start + PAGE_SIZE]
    st.caption(f"Showing {start + 1}–{min(start + PAGE_SIZE, total)} of {total} real records.")
    for _, row in chunk.iterrows():
        render_review_card(row)
