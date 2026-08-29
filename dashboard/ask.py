"""Ask AI — grounded answers from retrieved stored records only."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ai.chatbot import answer_question
from analytics.records import analysis_period_label, build_review_records
from dashboard.ui import empty_state

EXAMPLES = [
    "Why are Myntra users not purchasing products they save?",
    "What are the biggest complaints in the last 30 days?",
    "Compare Google Play Store and Apple App Store complaints.",
    "What are users saying about fit and sizing?",
    "What are the top reasons users postpone purchases?",
    "What are the top unmet needs?",
    "Which problem appears most frequently?",
    "Show evidence for this insight.",
    "Why are users not purchasing items they wishlist?",
    "What are the top reasons for wishlist abandonment?",
    "What do users do outside Myntra before purchasing?",
]


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    *,
    api_key: str,
    model: str,
    window_days: int,
) -> None:
    st.subheader("Ask AI")
    st.caption(
        "Answers are retrieved from this application's collected public conversations, "
        "then summarized with OpenRouter. This is not a generic fashion chatbot."
    )
    period = analysis_period_label(int(window_days))
    st.markdown(f"**{period}**")

    records = build_review_records(conversations, analysis)
    if records.empty:
        empty_state("No real reviews were collected for this period.")
        return

    if not api_key.strip():
        st.error("OPENROUTER_API_KEY is not configured. Retrieval still works; the model cannot generate an answer.")

    choice = st.selectbox("Example questions", ["(type your own)"] + EXAMPLES)
    if "ask_q" not in st.session_state:
        st.session_state["ask_q"] = ""
    if choice != "(type your own)":
        st.session_state["ask_q"] = choice
    question = st.text_input("Your question", key="ask_q")
    asked = st.button("Ask", type="primary")

    if not asked:
        st.caption(f"{len(records)} stored records are available for retrieval. Only a small relevant subset is sent to the model.")
        return
    if not question.strip():
        st.warning("Enter a question.")
        return

    with st.spinner("Retrieving stored records and asking OpenRouter…"):
        result = answer_question(
            question.strip(),
            records,
            api_key=api_key.strip(),
            model=model,
            period_label=period,
        )

    st.markdown("### Direct answer")
    st.write(result["direct_answer"])
    st.markdown("### Key insight")
    st.write(result.get("key_insight") or "—")
    st.markdown(f"**Relevant retrieved records:** {result['n_records']}")
    st.markdown(f"**Sources:** {', '.join(result['sources']) or '—'}")
    st.markdown(f"**Date range of evidence:** {result['period']}")
    st.markdown(f"**Confidence:** {result.get('confidence') or 'low'}")

    st.markdown("### Evidence from collected reviews")
    if not result["evidence"]:
        st.caption("No stored quotations available.")
    for item in result["evidence"]:
        url = item.get("url") or ""
        link = f" — [Open Original Source]({url})" if url else ""
        st.markdown(f"{item['n']}. “{item['quote']}”")
        st.caption(f"Source: {item['source']} · Date: {item['date']}{link}")

    st.markdown("### Observed pattern")
    st.write(result.get("observed_pattern") or "—")
    st.markdown("### Important caveats")
    st.write(result.get("caveats") or "")
    st.caption("Quotations above are taken from stored records. They are not fabricated by the model.")
