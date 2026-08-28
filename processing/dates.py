"""Research-window date helpers. Membership uses publication date, not collection date."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from processing.cleaning import parse_timestamp


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def window_bounds(days: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or utcnow()
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(days=int(days))
    return start, end


def in_research_window(
    published_at: datetime | None,
    days: int,
    now: datetime | None = None,
) -> bool:
    if published_at is None:
        return False
    start, end = window_bounds(days, now=now)
    ts = published_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return start <= ts <= end


def coerce_published_at(value: Any) -> datetime | None:
    return parse_timestamp(value)


def is_after(published_at: datetime | None, since: datetime | None) -> bool:
    if published_at is None or since is None:
        return True
    ts = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    cutoff = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    return ts > cutoff
