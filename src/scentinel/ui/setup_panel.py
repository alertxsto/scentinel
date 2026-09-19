"""Left-hand setup panel: geometry, scenario, and gas sources.

The panel owns no application state — it emits :attr:`SetupPanel.changed` with a
fresh ``(BinGeometry, Scenario)`` pair whenever the user edits a field, and
:meth:`SetupPanel.set_values` pushes state back in when a project is loaded.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from scentinel.core.gas_data import DEFAULT_SOURCE_GASES, citation
from scentinel.core.geometry import MOUND_SHAPES, BinGeometry, fill_fraction
from scentinel.core.scenario import WIND_DIRECTIONS, Scenario
from scentinel.ui.i18n import Translator

SHAPE_KEYS = {
    "flat": "shape.flat",
    "mounded": "shape.mounded",
    "left-heavy": "shape.left_heavy",
    "right-heavy": "shape.right_heavy",
    "twin-mound": "shape.twin_mound",
    "irregular": "shape.irregular",
}
DIRECTION_KEYS = {
    "left-to-right": "dir.left_to_right",
    "right-to-left": "dir.right_to_left",
}


class SetupPanel(QScrollArea):
    """Form for bin geometry, wind scenario, and per-gas source strengths."""

    changed = Signal(object, object)  # (BinGeometry, Scenario)

    def __init__(
        self,
        translator: Translator,
        *,
        default_mesh_size_m: float = 0.25,
        default_end_iteration: int = 500,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._t = translator
        self._default_mesh_size_m = default_mesh_size_m
        self._default_end_iteration = default_end_iteration
        self._gas_boxes: dict[str, QCheckBox] = {}
        self._gas_spins: dict[str, QDoubleSpinBox] = {}
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.addWidget(self._build_geometry_group())
        layout.addWidget(self._build_scenario_group())
        layout.addWidget(self._build_sources_group())
        layout.addWidget(self._build_simulation_group())
        layout.addStretch(1)
        self.setWidget(body)
        self.setWidgetResizable(True)

        self._t.changed.connect(self.retranslate)
        self.retranslate()

    # -- construction --------------------------------------------------------

    def _build_geometry_group(self) -> QGroupBox:
        self._geometry_group = QGroupBox(self)
        form = QFormLayout(self._geometry_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._geometry_help = _help_label()
        form.addRow(self._geometry_help)

        self._length = _spin(0.5, 30.0, 6.0, 0.1, " m", 2)
        self._height = _spin(0.5, 10.0, 2.5, 0.1, " m", 2)
        self._shape = QComboBox()
        for shape in MOUND_SHAPES:
            self._shape.addItem("", shape)
        self._fill = _spin(0.05, 1.0, 0.5, 0.05, "", 2, decimals=2)
        self._fill.setSingleStep(0.05)
        self._actual_fill = QLabel("—")
        self._actual_fill.setObjectName("actualFillLabel")

        self._length_label = QLabel()
        self._height_label = QLabel()
        self._shape_label = QLabel()
        self._fill_label = QLabel()
        self._actual_fill_caption = QLabel()
        self._shape_help = _help_label()
        form.addRow(self._length_label, self._length)
        form.addRow(self._height_label, self._height)
        form.addRow(self._shape_label, self._shape)
        form.addRow(self._fill_label, self._fill)
        form.addRow(self._actual_fill_caption, self._actual_fill)
        form.addRow(self._shape_help)

        for widget in (self._length, self._height, self._fill):
            widget.valueChanged.connect(self._emit)
        self._shape.currentIndexChanged.connect(self._emit)
        return self._geometry_group

    def _build_scenario_group(self) -> QGroupBox:
        self._scenario_group = QGroupBox(self)
        form = QFormLayout(self._scenario_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._scenario_help = _help_label()
        form.addRow(self._scenario_help)

        self._wind_speed = _spin(0.0, 20.0, 1.0, 0.1, " m/s", 2)
        self._wind_direction = QComboBox()
        for direction in WIND_DIRECTIONS:
            self._wind_direction.addItem("", direction)
        self._ventilation = QCheckBox()

        self._wind_speed_label = QLabel()
        self._wind_direction_label = QLabel()
        self._ventilation_label = QLabel()
        form.addRow(self._wind_speed_label, self._wind_speed)
        form.addRow(self._wind_direction_label, self._wind_direction)
        form.addRow(self._ventilation_label, self._ventilation)

        self._wind_speed.valueChanged.connect(self._emit)
        self._wind_direction.currentIndexChanged.connect(self._emit)
        self._ventilation.toggled.connect(self._emit)
        return self._scenario_group

    def _build_sources_group(self) -> QGroupBox:
        self._sources_group = QGroupBox(self)
        form = QFormLayout(self._sources_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._sources_help = _help_label()
        form.addRow(self._sources_help)

        self._gas_boxes: dict[str, QCheckBox] = {}
        self._gas_spins: dict[str, QDoubleSpinBox] = {}
        self._gas_auto: dict[str, QCheckBox] = {}
        for gas in DEFAULT_SOURCE_GASES:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            box = QCheckBox()
            box.setToolTip(citation(gas))
            spin = _spin(0.0, 1_000_000.0, 0.0, 10.0, " ppmv", 1, decimals=1)
            spin.setEnabled(False)
            auto = QCheckBox("auto")
            auto.setToolTip(citation(gas))
            auto.setChecked(True)

            # ``box`` and ``auto`` are rebound on each iteration, so they are
            # captured as defaults rather than closed over.
            box.toggled.connect(
                lambda checked, widget=spin, auto=auto: widget.setEnabled(
                    checked and not auto.isChecked()
                )
            )
            auto.toggled.connect(
                lambda checked, widget=spin, box=box: widget.setEnabled(
                    not checked and box.isChecked()
                )
            )
            box.toggled.connect(self._emit)
            auto.toggled.connect(self._emit)
            spin.valueChanged.connect(self._emit)

            row_layout.addWidget(spin, 1)
            row_layout.addWidget(auto)
            self._gas_boxes[gas] = box
            self._gas_spins[gas] = spin
            self._gas_auto[gas] = auto
            form.addRow(box, row)
        return self._sources_group

    def _build_simulation_group(self) -> QGroupBox:
        self._simulation_group = QGroupBox(self)
        form = QFormLayout(self._simulation_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._simulation_help = _help_label()
        form.addRow(self._simulation_help)

        self._mesh_size = _spin(
            0.05, 1.0, self._default_mesh_size_m, 0.05, " m", 2, decimals=2
        )
        self._end_iteration = QSpinBox()
        self._end_iteration.setRange(50, 10_000)
        self._end_iteration.setSingleStep(50)
        self._end_iteration.setValue(self._default_end_iteration)
        self._mesh_size_label = QLabel()
        self._end_iteration_label = QLabel()
        form.addRow(self._mesh_size_label, self._mesh_size)
        form.addRow(self._end_iteration_label, self._end_iteration)
        return self._simulation_group

    # -- state ---------------------------------------------------------------

    def geometry(self) -> BinGeometry:
        return BinGeometry(
            length_m=self._length.value(),
            height_m=self._height.value(),
            mound_shape=self._shape.currentData(),
            mound_fill_fraction=self._fill.value(),
        )

    def scenario(self) -> Scenario:
        return Scenario(
            wind_speed_m_s=self._wind_speed.value(),
            wind_direction=self._wind_direction.currentData(),
            ventilation_on=self._ventilation.isChecked(),
            gas_sources=self.gas_sources(),
        )

    def mesh_size_m(self) -> float:
        return self._mesh_size.value()

    def end_iteration(self) -> int:
        return self._end_iteration.value()

    def gas_sources(self) -> dict[str, float | str]:
        """Selected gases, as ``"auto"`` or an explicit ppmv value."""
        selected: dict[str, float | str] = {}
        for gas, box in self._gas_boxes.items():
            if not box.isChecked():
                continue
            selected[gas] = "auto" if self._gas_auto[gas].isChecked() else self._gas_spins[gas].value()
        return selected

    def set_values(self, geom: BinGeometry, scenario: Scenario) -> None:
        """Push a loaded project into the widgets without emitting spurious changes."""
        widgets = (
            self._length,
            self._height,
            self._shape,
            self._fill,
            self._wind_speed,
            self._wind_direction,
            self._ventilation,
            *self._gas_boxes.values(),
            *self._gas_spins.values(),
            *self._gas_auto.values(),
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self._length.setValue(geom.length_m)
            self._height.setValue(geom.height_m)
            self._shape.setCurrentIndex(self._shape.findData(geom.mound_shape))
            self._fill.setValue(geom.mound_fill_fraction)
            self._wind_speed.setValue(scenario.wind_speed_m_s)
            self._wind_direction.setCurrentIndex(
                self._wind_direction.findData(scenario.wind_direction)
            )
            self._ventilation.setChecked(scenario.ventilation_on)
            for gas, box in self._gas_boxes.items():
                value = scenario.gas_sources.get(gas)
                box.setChecked(value is not None)
                is_auto = isinstance(value, str)
                self._gas_auto[gas].setChecked(is_auto)
                if value is not None and not is_auto:
                    self._gas_spins[gas].setValue(float(value))
                self._gas_spins[gas].setEnabled(value is not None and not is_auto)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._refresh_derived()

    def retranslate(self) -> None:
        t = self._t.t
        self._geometry_group.setTitle(t("group.geometry"))
        self._scenario_group.setTitle(t("group.scenario"))
        self._sources_group.setTitle(t("group.gas_sources"))
        self._simulation_group.setTitle(t("group.simulation"))
        self._geometry_help.setText(t("help.geometry"))
        self._scenario_help.setText(t("help.scenario"))
        self._sources_help.setText(t("help.gas_sources"))
        self._simulation_help.setText(t("help.simulation"))

        self._length_label.setText(t("field.length"))
        self._height_label.setText(t("field.height"))
        self._shape_label.setText(t("field.mound_shape"))
        self._fill_label.setText(t("field.fill"))
        self._actual_fill_caption.setText(t("field.actual_fill"))
        self._wind_speed_label.setText(t("field.wind_speed"))
        self._wind_direction_label.setText(t("field.wind_direction"))
        self._ventilation_label.setText(t("field.ventilation"))
        self._mesh_size_label.setText(t("field.mesh_size"))
        self._end_iteration_label.setText(t("field.end_iteration"))

        for index, shape in enumerate(MOUND_SHAPES):
            self._shape.setItemText(index, t(SHAPE_KEYS[shape]))
        for index, direction in enumerate(WIND_DIRECTIONS):
            self._wind_direction.setItemText(index, t(DIRECTION_KEYS[direction]))
        self._shape_help.setText(t(f"help.shape.{self._shape.currentData()}"))

        self._refresh_derived()

    # -- internals -----------------------------------------------------------

    def _emit(self, *_args: object) -> None:
        self._refresh_derived()
        self.changed.emit(self.geometry(), self.scenario())

    def _refresh_derived(self) -> None:
        actual = fill_fraction(self.geometry())
        requested = self._fill.value()
        self._actual_fill.setText(f"{actual:.1%}")
        if abs(actual - requested) > 0.005:
            self._actual_fill.setToolTip(self._t.t("validation.fill_range"))
            self._actual_fill.setStyleSheet("color: #b45309;")
        else:
            self._actual_fill.setToolTip("")
            self._actual_fill.setStyleSheet("")
        self._shape_help.setText(self._t.t(f"help.shape.{self._shape.currentData()}"))


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


def _help_label() -> QLabel:
    label = QLabel()
    label.setObjectName("fieldHelp")
    label.setWordWrap(True)
    return label
