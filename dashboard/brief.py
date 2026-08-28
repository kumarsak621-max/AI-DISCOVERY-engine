"""AI research brief page."""

from __future__ import annotations

import streamlit as st

from analytics.brief import brief_to_pdf_bytes
from dashboard.ui import empty_state


def render(brief_markdown: str, _unused: str | None = None) -> None:
    st.subheader("AI Research Brief")
    st.caption("Automatically assembled from ANALYZED DATA. OBSERVATION ≠ HYPOTHESIS ≠ OPPORTUNITY.")
    if not brief_markdown:
        empty_state("Run Discovery, then generate this brief.")
        return

    st.download_button(
        "Download Markdown",
        data=brief_markdown.encode("utf-8"),
        file_name="myntra_research_brief.md",
        mime="text/markdown",
    )
    try:
        pdf = brief_to_pdf_bytes(brief_markdown)
        st.download_button(
            "Download PDF",
            data=pdf,
            file_name="myntra_research_brief.pdf",
            mime="application/pdf",
        )
    except Exception:
        st.caption("PDF export unavailable in this environment.")

    st.markdown(brief_markdown)
