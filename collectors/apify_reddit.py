"""Apify-based Reddit public-data collector.

Apify is a collection platform. This is not the official Reddit API.
Existing collectors (Play Store, YouTube, native Reddit JSON/OAuth) are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any

import requests

from collectors.base import SourceAdapter
from config import APIFY_REDDIT_QUERIES, DEFAULT_APIFY_REDDIT_SUBREDDITS, REQUEST_TIMEOUT_SECONDS
from processing.cleaning import is_valid_conversation, normalize_record, parse_timestamp
from processing.dates import is_after

logger = logging.getLogger(__name__)

APIFY_API = "https://api.apify.com/v2"
_TOKEN_RE = re.compile(r"apify_api_[A-Za-z0-9]+", re.IGNORECASE)


def _redact(text: str) -> str:
    return _TOKEN_RE.sub("[REDACTED]", str(text or ""))


def actor_path(actor_id: str) -> str:
    value = (actor_id or "").strip().strip("/")
    return value.replace("/", "~")


def configured_subreddits() -> list[str]:
    if "APIFY_REDDIT_SUBREDDITS" not in os.environ:
        return list(DEFAULT_APIFY_REDDIT_SUBREDDITS)
    raw = os.getenv("APIFY_REDDIT_SUBREDDITS", "").strip()
    if raw.lower() in {"", "none", "off", "-"}:
        return []
    return [part.strip().lstrip("r/") for part in raw.split(",") if part.strip()]


class ApifyRedditCollector(SourceAdapter):
    """Collects publicly visible Reddit posts/comments via a configurable Apify Actor."""

    name = "apify_reddit"
    requires_credentials = True
    conversation_source = "reddit"

    def __init__(self, **kwargs: Any) -> None:
        api_token = kwargs.pop("api_token", None)
        actor_id = kwargs.pop("actor_id", None)
        subreddits = kwargs.pop("subreddits", None)
        super().__init__(**kwargs)
        self.api_token = str(api_token if api_token is not None else os.getenv("APIFY_API_TOKEN", "")).strip()
        self.actor_id = str(actor_id if actor_id is not None else os.getenv("APIFY_REDDIT_ACTOR_ID", "")).strip()
        self.subreddits = list(subreddits) if subreddits is not None else configured_subreddits()
        self.queries = list(self.queries) or list(APIFY_REDDIT_QUERIES)
        self.poll_seconds = float(os.getenv("APIFY_POLL_SECONDS", "5"))
        self.max_wait_seconds = int(os.getenv("APIFY_RUN_TIMEOUT_SECONDS", "180"))
        self.max_retries = 3
        self.requested_records = 0
        self.requested_start: datetime | None = None
        self.requested_end: datetime | None = None
        self.earliest_published: datetime | None = None
        self.latest_published: datetime | None = None
        self.limitation_note = (
            "Apify returns whatever the selected Actor can see as a logged-out visitor. "
            "A 30-month window is applied locally on publication date. "
            "This does not mean Reddit's entire 30-month history was collected."
        )

    def is_available(self) -> tuple[bool, str]:
        if not self.api_token:
            return False, "Apify API token is not configured."
        if not self.actor_id:
            return False, "Apify Reddit Actor is not configured."
        return True, ""

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

    def _start_run(self, actor_input: dict[str, Any]) -> dict[str, Any]:
        path = actor_path(self.actor_id)
        url = f"{APIFY_API}/acts/{path}/runs"
        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(),
                    json=actor_input,
                    params={"waitForFinish": min(60, self.max_wait_seconds)},
                    timeout=max(REQUEST_TIMEOUT_SECONDS, 90),
                )
                if response.status_code in {401, 403}:
                    raise RuntimeError("Apify rejected the API token.")
                if response.status_code == 429:
                    time.sleep(2 * attempt)
                    last_error = "Apify rate limited"
                    continue
                if response.status_code >= 500:
                    time.sleep(2 * attempt)
                    last_error = f"Apify server error {response.status_code}"
                    continue
                if response.status_code >= 400:
                    raise RuntimeError(_redact(f"Apify Actor start failed ({response.status_code})"))
                payload = response.json()
                return payload.get("data") or payload
            except requests.Timeout as exc:
                last_error = f"Apify request timed out: {_redact(str(exc))}"
                time.sleep(2 * attempt)
            except requests.RequestException as exc:
                last_error = f"Apify network error: {_redact(str(exc))}"
                time.sleep(2 * attempt)
        raise RuntimeError(last_error or "Apify Actor start failed")

    def _wait_for_run(self, run_id: str, status: str) -> dict[str, Any]:
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            return {"id": run_id, "status": status}
        deadline = time.time() + self.max_wait_seconds
        last: dict[str, Any] = {"id": run_id, "status": status}
        while time.time() < deadline:
            response = requests.get(
                f"{APIFY_API}/actor-runs/{run_id}",
                headers=self._headers(),
                timeout=30,
            )
            if response.status_code == 429:
                time.sleep(self.poll_seconds * 2)
                continue
            response.raise_for_status()
            last = response.json().get("data") or {}
            status = str(last.get("status") or "")
            if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                return last
            time.sleep(self.poll_seconds)
        raise RuntimeError("Apify Actor run timed out while waiting for results.")

    def _dataset_items(self, dataset_id: str) -> list[dict[str, Any]]:
        if not dataset_id:
            return []
        items: list[dict[str, Any]] = []
        offset = 0
        limit = 250
        while len(items) < self.max_records * 3:
            response = requests.get(
                f"{APIFY_API}/datasets/{dataset_id}/items",
                headers=self._headers(),
                params={"offset": offset, "limit": limit, "clean": "true"},
                timeout=60,
            )
            if response.status_code >= 400:
                logger.warning("Apify dataset fetch failed: %s", response.status_code)
                break
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            items.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < limit:
                break
            offset += limit
        return items

    def _run_actor(self, actor_input: dict[str, Any]) -> list[dict[str, Any]]:
        started = self._start_run(actor_input)
        run_id = str(started.get("id") or "")
        status = str(started.get("status") or "")
        finished = self._wait_for_run(run_id, status) if run_id else started
        status = str(finished.get("status") or status)
        if status != "SUCCEEDED":
            message = finished.get("statusMessage") or status or "Apify Actor failed"
            raise RuntimeError(_redact(str(message)))
        dataset_id = (finished.get("defaultDatasetId") or started.get("defaultDatasetId") or "")
        return self._dataset_items(str(dataset_id))

    def _search_input(self, searches: list[str]) -> dict[str, Any]:
        return {
            "searches": searches,
            "searchPosts": True,
            "searchComments": True,
            "searchCommunities": False,
            "searchUsers": False,
            "skipComments": False,
            "sort": "new",
            "time": "all",
            "maxItems": min(self.max_records, 200),
            "maxPostCount": min(self.max_records, 100),
            "maxComments": min(max(self.max_records, 20), 200),
        }

    def _subreddit_input(self, names: list[str]) -> dict[str, Any]:
        urls = [{"url": f"https://www.reddit.com/r/{name}/"} for name in names if name]
        return {
            "startUrls": urls,
            "skipComments": False,
            "maxItems": min(self.max_records, 200),
            "maxPostCount": min(self.max_records, 50),
            "maxComments": min(max(self.max_records // 2, 10), 100),
        }

    def fetch(self) -> list[dict[str, Any]]:
        available, reason = self.is_available()
        if not available:
            self.status = "unavailable"
            self.last_error = reason
            return []
        self.requested_start = self.since
        self.requested_end = self.until
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        searches = [q.strip() for q in self.queries if q and q.strip()]
        self.requested_records = min(self.max_records, 200)

        try:
            if searches:
                chunk_size = 8
                for i in range(0, min(len(searches), 24), chunk_size):
                    if len(collected) >= self.max_records:
                        break
                    chunk = searches[i : i + chunk_size]
                    for item in self._run_actor(self._search_input(chunk)):
                        key = str(item.get("parsedId") or item.get("id") or item.get("url") or "")
                        if key and key in seen:
                            continue
                        if key:
                            seen.add(key)
                        collected.append(item)
            if self.subreddits and len(collected) < self.max_records:
                try:
                    for item in self._run_actor(self._subreddit_input(self.subreddits)):
                        key = str(item.get("parsedId") or item.get("id") or item.get("url") or "")
                        if key and key in seen:
                            continue
                        if key:
                            seen.add(key)
                        collected.append(item)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Apify subreddit run failed: %s", _redact(str(exc)))
                    extra = _redact(str(exc))[:200]
                    self.limitation_note += f" Subreddit crawl skipped: {extra}"
        except Exception as exc:  # noqa: BLE001
            self.status = "error"
            self.last_error = _redact(str(exc))[:400]
            logger.warning("Apify Reddit fetch failed: %s", self.last_error)
            return []

        kept: list[dict[str, Any]] = []
        for item in collected:
            published = parse_timestamp(
                item.get("createdAt")
                or item.get("created_utc")
                or item.get("created")
                or item.get("date")
            )
            if self.since and published and not is_after(published, self.since):
                continue
            if self.until and published and published > self.until:
                continue
            item["_published_at"] = published
            kept.append(item)
            if published:
                if self.earliest_published is None or published < self.earliest_published:
                    self.earliest_published = published
                if self.latest_published is None or published > self.latest_published:
                    self.latest_published = published
            if len(kept) >= self.max_records:
                break
        logger.info("Apify Reddit collector fetched %s public items", len(kept))
        return kept[: self.max_records]

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        data_type = str(raw.get("dataType") or raw.get("type") or "").lower()
        body = str(raw.get("body") or raw.get("text") or raw.get("selftext") or "")
        title = str(raw.get("title") or raw.get("link_title") or "")
        is_comment = "comment" in data_type or (body and not title and raw.get("parentId"))
        content_type = "comment" if is_comment else "post"
        post_id = str(raw.get("postId") or raw.get("parsedId") or raw.get("id") or "")
        comment_id = str(raw.get("commentId") or (raw.get("parsedId") if is_comment else "") or "")
        source_id = comment_id or post_id or str(raw.get("id") or raw.get("url") or "")
        url = str(raw.get("url") or raw.get("redditUrl") or "")
        if url and url.startswith("/"):
            url = f"https://www.reddit.com{url}"
        subreddit = str(
            raw.get("communityName")
            or raw.get("subreddit")
            or raw.get("community")
            or ""
        ).lstrip("r/")
        score = raw.get("upVotes")
        if score is None:
            score = raw.get("score")
        try:
            score_i = int(score) if score is not None else None
        except (TypeError, ValueError):
            score_i = None
        try:
            n_comments = int(raw.get("numberOfComments") or raw.get("num_comments") or 0)
        except (TypeError, ValueError):
            n_comments = None
        text = f"{title}\n\n{body}".strip() if title and body else (body or title)
        extra = {
            "source_type": "Reddit",
            "collection_platform": "Apify",
            "subreddit": subreddit or None,
            "post_id": post_id or None,
            "comment_id": comment_id or None,
            "score": score_i,
            "num_comments": n_comments,
            "content_type": content_type,
            "parent_id": raw.get("parentId") or raw.get("parent_id") or None,
            "author_display": raw.get("username") or raw.get("author") or None,
        }
        record = normalize_record(
            {
                "source": self.conversation_source,
                "source_item_id": source_id,
                "source_url": url,
                "author_id": extra["author_display"] or "",
                "published_at": raw.get("_published_at") or raw.get("createdAt") or raw.get("created_utc"),
                "title": title,
                "text": text,
                "original_text": text,
                "query_used": raw.get("_query") or "",
                "engagement_count": int(score_i or 0) + int(n_comments or 0),
                "extra": extra,
            }
        )
        # Keep distinct comments even when body text is similar.
        if source_id:
            digest = hashlib.sha256(f"reddit|{source_id}|{content_type}".encode("utf-8")).hexdigest()
            record["content_hash"] = digest
        return record

    def validate(self, record: dict[str, Any]) -> bool:
        if not is_valid_conversation(record, min_chars=20):
            return False
        return bool(record.get("published_at") and (record.get("source_url") or record.get("source_item_id")))
