"""Build the Scentinel gas database from scraped AP-42 data.

Reads docs/data/ap-42-chapter-2-section-4-tables-final.xlsx (downloaded from EPA)
and emits src/scentinel/core/gas_defaults.py with cited defaults.

Usage:
    .venv/bin/python scripts/build_gas_data.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "docs" / "data" / "ap-42-chapter-2-section-4-tables-final.xlsx"
OUT = ROOT / "src" / "scentinel" / "core" / "gas_defaults.py"

# Physical properties at 25 C, 1 atm. Diffusivities are **computed**, not
# transcribed: every gas goes through the Fuller-Schettler-Giddings correlation
#
#   D_AB [cm^2/s] = 0.00143 T^1.75 / (P sqrt(M_AB) (V_A^(1/3) + V_B^(1/3))^2)
#   M_AB = 2 / (1/M_A + 1/M_B)
#
# with the air side as component B. One correlation for every gas keeps the
# table self-consistent: published per-gas values come from different
# measurement sets, so mixing them would make the gases differ by method as
# well as by molecule. See docs/references.md for the citations.

#: Atomic diffusion volumes [cm^3] from Reid, Prausnitz & Poling, *The
#: Properties of Gases and Liquids*, 4th ed., Table 11-1.
ATOMIC_DIFFUSION_VOLUMES = {
    "C": 15.9,
    "H": 2.31,
    "O": 6.11,
    "N": 12.7,
    "F": 16.5,
    "Cl": 21.0,
    "Br": 26.7,
    "I": 32.9,
    "S": 20.1,
}

#: An aromatic ring is not additive in Table 11-1: 18.3 cm^3 is subtracted per
#: ring. Benzene and toluene each carry one.
AROMATIC_RING_VOLUME_CM3 = 18.3

#: Molecular formula per gas, as element counts plus the aromatic ring count.
#: ``VOC`` is the hexane proxy the AP-42 NMOC default is expressed as.
MOLECULAR_FORMULAS: dict[str, tuple[dict[str, int], int]] = {
    "CO": ({"C": 1, "O": 1}, 0),
    "CH4": ({"C": 1, "H": 4}, 0),
    "VOC": ({"C": 6, "H": 14}, 0),
    "H2S": ({"H": 2, "S": 1}, 0),
    "BENZENE": ({"C": 6, "H": 6}, 1),
    "TOLUENE": ({"C": 7, "H": 8}, 1),
    "ETHANE": ({"C": 2, "H": 6}, 0),
    "VINYL_CHLORIDE": ({"C": 2, "H": 3, "Cl": 1}, 0),
    "METHYL_MERCAPTAN": ({"C": 1, "H": 4, "S": 1}, 0),
    "DIMETHYL_SULFIDE": ({"C": 2, "H": 6, "S": 1}, 0),
}

#: FSG reference conditions, and the air side of the binary pair (component B).
FSG_TEMPERATURE_K = 298.15
FSG_PRESSURE_BAR = 1.01325
FSG_COEFFICIENT = 0.00143
AIR_MW_G_MOL = 28.96
AIR_DIFFUSION_VOLUME_CM3 = 19.7
CM2_PER_M2 = 1.0e4


def diffusion_volume(formula: dict[str, int], aromatic_rings: int = 0) -> float:
    """Additive FSG diffusion volume [cm^3] for one molecular formula."""
    volume = sum(
        ATOMIC_DIFFUSION_VOLUMES[element] * count for element, count in formula.items()
    )
    return volume - AROMATIC_RING_VOLUME_CM3 * aromatic_rings


def fsg_diffusivity(mw_g_mol: float, key: str) -> float:
    """Diffusivity of ``key`` in air [m^2/s] at 25 C, 1 atm, 3 significant digits.

    Sanity anchors for the correlation, from the same table: CO ~1.9e-5,
    H2S ~1.7e-5, hexane ~7.4e-6 m^2/s.
    """
    if key not in MOLECULAR_FORMULAS:
        raise KeyError(f"{key} has no molecular formula in MOLECULAR_FORMULAS")
    formula, rings = MOLECULAR_FORMULAS[key]
    volume_cm3 = diffusion_volume(formula, rings)
    m_ab = 2.0 / (1.0 / mw_g_mol + 1.0 / AIR_MW_G_MOL)
    d_cm2_s = (
        FSG_COEFFICIENT
        * FSG_TEMPERATURE_K**1.75
        / (
            FSG_PRESSURE_BAR
            * math.sqrt(m_ab)
            * (volume_cm3 ** (1.0 / 3.0) + AIR_DIFFUSION_VOLUME_CM3 ** (1.0 / 3.0)) ** 2
        )
    )
    return float(f"{d_cm2_s / CM2_PER_M2:.3g}")


#: Display name and molecular weight [g/mol] per gas, in the order the generated
#: table lists them. The weights are the AP-42 table values; the names are for
#: the UI and the provenance strings.
GAS_IDENTITY = {
    "CO": ("Carbon monoxide", 28.01),
    "CH4": ("Methane", 16.04),
    "VOC": ("Non-methane organic compounds (as hexane proxy)", 86.18),
    "H2S": ("Hydrogen sulfide", 34.08),
    "BENZENE": ("Benzene", 78.11),
    "TOLUENE": ("Toluene", 92.13),
    "ETHANE": ("Ethane", 30.07),
    "VINYL_CHLORIDE": ("Vinyl chloride", 62.5),
    "METHYL_MERCAPTAN": ("Methyl mercaptan", 48.11),
    "DIMETHYL_SULFIDE": ("Dimethyl sulfide (methyl sulfide)", 62.13),
}

#: Physical properties at 25 C, 1 atm. Every ``diffusivity_m2_s`` is computed by
#: :func:`fsg_diffusivity`; no diffusivity here is a transcribed literature value.
GAS_PROPERTIES = {
    key: {
        "name": name,
        "mw_g_mol": mw_g_mol,
        "diffusivity_m2_s": fsg_diffusivity(mw_g_mol, key),
    }
    for key, (name, mw_g_mol) in GAS_IDENTITY.items()
}

# Source concentrations, ppmv unless noted. Values cross-checked against the
# final AP-42 Ch.2.4 PDF (docs/data/c2s4_2024_final.pdf).
SOURCE_DEFAULTS = {
    "CO": {
        "conc_ppmv": 105,
        "basis": "AP-42 Final Factors: uncontrolled CO, parts per million (ref 98)",
        "rating": "Minimally representative",
    },
    "CH4": {
        "fraction_by_volume": 0.5,
        "basis": "EPA LMOP: LFG ~50% CH4 by volume",
        "alternate_fraction": 0.55,
        "alternate_basis": "AP-42 Ch.2.4 steady-state: ~55% CH4, 40% CO2, 5% N2",
    },
    "VOC": {
        "conc_ppmv": 550,
        "basis": "AP-42 Table 2.4-2: NMOC as hexane, no/unknown co-disposal, 1992+",
        "alternate_conc_ppmv": 2400,
        "alternate_basis": "AP-42 Table 2.4-2: NMOC as hexane, co-disposal (pre 1992)",
    },
    "H2S": {
        "conc_ppmv": 36,
        "basis": "AP-42 Table 2.4-1: default concentration",
        "rating": "B",
    },
}

#: Where each *added* gas's default lives in the workbook, so the value, the
#: rating, and the basis string are read out of AP-42 rather than transcribed.
#: ``condition`` selects the row when one table carries several for the same
#: pollutant (Table 2.4-2 splits benzene and toluene by co-disposal history);
#: ``alternate_condition`` is the co-disposal counterpart, when the table has
#: one. A gas with no alternate is legitimate — it then falls back to the base
#: default under a co-disposal stream instead of raising.
AP42_SOURCE_ROWS: dict[str, dict[str, str]] = {
    "BENZENE": {
        "table": "Table 2.4-2",
        "name": "Benzene",
        "condition": "No or Unknown co-disposal",
        "alternate_condition": "Co-disposal",
    },
    "TOLUENE": {
        "table": "Table 2.4-2",
        "name": "Toluene",
        "condition": "No or Unknown co-disposal",
        "alternate_condition": "Co-disposal",
    },
    "ETHANE": {"table": "Table 2.4-1", "name": "Ethane"},
    "VINYL_CHLORIDE": {"table": "Table 2.4-1", "name": "Vinyl chloride"},
    "METHYL_MERCAPTAN": {"table": "Table 2.4-1", "name": "Methyl mercaptan"},
    "DIMETHYL_SULFIDE": {"table": "Table 2.4-1", "name": "Dimethyl sulfide"},
}


def read_ap42() -> dict:
    wb = openpyxl.load_workbook(XLSX, data_only=True)

    ws = wb["Final Factors"]
    ppmv_factors = {}
    for row in ws.iter_rows(values_only=True):
        if not row or not row[2] or not row[3]:
            continue
        units = str(row[3]).strip().upper()
        activity = str(row[4] or "").upper()
        if units == "PARTS" and "MILLION PARTS" in activity:
            # column 7 is "Factor"; column 6 is "Composite Test Rating"
            ppmv_factors[str(row[2]).strip()] = row[7]

    trace = {}
    ws2 = wb["Table 2.4-1"]
    for row in ws2.iter_rows(values_only=True):
        if row and row[0] and row[1] is not None:
            trace[str(row[0]).strip()] = {
                "mw_g_mol": row[1],
                "conc_ppmv": row[2],
                "rating": row[3],
            }

    table_242 = []
    ws3 = wb["Table 2.4-2"]
    for row in ws3.iter_rows(values_only=True):
        if row and row[0] and row[1] is not None and row[2] is not None:
            table_242.append(
                {
                    "pollutant": str(row[0]).strip(),
                    "mw_g_mol": row[1],
                    "conc_ppmv": row[2],
                    "rating": row[3],
                }
            )

    return {"ppmv_factors": ppmv_factors, "trace_compounds": trace, "table_242": table_242}


def ap42_condition(pollutant: str) -> str:
    """The disposal condition from a Table 2.4-2 pollutant label.

    The table spells a row as ``"Benzene<footnote> - <condition>"``, so the
    condition is what follows the first ``" - "``.
    """
    _, separator, condition = pollutant.partition(" - ")
    return condition.strip() if separator else ""


def ap42_row(ap42: dict, spec: dict[str, str], condition: str | None = None) -> dict:
    """One AP-42 row for a gas, optionally narrowed by its disposal condition.

    Raises rather than returning a partial row: a missing pollutant or a
    condition that matches nothing would otherwise silently drop a cited default
    out of the generated table.
    """
    table = spec["table"]
    if table == "Table 2.4-2":
        candidates = [
            row for row in ap42["table_242"] if row["pollutant"].startswith(spec["name"])
        ]
    else:
        # Table 2.4-1 spells some names with a trailing footnote marker
        # ("Vinyl chloridea"), so match on the name as a prefix.
        candidates = [
            {"pollutant": name, **values}
            for name, values in ap42["trace_compounds"].items()
            if name.startswith(spec["name"])
        ]

    if condition is not None:
        # Exact match on the condition field: "Co-disposal" is a substring of
        # "No or Unknown co-disposal", so a substring test would select both.
        candidates = [
            row for row in candidates if ap42_condition(row["pollutant"]).lower() == condition.lower()
        ]
    if not candidates:
        wanted = f"{spec['name']!r} ({condition})" if condition else f"{spec['name']!r}"
        raise KeyError(f"no {wanted} row in {table}")
    if len(candidates) > 1:
        raise KeyError(f"{spec['name']!r} matches {len(candidates)} rows in {table}")
    return candidates[0]


def ap42_source_default(ap42: dict, key: str) -> dict:
    """The cited AP-42 default for one added gas, as a ``SOURCE_DEFAULTS`` entry."""
    spec = AP42_SOURCE_ROWS[key]
    table = spec["table"]
    row = ap42_row(ap42, spec, spec.get("condition"))
    condition = spec.get("condition")
    basis = f"AP-42 {table}: default concentration"
    if condition:
        basis = f"AP-42 {table}: {spec['name']}, {condition}"
    entry = {
        "conc_ppmv": row["conc_ppmv"],
        "basis": basis,
        "rating": row["rating"],
    }
    alternate_condition = spec.get("alternate_condition")
    if alternate_condition:
        alternate = ap42_row(ap42, spec, alternate_condition)
        entry["alternate_conc_ppmv"] = alternate["conc_ppmv"]
        entry["alternate_basis"] = f"AP-42 {table}: {spec['name']}, {alternate_condition}"
    return entry


def build_source_defaults(ap42: dict) -> dict:
    """``SOURCE_DEFAULTS`` plus every AP-42-sourced gas, in display order."""
    defaults = {key: dict(value) for key, value in SOURCE_DEFAULTS.items()}
    for key in GAS_IDENTITY:
        if key not in defaults:
            defaults[key] = ap42_source_default(ap42, key)
    return defaults


def build_gas_properties(ap42: dict) -> dict:
    """``GAS_PROPERTIES``, with the molecular weight checked against AP-42.

    The workbook is the authority for molecular weight; a disagreement means the
    hand-written identity table has drifted from the source, so it raises rather
    than quietly generating a table that cites a weight it does not use.
    """
    properties = {key: dict(value) for key, value in GAS_PROPERTIES.items()}
    for key, spec in AP42_SOURCE_ROWS.items():
        row = ap42_row(ap42, spec, spec.get("condition"))
        if abs(float(row["mw_g_mol"]) - properties[key]["mw_g_mol"]) > 0.005:
            raise ValueError(
                f"{key} molecular weight {properties[key]['mw_g_mol']} disagrees with "
                f"{spec['table']} ({row['mw_g_mol']})"
            )
    return properties


def build() -> dict:
    ap42 = read_ap42()
    properties = build_gas_properties(ap42)
    defaults = build_source_defaults(ap42)

    lines = [
        '"""Auto-generated by scripts/build_gas_data.py. Do not edit by hand."""',
        "",
        "# Data sources:",
        "#   EPA AP-42 Ch.2.4 final (Aug 2024): docs/data/c2s4_2024_final.pdf",
        "#   EPA AP-42 tables: docs/data/ap-42-chapter-2-section-4-tables-final.xlsx",
        "#   EPA LMOP landfill gas basics: https://www.epa.gov/lmop/basic-information-about-landfill-gas",
        "#",
        "# Diffusivities are computed by the Fuller-Schettler-Giddings correlation",
        "# from atomic diffusion volumes in Reid, Prausnitz & Poling,",
        "# 'The Properties of Gases and Liquids', 4th ed., Table 11-1.",
        "",
        "# Physical properties at 25 C, 1 atm. Every diffusivity is computed with",
        "# Fuller-Schettler-Giddings from atomic diffusion volumes in Reid,",
        "# Prausnitz & Poling, 'The Properties of Gases and Liquids', 4th ed.,",
        "# Table 11-1 (aromatic rings: -18.3 cm^3 each).",
        f"GAS_PROPERTIES = {json.dumps(properties, indent=4)}",
        "",
        f"SOURCE_DEFAULTS = {json.dumps(defaults, indent=4)}",
        "",
        f"AP42_TRACE_COMPOUNDS = {json.dumps(ap42['trace_compounds'], indent=4)}",
        "",
        f"AP42_TABLE_2_4_2 = {json.dumps(ap42['table_242'], indent=4)}",
        "",
        f"AP42_UNCONTROLLED_PPMV_FACTORS = {json.dumps(ap42['ppmv_factors'], indent=4)}",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[saved] {OUT}")
    return defaults


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, indent=2))
