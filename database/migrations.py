"""Lightweight SQLite migrations for additive columns (PostgreSQL-safe later)."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from database.models import Base

logger = logging.getLogger(__name__)


def apply_migrations(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "source_state" in tables and "source_health" not in tables:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE source_state RENAME TO source_health"))
            logger.info("Renamed source_state → source_health")
        inspector = inspect(engine)
        tables = inspector.get_table_names()
    if "conversations" not in tables:
        return
    existing = {col["name"] for col in inspector.get_columns("conversations")}
    statements: list[str] = []
    if "source_item_id" not in existing:
        statements.append("ALTER TABLE conversations ADD COLUMN source_item_id VARCHAR(256) DEFAULT ''")
    if "published_at" not in existing:
        statements.append("ALTER TABLE conversations ADD COLUMN published_at DATETIME")
        if "timestamp" in existing:
            statements.append("UPDATE conversations SET published_at = timestamp WHERE published_at IS NULL")
    if "extra_json" not in existing:
        statements.append("ALTER TABLE conversations ADD COLUMN extra_json TEXT DEFAULT '{}'")
    if "discovery_runs" in tables:
        run_cols = {col["name"] for col in inspector.get_columns("discovery_runs")}
        if "conversations_duplicate" not in run_cols:
            statements.append(
                "ALTER TABLE discovery_runs ADD COLUMN conversations_duplicate INTEGER DEFAULT 0"
            )
        if "records_fetched" not in run_cols:
            statements.append("ALTER TABLE discovery_runs ADD COLUMN records_fetched INTEGER DEFAULT 0")
        if "source_results_json" not in run_cols:
            statements.append("ALTER TABLE discovery_runs ADD COLUMN source_results_json TEXT DEFAULT '[]'")
        if "ai_provider" not in run_cols:
            statements.append("ALTER TABLE discovery_runs ADD COLUMN ai_provider VARCHAR(64) DEFAULT ''")
        if "ai_model" not in run_cols:
            statements.append("ALTER TABLE discovery_runs ADD COLUMN ai_model VARCHAR(128) DEFAULT ''")
    if "collection_runs" in tables:
        cr_cols = {col["name"] for col in inspector.get_columns("collection_runs")}
        if "requested_records" not in cr_cols:
            statements.append("ALTER TABLE collection_runs ADD COLUMN requested_records INTEGER DEFAULT 0")
    if statements:
        with engine.begin() as conn:
            for stmt in statements:
                try:
                    conn.execute(text(stmt))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Migration skipped (%s): %s", stmt, exc)
