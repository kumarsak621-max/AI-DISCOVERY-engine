"""Display labels and manual upload parsing — no fabricated product reviews."""

from analytics.records import (
    classification_label,
    corpus_stats,
    display_source,
    rating_display,
    theme_display,
    wishlist_intent_label,
)
from dashboard.ui import overall_collection_status
from dashboard.upload import frame_to_records, parse_upload_bytes
import pandas as pd


def test_display_source_labels() -> None:
    assert display_source("google_play") == "Google Play"
    assert display_source("youtube") == "YouTube"
    assert display_source("unknown_source") == "unknown_source"
    assert display_source("manual") == "Manual Upload"
    assert display_source("") == "Unknown"


def test_wishlist_intent_from_behavior() -> None:
    assert (
        wishlist_intent_label(
            "explicit_wishlist", status="complete", wishlist_intent="High"
        )
        == "High"
    )
    assert (
        wishlist_intent_label(
            "price_watch", status="complete", wishlist_intent="Unknown"
        )
        == "Unknown"
    )
    assert wishlist_intent_label("", status="pending") == "Not analyzed"
    assert wishlist_intent_label("", status="failed") == "Analysis failed"


def test_rating_display_does_not_invent_youtube_stars() -> None:
    assert rating_display("youtube", None) == "—"
    assert rating_display("youtube", 5) == "—"
    assert rating_display("google_play", 4) == 4
    assert rating_display("google_play", None) == "Not available"


def test_classification_distinguishes_pending_unknown_and_failed() -> None:
    assert classification_label("pending", None) == "Not analyzed"
    assert classification_label("complete", "unknown") == "Unknown"
    assert classification_label("complete", "negative", title_case=True) == "Negative"
    assert classification_label("failed", "positive") == "Analysis failed"
    assert theme_display("pending", "", "") == "Not analyzed"
    assert theme_display("complete", "Size / Fit", "") == "Size / Fit"
    assert theme_display("complete", "", "") == "Unclear"


def test_corpus_stats_from_rows_only() -> None:
    frame = pd.DataFrame(
        [
            {"source": "google_play", "published_at": "2026-01-01", "rating": 4},
            {"source": "youtube", "published_at": "2026-02-01", "rating": None},
        ]
    )
    stats = corpus_stats(frame)
    assert stats["google_play"] == 1
    assert stats["youtube"] == 1
    assert stats["total"] == 2
    assert stats["average_rating"] == 4.0
    empty = corpus_stats(pd.DataFrame())
    assert empty["total"] == 0
    assert empty["average_rating"] is None


def test_parse_txt_upload_does_not_invent_rows() -> None:
    data = b"Size chart on Myntra is confusing for kurtas.\n\n"
    frame = parse_upload_bytes("notes.txt", data)
    assert list(frame["text"]) == ["Size chart on Myntra is confusing for kurtas."]
    records = frame_to_records(frame)
    assert len(records) == 1
    assert records[0]["source"] == "manual"
    assert records[0]["published_at"] is None
    assert "rating" not in records[0]["extra"] or records[0]["extra"].get("rating") is None


def test_empty_upload_is_empty() -> None:
    assert parse_upload_bytes("empty.csv", b"").empty
    assert frame_to_records(pd.DataFrame()) == []


def test_overall_status_partial() -> None:
    assert (
        overall_collection_status(
            [
                {"source": "google_play", "status": "ok"},
                {"source": "youtube", "status": "error"},
            ]
        )
        == "PARTIAL SUCCESS"
    )
    assert overall_collection_status([]) == "NO RUN"
