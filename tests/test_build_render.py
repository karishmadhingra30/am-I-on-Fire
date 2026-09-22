from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

from fetch import _normalize_record  # noqa: E402
from summarize import _deterministic_summary  # noqa: E402
from test_fetch import BASE_RECORD  # noqa: E402
from build import _render_cards  # noqa: E402


class BuildRenderTest(unittest.TestCase):
    def test_fallback_summary_uses_incident_feed_when_no_ai_key_is_available(self) -> None:
        incident = _normalize_record(dict(BASE_RECORD), 0, "test")
        self.assertEqual(
            _deterministic_summary(incident),
            "The Test Fire is reported near Test location at 123.4 acres. "
            "The latest official feed lists containment at 56%.",
        )

    def test_active_card_contains_refresh_hooks_and_summary(self) -> None:
        html = _render_cards(
            [
                {
                    "id": "abc-123",
                    "name": "Test Fire",
                    "county": "Test County",
                    "url": "https://www.fire.ca.gov/incidents/2026/5/15/test-fire/",
                    "acres": 1234,
                    "containment": 40,
                    "startedDate": "2026-05-15",
                    "updated": "2026-05-25T18:36:37Z",
                    "active": True,
                    "location": "Near Test Road",
                    "summary": "The Test Fire is burning near Test Road in Test County at 1,234 acres. Containment stands at 40%.",
                }
            ]
        )
        self.assertIn('data-incident-id="abc-123"', html)
        self.assertIn('data-field="acres"', html)
        self.assertIn('data-field="containment"', html)
        self.assertIn("The Test Fire is burning", html)


if __name__ == "__main__":
    unittest.main()
