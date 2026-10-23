"""
xtal.agent.render
=================
A picture of a structure, for an agent to look at.

Numbers come first -- :func:`xtal.agent.inspect.inspect` is what a
judgement rests on -- but some things are seen before they are
counted: a linker folded back on itself, a cluster on the wrong side
of a cell face, a layer that is not flat.  This draws the structure
exactly as the viewport would (the same scene model, the same VTK
scene), with no window and no Qt.

**It always renders in a subprocess**, and the drawing half lives in
:mod:`xtalapp.viewport.snapshot`, because the core imports no GUI
code, not even lazily.  A machine with no OpenGL does
not raise: VTK reaches an access violation in C++ and the interpreter
dies (``tests/conftest.py::offscreen_gl_works`` says the same about
the suite).  An agent's session is worth more than a picture, so the
render gets a process of its own and a crash comes back as
``RENDER_UNAVAILABLE``.  The structure crosses as a project file, so
the bonds drawn are the bonds the session has -- nothing is perceived
on the way.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

from xtal.agent.answers import VerbResult
from xtal.agent.diagnostics import Diagnostic

#: Directions a picture can be taken along, besides a ``[u, v, w]``
#: and a plane ``{"hkl": [h, k, l]}``.
VIEWS = ("diagonal", "a", "b", "c")


def as_view(view):
    """``view`` checked and in the one spelling both renderers read.

    A name from :data:`VIEWS`, a plane ``{"hkl": [h, k, l]}`` -- its
    normal, which outside an orthogonal cell is not the direction
    [hkl] -- with integer indices, or a lattice direction ``[u, v,
    w]`` as floats.  Refused here, before a subprocess or the window's
    camera is touched: a misspelt key must not come out as some other
    picture.
    """
    if isinstance(view, str):
        if view in VIEWS:
            return view
    elif isinstance(view, dict):
        hkl = view.get("hkl") if set(view) == {"hkl"} else None
        if (isinstance(hkl, (list, tuple)) and len(hkl) == 3
                and all(float(h).is_integer() for h in hkl)):
            if not any(hkl):
                raise ValueError("(0 0 0) is not a plane")
            return {"hkl": [int(h) for h in hkl]}
    else:
        return [float(x) for x in view]
    raise ValueError(f"view is one of {', '.join(VIEWS)}, a lattice "
                     f"direction [u, v, w] or a plane "
                     f"{{'hkl': [h, k, l]}} of integers, not {view!r}")

#: Longest a render may take before it is abandoned.  Software GL
#: draws MFU-4l's 648 atoms in about five seconds.
TIMEOUT = 180

#: Why the ``xtal`` a packaged build carries does not render headless.
FROZEN = "connect the window to render (Help ▸ Connect an AI assistant)"


def render(structure, path, view="diagonal", size=(800, 600),
           style: str | None = None, highlight=(),
           show_cell: bool | None = None,
           view_settings: dict | None = None) -> VerbResult:
    """Draw ``structure`` to a PNG at ``path``.

    ``view`` is ``"diagonal"`` (the viewport's opening view), ``"a"``,
    ``"b"`` or ``"c"`` (looking down that axis), a lattice direction
    ``[u, v, w]``, or ``{"hkl": [h, k, l]}`` (looking straight onto
    that plane, along its normal).  ``highlight`` names P1 atoms to
    draw selected, which is how to see where the atoms a diagnostic
    names actually are.  ``view_settings`` is how it is drawn --
    style, rings, colour by, display ranges -- as a project's view
    holds them; ``style`` and ``show_cell``, given, win over its own
    for this picture, and ``None`` is the view's (the record's default
    where it has none).
    """
    from xtal.io.project import write_project

    path = Path(path)
    if path.suffix.lower() != ".png":
        raise ValueError(f"render writes a .png, not {path.name}")
    args = {"view": as_view(view),
            "size": [int(size[0]), int(size[1])], "style": style,
            "highlight": [int(a) for a in highlight],
            "show_cell": None if show_cell is None else bool(show_cell)}
    if getattr(sys, "frozen", False):
        # A packaged `xtal` is a program and not an interpreter: there
        # is no `-m` to run the snapshot module with.  The window has a
        # viewport, and draws for a connected assistant itself.
        return _unavailable(args, FROZEN)
    if find_spec("vtkmodules") is None:
        from xtal.install import command as install_command
        return _unavailable(args, f"rendering needs the gui extra: "
                                  f"{install_command('gui')}")
    with tempfile.TemporaryDirectory() as scratch:
        project = write_project(structure,
                                Path(scratch) / "render.xtalproj",
                                view=view_settings)
        command = [sys.executable, "-m", "xtalapp.viewport.snapshot",
                   str(project), str(path.resolve()), repr(args)]
        try:
            finished = subprocess.run(command, capture_output=True,
                                      text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return _unavailable(args, f"the render took longer than "
                                      f"{TIMEOUT} s and was abandoned")
    if finished.returncode != 0 or not path.exists():
        said = (finished.stderr or "").strip().splitlines()
        reason = next((line for line in reversed(said)
                       if "Error" in line), "")
        return _unavailable(
            args, "no OpenGL context could be made here (the renderer "
                  f"exited with status {finished.returncode})"
                  + (f": {reason}" if reason else ""))
    return VerbResult("render", True, f"wrote {path}",
                      data={"path": str(path), **args})


def _unavailable(args, reason) -> VerbResult:
    return VerbResult("render", False, reason, data=dict(args),
                      diagnostics=[Diagnostic("RENDER_UNAVAILABLE",
                                              reason)])
