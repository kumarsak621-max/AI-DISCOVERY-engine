"""Compliant public-web collector driven by config/sources.yaml.

Checks robots.txt, uses delays and a descriptive User-Agent, never bypasses access controls.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

from collectors.base import SourceAdapter
from config import SOURCES_YAML, USER_AGENT
from processing.cleaning import is_valid_conversation, normalize_record
from processing.dates import is_after, parse_timestamp

logger = logging.getLogger(__name__)

_robot_cache: dict[str, RobotFileParser | None] = {}


def robots_allows(url: str, user_agent: str = USER_AGENT) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if robots_url not in _robot_cache:
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
            _robot_cache[robots_url] = parser
        except Exception:
            logger.info("Could not read robots.txt at %s; skipping host", robots_url)
            _robot_cache[robots_url] = None
            return False
    parser = _robot_cache[robots_url]
    if parser is None:
        return False
    return bool(parser.can_fetch(user_agent, url))


def load_source_config(path: str | None = None) -> dict[str, Any]:
    target = path or str(SOURCES_YAML)
    with open(target, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


class WebCollector(SourceAdapter):
    name = "web"

    def __init__(self, config_path: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.config_path = config_path
        self.config = load_source_config(config_path)

    def fetch(self) -> list[dict[str, Any]]:
        since = self.since or self.get_last_collection_time()
        items: list[dict[str, Any]] = []
        for source in self.config.get("sources") or []:
            if not source.get("enabled", True):
                continue
            url = source.get("url") or ""
            delay = float(source.get("rate_limit_seconds") or 1.5)
            if not url:
                continue
            if not robots_allows(url):
                logger.info("Web source skipped by robots.txt: %s", url)
                continue
            try:
                response = requests.get(
                    url,
                    timeout=20,
                    headers={"User-Agent": USER_AGENT},
                )
                response.raise_for_status()
                parsed = feedparser.parse(response.content)
                for entry in parsed.entries:
                    published = parse_timestamp(
                        getattr(entry, "published", None) or getattr(entry, "updated", None)
                    )
                    if since and not is_after(published, since):
                        continue
                    if self.until and published and published > self.until:
                        continue
                    title = getattr(entry, "title", "") or ""
                    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
                    keywords = [k.lower() for k in (source.get("require_keywords") or [])]
                    blob = f"{title} {summary}".lower()
                    if keywords and not any(k in blob for k in keywords):
                        continue
                    items.append(
                        {
                            "title": getattr(entry, "title", ""),
                            "summary": getattr(entry, "summary", "") or getattr(entry, "description", ""),
                            "link": getattr(entry, "link", ""),
                            "published": getattr(entry, "published", "") or getattr(entry, "updated", ""),
                            "author": getattr(entry, "author", ""),
                            "id": getattr(entry, "id", "") or getattr(entry, "link", ""),
                            "query": source.get("query") or source.get("name") or "rss",
                            "source_name": source.get("name") or "rss",
                        }
                    )
            except requests.RequestException as exc:
                logger.warning("RSS fetch failed for %s: %s", url, exc)
                self.last_error = str(exc)[:300]
            time.sleep(delay)

        for source in self.config.get("html_sources") or []:
            if not source.get("enabled", True):
                continue
            url = source.get("url") or ""
            delay = float(source.get("rate_limit_seconds") or 2.0)
            if not url or not robots_allows(url):
                logger.info("HTML source skipped (robots or missing URL): %s", url)
                continue
            try:
                response = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")
                content_sel = source.get("content_selector") or "p"
                date_sel = source.get("date_selector") or "time"
                title_el = soup.find(source.get("title_selector") or "h1")
                content_el = soup.select_one(content_sel)
                date_el = soup.select_one(date_sel)
                text = content_el.get_text(" ", strip=True) if content_el else ""
                title = title_el.get_text(" ", strip=True) if title_el else source.get("name") or ""
                published = date_el.get("datetime") if date_el else ""
                if date_el and not published:
                    published = date_el.get_text(" ", strip=True)
                pub_dt = parse_timestamp(published)
                if since and not is_after(pub_dt, since):
                    continue
                items.append(
                    {
                        "title": title,
                        "summary": text,
                        "link": url,
                        "published": published,
                        "author": "",
                        "id": url,
                        "query": source.get("query") or source.get("name") or "html",
                        "source_name": source.get("name") or "html",
                    }
                )
            except requests.RequestException as exc:
                logger.warning("HTML fetch failed for %s: %s", url, exc)
            time.sleep(delay)

        logger.info("Web collector fetched %s items", len(items))
        if not items and self.last_error:
            self.status = "error"
        return items[: self.max_records]

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        title = raw.get("title") or ""
        summary = raw.get("summary") or ""
        return normalize_record(
            {
                "source": self.name,
                "source_item_id": str(raw.get("id") or raw.get("link") or "")[:256],
                "source_url": raw.get("link") or "",
                "author_id": raw.get("author") or "",
                "published_at": raw.get("published"),
                "title": title,
                "text": f"{title}\n\n{summary}".strip(),
                "query_used": raw.get("query") or "rss",
                "engagement_count": 0,
                "extra": {"feed": raw.get("source_name") or ""},
            }
        )

    def validate(self, record: dict[str, Any]) -> bool:
        return is_valid_conversation(record, min_chars=40) and bool(record.get("source_url"))
