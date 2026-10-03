"""
xtalapp.dialogs.stl_export
==========================
Where the STL goes, and how the model is built; and, the same form,
where Render in Blender's picture goes.

The generated form with two things it cannot do: Browse asks where to
*save*, and the path starts filled in -- the structure's own name, in
the folder the last export went to -- because a run that fails a
minute into Blender for want of a destination is a worse way to learn
there was a field than seeing it filled.  Run stays off while the
field is empty for the same reason.

What the form holds is still ``values()``, so the run is exactly the
one the CLI and the Modules tree make.  See
:mod:`xtal.modules.blender`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox

from xtalapp.dialogs.answered import answered
from xtalapp.dialogs.module_form import ModuleDialog


class StlExportDialog(ModuleDialog):

    TITLE = "Export as STL"
    FILTER = "STL meshes (*.stl)"
    SUFFIX = ".stl"

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(module, action, parent, initial)
        self.setWindowTitle(self.TITLE)
        self.output = self.form.widgets["output"]
        self.output.save = True
        self.output.filter = self.FILTER
        if not self.output.text().strip():
            self.output.setText(str(suggested_path(parent, self.SUFFIX)))
        self.form.changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.output.text().strip()))

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        with answered(cls(module, action, parent, initial)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.values()


class RenderDialog(StlExportDialog):

    TITLE = "Render in Blender"
    FILTER = "PNG images (*.png)"
    SUFFIX = ".png"


def suggested_path(window, suffix: str = ".stl") -> Path | str:
    """``<last directory>/<structure name><suffix>``, or nothing to go
    on.

    Read defensively off whatever the dialog was parented to: the
    Modules tree and the File menu both pass the window, a test may
    pass nothing.
    """
    document = None
    if window is not None and hasattr(window, "current_document"):
        document = window.current_document()
    if document is None:
        return ""
    stem = Path(document.title.rstrip("*")).stem or "structure"
    settings = getattr(window, "settings", None)
    folder = Path(getattr(settings, "last_directory", "") or Path.home())
    return folder / f"{stem}{suffix}"
