"""Google Play reviews collector.

There is no official public Play reviews API for third-party apps.
This collector checks robots.txt and does not scrape if disallowed or if the
page requires JavaScript/anti-bot measures. It reports Unavailable honestly
instead of inventing reviews.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from collectors.base import SourceAdapter
from config import USER_AGENT
from processing.cleaning import is_valid_conversation, normalize_record

logger = logging.getLogger(__name__)

APP_ID = os.getenv("PLAY_STORE_APP_ID", "com.myntra.android")
PLAY_URL = f"https://play.google.com/store/apps/details?id={APP_ID}&hl=en_IN"


class GooglePlayCollector(SourceAdapter):
    name = "google_play"
    requires_credentials = False

    def is_available(self) -> tuple[bool, str]:
        parsed = urlparse(PLAY_URL)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except Exception:
            return False, "Could not read Play Store robots.txt; skipping to avoid violating access rules"
        if not parser.can_fetch(USER_AGENT, PLAY_URL):
            return False, "Play Store robots.txt disallows this path; collector will not scrape"
        # Listing pages are JS-rendered; extracting reviews without unofficial APIs
        # would require bypassing client-side rendering / anti-bot systems.
        return False, (
            "Google Play has no official public reviews API. "
            "The listing page is JavaScript-rendered; scraping it would require "
            "evading access controls, which this app will not do."
        )

    def fetch(self) -> list[dict[str, Any]]:
        available, reason = self.is_available()
        self.status = "unavailable"
        self.last_error = reason
        logger.info("Google Play collector unavailable: %s", reason)
        return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return normalize_record(
            {
                "source": self.name,
                "source_item_id": str(raw.get("id") or ""),
                "source_url": raw.get("url") or PLAY_URL,
                "author_id": raw.get("author") or "",
                "published_at": raw.get("published_at"),
                "title": raw.get("title") or "",
                "text": raw.get("text") or "",
                "query_used": "Myntra",
                "engagement_count": int(raw.get("rating") or 0),
                "extra": {"rating": raw.get("rating"), "app_version": raw.get("app_version")},
            }
        )

    def validate(self, record: dict[str, Any]) -> bool:
        return is_valid_conversation(record) and bool(record.get("published_at"))
