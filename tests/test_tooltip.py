"""Hovering an atom, and what it is told to say.

Everything the application knows about an atom used to have to be gone
and looked for: its label in the Sites dock, its type in the Force
Field dock, its displacement parameters nowhere at all.  These cover
the half the window owns -- which atom is under the cursor, and which
of those facts the current view has earned.  The wording itself is
headless and is covered in ``test_describe.py``.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.structure import Structure  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.viewport import modes  # noqa: E402
from xtalapp.viewport.builder import build_scene  # noqa: E402
from xtalapp.viewport.widget import ViewportWidget  # noqa: E402


@pytest.fixture
def two_atoms():
    """A carbon and an oxygen, far enough apart to hover one at a
    time."""
    document = Document(Structure.empty(Lattice.cubic(20.0)))
    document.add_atom("C", [0.4, 0.5, 0.5])
    document.add_atom("O", [0.6, 0.5, 0.5])
    return document


class Hovering:
    """Enough of ViewportWidget to run its own hover against.

    Its ``_update_tooltip`` and ``_describe`` are the shipped ones --
    a stub with simpler versions of the two methods under test would
    pass while the real pair was broken.
    """

    def __init__(self, document, ray):
        self.document = document
        self.model = build_scene(document.structure, document.view)
        self.mode = modes.get("select")
        self.show_types = False
        self._tooltip_atom = None
        self._ray = ray
        self.tooltips: list = []

    def _ray_at(self, point):
        return self._ray

    def setToolTip(self, text):
        self.tooltips.append(text)

    def hover(self):
        ViewportWidget._update_tooltip(self, *self._ray)
        return self.tooltips[-1] if self.tooltips else None

    def _describe(self, atom):
        return ViewportWidget._describe(self, atom)


def ray_through(document, atom):
    target = np.asarray(document.cell.cart[atom], dtype=float)
    return (tuple(target + [0.0, 0.0, -10.0]), (0.0, 0.0, 1.0))


def test_hovering_an_atom_says_what_it_is(two_atoms):
    view = Hovering(two_atoms, ray_through(two_atoms, 0))
    assert "carbon" in view.hover()


def test_moving_off_an_atom_takes_the_tooltip_with_it(two_atoms):
    """One left over from the last atom would claim the cursor is
    somewhere it is not."""
    view = Hovering(two_atoms, ray_through(two_atoms, 0))
    assert "carbon" in view.hover()

    view._ray = ((0.0, 9.0, -10.0), (0.0, 0.0, 1.0))
    assert view.hover() == ""


def test_empty_space_that_was_always_empty_is_not_a_redraw(two_atoms):
    """Every mouse move across the background arrives here, and there
    is nothing to say each time."""
    view = Hovering(two_atoms, ((0.0, 9.0, -10.0), (0.0, 0.0, 1.0)))
    view.hover()
    view.hover()
    assert view.tooltips == []


def test_the_same_atom_twice_is_not_recomputed(two_atoms):
    """A mouse crossing a framework arrives here a hundred times over
    the same atom, and the text is the same every time."""
    view = Hovering(two_atoms, ray_through(two_atoms, 0))
    view.hover()
    view.hover()
    view.hover()
    assert len(view.tooltips) == 1


def test_moving_to_another_atom_says_the_other_atom(two_atoms):
    view = Hovering(two_atoms, ray_through(two_atoms, 0))
    assert "carbon" in view.hover()
    view._ray = ray_through(two_atoms, 1)
    assert "oxygen" in view.hover()


def test_the_uff_type_arrives_with_the_force_field_dock(two_atoms):
    """The type is part of what the view is about only while somebody
    is looking at the force field."""
    view = Hovering(two_atoms, ray_through(two_atoms, 0))
    assert "UFF" not in view.hover()

    view.show_types = True
    view._tooltip_atom = None
    assert "UFF" in view.hover()


def test_a_structure_the_typer_will_not_touch_still_hovers(two_atoms):
    """A label and an element are worth saying about an atom no force
    field has an opinion on -- the tooltip is not the place to raise
    the exception."""
    two_atoms.add_atom("Es", [0.5, 0.2, 0.5])       # no UFF parameters
    view = Hovering(two_atoms, ray_through(two_atoms, 0))
    view.show_types = True
    assert "carbon" in view.hover()


def test_a_marker_says_the_force_field_is_not_looking_at_it(two_atoms):
    """A dummy atom is a marker, not chemistry.  The tooltip inherits
    that from the typer rather than deciding it again."""
    two_atoms.add_atom("X", [0.5, 0.3, 0.5])
    view = Hovering(two_atoms, ray_through(two_atoms, 2))
    view.show_types = True
    assert "marker" in view.hover()


def test_the_ellipsoids_bring_their_own_numbers(two_atoms):
    """U_eq is what an ORTEP picture is of, and is noise beside a ball
    and stick."""
    two_atoms.structure.sites[0].u_iso = 0.02
    view = Hovering(two_atoms, ray_through(two_atoms, 0))
    assert "U_eq" not in view.hover()

    two_atoms.view.style = "ortep"
    view._tooltip_atom = None
    assert "U_eq" in view.hover()
