"""Collectors package."""

from collectors.apify_reddit import ApifyRedditCollector
from collectors.app_store import AppStoreCollector
from collectors.base import SourceAdapter
from collectors.google_play import GooglePlayCollector
from collectors.reddit import RedditCollector
from collectors.web_scraper import WebCollector
from collectors.youtube import YouTubeCollector

__all__ = [
    "SourceAdapter",
    "RedditCollector",
    "ApifyRedditCollector",
    "YouTubeCollector",
    "WebCollector",
    "GooglePlayCollector",
    "AppStoreCollector",
]
