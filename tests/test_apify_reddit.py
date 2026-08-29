"""Apify Reddit collector — missing credentials, normalize, comment identity."""

import hashlib

from collectors.apify_reddit import ApifyRedditCollector, actor_path
from collectors.google_play import GooglePlayCollector
from collectors.youtube import YouTubeCollector


def test_apify_missing_token(monkeypatch) -> None:
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.setenv("APIFY_REDDIT_ACTOR_ID", "trudax/reddit-scraper-lite")
    collector = ApifyRedditCollector(queries=["Myntra"], api_token="", actor_id="trudax/reddit-scraper-lite")
    ok, reason = collector.is_available()
    assert ok is False
    assert reason == "Apify API token is not configured."
    records, _failed = collector.collect()
    assert records == []
    assert collector.status == "unavailable"


def test_apify_missing_actor(monkeypatch) -> None:
    monkeypatch.setenv("APIFY_API_TOKEN", "token")
    monkeypatch.delenv("APIFY_REDDIT_ACTOR_ID", raising=False)
    collector = ApifyRedditCollector(queries=["Myntra"], api_token="token", actor_id="")
    ok, reason = collector.is_available()
    assert ok is False
    assert reason == "Apify Reddit Actor is not configured."


def test_actor_path_slash_to_tilde() -> None:
    assert actor_path("trudax/reddit-scraper-lite") == "trudax~reddit-scraper-lite"


def test_apify_normalize_post_and_comment_keep_distinct_hashes() -> None:
    collector = ApifyRedditCollector(queries=["Myntra"], api_token="t", actor_id="x/y")
    post = collector.normalize(
        {
            "dataType": "post",
            "parsedId": "abc123",
            "id": "abc123",
            "title": "Myntra wishlist",
            "body": "Same body text about fit uncertainty.",
            "url": "https://www.reddit.com/r/India/comments/abc123/",
            "communityName": "India",
            "username": "user1",
            "createdAt": "2026-08-01T00:00:00Z",
            "upVotes": 4,
            "numberOfComments": 2,
        }
    )
    comment = collector.normalize(
        {
            "dataType": "comment",
            "parsedId": "cmt999",
            "commentId": "cmt999",
            "postId": "abc123",
            "parentId": "abc123",
            "body": "Same body text about fit uncertainty.",
            "url": "https://www.reddit.com/r/India/comments/abc123/_/cmt999/",
            "communityName": "India",
            "username": "user2",
            "createdAt": "2026-08-02T00:00:00Z",
            "upVotes": 1,
        }
    )
    extra_p = __import__("json").loads(post["extra_json"])
    extra_c = __import__("json").loads(comment["extra_json"])
    assert post["source"] == "reddit"
    assert comment["source"] == "reddit"
    assert extra_p["content_type"] == "post"
    assert extra_c["content_type"] == "comment"
    assert extra_p["subreddit"] == "India"
    assert extra_c["collection_platform"] == "Apify"
    assert post["source_item_id"] != comment["source_item_id"]
    assert post["content_hash"] != comment["content_hash"]
    assert hashlib.sha256(b"reddit|cmt999|comment").hexdigest() == comment["content_hash"]


def test_play_and_youtube_collectors_still_import(monkeypatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    play = GooglePlayCollector()
    youtube = YouTubeCollector()
    assert play.name == "google_play"
    assert youtube.name == "youtube"
    ok, reason = youtube.is_available()
    assert ok is False
    assert "YOUTUBE_API_KEY" in reason
