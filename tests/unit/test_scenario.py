from __future__ import annotations

import pytest

from scentinel.core.casegen import resolve_sources
from scentinel.core.gas_data import source_concentration
from scentinel.core.scenario import Scenario, auto_concentration_ppmv, waste_spec


def test_default_mixed_msw_auto_matches_cited_ap42():
    scenario = Scenario(gas_sources={"CO": "auto", "VOC": "auto", "H2S": "auto"})
    assert auto_concentration_ppmv(scenario, "CO") == pytest.approx(105.0)
    assert auto_concentration_ppmv(scenario, "VOC") == pytest.approx(550.0)
    assert auto_concentration_ppmv(scenario, "H2S") == pytest.approx(36.0)


def test_co_disposal_uses_cited_alternate_voc_unscaled():
    scenario = Scenario(
        waste_type="co-disposal",
        organic_fraction=0.45,
        gas_sources={"VOC": "auto", "CH4": "auto"},
    )
    assert auto_concentration_ppmv(scenario, "VOC") == pytest.approx(
        source_concentration("VOC", regime="co-disposal")
    )
    assert auto_concentration_ppmv(scenario, "CH4") == pytest.approx(
        source_concentration("CH4", regime="co-disposal")
    )


def test_organic_rich_scales_msw_voc_from_the_50_percent_baseline():
    scenario = Scenario(
        waste_type="organic-rich",
        organic_fraction=0.80,
        gas_sources={"VOC": "auto", "CO": "auto"},
    )
    assert auto_concentration_ppmv(scenario, "VOC") == pytest.approx(550.0 * 0.80 / 0.50)
    assert auto_concentration_ppmv(scenario, "CO") == pytest.approx(105.0)


def test_resolve_sources_applies_the_waste_scale_as_volume_fraction():
    scenario = Scenario(waste_type="rdf-feedstock", organic_fraction=0.25, gas_sources={"VOC": "auto"})
    resolved = resolve_sources(scenario)
    assert resolved["VOC"] == pytest.approx((550.0 * 0.25 / 0.50) * 1e-6)


def test_unknown_waste_type_is_rejected():
    with pytest.raises(ValueError, match="waste_type"):
        Scenario(waste_type="nuclear")


def test_waste_spec_default_gases_are_nonempty():
    assert waste_spec("mixed-msw").default_gases == ("CO", "CH4", "VOC", "H2S")
    assert "VOC" in waste_spec("dry-recyclables").default_gases
