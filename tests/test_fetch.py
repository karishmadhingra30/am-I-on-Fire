from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

from fetch import CalFireDataError, _normalize_record, wildfire_only  # noqa: E402


BASE_RECORD = {
    "Name": "Test Fire",
    "Final": False,
    "Updated": "2026-05-25T18:36:37Z",
    "Started": "2026-05-15T16:19:54Z",
    "AdminUnit": "CAL FIRE Test Unit",
    "AdminUnitUrl": None,
    "County": "Test County",
    "Location": "Test location",
    "AcresBurned": 123.4,
    "PercentContained": 56,
    "ControlStatement": None,
    "AgencyNames": "",
    "Longitude": -120.0,
    "Latitude": 38.0,
    "Type": "Wildfire",
    "UniqueId": "abc-123",
    "Url": "https://www.fire.ca.gov/incidents/2026/5/15/test-fire/",
    "ExtinguishedDate": "",
    "ExtinguishedDateOnly": "",
    "StartedDateOnly": "2026-05-15",
    "IsActive": True,
    "CalFireIncident": True,
    "NotificationDesired": False,
}


class FetchNormalizationTest(unittest.TestCase):
    def test_normalizes_valid_record(self) -> None:
        incident = _normalize_record(dict(BASE_RECORD), 0, "test")
        self.assertEqual(incident.id, "abc-123")
        self.assertEqual(incident.name, "Test Fire")
        self.assertEqual(incident.acres, 123.4)
        self.assertTrue(incident.active)

    def test_missing_required_field_fails_loudly(self) -> None:
        record = dict(BASE_RECORD)
        del record["UniqueId"]
        with self.assertRaisesRegex(CalFireDataError, "missing fields: UniqueId"):
            _normalize_record(record, 0, "test")

    def test_bad_coordinate_fails_loudly(self) -> None:
        record = dict(BASE_RECORD)
        record["Latitude"] = "not a number"
        with self.assertRaisesRegex(CalFireDataError, "Latitude must be numeric"):
            _normalize_record(record, 0, "test")

    def test_wildfire_only_filters_other_incident_types(self) -> None:
        wildfire = _normalize_record(dict(BASE_RECORD), 0, "test")
        hazmat_record = dict(BASE_RECORD)
        hazmat_record["UniqueId"] = "hazmat-1"
        hazmat_record["Type"] = "Hazmat"
        hazmat = _normalize_record(hazmat_record, 1, "test")
        self.assertEqual(wildfire_only([wildfire, hazmat]), [wildfire])


if __name__ == "__main__":
    unittest.main()
