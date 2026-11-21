"""End-to-end tests for the local web server: API, security checks, static files and lifecycle."""

import base64
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request

from src.memory.fallback_loader import generate_sample_squad
from src.memory.process_reader import ProcessReadResult
from src.web.server import create_server
from src.web.service import TacticfyService

ROOT = Path(__file__).resolve().parent.parent


class WebApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        service = TacticfyService(ROOT / "config", Path(cls._tmp.name) / "offsets.user.json")
        cls.server = create_server(0, service=service, web_root=ROOT / "web")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = cls.server.origin

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls._tmp.cleanup()

    def call(self, path, body=None, headers=None):
        h = {"X-Tacticfy": "1", "Content-Type": "application/json"} if body is not None else {}
        h.update(headers or {})
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                ctype = resp.headers.get("Content-Type", "")
                return resp.status, (json.loads(raw) if "json" in ctype else raw), resp.headers
        except urllib.error.HTTPError as err:
            raw = err.read()
            return err.code, (json.loads(raw) if raw.startswith(b"{") else raw), err.headers

    def load_sample(self):
        status, state, _ = self.call("/api/load/sample", {})
        self.assertEqual(status, 200)
        return state

    # ------------------------------------------------------------------ basics
    def test_ping_meta_and_i18n(self) -> None:
        self.assertEqual(self.call("/api/ping")[1]["app"], "Tacticfy")
        meta = self.call("/api/meta")[1]
        self.assertIn("High-Scoring Attacking", meta["styles"])
        self.assertEqual(meta["bench_sizes"], [7, 9])
        self.assertTrue(meta["formations"])
        he = self.call("/api/i18n/he")[1]
        self.assertEqual(he["dir"], "rtl")
        self.assertEqual(self.call("/api/i18n/fr")[0], 404)

    def test_static_files_and_headers(self) -> None:
        status, body, headers = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(b"app.js", body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        for path in ("/app.js", "/theme-init.js", "/assets/app.css", "/assets/tacticfy-64.png"):
            self.assertEqual(self.call(path)[0], 200, path)

    def test_path_traversal_is_blocked(self) -> None:
        for path in ("/../config/offsets.json", "/%2e%2e/main.py", "/..%5cmain.py", "/assets/../../main.py"):
            self.assertEqual(self.call(path)[0], 404, path)

    # ------------------------------------------------------------------ security
    def test_post_requires_client_header_and_json(self) -> None:
        self.assertEqual(self.call("/api/load/sample", {}, {"X-Tacticfy": "0"})[0], 403)
        self.assertEqual(self.call("/api/load/sample", {}, {"Content-Type": "text/plain"})[0], 403)

    def test_foreign_origin_and_host_are_rejected(self) -> None:
        self.assertEqual(self.call("/api/load/sample", {}, {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.call("/api/ping", None, {"Host": "evil.example:80"})[0], 403)
        self.assertEqual(self.call("/api/load/sample", {}, {"Origin": self.base})[0], 200)

    # ------------------------------------------------------------------ analysis
    def test_sample_squad_analysis_shape(self) -> None:
        state = self.load_sample()
        a = state["analysis"]
        self.assertEqual(state["source"], "sample")
        self.assertEqual(len(a["lineup"]["best_xi"]), 11)
        slot = a["lineup"]["best_xi"][0]
        for key in ("slot_id", "ip_role", "oop_role", "ip_xy", "oop_xy", "instructions"):
            self.assertIn(key, slot)
        self.assertEqual(a["bench"]["size"], 9)
        self.assertEqual(len(a["squad"]), len(generate_sample_squad()))
        self.assertEqual(len(a["training"]), len(a["squad"]))
        self.assertTrue(a["plan_text"].startswith("FM27 Match Plan"))
        self.assertTrue(all(t["reason_key"].startswith("training.reason.") for t in a["training"]))

    def test_settings_update_and_validation(self) -> None:
        self.load_sample()
        status, state, _ = self.call("/api/settings", {"bench_size": 7, "style": "Defensive Solidity", "important": True})
        self.assertEqual(status, 200)
        self.assertEqual(state["analysis"]["bench"]["size"], 7)
        self.assertEqual(state["analysis"]["lineup"]["style"], "Defensive Solidity")
        self.assertTrue(state["analysis"]["lineup"]["important"])
        self.assertEqual(self.call("/api/settings", {"bench_size": 8})[0], 400)
        self.assertEqual(self.call("/api/settings", {"style": "Tiki-Taka"})[0], 400)
        self.assertEqual(self.call("/api/settings", {"formation": "9-0-1"})[0], 400)
        self.call("/api/settings", {"bench_size": 9, "style": "High-Scoring Attacking", "important": False})

    def test_lock_forces_player_into_best_xi(self) -> None:
        state = self.load_sample()
        starters = {s["player_id"] for s in state["analysis"]["lineup"]["best_xi"]}
        outsider = next(c["player"] for c in state["analysis"]["squad"]
                        if c["player"]["id"] not in starters and not c["player"]["is_gk"])
        status, state, _ = self.call("/api/lock", {"player_id": outsider["id"], "locked": True})
        self.assertEqual(status, 200)
        self.assertIn(outsider["id"], {s["player_id"] for s in state["analysis"]["lineup"]["best_xi"]})
        self.call("/api/lock", {"player_id": outsider["id"], "locked": False})
        self.assertEqual(self.call("/api/lock", {"player_id": -42, "locked": True})[0], 404)

    def test_import_csv(self) -> None:
        rows = ["Name,Age,Position,CA,PA"] + [f"Player {i},{20 + i % 10},MC,{120 + i},{150 + i}" for i in range(14)]
        data = base64.b64encode("\n".join(rows).encode()).decode()
        status, state, _ = self.call("/api/import", {"filename": "squad.csv", "data": data})
        self.assertEqual(status, 200, state)
        self.assertEqual(state["source"], "import")
        self.assertEqual(state["player_count"], 14)
        status, err, _ = self.call("/api/import", {"filename": "x.exe", "data": data})
        self.assertEqual(status, 400)
        small = base64.b64encode("Name,Age\nA,20".encode()).decode()
        status, err, _ = self.call("/api/import", {"filename": "small.csv", "data": small})
        self.assertEqual((status, err["error"]["key"]), (400, "dialog.import_incomplete.body"))

    def test_live_load_falls_back_when_fm_is_not_running(self) -> None:
        not_running = ProcessReadResult(False, "not_running", "fm.exe is not running.")
        with mock.patch.object(self.server.service.reader, "read_squad", return_value=not_running):
            status, state, _ = self.call("/api/load/live", {})
        self.assertEqual(status, 200)
        self.assertEqual(state["status"]["key"], "status.fallback")
        self.assertEqual(state["notice"]["title"], "dialog.not_loaded.title")
        self.assertIsNotNone(state["analysis"])

    def test_live_failure_is_flagged(self) -> None:
        failed = ProcessReadResult(False, "live_layout_error", "signature not found")
        with mock.patch.object(self.server.service.reader, "read_squad", return_value=failed):
            state = self.call("/api/load/live", {})[1]
        self.assertEqual(state["status"]["key"], "status.live_failed")
        self.assertTrue(state["notice"]["always"])
        # A squad is always shown afterwards: the previous one, or the demo squad when none was loaded.
        self.assertIn(state["status"]["args"]["shown"], ({"$t": "status.kept_current"}, {"$t": "status.showing_demo"}))
        self.assertIsNotNone(state["analysis"])

    def test_calibration_input_is_validated(self) -> None:
        self.assertEqual(self.call("/api/calibrate", {"p1": {"age": 99}})[0], 400)

    def test_bug_url(self) -> None:
        url = self.call("/api/bug-url")[1]["url"]
        self.assertTrue(url.startswith("https://github.com/tacticfyhelp/Tacticfy/issues/new?"))


class LifecycleTest(unittest.TestCase):
    def test_quit_and_idle_watchdog(self) -> None:
        service = TacticfyService(ROOT / "config")
        server = create_server(0, service=service, web_root=ROOT / "web", idle_timeout=0.3, startup_grace=0.3)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        watchdog = threading.Thread(target=server.watchdog, kwargs={"interval": 0.1}, daemon=True)
        watchdog.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), "idle server did not stop itself")
        server.server_close()

        server = create_server(0, service=service, web_root=ROOT / "web")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        req = urllib.request.Request(server.origin + "/api/quit", data=b"{}",
                                     headers={"X-Tacticfy": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), "server did not stop after /api/quit")
        server.server_close()


if __name__ == "__main__":
    unittest.main()
