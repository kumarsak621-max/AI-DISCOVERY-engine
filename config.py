"""Application constants, discovery queries, and scoring weights."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
CONFIG_DIR = ROOT_DIR / "config"
SOURCES_YAML = CONFIG_DIR / "sources.yaml"
DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "discovery.db"))

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_RECORDS = 200
DEFAULT_RESEARCH_WINDOW_DAYS = 30
REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_SCRAPE_DELAY_SECONDS = 1.5
USER_AGENT = os.getenv(
    "HTTP_USER_AGENT",
    "python:myntra-discovery-engine:v1.0 (public research; +https://localhost)",
)

OPPORTUNITY_WEIGHTS = {
    "frequency": 0.20,
    "severity": 0.20,
    "conversion_relevance": 0.25,
    "workaround": 0.15,
    "segment": 0.10,
    "confidence": 0.10,
}

HUMAN_VALIDATION_CONFIDENCE_THRESHOLD = 0.70

DISCLAIMER = (
    "Public conversation research is directional and does not represent "
    "Myntra's complete customer population or internal behavioral data."
)

BUSINESS_GOAL = (
    "Increase the percentage of users who purchase at least one item "
    "from their wishlist within 30 days of adding it."
)

MYNTRA_QUERIES: list[str] = [
    "Myntra wishlist",
    "Myntra saved items",
    "Myntra wishlist purchase",
    "Myntra saved product",
    "Myntra add to wishlist",
    "Myntra cart wishlist",
    "why didn't buy Myntra",
    "Myntra purchase hesitation",
    "Myntra product comparison",
    "Myntra size issue",
    "Myntra fit issue",
    "Myntra fitting",
    "Myntra size chart",
    "Myntra quality",
    "Myntra fabric",
    "Myntra reviews",
    "Myntra return",
    "Myntra price drop",
    "Myntra waiting for sale",
    "Myntra expensive",
    "Myntra alternative",
    "Myntra outfit",
    "Myntra styling",
    "Myntra occasion wear",
    "Myntra haul",
    "Myntra try on",
]

FASHION_QUERIES: list[str] = [
    "online clothes shopping hesitation",
    "online fashion purchase decision",
    "why I didn't buy clothes online",
    "clothes wishlist",
    "fashion wishlist",
    "online clothes size uncertainty",
    "online fashion fit problem",
    "how to know clothes will fit online",
    "online fashion reviews",
    "fashion product comparison",
    "clothes purchase regret",
    "online shopping return clothes",
    "how people decide what clothes to buy online",
    "fashion shopping uncertainty",
    "online fashion alternatives",
    "India online fashion shopping",
]

YOUTUBE_QUERIES: list[str] = [
    "Myntra reviews",
    "Myntra haul",
    "Myntra shopping",
    "Myntra fashion",
    "Myntra shopping experience",
    "Myntra sizing",
    "Myntra try on",
    "Myntra outfit review",
    "Myntra wishlist",
    "fashion shopping problems",
    "online fashion purchase uncertainty",
    "online fashion shopping India",
]

DISCOVERY_QUERIES: list[str] = MYNTRA_QUERIES + FASHION_QUERIES

HIGH_INTENT_STATUSES = {
    "considering",
    "postponed",
    "abandoned",
    "waiting",
    "alternative_purchased",
}

WISHLIST_BEHAVIORS = [
    "explicit_wishlist",
    "save_for_later",
    "cart_as_bookmark",
    "comparison_shortlist",
    "price_watch",
    "occasion_planning",
    "browsing_only",
    "unclear",
]

SCHEDULER_INTERVALS = {
    "Every 6 hours": 6,
    "Every 12 hours": 12,
    "Every 24 hours": 24,
    "Off (manual only)": 0,
}
