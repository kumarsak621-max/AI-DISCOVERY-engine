"""Ask AI — grounded answers from retrieved stored records only."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ai.chatbot import answer_question
from analytics.records import analysis_period_label, build_review_records, display_source
from dashboard.ui import empty_state

EXAMPLES = [
    "Why do users add fashion products to their wishlist?",
    "What prevents wishlisted products from being purchased?",
    "What are the biggest purchase barriers?",
    "What uncertainties do users have?",
    "Why do users postpone fashion purchases?",
    "How do users compare products?",
    "What information do users seek outside Myntra?",
    "What role does fit play?",
    "What role does price play?",
    "What role do reviews play?",
    "Which users use wishlist as bookmarking?",
    "Which users show genuine purchase intent?",
    "What are the biggest unmet needs?",
    "What problems appear across all sources?",
    "What problems are unique to Reddit?",
    "What problems are unique to Play Store?",
    "What problems are unique to YouTube?",
    "Which opportunity has the strongest evidence?",
    "Which opportunity is most relevant to wishlist-to-purchase conversion?",
    "What prevents wishlisted products from eventually being purchased?",
    "What uncertainties remain after users have identified a product they like?",
    "How do users compare multiple shortlisted products?",
    "What information do users seek outside Myntra before purchasing?",
    "What role do fit, size, styling, price, reviews, occasion and social validation play?",
    "When do users use the wishlist as genuine purchase intent versus simply as a bookmarking mechanism?",
    "How do these behaviors differ across user segments?",
    "What unmet needs emerge consistently across user conversations?",
]


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    *,
    api_key: str,
    model: str,
    window_days: int,
    provider: str = "openrouter",
    gemini_key: str = "",
) -> None:
    st.subheader("AI Product Manager Chatbot")
    st.caption(
        "Ask a question about the collected customer feedback. "
        "Answers retrieve real stored records, then send that evidence to the selected AI provider. "
        "Observed evidence is stored text. AI interpretation is labeled separately."
    )
    period = analysis_period_label(int(window_days))
    st.markdown(f"**{period}**")

    records = build_review_records(conversations, analysis)
    if not records.empty and "source" in records.columns:
        records = records[records["source"].isin(["google_play", "youtube"])]
    if records.empty:
        empty_state("No data available.")
        return

    if provider.lower() == "gemini" and not gemini_key.strip():
        st.error("Gemini API key is not configured.")
    elif provider.lower() != "gemini" and not api_key.strip():
        st.error("OpenRouter API key is not configured.")

    choice = st.selectbox("Example questions", ["(type your own)"] + EXAMPLES)
    if "ask_q" not in st.session_state:
        st.session_state["ask_q"] = ""
    if choice != "(type your own)":
        st.session_state["ask_q"] = choice
    question = st.text_input("Your question", key="ask_q")
    asked = st.button("Ask AI", type="primary")

    if not asked:
        st.caption(f"{len(records)} stored records are available for retrieval. Only a small relevant subset is sent to the model.")
        return
    if not question.strip():
        st.warning("Enter a question.")
        return

    with st.spinner("Retrieving stored records and asking the selected AI provider…"):
        result = answer_question(
            question.strip(),
            records,
            api_key=api_key.strip(),
            model=model,
            period_label=period,
            provider=provider,
            gemini_key=gemini_key.strip(),
        )

    st.markdown("### Direct Answer")
    st.write(result["direct_answer"])
    st.markdown("### Key Findings")
    st.write(result.get("key_finding") or result.get("key_insight") or "Insufficient evidence.")

    st.markdown("### Quantified Evidence")
    quant = result.get("quantification") or {}
    st.write(f"Retrieved real records used: **{result.get('n_records', 0)}**")
    themes = quant.get("themes") or {}
    if themes:
        st.write("Theme counts in retrieved set: " + ", ".join(f"{k} ({v})" for k, v in themes.items()))
    else:
        st.caption("Insufficient evidence.")
    intents = quant.get("intents") or {}
    if intents:
        st.write("Purchase intent in retrieved set: " + ", ".join(f"{k} ({v})" for k, v in intents.items()))
    st.caption("These counts are from retrieved stored rows only — not from all Myntra users.")

    st.markdown("### Source Comparison")
    breakdown = result.get("source_breakdown") or {}
    if breakdown:
        st.write(
            ", ".join(f"{display_source(k)}: {v}" for k, v in breakdown.items())
        )
    else:
        st.write("Insufficient evidence.")

    st.markdown("### Supporting Evidence")
    st.caption("OBSERVED EVIDENCE — stored user text. Not AI-generated.")
    if not result["evidence"]:
        st.caption("No stored quotations available.")
    for item in result["evidence"]:
        url = item.get("url") or ""
        link = f" — [Open Original Source]({url})" if url else ""
        src = display_source(item.get("source"))
        st.markdown(f"**Source:** {src}")
        st.markdown(f"**Date:** {item.get('date') or '—'}")
        if item.get("subreddit"):
            st.markdown(f"**Subreddit:** {item['subreddit']}")
        if item.get("video"):
            st.markdown(f"**Video:** {item['video']}")
        if item.get("rating") not in (None, "", "nan"):
            st.markdown(f"**Rating:** {item.get('rating')}")
        st.markdown(f"**Evidence:** “{item['quote']}”{link}")
        st.caption("Observed evidence above is stored text.")

    st.markdown("### Implication for Wishlist → Purchase Conversion")
    st.write(result.get("business_implication") or "Insufficient evidence.")
    st.caption("AI INTERPRETATION — hypothesis only, not a causal claim.")

    st.markdown("### Confidence")
    st.write(result.get("confidence") or "low")
    st.markdown("### Caveats")
    st.write(result.get("caveats") or "")
    st.caption(
        f"AI provider used: **{result.get('ai_provider') or '—'}** · "
        f"Model: **{result.get('ai_model') or model}**. "
        "Quotations above are taken from stored records. They are not fabricated by the model."
    )
