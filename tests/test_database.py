"""Database insert / unique content_hash tests."""

from datetime import datetime, timezone
from pathlib import Path

from ai.analyzer import persist_analysis
from ai.schemas import ConversationAnalysis
from database.db import init_db, reset_engine, session_scope
from database.models import Analysis, Conversation
from processing.cleaning import content_hash
from pipeline.discovery import persist_conversations


def test_persist_conversations_dedupes(tmp_path: Path) -> None:
    reset_engine()
    db = tmp_path / "test.db"
    init_db(str(db))
    text = "Wishlisted a dress on Myntra and waiting to understand the size."
    digest = content_hash(text)
    published = datetime(2026, 8, 1, tzinfo=timezone.utc)
    records = [
        {
            "source": "reddit",
            "source_item_id": "aaa",
            "source_url": "https://www.reddit.com/r/india/comments/aaa",
            "author_id_hash": "aaa",
            "published_at": published,
            "title": "t1",
            "text": text,
            "original_text": text,
            "language": "en",
            "query_used": "q",
            "engagement_count": 1,
            "content_hash": digest,
        },
        {
            "source": "youtube",
            "source_item_id": "bbb",
            "source_url": "https://www.youtube.com/watch?v=bbb",
            "author_id_hash": "bbb",
            "published_at": published,
            "title": "t2",
            "text": text,
            "original_text": text,
            "language": "en",
            "query_used": "q",
            "engagement_count": 2,
            "content_hash": digest,
        },
    ]
    with session_scope() as session:
        new_rows, dupes, failed = persist_conversations(session, records)
        assert failed == 0
        assert len(new_rows) == 1
        assert dupes == 1
        assert session.query(Conversation).count() == 1
    reset_engine()


def test_persist_analysis_roundtrip(tmp_path: Path) -> None:
    reset_engine()
    init_db(str(tmp_path / "test2.db"))
    text = "I don't know if this will fit me so it stays on my Myntra wishlist."
    with session_scope() as session:
        conv = Conversation(
            source="reddit",
            source_url="https://www.reddit.com/r/india/comments/x",
            author_id_hash="ccc",
            title="",
            text=text,
            original_text=text,
            language="en",
            content_hash=content_hash(text),
            published_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
        session.add(conv)
        session.flush()
        parsed = ConversationAnalysis(
            relevant=True,
            wishlist_behavior="explicit_wishlist",
            purchase_intent="high",
            purchase_status="considering",
            blockers=["size_uncertainty"],
            evidence_quote="I don't know if this will fit me",
            confidence=0.81,
            needs_human_validation=False,
        )
        persist_analysis(session, conv, parsed, provider="Gemini", model="gemini-2.0-flash")
        session.commit()
        row = session.query(Analysis).one()
        assert row.relevant_to_wishlist is True
        assert row.purchase_blocker == "size_uncertainty"
        assert row.confidence == 0.81
        assert row.theme == "Unclear"
        assert row.wishlist_intent == "Unknown"
        assert row.uncertainty_level == "Unknown"
        assert row.analysis_provider == "Gemini"
        assert row.analysis_model == "gemini-2.0-flash"
        assert conv.analysis_status == "complete"
    reset_engine()


def test_same_url_different_item_ids_are_not_collapsed(tmp_path: Path) -> None:
    reset_engine()
    init_db(str(tmp_path / "test3.db"))
    published = datetime(2026, 8, 1, tzinfo=timezone.utc)
    records = [
        {
            "source": "app_store",
            "source_item_id": "review-1",
            "source_url": "https://apps.apple.com/in/app/id907394059",
            "author_id_hash": "a",
            "published_at": published,
            "title": "r1",
            "text": "First unique App Store review about Myntra wishlist size issues in August.",
            "original_text": "First unique App Store review about Myntra wishlist size issues in August.",
            "language": "en",
            "query_used": "Myntra",
            "engagement_count": 5,
            "content_hash": content_hash(
                "First unique App Store review about Myntra wishlist size issues in August."
            ),
        },
        {
            "source": "app_store",
            "source_item_id": "review-2",
            "source_url": "https://apps.apple.com/in/app/id907394059",
            "author_id_hash": "b",
            "published_at": published,
            "title": "r2",
            "text": "Second unique App Store review about waiting for a Myntra sale on wishlisted items.",
            "original_text": "Second unique App Store review about waiting for a Myntra sale on wishlisted items.",
            "language": "en",
            "query_used": "Myntra",
            "engagement_count": 4,
            "content_hash": content_hash(
                "Second unique App Store review about waiting for a Myntra sale on wishlisted items."
            ),
        },
    ]
    with session_scope() as session:
        new_rows, dupes, failed = persist_conversations(session, records)
        assert failed == 0
        assert dupes == 0
        assert len(new_rows) == 2
        assert session.query(Conversation).count() == 2
    reset_engine()
