# Myntra AI Wishlist Conversion Discovery Engine

Live public-conversation research for:

> Percentage of users who purchase at least one item from their wishlist within 30 days of adding it.

This application collects **real, publicly available** posts, comments, and reviews. It does **not** include Demo Mode, synthetic reviews, or fabricated quotes.

**Public conversation research is directional and does not represent Myntra's complete customer population or internal behavioral data.**

Public data **cannot prove** actual Myntra wishlist-to-purchase conversion without internal transaction data.

Default **collection** window: **last 30 months**, using **publication date** (start = today − 30 months). Dates are computed dynamically.

Default **AI analysis** window: **last 30 days**, matching the wishlist→purchase business metric. The Analyze page also supports 6 / 12 / 30 months and a custom range.

---

## Architecture

```
Public sources (Google Play listing where allowed, YouTube Data API, Reddit, web/RSS, App Store)
        ↓
Collectors (robots.txt, rate limits, official APIs)
        ↓
Cleaning + publication-date window (30 months historical + latest incremental)
        ↓
Deduplication (source+item_id, content hash, URL)
        ↓
SQLite (PostgreSQL-compatible schema)
        ↓
AI provider layer (OpenRouter **or** Gemini — no silent failover)
        ↓
Theme clustering + Research-Based Opportunity Score
        ↓
Streamlit dashboard (Review Explorer, Analyze, Opportunities, Metric Decomposition, Ask AI)
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
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4o-mini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
YOUTUBE_API_KEY=
AI_PROVIDER=openrouter
CRON_SECRET=
```

Then:

```bash
streamlit run app.py
```

On first launch the app shows **Initializing 30-month historical collection...** (unless `SKIP_AUTO_COLLECTION=1`).

---

## API credentials

| Source | Required? | Notes |
| --- | --- | --- |
| **OpenRouter** | Required if that provider is selected | Collection still stores records if the key is missing; analysis stays `pending`. Missing key message: `OpenRouter API key is not configured.` |
| **Gemini** | Required if Gemini is selected | Google Generative Language API. Missing key message: `Gemini API key is not configured.` The app does **not** silently switch providers. |
| **YouTube** | Required for YouTube comments | Official Data API v3. Without `YOUTUBE_API_KEY` the source is **Unavailable** (not faked). |
| **Reddit (JSON/OAuth)** | Optional | Existing public JSON / OAuth collector is unchanged. Unauthenticated search is often HTTP 403. |
| **Reddit via Apify** | Required for Apify Reddit | `APIFY_API_TOKEN` + `APIFY_REDDIT_ACTOR_ID`. **Apify is used to collect publicly accessible Reddit data. It is not the official Reddit API.** Missing token: `Apify API token is not configured.` Missing actor: `Apify Reddit Actor is not configured.` A Reddit/Apify failure does not stop Play Store or YouTube. |
| **Web / RSS** | No key | `config/sources.yaml`. Each URL is checked against `robots.txt`. |
| **App Store** | No key | Public iTunes customer-review RSS. Coverage is whatever Apple's RSS returns (not a guaranteed 30-month dump). |
| **Google Play** | — | No official public reviews API. The listing HTML is robots-allowed; JSON-LD typically has aggregate rating only. Individual review RPCs are disallowed. The collector reports **Unavailable** rather than scraping blocked endpoints. |

Never commit `.env`. Never paste keys into dashboard logs.

---

## Reddit via Apify

**Apify is used to collect publicly accessible Reddit data. It is not the official Reddit API.**

1. Create an Apify account at [apify.com](https://apify.com/).
2. Create an API token (Console → Settings → Integrations).
3. Choose a Reddit Actor that collects public posts/comments (for example a public Reddit scraper Actor). Copy its Actor ID (`username/actor-name`).
4. Put placeholders only in `.env` (never commit real values):

```env
APIFY_API_TOKEN=
APIFY_REDDIT_ACTOR_ID=
# Optional: comma-separated public subreddit names. Use - to skip.
# APIFY_REDDIT_SUBREDDITS=India,IndianFashionAddicts,IndiaShopping
```

5. Run **Collect Latest Reviews** (or a 30-month refresh). Play Store and YouTube still run; Reddit/Apify is an extra source.
6. Open **Review Explorer**, filter **Reddit**, and inspect stored posts/comments.
7. Run **Analyze Reviews** with Gemini or OpenRouter — Reddit rows use the same AI layer.
8. Ask the chatbot questions such as “What does Reddit say about Myntra?”
9. Streamlit Cloud / Render secrets must include `APIFY_API_TOKEN` and `APIFY_REDDIT_ACTOR_ID`.

Search queries live in `config.py` (`APIFY_REDDIT_QUERIES`) and can be extended from the dashboard extra-queries box.

The Actor does **not** guarantee 30 months of Reddit history. The app requests a dynamic window (today − 30 months) and keeps records whose **publication date** falls in that window. Coverage is whatever the Actor actually returned.

---

## Historical vs latest collection

- **30-month historical** — `Full 30-Month Refresh` or first run. Start date = current date − 30 months. Older stored records are **not** deleted when newer collection runs.
- **Latest / Collect Latest Reviews** — incremental fetch of newly published public records since last successful collection, still filtered to the 30-month window. This is **not** a continuous real-time stream.

---

## Analyze Reviews

Default analysis period is **last 30 days**. Also supports last 6 / 12 / 30 months and a custom publication-date range.

Each analysis result shows an audit trail: AI provider, model, analysis timestamp, dataset range, records analyzed.

---

## Scheduled collection

Streamlit Community Cloud does **not** run a persistent worker. Options:

1. **Visit-based interval** in the sidebar (6h / 12h / 24h / off). Collection runs when someone opens the dashboard and the interval has elapsed. This is **not** a background daemon.
2. **CLI cron** (recommended on Render):

```bash
python -m scheduler.jobs
python -m scheduler.jobs --full-refresh --window-months 30
python -m scheduler.jobs --window-days 30 --provider gemini
```

3. **HTTP trigger** for external cron (cron-job.org, EasyCron, GitHub Actions):

```bash
python -m scheduler.http_endpoint --port 8080
```

Then `GET/POST /collect?token=CRON_SECRET`.

If only Streamlit is running, the same secret works as:

`https://YOUR-APP/?collect=1&token=CRON_SECRET`

Automatic collection is **not** active unless you set an interval **or** configure an external cron.

---

## What a collection run does

1. Collect from enabled live sources (incremental using `last_successful_collection_time`, or full 30-month refresh)
2. Normalize and hash content
3. Deduplicate (`source + source_item_id`, `content_hash`, URL)
4. Store new records only (older rows are kept)
5. Analyze **new/pending** records with the selected AI provider (OpenRouter or Gemini)
6. Cluster themes and score opportunities (Research-Based Opportunity Score + framework score)
7. Refresh the dashboard

Failed sources do not crash the run. Failed LLM calls are stored for retry. The app never silently switches AI providers.

---

## Incremental vs full refresh

- **Collect Latest Reviews** — fetch newly published items since last successful collection (still filtered to the 30-month window).
- **Full 30-Month Refresh** — rebuild from `NOW − 30 months`.

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
GEMINI_API_KEY = "..."
GEMINI_MODEL = "gemini-2.0-flash"
YOUTUBE_API_KEY = "..."
APIFY_API_TOKEN = "..."
APIFY_REDDIT_ACTOR_ID = "..."
CRON_SECRET = "..."
```

3. Main file: `app.py`

### Render

- Build: `pip install -r requirements.txt`
- Start: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
- Optional Cron Job: `python -m scheduler.jobs --window-months 30`
- Set `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `YOUTUBE_API_KEY`, optional Reddit keys, `CRON_SECRET`

### Docker

```bash
docker build -t myntra-discovery-engine .
docker run -p 8501:8501 --env-file .env myntra-discovery-engine
```

This repository is **deployment-ready**. Hosting still requires you to create the Streamlit Cloud / Render service and paste environment variables. The application is not deployed until that is done.

---

## Honesty about coverage

If a source cannot be accessed legally, the Source Health panel shows **Unavailable**, **Error**, or **not configured** with the last error. The app will **not** generate fake reviews, fake URLs, or fake publication dates to fill the gap.
