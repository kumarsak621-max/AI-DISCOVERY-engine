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
    if statements:
        with engine.begin() as conn:
            for stmt in statements:
                try:
                    conn.execute(text(stmt))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Migration skipped (%s): %s", stmt, exc)
