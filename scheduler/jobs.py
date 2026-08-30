"""Scheduled collection jobs for cron / Render / external schedulers.

Automatic collection is only active when this module is invoked on a schedule
(or when the dashboard visit-interval check is enabled). Visiting the UI does
not imply a background worker is running.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from config import DEFAULT_GEMINI_MODEL, DEFAULT_MODEL
from database.db import init_db, session_scope
from pipeline.discovery import run_discovery
from processing.dates import days_covering_months

logger = logging.getLogger("scheduler")


def run_job(
    *,
    full_refresh: bool = False,
    window_days: int = 30,
    sources: list[str] | None = None,
    max_records: int = 200,
) -> None:
    db_path = os.getenv("DATABASE_PATH", str(ROOT / "data" / "discovery.db"))
    init_db(db_path)
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    provider = os.getenv("AI_PROVIDER", "openrouter")
    if str(provider).lower() == "gemini":
        model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    else:
        model = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
    enabled = sources or ["google_play", "youtube"]
    with session_scope() as session:
        run = run_discovery(
            session,
            enabled_sources=enabled,
            max_records=max_records,
            model=model,
            temperature=0.1,
            api_key=api_key,
            window_days=window_days,
            full_refresh=full_refresh,
            provider=provider,
            gemini_key=gemini_key,
        )
        logger.info(
            "Scheduled run %s: new=%s analyzed=%s status=%s",
            run.id,
            run.conversations_new,
            run.conversations_analyzed,
            run.status,
        )


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(description="Myntra discovery collection job")
    parser.add_argument("--full-refresh", action="store_true", help="Rebuild last N-day window")
    parser.add_argument("--window-days", type=int, default=0, help="Override window in days (0 = last 30 months)")
    parser.add_argument("--window-months", type=int, default=30)
    parser.add_argument("--max-records", type=int, default=200)
    parser.add_argument(
        "--sources",
        default="google_play,youtube",
        help="Comma-separated source names",
    )
    parser.add_argument("--provider", default=os.getenv("AI_PROVIDER", "openrouter"))
    args = parser.parse_args()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    window_days = args.window_days or days_covering_months(args.window_months)
    os.environ["AI_PROVIDER"] = args.provider
    run_job(
        full_refresh=args.full_refresh,
        window_days=window_days,
        sources=sources,
        max_records=args.max_records,
    )


if __name__ == "__main__":
    main()
