"""Reddit collector — OAuth when configured, otherwise public JSON search.

Collects public posts and comments. Hashes authors. Filters by publication time.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

import requests

from collectors.base import SourceAdapter
from config import USER_AGENT
from processing.cleaning import is_valid_conversation, normalize_record
from processing.dates import is_after, parse_timestamp

logger = logging.getLogger(__name__)

PUBLIC_SEARCH = "https://www.reddit.com/search.json"
OAUTH_SEARCH = "https://oauth.reddit.com/search"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"


class RedditCollector(SourceAdapter):
    name = "reddit"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sleep_seconds = float(os.getenv("REDDIT_SLEEP_SECONDS", "1.2"))
        self.client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
        self.user_agent = os.getenv("REDDIT_USER_AGENT", USER_AGENT)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self._token: str | None = None

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def _auth_headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}", "User-Agent": self.user_agent}
        return {"User-Agent": self.user_agent}

    def _maybe_oauth(self) -> None:
        if not (self.client_id and self.client_secret) or self._token:
            return
        try:
            response = requests.post(
                TOKEN_URL,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self.user_agent},
                timeout=20,
            )
            if response.status_code == 200:
                self._token = response.json().get("access_token")
                logger.info("Reddit OAuth token acquired")
            else:
                logger.warning("Reddit OAuth failed (%s); using public JSON", response.status_code)
        except requests.RequestException as exc:
            logger.warning("Reddit OAuth error: %s", exc)

    def fetch(self) -> list[dict[str, Any]]:
        self._maybe_oauth()
        since = self.since or self.get_last_collection_time()
        collected: list[dict[str, Any]] = []
        if not self.queries:
            self.last_error = "No Reddit queries configured"
            self.status = "error"
            return []

        search_url = OAUTH_SEARCH if self._token else PUBLIC_SEARCH
        queries = self.queries[:20]
        per_query = max(5, min(25, self.max_records // max(len(queries), 1)))
        kinds = ("link", "comment")
        for query in queries:
            if len(collected) >= self.max_records:
                break
            for kind in kinds:
                if len(collected) >= self.max_records:
                    break
                try:
                    params = {
                        "q": query,
                        "sort": "new" if since else "relevance",
                        "limit": per_query,
                        "restrict_sr": "false",
                        "type": kind,
                        "t": "month",
                    }
                    response = self.session.get(
                        search_url, params=params, headers=self._auth_headers(), timeout=20
                    )
                    if response.status_code == 403:
                        self.last_error = (
                            "Reddit returned HTTP 403 for unauthenticated search. "
                            "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (script app) "
                            "and a REDDIT_USER_AGENT of the form python:app:v1.0 (by /u/yourname)."
                        )
                        self.status = "error"
                        logger.warning(self.last_error)
                        return collected
                    if response.status_code == 429:
                        self.last_error = "Reddit rate limited"
                        logger.warning("Reddit rate limited")
                        return collected
                    if response.status_code >= 400:
                        logger.warning("Reddit search %s for %r: %s", kind, query, response.status_code)
                        continue
                    children = response.json().get("data", {}).get("children", [])
                    for child in children:
                        data = child.get("data") or {}
                        created = parse_timestamp(data.get("created_utc"))
                        if since and not is_after(created, since):
                            continue
                        if self.until and created and created > self.until:
                            continue
                        data["_query"] = query
                        data["_kind"] = kind
                        collected.append(data)
                except requests.RequestException as exc:
                    logger.warning("Reddit fetch failed for %r: %s", query, exc)
                    self.last_error = str(exc)[:300]
                time.sleep(self.sleep_seconds)
        logger.info("Reddit collector fetched %s items", len(collected))
        return collected[: self.max_records]

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        kind = raw.get("_kind") or ("comment" if raw.get("body") and not raw.get("selftext") else "link")
        title = raw.get("title") or raw.get("link_title") or ""
        body = raw.get("selftext") or raw.get("body") or ""
        permalink = raw.get("permalink") or ""
        url = f"https://www.reddit.com{permalink}" if permalink else str(raw.get("url") or "")
        item_id = str(raw.get("id") or "")
        extra = {
            "source_type": "Reddit",
            "subreddit": raw.get("subreddit") or "",
            "kind": kind,
            "score": int(raw.get("score") or 0),
            "num_comments": int(raw.get("num_comments") or 0),
        }
        return normalize_record(
            {
                "source": self.name,
                "source_item_id": item_id,
                "source_url": url,
                "author_id": raw.get("author") or "",
                "published_at": raw.get("created_utc"),
                "title": title,
                "text": f"{title}\n\n{body}".strip(),
                "query_used": raw.get("_query") or "",
                "engagement_count": int(raw.get("score") or 0) + int(raw.get("num_comments") or 0),
                "extra": extra,
            }
        )

    def validate(self, record: dict[str, Any]) -> bool:
        if not is_valid_conversation(record, min_chars=30):
            return False
        return bool(record.get("source_url") and record.get("published_at"))
