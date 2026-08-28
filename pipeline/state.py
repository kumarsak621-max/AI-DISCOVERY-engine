"""Persisted last_successful_collection_time per source."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from collectors.base import SourceStateStore
from database.models import SourceState, utcnow


class DbSourceStateStore(SourceStateStore):
    def __init__(self, session: Session) -> None:
        self.session = session

    def _row(self, source: str) -> SourceState:
        row = self.session.get(SourceState, source)
        if row is None:
            row = SourceState(source=source, status="unknown")
            self.session.add(row)
            self.session.flush()
        return row

    def get_last_collection_time(self, source: str) -> datetime | None:
        row = self.session.get(SourceState, source)
        if row is None:
            return None
        return row.last_successful_collection_time

    def set_last_collection_time(self, source: str, when: datetime) -> None:
        row = self._row(source)
        row.last_successful_collection_time = when
        row.updated_at = utcnow()
        if when.tzinfo is None:
            row.last_successful_collection_time = when.replace(tzinfo=timezone.utc)

    def set_status(
        self,
        source: str,
        *,
        status: str,
        error: str = "",
        found: int = 0,
        new: int = 0,
        failed: int = 0,
    ) -> None:
        row = self._row(source)
        row.status = status
        row.last_error = error
        row.last_records_found = found
        row.last_records_new = new
        row.last_records_failed = failed
        row.updated_at = utcnow()
