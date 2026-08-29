"""Ask AI — grounded answers from retrieved stored records only."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ai.chatbot import answer_question
from analytics.records import analysis_period_label, build_review_records
from dashboard.ui import empty_state

EXAMPLES = [
    "Why do users add fashion products to their wishlist?",
    "What prevents wishlisted products from eventually being purchased?",
    "What uncertainties remain after users have identified a product they like?",
    "What causes users to postpone a purchase?",
    "How do users compare multiple shortlisted products?",
    "What information do users seek outside Myntra before purchasing?",
    "What role do fit, size, styling, price, reviews, occasion and social validation play?",
    "When do users use the wishlist as genuine purchase intent versus simply as a bookmarking mechanism?",
    "How do these behaviors differ across user segments?",
    "What unmet needs emerge consistently across user conversations?",
    "What are the top 5 problems in the last 30 days?",
    "Which problem has the strongest evidence?",
    "Which source reports the most fit-related complaints?",
    "Compare Play Store and YouTube complaints.",
    "Show evidence for the biggest opportunity.",
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

    st.markdown("### DIRECT ANSWER")
    st.write(result["direct_answer"])
    st.markdown("### KEY FINDING")
    st.write(result.get("key_finding") or result.get("key_insight") or "—")

    st.markdown("### QUANTIFICATION")
    quant = result.get("quantification") or {}
    st.write(f"Retrieved real records used: **{result.get('n_records', 0)}**")
    themes = quant.get("themes") or {}
    if themes:
        st.write("Theme counts in retrieved set: " + ", ".join(f"{k} ({v})" for k, v in themes.items()))
    intents = quant.get("intents") or {}
    if intents:
        st.write("Purchase intent in retrieved set: " + ", ".join(f"{k} ({v})" for k, v in intents.items()))
    st.caption("These counts are from retrieved stored rows only — not from all Myntra users.")

    st.markdown("### EVIDENCE")
    if not result["evidence"]:
        st.caption("No stored quotations available.")
    for item in result["evidence"]:
        url = item.get("url") or ""
        link = f" — [Open Original Source]({url})" if url else ""
        st.markdown(f"{item['n']}. “{item['quote']}”")
        st.caption(f"Source: {item['source']} · Date: {item['date']}{link}")

    st.markdown("### SOURCE BREAKDOWN")
    breakdown = result.get("source_breakdown") or {}
    if breakdown:
        st.write(", ".join(f"{k}: {v}" for k, v in breakdown.items()))
    else:
        st.write("—")

    st.markdown("### DATE RANGE")
    st.write(result.get("period") or "—")
    st.markdown("### CONFIDENCE")
    st.write(result.get("confidence") or "low")
    st.markdown("### CAVEATS")
    st.write(result.get("caveats") or "")
    st.caption("Quotations above are taken from stored records. They are not fabricated by the model.")
