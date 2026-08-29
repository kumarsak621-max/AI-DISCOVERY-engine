"""Live discovery pipeline: incremental collect → dedupe → analyze new only → cluster → score."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from ai.analyzer import ConversationAnalyzer
from ai.clustering import cluster_and_store
from ai.openrouter import OpenRouterClient
from analytics.brief import render_research_brief
from analytics.metrics import (
    build_discovery_summary,
    latest_run,
    load_analysis_frame,
    load_conversations_frame,
    load_opportunities_frame,
)
from analytics.opportunities import build_opportunities
from collectors.app_store import AppStoreCollector
from collectors.google_play import GooglePlayCollector
from collectors.reddit import RedditCollector
from collectors.web_scraper import WebCollector
from collectors.youtube import YouTubeCollector
from config import DISCOVERY_QUERIES, YOUTUBE_QUERIES
from database.models import CollectionRun, Conversation, DiscoveryRun
from pipeline.state import DbSourceStateStore
from processing.cleaning import is_valid_conversation, normalize_record
from processing.dates import in_research_window, utcnow, window_bounds
from processing.deduplication import deduplicate_records, flag_syndicated
from processing.language import detect_language

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, float], None]

COLLECTOR_FACTORIES = {
    "reddit": RedditCollector,
    "youtube": YouTubeCollector,
    "web": WebCollector,
    "google_play": GooglePlayCollector,
    "app_store": AppStoreCollector,
}


def _emit(cb: ProgressCb | None, message: str, fraction: float) -> None:
    if cb:
        cb(message, fraction)


def persist_conversations(
    session: Session, records: list[dict[str, Any]]
) -> tuple[list[Conversation], int, int]:
    """Insert only new records. Returns (new_rows, duplicate_count, failed_count)."""
    new_rows: list[Conversation] = []
    duplicates = 0
    failed = 0
    seen_hash: set[str] = set()
    for record in records:
        digest = record.get("content_hash")
        item_id = str(record.get("source_item_id") or "")
        source = str(record.get("source") or "")
        url = str(record.get("source_url") or "")
        if not digest:
            failed += 1
            continue
        if digest in seen_hash:
            duplicates += 1
            continue
        existing = (
            session.query(Conversation).filter(Conversation.content_hash == digest).first()
        )
        if existing:
            duplicates += 1
            seen_hash.add(digest)
            continue
        if item_id:
            existing_id = (
                session.query(Conversation)
                .filter(Conversation.source == source, Conversation.source_item_id == item_id)
                .first()
            )
            if existing_id:
                duplicates += 1
                continue
        if url and not item_id:
            existing_url = (
                session.query(Conversation).filter(Conversation.source_url == url).first()
            )
            if existing_url:
                duplicates += 1
                continue
        try:
            row = Conversation(
                source=source,
                source_item_id=item_id,
                source_url=url,
                author_id_hash=record.get("author_id_hash") or "",
                published_at=record.get("published_at"),
                title=record.get("title") or "",
                text=record["text"],
                original_text=record.get("original_text") or record["text"],
                language=record.get("language") or "unknown",
                query_used=record.get("query_used") or "",
                engagement_count=int(record.get("engagement_count") or 0),
                content_hash=digest,
                is_syndicated=bool(record.get("is_syndicated", False)),
                extra_json=record.get("extra_json") or "{}",
                analysis_status="pending",
            )
            session.add(row)
            session.flush()
            new_rows.append(row)
            seen_hash.add(digest)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Insert failed: %s", exc)
            failed += 1
    session.commit()
    for row in new_rows:
        session.refresh(row)
    return new_rows, duplicates, failed


def prepare_records(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in raw_records:
        record = raw if "content_hash" in raw else normalize_record(raw)
        if not record.get("language") or record.get("language") == "unknown":
            record["language"] = detect_language(record.get("text") or "")
        min_chars = 20 if record.get("source") in {"app_store", "google_play", "youtube"} else 40
        if record.get("source") == "reddit":
            min_chars = 30
        if is_valid_conversation(record, min_chars=min_chars):
            normalized.append(record)
    unique, _dupes = deduplicate_records(normalized)
    return flag_syndicated(unique)


def collect_source(
    session: Session,
    source_name: str,
    *,
    max_records: int,
    since: datetime | None,
    until: datetime | None,
    extra_queries: list[str] | None,
) -> tuple[list[dict[str, Any]], CollectionRun]:
    store = DbSourceStateStore(session)
    factory = COLLECTOR_FACTORIES[source_name]
    kwargs: dict[str, Any] = {
        "max_records": max_records,
        "state_store": store,
        "since": since,
        "until": until,
    }
    if source_name == "reddit":
        kwargs["queries"] = list(DISCOVERY_QUERIES) + (extra_queries or [])
    elif source_name == "youtube":
        kwargs["queries"] = list(YOUTUBE_QUERIES)
        kwargs["api_key"] = os.getenv("YOUTUBE_API_KEY", "")
    collector = factory(**kwargs)
    run = CollectionRun(source=source_name, status="running", started_at=utcnow())
    session.add(run)
    session.commit()

    available, reason = collector.is_available()
    if not available:
        run.status = "unavailable"
        run.error_message = reason
        run.completed_at = utcnow()
        store.set_status(source_name, status="unavailable", error=reason)
        session.commit()
        return [], run

    records, failed = collector.collect()
    run.records_found = len(records)
    run.records_failed = failed
    if collector.status == "error":
        run.status = "error"
        run.error_message = collector.last_error
        store.set_status(
            source_name,
            status="error",
            error=collector.last_error,
            found=len(records),
            failed=failed,
        )
    elif collector.status == "unavailable":
        run.status = "unavailable"
        run.error_message = collector.last_error
        store.set_status(
            source_name,
            status="unavailable",
            error=collector.last_error,
            found=len(records),
            failed=failed,
        )
    else:
        run.status = "ok"
        store.set_status(
            source_name,
            status="ok",
            error=collector.last_error,
            found=len(records),
            failed=failed,
        )
    run.completed_at = utcnow()
    session.commit()
    return records, run


def analyze_window(
    session: Session,
    *,
    api_key: str,
    model: str,
    temperature: float,
    window_days: int = 30,
    progress: ProgressCb | None = None,
    discovery_run: DiscoveryRun | None = None,
) -> dict[str, Any]:
    """Analyze stored records in the publication-date window. Does not collect or invent reviews."""
    start, end = window_bounds(window_days)
    client = OpenRouterClient(api_key=api_key, model=model, temperature=temperature)
    if not client.is_configured:
        return {
            "status": "error",
            "error": "OPENROUTER_API_KEY is not set",
            "analyzed": 0,
            "failed": 0,
            "pending": 0,
            "already_labeled": 0,
        }
    _emit(progress, "AI analysis", 0.2)
    pending = (
        session.query(Conversation)
        .filter(Conversation.analysis_status.in_(["pending", "failed"]))
        .all()
    )
    pending = [
        c
        for c in pending
        if c.published_at is None or in_research_window(c.published_at, window_days, now=end)
    ]
    analyzer = ConversationAnalyzer(client)
    analyzed, failed = analyzer.analyze_batch(session, pending)
    _emit(progress, "Theme clustering", 0.65)
    windowed = (
        session.query(Conversation)
        .filter(
            (Conversation.published_at.is_(None))
            | ((Conversation.published_at >= start) & (Conversation.published_at <= end))
        )
        .all()
    )
    analyses = [c.analysis for c in windowed if c.analysis is not None]
    cluster_and_store(session, analyses, llm_client=client)
    _emit(progress, "Opportunity scoring", 0.85)
    build_opportunities(session, analyses)
    conv_df = load_conversations_frame(session, window_days=window_days)
    analysis_df = load_analysis_frame(session, window_days=window_days)
    opp_df = load_opportunities_frame(session)
    summary = build_discovery_summary(conv_df, analysis_df, opp_df)
    brief = render_research_brief(summary, window_days=window_days)
    target = discovery_run or latest_run(session)
    if target:
        if analyzed:
            target.last_ai_success_at = utcnow()
        target.conversations_analyzed = analyzed
        target.relevant_count = int(summary["kpis"].get("relevant") or 0)
        target.summary_json = json.dumps(summary)
        target.brief_markdown = brief
        session.commit()
    _emit(progress, "Analysis complete", 1.0)
    return {
        "status": "complete",
        "error": "",
        "analyzed": analyzed,
        "failed": failed,
        "pending": len(pending),
        "already_labeled": len(analyses),
    }


def run_discovery(
    session: Session,
    *,
    enabled_sources: list[str],
    max_records: int,
    model: str,
    temperature: float,
    api_key: str,
    window_days: int = 30,
    full_refresh: bool = False,
    extra_queries: list[str] | None = None,
    progress: ProgressCb | None = None,
) -> DiscoveryRun:
    start, end = window_bounds(window_days)
    run = DiscoveryRun(
        status="running",
        started_at=utcnow(),
        window_days=window_days,
        full_refresh=full_refresh,
    )
    session.add(run)
    session.commit()

    try:
        store = DbSourceStateStore(session)
        all_raw: list[dict[str, Any]] = []
        source_results: list[dict[str, Any]] = []
        sources = enabled_sources or ["reddit", "youtube", "web", "app_store", "google_play"]
        n = max(len(sources), 1)
        for i, source_name in enumerate(sources):
            if source_name not in COLLECTOR_FACTORIES:
                continue
            label = {
                "reddit": "Collecting Reddit",
                "youtube": "Collecting YouTube",
                "web": "Collecting public web sources",
                "google_play": "Collecting Google Play",
                "app_store": "Collecting App Store",
            }.get(source_name, f"Collecting {source_name}")
            _emit(progress, label, 0.05 + 0.25 * (i / n))
            since = None if full_refresh else store.get_last_collection_time(source_name)
            if full_refresh:
                since = start
            try:
                records, src_run = collect_source(
                    session,
                    source_name,
                    max_records=max_records,
                    since=since,
                    until=end,
                    extra_queries=extra_queries,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Source %s failed: %s", source_name, exc)
                err = CollectionRun(
                    source=source_name,
                    status="error",
                    error_message=str(exc)[:500],
                    started_at=utcnow(),
                    completed_at=utcnow(),
                )
                session.add(err)
                store.set_status(source_name, status="error", error=str(exc)[:500])
                session.commit()
                source_results.append(
                    {
                        "source": source_name,
                        "status": "error",
                        "found": 0,
                        "error": str(exc)[:500],
                    }
                )
                continue
            # Keep only records with an actual publication timestamp inside the research window.
            in_window = []
            for rec in records:
                pub = rec.get("published_at")
                if pub is None:
                    continue
                if in_research_window(pub, window_days, now=end):
                    in_window.append(rec)
            all_raw.extend(in_window)
            source_results.append(
                {
                    "source": source_name,
                    "status": src_run.status,
                    "found": len(in_window),
                    "error": src_run.error_message or "",
                }
            )
            if src_run.status == "ok":
                store.set_last_collection_time(source_name, utcnow())
            session.commit()

        _emit(progress, "Cleaning", 0.35)
        prepared = prepare_records(all_raw)
        _emit(progress, "Deduplicating", 0.42)
        new_rows, dupes, failed = persist_conversations(session, prepared)
        run.conversations_collected = len(prepared)
        run.conversations_new = len(new_rows)
        run.conversations_duplicate = int(dupes)
        run.records_fetched = len(all_raw)
        run.source_results = source_results

        # Update last collection run duplicate counts
        last_runs = (
            session.query(CollectionRun).order_by(CollectionRun.id.desc()).limit(len(sources)).all()
        )
        if last_runs:
            last_runs[0].records_duplicate = dupes
            last_runs[0].records_new = len(new_rows)
            last_runs[0].records_failed += failed
            session.commit()

        _emit(progress, "AI analysis", 0.5)
        result = analyze_window(
            session,
            api_key=api_key,
            model=model,
            temperature=temperature,
            window_days=window_days,
            progress=progress,
            discovery_run=run,
        )
        if result["status"] == "error":
            logger.warning("%s — collected data stored, analysis pending", result.get("error"))
            run.conversations_analyzed = 0
        else:
            run.conversations_analyzed = int(result.get("analyzed") or 0)

        run.status = "complete"
        run.finished_at = utcnow()
        session.commit()
        _emit(progress, "Discovery complete", 1.0)
        return run
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:1000]
        run.finished_at = utcnow()
        session.commit()
        logger.exception("Discovery run failed")
        raise
