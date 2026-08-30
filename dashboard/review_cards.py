"""Shared card renderer for real collected reviews."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.records import (
    classification_label,
    display_source,
    rating_display,
    theme_display,
    title_level,
    wishlist_intent_label,
)


def render_review_card(row: pd.Series) -> None:
    title = str(row.get("title") or "")[:80]
    snippet = str(row.get("original_text") or row.get("text") or "")[:120]
    source = display_source(row.get("source"))
    pub = row.get("published_at") or "unknown publication date"
    header = f"{source} · {pub} — {title or snippet}"
    with st.expander(header, expanded=False):
        st.caption("REAL collected public record — not synthetic.")
        st.markdown(f"**Source / platform:** {source} (`{row.get('source') or 'unknown'}`)")
        st.markdown(f"**Publication date/time:** {pub}")
        st.markdown(f"**Collected at:** {row.get('collected_at') or '—'}")
        rating = rating_display(row.get("source"), row.get("rating"))
        st.markdown(f"**Rating:** {rating}")
        st.markdown(f"**Language:** {row.get('language') or 'unknown'}")
        url = str(row.get("source_url") or "")
        if url:
            st.markdown(f"**URL:** [Open Original Source]({url})")
        else:
            st.markdown("**URL:** not provided by source")
        author = str(row.get("author_id_hash") or "")
        st.markdown(f"**Author (hashed public id):** `{author[:16] or 'not available'}`")
        if str(row.get("source") or "") == "reddit":
            kind = str(row.get("content_type") or "community conversation")
            if kind in {"link", "post"}:
                kind = "post"
            elif kind in {"comment"}:
                kind = "comment"
            st.markdown("**Feedback type:** Community Conversation (`Reddit`)")
            st.markdown(f"**Post / comment:** {kind or '—'}")
            st.markdown(f"**Subreddit:** {row.get('subreddit') or 'not provided'}")
            score = row.get("score")
            st.markdown(f"**Score:** {score if pd.notna(score) and str(score) not in {'', 'None', 'nan'} else 'not provided'}")
            ncom = row.get("num_comments")
            if pd.notna(ncom) and str(ncom) not in {"", "None", "nan"}:
                st.markdown(f"**Number of comments:** {ncom}")
        st.markdown(f"**Product / brand / topic:** {row.get('fashion_category') or row.get('query_used') or row.get('title') or '—'}")
        video_title = str(row.get("video_title") or "")
        if video_title and str(row.get("source") or "") == "youtube":
            st.markdown(f"**Video title:** {video_title}")
            channel = str(row.get("channel") or "")
            if channel:
                st.markdown(f"**Channel:** {channel}")
        status = row.get("analysis_status")
        st.markdown(f"**Sentiment:** {classification_label(status, row.get('sentiment'), title_case=True)}")
        st.markdown(f"**Detected theme / pain point:** {theme_display(status, row.get('theme'), row.get('primary_problem') or row.get('pain_point'))}")
        purchase = (
            title_level(row.get("purchase_intent"))
            if str(status or "").strip().lower() == "complete"
            else classification_label(status, row.get("purchase_intent"))
        )
        st.markdown(f"**Purchase intent:** {purchase}")
        st.markdown(
            f"**Wishlist intent:** {wishlist_intent_label(row.get('wishlist_behavior'), status=status, wishlist_intent=row.get('wishlist_intent'))}"
        )
        st.markdown(f"**Wishlist behavior:** {row.get('wishlist_behavior') or '—'}")
        st.markdown(f"**User segment:** {classification_label(status, row.get('user_segment'))}")
        st.markdown(f"**Analysis status:** {row.get('analysis_status') or 'Not analyzed'}")
        provider = str(row.get("analysis_provider") or "").strip()
        model = str(row.get("analysis_model") or "").strip()
        analyzed_at = row.get("analyzed_at")
        if str(status or "").strip().lower() == "complete" and (provider or model or analyzed_at):
            bits = []
            if provider:
                bits.append(f"Provider: {provider}")
            if model:
                bits.append(f"Model: {model}")
            if analyzed_at is not None and str(analyzed_at) not in {"", "nan", "NaT", "None"}:
                bits.append(f"Analyzed: {analyzed_at}")
            if bits:
                st.caption(" · ".join(bits))
        insight = row.get("relevance_reason") or row.get("uncertainty_text") or ""
        st.markdown(f"**AI-generated insight:** {insight or 'pending analysis'}")
        st.markdown("**Review / comment text:**")
        st.text(str(row.get("original_text") or row.get("text") or ""))
        quote = str(row.get("evidence_quote") or "")
        if quote and quote.lower() != "no direct evidence":
            st.markdown(f"**Grounded quote:** “{quote}”")
