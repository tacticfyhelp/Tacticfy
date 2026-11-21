"""Guided In-Game Editor (IGE) memory offset calibration dialog."""

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.memory.aob_calibrator import AOBCalibrator, CalibrationPlayerInput


class CalibrationDialog(QDialog):
    """Wizard to recalibrate fm.exe RAM offsets using In-Game Editor values."""

    def __init__(self, offsets_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FM27 In-Game Editor (IGE) Memory Calibration")
        self.resize(560, 520)
        self.calibrator = AOBCalibrator(offsets_path)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Enter exact values from your FM27 In-Game Editor for 1 or 2 players in your current save.\n"
            "The AOB scanner will locate the player struct in fm.exe RAM and save the result as your personal offsets override."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.p1_inputs = self._create_player_group("Player 1 (Required)", default_name="Starter #1")
        self.p2_inputs = self._create_player_group("Player 2 (Optional Cross-Validation)", default_name="Starter #2")
        layout.addWidget(self.p1_inputs["group"])
        layout.addWidget(self.p2_inputs["group"])

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("Scan fm.exe & Calibrate")
        self.scan_btn.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 8px 14px;")
        self.scan_btn.clicked.connect(self._run_calibration)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        btn_row.addWidget(self.scan_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _create_player_group(title: str, default_name: str) -> dict:
        group = QGroupBox(title)
        form = QFormLayout(group)

        name_edit = QLineEdit(default_name)
        age_spin = QSpinBox()
        age_spin.setRange(15, 45)
        age_spin.setValue(22)

        ca_spin = QSpinBox()
        ca_spin.setRange(1, 200)
        ca_spin.setValue(145)

        pa_spin = QSpinBox()
        pa_spin.setRange(1, 200)
        pa_spin.setValue(165)

        pace_spin = QSpinBox()
        pace_spin.setRange(1, 20)
        pace_spin.setValue(15)

        fin_spin = QSpinBox()
        fin_spin.setRange(1, 20)
        fin_spin.setValue(12)

        pas_spin = QSpinBox()
        pas_spin.setRange(1, 20)
        pas_spin.setValue(14)

        tac_spin = QSpinBox()
        tac_spin.setRange(1, 20)
        tac_spin.setValue(13)

        dec_spin = QSpinBox()
        dec_spin.setRange(1, 20)
        dec_spin.setValue(14)

        form.addRow("Player Name:", name_edit)
        form.addRow("Age:", age_spin)
        form.addRow("Current Ability (CA):", ca_spin)
        form.addRow("Potential Ability (PA):", pa_spin)
        form.addRow("Pace (1-20):", pace_spin)
        form.addRow("Finishing (1-20):", fin_spin)
        form.addRow("Passing (1-20):", pas_spin)
        form.addRow("Tackling (1-20):", tac_spin)
        form.addRow("Decisions (1-20):", dec_spin)

        return {
            "group": group,
            "name": name_edit,
            "age": age_spin,
            "ca": ca_spin,
            "pa": pa_spin,
            "pace": pace_spin,
            "finishing": fin_spin,
            "passing": pas_spin,
            "tackling": tac_spin,
            "decisions": dec_spin,
        }

    @staticmethod
    def _extract_input(widgets: dict) -> CalibrationPlayerInput:
        return CalibrationPlayerInput(
            name=widgets["name"].text().strip() or "Player",
            age=widgets["age"].value(),
            ca=widgets["ca"].value(),
            pa=widgets["pa"].value(),
            pace=widgets["pace"].value(),
            finishing=widgets["finishing"].value(),
            passing=widgets["passing"].value(),
            tackling=widgets["tackling"].value(),
            decisions=widgets["decisions"].value(),
        )

    def _run_calibration(self) -> None:
        p1 = self._extract_input(self.p1_inputs)
        p2: Optional[CalibrationPlayerInput] = None
        if self.p2_inputs["name"].text().strip():
            p2 = self._extract_input(self.p2_inputs)

        res = self.calibrator.calibrate_live_process(p1, p2)
        if res.success:
            QMessageBox.information(self, "Calibration Complete", res.message)
            self.accept()
        else:
            QMessageBox.warning(self, "Calibration Failed", res.message)
