"""The Essential Elements chapter's screenshots, one function per figure.

Run through the run-app driver with a scratch profile, so every
figure is a first-run window at one size and nothing of the user's is
read or written::

    python .claude/skills/run-app/drive.py --scratch build/manual-shots \
        --script docs/manual/shots/essentials.py

Each function writes ``docs/manual/figures/essentials/<name>.png``.
Dialogs are shown, never exec'd, and closed after the shot; the
context menu is raised with ``popup`` (which returns at once, unlike
``exec``) and grabbed as a widget.  The names below are the run-app
scope: ``win``, ``app``, ``imp``, ``settle``.
"""

from pathlib import Path

from PySide6.QtCore import QPoint

ROOT = Path(imp("xtal.__file__")).resolve().parents[1]     # noqa: F821
FIGURES = ROOT / "docs" / "manual" / "figures" / "essentials"

win.resize(1600, 1000)                                      # noqa: F821
settle(400)                                                 # noqa: F821


def _out(name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    return FIGURES / f"{name}.png"


def _save(pixmap, path: Path) -> None:
    if not pixmap.save(str(path)):
        raise OSError(f"could not write {path}")
    print(f"shots: wrote {path.relative_to(ROOT)}")


def grab_dialog(dialog, path: Path, width=None, height=None) -> None:
    """A dialog shown, never exec'd, and closed after the shot."""
    dialog.show()
    if width:
        dialog.resize(width, height)
    settle(600)                                             # noqa: F821
    _save(dialog.grab(), path)
    dialog.close()


# ----------------------------------------------------------------------
#  essentials/symmetry.md
# ----------------------------------------------------------------------

def find_symmetry() -> None:
    """Symmetry > Find symmetry on MOF-5: P1 as written, Fm-3m found."""
    doc = win.open_sample("mof5")                           # noqa: F821
    settle(800)                                             # noqa: F821
    dialog = imp("xtalapp.dialogs.find_symmetry"            # noqa: F821
                 ".FindSymmetryDialog")(doc, win)           # noqa: F821
    grab_dialog(dialog, _out("find-symmetry"), 560, 520)
    win.close_current()                                     # noqa: F821


def descend_to_subgroup() -> None:
    """Symmetry > Descend to a subgroup on HKUST-1 (Fm-3m)."""
    doc = win.open_sample("hkust1")                         # noqa: F821
    settle(800)                                             # noqa: F821
    dialog = imp("xtalapp.dialogs.subgroup"                 # noqa: F821
                 ".SubgroupDialog")(doc, win)               # noqa: F821
    dialog.show()
    settle(600)                                             # noqa: F821
    # The first row selected, so the split column and the detail
    # underneath say what the descent does.
    dialog.table.setCurrentCell(0, 0)
    grab_dialog(dialog, _out("descend-to-subgroup"), 900, 600)


# ----------------------------------------------------------------------
#  essentials/cell.md
# ----------------------------------------------------------------------

def edit_cell() -> None:
    """Cell > Edit cell on HKUST-1: a cubic group leaves one free."""
    doc = win.current_document()                            # noqa: F821
    dialog = imp("xtalapp.dialogs.cell_edit"                # noqa: F821
                 ".CellEditDialog")(doc.structure, win)     # noqa: F821
    grab_dialog(dialog, _out("edit-cell"))


# ----------------------------------------------------------------------
#  essentials/structure.md
# ----------------------------------------------------------------------

def context_menu_atom() -> None:
    """A right-click on an atom, with two atoms selected."""
    doc = win.current_document()                            # noqa: F821
    doc.select([0, 1], "set")
    settle(200)                                             # noqa: F821
    menu = win.build_context_menu("atom")                   # noqa: F821
    viewport = win.current_viewport()                       # noqa: F821
    where = viewport.mapToGlobal(QPoint(viewport.width() // 2,
                                        viewport.height() // 2))
    menu.popup(where)
    settle(600)                                             # noqa: F821
    _save(menu.grab(), _out("context-menu-atom"))
    menu.close()
    doc.select_none()


find_symmetry()
descend_to_subgroup()
edit_cell()
context_menu_atom()
