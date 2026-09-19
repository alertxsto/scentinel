from __future__ import annotations

import pytest

from scentinel.core.gas_data import (
    DEFAULT_SOURCE_GASES,
    available_gases,
    citation,
    default_sources,
    get_gas,
    regime_concentration,
    source_concentration,
)


def test_available_gases_includes_core_set():
    assert {"CO", "CH4", "VOC", "H2S"}.issubset(set(available_gases()))


def test_added_gases_carry_the_cited_ap42_defaults():
    """Each added gas resolves to its AP-42 table value, weight, and rating."""
    expected = {
        # key: (ppmv, molecular weight, rating)
        "BENZENE": (1.9, 78.11, "B"),
        "TOLUENE": (39.0, 92.13, "A"),
        "ETHANE": (890.0, 30.07, "C"),
        "VINYL_CHLORIDE": (7.3, 62.5, "B"),
        "METHYL_MERCAPTAN": (2.5, 48.11, "C"),
        "DIMETHYL_SULFIDE": (7.8, 62.13, "C"),
    }
    for key, (ppmv, mw, rating) in expected.items():
        spec = get_gas(key)
        assert spec.default_conc_ppmv == pytest.approx(ppmv), key
        assert spec.mw_g_mol == pytest.approx(mw), key
        assert spec.rating == rating, key
        assert "AP-42" in spec.basis, key


def test_the_two_aromatics_carry_their_cited_co_disposal_alternate():
    """Table 2.4-2 splits benzene and toluene by disposal history."""
    assert source_concentration("BENZENE", regime="co-disposal") == pytest.approx(11.0)
    assert source_concentration("TOLUENE", regime="co-disposal") == pytest.approx(170.0)
    assert get_gas("BENZENE").alternate_conc_ppmv == pytest.approx(11.0)
    assert get_gas("TOLUENE").alternate_conc_ppmv == pytest.approx(170.0)


def test_a_gas_without_a_co_disposal_alternate_falls_back_to_its_base_default():
    """Table 2.4-1 has no co-disposal split, so there is nothing to switch to.

    The strict lookup still raises — it must not invent an alternate — but the
    regime lookup the app uses falls back to the base default, so every offered
    gas stays selectable under a co-disposal stream.
    """
    for key in ("ETHANE", "VINYL_CHLORIDE", "METHYL_MERCAPTAN", "DIMETHYL_SULFIDE", "H2S"):
        assert get_gas(key).alternate_conc_ppmv is None, key
        with pytest.raises(KeyError):
            source_concentration(key, regime="co-disposal")
        assert regime_concentration(key, regime="co-disposal") == pytest.approx(
            get_gas(key).default_conc_ppmv
        ), key


def test_every_offered_gas_resolves_under_both_regimes():
    """The panel offers these keys, so neither regime may raise for one."""
    for regime in ("msw-only", "co-disposal"):
        resolved = default_sources(regime)
        assert set(resolved) == set(DEFAULT_SOURCE_GASES), regime
        assert all(value > 0 for value in resolved.values()), regime


def test_diffusivities_are_physically_distinct_and_match_the_fsg_anchors():
    """One FSG correlation for every gas: the values must differ, and be sane.

    The anchors are the published diffusivities the correlation is checked
    against: CO ~1.9e-5, H2S ~1.7e-5, and the hexane proxy ~7.4e-6 m^2/s.
    """
    assert get_gas("CO").diffusivity_m2_s == pytest.approx(1.9e-5, rel=0.05)
    assert get_gas("H2S").diffusivity_m2_s == pytest.approx(1.7e-5, rel=0.05)
    assert get_gas("VOC").diffusivity_m2_s == pytest.approx(7.4e-6, rel=0.05)

    values = {key: get_gas(key).diffusivity_m2_s for key in DEFAULT_SOURCE_GASES}
    assert len(set(values.values())) == len(values), values
    # Heavier molecules diffuse more slowly, so the spread must be real.
    assert values["ETHANE"] > values["BENZENE"] > values["VOC"]


def test_get_gas_carries_properties_and_provenance():
    spec = get_gas("CO")
    assert spec.mw_g_mol == pytest.approx(28.01)
    assert spec.diffusivity_m2_s > 0
    assert spec.default_conc_ppmv == pytest.approx(105.0)
    assert "AP-42" in spec.basis


def test_msw_only_vs_codisposal_voc():
    assert source_concentration("VOC", regime="msw-only") == pytest.approx(550.0)
    assert source_concentration("VOC", regime="co-disposal") == pytest.approx(2400.0)


def test_methane_fraction_is_converted_to_ppmv():
    assert source_concentration("CH4") == pytest.approx(500_000.0)
    assert source_concentration("CH4", regime="co-disposal") == pytest.approx(550_000.0)


def test_default_sources_covers_every_offered_gas():
    sources = default_sources()
    assert set(sources) == set(DEFAULT_SOURCE_GASES)
    assert all(value > 0 for value in sources.values())


def test_citation_mentions_value_and_source():
    text = citation("H2S")
    assert "36" in text
    assert "AP-42" in text


def test_unknown_gas_raises():
    with pytest.raises(KeyError):
        get_gas("NOPE")


def test_unknown_regime_raises():
    with pytest.raises(ValueError):
        source_concentration("CO", regime="whatever")
