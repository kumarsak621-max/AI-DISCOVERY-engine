"""JSON extraction and schema validation tests."""

import pytest
from pydantic import ValidationError

from ai.openrouter import extract_json_object
from ai.schemas import ConversationAnalysis


def test_extract_plain_json() -> None:
    payload = extract_json_object('{"relevant": true, "confidence": 0.8}')
    assert payload["relevant"] is True


def test_extract_fenced_json() -> None:
    text = """Here you go
```json
{"relevant": false, "relevance_reason": "off topic"}
```
thanks"""
    payload = extract_json_object(text)
    assert payload["relevant"] is False


def test_extract_embedded_json() -> None:
    payload = extract_json_object('prefix {"relevant": true, "wishlist_behavior": "price_watch"} suffix')
    assert payload["wishlist_behavior"] == "price_watch"


def test_extract_empty_raises() -> None:
    with pytest.raises(ValueError):
        extract_json_object("   ")


def test_schema_coerces_confidence_percent() -> None:
    parsed = ConversationAnalysis.model_validate(
        {"relevant": True, "confidence": 82, "evidence_quote": ""}
    )
    assert parsed.confidence == 0.82
    assert parsed.evidence_quote == "no direct evidence"


def test_schema_rejects_invalid_behavior() -> None:
    with pytest.raises(ValidationError):
        ConversationAnalysis.model_validate({"relevant": True, "wishlist_behavior": "not_a_real_label"})


def test_blockers_from_comma_string() -> None:
    parsed = ConversationAnalysis.model_validate(
        {"relevant": True, "blockers": "size_uncertainty, waiting_for_price_drop"}
    )
    assert parsed.blockers == ["size_uncertainty", "waiting_for_price_drop"]
