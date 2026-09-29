"""File > Render in Blender, against a stand-in for Blender.

Everything on this side of Blender is tested here: the command line,
the centred PDB, the copy to where the user asked, the failures, and
where the camera goes, which is arithmetic that does not need Blender
to check.  The scene itself was checked by hand against Blender 3.4 on
MOF-5; CI has no Blender.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from tests.conftest_program import write_program
from xtal.core import bonding, cellcut
from xtal.modules import MODULES, Job, blender, process

FAKE = r'''
import json, os, pathlib, sys
args = sys.argv[sys.argv.index("--") + 1:]
pathlib.Path("argv.json").write_text(json.dumps(sys.argv[1:]))
mode = os.environ.get("FAKE_BLENDER", "")
if mode == "addon":
    print("[render] ERROR: could not find/enable the Atomic Blender "
          "PDB add-on.", flush=True)
    sys.exit(2)
if mode == "nothing":
    sys.exit(0)
for flag, body in (("--blend", b"BLENDER"), ("--image", b"\x89PNG")):
    pathlib.Path(args[args.index(flag) + 1]).write_bytes(body)
print("[render] Wrote render.png", flush=True)
'''

FOCAL = 40.0
ROTATION = (70.7437, 0.000522, 146.958)


@pytest.fixture
def fake_blender(tmp_path, monkeypatch):
    process.clear_hints()
    program = write_program(tmp_path, "blender", FAKE)
    monkeypatch.setenv("XTAL_BLENDER", str(program))
    yield program
    process.clear_hints()


class _Folder:
    def __init__(self, path):
        self.path = path

    def log(self):
        return None


def _render(structure, folder, output, **params):
    _module, action = MODULES.find("blender.render")
    values = action.coerce({"output": str(output), **params})
    return action.run(Job(structure=structure, params=values,
                          folder=folder))


def test_the_render_command_line_names_the_scene_script_and_the_pdb(
        fake_blender, tmp_path, halite):
    run = tmp_path / "run"
    result = _render(halite, _Folder(run), tmp_path / "out.png",
                     width=640, height=480, samples=7, frame=False)
    assert result.ok, result.detail
    argv = json.loads((run / "argv.json").read_text())
    assert argv[:5] == ["--background", "--factory-startup",
                        "--python-exit-code", "1", "--python"]
    assert Path(argv[5]) == blender.RENDER_SCRIPT
    assert blender.RENDER_SCRIPT.is_file()
    after = argv[argv.index("--") + 1:]

    def value(flag):
        return after[after.index(flag) + 1]
    assert value("--input") == str(run / blender.INPUT_NAME)
    assert value("--blend") == str(run / blender.SCENE_NAME)
    assert value("--image") == str(run / blender.IMAGE_NAME)
    assert (value("--width"), value("--height")) == ("640", "480")
    assert value("--samples") == "7"
    assert value("--viewport-samples") == "10"
    assert "--no-frame" in after
    assert (run / blender.INPUT_NAME).read_text().count("HETATM") == 27


def test_the_picture_is_copied_and_the_scene_kept_in_the_run(
        fake_blender, tmp_path, halite):
    run = tmp_path / "run"
    result = _render(halite, _Folder(run), tmp_path / "pics" / "nacl")
    assert result.ok, result.detail
    assert (tmp_path / "pics" / "nacl.png").is_file()
    assert (run / blender.SCENE_NAME).is_file()
    assert (run / blender.IMAGE_NAME).is_file()
    assert run / blender.SCENE_NAME in result.artifacts


def test_the_pdb_is_centred_off_every_symmetry_line(fake_blender,
                                                   tmp_path, halite):
    """Atomic Blender divides by a stick's distance from the origin,
    so a symmetric cut centred exactly on its mean is a
    ZeroDivisionError inside Blender -- MOF-5's was."""
    run = tmp_path / "run"
    assert _render(halite, _Folder(run), tmp_path / "o.png").ok
    cart = np.array([[float(line[30:38]), float(line[38:46]),
                      float(line[46:54])]
                     for line in (run / blender.INPUT_NAME)
                     .read_text().splitlines()
                     if line.startswith("HETATM")])
    assert np.allclose(cart.mean(axis=0), blender.OFF_CENTRE,
                       atol=2e-3)


def test_a_missing_add_on_fails_in_the_scripts_words(
        fake_blender, tmp_path, halite, monkeypatch):
    monkeypatch.setenv("FAKE_BLENDER", "addon")
    result = _render(halite, _Folder(tmp_path / "run"),
                     tmp_path / "o.png")
    assert not result.ok
    assert "Atomic Blender" in result.message
    assert "could not find/enable" in result.detail
    assert "[render]" not in result.detail


def test_blender_writing_no_picture_is_a_failure(fake_blender, tmp_path,
                                                 halite, monkeypatch):
    monkeypatch.setenv("FAKE_BLENDER", "nothing")
    result = _render(halite, _Folder(tmp_path / "run"),
                     tmp_path / "o.png")
    assert not result.ok
    assert "without writing a picture" in result.message
    assert not (tmp_path / "o.png").exists()


def test_no_destination_is_refused_before_blender_starts(
        fake_blender, tmp_path, halite):
    run = tmp_path / "run"
    _module, action = MODULES.find("blender.render")
    result = action.run(Job(structure=halite, folder=_Folder(run),
                            params=action.defaults()))
    assert not result.ok
    assert not run.exists()


def test_a_missing_blender_greys_render_as_it_greys_stl(monkeypatch):
    """Both are entries of the one Blender module, so the Modules menu
    greys them together and says why."""
    monkeypatch.setattr(blender, "PROGRAM", process.Program(
        name="no-such-blender-here", label="Blender"))
    module = MODULES.get("blender")
    available = module.availability()
    assert not available
    assert "Blender" in available.reason
    assert {action.name for action in module.actions} >= \
        {"export-stl", "render"}


# ---------------------------------------------------------- the camera

def test_a_camera_turned_ninety_degrees_about_x_looks_along_y():
    """Blender's camera looks down its own -Z; the Euler angles are
    applied X first.  A sign wrong here frames the empty space behind
    the camera."""
    looking = blender.framing.forward(
        blender.framing.rotation((90.0, 0.0, 0.0)))
    assert np.allclose(looking, (0.0, 1.0, 0.0), atol=1e-12)
    looking = blender.framing.forward(
        blender.framing.rotation((90.0, 0.0, 90.0)))
    assert np.allclose(looking, (-1.0, 0.0, 0.0), atol=1e-12)


def _mof5_outline(mof5):
    """The corners of a 1.5 A cube about every atom of MOF-5's cell,
    written the way the render writes it."""
    bonding.perceive(mof5)
    cut = blender.centred(cellcut.cut_cell(mof5))
    points = []
    for x, y, z in np.asarray(cut.cart):
        for dx in (-1.5, 1.5):
            for dy in (-1.5, 1.5):
                for dz in (-1.5, 1.5):
                    points.append((x + dx, y + dy, z + dz))
    return points


@pytest.fixture
def mof5():
    from xtal.io.cif_reader import read_cif
    return read_cif(Path("resources/samples/MOF-5.cif"))


@pytest.mark.parametrize("size", [(1920, 1080), (800, 1200)])
def test_an_auto_framed_camera_sees_every_atom(mof5, size):
    framing = blender.framing
    points = _mof5_outline(mof5)
    width, height = size
    camera = framing.frame(points, ROTATION, FOCAL, width, height)
    landed = [framing.project(point, camera, ROTATION, FOCAL, width,
                              height) for point in points]
    assert all(point is not None for point in landed)
    us = [u for u, _v in landed]
    vs = [v for _u, v in landed]
    assert min(us) >= 0.0 and max(us) <= 1.0
    assert min(vs) >= 0.0 and max(vs) <= 1.0
    # And no further back than it has to be: some atom is at the
    # margin, on one axis or the other.
    reach = max(max(abs(u - 0.5) for u in us),
                max(abs(v - 0.5) for v in vs))
    assert reach == pytest.approx(0.5 / (1.0 + framing.MARGIN),
                                  rel=1e-6)
    # It keeps the scene's direction: the camera is where the fixed
    # one is, only nearer, for a cell of MOF-5's size.
    fixed = np.array((42.0251, 64.6089, 26.9517))
    here = np.array(camera)
    cosine = here @ fixed / np.linalg.norm(here) / np.linalg.norm(fixed)
    assert cosine > 0.999
    assert np.linalg.norm(here) < np.linalg.norm(fixed)


def test_the_render_region_holds_every_atom_and_not_the_whole_frame(
        mof5):
    framing = blender.framing
    points = _mof5_outline(mof5)
    camera = framing.frame(points, ROTATION, FOCAL, 1920, 1080)
    left, right, bottom, top = framing.region(points, camera, ROTATION,
                                              FOCAL, 1920, 1080)
    for point in points:
        u, v = framing.project(point, camera, ROTATION, FOCAL, 1920,
                               1080)
        assert left <= u <= right and bottom <= v <= top
    assert (right - left) < 1.0


def test_a_point_behind_the_camera_renders_the_whole_frame():
    framing = blender.framing
    camera = (0.0, -10.0, 0.0)
    region = framing.region([(0.0, -20.0, 0.0), (0.0, 0.0, 0.0)],
                            camera, (90.0, 0.0, 0.0), FOCAL, 640, 480)
    assert region == (0.0, 1.0, 0.0, 1.0)


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

    settings = AppSettings("CrystalBuilderTest", f"Rnd{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_file_render_in_blender_files_the_run_under_the_structure(
        window, fake_blender, tmp_path, quartz, qtbot, monkeypatch):
    from xtalapp.dialogs.stl_export import RenderDialog

    document = window.new_document()
    document.set_structure(quartz, modified=False)
    destination = tmp_path / "quartz.png"

    def answer(module, action, parent=None, initial=None):
        return action.coerce({"output": str(destination)})
    monkeypatch.setattr(RenderDialog, "ask", staticmethod(answer))

    assert window.actions_["render_blender"].isEnabled()
    window.actions_["render_blender"].trigger()
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    assert destination.is_file()
    assert len(list(document.entry.path.rglob(blender.SCENE_NAME))) == 1


def test_the_render_dialog_suggests_a_png_beside_the_last_export(
        window, qtbot, halite):
    from xtalapp.dialogs import module_dialog
    module, action = MODULES.find("blender.render")
    document = window.new_document()
    document.set_structure(halite, modified=False)
    dialog = module_dialog(action.dialog)(module, action, window)
    qtbot.addWidget(dialog)
    suggested = Path(dialog.output.text())
    assert suggested.suffix == ".png"
    assert suggested.parent == Path(window.settings.last_directory)
    assert dialog.windowTitle() == "Render in Blender"
