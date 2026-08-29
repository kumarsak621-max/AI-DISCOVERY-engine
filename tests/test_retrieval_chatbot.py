"""Review explorer merge, 30-day filter, and grounded retrieval."""

from datetime import datetime, timedelta, timezone

import pandas as pd

from ai.chatbot import answer_question, records_to_evidence
from analytics.records import build_review_records, filter_review_records, source_summary
from analytics.retrieval import retrieve_records


def _rows() -> pd.DataFrame:
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    return pd.DataFrame(
        [
            {
                "id": 1,
                "source": "reddit",
                "source_url": "https://reddit.com/r/test/1",
                "author_id_hash": "aaa",
                "published_at": now - timedelta(days=2),
                "collected_at": now,
                "title": "size chart",
                "text": "I wishlisted this dress on Myntra but I am not sure about the fit",
                "original_text": "I wishlisted this dress on Myntra but I am not sure about the fit",
                "query_used": "Myntra wishlist",
                "analysis_status": "complete",
            },
            {
                "id": 2,
                "source": "app_store",
                "source_url": "https://apps.apple.com/app/id907394059",
                "author_id_hash": "bbb",
                "published_at": now - timedelta(days=40),
                "collected_at": now,
                "title": "old review",
                "text": "Price dropped last year on a saved item",
                "original_text": "Price dropped last year on a saved item",
                "query_used": "Myntra",
                "analysis_status": "complete",
            },
        ]
    )


def _analysis() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "conversation_id": 1,
                "sentiment": "negative",
                "purchase_intent": "high",
                "primary_problem": "fit uncertainty",
                "uncertainty_type": "fit",
                "uncertainty_text": "not sure about the fit",
                "purchase_blocker": "fit_uncertainty",
                "fashion_category": "dresses",
                "evidence_quote": "not sure about the fit",
                "wishlist_behavior": "explicit_wishlist",
                "relevance_reason": "wishlist + fit hesitation",
            }
        ]
    )


def test_last_30_days_excludes_older_publication(monkeypatch) -> None:
    frozen = datetime(2026, 8, 28, tzinfo=timezone.utc)
    monkeypatch.setattr("analytics.records.utcnow", lambda: frozen)
    merged = build_review_records(_rows(), _analysis())
    view = filter_review_records(merged, preset="last_30_days")
    assert len(view) == 1
    assert int(view.iloc[0]["id"]) == 1


def test_retrieve_prefers_fit_record_for_fit_question() -> None:
    merged = build_review_records(_rows(), _analysis())
    hit = retrieve_records(merged, "What fit problems are users talking about?", limit=8)
    assert not hit.empty
    assert "fit" in str(hit.iloc[0]["original_text"]).lower()


def test_evidence_quotes_come_from_stored_text() -> None:
    merged = build_review_records(_rows(), _analysis())
    hit = retrieve_records(merged, "fit", limit=8)
    evidence = records_to_evidence(hit)
    for item in evidence:
        assert item["quote"].lower() in item["text"].lower() or item["quote"] in item["text"]


def test_chatbot_without_key_returns_stored_evidence() -> None:
    merged = build_review_records(_rows(), _analysis())
    result = answer_question(
        "What fit problems are users talking about?",
        merged,
        api_key="",
        model="openai/gpt-4o-mini",
        period_label="Analysis period: 2026-07-29 – 2026-08-28",
    )
    assert result["used_openrouter"] is False
    assert result["n_records"] >= 1
    assert result["evidence"]
    assert "fit" in result["evidence"][0]["text"].lower()
    assert "OpenRouter" in result["direct_answer"] or "unavailable" in result["direct_answer"].lower() or "not set" in result["direct_answer"].lower()


def test_source_summary_uses_real_counts_including_zeros() -> None:
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    frame = pd.DataFrame(
        [
            {
                "source": "app_store",
                "published_at": now,
            },
            {
                "source": "app_store",
                "published_at": now,
            },
        ]
    )
    summary = source_summary(frame)
    by_source = {row["Source"]: row["Records"] for _, row in summary.iterrows()}
    assert by_source["Apple App Store"] == 2
    assert by_source["Google Play Store"] == 0
    assert by_source["Web"] == 0


def test_chatbot_empty_corpus_does_not_invent() -> None:
    result = answer_question(
        "Why don't users purchase?",
        pd.DataFrame(),
        api_key="",
        model="openai/gpt-4o-mini",
        period_label="Analysis period: 2026-07-29 – 2026-08-28",
    )
    assert result["n_records"] == 0
    assert result["evidence"] == []
    assert "No real reviews" in result["direct_answer"]
    assert result["used_openrouter"] is False
