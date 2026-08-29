"""YouTube comments collector via the official Data API v3."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from collectors.base import SourceAdapter
from processing.cleaning import is_valid_conversation, normalize_record
from processing.dates import is_after, parse_timestamp

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
COMMENT_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
RELEVANCE_TERMS = (
    "myntra",
    "wishlist",
    "wish list",
    "size",
    "fit",
    "sizing",
    "haul",
    "fashion",
    "dress",
    "kurta",
    "return",
    "sale",
    "price",
    "order",
    "buy",
    "cart",
    "quality",
    "fabric",
)


class YouTubeCollector(SourceAdapter):
    name = "youtube"
    requires_credentials = True

    def __init__(self, **kwargs: Any) -> None:
        api_key = kwargs.pop("api_key", None)
        super().__init__(**kwargs)
        self.api_key = str(api_key or os.getenv("YOUTUBE_API_KEY", "")).strip()

    def is_available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "YOUTUBE_API_KEY is not configured"
        return True, ""

    def fetch(self) -> list[dict[str, Any]]:
        if not self.api_key:
            self.status = "unavailable"
            self.last_error = "YOUTUBE_API_KEY is not configured"
            return []
        since = self.since or self.get_last_collection_time()
        published_after = None
        if since:
            published_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        video_meta: list[tuple[str, str, str]] = []
        for query in self.queries[:16]:
            try:
                params: dict[str, Any] = {
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": 10,
                    "order": "date",
                    "key": self.api_key,
                }
                if published_after:
                    params["publishedAfter"] = published_after
                response = requests.get(SEARCH_URL, params=params, timeout=20)
                if response.status_code in {401, 403}:
                    self.status = "error"
                    self.last_error = f"YouTube API rejected key ({response.status_code})"
                    return []
                response.raise_for_status()
                for item in response.json().get("items", []):
                    vid = item.get("id", {}).get("videoId")
                    snippet = item.get("snippet") or {}
                    if vid:
                        video_meta.append((vid, query, snippet.get("title") or ""))
            except requests.RequestException as exc:
                logger.warning("YouTube search failed for %r: %s", query, exc)
                self.last_error = str(exc)[:300]

        comments: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for video_id, query, video_title in video_meta:
            if len(comments) >= self.max_records:
                break
            page_token = None
            pages = 0
            while pages < 4 and len(comments) < self.max_records:
                pages += 1
                params = {
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": 50,
                    "textFormat": "plainText",
                    "order": "time",
                    "key": self.api_key,
                }
                if page_token:
                    params["nextPageToken"] = page_token
                    params["pageToken"] = page_token
                try:
                    response = requests.get(COMMENT_URL, params=params, timeout=20)
                    if response.status_code == 403:
                        break
                    response.raise_for_status()
                    payload = response.json()
                    for item in payload.get("items", []):
                        top = item.get("snippet", {}).get("topLevelComment", {})
                        snippet = top.get("snippet") or {}
                        comment_id = top.get("id") or item.get("id") or ""
                        published = parse_timestamp(snippet.get("publishedAt"))
                        if since and not is_after(published, since):
                            continue
                        if self.until and published and published > self.until:
                            continue
                        if comment_id in seen_ids:
                            continue
                        seen_ids.add(comment_id)
                        snippet["_query"] = query
                        snippet["_video_id"] = video_id
                        snippet["_video_title"] = video_title
                        snippet["_comment_id"] = comment_id
                        blob = f"{video_title} {snippet.get('textOriginal') or snippet.get('textDisplay') or ''}".lower()
                        if "myntra" not in (video_title or "").lower() and not any(
                            term in blob for term in RELEVANCE_TERMS
                        ):
                            continue
                        comments.append(snippet)
                        if len(comments) >= self.max_records:
                            break
                    page_token = payload.get("nextPageToken")
                    if not page_token:
                        break
                except requests.RequestException as exc:
                    logger.warning("YouTube comments failed for %s: %s", video_id, exc)
                    break
        logger.info("YouTube collector fetched %s comments", len(comments))
        return comments[: self.max_records]

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        video_id = raw.get("_video_id") or ""
        comment_id = raw.get("_comment_id") or ""
        text = raw.get("textDisplay") or raw.get("textOriginal") or ""
        channel = ""
        channel_obj = raw.get("authorChannelId")
        if isinstance(channel_obj, dict):
            channel = channel_obj.get("value") or ""
        extra = {
            "source_type": "YouTube",
            "video_id": video_id,
            "video_title": raw.get("_video_title") or "",
            "comment_id": comment_id,
            "channel": channel or raw.get("authorDisplayName") or "",
            "author_display": raw.get("authorDisplayName") or "",
            "like_count": int(raw.get("likeCount") or 0),
        }
        return normalize_record(
            {
                "source": self.name,
                "source_item_id": comment_id or f"{video_id}:{hash(text)}",
                "source_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
                "author_id": channel or raw.get("authorDisplayName") or "",
                "published_at": raw.get("publishedAt"),
                "title": raw.get("_video_title") or "",
                "text": text,
                "query_used": raw.get("_query") or "",
                "engagement_count": int(raw.get("likeCount") or 0),
                "extra": extra,
            }
        )

    def validate(self, record: dict[str, Any]) -> bool:
        return is_valid_conversation(record, min_chars=20) and bool(record.get("published_at"))
