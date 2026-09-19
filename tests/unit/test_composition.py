"""Composition and phase gates: the inputs everything downstream trusts."""

from __future__ import annotations

import pytest

from scentinel.core import composition as comp


def test_every_preset_is_a_valid_composition():
    for name, preset in comp.PRESETS.items():
        assert abs(preset.total - 1.0) < 1e-9, name
        assert all(0.0 <= v <= 1.0 for v in preset.as_dict().values()), name


def test_every_preset_has_a_moisture_value():
    assert set(comp.PRESET_MOISTURE) == set(comp.PRESETS)
    assert all(0.0 <= m <= 1.0 for m in comp.PRESET_MOISTURE.values())


def test_a_bad_sum_is_rejected_and_the_gap_is_named():
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        comp.WasteComposition(food=0.5, paper=0.4)


def test_an_out_of_range_fraction_is_rejected():
    with pytest.raises(ValueError, match="must be in"):
        comp.WasteComposition(food=1.5, inert=-0.5)


def test_a_negative_fraction_is_rejected():
    with pytest.raises(ValueError, match="must be in"):
        comp.WasteComposition(food=-0.1, inert=1.1)


def test_the_tolerance_accepts_float_noise_but_not_a_real_gap():
    """0.1*3 is not exactly 0.3 in binary; the tolerance must cover that."""
    ok = comp.WasteComposition(food=0.1, paper=0.1, inert=0.1, garden=0.7)
    assert abs(ok.total - 1.0) < 1e-9
    with pytest.raises(ValueError):
        comp.WasteComposition(food=0.1, paper=0.1, inert=0.1, garden=0.6)


def test_weighted_doc_matches_hand_arithmetic():
    c = comp.WasteComposition(food=0.5, paper=0.3, inert=0.2)
    # 0.5*0.15 + 0.3*0.40 + 0.2*0.00 = 0.195
    assert c.weighted_doc() == pytest.approx(0.195)


def test_weighted_doc_uses_the_cited_table_values():
    """Each material's DOC must be the Table HH-1 value, not a rounded copy."""
    expected = {
        "food": 0.15,
        "garden": 0.20,
        "paper": 0.40,
        "wood": 0.43,
        "textile": 0.24,
        "diaper": 0.24,
        "sludge": 0.05,
        "inert": 0.00,
    }
    for key, doc in expected.items():
        assert comp.MATERIALS[key].doc == pytest.approx(doc), key


def test_decay_ranges_match_the_cited_table():
    expected = {
        "food": (0.06, 0.185),
        "garden": (0.05, 0.10),
        "paper": (0.04, 0.06),
        "wood": (0.02, 0.03),
        "textile": (0.04, 0.06),
        "diaper": (0.05, 0.10),
        "sludge": (0.06, 0.185),
        "inert": (0.00, 0.00),
    }
    for key, (low, high) in expected.items():
        assert comp.MATERIALS[key].k_low == pytest.approx(low), key
        assert comp.MATERIALS[key].k_high == pytest.approx(high), key


def test_inert_carries_no_carbon_and_never_decays():
    inert = comp.WasteComposition(inert=1.0)
    assert inert.weighted_doc() == 0.0
    assert inert.weighted_decay(0.9) == 0.0
    assert inert.degradable_fraction() == pytest.approx(0.0)


def test_decay_footnote_selects_the_cited_endpoints():
    """Table HH-1 footnote c: wetter material uses the greater k."""
    food = comp.MATERIALS["food"]
    assert comp.decay_rate(food, comp.DRY_REFERENCE) == pytest.approx(food.k_low)
    assert comp.decay_rate(food, comp.WET_REFERENCE) == pytest.approx(food.k_high)
    # Outside the range the table's values still apply; no extrapolation.
    assert comp.decay_rate(food, 0.0) == pytest.approx(food.k_low)
    assert comp.decay_rate(food, 1.0) == pytest.approx(food.k_high)


def test_decay_is_monotonic_in_moisture():
    food = comp.MATERIALS["food"]
    rates = [comp.decay_rate(food, m) for m in (0.1, 0.3, 0.5, 0.7)]
    assert rates == sorted(rates)
    assert rates[0] < rates[-1]


def test_out_of_range_moisture_is_rejected_by_the_decay_rule():
    with pytest.raises(ValueError, match="moisture"):
        comp.decay_rate(comp.MATERIALS["food"], 1.5)
    with pytest.raises(ValueError, match="moisture"):
        comp.decay_rate(comp.MATERIALS["food"], -0.1)


@pytest.mark.parametrize(
    "age_h,expected",
    [
        (0.0, "I"),
        (8.0, "I"),              # a truck bin loaded this morning
        (48.0, "I"),
        (49.0, "II"),
        (24.0 * 60, "II"),
        (24.0 * 120, "III"),
        (24.0 * 400, "IV"),
        (24.0 * 365 * 5, "IV"),  # a mature landfill
    ],
)
def test_phase_follows_holding_time(age_h, expected):
    assert comp.phase_for(age_h) == expected


def test_negative_age_is_rejected():
    with pytest.raises(ValueError, match="negative"):
        comp.phase_for(-1.0)


def test_phase_one_does_not_offer_methane():
    """The whole reason a fresh bin is not a landfill."""
    assert "CH4" not in comp.PHASE_GASES["I"]
    assert "CO2" in comp.PHASE_GASES["I"]
    assert "CH4" in comp.PHASE_GASES["IV"]


def test_every_phase_has_a_gas_set_and_they_are_all_known_phases():
    assert set(comp.PHASE_GASES) == set(comp.PHASES)


def test_the_phase_model_is_a_labelled_assumption():
    """The cutoffs are a documented choice, not a measured constant."""
    m = comp.DEFAULT_PHASE_MODEL
    assert m.boundaries_h == (48.0, 24.0 * 90.0, 24.0 * 365.0)
    assert m.provenance == "model assumption"
    assert "AP-42" in m.basis
    assert m.uncertainty


def test_a_custom_phase_model_moves_the_boundaries():
    fast = comp.PhaseModel(
        boundaries_h=(1.0, 2.0, 3.0),
        provenance="user input",
        basis="test",
        uncertainty="test",
    )
    assert comp.phase_for(1.5, model=fast) == "II"
    assert comp.phase_for(1.5) == "I"


def test_preset_lookup_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="unknown waste preset"):
        comp.preset("unicorn")


def test_legacy_waste_types_all_resolve():
    """Old projects and manifests must keep loading."""
    for name in comp.LEGACY_WASTE_TYPES:
        c, moisture = comp.preset(name)
        assert abs(c.total - 1.0) < 1e-9
        assert 0.0 <= moisture <= 1.0


def test_material_keys_and_the_dataclass_fields_stay_in_step():
    """A material added to one and not the other would silently drop mass."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(comp.WasteComposition)}
    assert set(comp.MATERIAL_KEYS) <= fields
    assert set(comp.MATERIALS) == set(comp.MATERIAL_KEYS)
