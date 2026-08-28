"""Live source adapter interface with incremental collection timestamps."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class SourceStateStore(ABC):
    @abstractmethod
    def get_last_collection_time(self, source: str) -> datetime | None: ...

    @abstractmethod
    def set_last_collection_time(self, source: str, when: datetime) -> None: ...

    @abstractmethod
    def set_status(
        self,
        source: str,
        *,
        status: str,
        error: str = "",
        found: int = 0,
        new: int = 0,
        failed: int = 0,
    ) -> None: ...


class SourceAdapter(ABC):
    name: str = "base"
    requires_credentials: bool = False

    def __init__(
        self,
        queries: list[str] | None = None,
        max_records: int = 100,
        state_store: SourceStateStore | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> None:
        self.queries = queries or []
        self.max_records = max_records
        self.state_store = state_store
        self.since = since
        self.until = until
        self.last_error = ""
        self.status = "unknown"

    def get_last_collection_time(self) -> datetime | None:
        if self.state_store is None:
            return None
        return self.state_store.get_last_collection_time(self.name)

    def set_last_collection_time(self, when: datetime) -> None:
        if self.state_store is not None:
            self.state_store.set_last_collection_time(self.name, when)

    def is_available(self) -> tuple[bool, str]:
        """Return (available, reason). Override when credentials are required."""
        return True, ""

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Collect raw records. Must not raise on missing credentials — return []."""

    @abstractmethod
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Map a raw record to the conversations schema."""

    @abstractmethod
    def validate(self, record: dict[str, Any]) -> bool:
        """Return True if the normalized record is usable."""

    def collect(self) -> tuple[list[dict[str, Any]], int]:
        """Returns (valid records, failed_normalize_or_validate count)."""
        available, reason = self.is_available()
        if not available:
            self.status = "unavailable"
            self.last_error = reason
            return [], 0
        try:
            raw_items = self.fetch()
        except Exception as exc:  # noqa: BLE001
            self.status = "error"
            self.last_error = str(exc)[:500]
            return [], 0
        out: list[dict[str, Any]] = []
        failed = 0
        for raw in raw_items:
            try:
                record = self.normalize(raw)
            except Exception:
                failed += 1
                continue
            if self.validate(record):
                out.append(record)
            else:
                failed += 1
            if len(out) >= self.max_records:
                break
        self.status = "ok" if out or not self.last_error else self.status
        if not self.last_error and self.status != "unavailable":
            self.status = "ok"
        return out, failed
