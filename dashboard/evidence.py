"""Evidence explorer — from theme to quotes."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from dashboard.ui import empty_state, filter_analysis


def render(analysis: pd.DataFrame, themes: pd.DataFrame, filters: dict) -> None:
    st.subheader("Evidence Explorer")
    st.caption("Go from a ranked opportunity to the underlying quotes. Quotes must appear in original text.")

    df = filter_analysis(analysis, filters)
    relevant = df[df["relevant_to_wishlist"] == True] if not df.empty else df  # noqa: E712
    if relevant.empty:
        empty_state()
        return

    theme_names = ["All themes"] + (
        sorted(themes["theme_name"].tolist()) if not themes.empty else []
    )
    selected = st.selectbox("Theme", theme_names)
    show_high_intent = st.checkbox("High-intent friction only", value=False)
    show_validation = st.checkbox("Needs human validation only", value=False)

    view = relevant.copy()
    if selected != "All themes" and not themes.empty:
        # Match via primary problem / blocker heuristics used in clustering
        needle = selected.lower()
        mask = (
            view["primary_problem"].fillna("").str.lower().str.contains(needle.split()[0], regex=False)
            | view["uncertainty_type"].fillna("").str.lower().isin(
                [p.lower() for p in needle.replace("/", " ").split()]
            )
        )
        # Broader: if theme name contains FIT, filter fit-related blockers
        token_map = {
            "FIT": ["size_uncertainty", "fit_uncertainty", "appearance_uncertainty"],
            "PRICE": ["price_uncertainty", "waiting_for_price_drop", "budget_constraint"],
            "QUALITY": ["quality_uncertainty", "fabric_uncertainty"],
            "REVIEW": ["review_uncertainty", "trust_uncertainty"],
            "STYLING": ["styling_uncertainty", "occasion_uncertainty"],
            "COMPARISON": ["comparison_uncertainty"],
            "RETURN": ["return_uncertainty"],
            "DELIVERY": ["delivery_uncertainty"],
            "SOCIAL": ["social_validation"],
            "AVAILABILITY": ["availability_uncertainty"],
            "URGENCY": ["indecision", "low_urgency"],
            "ALTERNATIVE": ["discovered_better_alternative"],
        }
        blockers = []
        for token, vals in token_map.items():
            if token in selected.upper():
                blockers.extend(vals)
        if blockers:
            view = view[view["purchase_blocker"].isin(blockers) | view["blockers"].apply(
                lambda xs: any(b in (xs if isinstance(xs, list) else [xs]) for b in blockers)
            )]
        elif mask.any():
            view = view[mask]

    if show_high_intent:
        view = view[view["high_intent_friction"] == True]  # noqa: E712
    if show_validation:
        view = view[view["needs_human_validation"] == True]  # noqa: E712

    st.write(f"{len(view)} evidence rows")
    for _, row in view.head(80).iterrows():
        flag = "⚠️ Needs human validation" if row["needs_human_validation"] else ""
        with st.expander(
            f"{row['evidence_quote'][:80]} — {row['source']} · {row['purchase_intent']} / {row['purchase_status']} {flag}"
        ):
            st.markdown(f"**Original quote:** {row['evidence_quote']}")
            st.markdown(f"**Source:** `{row['source']}`")
            pub = row.get("published_at") or row.get("timestamp")
            st.markdown(f"**Publication date:** {pub}")
            st.markdown(f"**URL:** {row['source_url']}")
            if row.get("source_url"):
                st.markdown(f"[Open Original Source]({row['source_url']})")
            st.markdown(f"**Segment:** {row['user_segment']}")
            st.markdown(f"**Wishlist behavior:** {row['wishlist_behavior']}")
            st.markdown(f"**Purchase intent:** {row['purchase_intent']}")
            st.markdown(f"**Purchase status:** {row['purchase_status']}")
            st.markdown(f"**Blocker:** {row['purchase_blocker']}")
            st.markdown(f"**Uncertainty:** {row.get('uncertainty_type') or '—'} — {row.get('uncertainty_text') or ''}")
            st.markdown(f"**Workaround:** {row['workaround'] or '—'}")
            st.markdown(f"**Confidence:** {row['confidence']:.2f}")
            st.markdown("**Original text (preserved):**")
            st.text(row["original_text"] or row["text"])
