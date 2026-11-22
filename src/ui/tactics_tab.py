"""Tab 1: Dual side-by-side IP & OOP Pitch Visualizer, Team/Player Instructions and Matchday Bench."""

from dataclasses import dataclass
from html import escape
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.engine.bench_optimizer import DEFAULT_BENCH_SIZE, SUPPORTED_BENCH_SIZES, BenchPlan
from src.engine.instructions_gen import InstructionsGenerator
from src.engine.training_advisor import TrainingRecommendation
from src.models.tactics import MATCHUPS, SCORING_MODES, AssignedSlot, LineupResult, SlotExplanation
from src.ui import i18n
from src.ui.i18n import (
    bidi_row, cell_pad, ltr, table_open, tr, tr_attr, tr_button, tr_driver, tr_fitness, tr_focus, tr_intensity,
    tr_matchup, tr_reason, tr_scoring, tr_style, training_reason,
)
from src.ui.theme import FONT_FAMILY, LIGHT, Theme, to_qcolor


@dataclass(frozen=True)
class NodeGeometry:
    """Size of one player node (circle + label pill), adapted to the available pitch space."""

    radius: float
    label_w: float
    label_h: float
    gap: float
    two_line: bool  # False = compact mode: surname only, no role line

    @property
    def block_h(self) -> float:
        return 2 * self.radius + self.gap + self.label_h


class PitchCanvas(QWidget):
    """Draws a football pitch with players in a clean, symmetric formation shape."""

    BASE_RADIUS = 15.0
    BASE_LABEL_H = 30.0
    COMPACT_LABEL_H = 17.0
    LABEL_GAP = 3.0
    NODE_GAP = 5.0
    TOP_PAD = 6.0       # clearance between the attacking goal line and the highest circle
    BOTTOM_PAD = 12.0   # clearance between the GK label and the bottom border
    MAX_LABEL_W = 112.0
    MIN_LABEL_W = 54.0
    # Fallback only (slots without display coords): keep L/R slots off the centre line.
    CENTER_SPLIT = 14.0
    STRIPES = 10

    def __init__(
        self,
        title: str,
        phase: str,
        on_slot_selected: Callable[[AssignedSlot], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.phase = phase
        self.on_slot_selected = on_slot_selected
        self.slots: List[AssignedSlot] = []
        self.dropoff_map: dict = {}
        self.comparison_mode: bool = False
        self.theme: Theme = LIGHT
        self._hit_boxes: List[Tuple[QRectF, AssignedSlot]] = []
        self.setMinimumSize(280, 320)
        self.setCursor(Qt.PointingHandCursor)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def set_data(
        self,
        slots: List[AssignedSlot],
        dropoff_map: Optional[dict] = None,
        comparison_mode: bool = False,
    ) -> None:
        self.slots = slots
        self.dropoff_map = dropoff_map or {}
        self.comparison_mode = comparison_mode
        self.update()

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        for rect, slot in self._hit_boxes:
            if rect.contains(pos):
                self.on_slot_selected(slot)
                break
        super().mousePressEvent(event)

    # ------------------------------------------------------------------ layout
    def display_coords(self, slot: AssignedSlot) -> Tuple[float, float]:
        """Symmetric formation coordinates for this phase (role coordinates as a fallback)."""
        shape = slot.ip_display if self.phase == "IP" else slot.oop_display
        if shape is not None:
            return float(shape[0]), float(shape[1])
        x, y = slot.ip_coords if self.phase == "IP" else slot.oop_coords
        if slot.side == "L":
            x = min(x, 50.0 - self.CENTER_SPLIT)
        elif slot.side == "R":
            x = max(x, 50.0 + self.CENTER_SPLIT)
        return x, y

    def pitch_rect(self) -> QRectF:
        margin = 6
        top_pad = 24
        return QRectF(margin, top_pad, self.width() - 2 * margin, self.height() - top_pad - margin)

    def _choose_geometry(self, pitch_rect: QRectF, coords: List[Tuple[float, float]]) -> NodeGeometry:
        """Largest node size whose rows and columns fit the pitch without touching."""
        # Tightest horizontal spacing between team-mates on the same line (fraction of width).
        min_dx = 1.0
        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                if abs(coords[i][1] - coords[j][1]) <= 3.0:
                    min_dx = min(min_dx, abs(coords[i][0] - coords[j][0]) / 100.0 or 1.0)
        label_w = self.MIN_LABEL_W
        lw = self.MAX_LABEL_W
        while lw >= self.MIN_LABEL_W:
            inner_w = pitch_rect.width() - lw - 12
            if min_dx * inner_w >= lw + self.NODE_GAP:
                label_w = lw
                break
            lw -= 2

        # Tightest vertical spacing between nodes whose labels could actually collide horizontally.
        inner_w = pitch_rect.width() - label_w - 12
        min_dy = 1.0
        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                dx_px = abs(coords[i][0] - coords[j][0]) / 100.0 * inner_w
                dy = abs(coords[i][1] - coords[j][1]) / 100.0
                if dx_px < label_w + self.NODE_GAP and dy > 0:
                    min_dy = min(min_dy, dy)

        def fits(radius: float, label_h: float) -> bool:
            block = 2 * radius + self.LABEL_GAP + label_h
            inner_h = pitch_rect.height() - (radius + self.TOP_PAD) - (radius + self.LABEL_GAP + label_h + self.BOTTOM_PAD)
            return inner_h > 0 and min_dy * inner_h >= block + self.NODE_GAP

        scale = 1.0
        while scale >= 0.8:  # full two-line labels (surname + role)
            if fits(self.BASE_RADIUS * scale, self.BASE_LABEL_H * scale):
                return NodeGeometry(self.BASE_RADIUS * scale, label_w, self.BASE_LABEL_H * scale, self.LABEL_GAP, True)
            scale -= 0.02
        scale = 0.9
        while scale > 0.6:  # compact: surname only
            if fits(self.BASE_RADIUS * scale, self.COMPACT_LABEL_H):
                return NodeGeometry(self.BASE_RADIUS * scale, label_w, self.COMPACT_LABEL_H, self.LABEL_GAP, False)
            scale -= 0.02
        return NodeGeometry(self.BASE_RADIUS * 0.6, label_w, self.COMPACT_LABEL_H, self.LABEL_GAP, False)

    def layout_nodes(self, pitch_rect: QRectF) -> Tuple[List[QPointF], NodeGeometry]:
        """Place every node inside a padded inner rect; resolve any remaining overlap."""
        coords = [self.display_coords(s) for s in self.slots]
        geo = self._choose_geometry(pitch_rect, coords)
        r = geo.radius
        half_w = geo.label_w / 2.0 + 6

        top_pad = r + self.TOP_PAD
        bottom_pad = r + geo.gap + geo.label_h + self.BOTTOM_PAD
        inner = QRectF(
            pitch_rect.left() + half_w,
            pitch_rect.top() + top_pad,
            max(1.0, pitch_rect.width() - 2 * half_w),
            max(1.0, pitch_rect.height() - top_pad - bottom_pad),
        )

        side_rank = {"L": 0, "C": 1, "R": 2}
        pts = [
            [inner.left() + (x / 100.0) * inner.width(), inner.top() + (1.0 - y / 100.0) * inner.height()]
            for x, y in coords
        ]

        # Safety net for extreme sizes: push touching nodes apart (symmetric shapes rarely need it).
        min_dx = geo.label_w + self.NODE_GAP
        min_dy = geo.block_h + self.NODE_GAP
        for _ in range(80):
            moved = False
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    dx = pts[j][0] - pts[i][0]
                    dy = pts[j][1] - pts[i][1]
                    over_x = min_dx - abs(dx)
                    over_y = min_dy - abs(dy)
                    if over_x <= 0 or over_y <= 0:
                        continue
                    moved = True
                    if over_x <= over_y * 1.6:
                        if abs(dx) < 0.5:
                            rank_i = side_rank.get(self.slots[i].side, 1)
                            rank_j = side_rank.get(self.slots[j].side, 1)
                            sign = 1.0 if rank_j >= rank_i else -1.0
                        else:
                            sign = 1.0 if dx > 0 else -1.0
                        shift = over_x / 2.0 + 0.5
                        pts[i][0] -= sign * shift
                        pts[j][0] += sign * shift
                    else:
                        sign = 1.0 if dy >= 0 else -1.0
                        shift = over_y / 2.0 + 0.5
                        pts[i][1] -= sign * shift
                        pts[j][1] += sign * shift
            for pt in pts:
                pt[0] = min(max(pt[0], inner.left()), inner.right())
                pt[1] = min(max(pt[1], inner.top()), inner.bottom())
            if not moved:
                break

        return [QPointF(x, y) for x, y in pts], geo

    def node_boxes(self) -> List[QRectF]:
        """Bounding boxes (circle + label) of every node at the current widget size."""
        pts, geo = self.layout_nodes(self.pitch_rect())
        return [
            QRectF(p.x() - geo.label_w / 2, p.y() - geo.radius, geo.label_w, geo.block_h) for p in pts
        ]

    # ------------------------------------------------------------------ painting
    def _paint_pitch(self, painter: QPainter, pitch_rect: QRectF) -> None:
        t = self.theme
        path = QPainterPath()
        path.addRoundedRect(pitch_rect, 10, 10)

        painter.save()
        painter.setClipPath(path)
        painter.fillRect(pitch_rect, to_qcolor(t.turf))
        stripe_h = pitch_rect.height() / self.STRIPES
        stripe = to_qcolor(t.turf_stripe)
        for i in range(0, self.STRIPES, 2):
            painter.fillRect(
                QRectF(pitch_rect.left(), pitch_rect.top() + i * stripe_h, pitch_rect.width(), stripe_h), stripe
            )

        painter.setPen(QPen(to_qcolor(t.pitch_line), 1.3))
        painter.setBrush(Qt.NoBrush)
        inset = pitch_rect.adjusted(6, 6, -6, -6)
        painter.drawRect(inset)
        mid_y = inset.center().y()
        painter.drawLine(QPointF(inset.left(), mid_y), QPointF(inset.right(), mid_y))
        circle_r = min(38.0, inset.width() * 0.11, inset.height() * 0.09)
        painter.drawEllipse(QPointF(inset.center().x(), mid_y), circle_r, circle_r)
        painter.setBrush(QBrush(to_qcolor(t.pitch_line)))
        painter.drawEllipse(QPointF(inset.center().x(), mid_y), 2.0, 2.0)
        painter.setBrush(Qt.NoBrush)

        box_w, box_h = inset.width() * 0.50, inset.height() * 0.14
        six_w, six_h = inset.width() * 0.24, inset.height() * 0.05
        cx = inset.center().x()
        painter.drawRect(QRectF(cx - box_w / 2, inset.top(), box_w, box_h))
        painter.drawRect(QRectF(cx - six_w / 2, inset.top(), six_w, six_h))
        painter.drawRect(QRectF(cx - box_w / 2, inset.bottom() - box_h, box_w, box_h))
        painter.drawRect(QRectF(cx - six_w / 2, inset.bottom() - six_h, six_w, six_h))
        painter.restore()

        painter.setPen(QPen(to_qcolor(t.pitch_border), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def paintEvent(self, event) -> None:
        t = self.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._hit_boxes.clear()

        painter.setPen(to_qcolor(t.pitch_title))
        painter.setFont(QFont(FONT_FAMILY, 9, QFont.DemiBold))
        painter.drawText(QRectF(0, 3, self.width(), 18), Qt.AlignCenter, self.title)

        pitch_rect = self.pitch_rect()
        self._paint_pitch(painter, pitch_rect)
        if not self.slots:
            return

        positions, geo = self.layout_nodes(pitch_rect)
        r = geo.radius
        k = r / self.BASE_RADIUS
        name_font = QFont(FONT_FAMILY)
        name_font.setPointSizeF(max(6.5, 8.0 * k))
        name_font.setWeight(QFont.DemiBold)
        role_font = QFont(FONT_FAMILY)
        role_font.setPointSizeF(max(6.0, 7.0 * k))
        score_font = QFont(FONT_FAMILY)
        score_font.setPointSizeF(max(6.5, 8.0 * k))
        score_font.setBold(True)
        name_metrics = QFontMetricsF(name_font)
        role_metrics = QFontMetricsF(role_font)
        text_w = geo.label_w - 8
        shadow = to_qcolor("rgba(0, 0, 0, 0.28)")

        for slot, centre in zip(self.slots, positions):
            px, py = centre.x(), centre.y()

            node_color = to_qcolor(t.node_ip if self.phase == "IP" else t.node_oop)
            if self.phase == "OOP" and slot.transition_alert:
                node_color = to_qcolor(t.node_alert)

            node_rect = QRectF(px - r, py - r, r * 2, r * 2)
            label_rect = QRectF(px - geo.label_w / 2, py + r + geo.gap, geo.label_w, geo.label_h)
            self._hit_boxes.append((node_rect.united(label_rect), slot))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(shadow))
            painter.drawEllipse(node_rect.translated(0, 1.5))
            painter.setBrush(QBrush(node_color))
            painter.setPen(QPen(to_qcolor(t.node_ring), 2))
            painter.drawEllipse(node_rect)

            score_val = slot.ip_score if self.phase == "IP" else slot.oop_score
            if self.comparison_mode:
                score_txt = f"-{self.dropoff_map.get(slot.slot_id, 0.0):.0f}"
            else:
                score_txt = f"{score_val:.0f}"
            painter.setFont(score_font)
            painter.setPen(to_qcolor("#ffffff"))
            painter.drawText(node_rect, Qt.AlignCenter, score_txt)

            if slot.fitness_alert:  # matchday readiness warning badge (top-right of the node)
                br = max(4.5, r * 0.42)
                badge = QRectF(px + r * 0.72 - br, py - r * 0.72 - br, 2 * br, 2 * br)
                painter.setBrush(QBrush(to_qcolor(t.status["warning"])))
                painter.setPen(QPen(to_qcolor(t.node_ring), 1.2))
                painter.drawEllipse(badge)
                badge_font = QFont(FONT_FAMILY)
                badge_font.setPointSizeF(max(5.5, br * 1.1))
                badge_font.setBold(True)
                painter.setFont(badge_font)
                painter.setPen(to_qcolor("#ffffff"))
                painter.drawText(badge, Qt.AlignCenter, "!")

            surname = slot.player.name.split()[-1] if slot.player.name.strip() else slot.slot_id
            role_txt = slot.ip_role if self.phase == "IP" else slot.oop_role
            short_role = role_txt.split("(")[0].strip()

            painter.setBrush(QBrush(to_qcolor(t.label_bg)))
            painter.setPen(QPen(to_qcolor(t.label_border), 1))
            painter.drawRoundedRect(label_rect, 6, 6)

            painter.setPen(to_qcolor(t.label_text))
            painter.setFont(name_font)
            if geo.two_line:
                name_rect = QRectF(label_rect.left() + 4, label_rect.top(), text_w, label_rect.height() * 0.52)
                role_rect = QRectF(
                    label_rect.left() + 4, label_rect.top() + label_rect.height() * 0.48, text_w, label_rect.height() * 0.5
                )
            else:
                name_rect = QRectF(label_rect.left() + 4, label_rect.top(), text_w, label_rect.height())
                role_rect = None
            painter.drawText(name_rect, Qt.AlignCenter, name_metrics.elidedText(surname, Qt.ElideRight, text_w))
            if role_rect is not None:
                painter.setPen(to_qcolor(t.label_ip_role if self.phase == "IP" else t.label_oop_role))
                painter.setFont(role_font)
                painter.drawText(role_rect, Qt.AlignCenter, role_metrics.elidedText(short_role, Qt.ElideRight, text_w))


class TacticsTab(QWidget):
    """Dual IP/OOP tactical pitch view with Best XI / Second XI / Drop-Off / Bench & Subs and instructions."""

    MODES = (("tactics.mode.best", "BEST"), ("tactics.mode.second", "BACKUP"),
             ("tactics.mode.dropoff", "COMPARE"), ("tactics.mode.bench", "BENCH"))

    def __init__(
        self,
        parent=None,
        on_bench_size_changed: Optional[Callable[[int], None]] = None,
        on_context_changed: Optional[Callable[[], None]] = None,
        explain_slot: Optional[Callable[[AssignedSlot, List[AssignedSlot]], Optional[SlotExplanation]]] = None,
    ) -> None:
        super().__init__(parent)
        self.on_context_changed = on_context_changed
        self.explain_slot = explain_slot
        self.current_result: Optional[LineupResult] = None
        self.bench_plan: Optional[BenchPlan] = None
        self.training: Dict[int, TrainingRecommendation] = {}
        self.pool_label: str = ""
        self.view_mode = "BEST"
        self.theme: Theme = LIGHT
        self.on_bench_size_changed = on_bench_size_changed
        self._selected_slot: Optional[AssignedSlot] = None
        self._copied = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(6)

        # Summary + segmented view toggle
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        self.summary_label = QLabel()
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        top_bar.addWidget(self.summary_label, 1)

        segmented = QFrame()
        segmented.setObjectName("segmented")
        seg_layout = QHBoxLayout(segmented)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(2)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons: Dict[str, QPushButton] = {}
        for _, key in self.MODES:
            btn = QPushButton()
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            if key == "BEST":
                btn.setChecked(True)
            btn.clicked.connect(lambda _, k=key: self._set_view_mode(k))
            self.mode_group.addButton(btn)
            seg_layout.addWidget(btn)
            self.mode_buttons[key] = btn
        top_bar.addWidget(segmented)
        root.addLayout(top_bar)

        # Compact sub-bar for the secondary match controls (keeps the main toolbar from overflowing).
        sub_bar = QHBoxLayout()
        sub_bar.setSpacing(6)
        self.scoring_label = QLabel()
        self.scoring_label.setObjectName("toolbarLabel")
        sub_bar.addWidget(self.scoring_label)
        self.scoring_combo = QComboBox()
        for mode in SCORING_MODES:  # display text is translated, data stays the English engine key
            self.scoring_combo.addItem(mode, mode)
        self.scoring_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        sub_bar.addWidget(self.scoring_combo)
        sub_bar.addSpacing(8)
        self.matchup_label = QLabel()
        self.matchup_label.setObjectName("toolbarLabel")
        sub_bar.addWidget(self.matchup_label)
        self.matchup_combo = QComboBox()
        for matchup in MATCHUPS:
            self.matchup_combo.addItem(matchup, matchup)
        self.matchup_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        sub_bar.addWidget(self.matchup_combo)
        sub_bar.addSpacing(8)
        self.fitness_chk = QCheckBox()
        self.fitness_chk.setChecked(True)  # matchday readiness on by default
        sub_bar.addWidget(self.fitness_chk)
        sub_bar.addStretch(1)
        root.addLayout(sub_bar)
        self.scoring_combo.currentIndexChanged.connect(self._on_context_control)
        self.matchup_combo.currentIndexChanged.connect(self._on_context_control)
        self.fitness_chk.toggled.connect(self._on_context_control)

        content = QHBoxLayout()
        content.setSpacing(8)

        # Left: pitches or bench view
        self.main_stack = QStackedWidget()
        pitch_card = QFrame()
        pitch_card.setObjectName("card")
        # The pitch is a map: left flank stays on the left and IP stays left of OOP in every language.
        pitch_card.setLayoutDirection(Qt.LeftToRight)
        pitch_layout = QHBoxLayout(pitch_card)
        pitch_layout.setContentsMargins(6, 4, 6, 6)
        pitch_layout.setSpacing(6)
        self.ip_pitch = PitchCanvas("", "IP", self._on_slot_clicked)
        self.oop_pitch = PitchCanvas("", "OOP", self._on_slot_clicked)
        pitch_layout.addWidget(self.ip_pitch, 1)
        pitch_layout.addWidget(self.oop_pitch, 1)
        self.main_stack.addWidget(pitch_card)

        bench_card = QFrame()
        bench_card.setObjectName("card")
        bench_layout = QVBoxLayout(bench_card)
        bench_layout.setContentsMargins(10, 6, 6, 6)
        bench_layout.setSpacing(4)
        bench_header = QHBoxLayout()
        self.bench_title = QLabel()
        bench_header.addWidget(self.bench_title)
        bench_header.addStretch()
        self.bench_size_label = QLabel()
        bench_header.addWidget(self.bench_size_label)
        self.bench_size_combo = QComboBox()
        for size in SUPPORTED_BENCH_SIZES:
            self.bench_size_combo.addItem(str(size), size)
        self.bench_size_combo.setCurrentIndex(SUPPORTED_BENCH_SIZES.index(DEFAULT_BENCH_SIZE))
        self.bench_size_combo.currentIndexChanged.connect(self._on_bench_size_combo)
        bench_header.addWidget(self.bench_size_combo)
        bench_layout.addLayout(bench_header)
        bench_scroll = QScrollArea()
        bench_scroll.setWidgetResizable(True)
        bench_scroll.setFrameShape(QFrame.NoFrame)
        bench_panel = QWidget()
        bench_panel.setObjectName("tabPage")
        bench_panel_layout = QVBoxLayout(bench_panel)
        bench_panel_layout.setContentsMargins(0, 0, 6, 0)
        self.bench_label = QLabel()
        self.bench_label.setWordWrap(True)
        self.bench_label.setAlignment(Qt.AlignTop)
        self.bench_label.setTextFormat(Qt.RichText)
        bench_panel_layout.addWidget(self.bench_label)
        bench_panel_layout.addStretch()
        bench_scroll.setWidget(bench_panel)
        bench_layout.addWidget(bench_scroll, 1)
        self.main_stack.addWidget(bench_card)
        content.addWidget(self.main_stack, 1)

        # Right: match plan side card
        side_card = QFrame()
        side_card.setObjectName("card")
        side_card.setMinimumWidth(270)
        side_card.setMaximumWidth(360)
        side_card_layout = QVBoxLayout(side_card)
        side_card_layout.setContentsMargins(4, 6, 4, 4)
        side_card_layout.setSpacing(2)

        side_header = QHBoxLayout()
        side_header.setContentsMargins(8, 0, 6, 0)
        self.side_title = QLabel()
        side_header.addWidget(self.side_title)
        side_header.addStretch()
        self.copy_btn = QPushButton()
        self.copy_btn.setObjectName("smallButton")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self.copy_plan)
        side_header.addWidget(self.copy_btn)
        side_card_layout.addLayout(side_header)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side_panel = QWidget()
        side_panel.setObjectName("tabPage")
        self.side_layout = QVBoxLayout(side_panel)
        self.side_layout.setContentsMargins(10, 4, 10, 8)

        self.instructions_label = QLabel()
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setAlignment(Qt.AlignTop)
        self.instructions_label.setTextFormat(Qt.RichText)

        self.divider = QFrame()
        self.divider.setFixedHeight(1)

        self.player_detail_label = QLabel()
        self.player_detail_label.setWordWrap(True)
        self.player_detail_label.setAlignment(Qt.AlignTop)
        self.player_detail_label.setTextFormat(Qt.RichText)

        self.side_layout.addWidget(self.instructions_label)
        self.side_layout.addSpacing(4)
        self.side_layout.addWidget(self.divider)
        self.side_layout.addSpacing(4)
        self.side_layout.addWidget(self.player_detail_label)
        self.side_layout.addStretch()

        side_scroll.setWidget(side_panel)
        side_card_layout.addWidget(side_scroll)
        content.addWidget(side_card)

        root.addLayout(content, 1)
        self.retranslate()
        self.apply_theme(self.theme)

    # ------------------------------------------------------------------ language / theming
    def retranslate(self) -> None:
        """Re-apply every static string and re-render dynamic content in the active language."""
        for key, mode in self.MODES:
            self.mode_buttons[mode].setText(tr_button(key))
        self.ip_pitch.title = tr("tactics.pitch.ip")
        self.oop_pitch.title = tr("tactics.pitch.oop")
        self.ip_pitch.update()
        self.oop_pitch.update()
        self.side_title.setText(tr("tactics.match_plan"))
        self.copy_btn.setText(tr("tactics.copied") if self._copied else tr("tactics.copy_plan"))
        self.copy_btn.setToolTip(tr("tactics.copy_tip"))
        self.bench_title.setText(tr("bench.title"))
        self.bench_size_label.setText(tr("bench.size"))
        self.bench_size_combo.setToolTip(tr("bench.size_tip"))
        self.scoring_label.setText(tr("tactics.scoring"))
        self.scoring_combo.setToolTip(tr("tactics.scoring_tip"))
        self.scoring_label.setToolTip(tr("tactics.scoring_tip"))
        for i in range(self.scoring_combo.count()):
            self.scoring_combo.setItemText(i, tr_scoring(self.scoring_combo.itemData(i)))
        self.matchup_label.setText(tr("tactics.matchup"))
        self.matchup_combo.setToolTip(tr("tactics.matchup_tip"))
        self.matchup_label.setToolTip(tr("tactics.matchup_tip"))
        for i in range(self.matchup_combo.count()):
            self.matchup_combo.setItemText(i, tr_matchup(self.matchup_combo.itemData(i)))
        self.fitness_chk.setText(tr_button("tactics.fitness"))
        self.fitness_chk.setToolTip(tr("tactics.fitness_tip"))
        # Item texts changed language: let the combos re-measure (AdjustToContents caches the old width).
        for combo in (self.scoring_combo, self.matchup_combo):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            combo.setMinimumWidth(combo.minimumSizeHint().width())
            combo.updateGeometry()
        self._rerender()

    def _rerender(self) -> None:
        if self.current_result is None:
            self.summary_label.setText(tr("tactics.prompt"))
            self.instructions_label.setText(tr("tactics.instructions_placeholder"))
            self.player_detail_label.setText(tr("tactics.click_hint"))
        else:
            self._render_summary()
            self._render_instructions(self.current_result)
            if self._selected_slot:
                self._on_slot_clicked(self._selected_slot)
            else:
                self.player_detail_label.setText(tr("tactics.click_hint"))
        self._render_bench()

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.summary_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {theme.text};")
        self.side_title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {theme.text};")
        self.bench_title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {theme.text};")
        self.bench_size_label.setStyleSheet(f"font-size: 11px; color: {theme.text_secondary};")
        self.instructions_label.setStyleSheet(f"font-size: 11px; color: {theme.text};")
        self.bench_label.setStyleSheet(f"font-size: 11px; color: {theme.text};")
        self.player_detail_label.setStyleSheet(f"font-size: 11px; color: {theme.text_secondary};")
        self.divider.setStyleSheet(f"background-color: {theme.card_border}; border: none;")
        self.ip_pitch.set_theme(theme)
        self.oop_pitch.set_theme(theme)
        self._rerender()

    def _set_view_mode(self, mode: str) -> None:
        self.view_mode = mode
        self.mode_buttons[mode].setChecked(True)
        self.main_stack.setCurrentIndex(1 if mode == "BENCH" else 0)
        if self.current_result:
            self._apply_pitch_data()

    # ------------------------------------------------------------------ match context (sub-bar)
    def scoring_mode(self) -> str:
        data = self.scoring_combo.currentData()
        return data if isinstance(data, str) and data else SCORING_MODES[0]

    def matchup(self) -> str:
        data = self.matchup_combo.currentData()
        return data if isinstance(data, str) and data else MATCHUPS[0]

    def factor_in_fitness(self) -> bool:
        return self.fitness_chk.isChecked()

    def _on_context_control(self, *_args) -> None:
        if self.on_context_changed:
            self.on_context_changed()

    def _on_bench_size_combo(self, _index: int) -> None:
        size = self.bench_size_combo.currentData()
        if self.on_bench_size_changed and isinstance(size, int):
            self.on_bench_size_changed(size)

    # ------------------------------------------------------------------ data
    def set_pool_label(self, pool_label: str) -> None:
        self.pool_label = pool_label
        self._render_summary()

    def update_tactics(
        self,
        result: LineupResult,
        pool_label: str = "",
        training: Optional[List[TrainingRecommendation]] = None,
    ) -> None:
        self.current_result = result
        self.pool_label = pool_label
        if training is not None:
            self.training = {r.player.player_id: r for r in training}
        self._selected_slot = None
        self.copy_btn.setEnabled(True)
        self._render_summary()
        self._apply_pitch_data()
        self._render_instructions(result)
        self.player_detail_label.setText(tr("tactics.click_hint"))

    def _apply_pitch_data(self) -> None:
        result = self.current_result
        if result is None:
            return
        if self.view_mode == "BACKUP" and result.backup_xi:
            slots, compare = result.backup_xi, False
        elif self.view_mode == "COMPARE":
            slots, compare = result.best_xi, True
        else:
            slots, compare = result.best_xi, False
        self.ip_pitch.set_data(slots, result.dropoff_by_slot, comparison_mode=compare)
        self.oop_pitch.set_data(slots, result.dropoff_by_slot, comparison_mode=compare)

    def update_bench(self, plan: Optional[BenchPlan]) -> None:
        self.bench_plan = plan
        if plan is not None and plan.size in SUPPORTED_BENCH_SIZES:
            idx = SUPPORTED_BENCH_SIZES.index(plan.size)
            if self.bench_size_combo.currentIndex() != idx:
                self.bench_size_combo.blockSignals(True)
                self.bench_size_combo.setCurrentIndex(idx)
                self.bench_size_combo.blockSignals(False)
        self._render_bench()

    # ------------------------------------------------------------------ rendering
    def _render_summary(self) -> None:
        result, t = self.current_result, self.theme
        if result is None:
            return
        big_tag = f"  ·  {tr('tactics.summary.important')}" if result.big_match_mode else ""
        if result.matchup != MATCHUPS[0]:
            big_tag += f"  ·  {escape(tr_matchup(result.matchup))}"
        if result.excluded_count:
            big_tag += (f"  ·  <span style='color:{t.status['warning']};'>"
                        f"{escape(tr('tactics.summary.excluded', count=result.excluded_count))}</span>")
        pool_txt = (
            f"  ·  <span style='color:{t.text_tertiary}; font-weight:500;'>{escape(self.pool_label)}</span>"
            if self.pool_label else ""
        )
        self.summary_label.setText(
            f"{escape(ltr(result.formation_name))}  ·  {escape(tr_style(result.tactical_style))}  ·  "
            f"{tr('tactics.summary.synergy')} <span style='color:{t.accent_label};'>"
            f"{result.team_synergy_score:.1f}</span>{big_tag}{pool_txt}"
        )

    def _section_title(self, text: str) -> str:
        t = self.theme
        return (f"<p style='margin:8px 0 3px 0; color:{t.accent_label}; font-weight:600; font-size:10px;'>"
                f"{escape(text.upper())}</p>")

    def _render_instructions(self, result: LineupResult) -> None:
        t = self.theme
        ins = result.instructions

        def section(title: str, items: dict) -> str:
            rows = []
            current_phase = None
            for k, v in items.items():
                # FM27 phase sub-header (Build-Up / Progression / Final Third / High Press ...)
                phase = InstructionsGenerator.phase_of(k).split(" - ")[-1]
                if phase and phase != "Overview" and phase != current_phase:
                    rows.append(
                        f"<tr><td colspan='2' style='color:{t.text_tertiary}; font-size:10px; "
                        f"padding:4px 0 1px 0;'>{escape(tr('tactics.phase.' + phase))}</td></tr>"
                    )
                current_phase = phase
                # Tile names and values stay in FM27 English so they match the game screen 1:1.
                rows.append("<tr>" + bidi_row([
                    f"<td style='color:{t.text_secondary}; {cell_pad(1, 8)};'>{escape(ltr(k))}</td>",
                    f"<td style='color:{t.text}; padding:1px 0;'>{escape(ltr(v))}</td>",
                ]) + "</tr>")
            return self._section_title(title) + f"{table_open()}{''.join(rows)}</table>"

        html = [
            self._formations_html(result),
            f"<p style='margin:0; font-size:12px;'><b>{tr('tactics.mentality')}</b> "
            f"<span style='color:{t.text_secondary};'>{escape(ltr(ins.mentality))}</span></p>",
            section(tr("tactics.section.ip"), ins.in_possession),
            section(tr("tactics.section.transition"), ins.in_transition),
            section(tr("tactics.section.oop"), ins.out_of_possession),
        ]
        if ins.tactical_notes:
            html.append(self._section_title(tr("tactics.section.notes")))
            html.append(
                "".join(
                    f"<p style='margin:1px 0; color:{t.text_secondary};'>•&nbsp;{escape(ltr(n))}</p>"
                    for n in ins.tactical_notes
                )
            )
        self.instructions_label.setText(_rtl_wrap("".join(html)))

    def _formations_html(self, result: LineupResult) -> str:
        """Top 3 evaluated formations with their Team Synergy, so the recommendation is transparent."""
        ranking = result.formation_ranking[:3]
        if not ranking:
            return ""
        t = self.theme
        best = ranking[0][1]
        rows = []
        for i, (name, score) in enumerate(ranking, start=1):
            note = tr("why.formation_best") if i == 1 else tr("why.formation_gap", gap=f"{best - score:.1f}")
            color = t.accent_label if i == 1 else t.text_secondary
            rows.append("<tr>" + bidi_row([
                f"<td style='color:{color}; {cell_pad(1, 6)};'><b>{i}.</b></td>",
                f"<td style='color:{t.text}; {cell_pad(1, 8)};'>{escape(ltr(name))}</td>",
                f"<td style='color:{color}; {cell_pad(1, 8)};'><b>{score:.1f}</b></td>",
                f"<td style='color:{t.text_tertiary}; padding:1px 0;'>{escape(note)}</td>",
            ]) + "</tr>")
        return (self._section_title(tr("why.formations")).replace("margin:8px", "margin:0px")
                + f"{table_open()}{''.join(rows)}</table><p style='margin:4px 0 0 0;'></p>")

    def _render_bench(self) -> None:
        t = self.theme
        plan = self.bench_plan
        if plan is None or self.current_result is None:
            self.bench_label.setText(tr("tactics.prompt"))
            return
        if not plan.bench:
            self.bench_label.setText(tr("bench.empty"))
            return
        th_align = "right" if i18n.is_rtl() else "left"
        head = bidi_row(
            f"<th align='{th_align}' style='color:{t.text_tertiary}; font-weight:600; {cell_pad(3)};'>"
            f"{escape(tr(k))}</th>"
            for k in ("bench.col.player", "bench.col.pos", "bench.col.cover", "bench.col.covers",
                      "bench.col.best", "bench.col.impact")
        )
        rows = []
        for i, b in enumerate(plan.bench, start=1):
            role_color = t.status["info"] if b.bench_role == "backup_gk" else t.accent_label
            best = f"{b.best_cover_slot} ({b.best_cover_score:.1f})" if b.best_cover_slot else "—"
            pad = cell_pad()
            covers = ", ".join(b.covered_positions) or "—"
            warn = (f" <span style='color:{t.status['warning']};'>⚠ {escape(tr_fitness(b.fitness_alert))}</span>"
                    if b.fitness_alert else "")
            rows.append("<tr>" + bidi_row([
                f"<td style='{pad}; color:{t.text};'><b>{escape(ltr(f'{i}. {b.player.name}'))}</b>{warn}</td>",
                f"<td style='{pad}; color:{t.text_secondary};'>{escape(ltr('/'.join(b.player.positions)))}</td>",
                f"<td style='{pad}; color:{role_color};'>{escape(tr('bench.role.' + b.bench_role))}</td>",
                f"<td style='{pad}; color:{t.text_secondary};'>{escape(ltr(covers))}</td>",
                f"<td style='{pad}; color:{t.text_secondary};'>{escape(ltr(best))}</td>",
                f"<td style='padding:2px 0; color:{t.text_secondary};'>{b.impact:.1f}</td>",
            ]) + "</tr>")
        if plan.uncovered_slots:
            cover_note = (f"<p style='margin:6px 0 0 0; color:{t.status['warning']};'>"
                          f"{escape(tr('bench.uncovered', slots=', '.join(plan.uncovered_slots)))}</p>")
        else:
            cover_note = f"<p style='margin:6px 0 0 0; color:{t.status['success']};'>{escape(tr('bench.all_covered'))}</p>"

        subs = []
        for s in plan.scenarios:
            subs.append(
                f"<p style='margin:6px 0 0 0; color:{t.text};'>"
                f"<b style='color:{t.accent_label};'>{escape(ltr(s.minute))}  {escape(tr('subs.kind.' + s.kind))}</b><br>"
                f"{escape(tr('subs.change', on=ltr(s.player_on.name), off=ltr(s.player_off.name), slot=s.slot_id))}<br>"
                f"<span style='color:{t.text_secondary};'>{escape(tr('subs.roles'))}: "
                f"{escape(ltr(s.ip_role + ' / ' + s.oop_role))}</span><br>"
                f"<span style='color:{t.text_tertiary};'>{escape(tr_reason(s.reason_key, s.reason_args))}</span></p>"
            )
        subs_html = "".join(subs) or f"<p style='color:{t.text_tertiary};'>{escape(tr('bench.no_subs'))}</p>"
        self.bench_label.setText(_rtl_wrap(
            f"{table_open()}<tr>{head}</tr>{''.join(rows)}</table>{cover_note}"
            f"{self._section_title(tr('bench.subs_title'))}{subs_html}"
        ))

    # ------------------------------------------------------------------ clipboard (FM27 English on purpose)
    def plan_text(self) -> str:
        """Plain-text match plan (formation, Best XI roles, bench, instructions) for the clipboard."""
        result = self.current_result
        if result is None:
            return ""
        ins = result.instructions
        lines = [
            f"FM27 Match Plan - {result.formation_name} | {result.tactical_style}"
            f"{' | Important Match' if result.big_match_mode else ''}",
            f"Team Synergy: {result.team_synergy_score:.1f}  |  Mentality: {ins.mentality}",
            f"Scoring: {result.scoring_mode}  |  Matchup: {result.matchup}  |  "
            f"Factor in Fitness: {'On' if result.factor_in_fitness else 'Off'}",
            "Top formations: " + ", ".join(f"{n} ({s:.1f})" for n, s in result.formation_ranking[:3]),
            "",
            "BEST XI (In Possession role / Out of Possession role)",
        ]
        for a in result.best_xi:
            fit = f"  [{tr_fitness_en(a.fitness_alert)}]" if a.fitness_alert else ""
            lines.append(f"  {a.slot_id:<5} {a.player.name:<26} {a.ip_role} / {a.oop_role}  ({a.combined_score:.1f}){fit}")
            if a.individual_instructions:
                lines.append(f"        PI: {', '.join(a.individual_instructions)}")
        for title, items in (
            ("IN POSSESSION", ins.in_possession),
            ("IN TRANSITION", ins.in_transition),
            ("OUT OF POSSESSION", ins.out_of_possession),
        ):
            lines += ["", title]
            current_phase = None
            for k, v in items.items():
                phase = InstructionsGenerator.phase_of(k).split(" - ")[-1]
                if phase and phase != "Overview" and phase != current_phase:
                    lines.append(f"  [{phase}]")
                current_phase = phase
                lines.append(f"  {k}: {v}")
        if ins.tactical_notes:
            lines += ["", "NOTES"] + [f"  - {n}" for n in ins.tactical_notes]
        plan = self.bench_plan
        if plan is not None and plan.bench:
            lines += ["", f"MATCHDAY BENCH ({len(plan.bench)} subs)"]
            for b in plan.bench:
                lines.append(f"  {b.player.name:<26} {'/'.join(b.player.positions):<12} covers {', '.join(b.covered_positions)}")
            if plan.scenarios:
                lines += ["", "PLANNED SUBSTITUTIONS"]
                kinds = {"chase_goal": "Chase a Goal", "protect_lead": "Protect a Lead", "fatigue": "Fresh Legs"}
                for s in plan.scenarios:
                    lines.append(f"  {s.minute} {kinds.get(s.kind, s.kind)}: {s.player_on.name} ON for "
                                 f"{s.player_off.name} ({s.slot_id}) as {s.ip_role} / {s.oop_role}")
        return "\n".join(lines)

    def copy_plan(self) -> None:
        text = self.plan_text()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self._copied = True
        self.copy_btn.setText(tr("tactics.copied"))

        def reset() -> None:
            self._copied = False
            self.copy_btn.setText(tr("tactics.copy_plan"))

        QTimer.singleShot(1500, reset)

    def _on_slot_clicked(self, slot: AssignedSlot) -> None:
        self._selected_slot = slot
        t = self.theme
        alert_html = (
            f"<span style='color:{t.status['error']};'><b>{tr('tactics.detail.alert')}:</b> "
            f"{escape(ltr(slot.transition_alert))}</span>"
            if slot.transition_alert
            else f"<span style='color:{t.status['success']};'>{tr('tactics.detail.optimal')}</span>"
        )
        pi_html = "".join(
            f"<p style='margin:1px 0;'>•&nbsp;{escape(ltr(inst))}</p>" for inst in slot.individual_instructions
        )
        rec = self.training.get(slot.player.player_id)
        training_html = ""
        if rec is not None:
            training_html = (
                self._section_title(tr("tactics.detail.training"))
                + f"<p style='margin:1px 0;'>{escape(ltr(rec.role_focus))} · {escape(tr_focus(rec.additional_focus))}"
                f" · <b>{escape(tr_intensity(rec.intensity))}</b><br>"
                f"<span style='color:{t.text_tertiary};'>{escape(training_reason(rec))}</span></p>"
            )
        self.player_detail_label.setText(_rtl_wrap(
            f"<p style='margin:0; font-size:12px; color:{t.text};'><b>{escape(ltr(slot.player.name))}</b> "
            f"<span style='color:{t.text_tertiary};'>{escape(slot.slot_id)}</span></p>"
            f"<p style='margin:3px 0;'>{tr('tactics.detail.ip')}: <span style='color:{t.text};'>"
            f"{escape(ltr(slot.ip_role))}</span> ({slot.ip_score:.1f})<br>"
            f"{tr('tactics.detail.oop')}: <span style='color:{t.text};'>{escape(ltr(slot.oop_role))}</span> "
            f"({slot.oop_score:.1f})<br>"
            f"{tr('tactics.detail.displacement')}: {slot.transition_distance:.1f}m<br>{alert_html}<br>"
            f"{self._fitness_html(slot)}</p>"
            + self._why_html(slot)
            + self._section_title(tr("tactics.detail.pi")) + pi_html + training_html
        ))

    def _fitness_html(self, slot: AssignedSlot) -> str:
        t, p = self.theme, slot.player
        if p.match_sharpness is None and p.fatigue is None:
            return f"<span style='color:{t.text_tertiary};'>{escape(tr('fitness.unknown'))}</span>"
        detail = escape(tr("fitness.detail", pct=p.match_sharpness if p.match_sharpness is not None else "—",
                           fatigue=p.fatigue if p.fatigue is not None else "—"))
        if slot.fitness_alert:
            head = f"<span style='color:{t.status['warning']};'><b>⚠ {escape(tr_fitness(slot.fitness_alert))}</b></span>"
        else:
            head = f"<span style='color:{t.status['success']};'>{escape(tr('fitness.ready'))}</span>"
        penalty = ""
        if slot.fitness_factor < 0.995:
            penalty = (f"<br><span style='color:{t.text_tertiary};'>"
                       f"{escape(tr('fitness.penalty', pct=f'{(1 - slot.fitness_factor) * 100:.1f}'))}</span>")
        return f"{head}<br><span style='color:{t.text_tertiary};'>{detail}</span>{penalty}"

    def _displayed_lineup(self) -> List[AssignedSlot]:
        result = self.current_result
        if result is None:
            return []
        if self.view_mode == "BACKUP" and result.backup_xi:
            return result.backup_xi
        return result.best_xi

    def _why_html(self, slot: AssignedSlot) -> str:
        """'Why this player?': top contributing attributes and the runner-up comparison."""
        if self.explain_slot is None:
            return ""
        try:
            exp = self.explain_slot(slot, self._displayed_lineup())
        except Exception:  # noqa: BLE001 - an explanation must never break the pitch view
            return ""
        if exp is None:
            return ""
        t = self.theme
        attrs = " · ".join(
            f"{escape(tr_attr(c.attr))} <b>{c.value}</b>" for c in exp.top_attributes[:5]
        )
        parts = [self._section_title(tr("why.title")),
                 f"<p style='margin:1px 0; color:{t.text_secondary};'>{escape(tr('why.top_attrs'))}: {attrs}</p>"]
        if exp.runner_up is None:
            parts.append(f"<p style='margin:1px 0; color:{t.text_tertiary};'>{escape(tr('why.no_runner_up'))}</p>")
            return "".join(parts)
        key = "why.beat" if exp.gap >= 0 else "why.locked"
        parts.append(
            f"<p style='margin:1px 0; color:{t.text};'>{escape(tr(key, name=ltr(exp.runner_up.name), score=f'{exp.score:.1f}', runner=f'{exp.runner_up_score:.1f}', gap=f'{exp.gap:.1f}'))}</p>"
        )
        if exp.drivers:
            drivers = ", ".join(f"{d.delta:+.1f} {tr_driver(d.attrs)}" for d in exp.drivers)
            line = tr("why.drivers", drivers=drivers)
        else:
            line = tr("why.no_drivers")
        parts.append(f"<p style='margin:1px 0; color:{t.accent_label};'>{escape(line)}</p>")
        return "".join(parts)


def tr_fitness_en(alert) -> str:
    """Fitness alert in English for the clipboard plan (FM27 English on purpose)."""
    if not alert:
        return ""
    key, args = alert
    return i18n.EN.get(key, key).format(**args)


def _rtl_wrap(html: str) -> str:
    """Give rich text a right-to-left base direction in Hebrew (tables and bullets then flow from the right)."""
    return f"<div dir='rtl'>{html}</div>" if i18n.is_rtl() else html
