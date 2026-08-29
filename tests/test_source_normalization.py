"""Source normalization without network I/O."""

from collectors.reddit import RedditCollector
from collectors.youtube import YouTubeCollector


def test_reddit_normalize_hashes_author_and_keeps_url() -> None:
    collector = RedditCollector(queries=["Myntra wishlist"], max_records=5)
    record = collector.normalize(
        {
            "id": "abc123",
            "title": "Myntra wishlist question",
            "selftext": "I added a dress to my Myntra wishlist and I am waiting for the sale.",
            "author": "some_user_name",
            "permalink": "/r/india/comments/abc123/myntra/",
            "created_utc": 1_724_000_000,
            "score": 10,
            "num_comments": 4,
            "subreddit": "india",
            "_query": "Myntra wishlist",
            "_kind": "link",
        }
    )
    assert record["source"] == "reddit"
    assert record["source_item_id"] == "abc123"
    assert record["source_url"].startswith("https://www.reddit.com/")
    assert record["author_id_hash"] != "some_user_name"
    assert record["published_at"] is not None
    assert collector.validate(record) is True


def test_youtube_normalize_comment() -> None:
    collector = YouTubeCollector(queries=["Myntra haul"], max_records=5)
    record = collector.normalize(
        {
            "textOriginal": "This Myntra haul helped me decide whether to buy from my wishlist.",
            "publishedAt": "2026-08-01T10:00:00Z",
            "likeCount": "3",
            "authorChannelId": {"value": "UCxxxx"},
            "_video_id": "vid123",
            "_video_title": "Myntra haul",
            "_comment_id": "cmt1",
            "_query": "Myntra haul",
        }
    )
    assert record["source"] == "youtube"
    assert "youtube.com/watch" in record["source_url"]
    assert record["source_item_id"] == "cmt1"
    assert record["published_at"] is not None
    extra = __import__("json").loads(record["extra_json"])
    assert extra["source_type"] == "YouTube"
    assert extra["video_id"] == "vid123"
    assert extra["comment_id"] == "cmt1"
