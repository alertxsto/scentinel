"""2D mesh generation: the air region, extruded one cell thick.

OpenFOAM has no 2D solver — a 2D case is a 3D mesh one cell thick whose front
and back faces are declared as the ``empty`` patch. This module builds the air
cross-section, extrudes it by ``thickness_m`` with a single cell, and tags the
boundary curves so the resulting patches can be named in the case.

The waste mound is **not** meshed. It is a solid with no flow, so it only
contributes a boundary — the ``source`` patch. Meshing it would add cells that
carry no information and an interface that has to be stitched.

The air outline runs along the mound surface, up the bin wall, out into the
open air above the bin, across the top, and back down the other side. That
split matters: the wall below the bin rim is solid (``wallLeft``/``wallRight``)
while the part above the rim is open to the wind (``openLeft``/``openRight``).
Naming the patches geometrically and letting the case writer decide which open
side is the inlet keeps wind direction out of the mesh.

Boundary patches produced: ``source``, ``wallLeft``, ``wallRight``, ``openLeft``,
``openRight``, ``top``, ``frontAndBack``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import gmsh

from scentinel.core.geometry import BinGeometry, mound_surface

#: Boundary patch names present on every generated mesh.
PATCHES = ("source", "wallLeft", "wallRight", "openLeft", "openRight", "top", "frontAndBack")

#: Written as MSH 2.2. ``gmshToFoam`` reads the v2 sections (``$NOD``/``$ELM``)
#: and the v2 element line format; the gmsh default of 4.1 uses different
#: section names and a reordered element body, and is not readable.
MSH_FILE_VERSION = 2.2

DEFAULT_AIR_EXTENSION_M = 3.0
DEFAULT_THICKNESS_M = 0.01

_GMSH_TET = 4
_GMSH_HEX = 5
_GMSH_PRISM = 6
_GMSH_PYR = 7
_ELEMENT_NAMES = {
    _GMSH_TET: "tet",
    _GMSH_HEX: "hex",
    _GMSH_PRISM: "prism",
    _GMSH_PYR: "pyramid",
}


@dataclass
class MeshResult:
    """Outcome of a meshing run."""

    msh_path: Path
    patches: dict[str, int] = field(default_factory=dict)
    node_count: int = 0
    cell_count: int = 0
    element_types: dict[str, int] = field(default_factory=dict)
    mesh_size_m: float = 0.0
    air_extension_m: float = DEFAULT_AIR_EXTENSION_M
    thickness_m: float = DEFAULT_THICKNESS_M

    @property
    def is_hexahedral(self) -> bool:
        """True when every volume cell is a hexahedron."""
        return set(self.element_types) <= {"hex"}

    @property
    def hex_fraction(self) -> float:
        """Share of volume cells that are hexahedra, in ``[0, 1]``."""
        if not self.cell_count:
            return 0.0
        return self.element_types.get("hex", 0) / self.cell_count

    @property
    def is_predominantly_hexahedral(self) -> bool:
        """True when the mesh is essentially all hexes.

        The extruded mound outline leaves a handful of prisms where the
        recombination cannot close a quad. That is normal and ``checkMesh``
        accepts it; a large prism share means recombination failed.
        """
        return self.hex_fraction >= 0.99


def generate_mesh(
    geom: BinGeometry,
    mesh_size_m: float,
    out_dir: Path,
    *,
    air_extension_m: float = DEFAULT_AIR_EXTENSION_M,
    thickness_m: float = DEFAULT_THICKNESS_M,
) -> MeshResult:
    """Mesh the air around the waste mound and write an MSH 2.2 file.

    ``mesh_size_m`` is the target edge length. The mound profile contributes a
    vertex every few centimetres, and gmsh must honour those vertices, so the
    realised cells near the waste surface are finer than the target.
    """
    if mesh_size_m <= 0.0:
        raise ValueError("mesh_size_m must be positive")
    if air_extension_m <= 0.0:
        raise ValueError("air_extension_m must be positive")
    if thickness_m <= 0.0:
        raise ValueError("thickness_m must be positive")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    msh_path = out_dir / "case.msh"

    outline, groups = _air_outline(geom, air_extension_m)

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MshFileVersion", MSH_FILE_VERSION)
        gmsh.option.setNumber("Mesh.Binary", 0)
        # Recombination is what turns the 2D triangles into quads; without it
        # the extrusion produces tetrahedra instead of hexahedra.
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 1)
        gmsh.model.add("scentinel")

        points = [gmsh.model.geo.addPoint(x, y, 0.0, mesh_size_m) for x, y in outline]
        lines = [
            gmsh.model.geo.addLine(points[i], points[(i + 1) % len(points)])
            for i in range(len(points))
        ]
        surface = gmsh.model.geo.addPlaneSurface([gmsh.model.geo.addCurveLoop(lines)])
        gmsh.model.geo.synchronize()

        for name, indices in groups.items():
            gmsh.model.addPhysicalGroup(1, [lines[i] for i in indices], name=name)

        # One cell through the thickness. The extrude returns the far face
        # first, then the volume, then one side surface per input curve, in
        # curve order.
        extruded = gmsh.model.geo.extrude(
            [(2, surface)], 0.0, 0.0, thickness_m, numElements=[1], recombine=True
        )
        gmsh.model.geo.synchronize()

        back = next(tag for dim, tag in extruded if dim == 2)
        volume = next(tag for dim, tag in extruded if dim == 3)
        sides = [tag for dim, tag in extruded if dim == 2 and tag != back]

        # The side surfaces must carry the same physical groups as the curves
        # they came from. gmshToFoam maps boundary faces to patches by physical
        # tag, so an untagged side becomes an unusable `defaultFaces` patch.
        for name, indices in groups.items():
            gmsh.model.addPhysicalGroup(2, [sides[i] for i in indices], name=name)

        gmsh.model.addPhysicalGroup(2, [surface, back], name="frontAndBack")
        # A volume physical group is not decoration: with any physical group
        # present gmsh writes only tagged elements to the file, so without this
        # the hexes are silently dropped and the mesh arrives 2D.
        gmsh.model.addPhysicalGroup(3, [volume], name="air")

        gmsh.model.mesh.generate(3)
        gmsh.write(str(msh_path))

        patches = {
            gmsh.model.getPhysicalName(dim, tag): tag
            for dim, tag in (
                *gmsh.model.getPhysicalGroups(1),
                *gmsh.model.getPhysicalGroups(2),
                *gmsh.model.getPhysicalGroups(3),
            )
        }
        node_tags, _, _ = gmsh.model.mesh.getNodes()
        cell_count = 0
        element_types: dict[str, int] = {}
        for _dim, tag in gmsh.model.getEntities(3):
            # ``getElements`` returns (types, elementTags, nodeTags). The count
            # of *elements* is ``len(element_tags)``; ``len(node_tags)`` is the
            # connectivity length, which counts a hexahedron eight times.
            types, element_tags, _node_tags = gmsh.model.mesh.getElements(3, tag)
            for element_type, tags in zip(types, element_tags):
                name = _ELEMENT_NAMES.get(int(element_type), str(element_type))
                count = len(tags)
                element_types[name] = element_types.get(name, 0) + count
                cell_count += count
    finally:
        gmsh.finalize()

    if cell_count == 0:
        raise RuntimeError("meshing produced no volume cells")
    missing = set(groups) - set(patches)
    if missing:
        raise RuntimeError(f"physical groups missing from the mesh: {sorted(missing)}")

    return MeshResult(
        msh_path=msh_path,
        patches=patches,
        node_count=len(node_tags),
        cell_count=cell_count,
        element_types=element_types,
        mesh_size_m=mesh_size_m,
        air_extension_m=air_extension_m,
        thickness_m=thickness_m,
    )


def _air_outline(
    geom: BinGeometry, air_extension_m: float
) -> tuple[list[tuple[float, float]], dict[str, list[int]]]:
    """Air-region outline and the line indices making up each patch.

    The outline is walked counter-clockwise: along the mound from left to
    right, up the right-hand side of the bin, across the top, and back down
    the left. The bin rim at ``y = height_m`` is a vertex on both sides so the
    solid wall and the open sky can be separate patches.
    """
    surface = mound_surface(geom)
    length, height = geom.length_m, geom.height_m
    top_y = height + air_extension_m

    outline: list[tuple[float, float]] = list(surface)
    outline.append((length, height))  # bin rim, right
    outline.append((length, top_y))
    outline.append((0.0, top_y))
    outline.append((0.0, height))  # bin rim, left

    n_surface = len(surface) - 1  # segments forming the waste surface
    groups = {
        "source": list(range(n_surface)),
        "wallRight": [n_surface],
        "openRight": [n_surface + 1],
        "top": [n_surface + 2],
        "openLeft": [n_surface + 3],
        "wallLeft": [n_surface + 4],
    }
    return outline, groups
