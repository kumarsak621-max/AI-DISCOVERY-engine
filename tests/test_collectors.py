"""Collector availability and error isolation — no fake data when a source is blocked."""

from collectors.app_store import AppStoreCollector
from collectors.google_play import GooglePlayCollector
from collectors.reddit import RedditCollector
from collectors.youtube import YouTubeCollector
from scheduler.http_endpoint import _authorized


def test_youtube_unavailable_without_key(monkeypatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    collector = YouTubeCollector(queries=["Myntra"])
    ok, reason = collector.is_available()
    assert ok is False
    assert "YOUTUBE_API_KEY" in reason
    records, failed = collector.collect()
    assert records == []
    assert collector.status == "unavailable"


def test_google_play_reports_unavailable(monkeypatch) -> None:
    collector = GooglePlayCollector()
    monkeypatch.setattr(
        collector,
        "is_available",
        lambda: (False, "Google Play has no official public reviews API."),
    )
    ok, reason = collector.is_available()
    assert ok is False
    records, _failed = collector.collect()
    assert records == []
    assert collector.status == "unavailable"
    assert "official" in reason.lower()


def test_app_store_normalize_keeps_url_and_id() -> None:
    collector = AppStoreCollector()
    record = collector.normalize(
        {
            "id": {"label": "12345"},
            "title": {"label": "Sizing issue"},
            "content": {"label": "Wishlisted but sizing is unclear on Myntra"},
            "author": {"name": {"label": "A"}},
            "updated": {"label": "2026-08-10T00:00:00Z"},
            "im:rating": {"label": "3"},
        }
    )
    assert record["source"] == "app_store"
    assert record["source_item_id"] == "12345"
    assert "apps.apple.com" in record["source_url"]
    assert record["published_at"] is not None


def test_reddit_collect_without_queries_errors_cleanly() -> None:
    collector = RedditCollector(queries=[])
    records = collector.fetch()
    assert records == []
    assert collector.status in {"error", "unavailable", "unknown"}


def test_cron_unauthorized_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert _authorized("anything") is False


def test_cron_authorized_with_matching_secret(monkeypatch) -> None:
    monkeypatch.setenv("CRON_SECRET", "abc123")
    assert _authorized("abc123") is True
    assert _authorized("wrong") is False
