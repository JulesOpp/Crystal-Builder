"""File > Export as STL with Two-color printing ticked: the run,
headless, and the one form the window opens for both exports."""

import zipfile

import numpy as np
import pytest

from xtal.core import cellcut, limits, p1
from xtal.core.site import Site
from xtal.io.stl import read_stl
from xtal.modules import MODULES, Job, print3d
from xtal.printing import check


class _Log:
    def __init__(self, path):
        self.path = path
        self.lines = []

    def write(self, text):
        self.lines.append(text)


class _Folder:
    def __init__(self, path):
        self.path = path
        self._log = _Log(path / "run.log")

    def log(self):
        return self._log


def _run(structure, tmp_path, **params):
    folder = tmp_path / "run"
    folder.mkdir(parents=True, exist_ok=True)
    _module, action = MODULES.find("print3d.export")
    values = action.coerce({"output": str(tmp_path / "out" / "model"),
                            "two_color": True, "voxel_size": 0.2,
                            **params})
    job = Job(structure=structure, params=values, folder=_Folder(folder))
    return action.run(job), job


def test_the_export_writes_a_two_part_3mf_and_an_stl_of_each_color(
        tmp_path, halite):
    result, _job = _run(halite, tmp_path, element_colors="Na=2")
    assert result.ok, result.message
    out = tmp_path / "out"
    assert sorted(p.name for p in out.iterdir()) == [
        "model.3mf", "model_color1.stl", "model_color2.stl"]
    with zipfile.ZipFile(out / "model.3mf") as archive:
        assert "Metadata/model_settings.config" in archive.namelist()
    for color in (1, 2):
        report = check.report(*read_stl(out / f"model_color{color}.stl"))
        assert report.ok, report.says()
    assert (tmp_path / "run" / "model.3mf").is_file()


def test_the_two_stls_meet_on_the_same_vertices(tmp_path, halite):
    """What the slicer will check when both are loaded as one object:
    the interface is the same numbers in both files."""
    _run(halite, tmp_path, element_colors="Na=2")
    one, _ = read_stl(tmp_path / "out" / "model_color1.stl")
    two, _ = read_stl(tmp_path / "out" / "model_color2.stl")
    shared = {tuple(v) for v in one} & {tuple(v) for v in two}
    assert len(shared) > 100


def test_an_unassigned_element_is_color_one(halite):
    cut = cellcut.cut_cell(halite)
    colors = print3d.image_colors(cut, {"Na": 2}, {})
    for element, color in zip(cut.elements, colors, strict=True):
        assert color == (2 if element == "Na" else 1)


def test_an_atom_group_choice_overrides_its_elements_color(halite):
    """Color by element, then pick one atom out: every copy of that
    atom in the cut follows it, and no other."""
    cut = cellcut.cut_cell(halite)
    na = [k for k, e in enumerate(p1.expand(halite).elements) if e == "Na"]
    chosen = na[0]
    colors = print3d.image_colors(cut, {"Na": 2}, {chosen: 1})
    for site, element, color in zip(cut.sites, cut.elements, colors,
                                     strict=True):
        if site == chosen:
            assert color == 1
        else:
            assert color == (2 if element == "Na" else 1)


def test_a_badly_written_color_is_refused_before_anything_is_built(
        tmp_path, halite):
    result, _job = _run(halite, tmp_path, element_colors="Na=3")
    assert not result.ok
    assert "NAME=1 or NAME=2" in result.message
    result, _job = _run(halite, tmp_path, element_colors="Qq=2")
    assert not result.ok
    assert not (tmp_path / "out").exists()


def test_a_structure_too_big_for_the_budget_is_meshed_coarser_and_says_so(
        tmp_path, halite):
    result, job = _run(halite, tmp_path, element_colors="Na=2",
                       voxel_size=0.05, max_tris=40000)
    assert result.ok, result.message
    said = "\n".join(job.folder.log().lines)
    assert "coarser than the 0.050 A asked" in said
    assert "0.050 A" not in result.message


def test_a_model_over_the_hard_limit_is_refused_with_a_voxel_that_fits(
        tmp_path, halite):
    result, _job = _run(halite, tmp_path, voxel_size=0.02, max_tris=0)
    assert not result.ok
    assert "fits" in result.message
    assert limits.count(limits.bounds("print")[1]) in result.message


def test_no_destination_is_refused_before_anything_is_built(tmp_path,
                                                           halite):
    result, _job = _run(halite, tmp_path, output="")
    assert not result.ok
    assert "where the 3MF" in result.message


def test_one_color_throughout_writes_one_part_and_says_so(tmp_path,
                                                          halite):
    result, _job = _run(halite, tmp_path, bonds="1")
    assert result.ok, result.message
    assert "nothing is color 2" in result.message
    assert not (tmp_path / "out" / "model_color2.stl").exists()


def test_markers_are_left_out_of_the_print(tmp_path, halite):
    """A centroid placed to measure from is not a ball to print."""
    with_marker = halite.copy()
    with_marker.sites.append(
        Site("X", np.array([0.25, 0.25, 0.25]), label="X1"))
    plain, _ = _run(halite, tmp_path / "a", element_colors="Na=2")
    marked, _ = _run(with_marker, tmp_path / "b", element_colors="Na=2")
    assert plain.ok and marked.ok
    a = read_stl(tmp_path / "a" / "out" / "model_color1.stl")[1]
    b = read_stl(tmp_path / "b" / "out" / "model_color1.stl")[1]
    assert len(a) == len(b)


def test_target_size_scales_the_longest_side_to_millimetres(tmp_path,
                                                            halite):
    _run(halite, tmp_path, element_colors="Na=2", target_size=50.0)
    one, _ = read_stl(tmp_path / "out" / "model_color1.stl")
    two, _ = read_stl(tmp_path / "out" / "model_color2.stl")
    both = np.vstack([one, two])
    assert (both.max(axis=0) - both.min(axis=0)).max() == \
        pytest.approx(50.0, rel=1e-4)


# ---------------------------------------------------------------- window

@pytest.fixture
def window(qtbot, tmp_path):
    pytest.importorskip("pytestqt")
    from PySide6.QtWidgets import QWidget

    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    class _Stub(QWidget):
        def __init__(self, document, parent=None):
            super().__init__(parent)
            self.document = document

    settings = AppSettings("CrystalBuilderTest", f"Print{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _open(window, structure):
    document = window.new_document()
    document.set_structure(structure, modified=False)
    return document


def _dialog(window, qtbot, initial=None, two_color=True):
    from xtalapp.dialogs import module_dialog

    module, action = MODULES.find("print3d.export")
    initial = {"two_color": two_color, **(initial or {})}
    dialog = module_dialog(action.dialog)(module, action, window, initial)
    qtbot.addWidget(dialog)
    return dialog


def _rows(table):
    return [table.item(r, 0).text() for r in range(table.rowCount())]


def test_the_dialog_lists_each_element_present_once_metals_in_color_two(
        window, qtbot, halite):
    """A first export with nothing remembered: the elements of the
    cell, once each, the metal already in color 2."""
    _open(window, halite)
    dialog = _dialog(window, qtbot)
    assert sorted(_rows(dialog.elements)) == ["Cl", "Na"]
    colors = dict(item.split("=") for item in
                   dialog.values()["element_colors"].split())
    assert colors == {"Na": "2", "Cl": "1"}
    assert dialog.group_table is None
    assert dialog.output.text().endswith(".3mf")
    assert dialog.form.widgets["element_colors"].isHidden()


def test_the_dialog_starts_from_the_colors_last_used(window, qtbot,
                                                     halite):
    _open(window, halite)
    dialog = _dialog(window, qtbot, {"element_colors": "Na=1 Cl=2"})
    colors = dict(item.split("=") for item in
                   dialog.values()["element_colors"].split())
    assert colors == {"Na": "1", "Cl": "2"}


def test_a_group_set_to_color_two_reaches_the_run_as_its_atoms(
        window, qtbot, halite):
    """The run never sees groups -- they are view state -- so the form
    hands it their atoms, by P1 index."""
    from xtal.core import atom_groups

    document = _open(window, halite)
    cell = p1.expand(halite)
    chlorine = [k for k, e in enumerate(cell.elements) if e == "Cl"][:2]
    document.atom_groups.append(atom_groups.make(
        cell, halite.lattice, chlorine, "two chlorides"))
    dialog = _dialog(window, qtbot)
    assert _rows(dialog.group_table) == ["two chlorides"]
    assert dialog.values()["atom_colors"] == ""
    dialog.group_table.cellWidget(0, 1).setCurrentIndex(2)
    assert dialog.values()["atom_colors"] == " ".join(
        f"{k}=2" for k in sorted(chlorine))


def _blender(monkeypatch, found):
    from xtal.modules import blender
    from xtal.params import Availability

    monkeypatch.setattr(blender, "available", lambda: Availability(
        found, "" if found else "Blender is not installed"))


def test_the_one_form_shows_only_what_applies_to_one_color_or_two(
        window, qtbot, halite, monkeypatch):
    """Remesh is Blender's alone, the bonds and colors two colors'
    alone; the path follows the box between .stl and .3mf."""
    _blender(monkeypatch, True)
    _open(window, halite)
    dialog = _dialog(window, qtbot, two_color=False)
    hidden = dialog.form.widgets
    assert dialog.output.text().endswith(".stl")
    assert dialog.colors.isHidden() and hidden["bonds"].isHidden()
    assert not hidden["remesh"].isHidden()

    dialog.two_color.setChecked(True)
    assert dialog.output.text().endswith(".3mf")
    assert not dialog.colors.isHidden()
    assert not hidden["bonds"].isHidden()
    assert hidden["remesh"].isHidden()
    assert dialog.values()["two_color"] is True

    dialog.two_color.setChecked(False)
    assert dialog.output.text().endswith(".stl")
    assert dialog.colors.isHidden()


def test_without_blender_the_form_opens_and_runs_only_in_two_colors(
        window, qtbot, halite, monkeypatch):
    """The two-color export needs no Blender, so a missing Blender
    must not keep the form shut -- only Run, until the box is ticked,
    with the reason said."""
    from PySide6.QtWidgets import QDialogButtonBox

    _blender(monkeypatch, False)
    _open(window, halite)
    dialog = _dialog(window, qtbot, two_color=False)
    run = dialog.buttons.button(QDialogButtonBox.Ok)
    assert not run.isEnabled()
    assert not dialog.no_blender.isHidden()
    assert "Blender is not installed" in dialog.no_blender.text()
    dialog.two_color.setChecked(True)
    assert run.isEnabled()
    assert dialog.no_blender.isHidden()


def test_one_color_without_blender_is_refused_saying_two_need_none(
        tmp_path, halite, monkeypatch):
    _blender(monkeypatch, False)
    result, _job = _run(halite, tmp_path, two_color=False)
    assert not result.ok
    assert "Blender is not installed" in result.message
    assert "Two-color printing needs no Blender" in result.message
    assert not (tmp_path / "out").exists()


def test_the_path_takes_the_suffix_of_what_is_made(tmp_path):
    from pathlib import Path

    assert print3d.with_suffix("a/m.stl", True) == Path("a/m.3mf")
    assert print3d.with_suffix("a/m.3mf", False) == Path("a/m.stl")
    assert print3d.with_suffix("a/m.STL", False) == Path("a/m.STL")
    assert print3d.with_suffix("a/m.v2", True) == Path("a/m.v2.3mf")


def test_a_path_naming_an_stl_still_writes_a_3mf_in_two_colors(
        tmp_path, halite):
    result, _job = _run(halite, tmp_path, element_colors="Na=2",
                        output=str(tmp_path / "out" / "model.stl"))
    assert result.ok, result.message
    assert (tmp_path / "out" / "model.3mf").is_file()
    assert not (tmp_path / "out" / "model.stl").exists()


def test_file_export_as_stl_runs_two_colors(window, qtbot, halite,
                                            tmp_path, monkeypatch):
    from xtalapp.dialogs.stl_export import PrintExportDialog

    _open(window, halite)
    destination = tmp_path / "salt.3mf"
    seen = {}

    def answer(module, action, parent=None, initial=None):
        seen["action"] = f"{module.name}.{action.name}"
        return action.coerce({"output": str(destination),
                              "two_color": True,
                              "element_colors": "Na=2",
                              "voxel_size": 0.2})
    monkeypatch.setattr(PrintExportDialog, "ask", staticmethod(answer))

    assert "export_two_color" not in window.actions_
    assert window.actions_["export_stl"].isEnabled()
    window.actions_["export_stl"].trigger()
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=30000)
    assert destination.is_file()
    assert (tmp_path / "salt_color2.stl").is_file()
    assert seen["action"] == "print3d.export"
