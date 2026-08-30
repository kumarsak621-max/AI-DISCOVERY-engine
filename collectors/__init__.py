"""Collectors package."""

from collectors.base import SourceAdapter
from collectors.google_play import GooglePlayCollector
from collectors.youtube import YouTubeCollector

__all__ = [
    "SourceAdapter",
    "YouTubeCollector",
    "GooglePlayCollector",
]
