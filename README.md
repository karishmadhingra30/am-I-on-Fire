# CalFire incident summarizer

A static GitHub Pages site that summarizes active California wildfires and maps every CAL FIRE wildfire incident reported in the current calendar year.

## Run locally

Install Python 3.10+ dependencies:

```bash
pip install -r requirements.txt
```

Build the site:

```bash
python build/build.py
```

For local development, put `OPENAI_API_KEY=...` in `.env` or export it in your shell. GitHub Actions reads the key from repository secrets instead.

Preview the generated files:

```bash
cd dist
python -m http.server 8000
```

Open http://localhost:8000.

## Deploy

Push to `main` or run the GitHub Actions workflow manually. The workflow builds `dist/`, commits updated `cache/summaries.json` back to the repo, and deploys the built files to the `gh-pages` branch. There is no scheduled cron rebuild; the deployed page attempts to refresh volatile fields in the viewer's browser.

Required repository secret:

```text
OPENAI_API_KEY
```

GitHub Pages should be configured to serve the `gh-pages` branch.

## Data and summaries

The build reads CAL FIRE incident data from:

- Active incidents: `https://incidents.fire.ca.gov/umbraco/api/IncidentApi/List?inactive=false`
- Current-year incidents: `https://incidents.fire.ca.gov/umbraco/api/IncidentApi/List?inactive=true&year=YYYY`
- Official incident detail pages linked by the feed, used for recent update context when generating summaries

The list API currently exposes operational fields such as incident ID, name, update time, county, location, acres, containment, coordinates, incident type, active state, and official URL. Richer narrative context lives on the official detail pages, so the build fetches those pages for active wildfires before asking OpenAI for a two-sentence summary.

Summaries are cached in `cache/summaries.json` by `incident_id + last_updated_timestamp`. If an incident has not changed, the build reuses the cached summary and does not call OpenAI again.

The default model is `gpt-4.1-mini`, configurable with `OPENAI_MODEL`.

## Token cost note

Each active fire sends roughly 600-1,200 input tokens plus a short output of about 50-100 tokens, depending on the length of the official incident update page. Estimated build cost is approximately:

```text
(active fires needing new summaries) x (input tokens + output tokens) x model price
```

Because summaries are cached by update timestamp, most rebuilds should only pay for newly updated or newly reported active fires.

## Design decisions

- The page is dark by default for evening readability.
- The map starts fitted to California bounds, approximately southwest `[32.3, -124.5]` to northeast `[42.1, -114.1]`.
- Only records with `Type == "Wildfire"` are shown, so all-risk incidents like hazmat reports do not appear on the wildfire page.
- Browser live refresh is attempted on load. CAL FIRE currently does not advertise permissive CORS headers on the API response, so browsers may block direct refreshes. In that case the button is disabled and the page shows the last deployed build data.
- CSS is embedded into `index.html` so the built site ships as `index.html`, `incidents.json`, `historical.json`, and `refresh.js`.

## Disclaimer

This is not an official emergency information source. For evacuation orders, evacuation warnings, road closures, shelter information, and immediate safety instructions, see CAL FIRE, county emergency agencies, local law enforcement, and other local authorities.
