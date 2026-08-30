"""Manual upload of real customer feedback (CSV / XLSX / TXT)."""

from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd

from pipeline.discovery import persist_conversations, prepare_records
from processing.cleaning import parse_timestamp
from processing.dates import utcnow

TEXT_COLUMNS = (
    "text",
    "review",
    "comment",
    "feedback",
    "body",
    "content",
    "review_text",
    "comment_text",
    "original_text",
)
TITLE_COLUMNS = ("title", "subject", "headline")
DATE_COLUMNS = ("published_at", "date", "timestamp", "created_at", "review_date")
RATING_COLUMNS = ("rating", "stars", "score")
URL_COLUMNS = ("url", "source_url", "link", "permalink")
AUTHOR_COLUMNS = ("author", "user", "username", "reviewer")


def _pick(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lower = {str(c).strip().lower(): c for c in frame.columns}
    for name in names:
        if name in lower:
            return lower[name]
    return None


def parse_upload_bytes(filename: str, data: bytes) -> pd.DataFrame:
    """Parse uploaded bytes into a table. Empty file → empty frame. Does not invent rows."""
    name = (filename or "").lower()
    if not data:
        return pd.DataFrame()
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(data))
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(data))
    if name.endswith(".txt"):
        text = data.decode("utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return pd.DataFrame({"text": lines})
    raise ValueError("Unsupported file type. Use CSV, XLSX, or TXT.")


def frame_to_records(frame: pd.DataFrame, *, source: str = "manual") -> list[dict[str, Any]]:
    """Map user columns onto the conversation schema. Missing fields stay empty/null."""
    if frame is None or frame.empty:
        return []
    text_col = _pick(frame, TEXT_COLUMNS)
    if text_col is None:
        # Single-column files still count if that column holds text.
        if len(frame.columns) == 1:
            text_col = frame.columns[0]
        else:
            return []
    title_col = _pick(frame, TITLE_COLUMNS)
    date_col = _pick(frame, DATE_COLUMNS)
    rating_col = _pick(frame, RATING_COLUMNS)
    url_col = _pick(frame, URL_COLUMNS)
    author_col = _pick(frame, AUTHOR_COLUMNS)
    records: list[dict[str, Any]] = []
    for idx, row in frame.iterrows():
        text = str(row.get(text_col) or "").strip()
        if not text:
            continue
        title = str(row.get(title_col) or "").strip() if title_col else ""
        published = parse_timestamp(row.get(date_col)) if date_col else None
        url = str(row.get(url_col) or "").strip() if url_col else ""
        author = str(row.get(author_col) or "").strip() if author_col else ""
        rating = None
        if rating_col is not None and pd.notna(row.get(rating_col)):
            try:
                rating = float(row.get(rating_col))
            except (TypeError, ValueError):
                rating = None
        extra = {
            "source_type": "Manual Upload",
            "upload_row": int(idx) if isinstance(idx, (int, float)) else None,
        }
        if rating is not None:
            extra["rating"] = rating
        if author:
            extra["author_display"] = author
        records.append(
            {
                "source": source,
                "source_item_id": f"manual-{idx}",
                "source_url": url,
                "author": author,
                "title": title,
                "text": text,
                "original_text": text,
                "published_at": published,
                "query_used": "manual_upload",
                "extra": extra,
                "extra_json": json.dumps(extra),
            }
        )
    return records


def persist_upload(session, frame: pd.DataFrame, *, source: str = "manual") -> dict[str, int]:
    raw = frame_to_records(frame, source=source)
    prepared = prepare_records(raw)
    new_rows, duplicates, failed = persist_conversations(session, prepared)
    return {
        "parsed": len(raw),
        "accepted": len(prepared),
        "new": len(new_rows),
        "duplicates": int(duplicates),
        "failed": int(failed),
        "collected_at": utcnow().isoformat(),
    }
