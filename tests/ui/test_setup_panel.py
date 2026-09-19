from __future__ import annotations

import pytest

from scentinel.core.geometry import BinGeometry
from scentinel.core.scenario import WASTE_SPECS
from scentinel.ui.i18n import Translator
from scentinel.ui.setup_panel import SetupPanel


@pytest.fixture
def panel(qapp, translator):
    widget = SetupPanel(translator)
    yield widget
    widget.deleteLater()


def test_the_source_strength_readout_names_the_flux(panel):
    """The applied source is a mass flux; the panel must show it, not a ppmv value."""
    panel._waste_type.setCurrentIndex(panel._waste_type.findData("mixed-msw"))
    panel._age_h.setValue(24.0 * 365 * 3)
    text = panel.derived_tooltip()
    assert "kg/m" in text
    assert "emission" in text.lower() or "flux" in text.lower()


def test_defaults_match_the_default_project(panel):
    geom = panel.geometry()
    assert (geom.length_m, geom.height_m, geom.mound_shape) == (6.0, 2.5, "flat")
    assert panel.scenario().wind_speed_m_s == pytest.approx(1.0)
    assert panel.gas_sources() == {}


def test_a_fresh_holding_time_removes_methane_from_the_gas_list(panel):
    """A fresh aerobic load cannot select methane: its row is hidden, not disabled."""
    panel._age_h.setValue(8.0)
    assert "CH4" not in panel.offered_gas_keys()
    assert not panel._gas_boxes["CH4"].isVisibleTo(panel)
    assert panel.gas_sources() == {}
    panel._age_h.setValue(24.0 * 365 * 5)
    assert "CH4" in panel.offered_gas_keys()
    assert panel._gas_boxes["CH4"].isVisibleTo(panel)
    assert "CH4" in panel.gas_sources()


def test_editing_a_field_emits_the_new_geometry(panel):
    received = []
    panel.changed.connect(lambda geom, scenario: received.append((geom, scenario)))

    panel._length.setValue(8.0)

    assert received, "editing bin length should emit changed"
    geom, scenario = received[-1]
    assert geom.length_m == pytest.approx(8.0)
    assert scenario.wind_speed_m_s == pytest.approx(panel.scenario().wind_speed_m_s)


def test_checking_a_gas_source_includes_it_in_the_scenario(panel):
    panel._gas_boxes["CO"].setChecked(True)
    panel._gas_boxes["H2S"].setChecked(True)

    assert panel.gas_sources() == {"CO": "auto", "H2S": "auto"}
    assert set(panel.scenario().gas_sources) == {"CO", "H2S"}


def test_explicit_value_overrides_auto(panel):
    panel._gas_boxes["CO"].setChecked(True)
    panel._gas_auto["CO"].setChecked(False)
    panel._gas_spins["CO"].setValue(105.0)

    assert panel.gas_sources() == {"CO": 105.0}


def test_auto_checkbox_disables_the_value_spin(panel):
    panel._gas_boxes["CO"].setChecked(True)
    assert not panel._gas_spins["CO"].isEnabled()
    panel._gas_auto["CO"].setChecked(False)
    assert panel._gas_spins["CO"].isEnabled()


def test_disabling_a_gas_source_removes_it_again(panel):
    panel._gas_boxes["CO"].setChecked(True)
    panel._gas_boxes["CO"].setChecked(False)
    assert panel.gas_sources() == {}


def test_set_values_does_not_emit_and_round_trips(panel):
    from scentinel.core.scenario import Scenario

    received = []
    panel.changed.connect(lambda geom, scenario: received.append((geom, scenario)))

    geom = BinGeometry(length_m=7.5, height_m=3.0, mound_shape="irregular", mound_fill_fraction=0.35)
    panel.set_values(geom, Scenario())

    assert received == []
    assert panel.geometry() == geom


def test_set_values_restores_auto_sources(panel):
    from scentinel.core.scenario import Scenario

    panel.set_values(BinGeometry(), Scenario(gas_sources={"CO": "auto", "VOC": 2400.0}))
    assert panel.gas_sources() == {"CO": "auto", "VOC": 2400.0}


def test_set_values_restores_selected_gas_sources(panel):
    from scentinel.core.scenario import Scenario

    panel.set_values(BinGeometry(), Scenario(gas_sources={"CO": 105.0, "VOC": 2400.0}))
    assert panel.gas_sources() == {"CO": 105.0, "VOC": 2400.0}


def test_mound_shape_combo_carries_its_key(panel):
    panel._shape.setCurrentIndex(panel._shape.findData("mounded"))
    assert panel.geometry().mound_shape == "mounded"


@pytest.mark.parametrize(
    "shape",
    ["flat", "mounded", "left-heavy", "right-heavy", "twin-mound", "irregular"],
)
def test_every_waste_profile_is_available(panel, shape):
    panel._shape.setCurrentIndex(panel._shape.findData(shape))
    assert panel.geometry().mound_shape == shape
    assert panel._shape_help.text()


def test_simulation_controls_are_explicit_inputs(panel):
    panel._mesh_size.setValue(0.15)
    panel._end_iteration.setValue(750)
    assert panel.mesh_size_m() == pytest.approx(0.15)
    assert panel.end_iteration() == 750


def test_switching_language_relabels_the_group_boxes(qapp):
    translator = Translator("en")
    panel = SetupPanel(translator)
    english = panel._geometry_group.title()

    translator.set_locale("id")

    assert panel._geometry_group.title() != english
    assert panel._length_label.text() != "Bin length"
    panel.deleteLater()

def test_selecting_a_waste_type_applies_default_gases_and_fractions(panel):
    panel._waste_type.setCurrentIndex(panel._waste_type.findData("organic-rich"))
    scenario = panel.scenario()
    assert scenario.waste_type == "organic-rich"
    # The organic fraction is derived from the preset composition now, so it is
    # the degradable share rather than an independently entered number.
    assert scenario.organic_fraction == pytest.approx(
        WASTE_SPECS["organic-rich"].composition.degradable_fraction()
    )
    assert scenario.moisture_fraction == pytest.approx(0.60)
    # At the default 8 h holding time the load is aerobic, so methane is not
    # offered; the preset's other gases are.
    assert scenario.gas_sources == {"VOC": "auto", "H2S": "auto"}


def test_an_aged_holding_time_brings_methane_back(panel):
    panel._waste_type.setCurrentIndex(panel._waste_type.findData("organic-rich"))
    panel._age_h.setValue(24.0 * 365 * 5)
    assert panel.scenario().gas_sources == {"CH4": "auto", "VOC": "auto", "H2S": "auto"}


def test_set_values_restores_waste_age_without_resetting_gases(panel):
    from scentinel.core.scenario import Scenario

    panel.set_values(
        BinGeometry(),
        Scenario(
            waste_type="rdf-feedstock",
            age_h=30.0,
            moisture_fraction=0.12,
            gas_sources={"VOC": 100.0},
        ),
    )
    scenario = panel.scenario()
    assert scenario.waste_type == "rdf-feedstock"
    assert scenario.age_h == pytest.approx(30.0)
    assert scenario.gas_sources == {"VOC": 100.0}


def test_the_derived_readout_reports_the_phase_and_whether_methane_exists(panel):
    """The simulation-driven part: inputs imply the phase, before any run."""
    panel._waste_type.setCurrentIndex(panel._waste_type.findData("mixed-msw"))
    panel._age_h.setValue(8.0)
    fresh = panel._derived_label.text()
    assert "I" in fresh
    assert "not yet produced" in fresh

    panel._age_h.setValue(24.0 * 365 * 5)
    aged = panel._derived_label.text()
    assert "IV" in aged
    assert "produced" in aged and "not yet" not in aged
