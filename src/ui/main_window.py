"""Main PySide6 window coordinating RAM loading, optimization, theming, language and all 3 tabs."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QSizePolicy,
    QWidget,
)

import logging

from src import app_paths
from src.advisor.squad_classifier import SquadClassifier
from src.advisor.weakest_link import WeakestLinkAnalyzer
from src.engine.bench_optimizer import DEFAULT_BENCH_SIZE, BenchOptimizer, BenchPlan
from src.engine.role_evaluator import RoleEvaluator
from src.engine.synergy_optimizer import SynergyOptimizer
from src.engine.training_advisor import TrainingAdvisor
from src.memory.fallback_loader import generate_sample_squad, load_squad_from_file
from src.memory.process_reader import FM27ProcessReader, ProcessReadResult
from src.models.player import Player
from src.models.tactics import TACTICAL_STYLES, LineupResult
from src.ui import i18n
from src.ui.advisor_tab import AdvisorTab
from src.ui.calibration_dialog import CalibrationDialog
from src.ui.i18n import LANG_BUTTON_TEXT, tr
from src.ui.squad_tab import SquadTab
from src.ui.tactics_tab import TacticsTab
from src.ui.theme import DARK, LIGHT, Theme, build_stylesheet
from src.bug_report import build_issue_url

log = logging.getLogger("tacticfy.ui")

# Formation combo "auto" entries: (translation key, optimizer filter)
AUTO_ENTRIES = (("formation.auto_standard", SynergyOptimizer.FILTER_STANDARD),
                ("formation.auto_all", SynergyOptimizer.FILTER_ALL))
FORMATION_CATEGORIES = ("standard", "tactical_meta")


class ElidedLabel(QLabel):
    """Single-line label that elides with "…" instead of widening the window; full text in tooltip."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        super().setText(text)
        self.setToolTip(text)
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        # Never ask for more than the space the owner allows (see MainWindow._fit_status_label).
        full = self.fontMetrics().horizontalAdvance(self.text()) + 16
        return QSize(min(full, self.maximumWidth()), super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(40, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, rect.width())
        painter.drawText(rect, int(self.alignment()) | Qt.AlignVCenter, elided)


class SquadLoadWorker(QObject):
    """Runs the (multi-second) fm.exe RAM scan off the UI thread."""

    finished = Signal(object)  # ProcessReadResult

    def __init__(self, reader: FM27ProcessReader) -> None:
        super().__init__()
        self.reader = reader

    @Slot()
    def run(self) -> None:
        try:
            self.reader.reload_offsets()
            result = self.reader.read_squad()
        except Exception as exc:  # noqa: BLE001 - never let a worker exception vanish silently
            result = ProcessReadResult(False, "error", f"Unexpected error while reading fm.exe: {exc}")
        self.finished.emit(result)


class MainWindow(QMainWindow):
    """Top-level FM27 Scout & Tactical Synergy Optimizer window."""

    def __init__(self, project_root: Optional[Path] = None) -> None:
        super().__init__()
        # Read-only bundle root (sys._MEIPASS inside the frozen .exe, the checkout otherwise).
        self.project_root = Path(project_root) if project_root else app_paths.bundle_root()
        self.config_dir = self.project_root / "config"
        icon_file = self.project_root.joinpath(*app_paths.ICON_RELATIVE_PATH)
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))

        # Bundled offsets + per-user calibration overlay (%LOCALAPPDATA%\Tacticfy when installed).
        self.user_offsets_path = app_paths.user_offsets_path()
        self.reader = FM27ProcessReader(self.config_dir / "offsets.json", self.user_offsets_path)
        self.evaluator = RoleEvaluator(
            self.config_dir / "roles_in_possession.json",
            self.config_dir / "roles_out_possession.json",
        )
        self.optimizer = SynergyOptimizer(self.config_dir / "formations.json", self.evaluator)
        self.classifier = SquadClassifier(self.evaluator)
        self.weakest_analyzer = WeakestLinkAnalyzer(self.evaluator)
        self.training_advisor = TrainingAdvisor(self.evaluator)
        self.bench_optimizer = BenchOptimizer(self.evaluator)

        self.squad: List[Player] = []
        self.last_result: Optional[LineupResult] = None
        self.bench_size = DEFAULT_BENCH_SIZE
        self._load_thread: Optional[QThread] = None
        self._load_worker: Optional[SquadLoadWorker] = None
        self._load_interactive = False
        self.theme: Theme = LIGHT
        self.lang = i18n.current_language()
        # Status line source: (translation key, args) so it can be re-rendered on a language switch.
        self._status_src = ("status.ready", {})
        self._status_kind = "muted"
        self._pool_key = ""
        self.setMinimumSize(1024, 620)
        self.resize(1240, 720)
        self._build_ui()
        self.apply_theme(LIGHT)
        self.apply_language(self.lang)

    # ------------------------------------------------------------------ UI construction
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("canvas")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Single compact toolbar row
        toolbar_card = QFrame()
        toolbar_card.setObjectName("toolbarCard")
        self.toolbar_card = toolbar_card
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(6, 5, 6, 5)
        toolbar.setSpacing(4)

        self.load_btn = QPushButton()
        self.load_btn.setObjectName("successButton")
        self.load_btn.clicked.connect(lambda: self.on_load_clicked(interactive=True))
        toolbar.addWidget(self.load_btn)

        self.calibrate_btn = QPushButton()
        self.calibrate_btn.clicked.connect(self.on_calibrate_clicked)
        toolbar.addWidget(self.calibrate_btn)

        self.import_btn = QPushButton()
        self.import_btn.clicked.connect(self.on_import_clicked)
        toolbar.addWidget(self.import_btn)

        toolbar.addSpacing(6)
        self.style_label = self._toolbar_label("")
        toolbar.addWidget(self.style_label)
        self.style_combo = QComboBox()
        for style in TACTICAL_STYLES:  # display text is translated, data stays the English engine key
            self.style_combo.addItem(style, style)
        self.style_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.style_combo.setMinimumContentsLength(15)
        self.style_combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.style_combo.setMaximumWidth(190)
        toolbar.addWidget(self.style_combo)

        toolbar.addSpacing(4)
        self.formation_label = self._toolbar_label("")
        toolbar.addWidget(self.formation_label)
        self.formation_combo = QComboBox()
        for key, data in AUTO_ENTRIES:
            self.formation_combo.addItem(tr(key), data)
        self.formation_combo.insertSeparator(self.formation_combo.count())
        for category in FORMATION_CATEGORIES:
            for name, form in self.optimizer.formations.items():
                if form.category == category:
                    self.formation_combo.addItem(name, name)
        # Compact closed width; the popup still shows every full label.
        self.formation_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.formation_combo.setMinimumContentsLength(23)
        # Grow into spare toolbar space (full label at 1240 px+), shrink to the minimum at 1024 px.
        self.formation_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.formation_combo.setMaximumWidth(290)
        toolbar.addWidget(self.formation_combo, 4)

        toolbar.addSpacing(4)
        self.big_match_chk = QCheckBox()
        toolbar.addWidget(self.big_match_chk)

        toolbar.addStretch(1)

        self.optimize_btn = QPushButton()
        self.optimize_btn.setObjectName("primaryButton")
        self.optimize_btn.clicked.connect(self.run_optimization)
        toolbar.addWidget(self.optimize_btn)

        self.theme_btn = QPushButton()
        self.theme_btn.clicked.connect(self.toggle_theme)
        toolbar.addWidget(self.theme_btn)

        self.lang_btn = QPushButton(LANG_BUTTON_TEXT)
        self.lang_btn.setObjectName("langButton")
        self.lang_btn.setCheckable(True)  # checked = Hebrew
        self.lang_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lang_btn.setCursor(Qt.PointingHandCursor)
        self.lang_btn.toggled.connect(lambda he: self.apply_language("he" if he else "en"))
        toolbar.addWidget(self.lang_btn)

        self.report_btn = QPushButton()
        self.report_btn.setObjectName("reportButton")
        self.report_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.report_btn.setCursor(Qt.PointingHandCursor)
        self.report_btn.clicked.connect(self.on_report_bug_clicked)
        toolbar.addWidget(self.report_btn)

        root.addWidget(toolbar_card)

        # Instant re-optimization when any tactical control changes.
        self.style_combo.currentIndexChanged.connect(self._on_controls_changed)
        self.formation_combo.currentIndexChanged.connect(self._on_controls_changed)
        self.big_match_chk.stateChanged.connect(self._on_controls_changed)

        # Status line sits beside the tab pills to save a row.
        self.status_label = ElidedLabel("")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Tabs (segmented pill)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tactics_tab = TacticsTab(on_bench_size_changed=self.on_bench_size_changed)
        self.squad_tab = SquadTab(self.on_player_lock_changed)
        self.advisor_tab = AdvisorTab()
        for page in (self.tactics_tab, self.squad_tab, self.advisor_tab):
            page.setObjectName("tabPage")
            self.tabs.addTab(page, "")
        self.tabs.setCornerWidget(self.status_label, Qt.TopRightCorner)
        root.addWidget(self.tabs, 1)

    def _fit_status_label(self) -> None:
        """Give the status line only the width left beside the tab pills (no tab scroll arrows)."""
        free = self.tabs.width() - self.tabs.tabBar().sizeHint().width() - 12
        self.status_label.setMaximumWidth(max(40, free))
        self.status_label.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_status_label()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_status_label()

    @staticmethod
    def _toolbar_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("toolbarLabel")
        return lbl

    # ------------------------------------------------------------------ theming
    def apply_theme(self, theme: Theme) -> None:
        """Apply Apple Light / Dark Glass to the window and every tab."""
        self.theme = theme
        self.setStyleSheet(build_stylesheet(theme))
        self.theme_btn.setText(tr("toolbar.theme", name=tr(f"theme.{theme.name}")))
        self.tactics_tab.apply_theme(theme)
        self.squad_tab.apply_theme(theme)
        self.advisor_tab.apply_theme(theme)
        self._render_status()

    def toggle_theme(self) -> None:
        self.apply_theme(DARK if self.theme is LIGHT else LIGHT)

    # ------------------------------------------------------------------ language
    def apply_language(self, lang: str) -> None:
        """Switch every UI string between English and Hebrew and flip the layout direction."""
        i18n.set_language(lang)
        self.lang = lang
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        self.setWindowTitle(f"Tacticfy {app_paths.APP_VERSION}  –  {tr('app.title')}")

        self.lang_btn.blockSignals(True)
        self.lang_btn.setChecked(lang == "he")
        self.lang_btn.blockSignals(False)
        self.lang_btn.setToolTip(tr("toolbar.lang_tip"))

        self.load_btn.setText(tr("toolbar.scanning") if self.is_loading() else tr("toolbar.load"))
        self.load_btn.setToolTip(tr("toolbar.load_tip"))
        self.calibrate_btn.setText(tr("toolbar.calibrate"))
        self.calibrate_btn.setToolTip(tr("toolbar.calibrate_tip"))
        self.import_btn.setText(tr("toolbar.import"))
        self.import_btn.setToolTip(tr("toolbar.import_tip"))
        self.style_label.setText(tr("toolbar.style"))
        self.formation_label.setText(tr("toolbar.formation"))
        self.big_match_chk.setText(tr("toolbar.important"))
        self.big_match_chk.setToolTip(tr("toolbar.important_tip"))
        self.optimize_btn.setText(tr("toolbar.optimize"))
        self.optimize_btn.setToolTip(tr("toolbar.optimize_tip"))
        self.theme_btn.setText(tr("toolbar.theme", name=tr(f"theme.{self.theme.name}")))
        self.theme_btn.setToolTip(tr("toolbar.theme_tip"))
        self.report_btn.setText(tr("toolbar.report_bug"))
        self.report_btn.setToolTip(tr("toolbar.report_bug_tip"))

        # Combo display texts only; item data (engine keys) never changes.
        for i in range(self.style_combo.count()):
            self.style_combo.setItemText(i, i18n.tr_style(self.style_combo.itemData(i)))
        for i, (key, _) in enumerate(AUTO_ENTRIES):
            self.formation_combo.setItemText(i, tr(key))
        for i in range(self.formation_combo.count()):
            name = self.formation_combo.itemData(i)
            form = self.optimizer.formations.get(name) if isinstance(name, str) else None
            if form is not None:
                self.formation_combo.setItemText(
                    i, f"{name}  ·  {tr('formation.category.' + form.category)}"
                )
        self.formation_combo.view().setMinimumWidth(self.formation_combo.view().sizeHintForColumn(0) + 24)

        for i, key in enumerate(("tab.tactics", "tab.squad", "tab.advisor")):
            self.tabs.setTabText(i, tr(key))
        for tab in (self.tactics_tab, self.squad_tab, self.advisor_tab):
            tab.retranslate()
        if self.last_result is not None:
            self.tactics_tab.set_pool_label(tr(self._pool_key) if self._pool_key else "")
        self._render_status()

    # ------------------------------------------------------------------ status
    def _set_status(self, key: str, kind: str = "muted", **args) -> None:
        """Set the status line from a translation key; ``kind`` is muted / info / success / warning / error."""
        self._status_src = (key, args)
        self._status_kind = kind
        self._render_status()

    def _render_status(self) -> None:
        if not hasattr(self, "status_label"):
            return
        key, args = self._status_src
        kind = self._status_kind
        color = self.theme.status.get(kind, self.theme.status["muted"])
        weight = "500" if kind == "muted" else "600"
        self.status_label.setText(tr(key, **args))
        self._fit_status_label()
        self.status_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: {weight}; padding: 0 2px 0 12px;")

    # ------------------------------------------------------------------ loading
    def is_loading(self) -> bool:
        """True while a background fm.exe scan is in progress."""
        return self._load_thread is not None

    def on_load_clicked(self, interactive: bool = True) -> None:
        """Start a non-blocking squad load; results arrive in _on_load_finished."""
        if self.is_loading():
            return
        self._load_interactive = interactive
        thread = QThread(self)
        worker = SquadLoadWorker(self.reader)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_load_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._load_thread, self._load_worker = thread, worker
        self._set_loading_ui(True)
        thread.start()

    def _set_loading_ui(self, loading: bool) -> None:
        for btn in (self.load_btn, self.calibrate_btn, self.import_btn, self.optimize_btn):
            btn.setEnabled(not loading)
        if loading:
            self.load_btn.setText(tr("toolbar.scanning"))
            self._set_status("status.scanning", "info")
            QApplication.setOverrideCursor(Qt.BusyCursor)
        else:
            self.load_btn.setText(tr("toolbar.load"))
            QApplication.restoreOverrideCursor()

    @Slot(object)
    def _on_load_finished(self, res: ProcessReadResult) -> None:
        self._load_thread, self._load_worker = None, None
        self._set_loading_ui(False)
        interactive = self._load_interactive
        # Reader messages are technical (counts, offsets, errors) and contain no player data.
        log.log(logging.INFO if res.success else logging.WARNING,
                "Squad load: source=%s players=%d - %s", res.source, len(res.players), res.message)

        if res.success and res.players:
            self.squad = res.players
            self._set_status("status.live_ok", "success", message=res.message)
            self.run_optimization()
            if interactive:
                QMessageBox.information(self, tr("dialog.live_loaded.title"), res.message)
            return

        live_failed = res.source in ("live_layout_error", "error", "empty_read")
        kept_current = bool(self.squad)
        if not self.squad:
            self.squad = generate_sample_squad()

        shown = tr("status.kept_current") if kept_current else tr("status.showing_demo")
        if live_failed:
            self._set_status("status.live_failed", "error", message=res.message, shown=shown)
        else:
            self._set_status("status.fallback", "warning", message=res.message)
        self.run_optimization()

        if live_failed:
            # fm.exe IS running, so never pretend the demo data is the user's squad - always warn.
            QMessageBox.warning(
                self, tr("dialog.live_failed.title"), tr("dialog.live_failed.body", message=res.message, shown=shown)
            )
            return

        if interactive:
            if res.source == "uncalibrated":
                reply = QMessageBox.question(
                    self, tr("dialog.calibration.title"), tr("dialog.calibration.body"),
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self.on_calibrate_clicked()
            else:
                QMessageBox.information(
                    self, tr("dialog.not_loaded.title"), tr("dialog.not_loaded.body", message=res.message)
                )

    def closeEvent(self, event) -> None:
        if self._load_thread is not None:
            self._load_thread.quit()
            self._load_thread.wait(15000)
        super().closeEvent(event)

    def on_calibrate_clicked(self) -> None:
        dlg = CalibrationDialog(self.user_offsets_path, self)
        if dlg.exec():
            self.reader.reload_offsets()
            log.info("Calibration saved to the user offsets overlay")
            self._set_status("status.calibrated", "info")

    def on_report_bug_clicked(self) -> None:
        """Open a pre-filled GitHub issue (OS, app version, scrubbed log tail) in the default browser."""
        log.info("Report Bug opened")
        QDesktopServices.openUrl(QUrl(build_issue_url(), QUrl.TolerantMode))

    def on_import_clicked(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("dialog.import.title"), str(Path.home()), tr("dialog.import.filter")
        )
        if not file_path:
            return
        try:
            players = load_squad_from_file(Path(file_path))
            if len(players) < 11:
                QMessageBox.warning(
                    self, tr("dialog.import_incomplete.title"), tr("dialog.import_incomplete.body", count=len(players))
                )
                return
            self.squad = players
            self._set_status("status.imported", "info", count=len(players), file=Path(file_path).name)
            log.info("Imported %d players from a file", len(players))
            self.run_optimization()
        except Exception as exc:
            log.warning("File import failed: %s", type(exc).__name__)
            QMessageBox.critical(self, tr("dialog.import_error.title"), str(exc))

    def on_player_lock_changed(self, player_id: int, is_locked: bool) -> None:
        for p in self.squad:
            if p.player_id == player_id:
                p.locked_starter = is_locked
                break

    # ------------------------------------------------------------------ optimization
    def _on_controls_changed(self, *_args) -> None:
        """Style / formation / big-match changes re-optimize instantly once a squad is loaded."""
        if len(self.squad) >= 11 and not self.is_loading():
            self.run_optimization()

    def current_formation_filter(self) -> str:
        data = self.formation_combo.currentData()
        return data if isinstance(data, str) and data else SynergyOptimizer.FILTER_STANDARD

    def current_style(self) -> str:
        data = self.style_combo.currentData()
        return data if isinstance(data, str) and data else TACTICAL_STYLES[0]

    def compute_bench(self) -> Optional[BenchPlan]:
        if self.last_result is None:
            return None
        return self.bench_optimizer.select_bench(self.squad, self.last_result, self.bench_size)

    def on_bench_size_changed(self, size: int) -> None:
        self.bench_size = size
        self.tactics_tab.update_bench(self.compute_bench())

    def run_optimization(self) -> None:
        if len(self.squad) < 11:
            # Nothing usable yet: kick off a background load (it re-runs optimization when done).
            self.on_load_clicked(interactive=False)
            return

        formation_filter = self.current_formation_filter()
        result = self.optimizer.optimize(
            self.squad,
            tactical_style=self.current_style(),
            big_match_mode=self.big_match_chk.isChecked(),
            formation_filter=formation_filter,
        )
        self.last_result = result
        classified = self.classifier.classify(self.squad, result)
        weakest = self.weakest_analyzer.analyze(result)
        training = self.training_advisor.recommend(self.squad, result)

        if formation_filter == SynergyOptimizer.FILTER_STANDARD:
            self._pool_key = "pool.standard"
        elif formation_filter == SynergyOptimizer.FILTER_ALL:
            self._pool_key = "pool.all"
        else:
            self._pool_key = "pool.locked"

        self.tactics_tab.update_tactics(result, tr(self._pool_key), training=training)
        self.tactics_tab.update_bench(self.compute_bench())
        self.squad_tab.update_squad(classified, training)
        self.advisor_tab.update_advisor(classified, weakest, training)
