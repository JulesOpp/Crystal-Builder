"""Add centroid, and the dummy atoms it mostly places.

A centroid is a position somebody wants named -- the centre of a ring,
the vertex of a net -- rather than a piece of chemistry, and a dummy
atom is how that is said.  So it has to be *drawable to*: net edges and
measurements take one like any other atom, and perception takes none of
them, or the ring centre acquires bonds to its own carbons and a
coordination number nobody asked for.

The middle itself is a minimum-image middle.  A ring that straddles the
cell boundary has its centre in the ring, and the average of the
wrapped fractional coordinates is a point in the vacuum.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import bonding, measure, p1

pytest.importorskip("PySide6")

from xtalapp.document import Document  # noqa: E402


@pytest.fixture
def square():
    """Four carbons on a square, centred on (0.5, 0.5, 0.5)."""
    document = Document(Structure.empty(Lattice.cubic(10.0)))
    for x in (0.4, 0.6):
        for y in (0.4, 0.6):
            document.add_atom("C", [x, y, 0.5])
    return document


# ---------------------------------------------------------- the middle

def test_the_centroid_is_the_middle():
    structure = Structure.from_arrays(
        Lattice.cubic(10.0), ["C"] * 3,
        [[0.2, 0.5, 0.5], [0.4, 0.5, 0.5], [0.6, 0.5, 0.5]])
    point = measure.centroid(p1.expand(structure), structure.lattice,
                             [0, 1, 2])
    assert np.allclose(point, [4.0, 5.0, 5.0])


def test_a_group_across_the_boundary_has_its_middle_in_the_group():
    """The average of the wrapped coordinates is in the middle of the
    box, which is a point in the vacuum with nothing to do with the
    atoms it claims to be between."""
    structure = Structure.from_arrays(
        Lattice.cubic(10.0), ["C", "C"],
        [[0.02, 0.5, 0.5], [0.98, 0.5, 0.5]])
    point = measure.centroid(p1.expand(structure), structure.lattice,
                             [0, 1])
    assert point[0] == pytest.approx(0.0, abs=1e-9)


def test_a_centroid_of_nothing_is_refused():
    structure = Structure.from_arrays(Lattice.cubic(10.0), ["C"],
                                      [[0.5, 0.5, 0.5]])
    with pytest.raises(ValueError):
        measure.centroid(p1.expand(structure), structure.lattice, [])


# --------------------------------------------------------- the gesture

def test_a_centroid_lands_in_the_middle_of_the_selection(square):
    square.select([0, 1, 2, 3])
    assert "centroid of 4 atoms" in square.add_centroid()
    placed = square.structure.sites[-1]
    assert placed.element == "X"
    assert np.allclose(placed.frac, [0.5, 0.5, 0.5])


def test_it_can_be_a_real_element_instead(square):
    """Building a bridging atom into the middle of a ring is a
    different act with the same gesture."""
    square.select([0, 1, 2, 3])
    square.add_centroid("C")
    assert square.structure.sites[-1].element == "C"


def test_fewer_than_two_atoms_has_no_middle(square):
    square.select([0])
    assert "at least two" in square.add_centroid()
    assert square.structure.n_sites == 4


def test_the_new_atom_is_left_selected(square):
    """A centroid lands inside the ring it was taken from, where an
    unhighlighted new atom is genuinely hard to find."""
    square.select([0, 1, 2, 3])
    square.add_centroid()
    assert sorted(square.selection.atoms) == [4]


def test_a_centroid_is_one_undo_step(square):
    square.select([0, 1, 2, 3])
    square.add_centroid()
    assert square.undo() == "Add centroid"
    assert square.structure.n_sites == 4


# ------------------------------------------------------- dummy atoms

def test_a_dummy_atom_bonds_to_nothing(square):
    """Even at a distance that would bond anything else: it is not
    chemistry, and a ring centre with a bond to every carbon in the
    ring is the picture this rule exists to prevent.

    Asked for explicitly, because placing an atom no longer perceives
    anything on its own -- which makes recalculating the only way a
    perceived bond to the dummy could appear at all."""
    square.select([0, 1, 2, 3])
    square.add_centroid()               # a dummy at the centre
    square.recompute_bonds()
    dummy = next(i for i, e in enumerate(square.cell.elements)
                 if e == "X")
    assert not square.graph.neighbors(dummy)

    square.select([0, 1, 2, 3])
    square.add_centroid("C")            # the same place, as carbon
    square.recompute_bonds()
    carbon = square.structure.n_sites - 1
    placed = square.cell.indices_of_site(carbon)[0]
    assert square.graph.neighbors(int(placed))


def test_the_rules_refuse_a_dummy_pair():
    rules = bonding.BondRules()
    assert rules.allows("C", "C") is True
    assert rules.allows("C", "X") is False
    assert rules.allows("X", "X") is False


def test_deuterium_is_not_a_dummy():
    """``D`` is hydrogen with a neutron, not a marker."""
    assert bonding.BondRules().allows("D", "O") is True


def test_a_net_edge_can_be_drawn_to_a_dummy(square):
    """What they are mostly for: the vertex of a net is a position, and
    deciding which positions are nodes is the whole point."""
    square.select([0, 1, 2, 3])
    square.add_centroid()
    assert "net edge drawn" in square.add_topology_bond_between(4, 0)
    assert len(bonding.topology_graph(square.structure).bonds) == 1


def test_a_dummy_can_be_measured_to(square):
    square.select([0, 1, 2, 3])
    square.add_centroid()
    text = square.add_measurement([4, 0])
    assert "X1" in text and "A" in text


def test_a_bond_the_user_draws_to_a_dummy_is_still_drawn(square):
    """Perception refusing one is not the same as forbidding one: the
    user drawing a bond is information, and it is kept."""
    square.select([0, 1, 2, 3])
    square.add_centroid()
    assert square.add_bond_between(4, 0) == "bond added"
    assert len(square.graph.bonds) > 0


def test_a_dummy_survives_a_cif_round_trip(square, tmp_path):
    from xtal.io import FORMATS

    square.select([0, 1, 2, 3])
    square.add_centroid()
    path = tmp_path / "centroid.cif"
    FORMATS.write(square.structure, path)
    assert [s.element for s in FORMATS.read(path).sites][-1] == "X"


def test_a_force_field_says_what_is_wrong_rather_than_a_radius(square):
    """The refusal is reachable by an ordinary gesture now -- add a
    centroid, press Optimise -- so it has to name the dummy rather
    than talk about the end of the periodic table."""
    from xtal.ff import ENGINES
    from xtal.ff.uff.typer import TypingError

    square.select([0, 1, 2, 3])
    square.add_centroid()
    with pytest.raises(TypingError, match="dummy atom"):
        ENGINES.build("uff", square.structure)


# ------------------------------------------------- through the window

def test_the_action_needs_more_than_one_atom(qtbot, tmp_path,
                                             rutile_cif):
    """A menu entry that is enabled and then says "select at least two
    atoms" has already wasted the click."""
    pytest.importorskip("pytestqt")
    from tests.test_app_shell import StubViewport
    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    settings = AppSettings("CrystalBuilderTest",
                           f"Centroid{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    window = MainWindow(viewport_factory=StubViewport,
                        settings=settings)
    qtbot.addWidget(window)
    window.open_path(rutile_cif)
    document = window.current_document()

    document.select_none()
    assert not window.actions_["add_centroid"].isEnabled()
    document.select([0])
    assert not window.actions_["add_centroid"].isEnabled()
    document.select([0, 1])
    assert window.actions_["add_centroid"].isEnabled()


def test_the_dialog_offers_a_dummy_first(qtbot):
    """A centroid usually is one, and it is the answer that cannot
    quietly change what the crystal means."""
    pytest.importorskip("pytestqt")
    from xtalapp.dialogs.add_centroid import AddCentroidDialog

    dialog = AddCentroidDialog(4)
    qtbot.addWidget(dialog)
    assert dialog.dummy.isChecked()
    assert not dialog.element.isEnabled()
    assert dialog.result_values()["element"] == "X"

    dialog.real.setChecked(True)
    dialog.element.setCurrentText("N")
    assert dialog.element.isEnabled()
    assert dialog.result_values()["element"] == "N"


def test_the_dialog_refuses_a_word_that_is_not_an_element(qtbot):
    pytest.importorskip("pytestqt")
    from PySide6.QtWidgets import QDialog

    from xtalapp.dialogs.add_centroid import AddCentroidDialog

    dialog = AddCentroidDialog(4)
    qtbot.addWidget(dialog)
    dialog.real.setChecked(True)
    dialog.element.setCurrentText("Kryptonite")
    dialog._accept()
    # Not isVisible(): the dialog itself was never shown, so nothing
    # inside it is on screen either.
    assert not dialog.warning.isHidden()
    assert "not an element symbol" in dialog.warning.text()
    assert dialog.result() != QDialog.Accepted


# ------------------------------------------ dummy atoms and the modules

def test_a_module_is_never_handed_a_dummy_atom(square):
    """A marker has no force-field type and no radius a porosity code
    knows, and one in the cell is enough to fail a Zeo++ run on a
    structure the user considers perfectly ordinary."""
    from xtal.modules.job import without_dummies

    square.select([0, 1, 2, 3])
    square.add_centroid()
    handed, held = without_dummies(square.structure)
    assert [s.element for s in handed.sites] == ["C"] * 4
    assert held is not None


def test_a_structure_with_no_dummies_is_handed_over_untouched(square):
    """Which is every run on every structure anybody has opened."""
    from xtal.modules.job import without_dummies

    handed, held = without_dummies(square.structure)
    assert handed is square.structure
    assert held is None


def test_the_markers_come_back_with_their_bonds(square):
    """Taking a site out renumbers every bond after it, so putting the
    site back is not enough on its own -- a net edge drawn to a dummy
    has to survive the round trip."""
    from xtal.modules.job import restore_dummies, without_dummies

    square.select([0, 1, 2, 3])
    square.add_centroid()
    square.add_topology_bond_between(4, 0)
    edges = len(bonding.topology_graph(square.structure).bonds)

    handed, held = without_dummies(square.structure)
    assert not bonding.topology_graph(handed).bonds
    back, restored = restore_dummies(handed, held)
    assert restored
    assert [s.element for s in back.sites] == ["C"] * 4 + ["X"]
    assert len(bonding.topology_graph(back).bonds) == edges


def test_a_module_that_returns_different_atoms_says_so(square):
    """A supercell, or a framework built from nothing, is not a
    structure the old markers have positions in."""
    from xtal.commands.atoms import new_site
    from xtal.modules.job import restore_dummies, without_dummies

    square.select([0, 1, 2, 3])
    square.add_centroid()
    handed, held = without_dummies(square.structure)
    handed.add_sites([new_site("N", [0.1, 0.1, 0.1])])

    back, restored = restore_dummies(handed, held)
    assert not restored
    assert "X" not in [s.element for s in back.sites]


def test_the_runner_holds_the_dummies_back(qtbot, tmp_path, rutile_cif,
                                           monkeypatch):
    """Through the window, because holding them back at the door is
    the point: a module written next year would have to remember to
    do it itself, and would not."""
    pytest.importorskip("pytestqt")
    from tests.test_app_shell import StubViewport
    from xtalapp import module_runner
    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    monkeypatch.setenv("XTAL_STUB_MODULE", "1")
    from xtal.modules import MODULES
    from xtal.modules import stub as stub_module
    stub_module.register()

    settings = AppSettings("CrystalBuilderTest", f"Dum{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    window = MainWindow(viewport_factory=StubViewport,
                        settings=settings)
    qtbot.addWidget(window)
    window.open_path(rutile_cif)
    document = window.current_document()
    document.select([0, 1])
    document.add_centroid()
    assert "X" in [s.element for s in document.structure.sites]

    handed = []
    real_job = module_runner.Job

    def spy(**kwargs):
        handed.append(kwargs.get("structure"))
        return real_job(**kwargs)

    monkeypatch.setattr(module_runner, "Job", spy)
    monkeypatch.setattr(module_runner, "start_in_thread",
                        lambda worker, parent: None)

    module = MODULES.get("stub")
    action = module.action(next(iter(module)).name)
    window.module_runner._start_module(module, action, {}, document)

    assert handed and handed[0] is not None
    assert "X" not in [s.element for s in handed[0].sites]
    assert window.module_runner._held_dummies is not None
