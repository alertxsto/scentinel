from __future__ import annotations

import pytest

from scentinel.core.gas_data import (
    DEFAULT_SOURCE_GASES,
    GAS_FAMILIES,
    HEADLINE_GASES,
    GasApplicability,
    applicability,
    available_gases,
    citation,
    default_sources,
    get_gas,
    offered_gases,
    regime_concentration,
    short_label,
    source_concentration,
)


def test_every_offered_gas_has_an_applicability():
    for key in available_gases():
        app = applicability(key)
        assert isinstance(app, GasApplicability), key
        assert app.phases, key
        assert app.source, key
        assert app.uncertainty, key


def test_methane_is_not_offered_for_a_fresh_load():
    """The whole reason a truck bin is not a landfill: CH4 is absent below the phase."""
    assert "CH4" not in offered_gases(8.0)
    assert "CH4" in offered_gases(24.0 * 365 * 5)


def test_phase_one_offers_only_phase_one_gases():
    """A fresh load offers the odour/trace gases but not the methanogenic ones.

    CO2 is not a selectable source — it is reported by the generation model — so
    the offered set here is the catalogue gases that apply to phase I.
    """
    offered = offered_gases(8.0)
    assert "H2S" in offered
    assert "VOC" in offered
    assert all("I" in applicability(g).phases for g in offered)

def test_a_fresh_load_offers_only_gases_with_a_fresh_waste_basis():
    offered = set(offered_gases(8.0))
    assert "PERCHLOROETHYLENE" not in offered
    assert "BENZENE" not in offered
    assert "DICHLORODIFLUOROMETHANE" not in offered
    assert {"CO", "H2S", "VOC"} <= offered


def test_an_aged_load_offers_the_full_landfill_catalogue():
    assert len(offered_gases(24.0 * 365 * 5)) > len(offered_gases(8.0))


def test_every_unoffered_fresh_gas_states_the_missing_basis():
    app = applicability("BENZENE")
    assert "I" not in app.phases
    assert "fresh" in app.uncertainty.lower()



def test_unknown_gas_applicability_raises():
    with pytest.raises(KeyError):
        applicability("UNOBTAINIUM")


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
    # Isomers share a formula and therefore a diffusion volume, so their values
    # legitimately coincide (1,1- and 1,2-dichloroethane, the dichlorobenzenes).
    # What must hold is that the correlation produces a real spread, not that
    # every one of 47 gases is numerically unique.
    assert len(set(values.values())) >= 35, values
    # Heavier molecules diffuse more slowly, so the ordering must be real.
    assert values["ETHANE"] > values["BENZENE"] > values["VOC"]
    # Every gas must have a physically plausible diffusivity in air at 25 C:
    # roughly 5e-6 (heavy halocarbons) to 3e-5 (light gases) m^2/s.
    for key, value in values.items():
        assert 5e-6 <= value <= 3e-5, (key, value)


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


# -- full AP-42 catalogue ------------------------------------------------------


def test_the_whole_cited_catalogue_is_selectable():
    """Every Table 2.4-1 species with a usable value, plus the Table 2.4-2 splits."""
    assert len(DEFAULT_SOURCE_GASES) == 47
    assert len(set(DEFAULT_SOURCE_GASES)) == 47, "duplicate gas key"


def test_every_selectable_gas_resolves_completely():
    """A gas in the list that cannot be read would break the UI at selection time."""
    for key in DEFAULT_SOURCE_GASES:
        spec = get_gas(key)
        assert spec.name, key
        assert spec.mw_g_mol > 0, key
        assert spec.diffusivity_m2_s > 0, key
        assert spec.default_conc_ppmv > 0, key
        assert spec.basis, key
        assert "AP-42" in spec.basis or "LMOP" in spec.basis, (key, spec.basis)


def test_footnote_marked_cells_parse_instead_of_raising():
    """The cells that a bare float() rejected, now that all 47 are selectable."""
    assert get_gas("CHLOROFORM").default_conc_ppmv == pytest.approx(0.03)
    assert get_gas("CARBON_TETRACHLORIDE").default_conc_ppmv == pytest.approx(0.004)
    assert get_gas("ETHYLENE_DIBROMIDE").default_conc_ppmv == pytest.approx(0.001)


def test_gas_families_cover_the_catalogue_without_gaps_or_duplicates():
    flat = [gas for family in GAS_FAMILIES.values() for gas in family]
    assert len(flat) == len(set(flat)), "a gas appears in two families"
    assert set(flat) == set(DEFAULT_SOURCE_GASES)


def test_every_gas_has_a_short_label():
    """The UI shows these in dense rows; a missing one falls back to the full name."""
    for key in DEFAULT_SOURCE_GASES:
        assert short_label(key), key


def test_short_labels_are_actually_shorter_or_equal():
    for key in DEFAULT_SOURCE_GASES:
        assert len(short_label(key)) <= max(len(get_gas(key).name), 12), key


def test_the_headline_gases_come_first():
    assert DEFAULT_SOURCE_GASES[:4] == HEADLINE_GASES


def test_a_gas_without_a_co_disposal_alternate_still_resolves():
    """Only benzene/NMOC/toluene carry a cited alternate; the rest must fall back."""
    for key in ("ETHANE", "CHLOROFORM", "PROPANE"):
        assert get_gas(key).alternate_conc_ppmv is None
        # The strict lookup refuses; the resolving one falls back to the base
        # default, which is what the scenario path uses.
        with pytest.raises(KeyError):
            source_concentration(key, regime="co-disposal")
        assert regime_concentration(key, regime="co-disposal") == pytest.approx(
            get_gas(key).default_conc_ppmv
        )


def test_the_splits_that_do_have_alternates_keep_them():
    assert get_gas("BENZENE").alternate_conc_ppmv == pytest.approx(11.0)
    assert get_gas("TOLUENE").alternate_conc_ppmv == pytest.approx(170.0)
    assert get_gas("VOC").alternate_conc_ppmv == pytest.approx(2400.0)
