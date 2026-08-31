"""Right-clicking, and deleting whatever is in hand.

Every editing action used to be reachable only from the menu bar at the
top of the screen, a long way from the atom being edited.  These tests
cover the two halves of fixing that: what a right click selects before
it opens a menu, and what the menu is allowed to say it will do.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Menu{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def opened(window, rutile_cif):
    return window, window.open_path(rutile_cif)


def entries(window, kind):
    """The text of every entry in a context menu, without showing it."""
    menu = window.build_context_menu(kind)
    return [] if menu is None else [a.text() for a in menu.actions()]


# ------------------------------------------------------------- menus

def test_an_atom_menu_offers_the_atom_actions(opened):
    _window, document = opened
    document.select([0])
    texts = entries(_window, "atom")
    assert any("element" in t for t in texts)
    assert any("Delete" in t for t in texts)
    assert any("fragment" in t for t in texts)


def test_a_bond_menu_offers_deleting_the_bond(opened):
    window, document = opened
    document.select_bond(document.graph.bonds[0].key())
    assert any("bond" in t.lower() for t in entries(window, "bond"))


def test_a_bond_menu_offers_setting_the_bond_type(opened):
    """Right-clicking a bond is where an order gets corrected: the
    menu bar is a long way from the bond in question."""
    window, document = opened
    document.select_bond(document.graph.bonds[0].key())

    menu = window.build_context_menu("bond")
    submenus = [a.menu() for a in menu.actions() if a.menu() is not None]
    assert len(submenus) == 1
    assert [a.text().replace("&", "") for a in submenus[0].actions()] == [
        "Single", "Double", "Triple", "Aromatic", "Automatic"]


def test_the_bond_types_are_off_until_a_bond_is_selected(opened):
    window, document = opened
    assert not window.actions_["bond_type_double"].isEnabled()
    document.select_bond(document.graph.bonds[0].key())
    assert window.actions_["bond_type_double"].isEnabled()


def test_the_ticked_type_is_what_the_bond_already_is(opened):
    """A bond nobody has stated an order for is Automatic, even when
    the inference made it double."""
    window, document = opened
    document.select_bond(document.graph.bonds[0].key())
    assert window.actions_["bond_type_automatic"].isChecked()

    window.actions_["bond_type_double"].trigger()

    assert window.actions_["bond_type_double"].isChecked()
    assert not window.actions_["bond_type_automatic"].isChecked()
    assert document.selected_bond_type() == "Double"


def test_setting_a_bond_type_is_undoable(opened):
    window, document = opened
    document.select_bond(document.graph.bonds[0].key())
    window.actions_["bond_type_triple"].trigger()
    assert any(b.stated for b in document.structure.bonds)

    document.undo()

    assert not any(b.stated for b in document.structure.bonds)


def test_the_same_command_is_in_the_menu_bar(opened):
    """The context menu and the menu bar hold the same actions, so
    there is one place a bond type can be set from and two ways to
    reach it -- and enabling it in one enables it in the other."""
    window, document = opened
    in_the_bar = window.bond_type_menu.actions()
    assert window.actions_["bond_type_single"] in in_the_bar

    menu = window.build_context_menu("bond")
    in_the_click = [a.menu() for a in menu.actions()
                    if a.menu() is not None][0].actions()
    assert in_the_click == in_the_bar

    assert not window.actions_["bond_type_single"].isEnabled()
    document.select_bond(document.graph.bonds[0].key())
    assert window.actions_["bond_type_single"].isEnabled()


def test_the_empty_space_menu_is_about_the_view(opened):
    window, _document = opened
    texts = entries(window, "view")
    assert any("range" in t.lower() for t in texts)
    assert any("Style" in t for t in texts)


def test_an_unknown_target_offers_nothing(opened):
    window, _document = opened
    assert window.build_context_menu("nothing at all") is None


def test_the_menu_says_how_many_it_will_delete(opened):
    """"Delete" and "Delete 6 atoms" are different promises."""
    window, document = opened
    document.select_all()
    count = len(document.selection.atoms)
    assert count > 1
    assert any(f"Delete {count} atoms" == t
               for t in entries(window, "atom"))


def test_the_menu_bar_gets_its_own_wording_back(opened):
    """The context menu shares its actions with the menu bar, so a
    label written for one click must not outlive it."""
    window, document = opened
    before = window.actions_["delete_selection"].text()
    document.select_all()
    entries(window, "atom")
    assert window.actions_["delete_selection"].text() == before


def test_a_counted_entry_still_runs_the_real_action(opened):
    window, document = opened
    document.select_all()
    sites = document.structure.n_sites

    menu = window.build_context_menu("atom")
    counted = [a for a in menu.actions() if "atoms" in a.text()][0]
    counted.trigger()

    assert document.structure.n_sites < sites


# ------------------------------------------------ what a click selects

class FakeModel:
    """Stands in for a SceneModel: says what the ray hit."""

    def __init__(self, atom=0, bond=None):
        self._atom = atom
        self._bond = bond

    def instance(self, index):
        return self._atom, (0, 0, 0)

    def bond_key(self, index):
        return self._bond


class FakeViewport:
    """Just enough of ViewportWidget for select_under to run."""

    def __init__(self, document, model):
        self.document = document
        self.model = model

    def _ray_at(self, point):
        return (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)


def select_under(document, model, hit, monkeypatch):
    from xtalapp.viewport import picking
    from xtalapp.viewport.widget import ViewportWidget
    monkeypatch.setattr(picking, "pick",
                        lambda *a, **k: hit)
    return ViewportWidget.select_under(
        FakeViewport(document, model), None)


def test_right_clicking_outside_the_selection_selects_first(
        opened, monkeypatch):
    """A menu that acts on a selection nobody can see is how a context
    menu deletes the wrong thing."""
    _window, document = opened
    document.select([0])

    kind = select_under(document, FakeModel(atom=1), ("atom", 0),
                        monkeypatch)

    assert kind == "atom"
    assert document.selection.atoms == {1}


def test_right_clicking_inside_the_selection_keeps_it(opened,
                                                      monkeypatch):
    """Which is what makes "delete these fourteen atoms" reachable."""
    _window, document = opened
    document.select_all()
    chosen = set(document.selection.atoms)

    select_under(document, FakeModel(atom=next(iter(chosen))),
                 ("atom", 0), monkeypatch)

    assert document.selection.atoms == chosen


def test_right_clicking_a_bond_selects_the_bond(opened, monkeypatch):
    _window, document = opened
    key = document.graph.bonds[0].key()

    kind = select_under(document, FakeModel(bond=key), ("bond", 0),
                        monkeypatch)

    assert kind == "bond"
    assert document.selection.bonds == {key}


def test_right_clicking_nothing_is_the_view_menu(opened, monkeypatch):
    _window, document = opened
    kind = select_under(document, FakeModel(), (None, -1), monkeypatch)
    assert kind == "view"


# ---------------------------------------------------- deleting a bond

def test_deleting_a_selected_bond(rutile_cif):
    document = Document.load(rutile_cif)
    before = len(document.graph.bonds)
    document.select_bond(document.graph.bonds[0].key())

    message = document.delete_selected_bonds()

    assert len(document.graph.bonds) < before
    assert "removed" in message
    assert not document.selection.bonds


def test_deleting_a_bond_reports_the_whole_orbit(rutile_cif):
    """Suppressing one bond suppresses every bond symmetry says is the
    same bond, and the count has to say so."""
    document = Document.load(rutile_cif)
    before = len(document.graph.bonds)
    document.select_bond(document.graph.bonds[0].key())
    document.delete_selected_bonds()
    assert before - len(document.graph.bonds) > 1


def test_deleting_a_bond_is_one_undo_step(rutile_cif):
    document = Document.load(rutile_cif)
    before = len(document.graph.bonds)
    for bond in document.graph.bonds[:2]:
        document.select_bond(bond.key(), "add")

    document.delete_selected_bonds()
    document.undo()

    assert len(document.graph.bonds) == before


def test_delete_with_bonds_selected_deletes_the_bonds(opened):
    """One key, whichever thing is in hand."""
    window, document = opened
    sites = document.structure.n_sites
    bonds = len(document.graph.bonds)
    document.select_bond(document.graph.bonds[0].key())

    window.delete_selection()

    assert document.structure.n_sites == sites     # no atom went
    assert len(document.graph.bonds) < bonds


def test_nothing_selected_deletes_nothing(opened):
    window, document = opened
    document.select_none()
    window.delete_selection()
    assert document.stack.depth == 0
