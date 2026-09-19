"""Realtime gates: the assessment must update the moment an input changes.

The user's requirement was that output follow the simulation live, not after a
solve. These tests drive the panel's own widgets and assert the rendered text
changes — which is what a person actually sees.
"""

from __future__ import annotations

import pytest

from scentinel.core.composition import PRESETS
from scentinel.ui.batch_panel import BatchPanel


@pytest.fixture
def panel(qapp, translator):
    widget = BatchPanel(translator)
    yield widget
    widget.deleteLater()


def _text(panel: BatchPanel, key: str) -> str:
    return panel._fields[key].text()


def test_the_panel_produces_an_assessment_on_construction(panel):
    """No button, no solve: the readout is populated immediately."""
    assert panel.assessment() is not None
    assert _text(panel, "phase") in ("I", "II", "III", "IV")
    assert _text(panel, "recommendation") != "—"


def test_changing_holding_time_updates_the_phase_live(panel):
    panel._age_h.setValue(8.0)
    assert _text(panel, "phase") == "I"
    panel._age_h.setValue(24.0 * 365 * 5)
    assert _text(panel, "phase") == "IV"


def test_changing_holding_time_updates_the_gas_readout_live(panel):
    panel._age_h.setValue(8.0)
    fresh = _text(panel, "gas_now")
    panel._age_h.setValue(24.0 * 365 * 5)
    aged = _text(panel, "gas_now")
    assert fresh != aged
    assert "CH4 0.000" in fresh
    assert "CH4 0.000" not in aged


def test_changing_tonnage_updates_the_yield_live(panel):
    panel._tonnage.setValue(1.0)
    one = _text(panel, "yield")
    panel._tonnage.setValue(100.0)
    hundred = _text(panel, "yield")
    assert one != hundred


def test_changing_moisture_updates_the_decay_readout_live(panel):
    panel._age_h.setValue(24.0 * 365)
    panel._moisture.setValue(0.10)
    dry = _text(panel, "doc_k")
    panel._moisture.setValue(0.60)
    wet = _text(panel, "doc_k")
    assert dry != wet


def test_editing_a_fraction_updates_the_scores_live(panel):
    panel._preset.setCurrentIndex(panel._preset.findData("mixed-msw"))
    before = _text(panel, "scores")
    # Push the composition toward paper, which is the RDF feedstock.
    panel._fractions["paper"].setValue(0.80)
    panel._fractions["food"].setValue(0.05)
    after = _text(panel, "scores")
    assert before != after


def test_selecting_a_preset_rewrites_every_fraction(panel):
    panel._preset.setCurrentIndex(panel._preset.findData("dry-recyclables"))
    composition = panel.composition()
    expected = PRESETS["dry-recyclables"]
    for key in ("paper", "inert", "food"):
        assert getattr(composition, key) == pytest.approx(getattr(expected, key), abs=1e-6)


def test_selecting_a_preset_sets_its_moisture(panel):
    panel._preset.setCurrentIndex(panel._preset.findData("rdf-feedstock"))
    assert panel.moisture() == pytest.approx(0.15)


def test_the_assessment_signal_fires_on_every_change(panel):
    seen = []
    panel.assessed.connect(seen.append)
    panel._tonnage.setValue(5.0)
    panel._age_h.setValue(100.0)
    panel._moisture.setValue(0.30)
    assert len(seen) >= 3
    assert seen[-1].tonnage_t == pytest.approx(5.0)


def test_a_fresh_load_recommendation_carries_the_screening_caveat(panel):
    panel._age_h.setValue(8.0)
    assert "screening" in _text(panel, "caveats")


def test_missing_laboratory_inputs_are_named_in_the_panel(panel):
    assert _text(panel, "quality_missing") != "complete"
    assert "ncv" in _text(panel, "quality_missing")


def test_an_all_zero_fraction_table_falls_back_to_the_preset(panel):
    """A half-typed table must not crash or produce a nonsense assessment."""
    panel._preset.setCurrentIndex(panel._preset.findData("mixed-msw"))
    for widget in panel._fractions.values():
        widget.setValue(0.0)
    composition = panel.composition()
    assert abs(composition.total - 1.0) < 1e-9


def test_the_sum_warning_appears_when_fractions_do_not_sum_to_one(panel):
    for widget in panel._fractions.values():
        widget.setValue(0.05)
    assert "normalis" in _text(panel, "scores") or panel._sum_label.text() != ""


def test_the_panel_retranslates(panel, qapp):
    from scentinel.ui.i18n import Translator

    translator = Translator("en")
    widget = BatchPanel(translator)
    english = widget._inputs_group.title()
    translator.set_locale("id")
    assert widget._inputs_group.title() != english
    widget.deleteLater()


def test_reasons_and_caveats_are_shown_not_just_the_headline(panel):
    """A recommendation the user cannot audit is not usable."""
    assert _text(panel, "reasons") not in ("", "—")
    assert _text(panel, "caveats") not in ("", "—")
