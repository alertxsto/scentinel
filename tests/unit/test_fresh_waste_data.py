"""The fresh-waste research artifact must be honest about what was extracted.

A paywalled source is recorded as unavailable with a reason, never filled with a
guess. An extracted value carries its unit and its reference.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRESH = ROOT / "docs" / "data" / "fresh_waste_references.json"


def _data() -> dict:
    return json.loads(FRESH.read_text(encoding="utf-8"))


def test_the_artifact_records_a_status_for_every_named_source():
    data = _data()
    assert set(data) == {
        "statheropoulos_2005",
        "waste_management_2017",
        "niosh_3900",
    }
    for name, entry in data.items():
        assert entry["status"] in ("extracted", "reviewed", "unavailable"), name
        assert entry["canonical_url"]
        assert entry["retrieved_utc"]


def test_an_unavailable_source_states_why_and_estimates_nothing():
    data = _data()
    for name in ("waste_management_2017",):
        entry = data[name]
        assert entry["status"] == "unavailable"
        assert entry["reason"]
        assert "values" not in entry


def test_extracted_values_carry_a_unit_and_a_reference():
    entry = _data()["statheropoulos_2005"]
    assert entry["status"] == "extracted"
    assert entry["values"]
    for value in entry["values"]:
        assert value["unit"]
        assert value["reference"]
        assert value["median_ug_per_m3"] > 0


def test_the_recorded_hash_matches_the_raw_artifact():
    entry = _data()["statheropoulos_2005"]
    raw = ROOT / entry["raw_artifact"]
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    assert digest == entry["scraped_text_sha256"]


def test_limonene_is_recorded_with_its_measured_value():
    """The terpene the basis document names as a fresh-bin marker."""
    values = {v["species"]: v for v in _data()["statheropoulos_2005"]["values"]}
    assert "limonene" in values
    assert values["limonene"]["median_ug_per_m3"] == pytest.approx(334.9)
