"""Accuracy gates for the generation engine.

Every expected value here is derived independently of the implementation: from
the regulation's own equation, from the cited table, or from arithmetic that can
be checked by hand. A test that merely restated the code would prove nothing.
"""

from __future__ import annotations

import math

import pytest

from scentinel.core import composition as comp
from scentinel.core import generation as gen

# -- composition -------------------------------------------------------------


def test_presets_are_valid_compositions():
    for name, preset in comp.PRESETS.items():
        assert abs(preset.total - 1.0) < 1e-9, name
        assert all(0.0 <= value <= 1.0 for value in preset.as_dict().values()), name


def test_composition_rejects_a_bad_sum_and_names_the_gap():
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        comp.WasteComposition(food=0.5, paper=0.4)


def test_composition_rejects_an_out_of_range_fraction():
    with pytest.raises(ValueError, match="must be in"):
        comp.WasteComposition(food=1.5, inert=-0.5)


def test_weighted_doc_matches_hand_arithmetic():
    """DOC is the mass-weighted sum of the table values."""
    c = comp.WasteComposition(food=0.5, paper=0.3, inert=0.2)
    # 0.5*0.15 + 0.3*0.40 + 0.2*0.00 = 0.075 + 0.12 = 0.195
    assert c.weighted_doc() == pytest.approx(0.195)


def test_inert_carries_no_carbon():
    c = comp.WasteComposition(inert=1.0)
    assert c.weighted_doc() == 0.0
    assert c.degradable_fraction() == pytest.approx(0.0)


# -- phase -------------------------------------------------------------------


@pytest.mark.parametrize(
    "age_h,expected",
    [
        (0.0, "I"),
        (8.0, "I"),          # a truck bin loaded this morning
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


# -- decay -------------------------------------------------------------------


def test_decay_footnote_selects_the_cited_endpoints():
    """Table HH-1 footnote c: wetter material uses the greater k."""
    food = comp.MATERIALS["food"]
    assert comp.decay_rate(food, comp.DRY_REFERENCE) == pytest.approx(food.k_low)
    assert comp.decay_rate(food, comp.WET_REFERENCE) == pytest.approx(food.k_high)
    # Beyond the endpoints the table's values still apply; no extrapolation.
    assert comp.decay_rate(food, 0.0) == pytest.approx(food.k_low)
    assert comp.decay_rate(food, 1.0) == pytest.approx(food.k_high)


def test_decay_is_monotonic_in_moisture():
    food = comp.MATERIALS["food"]
    rates = [comp.decay_rate(food, m) for m in (0.1, 0.3, 0.5, 0.7)]
    assert rates == sorted(rates)
    assert rates[0] < rates[-1]


def test_inert_never_decays():
    assert comp.decay_rate(comp.MATERIALS["inert"], 0.9) == 0.0


# -- ultimate yield: checked against the regulation's own arithmetic ---------


def test_ultimate_yield_matches_hand_calculation():
    """DOC 0.31, MCF 1, DOCF 0.5, F 0.5, 16/12 -> 103.3 kg CH4 per tonne.

    This is the number written in docs/gas-composition-basis.md 3.2, recomputed
    here from the equation rather than read back from the module.
    """
    doc = 0.31
    expected_kg = 1000.0 * 1.0 * doc * 0.5 * 0.5 * (16.0 / 12.0)
    assert expected_kg == pytest.approx(103.33, abs=0.01)

    # A composition whose weighted DOC is exactly 0.31 must reproduce it.
    c = comp.WasteComposition(paper=0.775, inert=0.225)  # 0.775*0.40 = 0.31
    assert c.weighted_doc() == pytest.approx(doc)
    kg_per_t, m3_per_t = gen.ultimate_methane_yield(c)
    assert kg_per_t == pytest.approx(expected_kg, abs=0.02)
    assert m3_per_t == pytest.approx(expected_kg / 0.7167, abs=0.05)


def test_ultimate_yield_is_zero_for_pure_inert():
    kg, m3 = gen.ultimate_methane_yield(comp.WasteComposition(inert=1.0))
    assert kg == 0.0
    assert m3 == 0.0


# -- decay fraction: the fresh-load claim -----------------------------------


def test_a_truck_bin_produces_almost_no_methane():
    """Measured claim from the basis document 3.1, recomputed here.

    At 24 hours the fastest-decaying material reaches well under 0.1% of its
    ultimate yield. If this ever fails, the model has started disagreeing with
    the physics that motivated it.
    """
    fastest = comp.MATERIALS["food"].k_high  # 0.185 /yr
    fraction = gen.decay_fraction(fastest, 24.0)
    assert fraction < 0.001
    assert fraction == pytest.approx(0.000507, abs=5e-6)


def test_decay_fraction_matches_the_closed_form():
    k = 0.06
    for age_h in (24.0, 720.0, 8760.0):
        expected = 1.0 - math.exp(-k * age_h / gen.HOURS_PER_YEAR)
        assert gen.decay_fraction(k, age_h) == pytest.approx(expected)


def test_decay_fraction_is_bounded_and_monotonic():
    values = [gen.decay_fraction(0.185, h) for h in (0, 24, 720, 8760, 87600)]
    assert values[0] == 0.0
    assert values == sorted(values)
    assert all(0.0 <= v < 1.0 for v in values)


def test_decay_fraction_rejects_negative_inputs():
    with pytest.raises(ValueError, match="k_per_year"):
        gen.decay_fraction(-1.0, 24.0)
    with pytest.raises(ValueError, match="age_h"):
        gen.decay_fraction(0.1, -1.0)


# -- generation: the ceiling invariant --------------------------------------


def test_methane_fraction_never_exceeds_the_ap42_ceiling():
    """The defect that motivated this module: the old rule reached 85%."""
    for name, preset in comp.PRESETS.items():
        for moisture in (0.05, 0.2, 0.4, 0.6, 0.9):
            g = gen.generate(
                preset, tonnage_t=10.0, age_h=24 * 365 * 20, moisture=moisture
            )
            assert g.methane_fraction <= comp.STEADY_STATE_METHANE_CEILING + 1e-9, (
                f"{name} at moisture {moisture} produced "
                f"{g.methane_fraction:.4f} methane"
            )


def test_methane_fraction_matches_the_ap42_steady_state_ratio():
    """CO2 and N2 are tied to CH4 at 40:5, so the mixture sits at exactly 55%.

    The three cited components sum to 100% by volume, which is why the ceiling
    is 0.55 and not 55/95 — N2 is part of the gas.
    """
    g = gen.generate(comp.PRESETS["mixed-msw"], tonnage_t=1.0, age_h=1e6, moisture=0.5)
    assert g.methane_fraction == pytest.approx(comp.STEADY_STATE_METHANE_CEILING, abs=1e-9)
    assert g.methane_fraction == pytest.approx(0.55, abs=1e-9)


def test_a_fresh_load_reports_no_methane_in_its_gas_set():
    g = gen.generate(comp.PRESETS["mixed-msw"], tonnage_t=10.0, age_h=8.0, moisture=0.4)
    assert g.phase == "I"
    assert "CH4" not in g.gases
    assert any("pre-methanogenic" in note for note in g.notes)


def test_generation_scales_linearly_with_tonnage():
    """Twice the waste, twice the gas — no hidden nonlinearity."""
    preset = comp.PRESETS["mixed-msw"]
    one = gen.generate(preset, tonnage_t=1.0, age_h=24 * 365 * 10, moisture=0.4)
    ten = gen.generate(preset, tonnage_t=10.0, age_h=24 * 365 * 10, moisture=0.4)
    assert ten.ch4_kg == pytest.approx(one.ch4_kg * 10.0)
    assert ten.co2_kg == pytest.approx(one.co2_kg * 10.0)


def test_more_moisture_produces_more_gas_at_the_same_age():
    """Footnote c: wetter waste decays faster, so more gas by a given age."""
    preset = comp.PRESETS["mixed-msw"]
    dry = gen.generate(preset, tonnage_t=10.0, age_h=24 * 365 * 2, moisture=0.10)
    wet = gen.generate(preset, tonnage_t=10.0, age_h=24 * 365 * 2, moisture=0.60)
    assert wet.k_per_year > dry.k_per_year
    assert wet.ch4_kg > dry.ch4_kg


def test_age_orders_generation():
    """Older waste has produced more gas. Monotone, no oscillation."""
    preset = comp.PRESETS["mixed-msw"]
    amounts = [
        gen.generate(preset, tonnage_t=10.0, age_h=h, moisture=0.4).ch4_kg
        for h in (24 * 30, 24 * 365, 24 * 365 * 5, 24 * 365 * 30)
    ]
    assert amounts == sorted(amounts)
    assert amounts[0] < amounts[-1]


def test_an_all_inert_load_produces_nothing():
    g = gen.generate(
        comp.WasteComposition(inert=1.0), tonnage_t=10.0, age_h=24 * 365 * 10, moisture=0.5
    )
    assert g.ch4_kg == 0.0
    assert g.co2_kg == 0.0
    assert any("entirely inert" in note for note in g.notes)


def test_zero_tonnage_is_allowed_and_yields_nothing():
    g = gen.generate(comp.PRESETS["mixed-msw"], tonnage_t=0.0, age_h=1000.0, moisture=0.4)
    assert g.ch4_kg == 0.0
    assert g.methane_fraction == 0.0


def test_invalid_inputs_are_rejected():
    preset = comp.PRESETS["mixed-msw"]
    with pytest.raises(ValueError, match="tonnage_t"):
        gen.generate(preset, tonnage_t=-1.0, age_h=10.0, moisture=0.4)
    with pytest.raises(ValueError, match="moisture"):
        gen.generate(preset, tonnage_t=1.0, age_h=10.0, moisture=1.5)
    with pytest.raises(ValueError, match="age_h"):
        gen.generate(preset, tonnage_t=1.0, age_h=-1.0, moisture=0.4)


def test_co2_tracks_methane_at_the_cited_ratio():
    """CO2 mass is (40/55) of the methane's molar amount, in CO2 mass units."""
    ch4_kg = 100.0
    moles_ch4 = ch4_kg / (gen.METHANE_MOLAR_MASS / 1000.0)
    expected = moles_ch4 * (40.0 / 55.0) * (44.009 / 1000.0)
    assert gen.co2_from_ch4(ch4_kg) == pytest.approx(expected)


def test_reported_gases_can_be_overridden_but_never_invented():
    """A caller may narrow the set; the phase still governs what exists."""
    g = gen.generate(
        comp.PRESETS["mixed-msw"],
        tonnage_t=1.0,
        age_h=8.0,
        moisture=0.4,
        gases=("CO2", "H2S"),
    )
    assert g.gases == ("CO2", "H2S")


def test_legacy_waste_types_all_resolve_to_a_preset():
    """Old projects must keep loading; the mapping is total."""
    for name in comp.LEGACY_WASTE_TYPES:
        c, moisture = comp.preset(name)
        assert abs(c.total - 1.0) < 1e-9
        assert 0.0 <= moisture <= 1.0
