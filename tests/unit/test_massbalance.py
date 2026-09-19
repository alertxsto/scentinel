"""Mass balance gates: the arithmetic that turns a load into tonnage."""

from __future__ import annotations

import pytest

from scentinel.core import composition as comp
from scentinel.core import massbalance as mb


def test_a_batch_accounts_for_every_kilogram():
    result = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40)
    assert result.accounted_tonnes == pytest.approx(10.0, abs=1e-9)


def test_moisture_is_its_own_stream_not_a_product():
    result = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40)
    assert result.moisture_tonnes == pytest.approx(4.0)
    assert result.streams["moisture"].tonnes == pytest.approx(4.0)
    assert result.dry_tonnage_t == pytest.approx(6.0)
    # Moisture is not counted as RDF or any other product.
    for stream in ("rdf", "recyclable", "organic", "compost", "residue"):
        assert "water" not in result.streams[stream].by_material


def test_products_sum_to_the_dry_mass():
    result = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40)
    products = sum(
        result.streams[s].tonnes
        for s in ("rdf", "recyclable", "organic", "compost", "residue")
    )
    assert products == pytest.approx(result.dry_tonnage_t, abs=1e-9)


def test_dry_rdf_feedstock_yields_more_rdf_than_wet_food_waste():
    """The ordering the routing table is built to encode."""
    dry = mb.balance(comp.PRESETS["dry-recyclables"], tonnage_t=10.0, moisture=0.10)
    wet = mb.balance(comp.PRESETS["organic-rich"], tonnage_t=10.0, moisture=0.60)
    assert dry.yield_fraction("rdf") > wet.yield_fraction("rdf")
    assert wet.yield_fraction("organic") + wet.yield_fraction("compost") > 0.0


def test_an_all_inert_load_produces_no_organic_products():
    result = mb.balance(comp.WasteComposition(inert=1.0), tonnage_t=10.0, moisture=0.10)
    for stream in ("rdf", "organic", "compost"):
        assert result.streams[stream].tonnes == pytest.approx(0.0)


def test_zero_tonnage_produces_zero_everything():
    result = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=0.0, moisture=0.40)
    assert result.accounted_tonnes == pytest.approx(0.0)
    assert result.yield_fraction("rdf") == 0.0


def test_negative_tonnage_is_rejected():
    with pytest.raises(ValueError, match="tonnage_t"):
        mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=-1.0, moisture=0.4)


def test_out_of_range_moisture_is_rejected():
    with pytest.raises(ValueError, match="moisture"):
        mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=1.0, moisture=1.5)


def test_a_routing_table_that_loses_mass_is_rejected():
    """Splits must sum to one per material, or the balance would leak."""
    broken = {m: dict(v) for m, v in mb.DEFAULT_ROUTING.items()}
    broken["paper"] = {"rdf": 0.50, "recyclable": 0.20}  # sums to 0.70
    with pytest.raises(ValueError, match="sum to 1.0"):
        mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4, routing=broken)


def test_routing_naming_an_unknown_stream_is_rejected():
    broken = {m: dict(v) for m, v in mb.DEFAULT_ROUTING.items()}
    broken["paper"] = {"rdf": 0.5, "plasma": 0.5}
    with pytest.raises(ValueError, match="unknown streams"):
        mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4, routing=broken)


def test_routing_missing_a_material_is_rejected():
    broken = {m: dict(v) for m, v in mb.DEFAULT_ROUTING.items()}
    del broken["paper"]
    with pytest.raises(ValueError, match="missing material"):
        mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4, routing=broken)


def test_default_routing_is_labelled_an_assumption_not_a_citation():
    """The discipline that keeps a guess from reading as a measurement."""
    result = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4)
    assert set(result.routing_provenance.values()) == {mb.USER_ASSUMPTION}
    assert any("assumptions, not measurements" in note for note in result.notes)


def test_an_explicit_routing_table_can_be_marked_cited():
    result = mb.balance(
        comp.PRESETS["mixed-msw"],
        tonnage_t=10.0,
        moisture=0.4,
        routing=mb.DEFAULT_ROUTING,
        provenance={m: mb.CITED for m in comp.MATERIAL_KEYS},
    )
    assert set(result.routing_provenance.values()) == {mb.CITED}
    assert not any("assumptions" in note for note in result.notes)


def test_custom_routing_without_provenance_stays_a_user_assumption():
    """Supplying a routing table is not evidence that anyone published it.

    ``balance()`` labelled every material ``cited`` whenever the caller passed
    its own table, so a hand-edited split could be persisted as a sourced
    value. Provenance must be stated, never assumed from the presence of an
    argument.
    """
    custom = {m: dict(v) for m, v in mb.DEFAULT_ROUTING.items()}
    custom["food"] = {"organic": 1.0}
    result = mb.balance(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4, routing=custom
    )
    assert set(result.routing_provenance.values()) == {mb.USER_ASSUMPTION}


def test_scaling_tonnage_scales_every_stream():
    one = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=1.0, moisture=0.4)
    ten = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4)
    for stream in mb.STREAMS:
        assert ten.streams[stream].tonnes == pytest.approx(one.streams[stream].tonnes * 10.0)


def test_yield_fractions_sum_to_one_across_all_streams():
    result = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4)
    total = sum(result.yield_fraction(s) for s in mb.STREAMS)
    assert total == pytest.approx(1.0, abs=1e-9)


def test_unknown_stream_lookup_raises():
    result = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=1.0, moisture=0.4)
    with pytest.raises(KeyError, match="unknown stream"):
        result.yield_fraction("unicorn")


def test_every_material_contributes_to_some_stream():
    """No material may be silently dropped by the routing table."""
    result = mb.balance(comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.4)
    seen = {m for stream in mb.STREAMS for m in result.streams[stream].by_material}
    expected = {m for m in comp.MATERIAL_KEYS if getattr(comp.PRESETS["mixed-msw"], m) > 0}
    assert expected <= seen
