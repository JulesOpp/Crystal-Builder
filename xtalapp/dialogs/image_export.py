"""
xtalapp.dialogs.image_export
============================
One dialog for writing a picture of the view.

``Export Image`` was a native save dialog with a hard-coded PNG filter
and a hard-coded 2x magnification, which is three decisions taken on
the user's behalf and none of them announced.  This is the same shape
as :mod:`xtalapp.dialogs.export` -- a format picker that swaps the
suffix on a path, a *Browse...* button, and ``target()`` plus
``options()`` handed back to the caller -- and it says the two things
that cannot be guessed.

**What "resolution" means here.**  Not a magnification.  On a Retina
screen the render window is already twice the widget's logical size
(the reason :meth:`xtalapp.viewport.widget.ViewportWidget._display_at`
exists), so "2x" is 4x the pixels somebody thought they asked for.
The dialog multiplies it out and shows the pixel size that will
actually be written.

**What each format costs.**  ``ExportDialog`` has ``keeps_text``
under its picker for the same reason.  The line matters most for the
two ends of the list: JPEG throws away the sharp edges that a
ball-and-stick picture is almost entirely made of, and SVG has no
resolution to set because it is shapes rather than pixels.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

#: ``(label, suffix, filter, note)`` for each format the viewport can
#: write.  The note is the counterpart of ``ExportDialog``'s
#: ``keeps_text``: what this format costs, said before the file is
#: written rather than found afterwards.  SVG is last because it is
#: the odd one -- the two options above it are both meaningless for
#: it, and its note is the longest, which is what sizes the row.
FORMATS = (
    ("PNG image", ".png", "PNG image (*.png)",
     "Lossless, and the only raster format here that keeps a "
     "transparent background at a sensible size."),
    ("JPEG image", ".jpg", "JPEG image (*.jpg *.jpeg)",
     "Lossy, and with no alpha channel -- small files, and soft "
     "edges anywhere the colour changes sharply."),
    ("TIFF image", ".tif", "TIFF image (*.tif *.tiff)",
     "Uncompressed and transparency-capable: what a journal usually "
     "asks for, at roughly ten times a PNG."),
    ("SVG (vector)", ".svg", "SVG image (*.svg)",
     "One named, separately editable shape per atom, bond and cell "
     "edge.  Resolution-independent, so there is no size to set."),
)

#: What each format can carry, which is what greys the boxes out.
#: JPEG has no alpha channel.  SVG has no resolution at all -- it is
#: shapes, and "how many pixels" is a question its reader answers.
SUPPORTS_ALPHA = {".png", ".tif", ".svg"}
SUPPORTS_SCALE = {".png", ".jpg", ".tif"}

NOTES = {suffix: note for _label, suffix, _filter, note in FORMATS}
FILTERS = {suffix: filt for _label, suffix, filt, _note in FORMATS}


class ImageExportDialog(QDialog):
    """Pick a format, a size, and where the picture goes."""

    def __init__(self, parent=None, directory=None, stem="view",
                 size=(800, 600)):
        super().__init__(parent)
        self.setWindowTitle("Export Image")
        self._base = (max(int(size[0]), 1), max(int(size[1]), 1))

        self.format = QComboBox()
        for label, suffix, _filter, _note in FORMATS:
            self.format.addItem(f"{label} (*{suffix})", suffix)
        self.format.currentIndexChanged.connect(self._on_format)

        # Sized for the longest note from the start: a word-wrapped
        # label grown after the dialog is on screen is laid out at the
        # old height and its last line is cut off.
        self.note = QLabel(max(NOTES.values(), key=len))
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: palette(mid);")
        self.note.setMinimumWidth(320)
        self.note.setMinimumHeight(
            self.note.heightForWidth(self.note.minimumWidth()))

        self.scale = QSpinBox()
        self.scale.setRange(1, 8)
        self.scale.setValue(2)
        self.scale.setSuffix("x")
        self.scale.valueChanged.connect(self._on_scale)
        self.pixels = QLabel()
        self.pixels.setStyleSheet("color: palette(mid);")
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.scale)
        scale_row.addWidget(self.pixels, 1)

        self.transparent = QCheckBox("Transparent background")
        self.transparent.setToolTip(
            "Write the background as transparent rather than as the "
            "view's colour, so the picture drops onto any slide")

        self.path = QLineEdit()
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.choose_path)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path, 1)
        path_row.addWidget(browse)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Export")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Format", self.format)
        form.addRow("", self.note)
        form.addRow("Resolution", scale_row)
        form.addRow("File", path_row)

        body = QVBoxLayout()
        body.addLayout(form)
        body.addWidget(self.transparent)
        body.addWidget(self.buttons)
        self.setLayout(body)

        self._directory = Path(directory or Path.home())
        self._stem = stem or "view"
        self.path.setText(str(self._suggested()))
        self._on_format()

    # -- state ---------------------------------------------------------

    def suffix(self) -> str:
        return self.format.currentData()

    def _suggested(self) -> Path:
        return self._directory / f"{self._stem}{self.suffix()}"

    def output_size(self) -> tuple[int, int]:
        """The pixels this export will actually write.

        The render window's size times the magnification.  For SVG it
        is the size of the canvas the shapes are laid out on, which
        the reader is free to ignore -- see :meth:`_on_scale`.
        """
        if self.suffix() not in SUPPORTS_SCALE:
            return self._base
        scale = self.scale.value()
        return (self._base[0] * scale, self._base[1] * scale)

    def _on_format(self) -> None:
        suffix = self.suffix()
        self.note.setText(NOTES[suffix])
        self.transparent.setEnabled(suffix in SUPPORTS_ALPHA)
        self.scale.setEnabled(suffix in SUPPORTS_SCALE)
        self._on_scale()
        text = self.path.text().strip()
        if text:
            self.path.setText(str(Path(text).with_suffix(suffix)))

    def _on_scale(self) -> None:
        width, height = self.output_size()
        if self.suffix() not in SUPPORTS_SCALE:
            self.pixels.setText(
                f"{width} x {height} canvas, scales to any size")
            return
        self.pixels.setText(f"{width} x {height} pixels")

    def choose_path(self) -> None:
        suffix = self.suffix()
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Export Image",
            self.path.text() or str(self._suggested()),
            FILTERS[suffix])
        if chosen:
            self.path.setText(str(Path(chosen).with_suffix(suffix)))

    def target(self) -> Path | None:
        text = self.path.text().strip()
        return Path(text) if text else None

    def options(self) -> dict:
        """What to pass to
        :meth:`xtalapp.viewport.widget.ViewportWidget.save_image`."""
        return {
            "magnification": (self.scale.value()
                              if self.scale.isEnabled() else 1),
            "transparent": (self.transparent.isChecked()
                            and self.transparent.isEnabled()),
        }

    def accept(self) -> None:                       # pragma: no cover
        if self.target() is None:
            return
        super().accept()
