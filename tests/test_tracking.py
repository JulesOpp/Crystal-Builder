"""The same atoms found again after an edit renumbers the cell.

Headless: ``xtal.core.tracking`` is what keeps View > Show Only
Selected's hidden set on its atoms -- through an ordinary edit by
where they were, through a symmetry or cell change by the map the
operation states.  The window's half is in ``test_show_only.py``.
"""

from pathlib import Path

import numpy as np
import pytest

from xtal.commands import CommandStack, Host
from xtal.commands.atoms import DeleteSites, SubstituteHydrogens
from xtal.commands.base import StructureOperation
from xtal.commands.cell import (
    MakeSlab,
    ReduceCell,
    ShiftOrigin,
    Supercell,
    TransformCell,
    WrapIntoCell,
)
from xtal.commands.interpenetrate import Interpenetrate
from xtal.commands.prepare import Prepare
from xtal.commands.symmetry import (
    AssignWyckoff,
    DescendToSubgroup,
    FindSymmetry,
    Invert,
    MergeDuplicates,
    ReduceToP1,
    SetSpaceGroup,
    Standardize,
)
from xtal.core import p1, symmetry, tracking
from xtal.core.lattice import Lattice
from xtal.core.structure import Bond, Structure


def test_atoms_are_found_again_after_a_renumbering_edit(rutile):
    """Deleting the first Ti moves every index after it down one; the
    recorded oxygens are found at their new numbers, and a set of the
    old indices would have named the wrong atoms."""
    host, stack = Host(symmetry.reduce_to_p1(rutile)), CommandStack()
    cell = p1.expand(host.structure)
    oxygens = {a for a in range(cell.n_atoms) if cell.elements[a] == "O"}
    where = tracking.record(cell, oxygens)
    assert len(where) == len(oxygens) == 4

    first_ti = cell.elements.index("Ti")
    assert first_ti < min(oxygens)
    stack.push(DeleteSites([first_ti]), host)
    after = p1.expand(host.structure)

    found = tracking.find(after, where)
    assert found == {a - 1 for a in oxygens}
    assert all(after.elements[a] == "O" for a in found)


def test_an_atom_the_edit_removed_is_not_found(rutile):
    """A recorded atom that is gone is simply not found -- never
    matched to whatever now sits nearest."""
    host, stack = Host(symmetry.reduce_to_p1(rutile)), CommandStack()
    cell = p1.expand(host.structure)
    where = tracking.record(cell, [0, 1])
    stack.push(DeleteSites([0]), host)
    after = p1.expand(host.structure)
    assert tracking.find(after, where) == {0}


# ------------------------------------- through a symmetry or cell change


SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"


def _pushed(structure, command):
    """``(host, stack, before, after)`` with ``command`` run once."""
    host, stack = Host(structure), CommandStack()
    before = p1.expand(structure)
    stack.push(command, host)
    return host, stack, before, p1.expand(host.structure)


def _followed(before, structure_before, after, structure_after, atoms,
              via):
    where = tracking.record(before, atoms, structure_before.lattice)
    return tracking.follow(after, structure_after.lattice, where, via)


def _through(structure, command, atoms):
    """The atoms of the new cell that ``atoms`` of the old one are."""
    host, _stack, before, after = _pushed(structure, command)
    return after, _followed(before, structure, after, host.structure,
                            atoms, command.atom_map())


def test_a_supercell_carries_every_copy_of_a_tracked_atom(rutile):
    """One Ti tracked in the cell is both its copies in a 2x1x1: the
    supercell's fractions are half the cell's, so matching them as
    they stand found one Ti of twelve atoms."""
    cell = p1.expand(rutile)
    ti = cell.elements.index("Ti")
    after, found = _through(rutile, Supercell(2, 1, 1), [ti])
    assert len(found) == 2
    assert all(after.elements[a] == "Ti" for a in found)
    lattice = rutile.lattice.matrix
    home = cell.frac[ti] @ lattice
    for a in found:
        d = after.frac[a] @ (Supercell(2, 1, 1).apply_to(rutile)[0]
                             .lattice.matrix) - home
        # each copy is the tracked atom moved by a lattice vector
        shift = d @ np.linalg.inv(lattice)
        assert np.allclose(shift, np.round(shift), atol=1e-6)


def test_a_primitive_cell_keeps_an_atom_if_any_copy_it_stands_for_was_tracked(
        halite):
    """Halite's conventional cell has four Na for every one of the
    primitive cell's; tracking one of the four that is not the one the
    primitive atom lands on still keeps it."""
    cell = p1.expand(halite)
    sodium = [a for a in range(cell.n_atoms) if cell.elements[a] == "Na"]
    assert len(sodium) == 4
    for na in sodium:
        after, found = _through(halite, Standardize(to_primitive=True),
                                [na])
        assert after.n_atoms == 2
        assert [after.elements[a] for a in found] == ["Na"]


def _origin_movers():
    from xtal.io import read_cif

    return [("ZIF-8", read_cif(SAMPLES / "ZIF-8.cif")),
            ("MIL-53", read_cif(SAMPLES / "cod" / "MIL-53.cif"))]


@pytest.mark.slow
@pytest.mark.parametrize("name", ["ZIF-8", "MIL-53"])
def test_standardizing_a_cell_that_moves_its_origin_keeps_the_same_atoms(
        name):
    """ZIF-8 and MIL-53 come out of Standardize with their origin
    moved: matched by where they were, 9 of ZIF-8's 102 atoms and none
    of MIL-53's were found.  spglib's own transformation finds all of
    them, and a tracked metal is one metal, where that one went."""
    structure = dict(_origin_movers())[name]
    cell = p1.expand(structure)
    everything = range(cell.n_atoms)
    after, found = _through(structure, Standardize(), everything)
    assert found == set(range(after.n_atoms))

    metal = next(e for e in ("Zn", "Cr") if e in cell.elements)
    one = cell.elements.index(metal)
    command = Standardize()
    host, _stack, before, after = _pushed(structure, command)
    found = _followed(before, structure, after, host.structure, [one],
                      command.atom_map())
    assert len(found) == 1
    (atom,) = found
    assert after.elements[atom] == metal
    went = command.atom_map().forward(cell.frac[one])
    d = after.frac[atom] - went
    d -= np.round(d)
    assert np.linalg.norm(d @ host.structure.lattice.matrix) < 1e-3


def test_inverting_quartz_keeps_the_same_atoms(quartz):
    """Inverting a chiral crystal moves every atom: matched by where
    they were, none of quartz's nine was found."""
    cell = p1.expand(quartz)
    after, found = _through(quartz, Invert(), range(cell.n_atoms))
    assert found == set(range(after.n_atoms))
    silicon = cell.elements.index("Si")
    after, found = _through(quartz, Invert(), [silicon])
    assert [after.elements[a] for a in found] == ["Si"]


def test_undoing_a_standardize_puts_the_atoms_back():
    """Standardize then Ctrl+Z: the map inverted finds the tracked atom
    where it started, not wherever its new number now points."""
    structure = _origin_movers()[0][1]
    cell = p1.expand(structure)
    zinc = [a for a in range(cell.n_atoms) if cell.elements[a] == "Zn"]
    command = Standardize()
    host, stack, before, after = _pushed(structure, command)
    found = _followed(before, structure, after, host.structure, zinc[:2],
                      command.atom_map())
    standard = host.structure
    stack.undo(host)
    back = tracking.follow(
        p1.expand(host.structure), host.structure.lattice,
        tracking.record(after, found, standard.lattice),
        command.atom_map().inverse())
    assert back == set(zinc[:2])


def _pcu():
    s = Structure.from_arrays(Lattice.cubic(4.0), ["C"], [[0, 0, 0]])
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        s.add_bond(Bond(0, 0, image))
    return s


def _methane():
    """A CH4 in a 10 A box, bonded by hand, for Substitute."""
    d = 1.09 / np.sqrt(3) / 10.0
    s = Structure.from_arrays(
        Lattice.cubic(10.0), ["C", "H", "H", "H", "H"],
        [[0.5, 0.5, 0.5], [0.5 + d, 0.5 + d, 0.5 + d],
         [0.5 - d, 0.5 - d, 0.5 + d], [0.5 - d, 0.5 + d, 0.5 - d],
         [0.5 + d, 0.5 - d, 0.5 - d]])
    for h in range(1, 5):
        s.add_bond(Bond(0, h, (0, 0, 0)))
    return s


def _subgroup_of(structure):
    """A maximal subgroup that changes the cell, so the descent has a
    basis or an origin to state."""
    from xtal.core import subgroups

    for subgroup in subgroups.maximal_subgroups(structure.space_group):
        if subgroup.group is not None and not subgroup.keeps_the_cell:
            return subgroup
    return None


#: Every StructureOperation, and the structures it is run on, with how
#: many atoms of the result it adds rather than carries (an int), or
#: also which old atoms it takes away (``(added, removed)``).  A new
#: operation missing from here fails the first test below.
def _cases(rutile, quartz, halite):
    from xtal.analysis import interpenetrate

    p1_rutile = symmetry.reduce_to_p1(rutile)
    return {
        ReduceToP1: [(s, ReduceToP1(), 0) for s in (rutile, quartz,
                                                    halite)],
        FindSymmetry: [(symmetry.reduce_to_p1(s), FindSymmetry(1e-3),
                        0) for s in (rutile, quartz, halite)]
        + [(symmetry.reduce_to_p1(s), FindSymmetry(1e-3, True), 0)
           for s in (rutile, quartz, halite)],
        SetSpaceGroup: [(p1_rutile, SetSpaceGroup(rutile.space_group,
                                                  "impose"), 0)],
        Standardize: [(s, Standardize(to_primitive=prim,
                                      idealize=ideal), 0)
                      for s in (rutile, quartz, halite)
                      for prim in (False, True)
                      for ideal in (True, False)],
        AssignWyckoff: [(s, AssignWyckoff(), 0)
                        for s in (rutile, quartz, halite)],
        Invert: [(s, Invert(), 0) for s in (rutile, quartz, halite)],
        DescendToSubgroup: [(s, DescendToSubgroup(_subgroup_of(s)), 0)
                            for s in (rutile, quartz, halite)
                            if _subgroup_of(s) is not None],
        MergeDuplicates: [(s, MergeDuplicates(), 0)
                          for s in (rutile, quartz, halite)],
        Supercell: [(s, Supercell(2, 1, 2), 0)
                    for s in (rutile, quartz, halite)],
        TransformCell: [(s, TransformCell([[1, 1, 0], [-1, 1, 0],
                                           [0, 0, 1]]), 0)
                        for s in (rutile, quartz, halite)],
        MakeSlab: [(s, MakeSlab((1, 1, 0), 2, 10.0), 0)
                   for s in (rutile, quartz, halite)],
        ReduceCell: [(s, ReduceCell(kind), 0)
                     for s in (rutile, quartz, halite)
                     for kind in ("niggli", "delaunay")],
        ShiftOrigin: [(symmetry.reduce_to_p1(s),
                       ShiftOrigin([0.1, 0.2, 0.3]), 0)
                      for s in (rutile, quartz, halite)],
        WrapIntoCell: [(s, WrapIntoCell(), 0)
                       for s in (rutile, quartz, halite)],
        Prepare: [(s, Prepare(), 0) for s in (rutile, quartz, halite)],
        Interpenetrate: [(_pcu(), Interpenetrate(
            interpenetrate.best(_pcu(), 2)), 1)],
        SubstituteHydrogens: [(_methane(), SubstituteHydrogens(
            "F", [1]), (1, {1}))],
    }


def _operations():
    """Every StructureOperation under xtal.commands, imported first so
    that a module nothing else imports is counted too."""
    import importlib
    import pkgutil

    import xtal.commands

    for module in pkgutil.iter_modules(xtal.commands.__path__):
        importlib.import_module(f"xtal.commands.{module.name}")
    seen, todo = set(), [StructureOperation]
    while todo:
        for sub in todo.pop().__subclasses__():
            if sub not in seen:
                seen.add(sub)
                todo.append(sub)
    return {c for c in seen if c.__module__.startswith("xtal.")}


def test_every_structure_operation_states_a_map_that_finds_its_atoms(
        rutile, quartz, halite):
    """Every operation that rebuilds the cell, run on rutile, quartz
    and halite: every atom of the result that came from the old cell
    is found from it, and undoing finds every old atom again.  An
    operation that moves the frame without saying how fails here --
    and so does a new one nobody added to the table."""
    cases = _cases(rutile, quartz, halite)
    assert _operations() <= set(cases)
    for kind, runs in cases.items():
        ran = 0
        for k, (structure, command, change) in enumerate(runs):
            added, removed = (change if isinstance(change, tuple)
                              else (change, set()))
            _new, report = command.preview(structure)
            if report is not None and not report.ok:
                continue
            host, stack, before, after = _pushed(structure, command)
            via = command.atom_map()
            name = f"{kind.__name__}, case {k}"
            assert via is not None, name
            found = _followed(before, structure, after, host.structure,
                              range(before.n_atoms), via)
            assert len(found) == after.n_atoms - added, name
            new = host.structure
            stack.undo(host)
            back = tracking.follow(
                p1.expand(host.structure), host.structure.lattice,
                tracking.record(after, found, new.lattice),
                via.inverse())
            assert back == set(range(before.n_atoms)) - removed, name
            ran += 1
        assert ran, f"{kind.__name__} has no case that runs"
