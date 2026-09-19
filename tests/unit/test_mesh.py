from __future__ import annotations

import re
from pathlib import Path

import pytest

from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import MSH_FILE_VERSION, PATCHES, generate_mesh


@pytest.fixture(scope="module")
def mesh(tmp_path_factory):
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.45)
    return generate_mesh(geom, 0.5, tmp_path_factory.mktemp("mesh"))


def test_mesh_is_written_as_msh_22(mesh):
    """gmshToFoam only reads the v2 sections; the gmsh default of 4.1 fails."""
    text = mesh.msh_path.read_text()
    assert text.startswith("$MeshFormat")
    assert text.splitlines()[1].startswith(f"{MSH_FILE_VERSION} ")
    assert "$Nodes" in text and "$Elements" in text
    assert "$NOD" not in text  # v4 section naming would be wrong


def test_every_expected_patch_is_tagged(mesh):
    assert set(PATCHES) <= set(mesh.patches)


def test_mesh_has_volume_cells(mesh):
    """A 2D mesh has no cells at all, which gmshToFoam rejects outright."""
    assert mesh.cell_count > 0
    assert mesh.node_count > 0


def test_mesh_is_predominantly_hexahedral(mesh):
    """Hexes are what the extrusion aims for; tets mean recombination failed."""
    assert mesh.is_predominantly_hexahedral, mesh.element_types
    assert mesh.element_types.get("tet", 0) == 0


def test_both_slab_faces_are_tagged(mesh):
    """Without the front/back group the case has no `empty` patch."""
    assert "frontAndBack" in mesh.patches


def test_refining_increases_the_cell_count(tmp_path):
    geom = BinGeometry()
    coarse = generate_mesh(geom, 0.5, tmp_path / "coarse")
    fine = generate_mesh(geom, 0.25, tmp_path / "fine")
    assert fine.cell_count > coarse.cell_count
    assert fine.node_count > coarse.node_count


@pytest.mark.parametrize("shape", ["flat", "mounded", "irregular"])
def test_every_mound_shape_meshes(tmp_path, shape):
    geom = BinGeometry(mound_shape=shape, mound_fill_fraction=0.4)
    result = generate_mesh(geom, 0.5, tmp_path / shape)
    assert result.cell_count > 0
    assert set(PATCHES) <= set(result.patches)


def test_flat_mound_meshes_cleanly(tmp_path):
    """A flat profile has a rectangular surface: the outline must not self-touch."""
    geom = BinGeometry(mound_shape="flat", mound_fill_fraction=0.5)
    result = generate_mesh(geom, 0.5, tmp_path / "flat")
    assert result.is_predominantly_hexahedral
    assert result.cell_count > 0


def test_element_types_are_known_names(mesh):
    assert set(mesh.element_types) <= {"hex", "prism", "pyr", "tet"}


def test_cell_count_matches_the_elements_in_the_written_file(mesh):
    """The persisted mesh count must be the number of cells, not node tags.

    ``gmsh.model.mesh.getElements`` returns ``(types, elementTags, nodeTags)``.
    The counter read ``len()`` of the node-tag arrays, so a hexahedron was
    counted eight times: the manifest recorded 3444 cells for a file that holds
    431, and the same inflated number was reported as the mesh-size evidence.
    """
    lines = mesh.msh_path.read_text().splitlines()
    start = lines.index("$Elements")
    declared = int(lines[start + 1])
    true_counts: dict[int, int] = {}
    for line in lines[start + 2 : start + 2 + declared]:
        element_type = int(line.split()[1])
        true_counts[element_type] = true_counts.get(element_type, 0) + 1
    volume_types = {4: "tet", 5: "hex", 6: "prism", 7: "pyr"}
    true_cells = sum(
        count for element_type, count in true_counts.items() if element_type in volume_types
    )

    assert mesh.cell_count == true_cells
    assert mesh.cell_count == sum(mesh.element_types.values())
    assert mesh.element_types.get("hex", 0) == true_counts.get(5, 0)
    assert mesh.element_types.get("prism", 0) == true_counts.get(6, 0)


@pytest.mark.parametrize(
    "kwargs",
    [{"mesh_size_m": 0.0}, {"air_extension_m": -1.0}, {"thickness_m": 0.0}],
)
def test_invalid_parameters_raise(tmp_path, kwargs):
    call = {"mesh_size_m": 0.5, **kwargs}
    with pytest.raises(ValueError):
        generate_mesh(BinGeometry(), out_dir=tmp_path, **call)
