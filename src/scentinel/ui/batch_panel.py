"""Live batch assessment panel: the decision output, updated as you type.

This is the simulation-driven surface. Editing a composition fraction, the
holding time, the tonnage, or the moisture recomputes the whole chain
immediately — no solve, no button — and shows:

* the decomposition phase and the gas the load is producing right now,
* per-stream yield in tonnes,
* per-route suitability scores with the rule behind each one,
* the quality fields that are still missing, named rather than blanked,
* one recommendation with its reasons and caveats.

Every value shown here comes from :mod:`scentinel.core.pipeline`. Nothing is
computed in the widget, so the panel cannot drift from the model.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scentinel.core import massbalance as mb
from scentinel.core import pipeline
from scentinel.core import suitability as suit
from scentinel.core.composition import MATERIAL_KEYS, PRESET_MOISTURE, PRESETS
from scentinel.ui.i18n import Translator

#: Display order and labels for the composition fractions.
FRACTION_LABELS = {
    "food": "Food waste",
    "garden": "Garden waste",
    "paper": "Paper / card",
    "wood": "Wood / straw",
    "textile": "Textiles",
    "diaper": "Diapers",
    "sludge": "Sewage sludge",
    "inert": "Inert (glass, plastic, metal)",
}

STREAM_LABELS = {
    "rdf": "RDF",
    "recyclable": "Recyclable",
    "organic": "Organic recovery",
    "compost": "Compost",
    "residue": "Residue",
    "moisture": "Moisture (water)",
}


class BatchPanel(QScrollArea):
    """Composition inputs plus the live assessment they produce."""

    #: Emitted whenever the batch changes, with the recomputed assessment.
    assessed = Signal(object)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = translator
        self._loading = False

        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.addWidget(self._build_inputs())
        layout.addWidget(self._build_readout())
        layout.addStretch(1)
        self.setWidget(body)
        self.setWidgetResizable(True)

        self._t.changed.connect(self.retranslate)
        self.retranslate()
        self.recompute()

    # -- construction --------------------------------------------------------

    def _build_inputs(self) -> QGroupBox:
        self._inputs_group = QGroupBox(self)
        form = QFormLayout(self._inputs_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._preset = QComboBox()
        for name in PRESETS:
            self._preset.addItem("", name)
        self._preset.currentIndexChanged.connect(self._on_preset_changed)

        self._tonnage = _spin(0.0, 100_000.0, 10.0, 1.0, " t", 1)
        self._age_h = _spin(0.0, 24.0 * 365 * 50, 8.0, 1.0, " h", 1)
        self._moisture = _spin(0.0, 1.0, 0.40, 0.05, "", 2, decimals=2)

        self._preset_label = QLabel()
        self._tonnage_label = QLabel()
        self._age_label = QLabel()
        self._moisture_label = QLabel()
        form.addRow(self._preset_label, self._preset)
        form.addRow(self._tonnage_label, self._tonnage)
        form.addRow(self._age_label, self._age_h)
        form.addRow(self._moisture_label, self._moisture)

        self._fractions: dict[str, QDoubleSpinBox] = {}
        self._fraction_labels: dict[str, QLabel] = {}
        for key in MATERIAL_KEYS:
            widget = _spin(0.0, 1.0, 0.0, 0.01, "", 3, decimals=3)
            widget.valueChanged.connect(self._on_fraction_changed)
            label = QLabel()
            self._fractions[key] = widget
            self._fraction_labels[key] = label
            form.addRow(label, widget)

        self._sum_label = QLabel()
        self._sum_label.setWordWrap(True)
        form.addRow(self._sum_label)

        for widget in (self._tonnage, self._age_h, self._moisture):
            widget.valueChanged.connect(self.recompute)
        return self._inputs_group

    def _build_readout(self) -> QGroupBox:
        self._readout_group = QGroupBox(self)
        outer = QVBoxLayout(self._readout_group)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        self._fields: dict[str, QLabel] = {}
        keys = (
            "phase",
            "gas_cumulative",
            "gas_rate",
            "doc_k",
            "yield",
            "scores",
            "quality_missing",
            "recommendation",
            "reasons",
            "caveats",
        )
        self._field_labels: dict[str, QLabel] = {}
        for row, key in enumerate(keys):
            label = QLabel()
            label.setWordWrap(True)
            value = QLabel("—")
            value.setObjectName("batchValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._field_labels[key] = label
            self._fields[key] = value
            grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)
        return self._readout_group

    # -- state ---------------------------------------------------------------

    def composition(self):
        """The current fractions, normalised so the model always gets a valid input."""
        from scentinel.core.composition import WasteComposition

        raw = {key: widget.value() for key, widget in self._fractions.items()}
        total = sum(raw.values())
        if total <= 0.0:
            # An all-zero table is not a batch; fall back to the selected preset
            # so the readout keeps showing something coherent while the user types.
            return PRESETS[self._preset.currentData()]
        return WasteComposition(**{key: value / total for key, value in raw.items()})

    def tonnage_t(self) -> float:
        return self._tonnage.value()

    def age_h(self) -> float:
        return self._age_h.value()

    def moisture(self) -> float:
        return self._moisture.value()

    def assessment(self):
        return self._assessment

    def preset_key(self) -> str:
        """The stream key currently selected, which names the AP-42 regime."""
        return self._preset.currentData()

    def set_values(
        self,
        *,
        tonnage_t: float,
        age_h: float,
        moisture: float,
        waste_type: str,
        composition,
    ) -> None:
        """Load a stored batch without emitting a spurious assessment.

        Called while the window is ``_loading``, so the recompute below paints
        the readout for the stored batch but cannot mark the project dirty.
        """
        self._loading = True
        widgets = [
            self._preset,
            self._tonnage,
            self._age_h,
            self._moisture,
            *self._fractions.values(),
        ]
        try:
            for widget in widgets:
                widget.blockSignals(True)
            self._preset.setCurrentIndex(self._preset.findData(waste_type))
            self._tonnage.setValue(tonnage_t)
            self._age_h.setValue(age_h)
            self._moisture.setValue(moisture)
            for key, widget in self._fractions.items():
                widget.setValue(getattr(composition, key))
        finally:
            for widget in widgets:
                widget.blockSignals(False)
            self._loading = False
        self.recompute()

    def set_batch_inputs(
        self, *, age_h: float, moisture: float, waste_type: str | None = None
    ) -> None:
        """Mirror the setup panel's holding time, moisture, and stream into this panel.

        The stream is mirrored without re-applying its preset fractions: this is
        a synchronisation of the label the two panels share, not a request to
        overwrite the composition the user is editing.
        """
        self._loading = True
        widgets = [self._age_h, self._moisture]
        if waste_type is not None:
            widgets.append(self._preset)
        try:
            for widget in widgets:
                widget.blockSignals(True)
            self._age_h.setValue(age_h)
            self._moisture.setValue(moisture)
            if waste_type is not None:
                self._preset.setCurrentIndex(self._preset.findData(waste_type))
        finally:
            for widget in widgets:
                widget.blockSignals(False)
            self._loading = False
        self.recompute()

    # -- behaviour -----------------------------------------------------------

    def _on_preset_changed(self) -> None:
        if self._loading:
            return
        name = self._preset.currentData()
        preset = PRESETS[name]
        self._loading = True
        try:
            for key, widget in self._fractions.items():
                widget.blockSignals(True)
                widget.setValue(getattr(preset, key))
                widget.blockSignals(False)
            self._moisture.blockSignals(True)
            self._moisture.setValue(PRESET_MOISTURE[name])
            self._moisture.blockSignals(False)
        finally:
            self._loading = False
        self.recompute()

    def _on_fraction_changed(self) -> None:
        if self._loading:
            return
        self.recompute()

    def recompute(self) -> None:
        """Re-run the chain and repaint. Called on every input change."""
        composition = self.composition()
        assessment = pipeline.assess_batch(
            composition,
            tonnage_t=self.tonnage_t(),
            moisture=self.moisture(),
            age_h=self.age_h(),
        )
        self._assessment = assessment
        self._render(assessment)
        self.assessed.emit(assessment)

    def _render(self, assessment) -> None:
        gen = assessment.generation
        total = sum(widget.value() for widget in self._fractions.values())
        if abs(total - 1.0) > 1e-6:
            self._sum_label.setText(
                self._t.t("batch.sum_warning", total=f"{total:.3f}")
            )
            self._sum_label.setStyleSheet("color: palette(highlighted-text);")
        else:
            self._sum_label.setText(self._t.t("batch.sum_ok"))
            self._sum_label.setStyleSheet("")

        self._fields["phase"].setText(
            f"{assessment.phase} · {assessment.generation.phase_interpretation.applicability}"
        )
        self._fields["gas_cumulative"].setText(
            f"CH4 {gen.ch4_cumulative_kg:.3f} kg · CO2 {gen.co2_cumulative_kg:.3f} kg"
        )
        self._fields["gas_rate"].setText(
            f"CH4 {gen.ch4_rate_kg_per_h:.4f} kg/h · "
            f"CO2 {gen.co2_rate_kg_per_h:.4f} kg/h"
        )
        self._fields["doc_k"].setText(
            f"DOC {gen.doc:.4f} · k {gen.k_per_year:.4f} /yr · "
            f"decay reached {gen.decay_fraction:.4%}"
        )

        lines = []
        for stream in mb.STREAMS:
            tonnes = assessment.balance.streams[stream].tonnes
            if tonnes > 0.0:
                lines.append(
                    f"{STREAM_LABELS[stream]}: {tonnes:.2f} t "
                    f"({assessment.balance.yield_fraction(stream):.0%})"
                )
        self._fields["yield"].setText("\n".join(lines) or "—")

        score_lines = []
        for score in assessment.suitability.ranked():
            score_lines.append(f"{score.route}: {score.score:.2f}")
        withheld = [
            s for s in assessment.suitability.scores.values() if not s.available
        ]
        for score in withheld:
            score_lines.append(f"{score.route}: {suit.INSUFFICIENT}")
        self._fields["scores"].setText("\n".join(score_lines) or "—")

        quality = assessment.suitability.quality
        self._fields["quality_missing"].setText(
            ", ".join(quality.missing()) if not quality.complete else "complete"
        )

        rec = assessment.recommendation
        self._fields["recommendation"].setText(rec.headline)
        self._fields["reasons"].setText("\n".join(rec.reasons) or "—")
        self._fields["caveats"].setText("\n".join(rec.caveats) or "—")

    # -- i18n ----------------------------------------------------------------

    def retranslate(self) -> None:
        t = self._t.t
        self._inputs_group.setTitle(t("batch.group.inputs"))
        self._readout_group.setTitle(t("batch.group.readout"))
        self._preset_label.setText(t("batch.field.preset"))
        self._tonnage_label.setText(t("batch.field.tonnage"))
        self._age_label.setText(t("batch.field.age"))
        self._moisture_label.setText(t("batch.field.moisture"))
        for key, label in self._fraction_labels.items():
            label.setText(FRACTION_LABELS[key])
        for index, name in enumerate(PRESETS):
            self._preset.setItemText(index, name)
        for key, label in self._field_labels.items():
            label.setText(t(f"batch.readout.{key}"))


def _spin(
    minimum: float,
    maximum: float,
    value: float,
    step: float,
    suffix: str,
    precision: int,
    *,
    decimals: int = 3,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)
    return spin
