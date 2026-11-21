"""Tests for release plumbing: resource paths, user offsets overlay and the bug-report URL."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

from src import app_paths
from src.app_logging import scrub
from src.bug_report import LOG_LINES, MAX_URL_LENGTH, build_issue_url
from src.memory.process_reader import FM27ProcessReader, deep_merge

ROOT = Path(__file__).resolve().parent.parent


class TestAppPaths(unittest.TestCase):
    def test_resources_resolve_from_checkout(self) -> None:
        self.assertFalse(app_paths.is_frozen())
        self.assertEqual(app_paths.resource_path("config", "formations.json"), ROOT / "config" / "formations.json")
        self.assertTrue(app_paths.icon_path().exists())
        self.assertTrue(app_paths.bundled_offsets_path().exists())

    def test_frozen_uses_meipass_and_localappdata(self) -> None:
        with tempfile.TemporaryDirectory() as bundle, tempfile.TemporaryDirectory() as local:
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "_MEIPASS", bundle, create=True), \
                    mock.patch.dict("os.environ", {"LOCALAPPDATA": local}):
                self.assertTrue(app_paths.is_frozen())
                self.assertEqual(app_paths.resource_path("config"), Path(bundle) / "config")
                self.assertEqual(app_paths.user_data_dir(), Path(local) / "Tacticfy")
                self.assertEqual(app_paths.log_file(), Path(local) / "Tacticfy" / "logs" / "app.log")
                self.assertEqual(app_paths.user_offsets_path(), Path(local) / "Tacticfy" / "offsets.json")


class TestOffsetsOverlay(unittest.TestCase):
    def _reader(self, overlay: dict) -> FM27ProcessReader:
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        base = tmp / "offsets.json"
        base.write_text(json.dumps({"player_struct": {"stride_bytes": 1024, "ca_offset": 20}, "calibrated": False}))
        user = tmp / "user.json"
        user.write_text(json.dumps(overlay))
        return FM27ProcessReader(base, user)

    def test_deep_merge(self) -> None:
        merged = deep_merge({"a": {"x": 1, "y": 2}, "b": 1}, {"a": {"y": 3}, "c": 4})
        self.assertEqual(merged, {"a": {"x": 1, "y": 3}, "b": 1, "c": 4})

    def test_matching_overlay_is_merged(self) -> None:
        reader = self._reader({"_app_version": app_paths.APP_VERSION, "calibrated": True,
                               "player_struct": {"stride_bytes": 512}})
        self.assertTrue(reader.offsets["calibrated"])
        self.assertEqual(reader.offsets["player_struct"], {"stride_bytes": 512, "ca_offset": 20})

    def test_overlay_from_other_version_is_ignored(self) -> None:
        reader = self._reader({"_app_version": "0.0.1", "calibrated": True})
        self.assertFalse(reader.offsets["calibrated"])


class TestBugReport(unittest.TestCase):
    def test_url_is_prefilled(self) -> None:
        url = build_issue_url(["line one", "line two"])
        parsed = urlparse(url)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", app_paths.GITHUB_ISSUES_NEW_URL)
        query = parse_qs(parsed.query)
        body = query["body"][0]
        self.assertIn(app_paths.APP_VERSION, body)
        self.assertIn("OS:", body)
        self.assertIn("line two", body)
        self.assertIn(app_paths.APP_VERSION, query["title"][0])

    def test_long_logs_are_trimmed(self) -> None:
        lines = [f"{i:04d} " + "x" * 400 for i in range(LOG_LINES)]
        url = build_issue_url(lines)
        self.assertLessEqual(len(url), MAX_URL_LENGTH)
        self.assertIn(lines[-1][:4], parse_qs(urlparse(url).query)["body"][0])  # newest lines kept

    def test_scrub_removes_home_and_user(self) -> None:
        text = r"Error in C:\Users\alice\AppData\Local\Tacticfy and C:/Users/alice/x, user alice"
        out = scrub(text, [r"C:\Users\alice", "alice"])
        self.assertNotIn("alice", out)
        self.assertIn(r"~\AppData", out)


if __name__ == "__main__":
    unittest.main()
