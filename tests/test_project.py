"""The .xtalproj project file.

A project is the one format that keeps a whole session, so what these
check is mostly *loss*: what a CIF drops and a project must not.
"""

import json
import zipfile

import pytest

from xtal import Lattice, Structure
from xtal.core import bonding, p1
from xtal.core.structure import Bond
from xtal.io import (
    FORMATS,
    is_project,
    read_project,
    write_project,
)
from xtal.io.project import STRUCTURE_PART


@pytest.fixture
def bonded(rutile):
    """Rutile with a hand-drawn bond and a suppressed one -- the parts
    a CIF cannot carry."""
    cell = p1.expand(rutile)
    drawn = bonding.graph(rutile).bonds[0]
    rutile.add_bond(bonding.bond_between(rutile, cell, drawn.i,
                                         drawn.j, (0, 0, 0),
                                         drawn.image))
    rutile.add_bond(Bond(0, 1, image=(1, 0, 0), kind="suppressed",
                         op=3))
    rutile.bond_rules = {"scale": 1.2}
    return rutile


def test_a_project_round_trips_the_structure(tmp_path, bonded):
    bonded.ensure_labels()          # writing a CIF names the sites
    path = write_project(bonded, tmp_path / "demo.xtalproj")
    back, view, session = read_project(path)
    assert back == bonded
    assert back.space_group == bonded.space_group
    assert view == {} and "version" in session


def test_a_project_keeps_the_bonds_a_cif_would_lose(tmp_path, bonded):
    """A bond here is (site, site, operation, translation); there is no
    CIF tag for that, so it is written beside the CIF."""
    from xtal.io import read_cif, write_cif

    write_cif(bonded, tmp_path / "plain.cif")
    assert read_cif(tmp_path / "plain.cif").bonds == []

    path = write_project(bonded, tmp_path / "demo.xtalproj")
    back, _view, _session = read_project(path)
    assert len(back.bonds) == 2
    assert {b.op for b in back.bonds} == {b.op for b in bonded.bonds}
    assert {b.kind for b in back.bonds} == {"explicit", "suppressed"}
    assert back.bond_rules == {"scale": 1.2}
    # ... and the bonds still mean the same thing after the trip
    assert (len(bonding.perceive(back))
            == len(bonding.perceive(bonded)))


def test_a_project_keeps_the_view_and_the_session(tmp_path, rutile):
    view = {"style": "polyhedra", "atom_scale": 0.6,
            "element_colors": {"Ti": [1, 2, 3]}}
    session = {"selection": [0, 2], "measurements": []}
    path = write_project(rutile, tmp_path / "demo.xtalproj",
                         view=view, session=session)
    _back, got_view, got_session = read_project(path)
    assert got_view == view
    assert got_session["selection"] == [0, 2]


def test_a_project_is_a_zip_of_readable_text(tmp_path, bonded):
    """Openable in five years and diffable today: nothing in here is
    a pickle."""
    path = write_project(bonded, tmp_path / "demo.xtalproj",
                         view={"style": "stick"})
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert set(names) == {"structure.cif", "bonds.json",
                              "view.json", "session.json"}
        cif = archive.read(STRUCTURE_PART).decode()
        assert "_cell_length_a" in cif
        assert json.loads(archive.read("view.json"))["style"] == "stick"


def test_the_extension_is_added_if_it_is_missing(tmp_path, rutile):
    written = write_project(rutile, tmp_path / "noextension")
    assert written.suffix == ".xtalproj"
    assert written.exists()


def test_the_registry_reads_and_writes_projects(tmp_path, bonded):
    """Registered like any other format, so the open dialog, the save
    dialog and drag-and-drop all get it without knowing about it."""
    path = tmp_path / "viaregistry.xtalproj"
    FORMATS.write(bonded, path)
    assert FORMATS.read(path).n_sites == bonded.n_sites
    assert "xtalproj" in FORMATS
    assert any("xtalproj" in f.filter_string()
               for f in FORMATS.readable())
    assert is_project(path)
    assert not is_project(tmp_path / "something.cif")


def test_a_file_that_is_not_a_project_is_refused(tmp_path):
    plain = tmp_path / "notazip.xtalproj"
    plain.write_text("this is not a zip")
    with pytest.raises(ValueError, match="not a project"):
        read_project(plain)

    empty = tmp_path / "emptyzip.xtalproj"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("readme.txt", "nothing here")
    with pytest.raises(ValueError, match="no structure.cif"):
        read_project(empty)


def test_a_project_from_a_later_version_still_gives_up_its_crystal(
        tmp_path, rutile):
    """Losing a view setting is not a reason to lose a structure."""
    path = write_project(rutile, tmp_path / "future.xtalproj")
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("view.json", "{ not json at all")
    back, view, _session = read_project(path)
    assert back.n_sites == rutile.n_sites
    assert view == {}


def test_a_bond_that_no_longer_fits_is_dropped_not_fatal(tmp_path,
                                                          rutile):
    path = write_project(rutile, tmp_path / "demo.xtalproj")
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("bonds.json", json.dumps(
            {"bonds": [{"i": 0, "j": 99, "image": [0, 0, 0]},
                       {"i": 0, "j": 1, "image": [0, 0, 0], "op": 0}]}))
    back, _view, _session = read_project(path)
    assert len(back.bonds) == 1                  # the good one survived
    assert any("unreadable bond" in w
               for w in back.meta.get("warnings", []))


def test_a_project_survives_a_structure_it_cannot_simplify(tmp_path,
                                                           halite):
    """A 192-operation group with a bond on a high-index operation is
    the case where an index-based bond is most likely to be mangled."""
    cell = p1.expand(halite)
    drawn = bonding.graph(halite).bonds[0]
    stored = bonding.bond_between(halite, cell, drawn.i, drawn.j,
                                  (0, 0, 0), drawn.image)
    halite.add_bond(stored)
    assert stored.op > 0                         # not the easy case

    path = write_project(halite, tmp_path / "halite.xtalproj")
    back, _view, _session = read_project(path)
    assert back.bonds == [stored]
    assert ({b.key() for b in bonding.perceive(back)}
            == {b.key() for b in bonding.perceive(halite)})


def test_an_empty_structure_makes_a_valid_project(tmp_path):
    empty = Structure.empty(Lattice.cubic(5.0))
    path = write_project(empty, tmp_path / "empty.xtalproj")
    back, _view, _session = read_project(path)
    assert back.n_sites == 0
    assert back.lattice.almost_equal(empty.lattice)
