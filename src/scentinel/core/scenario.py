"""Scenario parameters: wind, ventilation, and per-gas source strengths."""

from __future__ import annotations

from dataclasses import dataclass, field

WIND_DIRECTIONS = ("left-to-right", "right-to-left")

WIND_SIGN = {"left-to-right": 1.0, "right-to-left": -1.0}


@dataclass
class Scenario:
    """One simulation configuration.

    ``gas_sources`` maps a gas key (see :mod:`scentinel.core.gas_data`) to
    either the source concentration at the waste surface in ppmv, or the string
    ``"auto"`` to take the cited AP-42 default. ``"auto"`` is resolved by
    :func:`scentinel.core.casegen.resolve_sources` when the case is written.
    """

    wind_speed_m_s: float = 1.0
    wind_direction: str = "left-to-right"
    ventilation_on: bool = False
    gas_sources: dict[str, float | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.wind_speed_m_s < 0.0:
            raise ValueError("wind_speed_m_s must not be negative")
        if self.wind_direction not in WIND_DIRECTIONS:
            raise ValueError(f"wind_direction must be one of {WIND_DIRECTIONS}")
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
