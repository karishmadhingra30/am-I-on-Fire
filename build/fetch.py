from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup


ACTIVE_URL = "https://incidents.fire.ca.gov/umbraco/api/IncidentApi/List?inactive=false"
HISTORICAL_URL = "https://incidents.fire.ca.gov/umbraco/api/IncidentApi/List?inactive=true&year={year}"
REQUIRED_FIELDS = {
    "UniqueId",
    "Name",
    "Updated",
    "Started",
    "County",
    "Location",
    "AcresBurned",
    "PercentContained",
    "Latitude",
    "Longitude",
    "Type",
    "IsActive",
    "Url",
}
HTTP_TIMEOUT = 30


class CalFireDataError(RuntimeError):
    """Raised when CAL FIRE data cannot be trusted for a build."""


@dataclass(frozen=True)
class Incident:
    id: str
    name: str
    updated: str
    started: str
    started_date: str
    county: str
    location: str
    acres: float | None
    containment: float | None
    latitude: float
    longitude: float
    incident_type: str
    active: bool
    final: bool
    url: str
    admin_unit: str
    control_statement: str
    agency_names: str
    extinguished_date: str

    @property
    def cache_key(self) -> str:
        return f"{self.id}:{self.updated}"

    def to_active_json(self, summary: str) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "updated": self.updated,
            "started": self.started,
            "startedDate": self.started_date,
            "county": self.county,
            "location": self.location,
            "acres": self.acres,
            "containment": self.containment,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "active": self.active,
            "url": self.url,
            "summary": summary,
        }

    def to_historical_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "started": self.started,
            "startedDate": self.started_date,
            "updated": self.updated,
            "county": self.county,
            "location": self.location,
            "acres": self.acres,
            "containment": self.containment,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "active": self.active,
            "contained": bool(self.final or self.containment == 100 or self.extinguished_date),
            "url": self.url,
        }


def fetch_active_incidents() -> list[Incident]:
    return _fetch_list(ACTIVE_URL)


def fetch_historical_incidents(year: int) -> list[Incident]:
    return _fetch_list(HISTORICAL_URL.format(year=year))


def wildfire_only(incidents: list[Incident]) -> list[Incident]:
    return [incident for incident in incidents if incident.incident_type.lower() == "wildfire"]


def fetch_incident_detail_text(url: str) -> str:
    if not url:
        return ""

    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT, headers=_headers())
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CalFireDataError(f"Failed to fetch incident detail page {url}: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return _extract_relevant_detail_lines(lines)


def _fetch_list(url: str) -> list[Incident]:
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT, headers=_headers())
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise CalFireDataError(f"Failed to fetch CAL FIRE endpoint {url}: {exc}") from exc
    except ValueError as exc:
        raise CalFireDataError(f"CAL FIRE endpoint returned invalid JSON: {url}") from exc

    if not isinstance(payload, list):
        raise CalFireDataError(f"Expected CAL FIRE endpoint to return a list: {url}")

    return [_normalize_record(record, index, url) for index, record in enumerate(payload)]


def _normalize_record(record: Any, index: int, source_url: str) -> Incident:
    if not isinstance(record, dict):
        raise CalFireDataError(f"Record {index} from {source_url} is not an object")

    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        raise CalFireDataError(f"Record {index} from {source_url} is missing fields: {', '.join(missing)}")

    incident_id = _required_str(record, "UniqueId", index)
    name = _required_str(record, "Name", index)
    updated = _required_str(record, "Updated", index)
    started = _required_str(record, "Started", index)
    latitude = _required_float(record, "Latitude", index)
    longitude = _required_float(record, "Longitude", index)
    incident_type = _required_str(record, "Type", index)
    url = _required_str(record, "Url", index)

    _require_iso_datetime(updated, "Updated", incident_id)
    _require_iso_datetime(started, "Started", incident_id)

    return Incident(
        id=incident_id,
        name=name.strip(),
        updated=updated,
        started=started,
        started_date=str(record.get("StartedDateOnly") or started[:10]),
        county=str(record.get("County") or "Unknown").strip(),
        location=str(record.get("Location") or "Unknown").strip(),
        acres=_optional_float(record.get("AcresBurned"), "AcresBurned", incident_id),
        containment=_optional_float(record.get("PercentContained"), "PercentContained", incident_id),
        latitude=latitude,
        longitude=longitude,
        incident_type=incident_type.strip(),
        active=bool(record.get("IsActive")),
        final=bool(record.get("Final")),
        url=url.strip(),
        admin_unit=str(record.get("AdminUnit") or "").strip(),
        control_statement=str(record.get("ControlStatement") or "").strip(),
        agency_names=str(record.get("AgencyNames") or "").strip(),
        extinguished_date=str(record.get("ExtinguishedDateOnly") or record.get("ExtinguishedDate") or "").strip(),
    )


def _extract_relevant_detail_lines(lines: list[str]) -> str:
    useful: list[str] = []
    capture = False
    stop_headings = {
        "ALERTCalifornia Camera Feed",
        "Resources Assigned",
        "Damage Assessment",
        "Social Media",
        "CAL FIRE Map Legend",
        "Quick Links",
    }

    for line in lines:
        if line in {"Incident Updates", "Latest News Updates"}:
            capture = True
            continue
        if capture and line in stop_headings:
            break
        if not capture:
            continue
        if line.startswith("Updated by:"):
            continue
        if line in {"More News Updates", "Less News Updates", "Reports", "Status reports"}:
            continue
        useful.append(line)
        if len(" ".join(useful)) > 1800:
            break

    return " ".join(useful)[:2200]


def _required_str(record: dict[str, Any], field: str, index: int) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CalFireDataError(f"Record {index} field {field} must be a non-empty string")
    return value


def _required_float(record: dict[str, Any], field: str, index: int) -> float:
    value = record.get(field)
    parsed = _optional_float(value, field, f"record {index}")
    if parsed is None:
        raise CalFireDataError(f"Record {index} field {field} must be a number")
    return parsed


def _optional_float(value: Any, field: str, incident_id: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise CalFireDataError(f"Incident {incident_id} field {field} must be numeric, not boolean")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CalFireDataError(f"Incident {incident_id} field {field} must be numeric") from exc


def _require_iso_datetime(value: str, field: str, incident_id: str) -> None:
    normalized = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CalFireDataError(f"Incident {incident_id} field {field} is not ISO-8601: {value}") from exc


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "User-Agent": "calfire-summarizer/1.0 (+https://github.com/)",
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

