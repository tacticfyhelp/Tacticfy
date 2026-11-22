"""Tab 1: Genie Scout style Squad & Hidden Attributes sortable table."""

from typing import Callable, Dict, List, Optional, Union

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.advisor.squad_classifier import has_real_finances
from src.engine.training_advisor import TrainingRecommendation
from src.models.tactics import PlayerClassification
from src.ui.i18n import EN, tr, tr_category, tr_focus, tr_intensity, training_reason
from src.ui.theme import LIGHT, Theme, category_color, to_qcolor


class SortableItem(QTableWidgetItem):
    """Table item that displays formatted text but sorts by an underlying numeric key."""

    def __init__(self, text: str, sort_key: Union[int, float, str]) -> None:
        super().__init__(text)
        self.sort_key = sort_key

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        if isinstance(other, SortableItem) and type(self.sort_key) is type(other.sort_key):
            return self.sort_key < other.sort_key
        if isinstance(other, SortableItem) and isinstance(self.sort_key, (int, float))                 and isinstance(other.sort_key, (int, float)):
            return self.sort_key < other.sort_key
        return super().__lt__(other)


class SquadTab(QWidget):
    """Displays full squad table with visible/hidden attributes, roles, training and starter locks."""

    # Column translation keys (display headers come from i18n).
    COLUMN_KEYS = [
        "squad.col.lock", "squad.col.exclude", "squad.col.name", "squad.col.age", "squad.col.pos", "squad.col.ca", "squad.col.pa",
        "squad.col.headroom", "squad.col.prof", "squad.col.amb", "squad.col.imp", "squad.col.pres",
        "squad.col.cons", "squad.col.inj", "squad.col.wage", "squad.col.best_ip", "squad.col.ip",
        "squad.col.best_oop", "squad.col.oop", "squad.col.role_focus", "squad.col.add_focus",
        "squad.col.intensity", "squad.col.status",
    ]
    # Backward-compatible English header list.
    COLUMNS = [EN[k] for k in COLUMN_KEYS]

    def __init__(
        self,
        on_lock_changed: Callable[[int, bool], None],
        parent=None,
        on_exclude_changed: Optional[Callable[[int, bool], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.on_lock_changed = on_lock_changed
        self.on_exclude_changed = on_exclude_changed
        # player_id -> (Lock XI checkbox, Exclude checkbox) of the rows currently shown.
        self._toggles: Dict[int, tuple] = {}
        self.theme: Theme = LIGHT
        self._classified: List[PlayerClassification] = []
        self._training: Dict[int, TrainingRecommendation] = {}
        self._build_ui()

    @classmethod
    def col(cls, key: str) -> int:
        return cls.COLUMN_KEYS.index(key)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(260)
        self.search_edit.setMaximumWidth(380)
        self.search_edit.textChanged.connect(self.apply_filter)
        header_row.addWidget(self.search_edit)
        self.count_label = QLabel("")
        header_row.addWidget(self.count_label)
        header_row.addStretch()
        self.header = QLabel()
        header_row.addWidget(self.header)
        layout.addLayout(header_row)

        self.table = QTableWidget(0, len(self.COLUMN_KEYS))
        self.table.horizontalHeader().setSortIndicator(self.col("squad.col.ca"), Qt.DescendingOrder)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        # Sorting physically reorders rows, so re-apply the filter once Qt has finished sorting.
        self.table.horizontalHeader().sortIndicatorChanged.connect(
            lambda *_: QTimer.singleShot(0, self.apply_filter)
        )
        self.retranslate()
        self.apply_theme(self.theme)

    def retranslate(self) -> None:
        self.table.setHorizontalHeaderLabels([tr(k) for k in self.COLUMN_KEYS])
        self.search_edit.setPlaceholderText(tr("squad.search"))
        self.header.setText(tr("squad.lock_hint"))
        if self._classified:
            self.update_squad(self._classified)
        else:
            self.apply_filter()

    def apply_filter(self, *_args) -> None:
        """Hide rows that do not contain every search term (case-insensitive, any text column)."""
        terms = self.search_edit.text().lower().split()
        total = self.table.rowCount()
        shown = 0
        for row in range(total):
            haystack = " ".join(
                self.table.item(row, col).text().lower()
                for col in range(2, self.table.columnCount())
                if self.table.item(row, col) is not None
            )
            visible = all(term in haystack for term in terms)
            self.table.setRowHidden(row, not visible)
            shown += visible
        self.count_label.setText(
            tr("squad.count_filtered", shown=shown, total=total) if terms else tr("squad.count", total=total)
        )

    def apply_theme(self, theme: Theme) -> None:
        """Re-colour the header and re-render rows so badge colours keep contrast in both themes."""
        self.theme = theme
        self.header.setStyleSheet(f"color: {theme.text_tertiary}; font-size: 11px;")
        self.count_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 11px;")
        if self._classified:
            self.update_squad(self._classified)

    def _checkbox_cell(self, row: int, col: int, checked: bool, tip: str) -> QCheckBox:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        chk = QCheckBox()
        chk.setChecked(checked)
        chk.setToolTip(tip)
        layout.addWidget(chk)
        self.table.setCellWidget(row, col, container)
        return chk

    def _on_toggle(self, player_id: int, kind: str, on: bool) -> None:
        """Lock XI and Exclude are mutually exclusive: checking one clears the other."""
        lock_chk, excl_chk = self._toggles.get(player_id, (None, None))
        other = excl_chk if kind == "lock" else lock_chk
        if on and other is not None and other.isChecked():
            other.blockSignals(True)
            other.setChecked(False)
            other.blockSignals(False)
            if kind == "lock" and self.on_exclude_changed:
                self.on_exclude_changed(player_id, False)
            elif kind == "exclude":
                self.on_lock_changed(player_id, False)
        if kind == "lock":
            self.on_lock_changed(player_id, on)
        elif self.on_exclude_changed:
            self.on_exclude_changed(player_id, on)

    def _intensity_color(self, intensity: str) -> str:
        t = self.theme
        return {"Double Intensity": t.status["success"], "Half Intensity": t.status["warning"]}.get(
            intensity, t.text_secondary
        )

    def update_squad(
        self,
        classified: List[PlayerClassification],
        training: Optional[List[TrainingRecommendation]] = None,
    ) -> None:
        """Populate the squad table with classified players (and their training plan when given)."""
        self._classified = list(classified)
        if training is not None:
            self._training = {r.player.player_id: r for r in training}
        t = self.theme
        bold = QFont()
        bold.setBold(True)
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(classified))
        show_wage = has_real_finances([c.player for c in classified])
        self.table.horizontalHeaderItem(self.col("squad.col.wage")).setToolTip(
            "" if show_wage else tr("squad.wage_unmapped")
        )
        intensity_order = {"Double Intensity": 0, "Normal": 1, "Half Intensity": 2}
        pos_order = ["GK", "DL", "DC", "DR", "WBL", "WBR", "DM", "ML", "MC", "MR", "AML", "AMC", "AMR", "ST"]

        self._toggles = {}
        dim = to_qcolor(t.text_tertiary)
        for row_idx, item in enumerate(classified):
            p = item.player
            rec = self._training.get(p.player_id)

            # Lock XI and Exclude checkboxes (mutually exclusive)
            lock_chk = self._checkbox_cell(row_idx, self.col("squad.col.lock"), p.locked_starter, tr("squad.lock_tip"))
            excl_chk = self._checkbox_cell(row_idx, self.col("squad.col.exclude"), p.excluded, tr("squad.exclude_tip"))
            lock_chk.toggled.connect(lambda on, pid=p.player_id: self._on_toggle(pid, "lock", on))
            excl_chk.toggled.connect(lambda on, pid=p.player_id: self._on_toggle(pid, "exclude", on))
            self._toggles[p.player_id] = (lock_chk, excl_chk)

            wage_txt = f"{p.wage_weekly:,}" if show_wage else "—"
            first_pos = p.positions[0] if p.positions else ""
            pos_key = pos_order.index(first_pos) if first_pos in pos_order else len(pos_order)

            role_focus = rec.role_focus if rec else "—"
            add_focus = tr_focus(rec.additional_focus) if rec else "—"
            intensity = tr_intensity(rec.intensity) if rec else "—"

            # (column key, display text, sort key, centered)
            values = [
                ("squad.col.name", p.name, p.name.split()[-1].lower() if p.name else "", False),
                ("squad.col.age", str(p.age), p.age, True),
                ("squad.col.pos", "/".join(p.positions), pos_key, False),
                ("squad.col.ca", str(p.hidden.ca), p.hidden.ca, True),
                ("squad.col.pa", str(p.hidden.pa), p.hidden.pa, True),
                ("squad.col.headroom", str(p.pa_ca_delta), p.pa_ca_delta, True),
                ("squad.col.prof", str(p.hidden.professionalism), p.hidden.professionalism, True),
                ("squad.col.amb", str(p.hidden.ambition), p.hidden.ambition, True),
                ("squad.col.imp", str(p.hidden.important_matches), p.hidden.important_matches, True),
                ("squad.col.pres", str(p.hidden.pressure), p.hidden.pressure, True),
                ("squad.col.cons", str(p.hidden.consistency), p.hidden.consistency, True),
                ("squad.col.inj", str(p.hidden.injury_proneness), p.hidden.injury_proneness, True),
                ("squad.col.wage", wage_txt, p.wage_weekly, True),
                ("squad.col.best_ip", item.best_ip_role, item.best_ip_role, False),
                ("squad.col.ip", f"{item.best_ip_score:.1f}", float(item.best_ip_score), True),
                ("squad.col.best_oop", item.best_oop_role, item.best_oop_role, False),
                ("squad.col.oop", f"{item.best_oop_score:.1f}", float(item.best_oop_score), True),
                ("squad.col.role_focus", role_focus, role_focus, False),
                ("squad.col.add_focus", add_focus, add_focus, False),
                ("squad.col.intensity", intensity, intensity_order.get(rec.intensity, 3) if rec else 3, True),
                ("squad.col.status", tr_category(item.category), item.category, False),
            ]

            for key, text, sort_key, centered in values:
                cell = SortableItem(text, sort_key)
                if centered:
                    cell.setTextAlignment(Qt.AlignCenter)

                if key == "squad.col.status":
                    cell.setForeground(to_qcolor(category_color(t, item.category)))
                    cell.setFont(bold)
                elif key == "squad.col.prof" and p.hidden.professionalism <= 9:
                    cell.setForeground(to_qcolor(t.categories["sell_high"]))
                    cell.setFont(bold)
                elif key == "squad.col.inj" and p.hidden.injury_proneness >= 14:
                    cell.setForeground(to_qcolor(t.categories["offload"]))
                    cell.setFont(bold)
                elif key == "squad.col.intensity" and rec is not None:
                    cell.setForeground(to_qcolor(self._intensity_color(rec.intensity)))
                    cell.setFont(bold)
                if rec is not None and key in ("squad.col.role_focus", "squad.col.add_focus", "squad.col.intensity"):
                    cell.setToolTip(training_reason(rec))

                if p.excluded:
                    cell.setForeground(dim)
                    font = cell.font()
                    font.setStrikeOut(key == "squad.col.name")
                    cell.setFont(font)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, self.col(key), cell)

        # Re-enabling sorting re-applies the current sort indicator (default: CA descending).
        self.table.setSortingEnabled(True)
        self.apply_filter()
