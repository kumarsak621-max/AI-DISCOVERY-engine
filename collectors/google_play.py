"""Google Play reviews collector for the public Myntra listing.

There is no official third-party Play reviews API.
robots.txt allows the app listing page but disallows /store/getreviews, /store/xhr, and /_.
This collector will not call those blocked endpoints. If the allowed listing HTML
contains no individual reviews, the source is reported Unavailable — never faked.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from collectors.base import SourceAdapter
from config import USER_AGENT
from processing.cleaning import is_valid_conversation, normalize_record
from processing.dates import is_after, parse_timestamp

logger = logging.getLogger(__name__)

APP_ID = os.getenv("PLAY_STORE_APP_ID", "com.myntra.android")
PLAY_URL = f"https://play.google.com/store/apps/details?id={APP_ID}&hl=en_IN&gl=IN"
BLOCKED_PATHS = ("/store/getreviews", "/store/xhr", "/_/")


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
            return False, "Play Store robots.txt disallows the listing path; collector will not scrape"
        for path in BLOCKED_PATHS:
            probe = f"{parsed.scheme}://{parsed.netloc}{path}"
            if not parser.can_fetch(USER_AGENT, probe):
                logger.info("Play Store robots.txt disallows %s", path)
        return True, ""

    def fetch(self) -> list[dict[str, Any]]:
        available, reason = self.is_available()
        if not available:
            self.status = "unavailable"
            self.last_error = reason
            logger.info("Google Play collector unavailable: %s", reason)
            return []
        try:
            response = requests.get(PLAY_URL, timeout=25, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
        except requests.RequestException as exc:
            self.status = "error"
            self.last_error = f"Play listing fetch failed: {exc}"[:400]
            logger.warning("Google Play listing fetch failed: %s", exc)
            return []

        reviews = self._reviews_from_jsonld(response.text)
        if reviews:
            logger.info("Google Play collector found %s JSON-LD reviews", len(reviews))
            since = self.since
            until = self.until
            kept = []
            for item in reviews:
                published = parse_timestamp(item.get("published_at"))
                if until and published and published > until:
                    continue
                if since and published and not is_after(published, since):
                    continue
                kept.append(item)
            return kept[: self.max_records]

        self.status = "unavailable"
        self.last_error = (
            "Google Play listing HTML has no individual reviews (JSON-LD has aggregateRating only). "
            "robots.txt disallows /store/getreviews, /store/xhr, and /_ so those endpoints are not used. "
            "No fake reviews were generated."
        )
        logger.info("Google Play collector unavailable: %s", self.last_error)
        return []

    def _iter_jsonld(self, data: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(data, list):
            for item in data:
                found.extend(self._iter_jsonld(item))
        elif isinstance(data, dict):
            found.append(data)
            if "@graph" in data:
                found.extend(self._iter_jsonld(data.get("@graph")))
        return found

    def _reviews_from_jsonld(self, html: str) -> list[dict[str, Any]]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []
        soup = BeautifulSoup(html, "lxml")
        out: list[dict[str, Any]] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
            except (TypeError, json.JSONDecodeError):
                continue
            for node in self._iter_jsonld(data):
                items = node.get("review")
                if items is None:
                    continue
                if isinstance(items, dict):
                    items = [items]
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    body = item.get("reviewBody") or item.get("description") or ""
                    if not str(body).strip():
                        continue
                    author = item.get("author")
                    if isinstance(author, dict):
                        author_name = author.get("name") or ""
                    else:
                        author_name = str(author or "")
                    rating = None
                    rating_obj = item.get("reviewRating") or {}
                    if isinstance(rating_obj, dict):
                        rating = rating_obj.get("ratingValue")
                    out.append(
                        {
                            "id": str(item.get("@id") or item.get("url") or "")[:256],
                            "text": str(body),
                            "title": str(item.get("name") or ""),
                            "author": author_name,
                            "published_at": item.get("datePublished") or item.get("dateCreated"),
                            "rating": rating,
                            "url": item.get("url") or PLAY_URL,
                            "language": item.get("inLanguage") or "",
                        }
                    )
        return out

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        rating = raw.get("rating")
        try:
            rating_int = int(float(rating)) if rating is not None and str(rating) != "" else 0
        except (TypeError, ValueError):
            rating_int = 0
        return normalize_record(
            {
                "source": self.name,
                "source_item_id": str(raw.get("id") or "")[:256],
                "source_url": raw.get("url") or PLAY_URL,
                "author_id": raw.get("author") or "",
                "published_at": raw.get("published_at"),
                "title": raw.get("title") or "",
                "text": raw.get("text") or "",
                "query_used": "Myntra",
                "language": raw.get("language") or "unknown",
                "engagement_count": rating_int,
                "extra": {
                    "source_type": "Google Play Store",
                    "rating": rating_int or None,
                    "app_id": APP_ID,
                    "author_display": raw.get("author") or "",
                },
            }
        )

    def validate(self, record: dict[str, Any]) -> bool:
        return is_valid_conversation(record, min_chars=20) and bool(record.get("published_at"))
