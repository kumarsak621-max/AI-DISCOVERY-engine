"""HTTP trigger for external cron services.

Streamlit Cloud and similar hosts do not run a persistent worker.
Point a cron job at this endpoint, or at the Streamlit app with
`?collect=1&token=CRON_SECRET`.

    python -m scheduler.http_endpoint --port 8080

GET/POST /collect?token=...
GET /health
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

logger = logging.getLogger("scheduler.http")


def _authorized(token: str) -> bool:
    secret = os.getenv("CRON_SECRET", "").strip()
    if not secret:
        return False
    return token == secret


def run_collection_job() -> dict:
    from processing.dates import days_covering_months
    from scheduler.jobs import run_job

    window_days = int(os.getenv("RESEARCH_WINDOW_DAYS", "0") or 0)
    if window_days <= 0:
        window_days = days_covering_months(int(os.getenv("HISTORICAL_WINDOW_MONTHS", "30")))
    run_job(full_refresh=False, window_days=window_days)
    return {"ok": True, "status": "collection started and completed"}


class CronHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _token(self) -> str:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if qs.get("token"):
            return qs["token"][0]
        return self.headers.get("X-Cron-Token", "")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/health"}:
            self._send(200, {"ok": True, "service": "myntra-discovery-cron"})
            return
        if path == "/collect":
            if not os.getenv("CRON_SECRET", "").strip():
                self._send(503, {"ok": False, "error": "CRON_SECRET is not configured"})
                return
            if not _authorized(self._token()):
                self._send(401, {"ok": False, "error": "unauthorized"})
                return
            try:
                self._send(200, run_collection_job())
            except Exception as exc:  # noqa: BLE001
                logger.exception("Cron collection failed")
                self._send(500, {"ok": False, "error": str(exc)[:300]})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        self.do_GET()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(description="HTTP cron trigger for discovery collection")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("CRON_PORT", "8080")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CronHandler)
    logger.info("Cron HTTP endpoint listening on %s:%s", args.host, args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
