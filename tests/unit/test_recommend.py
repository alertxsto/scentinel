"""Recommendation gates: it must cite its reasons and refuse to guess."""

from __future__ import annotations

import pytest

from scentinel.core import composition as comp
from scentinel.core import recommend as rec
from scentinel.core import suitability as suit


def test_a_dry_paper_rich_batch_is_recommended_for_rdf():
    result = rec.recommend(
        comp.PRESETS["dry-recyclables"], tonnage_t=10.0, moisture=0.10, age_h=8.0
    )
    assert result.actionable
    assert result.route == "rdf"
    assert "RDF" in result.headline


def test_a_wet_rdf_batch_names_moisture_reduction_in_the_headline():
    """The user's own example: 'recommended for RDF after moisture reduction'."""
    result = rec.recommend(
        comp.PRESETS["rdf-feedstock"], tonnage_t=10.0, moisture=0.60, age_h=8.0
    )
    assert result.route == "rdf"
    assert "moisture reduction" in result.headline


def test_a_food_heavy_wet_batch_is_not_recommended_for_rdf():
    result = rec.recommend(
        comp.PRESETS["organic-rich"], tonnage_t=10.0, moisture=0.70, age_h=8.0
    )
    assert result.route != "rdf"


def test_every_recommendation_cites_its_reasons_and_inputs():
    result = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.30, age_h=8.0
    )
    assert result.reasons
    assert result.inputs
    assert any("scores" in reason for reason in result.reasons)


def test_a_recommendation_carries_the_screening_caveat():
    """No output may claim more confidence than the transport underneath it."""
    result = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.30, age_h=8.0
    )
    assert any("screening" in caveat for caveat in result.caveats)


def test_the_screening_caveat_can_be_dropped_only_deliberately():
    result = rec.recommend(
        comp.PRESETS["mixed-msw"],
        tonnage_t=10.0,
        moisture=0.30,
        age_h=8.0,
        screening=False,
    )
    assert not any("screening" in caveat for caveat in result.caveats)


def test_missing_laboratory_inputs_are_named_as_a_caveat():
    result = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.30, age_h=8.0
    )
    assert any("laboratory" in caveat for caveat in result.caveats)


def test_a_complete_laboratory_set_removes_that_caveat():
    quality = suit.QualityInputs(
        ncv_mj_per_kg=18.0,
        ash_fraction=0.12,
        chlorine_fraction=0.006,
        source=suit.LABORATORY,
    )
    result = rec.recommend(
        comp.PRESETS["mixed-msw"],
        tonnage_t=10.0,
        moisture=0.30,
        age_h=8.0,
        quality=quality,
    )
    assert not any("require laboratory analysis" in c for c in result.caveats)


def test_zero_tonnage_yields_no_recommendation_and_names_the_gap():
    result = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=0.0, moisture=0.30, age_h=8.0
    )
    assert not result.actionable
    assert result.insufficient
    assert "tonnage_t" in result.missing


def test_an_unscoreable_batch_refuses_rather_than_inventing_a_route():
    """All-inert waste has no recoverable route worth recommending."""
    result = rec.recommend(
        comp.WasteComposition(inert=1.0), tonnage_t=10.0, moisture=0.05, age_h=8.0
    )
    # It may legitimately land on landfill/recycling; what it must not do is
    # claim an organic route.
    if result.actionable:
        assert result.route in ("landfill", "recycling")
    else:
        assert result.insufficient


def test_a_runner_up_is_reported_when_one_exists():
    result = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.30, age_h=8.0
    )
    assert result.alternative is not None
    assert "margin" in result.alternative


def test_the_projected_yield_is_quoted_and_matches_the_balance():
    from scentinel.core import massbalance as mb

    composition = comp.PRESETS["dry-recyclables"]
    result = rec.recommend(composition, tonnage_t=10.0, moisture=0.10, age_h=8.0)
    balance = mb.balance(composition, tonnage_t=10.0, moisture=0.10)
    expected = balance.streams["rdf"].tonnes
    assert any(f"{expected:.2f} t" in reason for reason in result.reasons)


def test_drying_caveat_appears_above_the_threshold_and_not_below():
    wet = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.60, age_h=8.0
    )
    dry = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.10, age_h=8.0
    )
    assert any("drying" in c for c in wet.caveats)
    assert not any("drying" in c for c in dry.caveats)


def test_caveats_are_deduplicated():
    result = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.60, age_h=8.0
    )
    assert len(result.caveats) == len(set(result.caveats))


def test_age_is_carried_through_as_an_input():
    result = rec.recommend(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.30, age_h=72.0
    )
    assert result.inputs["age_h"] == 72.0
