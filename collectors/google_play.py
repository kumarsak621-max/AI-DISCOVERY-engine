"""Google Play reviews collector for the public Myntra Android listing.

Uses the google-play-scraper library, which reads Google Play's public review
feed (not the listing HTML). Individual review text is stored as returned.
No reviews are invented when the feed is empty.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any

from collectors.base import SourceAdapter
from processing.cleaning import normalize_record, parse_timestamp

logger = logging.getLogger(__name__)

APP_ID = os.getenv("PLAY_STORE_APP_ID", "com.myntra.android")
PLAY_URL = f"https://play.google.com/store/apps/details?id={APP_ID}&hl=en_IN&gl=IN"
PAGE_SIZE = 200


def _as_utc(value: Any) -> datetime | None:
    parsed = value if isinstance(value, datetime) else parse_timestamp(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class GooglePlayCollector(SourceAdapter):
    name = "google_play"
    requires_credentials = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.app_id = os.getenv("PLAY_STORE_APP_ID", APP_ID)
        self.requested_records = 0
        self.requested_start: datetime | None = None
        self.requested_end: datetime | None = None
        self.earliest_published: datetime | None = None
        self.latest_published: datetime | None = None
        self.limitation_note = ""

    def is_available(self) -> tuple[bool, str]:
        try:
            import google_play_scraper  # noqa: F401
        except ImportError:
            return False, "google-play-scraper is not installed."
        return True, ""

    def fetch(self) -> list[dict[str, Any]]:
        try:
            from google_play_scraper import Sort, reviews as fetch_reviews
        except ImportError:
            self.status = "unavailable"
            self.last_error = "google-play-scraper is not installed."
            return []

        self.requested_start = self.since
        self.requested_end = self.until
        self.requested_records = int(self.max_records or 0)
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        token = None
        reached_source_end = False
        stopped_at_requested_start = False

        while len(collected) < self.max_records:
            count = min(PAGE_SIZE, self.max_records - len(collected))
            try:
                batch, token = fetch_reviews(
                    self.app_id,
                    lang="en",
                    country="in",
                    sort=Sort.NEWEST,
                    count=count,
                    continuation_token=token,
                )
            except Exception as exc:  # noqa: BLE001
                if collected:
                    self.limitation_note = (
                        f"Paging stopped after {len(collected)} reviews: {exc}"
                    )[:400]
                    logger.warning("Google Play paging stopped: %s", exc)
                    break
                self.status = "error"
                self.last_error = f"Google Play review fetch failed: {exc}"[:400]
                logger.warning("Google Play review fetch failed: %s", exc)
                return []

            if not batch:
                reached_source_end = True
                break

            for item in batch:
                if not isinstance(item, dict):
                    continue
                review_id = str(item.get("reviewId") or "").strip()
                if review_id and review_id in seen:
                    continue
                if review_id:
                    seen.add(review_id)
                published = _as_utc(item.get("at"))
                if self.until and published and published > _as_utc(self.until):
                    continue
                if self.since and published and published < _as_utc(self.since):
                    stopped_at_requested_start = True
                    break
                text = str(item.get("content") or "").strip()
                if not text:
                    continue
                collected.append(item)
                if self.earliest_published is None or (published and published < self.earliest_published):
                    self.earliest_published = published
                if self.latest_published is None or (published and published > self.latest_published):
                    self.latest_published = published
                if len(collected) >= self.max_records:
                    break

            if stopped_at_requested_start or token is None:
                if token is None:
                    reached_source_end = True
                break

        if not collected:
            self.limitation_note = "No Google Play reviews collected."
            logger.info("Google Play collector returned 0 reviews for %s", self.app_id)
            return []

        if self.since and self.earliest_published:
            requested = _as_utc(self.since)
            if requested and self.earliest_published > requested:
                extra = (
                    f" Stopped at max_records={self.max_records}."
                    if len(collected) >= self.max_records
                    else " The public review feed did not return older items."
                )
                self.limitation_note = (
                    "Google Play scraper/source availability limitation. "
                    f"Requested start {requested.date()} but earliest returned review is "
                    f"{self.earliest_published.date()}.{extra} "
                    "Missing history was not fabricated."
                )
        logger.info("Google Play collector found %s individual reviews", len(collected))
        return collected

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        review_id = str(raw.get("reviewId") or raw.get("id") or "").strip()
        text = str(raw.get("content") or raw.get("text") or "")
        published = raw.get("at") or raw.get("published_at")
        rating = raw.get("score") if raw.get("score") is not None else raw.get("rating")
        try:
            rating_int = int(float(rating)) if rating is not None and str(rating) != "" else 0
        except (TypeError, ValueError):
            rating_int = 0
        author = str(raw.get("userName") or raw.get("author") or "")
        url = PLAY_URL
        if review_id:
            url = f"{PLAY_URL}&reviewId={review_id}"
        record = normalize_record(
            {
                "source": self.name,
                "source_item_id": review_id[:256],
                "source_url": url,
                "author_id": author,
                "published_at": published,
                "title": "",
                "text": text,
                "query_used": "Myntra",
                "language": "unknown",
                "engagement_count": int(raw.get("thumbsUpCount") or rating_int or 0),
                "extra": {
                    "source_type": "Google Play Store",
                    "rating": rating_int or None,
                    "app_id": self.app_id,
                    "author_display": author,
                    "review_id": review_id,
                    "app_version": raw.get("reviewCreatedVersion") or raw.get("appVersion") or "",
                },
            }
        )
        if review_id:
            record["content_hash"] = hashlib.sha256(f"google_play|{review_id}".encode("utf-8")).hexdigest()
        return record

    def validate(self, record: dict[str, Any]) -> bool:
        text = str(record.get("text") or "").strip()
        return bool(record.get("source") == self.name and record.get("source_item_id") and text)
