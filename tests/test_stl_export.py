"""File > Export as STL, against a stand-in for Blender.

The real Blender takes seconds and is not on a CI machine; what is
tested here is everything on this side of it -- the command line, the
PDB it is handed, the copy to where the user asked, Stop, and the
sentence when the add-on is missing.  ``conftest_program`` is how the
stand-in starts on Windows as well.
"""

import importlib.util
import json
import sys
import threading
import types
from pathlib import Path

import numpy as np
import pytest

from tests.conftest_program import write_program
from xtal.core import cellcut
from xtal.modules import MODULES, Cancellation, Job, blender, process

FAKE = r'''
import json, os, pathlib, sys, time
args = sys.argv[sys.argv.index("--") + 1:]
pathlib.Path("argv.json").write_text(json.dumps(sys.argv[1:]))
mode = os.environ.get("FAKE_BLENDER", "")
if mode == "addon":
    print("[mol2stl] ERROR: could not find/enable the Atomic Blender "
          "PDB add-on.", flush=True)
    sys.exit(2)
if mode == "sleep":
    print("[mol2stl] Importing PDB", flush=True)
    time.sleep(60)
if mode == "crash":
    print("Traceback: something inside Blender", flush=True)
    sys.exit(1)
output = args[args.index("--output") + 1]
pathlib.Path(output).write_bytes(b"solid fake\nendsolid fake\n")
print("[mol2stl] Wrote " + output, flush=True)
'''


@pytest.fixture
def fake_blender(tmp_path, monkeypatch):
    process.clear_hints()
    program = write_program(tmp_path, "blender", FAKE)
    monkeypatch.setenv("XTAL_BLENDER", str(program))
    yield program
    process.clear_hints()


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


def _run(structure, folder, output, **params):
    _module, action = MODULES.find("blender.export-stl")
    values = action.coerce({"output": str(output), **params})
    job = Job(structure=structure, params=values, folder=folder)
    return action.run(job), job


def test_blender_is_given_the_script_and_the_pdb(fake_blender, tmp_path,
                                                halite):
    run = tmp_path / "run"
    result, _job = _run(halite, _Folder(run), tmp_path / "out.stl",
                        stick_radius=0.3, remesh=False)
    assert result.ok, result.detail
    argv = json.loads((run / "argv.json").read_text())
    assert argv[:5] == ["--background", "--factory-startup",
                        "--python-exit-code", "1", "--python"]
    assert Path(argv[5]) == blender.SCRIPT and blender.SCRIPT.is_file()
    after = argv[argv.index("--") + 1:]
    assert after[after.index("--input") + 1] == \
        str(run / blender.INPUT_NAME)
    assert after[after.index("--stick-radius") + 1] == "0.3"
    assert "--no-remesh" in after
    assert (run / blender.INPUT_NAME).read_text().count("HETATM") == 27


def test_the_mesh_is_copied_to_where_it_was_asked_for(fake_blender,
                                                     tmp_path, halite):
    run = tmp_path / "run"
    destination = tmp_path / "prints" / "halite"
    result, _job = _run(halite, _Folder(run), destination)
    assert result.ok, result.detail
    assert (tmp_path / "prints" / "halite.stl").is_file()
    assert (run / blender.OUTPUT_NAME).is_file()        # and kept
    assert "27 atoms" in result.message


def _pdb_positions(path):
    return np.array([[float(line[30:38]), float(line[38:46]),
                      float(line[46:54])]
                     for line in path.read_text().splitlines()
                     if line.startswith(("ATOM", "HETATM"))])


def test_the_pdb_is_centred_off_the_origin(fake_blender, tmp_path,
                                           halite):
    """Atomic Blender divides by the part of an atom's position
    perpendicular to its stick, which is zero when the stick's line
    runs through the origin; centred on its mean, MOF-5's cell cut has
    such lines and Blender stopped with ZeroDivisionError.  The PDB
    arrives centred a generic distance off the origin instead, and the
    atoms keep their places relative to one another."""
    run = tmp_path / "run"
    result, _job = _run(halite, _Folder(run), tmp_path / "out.stl")
    assert result.ok, result.detail
    written = _pdb_positions(run / blender.INPUT_NAME)
    assert np.allclose(written.mean(axis=0), blender.OFF_CENTRE,
                       atol=2e-3)
    cut = cellcut.cut_cell(halite)
    assert np.allclose(written - written[0], cut.cart - cut.cart[0],
                       atol=2e-3)


@pytest.fixture
def stl_scripts(monkeypatch):
    """The wrapper and the vendored script, loaded over a stand-in for
    Blender's ``bpy`` whose PDB importer has every property the
    script might name."""
    names = dict.fromkeys(["use_center", "use_sticks", "ball",
                           "scale_ballradius", "use_camera",
                           "use_light"])
    importer = types.SimpleNamespace(get_rna_type=lambda: types.
                                     SimpleNamespace(properties=names))
    bpy = types.ModuleType("bpy")
    bpy.app = types.SimpleNamespace(background=True)
    bpy.ops = types.SimpleNamespace(
        import_mesh=types.SimpleNamespace(pdb=importer))
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    spec = importlib.util.spec_from_file_location("printable_stl",
                                                  blender.SCRIPT)
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    return wrapper, wrapper.load()


def test_the_vendored_script_is_told_not_to_centre(stl_scripts,
                                                  monkeypatch):
    """The vendored script centres on the mean, which would undo the
    offset the PDB was written at.  The wrapper replaces its
    ``build_import_kwargs`` before its ``main`` runs, so the import
    ``process_one`` makes is the uncentred one."""
    wrapper, script = stl_scripts
    assert blender.VENDORED.is_file()
    assert script.build_import_kwargs(script.CONFIG)["use_center"]

    def main():
        return script.build_import_kwargs(script.CONFIG)
    monkeypatch.setattr(script, "main", main)
    monkeypatch.setattr(wrapper, "load", lambda: script)
    kwargs = wrapper.main()
    assert kwargs["use_center"] is False
    assert kwargs["use_sticks"] is script.CONFIG["use_sticks"]


def test_with_no_workspace_it_still_exports(fake_blender, tmp_path,
                                           halite):
    result, _job = _run(halite, None, tmp_path / "out.stl")
    assert result.ok, result.detail
    assert (tmp_path / "out.stl").is_file()


def test_a_missing_add_on_is_reported_in_the_scripts_words(
        fake_blender, tmp_path, halite, monkeypatch):
    monkeypatch.setenv("FAKE_BLENDER", "addon")
    result, _job = _run(halite, _Folder(tmp_path / "run"),
                        tmp_path / "out.stl")
    assert not result.ok
    assert "Atomic Blender" in result.message
    assert "could not find/enable" in result.detail
    assert not (tmp_path / "out.stl").exists()


def test_a_failure_inside_blender_is_a_failure(fake_blender, tmp_path,
                                              halite, monkeypatch):
    monkeypatch.setenv("FAKE_BLENDER", "crash")
    result, _job = _run(halite, _Folder(tmp_path / "run"),
                        tmp_path / "out.stl")
    assert not result.ok
    assert "status 1" in result.message
    assert "something inside Blender" in result.detail


def test_stop_reaches_blender(fake_blender, tmp_path, halite,
                              monkeypatch):
    monkeypatch.setenv("FAKE_BLENDER", "sleep")
    _module, action = MODULES.find("blender.export-stl")
    cancel = Cancellation()
    job = Job(structure=halite, folder=_Folder(tmp_path / "run"),
              params=action.coerce({"output": str(tmp_path / "o.stl")}),
              cancel=cancel)
    threading.Timer(0.5, cancel.cancel).start()
    result = action.run(job)
    assert result.cancelled
    assert not (tmp_path / "o.stl").exists()


def test_no_destination_is_refused_before_blender_starts(
        fake_blender, tmp_path, halite):
    run = tmp_path / "run"
    _module, action = MODULES.find("blender.export-stl")
    result = action.run(Job(structure=halite, folder=_Folder(run),
                            params=action.defaults()))
    assert not result.ok
    assert not run.exists()


def test_blender_is_found_where_macos_installs_it(tmp_path,
                                                  monkeypatch):
    """An application bundle's binary is on nobody's PATH."""
    process.clear_hints()
    monkeypatch.delenv("XTAL_BLENDER", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    (tmp_path / "Blender.app").mkdir()
    installed = write_program(tmp_path / "Blender.app", "Blender", "")
    program = process.Program(name="blender", known=(str(installed),))
    assert program.locate() == installed
    sources = [source for source, _c, found in program.search()
               if found is not None]
    assert sources == ["known"]


# ------------------------------------------------------ through the app

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

    settings = AppSettings("CrystalBuilderTest", f"Stl{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_file_export_as_stl_runs_with_the_markers_left_to_the_cut(
        window, fake_blender, tmp_path, quartz, qtbot, monkeypatch):
    """The runner hands most modules a structure with its markers
    removed, which renumbers the bonds and throws the perceived graph
    away.  This one reads the bonding, so it is handed the document's
    own -- and the PDB still has no X in it."""
    from xtal.core import bonding
    from xtal.core.site import Site
    from xtalapp.dialogs.stl_export import StlExportDialog

    document = window.new_document()
    marked = quartz.copy()
    bonding.perceive(marked)
    marked.add_sites([Site("X", [0.5, 0.5, 0.5])])
    document.set_structure(marked, modified=False)
    destination = tmp_path / "quartz.stl"
    seen = {}

    def answer(module, action, parent=None, initial=None):
        seen["action"] = action.name
        return action.coerce({"output": str(destination)})
    monkeypatch.setattr(StlExportDialog, "ask", staticmethod(answer))

    assert window.actions_["export_stl"].isEnabled()
    window.actions_["export_stl"].trigger()
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    assert seen["action"] == "export-stl"
    assert destination.is_file()
    written = list(document.entry.path.rglob(blender.INPUT_NAME))
    assert len(written) == 1
    pdb = written[0].read_text()
    assert pdb.count("HETATM") > 0
    assert not any(line[76:78].strip() == "X"
                   for line in pdb.splitlines())


def test_the_dialog_suggests_a_destination_and_asks_where_to_save(
        window, qtbot, halite):
    from PySide6.QtWidgets import QDialogButtonBox

    from xtalapp.dialogs import module_dialog
    module, action = MODULES.find("blender.export-stl")
    document = window.new_document()
    document.set_structure(halite, modified=False)
    dialog = module_dialog(action.dialog)(module, action, window)
    qtbot.addWidget(dialog)

    suggested = Path(dialog.output.text())
    assert suggested.suffix == ".stl"
    assert suggested.parent == Path(window.settings.last_directory)
    assert dialog.output.save
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    assert ok.isEnabled()
    dialog.output.setText("")
    assert not ok.isEnabled()
