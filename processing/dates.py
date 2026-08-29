"""Research-window date helpers. Membership uses publication date, not collection date."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from dateutil.relativedelta import relativedelta

from processing.cleaning import parse_timestamp

HISTORICAL_MONTHS = 30
DEFAULT_ANALYSIS_DAYS = 30


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def window_bounds(days: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or utcnow()
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(days=int(days))
    return start, end


def window_bounds_months(months: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or utcnow()
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - relativedelta(months=int(months))
    return start, end


def days_covering_months(months: int, now: datetime | None = None) -> int:
    start, end = window_bounds_months(months, now=now)
    return max(1, int((end - start).days))


def in_month_window(
    published_at: datetime | None,
    months: int,
    now: datetime | None = None,
) -> bool:
    if published_at is None:
        return False
    start, end = window_bounds_months(months, now=now)
    ts = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    return start <= ts <= end


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


def in_bounds(
    published_at: datetime | None,
    start: datetime,
    end: datetime,
) -> bool:
    if published_at is None:
        return False
    ts = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    lo = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    hi = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return lo <= ts <= hi


def resolve_window(
    *,
    days: int | None = None,
    months: int | None = None,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    if range_start is not None and range_end is not None:
        start = range_start if range_start.tzinfo else range_start.replace(tzinfo=timezone.utc)
        end = range_end if range_end.tzinfo else range_end.replace(tzinfo=timezone.utc)
        return start, end
    if months is not None:
        return window_bounds_months(int(months), now=now)
    return window_bounds(int(days or DEFAULT_ANALYSIS_DAYS), now=now)
