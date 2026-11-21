"""Application state behind the web API: the loaded squad, the user's settings and the last analysis.

All methods are thread-safe (one lock) because the HTTP server handles requests on worker threads.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import logging
from pathlib import Path
import tempfile
import threading
from typing import Any, Dict, List, Optional

from src import app_paths
from src.advisor.squad_classifier import SquadClassifier
from src.advisor.weakest_link import WeakestLinkAnalyzer
from src.engine.bench_optimizer import DEFAULT_BENCH_SIZE, SUPPORTED_BENCH_SIZES, BenchOptimizer
from src.engine.role_evaluator import RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer
from src.engine.training_advisor import TrainingAdvisor
from src.memory.aob_calibrator import AOBCalibrator, CalibrationPlayerInput
from src.memory.fallback_loader import generate_sample_squad, load_squad_from_file
from src.memory.process_reader import FM27ProcessReader, ProcessReadResult
from src.models.player import Player
from src.models.tactics import TACTICAL_STYLES
from src.web.serialize import analysis_json

log = logging.getLogger("tacticfy.service")

MAX_IMPORT_BYTES = 20 * 1024 * 1024
IMPORT_SUFFIXES = {".html", ".htm", ".csv", ".rtf", ".txt"}
LIVE_FAILURE_SOURCES = ("live_layout_error", "error", "empty_read")
AUTO_FORMATIONS = (("formation.auto_standard", SynergyOptimizer.FILTER_STANDARD),
                   ("formation.auto_all", SynergyOptimizer.FILTER_ALL))


class ApiError(Exception):
    """A user-facing error; ``key`` is a translation key, ``args`` fill its placeholders."""

    def __init__(self, key: str, status: int = 400, **args: Any) -> None:
        super().__init__(key)
        self.key = key
        self.status = status
        self.args_ = args


def t(key: str) -> Dict[str, str]:
    """Marks a status argument that the browser should translate itself."""
    return {"$t": key}


@dataclass
class Settings:
    style: str = TACTICAL_STYLES[0]
    formation: str = SynergyOptimizer.FILTER_STANDARD
    important: bool = False
    bench_size: int = DEFAULT_BENCH_SIZE


class TacticfyService:
    def __init__(self, config_dir: Optional[Path] = None, user_offsets: Optional[Path] = None) -> None:
        config_dir = Path(config_dir) if config_dir else app_paths.resource_path("config")
        self.user_offsets_path = Path(user_offsets) if user_offsets else app_paths.user_offsets_path()
        self.reader = FM27ProcessReader(config_dir / "offsets.json", self.user_offsets_path)
        self.evaluator = RoleEvaluator(config_dir / "roles_in_possession.json", config_dir / "roles_out_possession.json")
        self.optimizer = SynergyOptimizer(config_dir / "formations.json", self.evaluator)
        self.classifier = SquadClassifier(self.evaluator)
        self.weakest = WeakestLinkAnalyzer(self.evaluator)
        self.training = TrainingAdvisor(self.evaluator)
        self.bench = BenchOptimizer(self.evaluator)

        self.squad: List[Player] = []
        self.source = ""  # "live_ram" / "sample" / "import"
        self.settings = Settings()
        self.status: Dict[str, Any] = {"key": "status.ready", "kind": "muted", "args": {}}
        self._analysis: Optional[Dict[str, Any]] = None
        self._lock = threading.RLock()
        self._load_lock = threading.Lock()  # one fm.exe scan at a time

    # ------------------------------------------------------------------ metadata
    def meta(self) -> Dict[str, Any]:
        formations = [
            {"name": name, "category": form.category}
            for category in ("standard", "tactical_meta")
            for name, form in self.optimizer.formations.items()
            if form.category == category
        ]
        return {
            "app": app_paths.APP_NAME,
            "version": app_paths.APP_VERSION,
            "repo_url": app_paths.GITHUB_REPO_URL,
            "styles": list(TACTICAL_STYLES),
            "auto_formations": [{"key": key, "value": value} for key, value in AUTO_FORMATIONS],
            "formations": formations,
            "bench_sizes": list(SUPPORTED_BENCH_SIZES),
        }

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "settings": self.settings.__dict__.copy(),
                "status": self.status,
                "source": self.source,
                "player_count": len(self.squad),
                "analysis": self._analysis,
                "pool_key": self._pool_key(),
            }

    def _pool_key(self) -> str:
        if self.settings.formation == SynergyOptimizer.FILTER_STANDARD:
            return "pool.standard"
        if self.settings.formation == SynergyOptimizer.FILTER_ALL:
            return "pool.all"
        return "pool.locked"

    # ------------------------------------------------------------------ analysis
    def _recompute(self) -> None:
        if len(self.squad) < 11:
            self._analysis = None
            return
        s = self.settings
        result = self.optimizer.optimize(
            self.squad, tactical_style=s.style, big_match_mode=s.important, formation_filter=s.formation,
        )
        classified = self.classifier.classify(self.squad, result)
        weakest = self.weakest.analyze(result)
        training = self.training.recommend(self.squad, result)
        bench = self.bench.select_bench(self.squad, result, s.bench_size)
        self._analysis = analysis_json(self.squad, result, classified, weakest, training, bench)

    def update_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            s = self.settings
            if "style" in payload:
                if payload["style"] not in TACTICAL_STYLES:
                    raise ApiError("web.error.title")
                s.style = payload["style"]
            if "formation" in payload:
                value = payload["formation"]
                allowed = {SynergyOptimizer.FILTER_STANDARD, SynergyOptimizer.FILTER_ALL, *self.optimizer.formations}
                if value not in allowed:
                    raise ApiError("web.error.title")
                s.formation = value
            if "important" in payload:
                s.important = bool(payload["important"])
            if "bench_size" in payload:
                size = int(payload["bench_size"])
                if size not in SUPPORTED_BENCH_SIZES:
                    raise ApiError("web.error.title")
                s.bench_size = size
            self._recompute()
            return self.state()

    def set_lock(self, player_id: int, locked: bool) -> Dict[str, Any]:
        with self._lock:
            for p in self.squad:
                if p.player_id == player_id:
                    p.locked_starter = bool(locked)
                    break
            else:
                raise ApiError("web.no_squad", status=404)
            self._recompute()
            return self.state()

    # ------------------------------------------------------------------ loading
    def _set_squad(self, players: List[Player], source: str) -> None:
        self.squad = players
        self.source = source
        self._recompute()

    def load_sample(self) -> Dict[str, Any]:
        with self._lock:
            self._set_squad(generate_sample_squad(), "sample")
            self.status = {"key": "status.fallback", "kind": "warning", "args": {"message": ""}}
            return self.state()

    def load_live(self) -> Dict[str, Any]:
        """Read the squad from fm.exe; mirrors the desktop app's fallback rules. Returns state + a notice."""
        with self._load_lock:
            try:
                self.reader.reload_offsets()
                res = self.reader.read_squad()
            except Exception as exc:  # noqa: BLE001 - never let a reader crash take down the server
                res = ProcessReadResult(False, "error", f"Unexpected error while reading fm.exe: {exc}")
        log.log(logging.INFO if res.success else logging.WARNING,
                "Squad load: source=%s players=%d - %s", res.source, len(res.players), res.message)

        with self._lock:
            notice: Optional[Dict[str, Any]] = None
            if res.success and res.players:
                self._set_squad(res.players, "live_ram")
                self.status = {"key": "status.live_ok", "kind": "success", "args": {"message": res.message}}
                notice = {"kind": "success", "title": "dialog.live_loaded.title", "body": None,
                          "message": res.message}
            else:
                kept_current = bool(self.squad)
                if not self.squad:
                    self._set_squad(generate_sample_squad(), "sample")
                shown = t("status.kept_current" if kept_current else "status.showing_demo")
                if res.source in LIVE_FAILURE_SOURCES:
                    self.status = {"key": "status.live_failed", "kind": "error",
                                   "args": {"message": res.message, "shown": shown}}
                    notice = {"kind": "error", "title": "dialog.live_failed.title", "body": "dialog.live_failed.body",
                              "args": {"message": res.message, "shown": shown}, "always": True}
                else:
                    self.status = {"key": "status.fallback", "kind": "warning", "args": {"message": res.message}}
                    if res.source == "uncalibrated":
                        notice = {"kind": "warning", "title": "dialog.calibration.title",
                                  "body": "dialog.calibration.body", "args": {}, "action": "calibrate"}
                    else:
                        notice = {"kind": "info", "title": "dialog.not_loaded.title", "body": "dialog.not_loaded.body",
                                  "args": {"message": res.message}}
            state = self.state()
            state["notice"] = notice
            return state

    def import_file(self, filename: str, data_b64: str) -> Dict[str, Any]:
        name = Path(filename or "squad.html").name
        suffix = Path(name).suffix.lower()
        if suffix not in IMPORT_SUFFIXES:
            raise ApiError("dialog.import_error.title")
        try:
            data = base64.b64decode(data_b64, validate=True)
        except (binascii.Error, ValueError):
            raise ApiError("dialog.import_error.title")
        if len(data) > MAX_IMPORT_BYTES:
            raise ApiError("dialog.import_error.title", status=413)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"import{suffix}"
            path.write_bytes(data)
            try:
                players = load_squad_from_file(path)
            except Exception as exc:  # noqa: BLE001 - parser errors become a user-facing message
                log.warning("File import failed: %s", type(exc).__name__)
                raise ApiError("dialog.import_error.title", detail=str(exc))
        if len(players) < 11:
            raise ApiError("dialog.import_incomplete.body", count=len(players))
        log.info("Imported %d players from a file", len(players))
        with self._lock:
            self._set_squad(players, "import")
            self.status = {"key": "status.imported", "kind": "info", "args": {"count": len(players), "file": name}}
            return self.state()

    # ------------------------------------------------------------------ calibration
    @staticmethod
    def _calibration_input(raw: Dict[str, Any]) -> CalibrationPlayerInput:
        def num(key: str, lo: int, hi: int) -> int:
            try:
                value = int(raw.get(key))
            except (TypeError, ValueError):
                raise ApiError("web.calib.fail.title")
            if not lo <= value <= hi:
                raise ApiError("web.calib.fail.title")
            return value

        return CalibrationPlayerInput(
            name=str(raw.get("name") or "Player")[:80],
            age=num("age", 15, 45), ca=num("ca", 1, 200), pa=num("pa", 1, 200),
            pace=num("pace", 1, 20), finishing=num("finishing", 1, 20), passing=num("passing", 1, 20),
            tackling=num("tackling", 1, 20), decisions=num("decisions", 1, 20),
        )

    def calibrate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        p1 = self._calibration_input(payload.get("p1") or {})
        p2 = self._calibration_input(payload["p2"]) if payload.get("p2") else None
        with self._load_lock:
            res = AOBCalibrator(self.user_offsets_path).calibrate_live_process(p1, p2)
            if res.success:
                self.reader.reload_offsets()
        log.info("Calibration %s", "succeeded" if res.success else "failed")
        with self._lock:
            if res.success:
                self.status = {"key": "status.calibrated", "kind": "info", "args": {}}
            state = self.state()
            state["calibration"] = {"success": res.success, "message": res.message}
            return state
