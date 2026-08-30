"""Customer Insights — problems, barriers, segments, cross-source findings."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.quantify import source_comparison, theme_quantification
from analytics.records import build_review_records, display_source
from dashboard import analyze as analyze_page
from dashboard import blockers as blockers_page
from dashboard import comparison as comparison_page
from dashboard import part1 as part1_page
from dashboard import segments as segments_page
from dashboard import uncertainty as uncertainty_page
from dashboard import wishlist as wishlist_page
from dashboard.ui import data_layer_caption, empty_state, section_label


def _count_table(rows: list[dict], name_key: str, empty_msg: str) -> None:
    if not rows:
        empty_state("Insufficient evidence.")
        return
    frame = pd.DataFrame(rows)
    if "name" in frame.columns:
        frame = frame.rename(columns={"name": name_key, "count": "Count"})
    st.dataframe(frame, use_container_width=True, hide_index=True)


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    opportunities: pd.DataFrame,
    summary: dict | None,
    brief_md: str,
    *,
    last_collection=None,
    last_ai=None,
    last_stats: dict | None = None,
    audit: dict | None = None,
    filters: dict | None = None,
) -> dict:
    st.subheader("Customer Insights")
    st.caption(
        "Insights are labeled from real collected feedback. "
        "They are not Myntra conversion analytics and not sentiment-only summaries."
    )
    data_layer_caption()
    filters = filters or {}
    actions = {"analyze": False, "window_days": 30, "window_months": None, "range_start": None, "range_end": None}

    tab_overview, tab_analyze, tab_answers, tab_segments = st.tabs(
        ["Insight Overview", "Analyze Feedback", "Assignment Answers", "Segments & Behaviors"]
    )

    records = build_review_records(conversations, analysis)
    themes = theme_quantification(records)

    with tab_overview:
        section_label("Top User Problems")
        if themes.empty:
            empty_state("Insufficient evidence.")
        else:
            st.dataframe(themes, use_container_width=True, hide_index=True)
            st.caption("Share is of relevant analyzed records. Values are not invented.")

        section_label("Top Uncertainties")
        if summary:
            _count_table(summary.get("top_uncertainties") or [], "Uncertainty", "Insufficient evidence.")
        else:
            empty_state("Insufficient evidence.")

        section_label("Purchase Barriers")
        if summary:
            _count_table(summary.get("top_blockers") or [], "Barrier", "Insufficient evidence.")
        else:
            empty_state("Insufficient evidence.")

        section_label("Wishlist Behaviors")
        if not analysis.empty and "wishlist_behavior" in analysis.columns:
            wb = (
                analysis["wishlist_behavior"]
                .fillna("unknown")
                .replace("", "unknown")
                .value_counts()
                .reset_index()
            )
            wb.columns = ["Wishlist behavior", "Count"]
            if wb.empty:
                empty_state("Insufficient evidence.")
            else:
                st.dataframe(wb, use_container_width=True, hide_index=True)
        else:
            empty_state("Insufficient evidence.")

        section_label("User Segments")
        if summary:
            _count_table(summary.get("top_segments") or [], "Segment", "Insufficient evidence.")
        else:
            empty_state("Insufficient evidence.")

        section_label("Cross-source Findings")
        compare = source_comparison(records)
        if compare.empty:
            empty_state("No data collected.")
        else:
            compare = compare.copy()
            compare["Source"] = compare["Source"].map(
                lambda x: "Google Play" if x == "Google Play Store" else x
            )
            st.dataframe(compare, use_container_width=True, hide_index=True)
            present = compare[compare["Records"] > 0]["Source"].tolist()
            missing = compare[compare["Records"] == 0]["Source"].tolist()
            if present:
                st.caption("Sources with stored records: " + ", ".join(present))
            if missing:
                st.caption("No data collected for: " + ", ".join(missing))

        if not records.empty and "source" in records.columns and "primary_problem" in records.columns:
            by_source = records.copy()
            by_source["Source"] = by_source["source"].map(display_source)
            common = (
                by_source.dropna(subset=["primary_problem"])
                .groupby("primary_problem")["Source"]
                .nunique()
                .reset_index()
            )
            common = common[common["Source"] >= 2].sort_values("Source", ascending=False)
            st.markdown("**Problems appearing across multiple sources**")
            if common.empty:
                empty_state("Insufficient evidence.")
            else:
                common.columns = ["Theme", "Sources with evidence"]
                st.dataframe(common, use_container_width=True, hide_index=True)

    with tab_analyze:
        result = analyze_page.render(
            conversations,
            analysis,
            last_collection=last_collection,
            last_ai=last_ai,
            last_stats=last_stats,
            audit=audit,
        )
        actions.update(result or {})

    with tab_answers:
        if analysis.empty:
            empty_state("Insufficient evidence.")
        else:
            part1_page.render(analysis, opportunities)

    with tab_segments:
        wishlist_page.render(analysis, filters)
        st.divider()
        blockers_page.render(analysis, filters)
        st.divider()
        uncertainty_page.render(analysis, filters)
        st.divider()
        comparison_page.render(analysis, filters)
        st.divider()
        segments_page.render(analysis, opportunities, filters)

    _ = brief_md
    return actions
