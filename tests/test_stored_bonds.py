"""The bond graph as a thing the structure owns.

Perception used to be a memo: derived on demand, thrown away by the
next topology change, and re-run from scratch when a document was
reopened.  It is now a field -- ``Structure.perceived`` -- which is
what lets a recalculated graph survive a save, lets an added atom
perceive only its own bonds, and lets a bond keep pointing at the right
partner when an atom drifts across a cell face.

These tests are about that field: when it is written, when it is
reused, when it is thrown away, and what it is worth.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import bonding, p1
from xtal.core.structure import Bond, Change


def drawn_bond_lengths(structure) -> list[float]:
    """The length of every bond *as the viewport would draw it*.

    Not ``CellBond.distance``, which is what the bond measured when it
    was perceived.  This is what the picture actually shows, and it is
    where a stale periodic image turns into a line across the crystal.
    """
    cell = p1.expand(structure)
    out = []
    for bond in bonding.perceive(structure):
        separation = (cell.frac[bond.j] + np.array(bond.image)
                      - cell.frac[bond.i])
        out.append(float(np.linalg.norm(
            separation @ structure.lattice.matrix)))
    return out


@pytest.fixture
def straddling() -> Structure:
    """Two carbons bonded through the x = 0 face, 1.36 A apart."""
    return Structure.from_arrays(
        Lattice.cubic(8.0), ["C", "C"],
        [[0.02, 0.5, 0.5], [0.85, 0.5, 0.5]])


# ======================================================================
#  IT IS STORED
# ======================================================================

def test_perceiving_writes_the_graph_onto_the_structure(rutile):
    assert rutile.perceived is None
    bonds = bonding.perceive(rutile)
    assert rutile.perceived is not None
    assert len(rutile.perceived.bonds) == len(bonds)
    assert rutile.perceived.elements == p1.expand(rutile).elements


def test_a_stored_graph_is_reused_rather_than_perceived_again(
        rutile, monkeypatch):
    bonding.perceive(rutile)
    calls = []
    original = bonding._search
    monkeypatch.setattr(bonding, "_search",
                        lambda *a, **k: (calls.append(k.get("subset")),
                                         original(*a, **k))[1])

    rutile.touch(Change.TOPOLOGY)       # drops the memo, not the store
    bonding.perceive(rutile)
    assert calls == []


def test_changing_the_rules_perceives_again(rutile):
    """A stored graph is the answer, not an override: loosening the
    criteria has to still change what is found."""
    before = len(bonding.perceive(rutile))
    rutile.bond_rules = {"scale": 0.5}
    rutile.touch(Change.TOPOLOGY)
    assert len(bonding.perceive(rutile)) < before
    assert rutile.perceived.signature.startswith("0.5|")


def test_asking_with_other_rules_does_not_overwrite_the_store(rutile):
    """The bond rules dialog previews criteria the structure has not
    adopted; that must not quietly become what the document holds."""
    bonding.perceive(rutile)
    stored = rutile.perceived

    loose = bonding.BondRules(scale=2.0)
    assert len(bonding.perceive(rutile, loose)) != len(stored.bonds)
    assert rutile.perceived is stored


def test_removing_a_site_perceives_again(rutile):
    bonding.perceive(rutile)
    rutile.remove_sites([1])
    assert bonding.perceive(rutile) == []
    assert rutile.perceived.elements == ("Ti", "Ti")


def test_a_new_lattice_throws_the_graph_away(rutile):
    bonding.perceive(rutile)
    rutile.set_lattice(Lattice.cubic(20.0))
    assert rutile.perceived is None


# ======================================================================
#  ADDING AN ATOM
# ======================================================================

def test_adding_an_atom_perceives_only_that_atom(straddling,
                                                 monkeypatch):
    """The point of storing the graph rather than memoising it: an
    added atom used to invalidate the lot, so dropping a hydrogen into
    a framework re-derived every bond in it."""
    from xtal.core.site import Site

    before = {b.key() for b in bonding.perceive(straddling)}
    searched = []
    original = bonding._search
    monkeypatch.setattr(
        bonding, "_search",
        lambda *a, **k: (searched.append(k.get("subset")),
                         original(*a, **k))[1])

    straddling.add_site(Site("C", [0.71, 0.5, 0.5]))
    after = {b.key() for b in bonding.perceive(straddling)}

    assert len(searched) == 1
    assert list(searched[0]) == [2]          # the new atom, nobody else
    assert before < after                    # the old bonds are intact
    assert len(after) == len(before) + 1


def test_the_incremental_graph_is_the_one_a_full_perception_gives(
        straddling):
    """Cheaper has to mean cheaper, not different."""
    from xtal.core.site import Site

    bonding.perceive(straddling)             # store it first
    straddling.add_site(Site("C", [0.71, 0.5, 0.5]))
    incremental = {b.key() for b in bonding.perceive(straddling)}

    fresh = straddling.copy()
    fresh.clear_perceived()
    assert {b.key() for b in bonding.perceive(fresh)} == incremental


# ======================================================================
#  THE WRAP
# ======================================================================

def test_a_bond_follows_an_atom_across_the_cell_face(straddling):
    """The failure this pins was visible from across the room: an atom
    relaxing past x = 0 is redrawn at x = 1, and its bonds were left
    pointing at where it used to be -- a line the full width of the
    crystal.

    Perception is not re-run when atoms move, and it should not be.
    What has to move is the periodic image each bond carries.
    """
    assert drawn_bond_lengths(straddling) == pytest.approx([1.36])

    straddling.set_frac(0, [-0.01, 0.5, 0.5])   # redrawn at x = 0.99
    assert drawn_bond_lengths(straddling) == pytest.approx([1.12])


def test_the_wrap_correction_costs_nothing_when_nothing_wrapped(
        straddling):
    """It is checked on every frame, so the common answer has to be
    the cheap one: the same objects, not a rebuilt graph."""
    first = bonding.graph(straddling)
    straddling.set_frac(0, [0.03, 0.5, 0.5])
    assert bonding.graph(straddling) is first

    straddling.set_frac(0, [-0.01, 0.5, 0.5])
    assert bonding.graph(straddling) is not first


def test_rebase_is_its_own_inverse(straddling):
    bonds = bonding.perceive(straddling)
    tau = np.zeros((2, 3), dtype=int)
    other = np.array([[1, 0, 0], [0, -1, 0]])
    there = bonding.rebase(bonds, tau, other)
    assert [b.key() for b in bonding.rebase(there, other, tau)] == \
        [b.key() for b in bonds]


# ======================================================================
#  IT SURVIVES A SAVE
# ======================================================================

def test_a_project_round_trip_keeps_the_perceived_graph(rutile,
                                                        tmp_path):
    from xtal.io.project import read_project, write_project

    keys = {b.key() for b in bonding.perceive(rutile)}
    rutile.set_frac(1, [0.45, 0.45, 0.0])    # bonds do not follow
    assert {b.key() for b in bonding.perceive(rutile)} == keys

    path = write_project(rutile, tmp_path / "p.xtalproj")
    back, _view, _session = read_project(path)

    assert back.perceived is not None
    assert {b.key() for b in bonding.perceive(back)} == keys
    # and it is the stored graph that said so, not a fresh perception
    fresh = back.copy()
    fresh.clear_perceived()
    assert {b.key() for b in bonding.perceive(fresh)} != keys


def test_a_round_trip_keeps_the_suppressions_layered_on_it(rutile,
                                                           tmp_path):
    from xtal.io.project import read_project, write_project

    doomed = bonding.graph(rutile).bonds[0]
    drawn = bonding.bond_between(rutile, p1.expand(rutile), doomed.i,
                                 doomed.j, image_b=doomed.image)
    rutile.add_bond(Bond(drawn.i, drawn.j, drawn.image, drawn.order,
                         "suppressed", drawn.op))
    keys = {b.key() for b in bonding.perceive(rutile)}
    assert doomed.key() not in keys

    path = write_project(rutile, tmp_path / "p.xtalproj")
    back, _view, _session = read_project(path)
    assert {b.key() for b in bonding.perceive(back)} == keys


def test_an_unreadable_stored_graph_is_a_warning_not_a_lost_crystal(
        rutile, tmp_path):
    import json
    import zipfile

    from xtal.io.project import read_project, write_project

    bonding.perceive(rutile)
    path = write_project(rutile, tmp_path / "p.xtalproj")
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("bonds.json", json.dumps(
            {"perceived": {"signature": "x", "elements": ["Ti"],
                           "tau": [], "bonds": []}}))

    back, _view, _session = read_project(path)
    assert back.n_sites == 2
    assert any("stored bond graph" in w
               for w in back.meta.get("warnings", []))
    assert len(bonding.perceive(back)) == 12


def test_a_copy_carries_the_graph_without_perceiving_it_again(rutile):
    """The optimiser hands a copy to a worker thread; it must not pay
    for perception twice, and must not share a list with the document.
    """
    bonding.perceive(rutile)
    copy = rutile.copy()
    assert copy.perceived is not rutile.perceived
    assert copy.perceived.bonds == rutile.perceived.bonds
