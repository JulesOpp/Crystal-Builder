"""The agent's picture: drawn in a subprocess, so a missing GL is a
diagnostic and not a dead interpreter.

Marked ``gui`` by hand: nothing here imports Qt, but it needs VTK, the
same extra the window needs.
"""

import importlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tests.conftest import needs_offscreen_gl
from xtal.agent.render import render

# The module and not the function the package exports under its name.
render_module = importlib.import_module("xtal.agent.render")

pytestmark = pytest.mark.gui

pytest.importorskip("vtkmodules")


@needs_offscreen_gl
@pytest.mark.slow
def test_render_writes_a_png_without_importing_pyside(tmp_path, rutile):
    """If the render path ever pulls in Qt, a headless agent box without
    the window's libraries can no longer draw anything."""
    from xtal.io.project import write_project

    project = write_project(rutile, tmp_path / "r.xtalproj")
    out = tmp_path / "r.png"
    probe = (
        "import sys\n"
        "from xtalapp.viewport.snapshot import draw\n"
        f"draw({str(project)!r}, {str(out)!r}, dict(view='c', "
        "size=[200, 150], style='ball_stick', highlight=[0], "
        "show_cell=True))\n"
        "assert 'PySide6' not in sys.modules, 'Qt was imported'\n")
    finished = subprocess.run([sys.executable, "-c", probe],
                              capture_output=True, text=True,
                              timeout=180)
    assert finished.returncode == 0, finished.stderr
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@needs_offscreen_gl
@pytest.mark.slow
def test_a_session_render_looks_down_the_axis_it_was_given(tmp_path,
                                                           rutile):
    from xtal.agent.session import Session

    answer = Session(rutile).render(tmp_path / "a.png", view="a",
                                    size=(160, 120))
    assert answer.ok, answer
    assert Path(answer.data["path"]).exists()
    assert answer.data["view"] == "a"


def test_a_renderer_that_dies_is_a_diagnostic_not_a_crash(
        tmp_path, rutile, monkeypatch):
    """The failure on a machine with no GL is a segfault in C++; the
    session must survive it and say so by code."""
    def dies(*args, **kwargs):
        return subprocess.CompletedProcess(args, -11, "",
                                           "Segmentation fault")

    monkeypatch.setattr(render_module.subprocess, "run", dies)
    answer = render(rutile, tmp_path / "x.png")
    assert not answer.ok
    assert answer.diagnostics[0].code == "RENDER_UNAVAILABLE"


def test_a_view_that_is_not_one_is_refused_before_anything_runs(
        tmp_path, rutile):
    with pytest.raises(ValueError):
        render(rutile, tmp_path / "x.png", view="sideways")
    with pytest.raises(ValueError):
        render(rutile, tmp_path / "x.jpg")


def test_a_frozen_launcher_says_to_connect_the_window_rather_than_render(
        tmp_path, rutile, monkeypatch):
    """A packaged ``xtal`` has no ``-m`` to run the snapshot module
    with; the window draws instead, so the answer names how to reach
    it rather than a renderer that died."""
    def never(*args, **kwargs):
        raise AssertionError("a frozen build started a renderer")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(render_module.subprocess, "run", never)
    answer = render(rutile, tmp_path / "x.png")
    assert not answer.ok
    assert answer.diagnostics[0].code == "RENDER_UNAVAILABLE"
    assert answer.message == ("connect the window to render "
                              "(Help ▸ Connect an AI assistant)")


def test_a_render_takes_a_plane_as_its_view(tmp_path, rutile,
                                            monkeypatch):
    """``{"hkl": [h, k, l]}`` reaches the subprocess as a plane, with
    its indices as integers -- a float there would be a direction."""
    seen = []

    def runs(command, **kwargs):
        seen.append(command[-1])
        return subprocess.CompletedProcess(command, -11, "", "")

    monkeypatch.setattr(render_module.subprocess, "run", runs)
    answer = render(rutile, tmp_path / "x.png", view={"hkl": [1, 1.0, 0]})
    assert answer.data["view"] == {"hkl": [1, 1, 0]}
    assert "{'hkl': [1, 1, 0]}" in seen[0]


def test_a_plane_that_is_not_one_is_refused_before_anything_runs(
        tmp_path, rutile, monkeypatch):
    """(0 0 0) has no normal, a fractional index is no plane, and a
    misspelt key is not quietly a diagonal view."""
    def never(*args, **kwargs):
        raise AssertionError("a renderer was started")

    monkeypatch.setattr(render_module.subprocess, "run", never)
    for view in ({"hkl": [0, 0, 0]}, {"hkl": [1, 0.5, 0]},
                 {"hkl": [1, 0]}, {"uvw": [1, 0, 0]}):
        with pytest.raises(ValueError):
            render(rutile, tmp_path / "x.png", view=view)


def test_the_snapshot_looks_onto_a_plane_as_it_looks_down_an_axis(
        halite, quartz):
    """Same end of the line as its own view "a": (100) of a cubic cell
    is that view, and in quartz it is a*, not a."""
    snapshot = pytest.importorskip("xtalapp.viewport.snapshot")

    def unit(v):
        return v / np.linalg.norm(v)

    plane = snapshot._direction(halite.lattice, {"hkl": [1, 0, 0]})
    axis = snapshot._direction(halite.lattice, "a")
    assert unit(plane) == pytest.approx(unit(axis))
    a_star = quartz.lattice.reciprocal().matrix[0]
    assert unit(snapshot._direction(quartz.lattice, {"hkl": [1, 0, 0]})) \
        == pytest.approx(-unit(a_star))
