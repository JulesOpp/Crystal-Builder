"""The same atoms found again after an edit renumbers the cell.

Headless: ``xtal.core.tracking`` is what keeps View > Show Only
Selected's hidden set on its atoms; the window's half is in
``test_show_only.py``.
"""

from xtal.commands import CommandStack, Host
from xtal.commands.atoms import DeleteSites
from xtal.core import p1, symmetry, tracking


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
