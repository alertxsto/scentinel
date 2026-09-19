from __future__ import annotations

import pytest

from scentinel.core.gas_data import (
    DEFAULT_SOURCE_GASES,
    available_gases,
    citation,
    default_sources,
    get_gas,
    source_concentration,
)


def test_available_gases_includes_core_set():
    assert {"CO", "CH4", "VOC", "H2S"}.issubset(set(available_gases()))


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
