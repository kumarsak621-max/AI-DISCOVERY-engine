"""Opportunity Areas — ranked from stored analysis, not invented complaints."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from analytics.metrics import kpi_counts
from analytics.opportunities import multiplicative_framework_score
from config import OPPORTUNITY_WEIGHTS
from dashboard.ui import empty_state


def render(
    conversations: pd.DataFrame,
    analysis: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> None:
    st.subheader("Opportunity Areas")
    st.markdown(
        "Ranked research hypotheses from **analyzed public conversations**. "
        "This is not a list of product features and not Myntra conversion analytics."
    )
    with st.expander("Scoring methodology", expanded=False):
        st.markdown(
            """
Research-Based Opportunity Score is a weighted combination of:

- **Frequency** (20%): share of relevant records mentioning the theme  
- **Severity** (20%): share postponed / abandoned / waiting / rejected / alternative purchased  
- **Purchase relevance** (25%): high purchase intent plus still-open friction statuses  
- **Workaround** (15%): users leaving Myntra or describing a workaround  
- **Segment concentration** (10%): how concentrated the theme is in one segment  
- **Confidence** (10%): mean model confidence on those records  

Weights: """
            + ", ".join(f"{k}={v:.0%}" for k, v in OPPORTUNITY_WEIGHTS.items())
            + """

A second comparable score is also shown:

**Framework score** = Frequency share × Purchase relevance × User impact × Evidence strength  
(normalized 0–100 across opportunities in this table).

This is an evidence-based prioritization framework, **not proof of causality**.
"""
        )

    if conversations.empty:
        empty_state("No real records were collected from this source during the selected period.")
        return
    if opportunities.empty:
        empty_state("No opportunities scored yet. Collect real records, then run Analyze Reviews.")
        return

    kpis = kpi_counts(conversations, analysis)
    relevant_n = int(kpis.get("relevant") or 0)
    st.caption(f"Relevant analyzed records in window: **{relevant_n}**")

    ranked = opportunities.sort_values("opportunity_score", ascending=False).reset_index(drop=True)
    raw_scores = []
    for _, row in ranked.iterrows():
        evidence_n = int(row.get("evidence_count") or 0)
        raw_scores.append(
            multiplicative_framework_score(
                evidence_n,
                relevant_n,
                float(row.get("conversion_relevance_score") or 0),
                float(row.get("severity_score") or 0),
                evidence_n,
            )
        )
    peak = max(raw_scores) if raw_scores and max(raw_scores) > 0 else 1.0
    rows = []
    for i, row in ranked.iterrows():
        evidence_n = int(row.get("evidence_count") or 0)
        share = round(100.0 * evidence_n / relevant_n, 1) if relevant_n else 0.0
        conv = float(row.get("conversion_relevance_score") or 0)
        if conv >= 50:
            impact = "High"
        elif conv >= 25:
            impact = "Medium/High"
        else:
            impact = "Medium"
        framework = round(100.0 * raw_scores[int(i)] / peak, 1)
        rows.append(
            {
                "Rank": int(i) + 1,
                "Opportunity": row.get("opportunity_name"),
                "User problem": row.get("problem_statement"),
                "Frequency": evidence_n,
                "Percentage": share,
                "Purchase relevance": round(conv, 1),
                "User impact": impact,
                "Evidence count": evidence_n,
                "Sources": row.get("user_segment"),
                "Confidence": round(float(row.get("confidence_score") or 0), 1),
                "Weighted score": row.get("opportunity_score"),
                "Framework score (normalized)": framework,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    for _, row in ranked.head(8).iterrows():
        name = row.get("opportunity_name")
        st.markdown(f"### {name}")
        evidence_n = int(row.get("evidence_count") or 0)
        share = round(100.0 * evidence_n / relevant_n, 1) if relevant_n else 0.0
        st.write(
            f"Frequency: {evidence_n} records · {share}% of relevant records · "
            f"Purchase relevance: {round(float(row.get('conversion_relevance_score') or 0), 1)} · "
            f"Evidence: {evidence_n} records · Confidence: {round(float(row.get('confidence_score') or 0), 1)}"
        )
        st.caption(str(row.get("problem_statement") or ""))
        quotes = []
        try:
            quotes = json.loads(row.get("supporting_evidence") or "[]")
        except json.JSONDecodeError:
            quotes = []
        if quotes:
            for item in quotes[:4]:
                url = item.get("url") or ""
                link = f"[Open Original Source]({url})" if url else ""
                st.markdown(f"- “{item.get('quote')}” — `{item.get('source')}` {link}")
        else:
            st.caption("No grounded quotes stored for this opportunity.")
