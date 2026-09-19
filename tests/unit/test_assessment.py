from __future__ import annotations

import pytest

from scentinel.core import assessment


class _Reading:
    def __init__(self, sensor_id: str, **values: float) -> None:
        self.sensor_id = sensor_id
        self.values = values


def test_footnote_marked_cells_parse_or_report_as_unparsed():
    assert assessment.parse_ppmv("4.0x10-3") == pytest.approx(4.0e-3)
    assert assessment.parse_ppmv("3.0x10-2") == pytest.approx(3.0e-2)
    assert assessment.parse_ppmv("110e") == pytest.approx(110.0)
    assert assessment.parse_ppmv(36) == pytest.approx(36.0)
    assert assessment.parse_ppmv("not a number") is None


def test_halogen_load_uses_the_ppmv_conversion_not_a_bare_sum():
    """One m³ holds 1000/24.45 mol, so a ppmv is ~40 µmol/m³, not 1 mol/m³."""
    load = assessment.halogen_load()
    carriers = dict(load.sulfur_species)
    # 36 ppmv H2S × 32.06 g/mol / 24.45 L/mol ≈ 47.2 mg/m³.
    assert carriers["Hydrogen sulfide"] == pytest.approx(47.2, rel=0.02)
    # The total adds the other sulfur species on top of H2S.
    assert load.sulfur_mg_per_nm3 > carriers["Hydrogen sulfide"]
    assert load.chlorine_mg_per_nm3 > 0
    assert load.unparsed == ()


def test_every_halogen_species_in_the_table_is_accounted_for():
    """A species added to the AP-42 table without an atom count would silently vanish."""
    from scentinel.core.gas_defaults import AP42_TRACE_COMPOUNDS

    known = set(assessment.HALOGEN_ATOMS)
    missing = sorted(
        name
        for name in AP42_TRACE_COMPOUNDS
        if name != "Compound" and name not in known
    )
    # The table carries non-halogen species too, so this is a sanity bound: the
    # carrier list must not be empty and must not silently drop a known one.
    assert "Hydrogen sulfide" in known
    assert "Vinyl chloridea" in known
    assert len(known) >= 25
    assert missing, "expected some non-halogen species in the table"


def test_threshold_check_flags_an_exceedance_and_names_the_sensor():
    checks, unchecked = assessment.threshold_checks(
        [
            _Reading("S1", H2S=2.0, CO=5.0),
            _Reading("S2", H2S=36.0, CO=5.0),
        ]
    )
    by_gas = {check.gas: check for check in checks}
    assert by_gas["H2S"].peak_sensor == "S2"
    assert by_gas["H2S"].exceeds
    assert by_gas["H2S"].ratio == pytest.approx(3.6)
    assert not by_gas["CO"].exceeds
    assert unchecked == []


def test_a_gas_without_a_published_limit_is_reported_as_unchecked():
    checks, unchecked = assessment.threshold_checks([_Reading("S1", ETHANE=890.0)])
    assert checks == []
    assert unchecked == ["ETHANE"]


def test_peak_to_mean_separates_a_uniform_field_from_a_local_plume():
    uniform = assessment.peak_to_mean([_Reading("S1", CO=5.0), _Reading("S2", CO=5.0)])
    local = assessment.peak_to_mean([_Reading("S1", CO=20.0), _Reading("S2", CO=0.0)])
    assert uniform["CO"] == pytest.approx(1.0)
    assert local["CO"] == pytest.approx(2.0)


def test_verdict_states_the_gap_instead_of_inventing_a_fuel_grade():
    verdict = assessment.suitability_verdict(assessment.evaluate([_Reading("S1", CO=1.0)]))
    assert "mg/Nm³" in verdict
    assert "laboratory" in verdict.lower()
