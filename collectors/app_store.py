"""Apple App Store reviews via the public iTunes customer-review RSS (no login)."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from collectors.base import SourceAdapter
from config import USER_AGENT
from processing.cleaning import is_valid_conversation, normalize_record
from processing.dates import is_after, parse_timestamp

logger = logging.getLogger(__name__)

APP_ID = os.getenv("APP_STORE_APP_ID", "907394059")
COUNTRY = os.getenv("APP_STORE_COUNTRY", "in")
MAX_PAGES = 10
APP_URL = f"https://apps.apple.com/{COUNTRY}/app/id{APP_ID}"


def _rss_url(page: int) -> str:
    return (
        f"https://itunes.apple.com/{COUNTRY}/rss/customerreviews/"
        f"page={page}/id={APP_ID}/sortBy=mostRecent/json"
    )


def _entry_url(raw: dict[str, Any]) -> str:
    link = raw.get("link")
    if isinstance(link, dict):
        href = (link.get("attributes") or {}).get("href") or link.get("label") or ""
        if href:
            return str(href)
    if isinstance(link, list):
        for item in link:
            if not isinstance(item, dict):
                continue
            href = (item.get("attributes") or {}).get("href") or item.get("label") or ""
            if href:
                return str(href)
    entry_id = raw.get("id", {})
    label = entry_id.get("label") if isinstance(entry_id, dict) else str(entry_id or "")
    if str(label).startswith("http"):
        return str(label)
    return APP_URL


class AppStoreCollector(SourceAdapter):
    name = "app_store"

    def fetch(self) -> list[dict[str, Any]]:
        since = self.since or self.get_last_collection_time()
        reviews: list[dict[str, Any]] = []
        older_page = False
        empty_pages = 0
        try:
            for page in range(1, MAX_PAGES + 1):
                response = requests.get(
                    _rss_url(page),
                    timeout=20,
                    headers={"User-Agent": USER_AGENT},
                )
                response.raise_for_status()
                payload = response.json()
                entries = payload.get("feed", {}).get("entry", [])
                if not isinstance(entries, list):
                    entries = [entries] if entries else []
                page_reviews = 0
                for entry in entries:
                    if not isinstance(entry, dict) or "content" not in entry:
                        continue
                    updated = entry.get("updated", {})
                    published = parse_timestamp(updated.get("label") if isinstance(updated, dict) else "")
                    if self.until and published and published > self.until:
                        continue
                    if since and published and not is_after(published, since):
                        older_page = True
                        continue
                    reviews.append(entry)
                    page_reviews += 1
                    if len(reviews) >= self.max_records:
                        logger.info("App Store collector fetched %s reviews", len(reviews))
                        return reviews
                if page_reviews == 0:
                    empty_pages += 1
                    if older_page or empty_pages >= 2:
                        if reviews or empty_pages >= 3:
                            break
                    continue
                empty_pages = 0
            logger.info("App Store collector fetched %s reviews", len(reviews))
            return reviews
        except requests.RequestException as exc:
            self.status = "error"
            self.last_error = str(exc)[:400]
            logger.warning("App Store RSS fetch failed: %s", exc)
            return reviews
        except ValueError as exc:
            self.status = "error"
            self.last_error = f"JSON parse failed: {exc}"
            return reviews

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        content = raw.get("content", {})
        text = content.get("label") if isinstance(content, dict) else str(content or "")
        title_obj = raw.get("title", {})
        title = title_obj.get("label") if isinstance(title_obj, dict) else str(title_obj or "")
        author_obj = raw.get("author", {}).get("name", {}) if isinstance(raw.get("author"), dict) else {}
        author = author_obj.get("label") if isinstance(author_obj, dict) else ""
        updated = raw.get("updated", {})
        timestamp = updated.get("label") if isinstance(updated, dict) else ""
        rating_obj = raw.get("im:rating", {})
        rating = rating_obj.get("label") if isinstance(rating_obj, dict) else ""
        version_obj = raw.get("im:version", {})
        version = version_obj.get("label") if isinstance(version_obj, dict) else ""
        entry_id = raw.get("id", {})
        item_id = entry_id.get("label") if isinstance(entry_id, dict) else str(entry_id or "")
        lang = ""
        if isinstance(content, dict):
            lang = str(content.get("attributes", {}).get("xml:lang") or "")
        return normalize_record(
            {
                "source": self.name,
                "source_item_id": item_id[:256],
                "source_url": _entry_url(raw),
                "author_id": author,
                "published_at": timestamp,
                "title": title,
                "text": f"{title}\n\n{text}".strip(),
                "query_used": "Myntra",
                "language": lang or "unknown",
                "engagement_count": int(rating) if str(rating).isdigit() else 0,
                "extra": {
                    "source_type": "Apple App Store",
                    "rating": int(rating) if str(rating).isdigit() else None,
                    "app_version": version,
                    "app_id": APP_ID,
                    "country": COUNTRY,
                    "author_display": author,
                },
            }
        )

    def validate(self, record: dict[str, Any]) -> bool:
        return is_valid_conversation(record, min_chars=20) and bool(record.get("published_at"))
