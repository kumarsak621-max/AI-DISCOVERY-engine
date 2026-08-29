"""Text cleaning and record normalization."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = _CONTROL_RE.sub("", str(text))
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def normalize_for_hash(text: str) -> str:
    """Lowercase, strip URLs and punctuation-heavy noise for stable content hashing."""
    value = clean_text(text).lower()
    value = _URL_RE.sub("", value)
    value = re.sub(r"[^\w\s\u0900-\u097F]", " ", value, flags=re.UNICODE)
    value = _WHITESPACE_RE.sub(" ", value).strip()
    return value


def content_hash(text: str) -> str:
    normalized = normalize_for_hash(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_author(author_id: str | None) -> str:
    if not author_id:
        return ""
    return hashlib.sha256(str(author_id).strip().lower().encode("utf-8")).hexdigest()[:16]


def parse_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        from dateutil import parser as date_parser

        parsed = date_parser.parse(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, OverflowError, TypeError):
        return None


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a collector record into the conversations table shape."""
    import json

    text = clean_text(raw.get("text") or raw.get("body") or raw.get("content") or "")
    title = clean_text(raw.get("title") or "")
    original = clean_text(raw.get("original_text") or text)
    published = parse_timestamp(
        raw.get("published_at") or raw.get("timestamp") or raw.get("created_utc") or raw.get("date")
    )
    extra = raw.get("extra") or raw.get("extra_json") or {}
    if not isinstance(extra, str):
        extra = json.dumps(extra)
    source = str(raw.get("source") or "unknown")[:64]
    url = str(raw.get("source_url") or raw.get("url") or "")[:1024]
    sid = str(raw.get("source_item_id") or raw.get("id") or "")[:256]
    if sid:
        digest = content_hash(f"{title} {text}")
    else:
        published_key = published.isoformat() if published else ""
        payload = f"{source}|{url}|{published_key}|{normalize_for_hash(f'{title} {text}')}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {
        "source": source,
        "source_item_id": sid,
        "source_url": url,
        "author_id_hash": hash_author(str(raw.get("author_id") or raw.get("author") or "")),
        "published_at": published,
        "title": title[:512],
        "text": text,
        "original_text": original,
        "language": str(raw.get("language") or "unknown")[:32],
        "query_used": str(raw.get("query_used") or raw.get("query") or "")[:256],
        "engagement_count": int(raw.get("engagement_count") or raw.get("score") or 0 or 0),
        "content_hash": digest,
        "extra_json": extra,
    }


def is_valid_conversation(record: dict[str, Any], min_chars: int = 40) -> bool:
    text = clean_text(record.get("text") or "")
    if len(text) < min_chars:
        return False
    if not record.get("source"):
        return False
    return True
