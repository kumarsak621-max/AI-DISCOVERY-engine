"""Tests for text cleaning and record normalization."""

from processing.cleaning import (
    clean_text,
    content_hash,
    hash_author,
    is_valid_conversation,
    normalize_for_hash,
    normalize_record,
    parse_timestamp,
)


def test_clean_text_whitespace() -> None:
    assert clean_text("  hello\n\n  world\t") == "hello world"


def test_normalize_for_hash_strips_urls_and_case() -> None:
    a = normalize_for_hash("Check https://myntra.com/x THIS Dress!!!")
    b = normalize_for_hash("check this dress")
    assert a == b


def test_content_hash_stable() -> None:
    assert content_hash("Hello World") == content_hash("hello   world")


def test_hash_author_not_raw() -> None:
    digest = hash_author("reddit_user_99")
    assert digest != "reddit_user_99"
    assert len(digest) == 16


def test_normalize_record_maps_fields() -> None:
    raw = {
        "source": "reddit",
        "url": "https://www.reddit.com/r/india/comments/abc",
        "author": "sam",
        "title": "Myntra wishlist",
        "text": "I added a kurta and I am waiting for the sale before I buy.",
        "created_utc": 1_700_000_000,
        "score": 12,
        "query": "Myntra wishlist",
    }
    record = normalize_record(raw)
    assert record["source"] == "reddit"
    assert record["source_url"].startswith("https://")
    assert record["content_hash"]
    assert "kurta" in record["text"]
    assert record["engagement_count"] == 12
    assert record["published_at"] is not None
    assert parse_timestamp(raw["created_utc"]) is not None


def test_is_valid_conversation_rejects_short() -> None:
    assert is_valid_conversation({"source": "reddit", "text": "too short"}) is False
    assert (
        is_valid_conversation(
            {
                "source": "reddit",
                "text": "I wishlisted a dress on Myntra but I am not sure about the size at all.",
            }
        )
        is True
    )
