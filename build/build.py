from __future__ import annotations

import html
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from fetch import (
    ACTIVE_URL,
    CalFireDataError,
    fetch_active_incidents,
    fetch_historical_incidents,
    fetch_incident_detail_text,
    utc_now_iso,
    wildfire_only,
)
from summarize import SummaryError, load_cache, save_cache, summarize_incident


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build"
CACHE_PATH = ROOT / "cache" / "summaries.json"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"
TEMPLATE_PATH = BUILD_DIR / "template.html"


def main() -> int:
    try:
        build_site()
    except (CalFireDataError, SummaryError, OSError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    return 0


def build_site() -> None:
    _load_dotenv(ROOT / ".env")
    build_time = datetime.now(timezone.utc).replace(microsecond=0)
    year = build_time.year

    active = sorted(wildfire_only(fetch_active_incidents()), key=lambda item: item.acres or 0, reverse=True)
    historical = sorted(wildfire_only(fetch_historical_incidents(year)), key=lambda item: item.started)

    cache = load_cache(CACHE_PATH)
    active_json = []
    for incident in active:
        detail_text = fetch_incident_detail_text(incident.url)
        summary = summarize_incident(incident, detail_text, cache)
        active_json.append(incident.to_active_json(summary))

    historical_json = [incident.to_historical_json() for incident in historical]
    save_cache(CACHE_PATH, cache)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    (DIST_DIR / "incidents.json").write_text(_dump_json(active_json), encoding="utf-8")
    (DIST_DIR / "historical.json").write_text(_dump_json(historical_json), encoding="utf-8")
    shutil.copyfile(STATIC_DIR / "refresh.js", DIST_DIR / "refresh.js")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    index_html = _render_template(
        template,
        {
            "styles": styles,
            "build_timestamp": build_time.isoformat().replace("+00:00", "Z"),
            "build_timestamp_label": _format_datetime(build_time),
            "data_refreshed_label": "Not refreshed in this browser",
            "active_endpoint": ACTIVE_URL,
            "year": str(year),
            "cards": _render_cards(active_json),
            "empty_state_hidden": "" if not active_json else "hidden",
            "initial_incidents_json": _json_script(active_json),
            "historical_json": _json_script(historical_json),
            "repo_url": _repo_url(),
            "site_built_label": _format_datetime(build_time),
        },
    )
    (DIST_DIR / "index.html").write_text(index_html, encoding="utf-8")

    print(f"Built {DIST_DIR} at {utc_now_iso()} with {len(active_json)} active fires and {len(historical_json)} map records.")


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
    return rendered


def _render_cards(incidents: list[dict]) -> str:
    if not incidents:
        return ""
    return "\n".join(_render_card(incident) for incident in incidents)


def _render_card(incident: dict) -> str:
    status = "Active" if incident.get("active") else "No longer active"
    return f"""
<article class="incident-card" data-incident-id="{_attr(incident['id'])}" data-incident-url="{_attr(incident['url'])}">
  <div class="card-topline">
    <p class="eyebrow">{_text(incident.get('county') or 'Unknown county')}</p>
    <span class="status-pill" data-status>{_text(status)}</span>
  </div>
  <h3><a href="{_attr(incident['url'])}">{_text(incident['name'])}</a></h3>
  <dl class="metrics">
    <div>
      <dt>Acres</dt>
      <dd data-field="acres">{_text(_format_acres(incident.get('acres')))}</dd>
    </div>
    <div>
      <dt>Contained</dt>
      <dd data-field="containment">{_text(_format_percent(incident.get('containment')))}</dd>
    </div>
    <div>
      <dt>Started</dt>
      <dd>{_text(_format_date(incident.get('startedDate') or incident.get('started')))}</dd>
    </div>
  </dl>
  <p class="summary" data-summary>{_text(incident.get('summary') or 'Summary pending next build.')}</p>
  <p class="location">{_text(incident.get('location') or 'Location unavailable')}</p>
  <p class="card-refresh" data-card-refresh>Build data updated {_text(_format_date_time_short(incident.get('updated')))}</p>
</article>
""".strip()


def _json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _format_acres(acres: float | None) -> str:
    if acres is None:
        return "Unknown"
    if acres < 1:
        return f"{acres:g}"
    return f"{round(acres):,}"


def _format_percent(percent: float | None) -> str:
    if percent is None:
        return "Unknown"
    return f"{percent:g}%"


def _format_date(value: str | None) -> str:
    if not value:
        return "Unknown"
    try:
        parsed = datetime.fromisoformat(value[:10])
        return parsed.strftime("%b %-d, %Y")
    except ValueError:
        return value


def _format_date_time_short(value: str | None) -> str:
    if not value:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%b %-d, %Y %H:%M UTC")
    except ValueError:
        return value


def _format_datetime(value: datetime) -> str:
    return value.strftime("%b %-d, %Y %H:%M UTC")


def _text(value: object) -> str:
    return html.escape(str(value), quote=False)


def _attr(value: object) -> str:
    return html.escape(str(value), quote=True)


def _repo_url() -> str:
    return os.environ.get("GITHUB_REPOSITORY_URL") or "https://github.com/your-org/calfire-summarizer"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
