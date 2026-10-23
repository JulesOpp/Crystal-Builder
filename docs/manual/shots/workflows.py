"""The Workflows chapter's screenshots, one function per figure.

Run through the run-app driver with a scratch profile, so every
figure is a first-run window at one size and nothing of the user's is
read or written, in a neutral folder outside the repository
(the Structure panel's file row shows the scratch path)::

    XTAL_NO_CONFIRM_CLOSE=1 python .claude/skills/run-app/drive.py \
        --scratch /tmp/crystal-builder-shots \
        --script docs/manual/shots/workflows.py

Each function writes ``docs/manual/figures/workflows/<name>.png``.
The assistant is the window's own host (``win.agent_host``) driven
from here, so its steps land in the tab exactly as an MCP client's
would.  The server is said to be running rather than started: the
strip shows only while an assistant could connect, and nothing here
needs a port.  The crystal comes from VTK through
``viewport.save_image`` and is pasted into the grabbed chrome, as
``quickstart.py`` does, because a Qt grab cannot see into a GL
surface.  The History menu is raised with ``popup`` (which returns at
once, unlike ``exec``) and grabbed as a widget.  The names below are
the run-app scope: ``win``, ``app``, ``imp``, ``settle``.
"""

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter

ROOT = Path(imp("xtal.__file__")).resolve().parents[1]     # noqa: F821
FIGURES = ROOT / "docs" / "manual" / "figures" / "workflows"

win.resize(1600, 1000)                                      # noqa: F821
settle(400)                                                 # noqa: F821


def _out(name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    return FIGURES / f"{name}.png"


def _save(pixmap, path: Path) -> None:
    if not pixmap.save(str(path)):
        raise OSError(f"could not write {path}")
    print(f"shots: wrote {path.relative_to(ROOT)}")


def _window_with_render(path: Path) -> None:
    """The window's chrome with the VTK render pasted over the
    viewport's own geometry."""
    chrome = win.grab().toImage()                           # noqa: F821
    viewport = win.current_viewport()                       # noqa: F821
    render = FIGURES / "_viewport-render.png"
    viewport.save_image(str(render))
    picture = QImage(str(render))
    render.unlink()
    # The grab carries the screen's device pixel ratio and a painter on
    # it works in logical pixels; save_image magnifies on top of that
    # ratio, so the render is brought to the widget's device size and
    # given the same ratio before it is drawn at the logical corner.
    ratio = chrome.devicePixelRatio()
    corner = viewport.mapTo(win, QPoint(0, 0))              # noqa: F821
    picture = picture.scaled(int(viewport.width() * ratio),
                             int(viewport.height() * ratio),
                             Qt.IgnoreAspectRatio,
                             Qt.SmoothTransformation)
    picture.setDevicePixelRatio(ratio)
    painter = QPainter(chrome)
    painter.drawImage(corner, picture)
    painter.end()
    if not chrome.save(str(path)):
        raise OSError(f"could not write {path}")
    print(f"shots: wrote {path.relative_to(ROOT)} "
          "(chrome grab with the VTK render pasted in)")


def _strip_says():
    strip = win.agent_strip                                 # noqa: F821
    strip.refresh()
    settle(300)                                             # noqa: F821
    print(f"shots: strip says {strip.label.text()!r}, "
          f"button {strip.action_button.text()!r}")
    return strip


def _strip(path: Path) -> None:
    _save(_strip_says().grab(), path)


# ----------------------------------------------------------------------
#  workflows/assistant.md: Taking back what it did
# ----------------------------------------------------------------------

def open_mof5() -> None:
    """MOF-5, once for every figure: opening the sample again raises
    its tab with an *already open* notice over the strip."""
    win.open_sample("mof5")                                 # noqa: F821
    settle(800)                                             # noqa: F821
    win.reset_view()                                        # noqa: F821
    settle(400)                                             # noqa: F821


def assistant_works() -> None:
    """Two requests on MOF-5: one zinc made cobalt, then two oxygens
    put in the cavities -- the strip names the second."""
    session = win.agent_host.current()                      # noqa: F821
    session.checkpoint("One zinc to cobalt")
    assert session.set_element([0], "Co").ok
    session.checkpoint("Two oxygens")
    assert session.add_atom("O", frac=[0.0, 0.0, 0.0]).ok
    assert session.add_atom("O", frac=[0.5, 0.5, 0.5]).ok
    settle(800)                                             # noqa: F821


def agent_strip() -> None:
    """The whole window: the structure, and the strip over it."""
    _strip_says()
    _window_with_render(_out("agent-strip"))


def agent_strip_also() -> None:
    """The person adds an atom of their own: Revert says it takes it."""
    win.current_document().add_atom("Ar", [0.5, 0.0, 0.0])  # noqa: F821
    settle(400)                                             # noqa: F821
    _strip(_out("agent-strip-also"))


def agent_strip_history() -> None:
    """History, with both requests and what reverting each takes."""
    strip = win.agent_strip                                 # noqa: F821
    menu = strip.history_menu()
    button = strip.history_button
    menu.popup(button.mapToGlobal(QPoint(0, button.height())))
    settle(600)                                             # noqa: F821
    print("shots: history lists "
          f"{[a.text() for a in menu.actions() if a.text()]!r}")
    _save(menu.grab(), _out("agent-strip-history"))
    menu.close()


def agent_strip_reverted() -> None:
    """After Revert: what it took, and Restore."""
    strip = win.agent_strip                                 # noqa: F821
    strip.action_button.click()
    settle(400)                                             # noqa: F821
    _strip(_out("agent-strip-reverted"))
    strip.action_button.click()                             # Restore
    settle(400)                                             # noqa: F821


# ----------------------------------------------------------------------
#  workflows/assistant.md: Asking it to change how a tab looks
# ----------------------------------------------------------------------

#: What the assistant is asked for.
RESTYLE = {"style": "polyhedra", "show_rings": True,
           "color_by": "coordination"}


def view_before() -> None:
    """MOF-5 as it opens, before anything is asked."""
    _window_with_render(_out("view-before"))


def view_after() -> None:
    """The same window once the assistant has restyled the tab, then
    put back with the answer's ``was``, so the strip's figures start
    from MOF-5 as it opened (a view change is no undo step to take
    back)."""
    session = win.agent_host.current()                      # noqa: F821
    # The colour key, or the figure's colours say nothing; the prose's
    # example (RESTYLE) stays the three settings it names.
    answer = session.set_view({**RESTYLE, "show_legend": True})
    assert answer.ok, answer.message
    settle(800)                                             # noqa: F821
    print(f"shots: set_view {answer.message!r}, "
          f"was {answer.data['was']!r}")
    _window_with_render(_out("view-after"))
    assert session.set_view(answer.data["was"]).ok
    settle(400)                                             # noqa: F821


server = imp("xtalapp.agent_server.AgentServer")            # noqa: F821
running = server.__dict__["running"]
server.running = property(lambda self: True)
try:
    open_mof5()
    view_before()
    view_after()
    assistant_works()
    agent_strip()
    agent_strip_also()
    agent_strip_history()
    agent_strip_reverted()
finally:
    server.running = running
