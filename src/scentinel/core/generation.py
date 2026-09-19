"""Gas generation from waste composition, by the EPA's own regulatory model.

Implements Equation HH-1 of 40 CFR §98.343(a)(1):

    G_CH4 = Σ_x W_x · MCF · DOC · DOC_F · F · (16/12)
            · ( e^(-k(T-x-1)) - e^(-k(T-x)) )

That equation describes annual generation from waste placed in year ``x``. This
module applies the same first-order decay to a single batch of known mass and
known age, which is the question the app actually asks: *what is this load
producing now?*

Two properties matter for accuracy and are asserted by test:

* **The steady-state ceiling holds.** AP-42 p.2.4-3 states landfill gas at
  steady state is ~55% CH4, 40% CO2, 5% N2. No composition may produce a methane
  fraction above that, and the old linear rule could reach 85%.
* **A fresh load produces almost no methane.** With ``k`` in yr^-1 and a holding
  time in hours, the decay factor for a truck bin is below 0.06% of the ultimate
  yield. The model therefore agrees with the physics rather than contradicting it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scentinel.core.composition import (
    CARBON_MOLAR_MASS,
    DISSIMILATED_DOC_FRACTION,
    LANDFILL_GAS_METHANE_FRACTION,
    METHANE_CORRECTION_FACTOR,
    METHANE_DENSITY_KG_PER_M3,
    METHANE_MOLAR_MASS,
    STEADY_STATE_METHANE_CEILING,
    WasteComposition,
    phase_for,
)

HOURS_PER_YEAR = 24.0 * 365.25

#: Stoichiometric CH4/C mass ratio. The regulation writes it as exactly 16/12,
#: so the exact ratio is used rather than a ratio of precise molar masses: the
#: point of this module is to reproduce the regulatory equation, and using
#: 16.043/12.011 would silently disagree with it by 0.2%.
STOICHIOMETRIC_RATIO = 16.0 / 12.0

#: Molar masses for converting a mass of gas to its molar (volume) share.
MOLAR_MASS_G_PER_MOL = {"CH4": METHANE_MOLAR_MASS, "CO2": 44.009, "N2": 28.014}

#: Internal alias kept so the module's own arithmetic reads unchanged.
_MOLAR_MASS = MOLAR_MASS_G_PER_MOL

#: AP-42 p.2.4-3 steady-state composition, by volume: 55% CH4, 40% CO2, 5% N2.
#: The three sum to 100%, which is why the methane ceiling is exactly 0.55 and
#: not 55/95.
STEADY_STATE_MIX = {"CH4": 55.0, "CO2": 40.0, "N2": 5.0}


@dataclass(frozen=True)
class Generation:
    """Gas produced by one batch at a given age."""

    phase: str
    age_h: float
    tonnage_t: float
    doc: float
    k_per_year: float
    decay_fraction: float
    ultimate_ch4_kg_per_t: float
    ultimate_ch4_m3_per_t: float
    ch4_kg: float
    ch4_m3: float
    co2_kg: float
    n2_kg: float
    methane_fraction: float
    gases: tuple[str, ...]
    notes: tuple[str, ...]


def ultimate_methane_yield(composition: WasteComposition) -> tuple[float, float]:
    """Ultimate CH4 per tonne of waste [kg/t, m3/t], with all carbon degraded.

    The HH-1 sum with the decay factors omitted, which is the ceiling a batch
    approaches as ``age`` grows without bound.
    """
    doc = composition.weighted_doc()
    kg_per_t = (
        1000.0
        * METHANE_CORRECTION_FACTOR
        * doc
        * DISSIMILATED_DOC_FRACTION
        * LANDFILL_GAS_METHANE_FRACTION
        * STOICHIOMETRIC_RATIO
    )
    return kg_per_t, kg_per_t / METHANE_DENSITY_KG_PER_M3


def decay_fraction(k_per_year: float, age_h: float) -> float:
    """Fraction of the ultimate yield reached by ``age_h``.

    ``1 - e^(-k·Δt)``: the same first-order form as HH-1, evaluated for a single
    batch instead of summed over disposal years.
    """
    if k_per_year < 0.0:
        raise ValueError("k_per_year must not be negative")
    if age_h < 0.0:
        raise ValueError("age_h must not be negative")
    return 1.0 - math.exp(-k_per_year * (age_h / HOURS_PER_YEAR))


def co2_from_ch4(ch4_kg: float) -> float:
    """CO2 mass accompanying a methane mass at the AP-42 steady-state ratio.

    AP-42 p.2.4-3 gives 55% CH4 / 40% CO2 by volume, so CO2 carries ``(40/55)``
    of the methane's molar quantity. Applied to the gas actually produced, not
    to the ultimate potential.
    """
    if ch4_kg < 0.0:
        raise ValueError("ch4_kg must not be negative")
    moles_ch4 = ch4_kg / (_MOLAR_MASS["CH4"] / 1000.0)
    moles_co2 = moles_ch4 * (STEADY_STATE_MIX["CO2"] / STEADY_STATE_MIX["CH4"])
    return moles_co2 * (_MOLAR_MASS["CO2"] / 1000.0)


def nitrogen_from_ch4(ch4_kg: float) -> float:
    """N2 mass accompanying a methane mass at the AP-42 steady-state ratio.

    The third component of the cited mixture. It carries no carbon and is not a
    product of decay, but it is part of the gas, and leaving it out is what
    would make the methane share read 57.9% instead of the cited 55%.
    """
    if ch4_kg < 0.0:
        raise ValueError("ch4_kg must not be negative")
    moles_ch4 = ch4_kg / (_MOLAR_MASS["CH4"] / 1000.0)
    moles_n2 = moles_ch4 * (STEADY_STATE_MIX["N2"] / STEADY_STATE_MIX["CH4"])
    return moles_n2 * (_MOLAR_MASS["N2"] / 1000.0)


def generate(
    composition: WasteComposition,
    *,
    tonnage_t: float,
    age_h: float,
    moisture: float,
    gases: tuple[str, ...] | None = None,
) -> Generation:
    """Gas produced by ``tonnage_t`` tonnes of ``composition`` at ``age_h``.

    ``gases`` is the phase's allowable set; when omitted it is derived from the
    phase. Methane is dropped from the reported set in phases where it is not
    yet produced, which is what makes a fresh load read as a fresh load.
    """
    if tonnage_t < 0.0:
        raise ValueError("tonnage_t must not be negative")
    if not 0.0 <= moisture <= 1.0:
        raise ValueError("moisture must be in [0, 1]")

    phase = phase_for(age_h)
    doc = composition.weighted_doc()
    k = composition.weighted_decay(moisture)
    fraction = decay_fraction(k, age_h)
    kg_per_t, m3_per_t = ultimate_methane_yield(composition)

    # Pre-methanogenic phases produce no methane at all: AP-42 §2.4.4 states the
    # first phase is aerobic with "little methane" and methanogens establish only
    # after oxygen depletes. Reporting a small nonzero value here would contradict
    # the phase the same model just assigned, so the generation is suppressed
    # rather than left as arithmetic residue.
    producing_methane = phase in ("III", "IV")
    effective_fraction = fraction if producing_methane else 0.0

    ch4_kg = kg_per_t * tonnage_t * effective_fraction
    ch4_m3 = ch4_kg / METHANE_DENSITY_KG_PER_M3

    if producing_methane:
        # Methanogenic phases: CO2 accompanies CH4 at the AP-42 steady-state ratio.
        co2_kg = co2_from_ch4(ch4_kg)
        n2_kg = nitrogen_from_ch4(ch4_kg)
    else:
        # Aerobic phase I: carbon is oxidised to CO2 without methane. The gas is
        # CO2-dominated, which is exactly what AP-42 §2.4.4 describes, and it is
        # why a fresh bin smells of decomposition rather than of landfill gas.
        # The carbon available is the same DOC, oxidised to CO2 instead of CH4.
        # This is a *mass* balance, not a mixture composition: AP-42 gives no
        # CO2/N2 split for phase I, so ``methane_fraction`` below is 0.0 rather
        # than a share, and consumers that need a phase-I CO2 volume fraction
        # must treat it as uncited (see ``scenario.generated_source_ppmv``).
        carbon_kg = (
            1000.0
            * doc
            * DISSIMILATED_DOC_FRACTION
            * tonnage_t
            * fraction
        )
        co2_kg = carbon_kg * (_MOLAR_MASS["CO2"] / CARBON_MOLAR_MASS)
        n2_kg = 0.0

    # The 55% ceiling in AP-42 is a *volume* (molar) fraction over the whole gas
    # mixture — CH4 + CO2 + N2 — so the check is on moles, not mass. Mass
    # fractions differ: CO2 is ~2.75x heavier per mole than CH4.
    moles = {
        gas: mass / (_MOLAR_MASS[gas] / 1000.0)
        for gas, mass in (("CH4", ch4_kg), ("CO2", co2_kg), ("N2", n2_kg))
    }
    total_moles = sum(moles.values())
    methane_fraction = moles["CH4"] / total_moles if total_moles > 0.0 else 0.0

    notes: list[str] = []
    if methane_fraction > STEADY_STATE_METHANE_CEILING + 1e-9:
        # Unreachable while CO2 is derived from CH4 at the AP-42 ratio; kept as
        # an assertion of that invariant rather than a silent clamp.
        raise AssertionError(
            f"methane volume fraction {methane_fraction:.4f} exceeds the AP-42 "
            f"ceiling {STEADY_STATE_METHANE_CEILING}"
        )
    if phase in ("I", "II"):
        notes.append(
            f"phase {phase} is pre-methanogenic: methane is reported as negligible"
        )
    if composition.inert >= 1.0:
        notes.append("composition is entirely inert: no gas is produced")
    if moisture < 0.15:
        notes.append("dry load: decay rate is at the low end of the cited range")

    allowed = gases if gases is not None else PHASE_GASES_FOR(phase)
    return Generation(
        phase=phase,
        age_h=age_h,
        tonnage_t=tonnage_t,
        doc=doc,
        k_per_year=k,
        decay_fraction=fraction,
        ultimate_ch4_kg_per_t=kg_per_t,
        ultimate_ch4_m3_per_t=m3_per_t,
        ch4_kg=ch4_kg,
        ch4_m3=ch4_m3,
        co2_kg=co2_kg,
        n2_kg=n2_kg,
        methane_fraction=methane_fraction,
        gases=allowed,
        notes=tuple(notes),
    )


def PHASE_GASES_FOR(phase: str) -> tuple[str, ...]:  # noqa: N802 - mirrors the constant
    """Gases a phase can produce, from :data:`composition.PHASE_GASES`."""
    from scentinel.core.composition import PHASE_GASES

    if phase not in PHASE_GASES:
        raise ValueError(f"unknown phase {phase!r}")
    return PHASE_GASES[phase]
