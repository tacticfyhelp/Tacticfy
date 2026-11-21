"""Tab 3: Squad Planner, Keep/Loan/Sell Advisor, Weakest Link profile and Individual Training Plan."""

from html import escape
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.advisor.squad_classifier import has_real_finances
from src.engine.training_advisor import TrainingRecommendation
from src.models.tactics import PlayerClassification, WeakestLinkReport
from src.ui import i18n
from src.ui.i18n import bidi_row, cell_pad, ltr, table_open, tr, tr_attr, tr_category, tr_focus, tr_intensity, training_reason
from src.ui.theme import LIGHT, Theme, category_key

# bucket key -> theme category colour key (titles come from i18n "advisor.bucket.<KEY>")
BUCKETS: Dict[str, str] = {
    "KEEP": "core",
    "LOAN": "loan",
    "SELL_HIGH": "sell_high",
    "OFFLOAD": "offload",
}


def _rtl_wrap(html: str) -> str:
    return f"<div dir='rtl'>{html}</div>" if i18n.is_rtl() else html


class AdvisorTab(QWidget):
    """Displays actionable squad buckets, the Weakest Link target profile and the training plan."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.theme: Theme = LIGHT
        self._data: Optional[Tuple[List[PlayerClassification], WeakestLinkReport]] = None
        self._training: List[TrainingRecommendation] = []
        self.bucket_boxes: Dict[str, QGroupBox] = {}
        self.bucket_labels: Dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(10)

        self.weakest_box = QGroupBox()
        w_layout = QVBoxLayout(self.weakest_box)
        self.weakest_label = QLabel()
        self.weakest_label.setWordWrap(True)
        self.weakest_label.setTextFormat(Qt.RichText)
        w_layout.addWidget(self.weakest_label)
        root.addWidget(self.weakest_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        container.setObjectName("tabPage")
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 4, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)

        for key, (row, col) in zip(BUCKETS, [(0, 0), (0, 1), (1, 0), (1, 1)]):
            box = QGroupBox()
            layout = QVBoxLayout(box)
            lbl = QLabel()
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.RichText)
            lbl.setAlignment(Qt.AlignTop)
            layout.addWidget(lbl)
            layout.addStretch()
            grid.addWidget(box, row, col)
            self.bucket_boxes[key] = box
            self.bucket_labels[key] = lbl

        self.training_box = QGroupBox()
        t_layout = QVBoxLayout(self.training_box)
        self.training_label = QLabel()
        self.training_label.setWordWrap(True)
        self.training_label.setTextFormat(Qt.RichText)
        self.training_label.setAlignment(Qt.AlignTop)
        t_layout.addWidget(self.training_label)
        grid.addWidget(self.training_box, 2, 0, 1, 2)

        scroll.setWidget(container)
        root.addWidget(scroll)
        self.retranslate()
        self.apply_theme(self.theme)

    # Backward-compatible attribute names
    @property
    def keep_label(self) -> QLabel:
        return self.bucket_labels["KEEP"]

    @property
    def loan_label(self) -> QLabel:
        return self.bucket_labels["LOAN"]

    @property
    def sell_high_label(self) -> QLabel:
        return self.bucket_labels["SELL_HIGH"]

    @property
    def offload_label(self) -> QLabel:
        return self.bucket_labels["OFFLOAD"]

    # ------------------------------------------------------------------ language / theming
    def retranslate(self) -> None:
        self.weakest_box.setTitle(tr("advisor.weakest.title"))
        for key in BUCKETS:
            self.bucket_boxes[key].setTitle(tr(f"advisor.bucket.{key}"))
        self.training_box.setTitle(tr("advisor.training.title"))
        self._rerender()

    def _rerender(self) -> None:
        if self._data:
            self.update_advisor(*self._data)
        else:
            self.weakest_label.setText(tr("advisor.weakest.placeholder"))
            for lbl in self.bucket_labels.values():
                lbl.setText(tr("advisor.bucket.empty"))
        self._render_training()

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.weakest_box.setStyleSheet(f"QGroupBox {{ color: {theme.status['warning']}; font-size: 13px; }}")
        self.weakest_label.setStyleSheet(f"font-weight: normal; color: {theme.text}; font-size: 12px;")
        for key, color_key in BUCKETS.items():
            self.bucket_boxes[key].setStyleSheet(
                f"QGroupBox {{ color: {theme.categories[color_key]}; font-size: 13px; }}"
            )
            self.bucket_labels[key].setStyleSheet(f"font-weight: normal; color: {theme.text}; font-size: 12px;")
        self.training_box.setStyleSheet(f"QGroupBox {{ color: {theme.accent_label}; font-size: 13px; }}")
        self.training_label.setStyleSheet(f"font-weight: normal; color: {theme.text}; font-size: 12px;")
        self._rerender()

    # ------------------------------------------------------------------ data
    def update_advisor(
        self,
        classified: List[PlayerClassification],
        weakest: WeakestLinkReport,
        training: Optional[List[TrainingRecommendation]] = None,
    ) -> None:
        """Populate the Weakest Link card, the four squad management buckets and the training plan."""
        self._data = (classified, weakest)
        if training is not None:
            self._training = list(training)
        t = self.theme
        attrs_str = ", ".join(f"{escape(tr_attr(k))} &ge; {v}" for k, v in weakest.minimum_attributes.items())
        if weakest.steepest_dropoff_delta > 0:  # 0 everywhere = no full Second XI to compare against
            depth = tr("advisor.weakest.depth", slot=weakest.steepest_dropoff_slot,
                       delta=f"{weakest.steepest_dropoff_delta:.1f}")
        else:
            depth = tr("advisor.weakest.no_depth")
        summary = tr("advisor.weakest.summary", slot=weakest.weakest_slot_id, name=ltr(weakest.weakest_player_name),
                     score=f"{weakest.weakest_slot_score:.1f}", role=ltr(weakest.target_role))
        self.weakest_label.setText(_rtl_wrap(
            f"<p style='margin:0 0 6px 0;'><b>{escape(summary)} {escape(depth)}</b></p>"
            f"<p style='margin:0; color:{t.text_secondary};'>{escape(tr('advisor.weakest.filter'))} "
            f"<b style='color:{t.text};'>{escape(weakest.target_position)} ({escape(ltr(weakest.target_role))})</b>:</p>"
            f"<p style='margin:4px 0 0 0; color:{t.accent_label};'>{attrs_str}</p>"
        ))

        buckets: Dict[str, List[str]] = {key: [] for key in BUCKETS}
        show_wage = has_real_finances([c.player for c in classified])
        for item in classified:
            p = item.player
            wage_txt = f", ${p.wage_weekly:,}/wk" if show_wage else ""
            key = category_key(item.category)
            bucket = {"core": "KEEP", "rotation": "KEEP", "loan": "LOAN", "sell_high": "SELL_HIGH"}.get(key, "OFFLOAD")
            tag = (
                f" <span style='color:{t.categories[key]};'>· {escape(tr_category(item.category))}</span>"
                if bucket == "KEEP" else ""
            )
            # CA / PA / wage stay one left-to-right run so Hebrew text cannot reorder them.
            stats = ltr(f"CA {p.hidden.ca} / PA {p.hidden.pa}{wage_txt}")
            line = tr("advisor.player_line", age=p.age, stats=stats)
            buckets[bucket].append(
                f"<p style='margin:0 0 7px 0;'><b>{escape(ltr(p.name))}</b>{tag}<br>"
                f"<span style='color:{t.text_tertiary};'>{escape(line)}</span><br>"
                f"<span style='color:{t.text_secondary};'>{escape(ltr(' '.join(item.reasons)))}</span></p>"
            )

        for key, lines in buckets.items():
            self.bucket_labels[key].setText(_rtl_wrap(
                "".join(lines) or f"<span style='color:{t.text_tertiary};'>{escape(tr('advisor.none'))}</span>"
            ))
        self._render_training()

    def _render_training(self) -> None:
        t = self.theme
        if not self._training:
            self.training_label.setText(tr("advisor.training.placeholder"))
            return
        intensity_color = {"Double Intensity": t.status["success"], "Half Intensity": t.status["warning"]}
        th_align = "right" if i18n.is_rtl() else "left"
        head = bidi_row(
            f"<th align='{th_align}' style='color:{t.text_tertiary}; font-weight:600; {cell_pad(3, 12)};'>"
            f"{escape(tr(k))}</th>"
            for k in ("training.col.player", "training.col.role_focus", "training.col.add_focus",
                      "training.col.intensity", "training.col.reason")
        )
        rows = []
        for rec in self._training:
            color = intensity_color.get(rec.intensity, t.text_secondary)
            pad = cell_pad(2, 12)
            rows.append("<tr>" + bidi_row([
                f"<td style='{pad};'><b>{escape(ltr(rec.player.name))}</b> "
                f"<span style='color:{t.text_tertiary};'>{escape(tr('training.source.' + rec.role_source))}</span></td>",
                f"<td style='{pad};'>{escape(ltr(rec.role_focus))}</td>",
                f"<td style='{pad};'>{escape(tr_focus(rec.additional_focus))}</td>",
                f"<td style='{pad}; color:{color}; font-weight:600;'>{escape(tr_intensity(rec.intensity))}</td>",
                f"<td style='padding:2px 0; color:{t.text_secondary};'>{escape(training_reason(rec))}</td>",
            ]) + "</tr>")
        self.training_label.setText(_rtl_wrap(f"{table_open()}<tr>{head}</tr>{''.join(rows)}</table>"))
