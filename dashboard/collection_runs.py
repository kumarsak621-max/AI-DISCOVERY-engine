"""Collection Runs — persisted collector and discovery run history."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from database.models import CollectionRun, DiscoveryRun
from dashboard.ui import empty_state


def load_collection_runs(session: Session, limit: int = 50) -> pd.DataFrame:
    rows = session.query(CollectionRun).order_by(CollectionRun.id.desc()).limit(limit).all()
    records = []
    for row in rows:
        records.append(
            {
                "Run ID": row.id,
                "Source": row.source,
                "Start time": str(row.started_at or ""),
                "End time": str(row.completed_at or ""),
                "Records fetched": int(row.records_found or 0),
                "Requested records": int(getattr(row, "requested_records", 0) or 0),
                "New records": int(row.records_new or 0),
                "Duplicates": int(row.records_duplicate or 0),
                "Errors": int(row.records_failed or 0),
                "Status": row.status,
                "Error message": (row.error_message or "")[:300],
            }
        )
    return pd.DataFrame.from_records(records)


def load_discovery_runs(session: Session, limit: int = 20) -> pd.DataFrame:
    rows = session.query(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(limit).all()
    records = []
    for row in rows:
        play = youtube = reddit = 0
        for item in row.source_results or []:
            src = str(item.get("source") or "")
            found = int(item.get("found") or 0)
            if src == "google_play":
                play = found
            elif src == "youtube":
                youtube = found
            elif src in {"reddit", "apify_reddit"}:
                reddit += found
        records.append(
            {
                "Run ID": row.id,
                "Start time": str(row.started_at or ""),
                "End time": str(row.finished_at or ""),
                "Play Store records fetched": play,
                "YouTube records fetched": youtube,
                "Reddit records fetched": reddit,
                "New records": int(row.conversations_new or 0),
                "Duplicates": int(row.conversations_duplicate or 0),
                "Errors": 1 if row.status in {"failed", "error"} else 0,
                "Status": row.status,
                "AI provider": getattr(row, "ai_provider", "") or "—",
            }
        )
    return pd.DataFrame.from_records(records)


def render(session: Session) -> None:
    st.subheader("Collection Runs")
    st.caption("Each row is a real collector or pipeline run stored in the database. Counts are not estimates.")

    discovery = load_discovery_runs(session)
    st.markdown("#### Pipeline runs")
    if discovery.empty:
        empty_state("No discovery pipeline runs have been stored yet.")
    else:
        st.dataframe(discovery, use_container_width=True, hide_index=True)

    sources = load_collection_runs(session)
    st.markdown("#### Per-source collector runs")
    if sources.empty:
        empty_state("No per-source collection runs have been stored yet.")
    else:
        st.dataframe(sources, use_container_width=True, hide_index=True)
