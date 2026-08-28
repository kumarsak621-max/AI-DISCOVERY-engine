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
RSS_URL = (
    f"https://itunes.apple.com/in/rss/customerreviews/id={APP_ID}/sortBy=mostRecent/json"
)


class AppStoreCollector(SourceAdapter):
    name = "app_store"

    def fetch(self) -> list[dict[str, Any]]:
        since = self.since or self.get_last_collection_time()
        try:
            response = requests.get(RSS_URL, timeout=20, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            payload = response.json()
            entries = payload.get("feed", {}).get("entry", [])
            reviews = []
            for entry in entries:
                if "content" not in entry:
                    continue
                updated = entry.get("updated", {})
                published = parse_timestamp(updated.get("label") if isinstance(updated, dict) else "")
                if since and not is_after(published, since):
                    continue
                if self.until and published and published > self.until:
                    continue
                reviews.append(entry)
            logger.info("App Store collector fetched %s reviews", len(reviews))
            return reviews[: self.max_records]
        except requests.RequestException as exc:
            self.status = "error"
            self.last_error = str(exc)[:400]
            logger.warning("App Store RSS fetch failed: %s", exc)
            return []
        except ValueError as exc:
            self.status = "error"
            self.last_error = f"JSON parse failed: {exc}"
            return []

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
        return normalize_record(
            {
                "source": self.name,
                "source_item_id": item_id[:256],
                "source_url": f"https://apps.apple.com/in/app/id{APP_ID}",
                "author_id": author,
                "published_at": timestamp,
                "title": title,
                "text": f"{title}\n\n{text}".strip(),
                "query_used": "Myntra",
                "engagement_count": int(rating) if str(rating).isdigit() else 0,
                "extra": {"rating": rating, "app_version": version},
            }
        )

    def validate(self, record: dict[str, Any]) -> bool:
        return is_valid_conversation(record, min_chars=20) and bool(record.get("published_at"))
