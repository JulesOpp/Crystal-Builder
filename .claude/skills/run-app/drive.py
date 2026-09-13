"""Launch the real Crystal Builder window and drive it from a script.

The suite has 1400+ tests and none of them can tell you that a button
does nothing when a person presses it: the widget tests inject a stub
in place of the VTK viewport and call methods directly.  This builds
the window the ``crystal-builder`` entry point builds -- real viewport,
real plugins, real actions -- performs a list of steps in the order
given, and writes PNGs, so "it works" can be looked at.

Steps run in command-line order, so

    --open a.cif --action recalc_bonds --shot after.png

means what it reads as.  Every step prints a line to stdout; a step
that raises stops the run with a non-zero exit rather than leaving a
window open with nobody watching.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

# Before anything imports VTK's Qt bridge: VTK picks its binding from
# QT_API and getting it wrong is an import-time crash.
os.environ.setdefault("QT_API", "pyside6")
# Nothing here can answer a modal.  Without this, tearing the window
# down with unsaved edits raises the quit prompt and the run hangs
# until something kills it.
os.environ.setdefault("XTAL_NO_CONFIRM_CLOSE", "1")

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Step(argparse.Action):
    """Collect options into one ordered list instead of separate ones."""

    def __call__(self, parser, namespace, values, option_string=None):
        namespace.steps.append((self.dest, values))


def _parse(argv):
    p = argparse.ArgumentParser(
        prog="drive.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.set_defaults(steps=[])
    p.add_argument("--open", action=_Step, metavar="PATH",
                   help="open a structure file in a new tab")
    p.add_argument("--action", action=_Step, metavar="NAME",
                   help="trigger a registered action by name "
                        "(see --list-actions)")
    p.add_argument("--eval", action=_Step, metavar="CODE",
                   help="exec Python with win, doc, app, tabs in scope")
    p.add_argument("--script", action=_Step, metavar="PATH",
                   help="exec a Python file in the same scope as "
                        "--eval; for a probe too long for a shell "
                        "argument")
    p.add_argument("--shot", action=_Step, metavar="PATH",
                   help="PNG of the whole window (menus, docks, tabs)")
    p.add_argument("--viewport-shot", action=_Step, metavar="PATH",
                   help="PNG of the 3D view via VTK, which the window "
                        "grab cannot capture")
    p.add_argument("--grab", action=_Step, nargs="+",
                   metavar="EXPR PATH [WxH]",
                   help="PNG of one dock or dialog: EXPR is a dock's "
                        "attribute name (style_dock) or a Python "
                        "expression for a widget, in the --eval scope. "
                        "A dock is floated for the shot and put back; "
                        "a dialog is shown modelessly and closed")
    p.add_argument("--settle", action=_Step, metavar="MS", type=int,
                   help="pump the event loop for this many milliseconds")
    p.add_argument("--list-actions", action=_Step, nargs=0,
                   help="print every action name and its menu text")
    p.add_argument("--list-docks", action=_Step, nargs=0,
                   help="print every dock's attribute name and title")
    p.add_argument("--scratch", metavar="DIR",
                   help="preferences and the default workspace in DIR "
                        "instead of the real ones: a clean first-run "
                        "window, and nothing recorded in the user's "
                        "recent files, layout or last workspace")
    p.add_argument("--keep", action="store_true",
                   help="hand the running window to the user instead of "
                        "quitting (blocks; dialogs are left working)")
    p.add_argument("--allow-dialogs", action="store_true",
                   help="do not turn a modal into an error -- only with "
                        "somebody at the keyboard")
    return p.parse_args(argv)


def _refuse_modals():
    """Turn a modal dialog into a failure instead of a hung run.

    Same bargain as ``tests/conftest.py``: a dialog blocks until
    somebody clicks and nobody will, so reaching one has to say so
    rather than wait.  Patch the classmethod above the dialog (e.g.
    ``ModuleDialog.ask``) in an --eval step if a step needs one.
    """
    from PySide6.QtWidgets import QDialog, QMessageBox

    def refuse(self, *a, **k):
        raise AssertionError(
            f"{type(self).__name__}.exec() would wait for a click. "
            "Patch it in an --eval step, or pass --allow-dialogs and "
            "answer it yourself.")

    QDialog.exec = refuse
    for name in ("question", "warning", "information", "critical", "about"):
        def refuse_static(*a, _name=name, **k):
            raise AssertionError(
                f"QMessageBox.{_name}() would wait for a click. "
                "Patch it in an --eval step.")
        setattr(QMessageBox, name, staticmethod(refuse_static))


def _settle(app, ms=250):
    """Let Qt and VTK catch up.

    Not politeness: on macOS the render window must be realised and
    its events processed before VTK initialises it, and a screenshot
    taken before that is of a window that has not drawn yet.
    """
    from PySide6.QtCore import QDeadlineTimer, QEventLoop
    deadline = QDeadlineTimer(ms)
    while not deadline.hasExpired():
        app.processEvents(QEventLoop.AllEvents, 20)


def main(argv=None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    for step, value in args.steps:
        if step == "grab" and len(value) not in (2, 3):
            raise SystemExit("--grab takes EXPR PATH and an optional WxH")

    if args.scratch:
        # Before xtalapp is imported: AppSettings reads the variable
        # when it opens its store, and the workspace root is asked for
        # when the window is built.  The same two the suite sets.
        scratch = Path(args.scratch).resolve()
        (scratch / "settings").mkdir(parents=True, exist_ok=True)
        os.environ["XTAL_SETTINGS_DIR"] = str(scratch / "settings")
        os.environ["XTAL_WORKSPACE_ROOT"] = str(scratch / "workspace")

    from PySide6.QtWidgets import QApplication

    from xtal import plugins
    from xtalapp.mainwindow import APP_NAME, MainWindow

    if not args.allow_dialogs and not args.keep:
        _refuse_modals()

    report = plugins.load()
    for name, message in report.failures:
        print(f"warning: plugin {name} failed to load: {message}",
              file=sys.stderr)

    from xtalapp.application import keep_siblings_non_native

    keep_siblings_non_native()          # as the shipped app does
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("CrystalBuilder")

    win = MainWindow()
    win.show()
    _settle(app, 600)          # realise the window before VTK is asked

    try:
        for step, value in args.steps:
            _run(step, value, win, app)
    except Exception:
        traceback.print_exc()
        print("FAILED", file=sys.stderr)
        return 1

    if args.keep:
        print("window is yours -- close it to finish")
        return app.exec()

    win.close()
    return 0


def _run(step, value, win, app) -> None:
    if step == "open":
        path = Path(value).resolve()
        win.open_path(path)
        _settle(app, 400)
        doc = win.current_document()
        n = len(doc.structure.sites) if doc else 0
        print(f"opened {path.name}: {n} sites, "
              f"{win.tabs.count()} tab(s)")

    elif step == "action":
        if value not in win.actions_:
            raise SystemExit(
                f"no action named {value!r}; --list-actions to see them")
        action = win.actions_[value]
        if not action.isEnabled():
            raise SystemExit(
                f"action {value!r} ({action.text()}) is disabled -- "
                "nothing would happen if a user clicked it")
        action.trigger()
        _settle(app, 400)
        print(f"triggered {value!r} ({action.text()})")

    elif step in ("eval", "script"):
        scope = _scope(win, app)
        if step == "script":
            path = Path(value).resolve()
            code = compile(path.read_text(), str(path), "exec")
            exec(code, scope)
            _settle(app, 250)
            print(f"ran {path.name}")
        else:
            exec(value, scope)
            _settle(app, 250)
            print(f"eval ok: {value}")

    elif step == "shot":
        path = Path(value).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        _settle(app, 300)
        if not win.grab().save(str(path)):
            raise SystemExit(f"could not write {path}")
        print(f"wrote {path}  (window chrome; 3D view will be blank -- "
              f"use --viewport-shot for that)")

    elif step == "viewport_shot":
        path = Path(value).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        viewport = win.current_viewport()
        if viewport is None or not hasattr(viewport, "save_image"):
            raise SystemExit(
                "no 3D viewport in the current tab -- open a structure "
                "first")
        _settle(app, 300)
        viewport.save_image(str(path))
        print(f"wrote {path}  (3D view)")

    elif step == "grab":
        _grab(win, app, *value)

    elif step == "settle":
        _settle(app, value)
        print(f"settled {value} ms")

    elif step == "list_actions":
        for name in sorted(win.actions_.names()):
            action = win.actions_[name]
            state = "" if action.isEnabled() else "   [disabled]"
            print(f"  {name:<28} {action.text()}{state}")

    elif step == "list_docks":
        for dock in win.docks:
            name = next(n for n, v in vars(win).items() if v is dock)
            state = "shown" if dock.isVisible() else "hidden"
            print(f"  {name:<18} {dock.windowTitle():<14} {state}")


def _scope(win, app) -> dict:
    """What --eval, --script and --grab can name."""
    import importlib

    def imp(dotted):
        """``imp("xtalapp.dialogs.preferences.PreferencesDialog")``."""
        module, _, attr = dotted.rpartition(".")
        return getattr(importlib.import_module(module), attr)

    return {"win": win, "app": app, "tabs": win.tabs,
            "doc": win.current_document(),
            "viewport": win.current_viewport(),
            "settle": lambda ms=250: _settle(app, ms),
            "imp": imp}


def _grab(win, app, expr, path, size=None) -> None:
    """One widget to a PNG, left as it was found.

    A dock tabbed behind another is not drawn, and one squeezed into
    the right-hand column is drawn at the column's width, so it is
    floated at the requested size for the shot and docked again.  A
    dialog built by the expression is shown without ``exec`` -- which
    would wait for a click -- and closed afterwards.
    """
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QDockWidget

    widget = getattr(win, expr, None) if expr.isidentifier() else None
    if widget is None:
        widget = eval(expr, _scope(win, app))
    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    width, height = (int(n) for n in size.lower().split("x")) \
        if size else (None, None)

    if isinstance(widget, QDockWidget):
        floating, visible = widget.isFloating(), widget.isVisible()
        widget.setFloating(True)
        widget.show()
        widget.raise_()
        # On the window's own screen: a floating dock restored from a
        # layout saved on another monitor lands off every screen.
        widget.move(win.geometry().topLeft() + QPoint(60, 60))
        if width:
            widget.resize(width, height)
        _settle(app, 400)
        ok = widget.grab().save(str(out))
        widget.setFloating(floating)
        widget.setVisible(visible)
    else:
        opened = not widget.isVisible()
        if opened:
            widget.show()
        if width:
            widget.resize(width, height)
        _settle(app, 400)
        ok = widget.grab().save(str(out))
        if opened:
            widget.close()
    if not ok:
        raise SystemExit(f"could not write {out}")
    print(f"wrote {out}  ({type(widget).__name__})")


if __name__ == "__main__":
    raise SystemExit(main())
