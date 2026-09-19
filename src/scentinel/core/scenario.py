"""Scenario parameters: wind, waste stream, ventilation, and per-gas sources.

The waste stream is described by a :class:`~scentinel.core.composition.WasteComposition`
and a holding time. Gases that the decomposition model produces — methane and
carbon dioxide — take their source strength from that model, so a fresh load
carries no methane and an aged one carries the cited steady-state fraction. Trace
species keep their AP-42 Table 2.4-1 defaults because the decomposition model does
not describe them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scentinel.core import composition as comp
from scentinel.core import gas_data
from scentinel.core import generation as gen
from scentinel.core.gas_data import regime_concentration

WIND_DIRECTIONS = ("left-to-right", "right-to-left")

WIND_SIGN = {"left-to-right": 1.0, "right-to-left": -1.0}

#: Streams the UI offers. These name a preset composition; they are no longer the
#: thing that scales the source strength.
WASTE_TYPES = comp.LEGACY_WASTE_TYPES

#: Gases whose source strength comes from the decomposition model rather than
#: from a table: they are products of decay, so their concentration follows from
#: the composition, the age, and the moisture.
GENERATED_GASES = frozenset({"CH4", "CO2"})

#: Volume fractions of the generated gas mixture, for the two products. The
#: composition model reports these directly; these constants exist so the
#: conversion is stated once.
PPMV_PER_FRACTION = 1_000_000.0


@dataclass(frozen=True)
class WasteSpec:
    """One truck-load stream: its preset composition and moisture."""

    key: str
    regime: str
    default_gases: tuple[str, ...]
    composition: comp.WasteComposition
    moisture_fraction: float

    #: Kept for callers that read the old scalar fields. ``organic_fraction`` is
    #: now derived from the composition rather than driving anything: it is the
    #: degradable share, not a scaling factor.
    @property
    def organic_fraction(self) -> float:
        return self.composition.degradable_fraction()


def _spec(key: str) -> WasteSpec:
    composition, moisture = comp.preset(key)
    regime = "co-disposal" if key == "co-disposal" else "msw-only"
    gases = ("CO", "CH4", "VOC", "H2S")
    if key == "organic-rich":
        gases = ("CH4", "VOC", "H2S")
    elif key == "green-waste":
        gases = ("CH4", "VOC")
    elif key == "rdf-feedstock":
        gases = ("CO", "VOC")
    elif key == "dry-recyclables":
        gases = ("VOC",)
    return WasteSpec(
        key=key,
        regime=regime,
        default_gases=gases,
        composition=composition,
        moisture_fraction=moisture,
    )


WASTE_SPECS: dict[str, WasteSpec] = {key: _spec(key) for key in WASTE_TYPES}


def waste_spec(key: str) -> WasteSpec:
    if key not in WASTE_SPECS:
        raise ValueError(f"waste_type must be one of {WASTE_TYPES}")
    return WASTE_SPECS[key]


def generated_source_ppmv(scenario: Scenario, gas: str) -> float:
    """Source concentration of a decomposition product, in ppmv.

    The gas phase above the waste is the mixture the decomposition model reports,
    so the source strength of a product is its volume share of that mixture:
    methane is 0 ppmv in a fresh load and 550 000 ppmv at the cited steady state,
    and nothing in between is invented.

    In the pre-methanogenic phases the CO2 volume share is **not cited**: AP-42
    describes phase I as CO2-dominated with high N2 but gives no split, and the
    generation model's CO2 mass is a carbon-balance result, not a measured
    mixture composition. Returning a share would mean dividing by a mixture that
    contains only CO2 — 1 000 000 ppmv — so the gap is stated instead. The mass
    remains available on :class:`~scentinel.core.generation.Generation`.
    """
    if gas not in GENERATED_GASES:
        raise ValueError(f"{gas!r} is not a decomposition product")

    result = gen.generate(
        scenario.composition,
        tonnage_t=1.0,
        age_h=scenario.age_h,
        moisture=scenario.moisture_fraction,
    )
    if gas == "CH4":
        return result.methane_fraction * PPMV_PER_FRACTION
    if result.phase in ("I", "II"):
        raise ValueError(
            f"a phase-{result.phase} CO2 volume share is not cited: AP-42 §2.4.4 "
            "describes the aerobic/transition gas as CO2-dominated with high N2 "
            "but publishes no split, and the generation model's CO2 mass is a "
            "carbon balance, not a mixture measurement. Use the mass "
            "(Generation.co2_kg) or an aged scenario instead."
        )
    # CO2 share of the same mixture.
    molar = gen.MOLAR_MASS_G_PER_MOL
    moles_ch4 = result.ch4_kg / (molar["CH4"] / 1000.0)
    moles_co2 = result.co2_kg / (molar["CO2"] / 1000.0)
    moles_n2 = result.n2_kg / (molar["N2"] / 1000.0)
    total = moles_ch4 + moles_co2 + moles_n2
    if total <= 0.0:
        return 0.0
    return (moles_co2 / total) * PPMV_PER_FRACTION


def auto_concentration_ppmv(scenario: Scenario, gas: str) -> float:
    """Cited default source concentration for ``gas``, in ppmv.

    Decomposition products are computed from the waste; trace species come from
    AP-42 Table 2.4-1, falling back to the base default when the stream is
    co-disposal and the species has no cited co-disposal value.
    """
    if gas in GENERATED_GASES:
        return generated_source_ppmv(scenario, gas)
    return regime_concentration(gas, regime=scenario.regime)


def auto_provenance(scenario: Scenario, gas: str) -> str:
    """One-line provenance for an ``"auto"`` source, matching its resolved value.

    Trace species keep :func:`gas_data.citation` — their number is the table's.
    A decomposition product's number is not in any table: it comes from the
    generation model, so its provenance names that model, the composition, and
    the age, and states the value the manifest is about to persist. Citing the
    static ``SOURCE_DEFAULTS`` entry here made the record contradict itself.
    """
    if gas in GENERATED_GASES:
        ppmv = generated_source_ppmv(scenario, gas)
        return (
            f"{gas}: {ppmv:.0f} ppmv — computed by the generation model "
            f"(40 CFR 98.343(a)(1) Equation HH-1) for waste_type={scenario.waste_type!r}, "
            f"age_h={scenario.age_h:g}, moisture={scenario.moisture_fraction:.2f}; "
            f"AP-42 Ch.2.4 steady-state ratio 55% CH4 / 40% CO2 / 5% N2"
        )
    return gas_data.citation(gas)


@dataclass
class Scenario:
    """One simulation configuration.

    ``gas_sources`` maps a gas key to either an explicit ppmv value or the string
    ``"auto"``, which resolves through :func:`auto_concentration_ppmv` when the
    case is written.

    ``composition_fractions`` overrides the preset composition that
    ``waste_type`` selects. It exists because the batch panel edits the fraction
    table directly: without it the assessment would describe one waste and the
    run would solve another. ``tonnage_t`` is carried for the same reason — the
    yield and the generation report are per-batch, and a record that cannot say
    how much waste it assessed is not reproducible.
    """

    wind_speed_m_s: float = 1.0
    wind_direction: str = "left-to-right"
    ventilation_on: bool = False
    waste_type: str = "mixed-msw"
    age_h: float = 8.0
    moisture_fraction: float = 0.40
    tonnage_t: float = 10.0
    gas_sources: dict[str, float | str] = field(default_factory=dict)
    composition_fractions: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.wind_speed_m_s < 0.0:
            raise ValueError("wind_speed_m_s must not be negative")
        if self.wind_direction not in WIND_DIRECTIONS:
            raise ValueError(f"wind_direction must be one of {WIND_DIRECTIONS}")
        if self.waste_type not in WASTE_SPECS:
            raise ValueError(f"waste_type must be one of {WASTE_TYPES}")
        if self.age_h < 0.0:
            raise ValueError("age_h must not be negative")
        if not 0.0 <= self.moisture_fraction <= 1.0:
            raise ValueError("moisture_fraction must be in [0, 1]")
        if self.tonnage_t < 0.0:
            raise ValueError("tonnage_t must not be negative")
        if self.composition_fractions is not None:
            # ``WasteComposition`` validates the range and the sum, so an
            # invalid override is rejected here rather than reaching the model.
            self.composition_fractions = comp.WasteComposition(
                **self.composition_fractions
            ).as_dict()
        resolved: dict[str, float | str] = {}
        for key, value in self.gas_sources.items():
            if isinstance(value, str):
                if value != "auto":
                    raise ValueError(f"gas source for {key} must be a number or 'auto'")
                resolved[key] = value
            else:
                resolved[key] = float(value)
        self.gas_sources = resolved

    @property
    def wind_sign(self) -> float:
        """+1 when the wind blows left to right, -1 otherwise."""
        return WIND_SIGN[self.wind_direction]

    @property
    def waste(self) -> WasteSpec:
        return waste_spec(self.waste_type)

    @property
    def composition(self) -> comp.WasteComposition:
        """The composition the model uses: the override, else the preset."""
        if self.composition_fractions is not None:
            return comp.WasteComposition(**self.composition_fractions)
        return self.waste.composition

    @property
    def regime(self) -> str:
        return self.waste.regime

    @property
    def phase(self) -> str:
        return comp.phase_for(self.age_h)

    @property
    def organic_fraction(self) -> float:
        """Degradable share of the load, derived from the composition.

        Retained because manifests and the UI read it; it no longer scales any
        source strength, which is what the removed linear rule did.
        """
        return self.composition.degradable_fraction()

    @property
    def generated_gases(self) -> tuple[str, ...]:
        """Gases the current phase can produce, in a stable order."""
        return comp.PHASE_GASES[self.phase]
