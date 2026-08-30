"""Collector availability and error isolation — no fake data when a source is blocked."""

from datetime import datetime, timezone

from collectors.app_store import AppStoreCollector
from collectors.google_play import GooglePlayCollector
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
            "link": {"attributes": {"href": "https://itunes.apple.com/in/review?id=907394059"}},
        }
    )
    assert record["source"] == "app_store"
    assert record["source_item_id"] == "12345"
    assert "itunes.apple.com" in record["source_url"]
    assert record["published_at"] is not None
    extra = __import__("json").loads(record["extra_json"])
    assert extra["source_type"] == "Apple App Store"
    assert extra["rating"] == 3
    assert extra["app_id"] == "907394059"


def test_google_play_empty_feed_is_zero_not_fake(monkeypatch) -> None:
    collector = GooglePlayCollector(max_records=5)
    monkeypatch.setattr(collector, "is_available", lambda: (True, ""))

    def fake_reviews(*_args, **_kwargs):
        return [], None

    monkeypatch.setattr("google_play_scraper.reviews", fake_reviews)
    records, _failed = collector.collect()
    assert records == []
    assert collector.status == "ok"


def test_google_play_reviews_are_normalized() -> None:
    collector = GooglePlayCollector()
    record = collector.normalize(
        {
            "reviewId": "abc123",
            "userName": "Pat",
            "content": "Size chart on Myntra is confusing so I did not buy the wishlisted dress.",
            "score": 2,
            "at": datetime(2026, 8, 20, tzinfo=timezone.utc),
            "thumbsUpCount": 1,
        }
    )
    assert record["source"] == "google_play"
    assert record["source_item_id"] == "abc123"
    assert "Size chart" in record["text"]
    extra = __import__("json").loads(record["extra_json"])
    assert extra["source_type"] == "Google Play Store"
    assert extra["rating"] == 2
    assert extra["app_id"] == "com.myntra.android"
    again = collector.normalize(
        {
            "reviewId": "abc123",
            "userName": "Pat",
            "content": "Size chart on Myntra is confusing so I did not buy the wishlisted dress.",
            "score": 2,
            "at": datetime(2026, 8, 20, tzinfo=timezone.utc),
        }
    )
    assert again["content_hash"] == record["content_hash"]


def test_cron_unauthorized_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert _authorized("anything") is False


def test_cron_authorized_with_matching_secret(monkeypatch) -> None:
    monkeypatch.setenv("CRON_SECRET", "abc123")
    assert _authorized("abc123") is True
    assert _authorized("wrong") is False
