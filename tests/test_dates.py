"""Date filtering and 30-day research window (publication date)."""

from datetime import datetime, timedelta, timezone

from processing.dates import in_research_window, window_bounds


def test_window_bounds_30_days() -> None:
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    start, end = window_bounds(30, now=now)
    assert end == now
    assert start == now - timedelta(days=30)


def test_in_window_uses_publication_not_collection() -> None:
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    published_inside = now - timedelta(days=10)
    published_outside = now - timedelta(days=45)
    assert in_research_window(published_inside, 30, now=now) is True
    assert in_research_window(published_outside, 30, now=now) is False
    assert in_research_window(None, 30, now=now) is False


def test_7_vs_30_vs_90() -> None:
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    pub = now - timedelta(days=20)
    assert in_research_window(pub, 7, now=now) is False
    assert in_research_window(pub, 30, now=now) is True
    assert in_research_window(pub, 90, now=now) is True
