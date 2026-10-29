"""The fullerene builder as a module, and its form:
xtal.modules.fullerene and xtalapp.dialogs.fullerene_build."""

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from xtal.core import bonding
from xtal.modules import MODULES, Job

C60 = "1 7 9 11 13 15 18 20 22 24 26 32"

#: C50-D5h, the last of C50's 271 isomers.
C50 = "1 2 9 10 12 14 15 17 20 22 24 26"


def _run(**changes):
    _module, action = MODULES.find("fullerene.build")
    return action.run(Job(params=action.coerce(changes)))


def _rows(result):
    return {row.label: row for row in result.report.tables[0].rows}


def test_the_fullerene_builder_needs_no_structure():
    """A builder: in the Build group, asking for no open structure,
    returning one with its bonds stated, and a report of what was
    built."""
    module, action = MODULES.find("fullerene.build")
    assert module.group == "build"
    assert action.needs_structure is False
    assert action.kind == "build"
    result = _run()
    assert result.ok, result.message
    structure = result.structure
    assert structure.perceived is not None
    assert len(bonding.graph(structure).bonds) == len(
        structure.perceived.bonds) == 90
    assert [t.title for t in result.report.tables] == ["What was built"]


def test_the_defaults_build_buckminsterfullerene():
    """No parameters given is C60-Ih: the report names the cage, its
    group of 120 and its isolated pentagons."""
    result = _run()
    assert result.message.startswith("C60-Ih: 60 atoms")
    rows = _rows(result)
    assert rows["Cage"].value == "C60-Ih"
    assert rows["Point group"].value == "Ih"
    assert "order 120" in rows["Point group"].note
    assert rows["Isolated pentagons"].value == "yes"
    assert rows["Spiral"].value == C60


def test_an_isomer_is_picked_by_its_number():
    """C76's IPR isomer 2 is the Td one, not the default D2."""
    assert _rows(_run(n=76))["Cage"].value == "C76-D2"
    assert _rows(_run(n=76, isomer=2))["Cage"].value == "C76-Td"


def test_a_refusal_is_a_failed_run_naming_why():
    """Two elements, an isomer the size does not have, and a size the
    table does not hold with no spiral: each a failed run whose
    message says why, never an exception."""
    for changes, why in [({"element": "B N"}, "odd rings"),
                         ({"n": 76, "isomer": 3}, "isomers 1 to 2"),
                         ({"n": 50}, "spiral can be typed")]:
        result = _run(**changes)
        assert not result.ok
        assert why in result.message


def test_a_typed_spiral_builds_a_size_the_table_does_not_hold():
    """C50 has 271 isomers and none is in the table; its D5h one, the
    last, is built from its spiral."""
    result = _run(n=50, spiral=C50,
                  relax="none")
    assert result.ok, result.message
    assert len(result.structure.sites) == 50
    assert _rows(result)["Isomer"].value.startswith("typed spiral")


def test_xtal_run_fullerene_build_writes_a_structure_and_a_report(
        tmp_path, capsys):
    """``xtal run fullerene.build`` files the cage as an entry of its
    own, as the window does, and prints the report."""
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "fullerene.build", "-p", "n=70",
                 "--workspace", str(workspace)]) == 0
    out = capsys.readouterr().out
    assert "What was built" in out
    assert "C70-D5h" in out
    cifs = [p for p in workspace.rglob("*.cif")
            if ".autosave" not in p.parts]
    assert len(cifs) == 1


def test_an_assistant_builds_a_cage_through_session_build(tmp_path):
    """The MCP's way in to a builder: Session.build files the cage and
    hands back a session on it."""
    from xtal.agent.session import Session

    session = Session.build("fullerene.build", tmp_path / "ws",
                            n=60, hydrogenate=True)
    assert session.built.ok
    assert session.n_atoms == 120


# -- the form ---------------------------------------------------------

@pytest.fixture
def dialog(qtbot):
    from xtalapp.dialogs import module_dialog

    module = MODULES.get("fullerene")
    made = module_dialog("fullerene-build")(module,
                                            module.action("build"))
    qtbot.addWidget(made)
    return made


def _widget(dialog, name):
    for form in dialog.forms.values():
        if name in form.widgets:
            return form.widgets[name]
    raise KeyError(name)


def test_every_parameter_is_on_the_form_and_comes_back(dialog):
    """The groups and the isomer list hold everything the module
    declares, and the values come back in the module's own types."""
    from xtalapp.dialogs.fullerene_build import GROUPS

    on_form = [n for _title, names in GROUPS for n in names] + ["isomer"]
    declared = [p.name for p in MODULES.get("fullerene").action(
        "build").params]
    assert sorted(on_form) == sorted(declared)
    values = dialog.values()
    assert values["n"] == 60 and values["isomer"] == 0
    assert "C60-Ih" in dialog.readout.text()


def test_the_isomer_list_follows_the_size(dialog):
    """C40 lists its default and all forty isomers; choosing one is
    what values() hands back, and the readout names it."""
    _widget(dialog, "n").setValue(40)
    assert dialog.isomer.count() == 41
    assert dialog.isomer.itemText(0) == "Default: C40-Td"
    dialog.isomer.setCurrentIndex(dialog.isomer.findData(39))
    assert dialog.values()["isomer"] == 39
    assert "C40-D5d" in dialog.readout.text()


def test_a_size_the_table_lacks_asks_for_a_spiral(dialog):
    """C50 is in no row: Build greys until a spiral is typed, and a
    typed spiral greys the isomer list."""
    build = dialog.buttons.button(QDialogButtonBox.Ok)
    _widget(dialog, "n").setValue(50)
    assert not build.isEnabled()
    assert "spiral" in dialog.isomer.itemText(0)
    _widget(dialog, "spiral").setText("1 2 9 10 12 14 15 17 20 22 24 26")
    assert build.isEnabled()
    assert not dialog.isomer.isEnabled()


def test_a_spiral_that_does_not_close_greys_build_saying_so(dialog):
    build = dialog.buttons.button(QDialogButtonBox.Ok)
    _widget(dialog, "spiral").setText("1 2 3 4 5 6 7 8 9 10 11 32")
    assert not build.isEnabled()
    assert "does not close" in dialog.readout.text()


def test_a_cage_uff_cannot_type_fails_with_a_sentence(monkeypatch):
    """A typing error past the recipe's own check is a failed run with
    the typer's reason, never a traceback."""
    from xtal.ff.uff.typer import TypingError
    from xtal.fullerene import build as cage

    def refuse(*_args, **_kwargs):
        raise TypingError("UFF has no parameters for Qq")

    monkeypatch.setattr(cage, "_relax", refuse)
    result = _run(n=20)
    assert not result.ok
    assert "UFF has no parameters for Qq" in result.message
