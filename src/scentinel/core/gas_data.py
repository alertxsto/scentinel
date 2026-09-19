"""Gas table loader: reads the generated AP-42 defaults and exposes them per gas."""

from __future__ import annotations

from dataclasses import dataclass

from scentinel.core.gas_defaults import GAS_PROPERTIES, SOURCE_DEFAULTS

REGIMES = ("msw-only", "co-disposal")

#: Gas keys offered as scenario sources, in display order: the AP-42 headline
#: gases first, then the added trace species grouped by chemical family
#: (hydrocarbon, aromatics, chlorinated, sulfur).
DEFAULT_SOURCE_GASES = (
    "CO",
    "CH4",
    "VOC",
    "H2S",
    "ETHANE",
    "BENZENE",
    "TOLUENE",
    "VINYL_CHLORIDE",
    "METHYL_MERCAPTAN",
    "DIMETHYL_SULFIDE",
)


@dataclass(frozen=True)
class GasSpec:
    """Physical properties plus the cited source default for one gas."""

    key: str
    name: str
    mw_g_mol: float
    diffusivity_m2_s: float
    default_conc_ppmv: float
    basis: str
    rating: str = ""
    alternate_conc_ppmv: float | None = None
    alternate_basis: str = ""


def available_gases() -> list[str]:
    return list(GAS_PROPERTIES)


def get_gas(key: str) -> GasSpec:
    if key not in GAS_PROPERTIES:
        raise KeyError(f"Unknown gas: {key}")
    props = GAS_PROPERTIES[key]
    defaults = SOURCE_DEFAULTS.get(key, {})
    if "conc_ppmv" in defaults:
        default_conc = float(defaults["conc_ppmv"])
    elif "fraction_by_volume" in defaults:
        default_conc = float(defaults["fraction_by_volume"]) * 1_000_000.0
    else:
        raise KeyError(f"No concentration default for {key}")
    alternate = defaults.get("alternate_conc_ppmv")
    if alternate is None and "alternate_fraction" in defaults:
        alternate = float(defaults["alternate_fraction"]) * 1_000_000.0
    return GasSpec(
        key=key,
        name=props["name"],
        mw_g_mol=props["mw_g_mol"],
        diffusivity_m2_s=props["diffusivity_m2_s"],
        default_conc_ppmv=default_conc,
        basis=defaults.get("basis", ""),
        rating=defaults.get("rating", ""),
        alternate_conc_ppmv=None if alternate is None else float(alternate),
        alternate_basis=defaults.get("alternate_basis", ""),
    )


def source_concentration(gas_key: str, regime: str = "msw-only") -> float:
    """Cited default source concentration in ppmv for one gas and disposal regime.

    Strict by design: a co-disposal lookup for a gas AP-42 gives no alternate for
    raises rather than guessing. Use :func:`default_sources` (or
    :func:`scentinel.core.scenario.auto_concentration_ppmv`) when the desired
    behaviour is a fallback.
    """
    if regime not in REGIMES:
        raise ValueError(f"regime must be one of {REGIMES}")
    spec = get_gas(gas_key)
    if regime == "co-disposal":
        if spec.alternate_conc_ppmv is None:
            raise KeyError(f"No co-disposal default for {gas_key}")
        return spec.alternate_conc_ppmv
    return spec.default_conc_ppmv


def regime_concentration(gas_key: str, regime: str = "msw-only") -> float:
    """Default concentration for ``gas_key`` under ``regime``, falling back.

    Uses the cited co-disposal alternate where AP-42 publishes one and the base
    default where it does not, so this never raises for a gas in
    :data:`DEFAULT_SOURCE_GASES`. :func:`source_concentration` is the strict
    variant, for callers that need to know whether a cited alternate exists.
    """
    if regime not in REGIMES:
        raise ValueError(f"regime must be one of {REGIMES}")
    spec = get_gas(gas_key)
    if regime == "co-disposal" and spec.alternate_conc_ppmv is not None:
        return spec.alternate_conc_ppmv
    return spec.default_conc_ppmv


def default_sources(regime: str = "msw-only") -> dict[str, float]:
    """Every source gas at its cited default, ready to drop into a scenario.

    Mirrors :func:`scentinel.core.scenario.auto_concentration_ppmv`: a
    co-disposal regime uses each gas's cited alternate where AP-42 has one and
    falls back to the base default where it does not, so this covers every entry
    of :data:`DEFAULT_SOURCE_GASES` under both regimes.
    """
    return {key: regime_concentration(key, regime) for key in DEFAULT_SOURCE_GASES}


def citation(gas_key: str) -> str:
    """One-line provenance string for the given gas, e.g. for a tooltip."""
    spec = get_gas(gas_key)
    parts = [f"{spec.name}: {spec.default_conc_ppmv:g} ppmv", spec.basis]
    if spec.rating:
        parts.append(f"EPA rating {spec.rating}")
    return " — ".join(part for part in parts if part)
