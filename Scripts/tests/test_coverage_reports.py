"""Checks for two-report preflight and layer-aware coverage policy."""

import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from validate_coverage_reports import (  # noqa: E402
    CoverageReportError,
    validate_cobertura,
    validate_lcov,
)


LCOV = (
    "TN:\\n"
    "SF:MeetingBar/Calendar/EventFiltering.swift\\n"
    "DA:12,1\\n"
    "DA:13,0\\n"
    "end_of_record\\n"
)
XML = (
    '<coverage lines-valid="2" lines-covered="1">'
    '<packages><package name="MeetingBar"><classes>'
    '<class name="CalendarSync" filename="CalendarSync.swift"/>'
    '</classes></package></packages></coverage>'
)

class CoverageReportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.logic = Path(self.temp.name) / "swiftpm.lcov"
        self.app = Path(self.temp.name) / "cobertura.xml"

    def write_both(self):
        self.logic.write_text(LCOV, encoding="utf-8")
        self.app.write_text(XML, encoding="utf-8")

    def test_valid_reports_pass(self):
        self.write_both()
        validate_lcov(self.logic)
        validate_cobertura(self.app)

    def test_missing_swiftpm_report_fails(self):
        self.app.write_text(XML, encoding="utf-8")
        with self.assertRaises(CoverageReportError):
            validate_lcov(self.logic)

    def test_missing_app_report_fails(self):
        self.logic.write_text(LCOV, encoding="utf-8")
        with self.assertRaises(CoverageReportError):
            validate_cobertura(self.app)

    def test_empty_or_incomplete_lcov_fails(self):
        self.logic.write_text("TN:\nSF:MeetingBar/foo.swift\nend_of_record\n", encoding="utf-8")
        with self.assertRaises(CoverageReportError):
            validate_lcov(self.logic)

    def test_malformed_or_empty_cobertura_fails(self):
        self.app.write_text("<coverage", encoding="utf-8")
        with self.assertRaises(CoverageReportError):
            validate_cobertura(self.app)
        self.app.write_text('<coverage lines-valid="0" lines-covered="0"/>', encoding="utf-8")
        with self.assertRaises(CoverageReportError):
            validate_cobertura(self.app)


class CoverageScopeTests(unittest.TestCase):
    def test_all_swiftpm_sources_are_in_blocking_domain_scope(self):
        package = (ROOT / "Package.swift").read_text(encoding="utf-8")
        sources_match = re.search(r"sources:\s*\[(.*?)\]", package, re.S)
        self.assertIsNotNone(sources_match)
        swiftpm = {
            "MeetingBar/" + path
            for path in re.findall(r'"([^"]+\.swift)"', sources_match.group(1))
        }
        self.assertTrue(swiftpm)

        config = (ROOT / "codecov.yml").read_text(encoding="utf-8")
        domain_section = config.split("      domain_logic:", 1)[1].split("      full_app:", 1)[0]
        domain = set(re.findall(r"^\s+- (MeetingBar/[^\s]+\.swift)$", domain_section, re.M))
        self.assertFalse(swiftpm - domain, f"SwiftPM sources missing from gate: {swiftpm - domain}")

    def test_provider_ui_boundary_is_not_hidden_from_full_app_report(self):
        config = (ROOT / "codecov.yml").read_text(encoding="utf-8")
        self.assertIn("      full_app:", config)
        self.assertIn("        informational: true", config.split("      full_app:", 1)[1])
        self.assertIn("          - MeetingBar/", config.split("      full_app:", 1)[1])
        self.assertNotIn("\nignore:", config)
        domain_section = config.split("      domain_logic:", 1)[1].split("      full_app:", 1)[0]
        for boundary in (
            "MeetingBar/Calendar/Providers/EventKit/EventKitEventStore.swift",
            "MeetingBar/Calendar/Providers/Google/GoogleCalendarEventStore.swift",
            "MeetingBar/Preferences/CalendarsTab.swift",
        ):
            self.assertNotIn(boundary, domain_section)
        for reliability in (
            "MeetingBar/Calendar/CalendarRepository.swift",
            "MeetingBar/Calendar/CalendarSync.swift",
            "MeetingBar/Notifications/NotificationScheduler.swift",
        ):
            self.assertIn(reliability, domain_section)


if __name__ == "__main__":
    unittest.main()
