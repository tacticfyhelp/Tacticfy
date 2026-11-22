"""Upgrading over an older install: a stale %LOCALAPPDATA%\\Tacticfy\\offsets.json must never shadow the
bundled config/offsets.json of the new release (in particular fm27_live_layout.human_team)."""

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from src import app_paths
from src.memory.process_reader import FM27ProcessReader, USER_OVERLAY_KEYS

ROOT = Path(__file__).resolve().parent.parent
BUNDLED = json.loads((ROOT / "config" / "offsets.json").read_text(encoding="utf-8"))


def v100_style_offsets(app_version=None) -> dict:
    """A full offsets.json as shipped by v1.0.0: same layout but no human_team (+ optional version stamp)."""
    old = copy.deepcopy(BUNDLED)
    old.pop("_app_version", None)
    old["fm27_live_layout"].pop("human_team")
    old["fm27_live_layout"]["_note"] = "v1.0.0 layout"
    if app_version is not None:
        old["_app_version"] = app_version
    return old


class TestUpgradeFromStaleUserOffsets(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.local = Path(self.enterContext(tempfile.TemporaryDirectory()))
        shutil.copytree(ROOT / "config", self.bundle / "config")
        # Simulate the installed (frozen) app: resources from _MEIPASS, user data from %LOCALAPPDATA%.
        self.enterContext(mock.patch.object(sys, "frozen", True, create=True))
        self.enterContext(mock.patch.object(sys, "_MEIPASS", str(self.bundle), create=True))
        self.enterContext(mock.patch.dict("os.environ", {"LOCALAPPDATA": str(self.local)}))

    def write_stale_user_offsets(self, data: dict) -> Path:
        path = app_paths.user_offsets_path()
        self.assertEqual(path, self.local / "Tacticfy" / "offsets.json")
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def make_reader(self) -> FM27ProcessReader:
        return FM27ProcessReader(app_paths.bundled_offsets_path(), app_paths.user_offsets_path())

    def assert_bundled_layout(self, reader: FM27ProcessReader) -> None:
        live = reader.offsets["fm27_live_layout"]
        self.assertIn("human_team", live)
        self.assertEqual(live, BUNDLED["fm27_live_layout"])

    def test_unstamped_v100_copy_is_ignored(self) -> None:
        self.write_stale_user_offsets(v100_style_offsets())
        self.assert_bundled_layout(self.make_reader())

    def test_v100_stamped_copy_is_ignored(self) -> None:
        self.write_stale_user_offsets(v100_style_offsets("1.0.0"))
        self.assert_bundled_layout(self.make_reader())

    def test_current_version_overlay_cannot_shadow_live_layout(self) -> None:
        # Even an overlay stamped with the running version may only carry calibration keys.
        stale = v100_style_offsets(app_paths.APP_VERSION)
        stale["calibrated"] = True
        stale["player_struct"] = dict(stale.get("player_struct", {}), stride_bytes=512)
        self.write_stale_user_offsets(stale)
        reader = self.make_reader()
        self.assert_bundled_layout(reader)
        self.assertEqual(reader.offsets["process_name"], BUNDLED["process_name"])
        self.assertTrue(reader.offsets["calibrated"])  # calibration keys still apply
        self.assertEqual(reader.offsets["player_struct"]["stride_bytes"], 512)

    def test_unreadable_overlay_falls_back_to_bundled(self) -> None:
        app_paths.user_offsets_path().write_text("{ not json", encoding="utf-8")
        self.assert_bundled_layout(self.make_reader())

    def test_human_team_reader_is_used_after_upgrade(self) -> None:
        from src.memory.live_layout import FM27LiveSquadReader

        self.write_stale_user_offsets(v100_style_offsets("1.0.0"))
        reader = FM27LiveSquadReader(self.make_reader().offsets["fm27_live_layout"])
        self.assertIsNotNone(reader.team_layout)


class TestBundledConfigIsCurrent(unittest.TestCase):
    def test_bundled_offsets_are_stamped_with_app_version(self) -> None:
        self.assertEqual(BUNDLED.get("_app_version"), app_paths.APP_VERSION,
                         "bump config/offsets.json _app_version together with APP_VERSION")

    def test_bundled_offsets_have_human_team(self) -> None:
        self.assertIn("human_team", BUNDLED["fm27_live_layout"])

    def test_calibrator_only_writes_overlay_keys(self) -> None:
        from src.memory.aob_calibrator import AOBCalibrator

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "offsets.json"
            calibrator = AOBCalibrator.__new__(AOBCalibrator)
            calibrator.offsets_path = path
            calibrator._persist_calibration({"estimated_stride": 512, "scale": "1-20"})
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(set(written) <= USER_OVERLAY_KEYS, set(written) - USER_OVERLAY_KEYS)

    @unittest.skipUnless((ROOT / "build" / "installer.iss").exists(), "installer script not in this working copy")
    def test_installer_blocks_downgrades_and_stamps_version(self) -> None:
        iss = (ROOT / "build" / "installer.iss").read_text(encoding="utf-8")
        self.assertIn("VersionInfoVersion", iss)
        self.assertIn("InitializeSetup", iss)


if __name__ == "__main__":
    unittest.main()
