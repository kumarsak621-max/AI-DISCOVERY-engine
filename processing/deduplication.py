"""Deduplication by source_item_id, content hash, and URL."""

from __future__ import annotations

from typing import Any

from processing.cleaning import content_hash, normalize_for_hash


def record_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    source = str(record.get("source") or "")
    item_id = str(record.get("source_item_id") or "")
    digest = record.get("content_hash") or content_hash(
        f"{record.get('title', '')} {record.get('text', '')}"
    )
    url = str(record.get("source_url") or "")
    record["content_hash"] = digest
    return source, item_id, digest, url  # type: ignore[return-value]


def deduplicate_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep first occurrence of source+item_id, content_hash, or URL+hash."""
    seen_hash: set[str] = set()
    seen_item: set[tuple[str, str]] = set()
    seen_url: set[str] = set()
    unique: list[dict[str, Any]] = []
    duplicates = 0
    for record in records:
        digest = record.get("content_hash") or content_hash(
            f"{record.get('title', '')} {record.get('text', '')}"
        )
        record["content_hash"] = digest
        source = str(record.get("source") or "")
        item_id = str(record.get("source_item_id") or "")
        url = str(record.get("source_url") or "")
        if digest in seen_hash:
            duplicates += 1
            continue
        if item_id and (source, item_id) in seen_item:
            duplicates += 1
            continue
        if url and url in seen_url and digest in seen_hash:
            duplicates += 1
            continue
        seen_hash.add(digest)
        if item_id:
            seen_item.add((source, item_id))
        if url:
            seen_url.add(url)
        unique.append(record)
    return unique, duplicates


def flag_syndicated(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_text: dict[str, set[str]] = {}
    for record in records:
        key = normalize_for_hash(str(record.get("text") or ""))
        source = str(record.get("source") or "")
        by_text.setdefault(key, set()).add(source)
    for record in records:
        key = normalize_for_hash(str(record.get("text") or ""))
        record["is_syndicated"] = len(by_text.get(key, set())) > 1
    return records
