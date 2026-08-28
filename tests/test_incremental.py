"""Incremental collection: only newer publication timestamps are kept."""

from datetime import datetime, timedelta, timezone

from processing.dates import is_after


def test_is_after_incremental_cutoff() -> None:
    last = datetime(2026, 8, 20, tzinfo=timezone.utc)
    older = last - timedelta(hours=2)
    newer = last + timedelta(minutes=5)
    assert is_after(older, last) is False
    assert is_after(newer, last) is True
    assert is_after(None, last) is True
    assert is_after(newer, None) is True


def test_incremental_filter_list() -> None:
    last = datetime(2026, 8, 20, tzinfo=timezone.utc)
    items = [
        {"id": "old", "published_at": last - timedelta(days=1)},
        {"id": "new", "published_at": last + timedelta(hours=1)},
    ]
    kept = [i for i in items if is_after(i["published_at"], last)]
    assert [i["id"] for i in kept] == ["new"]
