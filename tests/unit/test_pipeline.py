"""End-to-end gates: waste in, decision out, with every stage consistent."""

from __future__ import annotations

import pytest

from scentinel.core import composition as comp
from scentinel.core import massbalance as mb
from scentinel.core import pipeline
from scentinel.core import suitability as suit


def test_the_whole_chain_runs_and_produces_a_decision():
    result = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40, age_h=8.0
    )
    assert result.phase == "I"
    assert result.recommendation.headline
    assert result.recommendation.reasons


def test_every_stage_sees_the_same_inputs():
    """A stage reading different inputs than its neighbour is a silent bug."""
    result = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40, age_h=8.0
    )
    assert result.generation.tonnage_t == result.balance.tonnage_t == 10.0
    assert result.generation.age_h == result.age_h == 8.0
    assert result.balance.moisture_tonnes == pytest.approx(10.0 * 0.40)


def test_mass_closes_end_to_end():
    result = pipeline.assess_batch(
        comp.PRESETS["organic-rich"], tonnage_t=7.5, moisture=0.55, age_h=12.0
    )
    assert result.balance.accounted_tonnes == pytest.approx(7.5, abs=1e-9)


def test_a_fresh_load_reports_phase_one_and_no_methane():
    result = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40, age_h=6.0
    )
    assert result.phase == "I"
    assert "CH4" not in result.generation.gases
    assert result.generation.ch4_kg < 0.001 * 10.0


def test_the_same_load_years_later_is_phase_four_with_methane():
    fresh = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40, age_h=8.0
    )
    aged = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40, age_h=24 * 365 * 3
    )
    assert aged.phase == "IV"
    assert "CH4" in aged.generation.gases
    assert aged.generation.ch4_kg > fresh.generation.ch4_kg * 1000


def test_the_methane_ceiling_holds_end_to_end():
    for name, preset in comp.PRESETS.items():
        for age_h in (8.0, 24 * 200, 24 * 365 * 30):
            result = pipeline.assess_batch(
                preset, tonnage_t=10.0, moisture=0.5, age_h=age_h
            )
            assert (
                result.generation.methane_fraction
                <= comp.STEADY_STATE_METHANE_CEILING + 1e-9
            ), name


def test_the_summary_is_readable_and_ordered():
    result = pipeline.assess_batch(
        comp.PRESETS["dry-recyclables"], tonnage_t=10.0, moisture=0.10, age_h=8.0
    )
    lines = result.summary_lines()
    assert lines[0].startswith("Batch:")
    assert any(line.strip().startswith("=>") for line in lines)
    assert any("because" in line for line in lines)
    assert any("caveat" in line for line in lines)


def test_tonnage_scales_the_whole_assessment():
    one = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=1.0, moisture=0.4, age_h=24 * 365
    )
    ten = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4, age_h=24 * 365
    )
    assert ten.generation.ch4_kg == pytest.approx(one.generation.ch4_kg * 10.0)
    for stream in mb.STREAMS:
        assert ten.balance.streams[stream].tonnes == pytest.approx(
            one.balance.streams[stream].tonnes * 10.0
        )


def test_the_recommendation_inherits_the_screening_caveat():
    result = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4, age_h=8.0
    )
    assert any("screening" in c for c in result.recommendation.caveats)


def test_a_complete_laboratory_set_flows_through_to_the_recommendation():
    quality = suit.QualityInputs(
        ncv_mj_per_kg=17.5,
        ash_fraction=0.11,
        chlorine_fraction=0.005,
        source=suit.LABORATORY,
    )
    result = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"],
        tonnage_t=10.0,
        moisture=0.3,
        age_h=8.0,
        quality=quality,
    )
    assert result.suitability.quality.complete
    assert not any("require laboratory analysis" in c for c in result.recommendation.caveats)


def test_invalid_inputs_are_rejected_before_any_stage_runs():
    with pytest.raises(ValueError, match="tonnage_t"):
        pipeline.assess_batch(
            comp.PRESETS["mixed-msw"], tonnage_t=-1.0, moisture=0.4, age_h=8.0
        )
    with pytest.raises(ValueError, match="moisture"):
        pipeline.assess_batch(
            comp.PRESETS["mixed-msw"], tonnage_t=1.0, moisture=2.0, age_h=8.0
        )
