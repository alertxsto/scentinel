"""Waste composition and decomposition phase.

The model describes *waste*, not gas. A batch is seven mass fractions plus a
holding time; the gases follow from those. This is the layer that replaces the
single ``waste_type`` label and the uncited linear scaling that used to sit in
:mod:`scentinel.core.scenario`.

Every constant here is copied from Table HH-1 to Subpart HH of 40 CFR Part 98
(revision at 89 FR 31940, effective 2025-01-01). The table's own footnotes
govern how the ``k`` range is collapsed to one value; see :func:`decay_rate`.
Provenance for the whole chain is in ``docs/gas-composition-basis.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Molar mass of carbon and of methane, for the stoichiometric CH4/C ratio.
CARBON_MOLAR_MASS = 12.011
METHANE_MOLAR_MASS = 16.043

#: Methane density at 0 °C, 1 atm [kg/m3]. Used only to express a yield in m3.
METHANE_DENSITY_KG_PER_M3 = 0.7167

#: Table HH-1, "Other parameters - All MSW landfills". Single values, not ranges.
METHANE_CORRECTION_FACTOR = 1.0  # MCF
DISSIMILATED_DOC_FRACTION = 0.5  # DOCF
LANDFILL_GAS_METHANE_FRACTION = 0.5  # F

#: AP-42 Ch.2.4 p.2.4-3: at steady state LFG is ~55% CH4, 40% CO2, 5% N2.
#: This is a ceiling, not a target: no composition may exceed it.
STEADY_STATE_METHANE_CEILING = 0.55

#: The four decomposition phases of AP-42 Ch.2.4 section 2.4.4.
PHASES = ("I", "II", "III", "IV")

#: Phase boundaries in hours, from the AP-42 narrative: phase I is aerobic and
#: lasts while oxygen remains (hours to a few days); phase II is the transition
#: as O2 depletes and CO2/H2 dominate; phase III is the onset of methanogenesis;
#: phase IV is steady state. AP-42 states the durations "vary with landfill
#: conditions" and gives no exact cut-offs, so these are the documented
#: qualitative boundaries expressed as a decision rule, not measured constants.
PHASE_I_MAX_HOURS = 48.0
PHASE_II_MAX_HOURS = 24.0 * 90.0
PHASE_III_MAX_HOURS = 24.0 * 365.0

#: Gases each phase can produce. Phase I is aerobic: CO2 dominates and methane
#: is negligible, which is the whole reason a fresh truck bin is not a landfill.
PHASE_GASES: dict[str, tuple[str, ...]] = {
    "I": ("CO2", "H2S", "METHYL_MERCAPTAN", "DIMETHYL_SULFIDE", "VOC", "CO"),
    "II": ("CO2", "H2S", "METHYL_MERCAPTAN", "DIMETHYL_SULFIDE", "VOC", "CO"),
    "III": ("CH4", "CO2", "H2S", "VOC", "CO"),
    "IV": ("CH4", "CO2", "H2S", "VOC", "CO"),
}


@dataclass(frozen=True)
class WasteMaterial:
    """One degradable fraction: its Table HH-1 carbon content and decay range."""

    key: str
    doc: float
    k_low: float
    k_high: float


#: Table HH-1, "DOC and k values - Waste composition option", wet basis.
MATERIALS: dict[str, WasteMaterial] = {
    "food": WasteMaterial("food", 0.15, 0.06, 0.185),
    "garden": WasteMaterial("garden", 0.20, 0.05, 0.10),
    "paper": WasteMaterial("paper", 0.40, 0.04, 0.06),
    "wood": WasteMaterial("wood", 0.43, 0.02, 0.03),
    "textile": WasteMaterial("textile", 0.24, 0.04, 0.06),
    "diaper": WasteMaterial("diaper", 0.24, 0.05, 0.10),
    "sludge": WasteMaterial("sludge", 0.05, 0.06, 0.185),
    "inert": WasteMaterial("inert", 0.00, 0.00, 0.00),
}

MATERIAL_KEYS = tuple(MATERIALS)

_FRACTION_TOLERANCE = 1e-6


def phase_for(age_h: float) -> str:
    """The AP-42 decomposition phase for a holding time in hours."""
    if age_h < 0.0:
        raise ValueError("age_h must not be negative")
    if age_h <= PHASE_I_MAX_HOURS:
        return "I"
    if age_h <= PHASE_II_MAX_HOURS:
        return "II"
    if age_h <= PHASE_III_MAX_HOURS:
        return "III"
    return "IV"


def decay_rate(material: WasteMaterial, moisture: float) -> float:
    """Collapse the Table HH-1 ``k`` range using the table's own footnote.

    Footnote c of Table HH-1: *"Use the lesser value when the potential
    evapotranspiration rate exceeds the mean annual precipitation rate plus
    recirculated leachate. Use the greater value when the potential
    evapotranspiration rate does not exceed ..."* — i.e. a wetter material
    decays faster.

    Moisture is the model's proxy for that balance: at or below the dry
    reference it takes ``k_low``, at or above the wet reference ``k_high``, and
    interpolates linearly between. The endpoints are the table's; the
    interpolation is this model's stated choice, not a cited curve.
    """
    if not 0.0 <= moisture <= 1.0:
        raise ValueError("moisture must be in [0, 1]")
    if material.k_high <= material.k_low:
        return material.k_low
    span = DRY_REFERENCE - WET_REFERENCE
    position = (DRY_REFERENCE - moisture) / span
    position = min(1.0, max(0.0, position))
    return material.k_low + position * (material.k_high - material.k_low)


#: Moisture endpoints for the footnote-c interpolation. Dry is the lower bound
#: of the MSW range commonly quoted for as-received waste; wet is saturated.
DRY_REFERENCE = 0.15
WET_REFERENCE = 0.65


@dataclass(frozen=True)
class WasteComposition:
    """A batch's mass fractions, wet basis, summing to one.

    ``moisture`` is carried separately because it is not a material: it selects
    the decay rate and sets the dry-mass basis, and it leaves the process as its
    own stream rather than appearing in a product.
    """

    food: float = 0.0
    garden: float = 0.0
    paper: float = 0.0
    wood: float = 0.0
    textile: float = 0.0
    diaper: float = 0.0
    sludge: float = 0.0
    inert: float = 0.0

    def __post_init__(self) -> None:
        for key in MATERIAL_KEYS:
            value = getattr(self, key)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{key} fraction must be in [0, 1], got {value}")
        total = self.total
        if abs(total - 1.0) > _FRACTION_TOLERANCE:
            raise ValueError(
                f"composition fractions must sum to 1.0, got {total:.6f} "
                f"(difference {total - 1.0:+.6f})"
            )

    @property
    def total(self) -> float:
        return sum(getattr(self, key) for key in MATERIAL_KEYS)

    def as_dict(self) -> dict[str, float]:
        return {key: getattr(self, key) for key in MATERIAL_KEYS}

    def degradable_fraction(self) -> float:
        """Mass fraction that can produce gas (everything except inerts)."""
        return 1.0 - self.inert

    def weighted_doc(self) -> float:
        """Composition-weighted degradable organic carbon, wet basis.

        The HH-1 sum: each material's DOC weighted by its mass fraction.
        """
        return sum(getattr(self, key) * MATERIALS[key].doc for key in MATERIAL_KEYS)

    def weighted_decay(self, moisture: float) -> float:
        """Composition-weighted first-order decay rate [1/yr]."""
        return sum(
            getattr(self, key) * decay_rate(MATERIALS[key], moisture)
            for key in MATERIAL_KEYS
        )


def _normalise(**fractions: float) -> WasteComposition:
    """Build a composition from relative weights, normalised to sum to one."""
    total = sum(fractions.values())
    if total <= 0.0:
        raise ValueError("preset fractions must sum to a positive value")
    scaled = {key: value / total for key, value in fractions.items()}
    return WasteComposition(**scaled)


#: Presets for the six streams the UI already offered. Fractions are the model's
#: starting points for each stream description, normalised to sum to one; they
#: are user-editable inputs, not cited measurements, and the UI labels them as
#: such. The *physics* applied to them (DOC, k) is the cited part.
PRESETS: dict[str, WasteComposition] = {
    "mixed-msw": _normalise(
        food=0.30, garden=0.08, paper=0.25, wood=0.06, textile=0.05, diaper=0.05, inert=0.21
    ),
    "co-disposal": _normalise(
        food=0.25, garden=0.05, paper=0.28, wood=0.07, textile=0.06, diaper=0.04, inert=0.25
    ),
    "organic-rich": _normalise(
        food=0.55, garden=0.15, paper=0.12, wood=0.04, textile=0.03, diaper=0.05, inert=0.06
    ),
    "green-waste": _normalise(
        food=0.10, garden=0.60, paper=0.08, wood=0.14, textile=0.02, diaper=0.01, inert=0.05
    ),
    "rdf-feedstock": _normalise(
        food=0.08, garden=0.02, paper=0.30, wood=0.08, textile=0.12, diaper=0.05, inert=0.35
    ),
    "dry-recyclables": _normalise(
        food=0.02, garden=0.01, paper=0.35, wood=0.03, textile=0.04, diaper=0.01, inert=0.54
    ),
}

#: Moisture presets per stream, used when a preset is selected.
PRESET_MOISTURE: dict[str, float] = {
    "mixed-msw": 0.40,
    "co-disposal": 0.35,
    "organic-rich": 0.60,
    "green-waste": 0.55,
    "rdf-feedstock": 0.15,
    "dry-recyclables": 0.10,
}

#: Legacy ``waste_type`` values that map onto a preset, so existing projects and
#: manifests keep loading. The mapping is total: every old key resolves.
LEGACY_WASTE_TYPES = tuple(PRESETS)


def preset(name: str) -> tuple[WasteComposition, float]:
    """Composition and moisture for a named preset."""
    if name not in PRESETS:
        raise ValueError(f"unknown waste preset {name!r}; expected one of {LEGACY_WASTE_TYPES}")
    return PRESETS[name], PRESET_MOISTURE[name]
