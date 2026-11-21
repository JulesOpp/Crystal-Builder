"""The two-colour print writers: binary STL and a 3MF of two parts."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest

from xtal.io.stl import read_stl, write_stl
from xtal.io.threemf import (
    BAMBU_CONFIG,
    CORE_NS,
    MODEL_PATH,
    PRUSA_CONFIG,
    Part,
    write_3mf,
)

# Corners of the unit cube, and its faces wound counter-clockwise seen
# from outside, two triangles each.
_CORNERS = np.array([[x, y, z] for z in (0, 1) for y in (0, 1)
                     for x in (0, 1)], dtype=float)
_FACES = np.array([
    [0, 2, 1], [1, 2, 3],   # z = 0
    [4, 5, 6], [5, 7, 6],   # z = 1
    [0, 1, 4], [1, 5, 4],   # y = 0
    [2, 6, 3], [3, 6, 7],   # y = 1
    [0, 4, 2], [2, 4, 6],   # x = 0
    [1, 3, 5], [3, 7, 5],   # x = 1
])

NS = {"m": CORE_NS}


def _cube(offset) -> tuple[np.ndarray, np.ndarray]:
    # 0.1 is not a float32, so the shared face is only shared if both
    # writers round it the same way.
    return _CORNERS * 1.1 + np.asarray(offset) * 1.1 + 0.1, _FACES


@pytest.fixture
def two_cubes():
    """Two cubes meeting at the face x = 1.2."""
    return [Part("colour 1", *_cube((0, 0, 0)), extruder=1),
            Part("colour 2", *_cube((1, 0, 0)), extruder=2)]


def _model(path):
    with zipfile.ZipFile(path) as archive:
        return ET.fromstring(archive.read(MODEL_PATH))


def _mesh_vertices(obj) -> np.ndarray:
    return np.array([[float(v.get(k)) for k in "xyz"]
                     for v in obj.iterfind("m:mesh/m:vertices/m:vertex",
                                           NS)], dtype=np.float32)


def test_a_3mf_holds_one_object_of_two_parts_on_extruders_one_and_two(
        tmp_path, two_cubes):
    """If this breaks, Bambu Studio lays the two colours out as two
    objects apart on the bed, or prints both with one filament."""
    path = write_3mf(tmp_path / "print.3mf", two_cubes)
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert {"[Content_Types].xml", "_rels/.rels", MODEL_PATH,
                BAMBU_CONFIG, PRUSA_CONFIG} <= names
        model = ET.fromstring(archive.read(MODEL_PATH))
        bambu = ET.fromstring(archive.read(BAMBU_CONFIG))
        prusa = ET.fromstring(archive.read(PRUSA_CONFIG))
    assert model.get("unit") == "millimeter"
    items = model.findall("m:build/m:item", NS)
    assert len(items) == 1
    objects = {o.get("id"): o for o in model.iterfind(
        "m:resources/m:object", NS)}
    top = objects[items[0].get("objectid")]
    refs = [c.get("objectid") for c in top.iterfind(
        "m:components/m:component", NS)]
    assert len(refs) == 2
    assert all(objects[r].find("m:mesh", NS) is not None for r in refs)

    (config,) = bambu.findall("object")
    assert config.get("id") == top.get("id")
    parts = config.findall("part")
    assert [p.get("id") for p in parts] == refs
    extruders = [p.find("metadata[@key='extruder']").get("value")
                 for p in parts]
    assert extruders == ["1", "2"]

    by_id = {o.get("id"): o for o in prusa.findall("object")}
    assert [by_id[r].find("volume/metadata[@key='extruder']").get("value")
            for r in refs] == ["1", "2"]


def test_the_stl_round_trips_its_triangles(tmp_path, two_cubes):
    """If this breaks, the STL a person prints is not the mesh the
    mesher made."""
    part = two_cubes[0]
    path = write_stl(tmp_path / "one.stl", part.vertices, part.triangles,
                     name="colour 1")
    vertices, triangles = read_stl(path)
    assert path.stat().st_size == 84 + 50 * len(part.triangles)
    assert len(vertices) == 8
    original = part.vertices.astype(np.float32)[part.triangles]
    np.testing.assert_array_equal(vertices[triangles], original)


def test_the_two_stls_and_the_3mf_share_coordinates(tmp_path, two_cubes):
    """If this breaks, the shared face lands a rounding apart in the
    two files, and a slicer sees two bodies that gap or overlap."""
    stl_vertices = []
    for i, part in enumerate(two_cubes):
        path = write_stl(tmp_path / f"{i}.stl", part.vertices,
                         part.triangles)
        stl_vertices.append(read_stl(path)[0])
    on_face = [v[np.isclose(v[:, 0], 1.2)] for v in stl_vertices]
    assert len(on_face[0]) == 4
    assert {tuple(v) for v in on_face[0]} == {tuple(v) for v in on_face[1]}

    model = _model(write_3mf(tmp_path / "print.3mf", two_cubes))
    meshes = [o for o in model.iterfind("m:resources/m:object", NS)
              if o.find("m:mesh", NS) is not None]
    for mesh, from_stl in zip(meshes, stl_vertices, strict=True):
        assert ({tuple(v) for v in _mesh_vertices(mesh)}
                == {tuple(v) for v in from_stl})


def test_an_empty_part_is_left_out_of_the_3mf(tmp_path, two_cubes):
    """If this breaks, a colour with nothing in it writes an object with
    an empty mesh, and the slicer refuses the whole file."""
    empty = Part("nothing", np.zeros((0, 3)), np.zeros((0, 3), int), 3)
    path = write_3mf(tmp_path / "print.3mf", [two_cubes[0], empty])
    model = _model(path)
    with zipfile.ZipFile(path) as archive:
        bambu = ET.fromstring(archive.read(BAMBU_CONFIG))
    meshes = [o for o in model.iterfind("m:resources/m:object", NS)
              if o.find("m:mesh", NS) is not None]
    assert len(meshes) == 1
    assert [p.find("metadata[@key='name']").get("value")
            for p in bambu.iter("part")] == ["colour 1"]


def test_stl_normals_follow_the_winding(tmp_path, two_cubes):
    """If this breaks, a slicer that trusts the stored normals sees the
    cube inside out."""
    part = two_cubes[0]
    path = write_stl(tmp_path / "one.stl", part.vertices, part.triangles)
    data = path.read_bytes()
    records = np.frombuffer(data, dtype=np.dtype([
        ("normal", "<f4", 3), ("vertices", "<f4", (3, 3)),
        ("attribute", "<u2")]), offset=84)
    centre = part.vertices.mean(axis=0)
    outward = records["vertices"].mean(axis=1) - centre
    assert np.all(np.einsum("ij,ij->i", records["normal"], outward) > 0)
    np.testing.assert_allclose(np.linalg.norm(records["normal"], axis=1),
                               1.0, rtol=1e-6)
    flipped = write_stl(tmp_path / "flipped.stl", part.vertices,
                        part.triangles[:, ::-1])
    back = np.frombuffer(flipped.read_bytes(), dtype=records.dtype,
                         offset=84)
    np.testing.assert_allclose(back["normal"], -records["normal"])
