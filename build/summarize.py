from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from fetch import Incident


DEFAULT_MODEL = "gpt-4.1-mini"
PENDING_SUMMARY = "Summary pending next build."


class SummaryError(RuntimeError):
    """Raised when an incident summary cannot be generated safely."""


def load_cache(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SummaryError(f"Summary cache is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise SummaryError(f"Summary cache must be a JSON object: {path}")
    return data


def save_cache(path: Path, cache: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summarize_incident(incident: Incident, detail_text: str, cache: dict[str, dict[str, str]]) -> str:
    cached = cache.get(incident.cache_key)
    if isinstance(cached, dict) and cached.get("summary"):
        return cached["summary"]

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SummaryError(
            "OPENAI_API_KEY is required to generate a new summary. "
            f"Missing cache entry for {incident.name} ({incident.cache_key})."
        )

    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    summary = _call_openai(incident, detail_text, model)
    summary = _normalize_summary(summary)

    cache[incident.cache_key] = {
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model": model,
        "incident_name": incident.name,
    }
    return summary


def _call_openai(incident: Incident, detail_text: str, model: str) -> str:
    client = OpenAI()
    prompt = f"""
Write exactly two sentences about this California wildfire.

Rules:
- First sentence: where the fire is and how big.
- Second sentence: current status and notable context, only if supported by the source.
- Neutral tone. Do not editorialize.
- Do not use words like "tragically" or "devastatingly".
- Do not invent evacuation, weather, damage, threat, or historical context.
- If the source is thin, keep the summary thin.
- Return only the two-sentence summary.

Incident feed:
Name: {incident.name}
County: {incident.county}
Location: {incident.location}
Acres burned: {_format_acres_for_prompt(incident.acres)}
Containment: {_format_percent_for_prompt(incident.containment)}
Started: {incident.started}
Updated: {incident.updated}
Admin unit: {incident.admin_unit or "Unknown"}
Control statement: {incident.control_statement or "None"}
Agencies: {incident.agency_names or "None"}

Official CAL FIRE incident update text:
{detail_text or "No detail-page update text was available."}
""".strip()

    try:
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": "You write concise, factual public-safety summaries from official wildfire data.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_output_tokens=180,
        )
    except Exception as exc:  # The SDK raises several API-specific subclasses.
        raise SummaryError(f"OpenAI summary generation failed for {incident.name}: {exc}") from exc

    text = getattr(response, "output_text", "") or ""
    if not text:
        raise SummaryError(f"OpenAI returned an empty summary for {incident.name}")
    return text


def _normalize_summary(text: str) -> str:
    clean = re.sub(r"\s+", " ", text.strip().strip('"')).strip()
    sentences = re.findall(r"[^.!?]+[.!?]", clean)
    if len(sentences) != 2:
        raise SummaryError(f"Summary must contain exactly two sentences, got {len(sentences)}: {clean}")
    return " ".join(sentence.strip() for sentence in sentences)


def _format_acres_for_prompt(acres: float | None) -> str:
    if acres is None:
        return "Unknown"
    return f"{acres:g}"


def _format_percent_for_prompt(percent: float | None) -> str:
    if percent is None:
        return "Unknown"
    return f"{percent:g}%"

