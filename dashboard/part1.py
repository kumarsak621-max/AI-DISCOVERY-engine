"""Part 1 — AI Discovery Answers. Direct answers to every research question."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.part1_answers import PCT_LABEL, build_part1_answers, part1_markdown
from dashboard.ui import empty_state


def _question_shell(q: dict) -> None:
    st.markdown(f"**{q['question']}**")
    st.info(q["direct_answer"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Evidence count", q["evidence_count"])
    c2.metric(PCT_LABEL, f"{q['pct_of_relevant']}%")
    c3.metric("High-intent evidence", q["high_intent_evidence"])
    c4.metric("Confidence", q["confidence"])
    segs = ", ".join(s["segment"] for s in q.get("segments") or []) or "insufficient evidence"
    st.markdown(f"**Relevant user segments:** {segs}")
    st.markdown(f"**Trend over the last 30 days (publication date):** {q['trend'].get('direction')}")
    weekly = q["trend"].get("weekly") or []
    if len(weekly) >= 2:
        st.plotly_chart(
            px.bar(
                pd.DataFrame(weekly),
                x="week",
                y="mentions",
                title="Weekly mentions in this question's evidence (publication date)",
            ),
            use_container_width=True,
        )
    st.markdown("**Representative real quotes**")
    if not q.get("quotes"):
        st.caption("no direct evidence")
    for item in q.get("quotes") or []:
        url = item.get("url") or ""
        link = f" — [Open source]({url})" if url else ""
        st.markdown(f"- “{item['quote']}” `{item.get('source')}`{link}")
    st.markdown("**Source links**")
    links = q.get("source_links") or []
    if not links:
        st.caption("No source URLs on the quoted rows.")
    for link in links:
        if link.get("url"):
            st.markdown(f"- [{link.get('source')}]({link['url']})")
    st.markdown("**Evidence gaps**")
    for gap in q.get("evidence_gaps") or []:
        st.markdown(f"- {gap}")


def _table(rows: list[dict], title: str, drop: list[str] | None = None) -> None:
    if not rows:
        st.caption(f"No rows for {title}.")
        return
    st.markdown(f"**{title}**")
    frame = pd.DataFrame(rows)
    for col in drop or []:
        if col in frame.columns:
            frame = frame.drop(columns=[col])
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_question_tables(key: str, q: dict) -> None:
    tables = q.get("tables") or {}
    if key == "q1":
        _table(tables.get("motivations") or [], "Top wishlist motivations")
    elif key == "q2":
        st.markdown("**Wanted the product but did not purchase** vs **Never intended to purchase**")
        st.json(tables.get("wanted_vs_never") or {})
        _table(
            tables.get("blockers_among_wanted") or [],
            "Blockers among 'wanted the product but did not purchase'",
        )
    elif key == "q3":
        _table(tables.get("uncertainty_map") or [], "Uncertainty map")
    elif key == "q4":
        _table(tables.get("postponement_reasons") or [], "Purchase delay reasons")
    elif key == "q5":
        st.markdown("**How many alternatives users typically consider**")
        st.caption("Numeric values appear only when a source stated a number. No invented counts.")
        st.json(tables.get("stated_alternative_counts") or {})
        _table(tables.get("attributes_compared") or [], "Comparison dimensions in stated text")
        _table(tables.get("where_they_compare") or [], "Where comparison happens")
        st.caption(
            f"Other shopping platform evidence: {tables.get('other_shopping_platform_evidence', 0)} · "
            f"Delay/open decision: {tables.get('comparison_associated_with_delay_or_open_decision', 0)} · "
            f"Alternative purchased: {tables.get('alternative_purchased_evidence', 0)}"
        )
    elif key == "q6":
        _table(tables.get("by_source") or [], "External sources (all listed; zero means no evidence in this corpus)")
        _table(tables.get("information_gaps") or [], "Information gaps (what they still seek)")
    elif key == "q7":
        st.caption(
            "Highest-frequency factor is **evidence strength**, not proof that it causes conversion failure."
        )
        for factor in tables.get("factors") or []:
            st.markdown(f"### {factor.get('factor')}")
            st.markdown(factor.get("what_users_say") or "")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Evidence frequency", factor.get("evidence_frequency", 0))
            m2.metric("High-intent frequency", factor.get("high_intent_frequency", 0))
            m3.metric("Postponement association", factor.get("postponement_association", 0))
            m4.metric("Evidence strength", factor.get("evidence_strength", "Low"))
            st.caption(
                f"Abandonment association: {factor.get('abandonment_association', 0)} · "
                f"External workaround association: {factor.get('external_workaround_association', 0)} · "
                f"{PCT_LABEL}: {factor.get('pct_of_relevant', 0)}% · "
                f"Affected segments: {factor.get('affected_segments')}"
            )
            for item in factor.get("quotes") or []:
                url = item.get("url") or ""
                link = f" — [source]({url})" if url else ""
                st.markdown(f"- “{item['quote']}”{link}")
        _table(tables.get("factors") or [], "Factor comparison", drop=["quotes", "what_users_say"])
    elif key == "q8":
        st.caption("These are **signals associated with purchase intent**, not actual conversion rates.")
        _table(tables.get("intent_categories") or [], "Wishlist intent categories")
    elif key == "q9":
        _table(tables.get("segments") or [], "Behavioral segments")
        _table(
            tables.get("matrix") or [],
            "Segment × problem matrix (High/Medium/Low/None from this corpus only)",
        )
    elif key == "q10":
        needs = tables.get("unmet_needs") or []
        if not needs:
            st.caption("No unmet need met the repetition rule in this corpus.")
        for need in needs:
            st.markdown(f"### User need: {need.get('user_need')}")
            st.markdown(f"- **Current problem:** {need.get('current_problem')}")
            st.markdown(f"- **Current workaround:** {need.get('current_workaround')}")
            st.markdown(f"- **Affected segment:** {need.get('affected_segment')}")
            st.markdown(f"- **Wishlist/purchase relevance:** {need.get('wishlist_purchase_relevance')}")
            st.markdown(
                f"- **Evidence strength:** {need.get('evidence_strength')} "
                f"(n={need.get('evidence_count')}, {PCT_LABEL} {need.get('pct_of_relevant')}%)"
            )
            st.markdown("**Evidence**")
            for item in need.get("quotes") or []:
                st.markdown(f"- “{item['quote']}” — {item.get('url') or ''}")


def render(analysis: pd.DataFrame, opportunities: pd.DataFrame) -> None:
    st.title("Part 1 — AI Discovery Answers")
    st.caption(
        "Direct answers to the discovery questions. Percentages are of analyzed public conversations, "
        "never of Myntra users. OBSERVATION ≠ HYPOTHESIS. Output is DISCOVERY → OPPORTUNITY HYPOTHESIS. "
        "No product solution is proposed."
    )
    if analysis.empty:
        empty_state("Collect and analyze public conversations before Part 1 can answer these questions.")
        return

    payload = build_part1_answers(analysis, opportunities)
    st.warning(payload["disclaimer"])
    m1, m2 = st.columns(2)
    m1.metric("Relevant conversations in window", payload["n_relevant"])
    m2.metric("Analyzed rows in window", payload["n_analyzed"])

    qs = payload["questions"]
    st.markdown(
        " | ".join(f"**{qs[f'q{i}']['title']}**" for i in range(1, 11))
        + " | **Chains** | **What we learned** | **Opportunities** | **Handoff**"
    )

    for i in range(1, 11):
        key = f"q{i}"
        q = qs[key]
        with st.expander(q["title"], expanded=True):
            _question_shell(q)
            _render_question_tables(key, q)

    st.header("Cross-question analysis")
    st.caption("Behavioral chains appear only when 3+ conversations in this corpus support the same sequence.")
    chains = payload.get("chains") or []
    if not chains:
        st.caption("No behavioral chain had 3+ supporting conversations. Chains are not invented.")
    for chain in chains:
        st.markdown(
            f"- **{chain['chain']}** — {chain['supporting_conversations']} supporting conversations "
            f"({chain['pct_of_relevant']}% {PCT_LABEL.lower()})"
        )
        for item in chain.get("quotes") or []:
            st.markdown(f"  - “{item['quote']}”")

    st.header("What we learned")
    syn = payload.get("synthesis") or {}
    labels = {
        "why_wishlist": "1. Why do users wishlist?",
        "closest_to_purchase": "2. Which wishlist users appear closest to purchase?",
        "high_intent_blockers": "3. What prevents high-intent users from purchasing?",
        "biggest_uncertainties": "4. What are their biggest uncertainties?",
        "how_they_compare": "5. How do they compare alternatives?",
        "external_information": "6. What information do they seek outside Myntra?",
        "factors_that_matter": "7. Which purchase factors matter most?",
        "segment_differences": "8. Which user segments experience which problems?",
        "workarounds": "9. What workarounds do users currently use?",
        "unmet_needs": "10. What unmet needs repeatedly emerge?",
    }
    for key, label in labels.items():
        st.markdown(f"### {label}")
        st.write(syn.get(key) or "Insufficient evidence.")

    st.header("Opportunity prioritization")
    st.caption(
        "Research-Based Opportunity Score. **DISCOVERY → OPPORTUNITY HYPOTHESIS.** Not feature design."
    )
    _table(payload.get("opportunities") or [], "Top 5 opportunity hypotheses")
    st.markdown(payload.get("why_top_opportunity") or "")
    st.markdown("### Why this opportunity is more promising than the alternatives")
    st.write(payload.get("why_top_opportunity") or "Insufficient evidence.")

    st.header("Primary research handoff")
    h = payload.get("handoff") or {}
    st.markdown("### Recommended interview segment")
    st.write(h.get("recommended_interview_segment"))
    st.write(h.get("why_segment"))
    st.markdown("### Recommended problem to validate")
    st.write(h.get("recommended_problem_to_validate"))
    st.write(h.get("why_problem"))
    st.markdown("### 10 interview hypotheses")
    for hyp in h.get("interview_hypotheses") or []:
        st.markdown(f"- {hyp}")
    st.markdown("### Questions we still cannot answer from public data")
    st.caption("These unknowns are inputs to Part 3 user interviews.")
    for item in h.get("questions_public_data_cannot_answer") or []:
        st.markdown(f"- {item}")

    md = part1_markdown(payload)
    st.download_button(
        "Download Part 1 answers (Markdown)",
        data=md.encode("utf-8"),
        file_name="part1_discovery_answers.md",
        mime="text/markdown",
    )
