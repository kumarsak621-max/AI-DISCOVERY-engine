# Myntra AI Wishlist Conversion Discovery Engine

Live public-conversation research for:

> Percentage of users who purchase at least one item from their wishlist within 30 days of adding it.

This application collects **real, publicly available** posts, comments, and reviews. It does **not** include Demo Mode, synthetic reviews, or fabricated quotes.

**Public conversation research is directional and does not represent Myntra's complete customer population or internal behavioral data.**

Public data **cannot prove** actual Myntra wishlist-to-purchase conversion without internal transaction data.

Default research window: **last 30 days**, using **publication date** (not collection date). The window can be set to 7 / 30 / 60 / 90 days.

---

## Architecture

```
Public sources (Reddit, YouTube, web/RSS, App Store, Google Play)
        ↓
Collectors (robots.txt, rate limits, official APIs)
        ↓
Cleaning + publication-date window
        ↓
Deduplication (source+item_id, content hash, URL)
        ↓
SQLite (PostgreSQL-compatible schema)
        ↓
OpenRouter (per-conversation analysis; failures isolated)
        ↓
Theme clustering + Research-Based Opportunity Score
        ↓
Streamlit dashboard (Part 1 answers + evidence)
```

---

## Local setup

```bash
python -m venv .venv

# Mac/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill keys. **Never commit `.env`.**

```env
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=openai/gpt-4o-mini
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=python:myntra-discovery-engine:v1.0 (by /u/yourname)
YOUTUBE_API_KEY=
CRON_SECRET=
```

Then:

```bash
streamlit run app.py
```

The first dashboard page is **Part 1 — AI Discovery Answers**. Percentages are labeled **Percentage of analyzed public conversations**, never as percentages of Myntra users.

On first launch the app shows **Initializing 30-day discovery...** and collects the previous 30 days from configured sources (unless `SKIP_AUTO_COLLECTION=1`).

---

## API credentials

| Source | Required? | Notes |
| --- | --- | --- |
| **OpenRouter** | Required for AI analysis | Collection still stores records if the key is missing; analysis stays `pending`. |
| **Reddit** | Strongly recommended | Unauthenticated `search.json` is often HTTP 403. Create a Reddit **script** app. |
| **YouTube** | Required for YouTube | Official Data API v3. Without `YOUTUBE_API_KEY` the source is **Unavailable** (not faked). |
| **Web / RSS** | No key | `config/sources.yaml`. Each URL is checked against `robots.txt`. |
| **App Store** | No key | Public iTunes customer-review RSS. |
| **Google Play** | — | No official public reviews API. The collector reports **Unavailable** rather than scraping a JS/anti-bot page. |

Never commit `.env`. Never paste keys into dashboard logs.

---

## What a collection run does

1. Collect from enabled live sources (incremental using `last_successful_collection_time`, or full 30-day refresh)
2. Normalize and hash content
3. Deduplicate (`source + source_item_id`, `content_hash`, URL)
4. Store new records only
5. Analyze **new/pending** records with OpenRouter
6. Cluster themes and score opportunities (Research-Based Opportunity Score)
7. Refresh the dashboard

Failed sources do not crash the run. Failed LLM calls are stored for retry.

---

## Incremental vs full refresh

- **Run Collection Now** — fetch newly published items since last successful collection (still filtered to the research window).
- **Full 30-Day Refresh** — rebuild from `NOW-30 days` (or the selected window).

---

## Automatic collection / scheduled HTTP endpoint

Streamlit Community Cloud does **not** run a persistent worker. Options:

1. **Visit-based interval** in the sidebar (6h / 12h / 24h / off). Collection runs when someone opens the dashboard and the interval has elapsed. This is **not** a background daemon.
2. **CLI cron** (recommended on Render):

```bash
python -m scheduler.jobs
python -m scheduler.jobs --full-refresh --window-days 30
```

3. **HTTP trigger** for external cron (cron-job.org, EasyCron, GitHub Actions):

```bash
python -m scheduler.http_endpoint --port 8080
```

Then `GET/POST /collect?token=CRON_SECRET`.

If only Streamlit is running, the same secret works as:

`https://YOUR-APP/?collect=1&token=CRON_SECRET`

`CRON_SECRET` must be set or the trigger is rejected.

Automatic collection is **not** active unless you set an interval **or** configure an external cron.

---

## Web sources

Edit `config/sources.yaml`. Each RSS/HTML source can set URL, rate limit, and query. HTML sources are fetched only if `robots.txt` allows the path. The scraper never bypasses CAPTCHA, login, paywalls, or anti-bot systems.

---

## Tests

```bash
pytest
```

Covers date/window filtering, hashing, deduplication, JSON parsing, opportunity scoring, database insertion, incremental cutoffs, collector unavailability, OpenRouter missing-key handling, and Part 1 answer percentages.

---

## Deployment

### Streamlit Community Cloud

1. Push the repo (no `.env`, no `*.db`)
2. Set secrets in the Streamlit Cloud UI:

```toml
OPENROUTER_API_KEY = "..."
OPENROUTER_MODEL = "openai/gpt-4o-mini"
YOUTUBE_API_KEY = "..."
CRON_SECRET = "..."
```

3. Main file: `app.py`

### Render

- Build: `pip install -r requirements.txt`
- Start: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
- Optional Cron Job: `python -m scheduler.jobs`
- Set `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, optional Reddit/YouTube keys, `CRON_SECRET`

### Docker

```bash
docker build -t myntra-discovery-engine .
docker run -p 8501:8501 --env-file .env myntra-discovery-engine
```

This repository is **deployment-ready**. Hosting still requires you to create the Streamlit Cloud / Render service and paste environment variables. The application is not deployed until that is done.

---

## Honesty about coverage

If a source cannot be accessed legally, the Source Health panel shows **Unavailable**, **Error**, or **not configured** with the last error. The app will **not** generate fake reviews, fake URLs, or fake publication dates to fill the gap.
