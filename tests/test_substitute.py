"""Hydrogens replaced by a group: where it goes, what it is bonded to,
and what a space group allows.

On MOF-5, the sample, in P1 as shipped and in Fm-3m as found.  What
breaks if these regress: a group bonded to the wrong atom or to
everything near it, an undo that leaves a perceived graph behind, a
symmetric cell that grows four hydrogens on every nitrogen, or a
reduction to P1 that nobody is told about.
"""

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from xtal.build import MISSING
from xtal.build import installed as rdkit_installed
from xtal.commands import CommandStack, Host
from xtal.core import bonding, p1
from xtal.io import FORMATS

pytestmark = pytest.mark.skipif(not rdkit_installed(), reason=MISSING)

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"


@pytest.fixture
def mof5():
    return FORMATS.read(SAMPLES / "MOF-5.cif")


@pytest.fixture(scope="module")
def mof5_fm3m():
    from xtal.commands.symmetry import FindSymmetry

    found, _report = FindSymmetry(1e-2).apply_to(
        FORMATS.read(SAMPLES / "MOF-5.cif"))
    assert found.space_group.short_name == "Fm-3m"
    return found


def _ring_hydrogen(structure):
    """The first hydrogen of the P1 cell, and the carbon it is on."""
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    hydrogen = cell.elements.index("H")
    return hydrogen, graph.neighbors(hydrogen)[0]


def _substituted(structure, group, atoms=(), per_ring=False):
    from xtal.commands.atoms import SubstituteHydrogens

    host = Host(structure)
    stack = CommandStack()
    command = SubstituteHydrogens(group, atoms, per_ring=per_ring)
    stack.push(command, host)
    return host, stack, command


def test_a_substituted_hydrogen_becomes_the_group_bonded_to_its_carbon(
        mof5):
    """The hydrogen goes, and the nitrogen of an NH2 takes its place a
    C-N bond out along the old C-H -- bonded to that carbon and to its
    own two hydrogens, not left floating."""
    hydrogen, carbon = _ring_hydrogen(mof5)
    before = p1.expand(mof5)
    host, _stack, command = _substituted(mof5, "NH2", [hydrogen])

    cell = p1.expand(host.structure)
    graph = bonding.graph(host.structure)
    counts = Counter(cell.elements)
    assert counts["H"] == Counter(before.elements)["H"] - 1 + 2
    assert counts["N"] == 1
    nitrogen = cell.elements.index("N")
    partners = sorted(cell.elements[j] for j in graph.neighbors(nitrogen))
    assert partners == ["C", "H", "H"]
    reach = min(b.length(cell.frac, host.structure.lattice.matrix)
                for b in graph.bonds_of(nitrogen)
                if cell.elements[b.j if b.i == nitrogen else b.i] == "C")
    assert reach == pytest.approx(bonding.bond_distance("C", "N"),
                                  abs=1e-6)
    assert command.report.message.startswith("replaced 1 H with Amino")


def test_a_substitution_is_one_undo_step_and_undo_restores_the_graph(
        mof5):
    perceived = [b.key() for b in bonding.graph(mof5).bonds]
    sites = mof5.n_sites
    host, stack, _command = _substituted(mof5, "OMe", per_ring=True)
    assert host.structure.n_sites != sites

    stack.undo(host)

    assert host.structure.n_sites == sites
    assert [b.key() for b in bonding.graph(host.structure).bonds] == \
        perceived
    assert not stack.can_undo


def test_one_per_ring_puts_exactly_one_group_on_every_ring(mof5):
    """MOF-5 to IRMOF-3: one amine on each of the 24 rings in the cell,
    which is Zn4O(C8H5NO4)3 eight times over."""
    host, _stack, _command = _substituted(mof5, "NH2", per_ring=True)

    cell = p1.expand(host.structure)
    graph = bonding.graph(host.structure)
    assert Counter(cell.elements) == {"Zn": 32, "O": 104, "C": 192,
                                      "H": 120, "N": 24}
    for ring in bonding.aromatic_rings(cell, graph):
        amines = [j for member in ring for j in graph.neighbors(member)
                  if cell.elements[j] == "N"]
        assert len(amines) == 1


def test_the_group_is_turned_to_the_angle_with_the_most_room(mof5):
    """A nitro beside a carboxylate: every turn about the C-N bond is
    measured, brute force, and the one chosen has as much room as any
    to within the slack the choice allows."""
    from xtal.build import substitute
    from xtal.build.clearance import SLACK, turn

    hydrogen, carbon = _ring_hydrogen(mof5)
    group = substitute.group("NO2")
    placement = substitute.plan(mof5, group, [hydrogen]).placements[0]

    cell = p1.expand(mof5)
    lattice = mof5.lattice
    keep = [k for k in range(cell.n_atoms) if k not in (hydrogen, carbon)]
    others = lattice.to_cart(cell.frac[keep])
    shifts = np.array([[a, b, c] for a in (-1, 0, 1) for b in (-1, 0, 1)
                       for c in (-1, 0, 1)], dtype=float) @ lattice.matrix
    images = (others[None] + shifts[:, None]).reshape(-1, 3)
    origin = placement.cart[group.attach]
    axis = origin - lattice.to_cart(cell.frac[carbon])
    axis = axis - np.round(lattice.to_frac(axis)) @ lattice.matrix
    axis /= np.linalg.norm(axis)
    moving = [k for k in range(group.n_atoms) if k != group.attach]

    def room(points):
        gap = np.linalg.norm(points[moving][:, None] - images[None], axis=2)
        return float(gap.min())

    best = max(room(turn(placement.cart, axis, origin, np.radians(a)))
               for a in range(0, 360, 5))
    assert room(placement.cart) >= best - SLACK - 0.05


def test_substituting_in_a_symmetric_cell_substitutes_the_orbit(
        mof5_fm3m):
    """One hydrogen stands for its site: every one of its 96 copies
    becomes a fluorine, and Fm-3m is kept -- a single atom keeps any
    symmetry the hydrogen had."""
    hydrogen, _carbon = _ring_hydrogen(mof5_fm3m)
    host, _stack, command = _substituted(mof5_fm3m, "F", [hydrogen])

    assert host.structure.space_group.short_name == "Fm-3m"
    counts = Counter(p1.expand(host.structure).elements)
    assert counts["F"] == 96 and "H" not in counts
    assert "keeping Fm-3m" in command.report.message
    assert command.report.warnings == []


def test_a_group_that_breaks_the_site_symmetry_reduces_to_p1_and_says_so(
        mof5_fm3m):
    """An NH2's hydrogens are off the mirror its carbon sits on, so the
    group would multiply them onto each other: two hydrogens on every
    nitrogen, not four, and the reduction said."""
    hydrogen, _carbon = _ring_hydrogen(mof5_fm3m)
    host, _stack, command = _substituted(mof5_fm3m, "NH2", [hydrogen])

    assert host.structure.space_group.is_p1
    counts = Counter(p1.expand(host.structure).elements)
    assert counts["N"] == 96 and counts["H"] == 192
    assert any(w.startswith("reduced from Fm-3m")
               for w in command.report.warnings)


def test_one_per_ring_in_a_group_that_ties_the_ring_reduces_to_p1_and_says_so(
        mof5_fm3m):
    host, _stack, command = _substituted(mof5_fm3m, "NH2", per_ring=True)

    assert host.structure.space_group.is_p1
    assert Counter(p1.expand(host.structure).elements)["N"] == 24
    assert any("one group per ring is not an orbit" in w
               for w in command.report.warnings)


def test_nothing_is_perceived_the_group_bonds_only_as_built(mof5):
    """Every bond the framework had is still there bar the C-H that
    went, and what arrived is the group's own bonds and one to its
    carbon each -- a methoxy's methyl a contact from a carboxylate is
    not bonded to it."""
    before = {b.key() for b in bonding.graph(mof5).bonds}
    host, _stack, _command = _substituted(mof5, "OMe", per_ring=True)

    cell = p1.expand(host.structure)
    after = bonding.graph(host.structure).bonds
    old = p1.expand(mof5).n_atoms - 24
    kept = [b for b in after if b.i < old and b.j < old]
    new = [b for b in after if b.i >= old or b.j >= old]
    assert len(kept) == len(before) - 24
    # OCH3: O-C and three C-H, and O to the ring carbon.
    assert len(new) == 24 * 5
    crossing = [b for b in new if (b.i < old) != (b.j < old)]
    assert len(crossing) == 24
    assert all(cell.elements[min(b.i, b.j)] == "C" for b in crossing)


def test_a_group_with_no_room_is_said_not_hidden(mof5):
    """A phenyl on every BDC of MOF-5 cannot fit with the ring held
    still: the edit is made, and the report says how close it came."""
    _host, _stack, command = _substituted(mof5, "Ph", per_ring=True)

    assert any("would have to turn" in w for w in command.report.warnings)


def test_an_atom_that_is_not_a_hydrogen_is_refused_by_name(mof5):
    from xtal.commands.atoms import SubstituteHydrogens

    carbon = p1.expand(mof5).elements.index("C")
    _new, report = SubstituteHydrogens("NH2", [carbon]).apply_to(mof5)

    assert not report.ok
    assert "is not a hydrogen" in report.message
