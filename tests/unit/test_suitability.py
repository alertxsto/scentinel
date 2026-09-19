"""Suitability gates: the scores must respond to inputs and refuse to guess."""

from __future__ import annotations

import pytest

from scentinel.core import composition as comp
from scentinel.core import suitability as suit


def test_a_dry_paper_rich_load_scores_higher_for_rdf_than_a_wet_food_load():
    dry = suit.assess(comp.PRESETS["dry-recyclables"], moisture=0.10)
    wet = suit.assess(comp.PRESETS["organic-rich"], moisture=0.60)
    assert dry.scores["rdf"].score > wet.scores["rdf"].score


def test_a_food_heavy_load_scores_higher_for_digestion():
    food = suit.assess(comp.PRESETS["organic-rich"], moisture=0.60)
    dry = suit.assess(comp.PRESETS["dry-recyclables"], moisture=0.10)
    assert food.scores["anaerobic_digestion"].score > dry.scores["anaerobic_digestion"].score


def test_composting_prefers_working_moisture_over_bone_dry():
    """The rule peaks near 0.5; saturation and dryness both score lower."""
    preset = comp.PRESETS["organic-rich"]
    at_half = suit.assess(preset, moisture=0.50).scores["composting"].score
    bone_dry = suit.assess(preset, moisture=0.00).scores["composting"].score
    saturated = suit.assess(preset, moisture=1.00).scores["composting"].score
    assert at_half > bone_dry
    assert at_half > saturated


def test_an_all_inert_load_scores_high_for_recycling_and_landfill():
    inert = comp.WasteComposition(inert=1.0)
    scores = suit.assess(inert, moisture=0.05).scores
    assert scores["recycling"].score > 0.5
    assert scores["landfill"].score > 0.5
    assert scores["composting"].score < 0.5


def test_every_score_is_a_fraction():
    for name, preset in comp.PRESETS.items():
        for moisture in (0.0, 0.3, 0.6, 1.0):
            result = suit.assess(preset, moisture=moisture)
            for route, score in result.scores.items():
                assert score.score is not None, (name, route)
                assert 0.0 <= score.score <= 1.0, (name, route, score.score)


def test_every_score_states_its_rule_and_its_inputs():
    """A number without its rule is not reviewable."""
    result = suit.assess(comp.PRESETS["mixed-msw"], moisture=0.4)
    for route, score in result.scores.items():
        assert score.rule, route
        assert score.inputs, route
        assert score.route == route


def test_scores_change_when_composition_changes():
    """The defect this module replaces: output that ignores its input."""
    a = suit.assess(comp.PRESETS["mixed-msw"], moisture=0.4).scores["rdf"].score
    b = suit.assess(comp.PRESETS["dry-recyclables"], moisture=0.4).scores["rdf"].score
    assert a != b


def test_scores_change_when_moisture_changes():
    preset = comp.PRESETS["mixed-msw"]
    a = suit.assess(preset, moisture=0.1).scores["rdf"].score
    b = suit.assess(preset, moisture=0.7).scores["rdf"].score
    assert a > b


def test_ranking_excludes_withheld_routes_and_orders_the_rest():
    result = suit.assess(comp.PRESETS["organic-rich"], moisture=0.6)
    ranked = result.ranked()
    assert ranked, "at least one route must be scoreable"
    values = [s.score for s in ranked]
    assert values == sorted(values, reverse=True)
    assert result.best().route == ranked[0].route


def test_out_of_range_moisture_is_rejected():
    with pytest.raises(ValueError, match="moisture"):
        suit.assess(comp.PRESETS["mixed-msw"], moisture=1.5)


# -- quality: the honest gap -------------------------------------------------


def test_missing_quality_inputs_are_named_not_defaulted():
    quality = suit.QualityInputs()
    assert not quality.complete
    assert set(quality.missing()) == {"ncv_mj_per_kg", "ash_fraction", "chlorine_fraction"}


def test_a_partial_quality_set_is_still_incomplete():
    quality = suit.QualityInputs(ncv_mj_per_kg=18.0, source=suit.LABORATORY)
    assert not quality.complete
    assert "ash_fraction" in quality.missing()
    assert "chlorine_fraction" in quality.missing()


def test_a_complete_laboratory_set_is_complete():
    quality = suit.QualityInputs(
        ncv_mj_per_kg=18.0,
        ash_fraction=0.12,
        chlorine_fraction=0.006,
        source=suit.LABORATORY,
    )
    assert quality.complete
    assert quality.missing() == ()


def test_no_fuel_class_without_all_three_parameters():
    """A grade from two of three inputs is the number a decision would rest on."""
    grade, reason = suit.fuel_grade(suit.QualityInputs(ncv_mj_per_kg=18.0))
    assert grade is None
    assert "ash_fraction" in reason


def test_no_fuel_class_from_values_of_unknown_provenance():
    quality = suit.QualityInputs(
        ncv_mj_per_kg=18.0, ash_fraction=0.12, chlorine_fraction=0.006
    )
    grade, reason = suit.fuel_grade(quality)
    assert grade is None
    assert "provenance" in reason


def test_no_fuel_class_while_the_standard_is_uncited():
    """The class boundaries are not in this repo; the code says so instead of guessing."""
    quality = suit.QualityInputs(
        ncv_mj_per_kg=18.0,
        ash_fraction=0.12,
        chlorine_fraction=0.006,
        source=suit.LABORATORY,
    )
    grade, reason = suit.fuel_grade(quality)
    assert grade is None
    assert "not yet cited" in reason


def test_assessment_reports_the_missing_laboratory_inputs():
    result = suit.assess(comp.PRESETS["mixed-msw"], moisture=0.4)
    assert any("laboratory" in note for note in result.notes)


def test_assessment_states_that_scores_are_heuristics():
    result = suit.assess(comp.PRESETS["mixed-msw"], moisture=0.4)
    assert any("heuristics" in note for note in result.notes)


def test_zero_moisture_and_full_moisture_do_not_crash_any_route():
    for moisture in (0.0, 1.0):
        result = suit.assess(comp.PRESETS["mixed-msw"], moisture=moisture)
        assert all(s.score is not None for s in result.scores.values())
