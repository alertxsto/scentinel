from __future__ import annotations

import pytest

from scentinel.core.casegen import resolve_sources
from scentinel.core.gas_data import source_concentration
from scentinel.core.scenario import (
    WASTE_TYPES,
    Scenario,
    auto_concentration_ppmv,
    waste_spec,
)


def test_default_mixed_msw_auto_matches_cited_ap42():
    scenario = Scenario(gas_sources={"CO": "auto", "VOC": "auto", "H2S": "auto"})
    assert auto_concentration_ppmv(scenario, "CO") == pytest.approx(105.0)
    assert auto_concentration_ppmv(scenario, "VOC") == pytest.approx(550.0)
    assert auto_concentration_ppmv(scenario, "H2S") == pytest.approx(36.0)


def test_co_disposal_uses_cited_alternate_voc():
    """Trace species keep their cited table values; only decay products are computed."""
    scenario = Scenario(waste_type="co-disposal", gas_sources={"VOC": "auto"})
    assert auto_concentration_ppmv(scenario, "VOC") == pytest.approx(
        source_concentration("VOC", regime="co-disposal")
    )


def test_trace_species_do_not_scale_with_organic_fraction():
    """The removed rule multiplied VOC/H2S by organic/0.50 and had no citation.

    Trace concentrations now come straight from the cited table. The organic
    fraction is still exposed (it is derived from the composition) but it no
    longer scales anything, which is what this asserts.
    """
    organic = Scenario(waste_type="organic-rich", gas_sources={"VOC": "auto"})
    mixed = Scenario(waste_type="mixed-msw", gas_sources={"VOC": "auto"})
    assert auto_concentration_ppmv(organic, "VOC") == pytest.approx(
        source_concentration("VOC", regime="msw-only")
    )
    assert auto_concentration_ppmv(organic, "VOC") == auto_concentration_ppmv(mixed, "VOC")


def test_a_fresh_load_has_no_methane_source():
    """The defect the composition model fixed: CH4 for waste loaded hours ago."""
    scenario = Scenario(waste_type="mixed-msw", age_h=8.0, gas_sources={"CH4": "auto"})
    assert auto_concentration_ppmv(scenario, "CH4") == pytest.approx(0.0)
    assert "CH4" not in scenario.generated_gases


def test_an_aged_load_reaches_the_cited_steady_state_methane():
    scenario = Scenario(waste_type="mixed-msw", age_h=24.0 * 365 * 30, gas_sources={"CH4": "auto"})
    assert auto_concentration_ppmv(scenario, "CH4") == pytest.approx(550_000.0, rel=1e-6)


def test_generated_methane_never_exceeds_the_ap42_ceiling():
    from scentinel.core.composition import STEADY_STATE_METHANE_CEILING

    for waste_type in WASTE_TYPES:
        for age_h in (8.0, 24 * 100, 24 * 365 * 50):
            scenario = Scenario(waste_type=waste_type, age_h=age_h)
            ppmv = auto_concentration_ppmv(scenario, "CH4")
            assert ppmv <= STEADY_STATE_METHANE_CEILING * 1e6 + 1.0, (waste_type, age_h)


def test_resolve_sources_carries_the_generated_value_as_a_volume_fraction():
    scenario = Scenario(waste_type="mixed-msw", age_h=24.0 * 365 * 30, gas_sources={"CH4": "auto"})
    resolved = resolve_sources(scenario)
    assert resolved["CH4"] == pytest.approx(0.55, rel=1e-6)


def test_moisture_changes_the_generated_source():
    """The input that used to be dead now moves the result."""
    dry = Scenario(waste_type="mixed-msw", age_h=24.0 * 365, moisture_fraction=0.10)
    wet = Scenario(waste_type="mixed-msw", age_h=24.0 * 365, moisture_fraction=0.60)
    assert auto_concentration_ppmv(wet, "CH4") > auto_concentration_ppmv(dry, "CH4")


def test_age_and_moisture_are_validated():
    with pytest.raises(ValueError, match="age_h"):
        Scenario(age_h=-1.0)
    with pytest.raises(ValueError, match="moisture_fraction"):
        Scenario(moisture_fraction=1.5)


def test_unknown_waste_type_is_rejected():
    with pytest.raises(ValueError, match="waste_type"):
        Scenario(waste_type="nuclear")


def test_a_no_alternate_gas_under_a_co_disposal_stream_falls_back():
    """AP-42 splits only benzene/NMOC/toluene; the rest keep their base default.

    Selecting an added trace gas under the co-disposal stream must resolve to a
    cited number rather than raising, otherwise the gas would be unselectable in
    the panel for that waste type.
    """
    scenario = Scenario(waste_type="co-disposal", gas_sources={"ETHANE": "auto"})

    assert auto_concentration_ppmv(scenario, "ETHANE") == pytest.approx(890.0)
    assert auto_concentration_ppmv(scenario, "ETHANE") == pytest.approx(
        source_concentration("ETHANE", regime="msw-only")
    )
    # The gases AP-42 does split still switch to their cited alternate.
    assert auto_concentration_ppmv(scenario, "BENZENE") == pytest.approx(11.0)
    assert auto_concentration_ppmv(scenario, "TOLUENE") == pytest.approx(170.0)
    assert resolve_sources(scenario)["ETHANE"] == pytest.approx(890e-6)


def test_waste_spec_default_gases_are_nonempty():
    assert waste_spec("mixed-msw").default_gases == ("CO", "CH4", "VOC", "H2S")
    assert "VOC" in waste_spec("dry-recyclables").default_gases
