"""External workarounds — information sought outside Myntra."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.ui import empty_state, filter_analysis


def render(analysis: pd.DataFrame, filters: dict) -> None:
    st.subheader("External Information Seeking")
    st.caption(
        "What users look up outside Myntra, and why they leave the listing. "
        "This is not a recommendation to build a specific feature."
    )
    df = filter_analysis(analysis, filters)
    relevant = df[df["relevant_to_wishlist"] == True] if not df.empty else df  # noqa: E712
    if relevant.empty:
        empty_state()
        return

    sources_required = [
        "Google",
        "YouTube",
        "Reddit",
        "Instagram",
        "friends",
        "influencers",
        "other shopping apps",
        "brand website",
        "physical store",
    ]
    sources = relevant["external_information_source"].fillna("unknown").replace("", "unknown")
    counts = sources.value_counts()
    count_df = pd.DataFrame(
        {
            "Where users go": sources_required + [s for s in counts.index if s not in sources_required],
        }
    )
    count_df["Conversations"] = count_df["Where users go"].map(counts).fillna(0).astype(int)
    st.plotly_chart(px.bar(count_df, x="Where users go", y="Conversations"), use_container_width=True)

    st.markdown("#### Information sought by source")
    for src in sources_required:
        sub = relevant[relevant["external_information_source"] == src]
        sought: list[str] = []
        for items in sub["information_sought"] if not sub.empty else []:
            if isinstance(items, list):
                sought.extend(str(x) for x in items if x)
        label = ", ".join(pd.Series(sought).value_counts().head(4).index.tolist()) if sought else "no evidence in corpus"
        st.markdown(f"- **{src}** ({int(len(sub))}): {label}")

    left = relevant[relevant["leaves_myntra"] == True]  # noqa: E712
    st.metric("Conversations reporting leaving Myntra for information", int(len(left)))

    st.markdown("#### Workarounds with evidence")
    shown = relevant[relevant["workaround"].astype(str).str.len() > 3].head(20)
    for _, row in shown.iterrows():
        url = row.get("source_url") or ""
        link = f" — [Open Original Source]({url})" if url else ""
        st.markdown(
            f"- “{row['evidence_quote']}” → workaround: *{row['workaround']}* "
            f"({row['external_information_source']}){link}"
        )
