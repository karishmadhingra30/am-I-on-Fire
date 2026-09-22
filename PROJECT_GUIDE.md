# CalFire incident summarizer

A public, static wildfire dashboard that turns official CAL FIRE incident records into a browser-friendly map and incident list.

## What it does

The build downloads active and current-year California wildfire records, filters to wildfires, and generates static HTML and JSON. Visitors can inspect the published snapshot and open each official incident page; the site is explicitly not an emergency-alert source.

AI enrichment is optional. Without an API key, every new incident receives a deterministic summary based only on CAL FIRE feed fields, keeping the public deployment reliable and credential-free.

## Architecture

```text
CAL FIRE incident feed -> Python build -> dist/ static site -> GitHub Pages
                                  |
                         optional OpenAI summary
```

- `build/fetch.py`: retrieves and normalizes official incident records.
- `build/build.py`: creates the portable static site and JSON data files.
- `build/summarize.py`: reuses reviewable cached summaries, optionally enriches new incidents, or falls back to feed data.
- `static/refresh.js`: attempts a browser-side freshness check and clearly retains the published snapshot if CORS blocks it.

## Stack

| Layer | Technology | Why it is here |
| --- | --- | --- |
| Data source | CAL FIRE public incident API | Official source for the incident records shown. |
| Build | Python | Produces a low-cost portable site from a versioned snapshot. |
| Hosting | GitHub Pages | Hosts the finished static files without a backend. |
| Optional enrichment | OpenAI Responses API | Adds concise context only when a key is intentionally configured. |

## Running it

```bash
pip install -r requirements.txt
python build/build.py
cd dist && python -m http.server 8000
```

Run `python -m unittest discover tests` for the build and normalization checks. These tests were run locally on 2026-09-22. An API key is not needed for the baseline build.

## Decisions and tradeoffs

| Decision | Chosen | Rejected or alternative | Why / tradeoff |
| --- | --- | --- | --- |
| Baseline summary | Deterministic feed-derived text | Make AI mandatory | A public safety-adjacent site must keep building without secret-dependent enrichment. |
| Delivery | Static GitHub Pages build | Always-on backend | Reduces operating cost and makes each snapshot reviewable in Git. |
| Freshness | Published snapshot with a browser refresh attempt | Claim live data unconditionally | CAL FIRE CORS policy can block client fetches, so the interface must preserve that uncertainty. |
