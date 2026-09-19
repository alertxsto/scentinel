"""Scenario parameters: wind, waste stream, ventilation, and per-gas sources."""

from __future__ import annotations

from dataclasses import dataclass, field

from scentinel.core.gas_data import source_concentration

WIND_DIRECTIONS = ("left-to-right", "right-to-left")

WIND_SIGN = {"left-to-right": 1.0, "right-to-left": -1.0}

#: AP-42 Table 2.4-2 MSW-only is the organic-fraction baseline. Auto CH₄/VOC/H₂S
#: for an ``msw-only`` stream scale linearly with ``organic_fraction / 0.50``.
#: Co-disposal keeps the cited alternate concentrations unscaled.
ORGANIC_REFERENCE = 0.50
ORGANIC_SCALE_GASES = frozenset({"CH4", "VOC", "H2S"})

WASTE_TYPES = (
    "mixed-msw",
    "co-disposal",
    "organic-rich",
    "green-waste",
    "rdf-feedstock",
    "dry-recyclables",
)


@dataclass(frozen=True)
class WasteSpec:
    """One truck-load stream: cited AP-42 regime plus composition defaults."""

    key: str
    regime: str
    default_gases: tuple[str, ...]
    organic_fraction: float
    moisture_fraction: float


WASTE_SPECS: dict[str, WasteSpec] = {
    "mixed-msw": WasteSpec("mixed-msw", "msw-only", ("CO", "CH4", "VOC", "H2S"), 0.50, 0.40),
    "co-disposal": WasteSpec(
        "co-disposal", "co-disposal", ("CO", "CH4", "VOC", "H2S"), 0.45, 0.35
    ),
    "organic-rich": WasteSpec("organic-rich", "msw-only", ("CH4", "VOC", "H2S"), 0.80, 0.60),
    "green-waste": WasteSpec("green-waste", "msw-only", ("CH4", "VOC"), 0.85, 0.55),
    "rdf-feedstock": WasteSpec("rdf-feedstock", "msw-only", ("CO", "VOC"), 0.25, 0.15),
    "dry-recyclables": WasteSpec("dry-recyclables", "msw-only", ("VOC",), 0.10, 0.10),
}


def waste_spec(key: str) -> WasteSpec:
    if key not in WASTE_SPECS:
        raise ValueError(f"waste_type must be one of {WASTE_TYPES}")
    return WASTE_SPECS[key]


def auto_concentration_ppmv(scenario: Scenario, gas: str) -> float:
    """Cited AP-42 default for ``gas``, scaled by waste stream when applicable."""
    spec = waste_spec(scenario.waste_type)
    ppmv = source_concentration(gas, regime=spec.regime)
    if spec.regime == "msw-only" and gas in ORGANIC_SCALE_GASES:
        ppmv *= scenario.organic_fraction / ORGANIC_REFERENCE
    return ppmv


@dataclass
class Scenario:
    """One simulation configuration.

    ``gas_sources`` maps a gas key (see :mod:`scentinel.core.gas_data`) to
    either the source concentration at the waste surface in ppmv, or the string
    ``"auto"`` to take the cited AP-42 default for the selected waste stream.
    ``"auto"`` is resolved by :func:`scentinel.core.casegen.resolve_sources`
    when the case is written.
    """

    wind_speed_m_s: float = 1.0
    wind_direction: str = "left-to-right"
    ventilation_on: bool = False
    waste_type: str = "mixed-msw"
    organic_fraction: float = 0.50
    moisture_fraction: float = 0.40
    gas_sources: dict[str, float | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.wind_speed_m_s < 0.0:
            raise ValueError("wind_speed_m_s must not be negative")
        if self.wind_direction not in WIND_DIRECTIONS:
            raise ValueError(f"wind_direction must be one of {WIND_DIRECTIONS}")
        if self.waste_type not in WASTE_SPECS:
            raise ValueError(f"waste_type must be one of {WASTE_TYPES}")
        if not 0.0 < self.organic_fraction <= 1.0:
            raise ValueError("organic_fraction must be in (0, 1]")
        if not 0.0 <= self.moisture_fraction <= 1.0:
            raise ValueError("moisture_fraction must be in [0, 1]")
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
