"""2D cross-section geometry for the truck bin and the waste mound.

Coordinates are metres in a right-handed 2D frame: ``x`` runs along the bin
length (``0 .. length_m``) and ``y`` runs up from the bin floor
(``0 .. height_m``).

``mound_fill_fraction`` is the fraction of the bin cross-section occupied by
waste, i.e. the mound area is ``length_m * height_m * fraction``. Non-flat
profiles are normalised to that area, unless reaching it would push the mound
through the bin roof; then the mound is clipped at the roof and the real area
is smaller. Read the truth back with :func:`mound_area` / :func:`fill_fraction`
rather than assuming the requested fraction was met.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MOUND_SHAPES = ("flat", "mounded", "left-heavy", "right-heavy", "twin-mound", "irregular")

_PROFILE_STEPS = 64
"""Segments used to sample a non-flat mound profile."""


@dataclass(frozen=True)
class BinGeometry:
    """Parameterised bin cross-section and waste mound."""

    length_m: float = 6.0
    height_m: float = 2.5
    width_m: float = 2.4
    mound_shape: str = "flat"
    mound_fill_fraction: float = 0.5

    def __post_init__(self) -> None:
        if self.length_m <= 0.0:
            raise ValueError("length_m must be positive")
        if self.height_m <= 0.0:
            raise ValueError("height_m must be positive")
        if self.width_m <= 0.0:
            raise ValueError("width_m must be positive")
        if self.mound_shape not in MOUND_SHAPES:
            raise ValueError(f"mound_shape must be one of {MOUND_SHAPES}")
        if not 0.0 < self.mound_fill_fraction <= 1.0:
            raise ValueError("mound_fill_fraction must be in (0, 1]")


def bin_polygon(geom: BinGeometry) -> list[tuple[float, float]]:
    """Closed outline of the bin, counter-clockwise from the floor-left corner."""
    return [
        (0.0, 0.0),
        (geom.length_m, 0.0),
        (geom.length_m, geom.height_m),
        (0.0, geom.height_m),
    ]


def mound_surface(geom: BinGeometry) -> list[tuple[float, float]]:
    """Top profile of the mound, left to right, as an open polyline.

    This is the boundary the air actually sees. It excludes the floor edge and
    the vertical risers that :func:`mound_polygon` needs to close the shape, so
    for a flat mound it is a single segment at the fill height rather than a
    rectangle.
    """
    length, height = geom.length_m, geom.height_m
    target_area = length * height * geom.mound_fill_fraction

    if geom.mound_shape == "flat":
        top = height * geom.mound_fill_fraction
        return [(0.0, top), (length, top)]

    xs = [length * i / _PROFILE_STEPS for i in range(_PROFILE_STEPS + 1)]
    if geom.mound_shape == "mounded":
        raw = [math.sin(math.pi * x / length) for x in xs]
    elif geom.mound_shape == "left-heavy":
        raw = [
            (x / length) * (1.0 - x / length) ** 2
            for x in xs
        ]
    elif geom.mound_shape == "right-heavy":
        raw = [
            (x / length) ** 2 * (1.0 - x / length)
            for x in xs
        ]
    elif geom.mound_shape == "twin-mound":
        raw = [abs(math.sin(2.0 * math.pi * x / length)) for x in xs]
    else:
        raw = [
            math.sin(math.pi * x / length) * (1.0 + 0.15 * math.sin(7.0 * math.pi * x / length))
            for x in xs
        ]
    raw[0] = 0.0
    raw[-1] = 0.0

    scale = target_area / _trapezoid(xs, raw)
    peak = scale * max(raw)
    if peak > height:
        scale = height / max(raw)
    return [(x, scale * value) for x, value in zip(xs, raw)]


def mound_polygon(geom: BinGeometry) -> list[tuple[float, float]]:
    """Closed outline of the waste mound, sitting on the bin floor."""
    polygon = list(mound_surface(geom))
    if polygon[-1] != (geom.length_m, 0.0):
        polygon.append((geom.length_m, 0.0))
    if polygon[0] != (0.0, 0.0):
        polygon.insert(0, (0.0, 0.0))
    return polygon


def mound_height_at(geom: BinGeometry, x: float) -> float:
    """Height of the mound surface at ``x`` metres along the bin, in m.

    Returns 0 outside the bin length. Used to keep sensor points clear of the
    waste and to draw the free-air region.
    """
    if not 0.0 <= x <= geom.length_m:
        return 0.0
    surface = mound_surface(geom)
    for (x0, y0), (x1, y1) in zip(surface, surface[1:]):
        if x0 <= x <= x1:
            span = x1 - x0
            if span <= 0.0:
                return max(y0, y1)
            return y0 + (y1 - y0) * (x - x0) / span
    return surface[-1][1] if x >= surface[-1][0] else surface[0][1]


def placement_problem(geom: BinGeometry, x: float, y: float) -> str:
    """Why a sensor cannot be placed at ``(x, y)``, or ``""`` when valid."""
    if not (0.0 <= x <= geom.length_m and 0.0 <= y <= geom.height_m):
        return "outside the bin"
    if y < mound_height_at(geom, x):
        return "inside the waste mound"
    return ""


def mound_area(geom: BinGeometry) -> float:
    """Area of the mound cross-section, in m^2."""
    return _shoelace(mound_polygon(geom))


def mound_profile_length(geom: BinGeometry) -> float:
    """Length of the mound surface seen by the air, in m.

    The sum of the segment lengths of :func:`mound_surface`. For a flat mound
    this is just the bin length; a curved profile is longer than its span.
    """
    surface = mound_surface(geom)
    return sum(
        math.hypot(x1 - x0, y1 - y0)
        for (x0, y0), (x1, y1) in zip(surface, surface[1:])
    )


def emission_area_m2(geom: BinGeometry) -> float:
    """Area of waste surface that emits into the air, in m^2.

    The case is a 2D cross-section, so the emitting surface is the mound
    profile extruded by the bin width: ``mound_profile_length(geom) * width_m``.
    This is what turns a batch's generation rate (kg/s) into an emission flux
    (kg/m^2/s).
    """
    return mound_profile_length(geom) * geom.width_m


def fill_fraction(geom: BinGeometry) -> float:
    """Fraction of the bin cross-section actually occupied by waste."""
    return mound_area(geom) / (geom.length_m * geom.height_m)


def air_domain(geom: BinGeometry, extension_m: float) -> list[tuple[float, float]]:
    """Bin cross-section extended upwards by ``extension_m`` of free air."""
    return [
        (0.0, 0.0),
        (geom.length_m, 0.0),
        (geom.length_m, geom.height_m + extension_m),
        (0.0, geom.height_m + extension_m),
    ]


def _shoelace(points: list[tuple[float, float]]) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _trapezoid(xs: list[float], ys: list[float]) -> float:
    return sum(
        0.5 * (y0 + y1) * (x1 - x0)
        for x0, x1, y0, y1 in zip(xs, xs[1:], ys, ys[1:])
    )
