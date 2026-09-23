"""
xtalapp.dialogs.pattern
=======================
A diffraction pattern with pan, zoom, an overlay and a vector export.

The results dock draws a calculated pattern with ``QPainter``
(:mod:`xtalapp.curve`) and that is the right thing for a panel: it
costs nothing, it follows the theme, and it works on a machine with
four packages installed.  What it cannot do is the two things a
pattern is actually *used* for -- putting a measured file on top of
the calculation and reading off which peak moved, and writing a figure
somebody can open in Illustrator.  Both want axes that zoom, and
neither is worth a second hand-written plotting library.

**So matplotlib comes in, and it comes in as an extra.**  ``pip
install 'crystal-builder[pxrd]'``, checked with ``find_spec`` and
never an import, the pattern ``build``, ``sketch`` and ``ase`` already
follow: the button in the results panel greys out naming the extra and
the calculated pattern is still drawn without it.  This reverses
[docs/PLAN.md](../../docs/PLAN.md) § 2's "no plotting library", which
had already named the case that would reverse it -- "PXRD overlays
with pan, zoom and picking is a real reason to reconsider".

**Every trace is scaled to its own maximum.**  A calculated pattern is
in electrons squared and a measured one is in counts; on one absolute
axis one of them is a flat line along the bottom.  The axis is
labelled as a percentage for that reason, which is what a published
overlay does.

**The measured file is not resampled onto the calculated grid.**  It
is drawn on its own x, because a measured pattern's step is the
instrument's and interpolating it onto somebody else's grid invents
intensity between the points that were actually counted.  What that
costs is that the two traces cannot be subtracted here, and
subtracting them is refinement rather than comparison.

**Editable text is the whole of the vector export.**  ``svg.fonttype:
"none"`` emits ``<text>`` rather than outlined paths and
``pdf.fonttype: 42`` embeds TrueType rather than Type 3, and without
the pair the axis labels arrive in the vector editor as unselectable
shapes -- which is the one thing somebody exporting a vector figure
wanted.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from xtal.io.xy import read_xy, write_xy
from xtalapp.widgets.tone import HINT, set_tone

MISSING = ("matplotlib is not installed, so a pattern can be looked "
           "at in the panel but not zoomed, overlaid or exported as "
           "a figure -- pip install 'crystal-builder[pxrd]'")

#: Keeping text as text rather than as outlines is what makes a label
#: editable after the file is opened in a vector editor.  Applied
#: through ``rc_context`` at the moment of writing, so nothing else
#: drawn in this process is affected.
EDITABLE_TEXT = {
    "svg.fonttype": "none",         # emit <text>, not <path>
    "pdf.fonttype": 42,             # embed TrueType, not Type 3
    "ps.fonttype": 42,
}

VECTOR_SUFFIXES = (".pdf", ".svg", ".eps")

#: Offered in the save dialog; the chosen suffix picks the writer.
FIGURE_FILTERS = ";;".join((
    "PDF, vector and editable (*.pdf)",
    "SVG, vector and editable (*.svg)",
    "EPS, vector (*.eps)",
    "PNG, raster (*.png)",
    "TIFF, raster (*.tif)",
))

RASTER_DPI = 300

#: Filters for a two-column file that is not a diffraction pattern.
DATA_FILTER = "Two-column data (*.xy *.dat *.txt);;All files (*)"

#: Where the tick combs are drawn, in percent of the tallest peak.
#: Below the traces rather than over them, one row per set: the rows
#: are what tell an unexpected peak sitting over a *forbidden*
#: position apart from one sitting over nothing.
COMB_TOP = -2.0
COMB_ROW = 5.0

#: The colours the combs are drawn in, in the order the sets arrive:
#: allowed, then forbidden.  Matched to :data:`xtalapp.curve.TICK_COLORS`
#: so the panel and this window are the same picture.
COMB_COLORS = ("0.45", "#c65252", "#7896be")


def installed() -> bool:
    """Whether matplotlib is importable -- without importing it."""
    try:
        return importlib.util.find_spec("matplotlib") is not None
    except (ImportError, ValueError):               # pragma: no cover
        return False


def _figure_canvas():
    """The Qt canvas, its toolbar and the pyplot-free Figure class.

    Imported here rather than at module scope so that this module can
    be imported -- and :func:`installed` asked -- on a machine with no
    matplotlib.  ``QtAgg`` reads ``QT_API``, which
    :mod:`xtalapp.application` already sets to ``pyside6`` for VTK's
    sake, so the backend binds to the same Qt this window is built in
    rather than importing a second one.
    """
    from matplotlib.backends.backend_qtagg import (
        FigureCanvasQTAgg,
        NavigationToolbar2QT,
    )
    from matplotlib.figure import Figure

    return FigureCanvasQTAgg, NavigationToolbar2QT, Figure


class PatternDialog(QDialog):
    """One :class:`xtal.modules.report.Curve`, plotted properly.

    Built from a report block rather than from a
    :class:`~xtal.analysis.pxrd.Simulation` on purpose: the panel that
    opens it holds a report and knows no module, so a window that
    wanted the simulation would have made the panel know about PXRD.
    """

    def __init__(self, curve, parent=None, directory: str = ""):
        super().__init__(parent)
        self.setWindowTitle(curve.title or "Pattern")
        self.curve = curve
        # A scan's profile arrives here too, and every word below that
        # says "pattern" or "2-theta" is wrong for it -- the axis is a
        # volume or a distance, and the traces are not scaled.
        self.pattern = bool(curve.normalised)
        self.directory = str(directory or "")
        #: What has been laid over the calculation: ``(label, x, y)``.
        self.overlays: list[tuple[str, np.ndarray, np.ndarray]] = []

        canvas_class, toolbar_class, figure_class = _figure_canvas()
        self.figure = figure_class(figsize=(7.0, 4.2))
        self.axes = self.figure.add_subplot(111)
        self.canvas = canvas_class(self.figure)
        self.canvas.setMinimumSize(560, 320)
        # So that clicking the plot takes the focus off a range box
        # and the box applies what was typed into it.
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.toolbar = toolbar_class(self.canvas, self)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        set_tone(self.status, HINT)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.overlay_button = buttons.addButton(
            "Overlay data...", QDialogButtonBox.ActionRole)
        self.overlay_button.setToolTip(
            "Read a measured pattern from a two-column .xy file and "
            "draw it over the calculation" if self.pattern else
            "Read a two-column file and draw it over this curve")
        self.overlay_button.clicked.connect(self.add_overlay)
        self.figure_button = buttons.addButton(
            "Save figure...", QDialogButtonBox.ActionRole)
        self.figure_button.setToolTip(
            "PDF, SVG or EPS keeps the text editable in a vector "
            "editor; PNG and TIFF are raster")
        self.figure_button.clicked.connect(self.save_figure)
        self.data_button = buttons.addButton(
            "Save pattern..." if self.pattern else "Save data...",
            QDialogButtonBox.ActionRole)
        self.data_button.setToolTip(
            "Write the calculated pattern as a two-column .xy file"
            if self.pattern else
            "Write this curve as a two-column .xy file")
        self.data_button.clicked.connect(self.save_pattern)
        buttons.rejected.connect(self.reject)

        units = "degrees" if self.pattern else _units(curve.x_label)
        within = f", in {units}" if units else ""
        self.low = _range_entry(
            f"The left-hand end of the axis{within}")
        self.high = _range_entry(
            f"The right-hand end of the axis{within}")
        for entry in (self.low, self.high):
            entry.editingFinished.connect(self._on_range)
            entry.returnPressed.connect(self._on_range)

        top = QHBoxLayout()
        top.addWidget(self.toolbar, 1)
        top.addWidget(QLabel(
            "2-theta" if self.pattern
            else _quantity(curve.x_label) or "x"))
        top.addWidget(self.low)
        top.addWidget(QLabel("to"))
        top.addWidget(self.high)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.status)
        layout.addWidget(buttons)

        self.replot()
        self._show_range()

    # -- drawing -------------------------------------------------------

    def replot(self) -> None:
        """Redraw from scratch.

        From scratch rather than by adding a line, because the zoom
        the user set is worth keeping and everything else is cheap:
        the limits are read back and restored, so overlaying a file
        does not throw away the region they had zoomed into.
        """
        had_limits = bool(self.axes.lines)
        limits = (self.axes.get_xlim(), self.axes.get_ylim())
        self.axes.clear()
        curve = self.curve

        x = np.asarray(curve.x, dtype=float)
        for label, values in curve.all_series():
            values = np.asarray(values, dtype=float)
            if len(values) != len(x):               # pragma: no cover
                continue
            self.axes.plot(x, self._scaled(values), lw=1.2,
                           label=label,
                           marker="" if self.pattern else "o",
                           markersize=3)
        for label, other_x, other_y in self.overlays:
            self.axes.plot(other_x, self._scaled(other_y), lw=1.0,
                           label=label)

        self._draw_ticks()
        if self.pattern:
            self.axes.set_xlabel(curve.x_label
                                 or r"2$\theta$ (degrees)")
            self.axes.set_ylabel("intensity (% of maximum)")
        else:
            self.axes.set_xlabel(curve.x_label or "x")
            self.axes.set_ylabel(curve.y_label or "y")
        if curve.title:
            self.axes.set_title(curve.title)
        self.axes.legend(loc="upper right", frameon=False, fontsize=9)
        self.axes.margins(x=0.01)
        self.figure.tight_layout()
        if had_limits:
            self.axes.set_xlim(*limits[0])
            self.axes.set_ylim(*limits[1])
        self.canvas.draw_idle()
        self.status.setText(self._sentence())
        if hasattr(self, "low"):
            self._show_range()

    def _scaled(self, values) -> np.ndarray:
        """A pattern's trace in percent; anything else as it is."""
        return _percent(values) if self.pattern \
            else np.asarray(values, dtype=float)

    def _draw_ticks(self) -> None:
        """The reflection positions, as combs below the traces.

        Below zero rather than on the curve: a reflection's height on
        this axis would be a second intensity scale, and where it is
        is the only thing a comb is for.  One row per set, each in its
        own colour, so an unexpected peak can be read against the
        allowed positions and the forbidden ones at once.
        """
        rows = [(label, np.asarray(positions, dtype=float))
                for label, positions in self.curve.tick_sets]
        rows = [(label, positions) for label, positions in rows
                if positions.size]
        if not rows:
            return
        for index, (label, positions) in enumerate(rows):
            top = COMB_TOP - index * COMB_ROW
            self.axes.vlines(
                positions, top - COMB_ROW + 1.0, top,
                colors=COMB_COLORS[index % len(COMB_COLORS)],
                linewidths=0.8, label=label)
        self.axes.set_ylim(COMB_TOP - len(rows) * COMB_ROW - 2.0,
                           105.0)

    def _sentence(self) -> str:
        if not self.pattern:
            return (self.curve.note if not self.overlays else
                    f"{len(self.overlays)} file(s) overlaid, on the "
                    f"same scale as the curve.")
        if not self.overlays:
            return (self.curve.note or
                    "Overlay a measured .xy file to compare it with "
                    "this calculation.")
        return (f"{len(self.overlays)} measured pattern(s) overlaid.  "
                "Each trace is scaled to its own maximum, so the "
                "heights are comparable and the counts are not.")

    # -- the axis range ------------------------------------------------

    def _show_range(self) -> None:
        """Put the axis's own limits into the boxes.

        So the two entries always say what is on screen, including
        after a zoom with the toolbar -- boxes that only ever
        *accepted* a range would disagree with the picture the moment
        anybody used the magnifier beside them.
        """
        low, high = self.axes.get_xlim()
        for entry, value in ((self.low, low), (self.high, high)):
            blocked = entry.blockSignals(True)
            entry.setText(f"{value:g}")
            entry.blockSignals(blocked)

    def limits(self) -> tuple[float, float]:
        """The full extent of everything plotted, along x.

        The calculation and every measurement laid over it, because a
        measured pattern can run past the range the calculation was
        asked for and "show me everything" has to mean everything.
        """
        low = [float(np.min(self.curve.x))] if self.curve.n_points \
            else [0.0]
        high = [float(np.max(self.curve.x))] if self.curve.n_points \
            else [1.0]
        for _label, other_x, _y in self.overlays:
            if len(other_x):
                low.append(float(np.min(other_x)))
                high.append(float(np.max(other_x)))
        return min(low), max(high)

    def _on_range(self) -> None:
        """Apply what the boxes say, with an emptied one meaning all
        of it.

        Clearing a box is a request rather than a mistake -- it is how
        somebody asks for that end of the axis back -- so it resets to
        the data's own limit instead of restoring what was typed
        before.  Either box, or both.  Reversed ends are swapped
        rather than refused, because that is unambiguously what was
        meant, and two ends that land on the same number leave the
        axis alone because an empty axis is not what anybody asked
        for.
        """
        edge = self.limits()
        low = _number(self.low.text(), edge[0])
        high = _number(self.high.text(), edge[1])
        if low == high:
            self._show_range()
            return
        if low > high:
            low, high = high, low
        self.axes.set_xlim(low, high)
        self._show_range()
        self.canvas.draw_idle()

    # -- what the buttons do -------------------------------------------

    def add_overlay(self) -> None:
        """Read a measured pattern and draw it on top."""
        path, _filter = QFileDialog.getOpenFileName(
            self, "Overlay a measured pattern" if self.pattern
            else "Overlay data", self.directory,
            "Diffraction pattern (*.xy *.xye *.dat);;All files (*)"
            if self.pattern else DATA_FILTER)
        if not path:
            return
        try:
            x, y = read_xy(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Overlay", str(exc))
            return
        self.directory = str(Path(path).parent)
        self.overlays.append((Path(path).stem, x, y))
        self.replot()

    def save_figure(self) -> None:
        """Write the figure, vector or raster, from the suffix."""
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save the figure",
            str(Path(self.directory) / f"{_stem(self.curve)}.pdf"),
            FIGURE_FILTERS)
        if not path:
            return
        import matplotlib as mpl

        try:
            with mpl.rc_context(EDITABLE_TEXT):
                self.figure.savefig(path, dpi=RASTER_DPI,
                                    bbox_inches="tight",
                                    facecolor="white")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Save the figure", str(exc))
            return
        self.directory = str(Path(path).parent)
        self.status.setText(
            f"Wrote {Path(path).name}"
            + (" -- the text in it is still text."
               if Path(path).suffix.lower() in VECTOR_SUFFIXES else ""))

    def save_pattern(self) -> None:
        """Write the calculated trace as two columns."""
        noun = "pattern" if self.pattern else "data"
        path, _filter = QFileDialog.getSaveFileName(
            self, f"Save the {noun}",
            str(Path(self.directory) / f"{_stem(self.curve)}.xy"),
            "Diffraction pattern (*.xy)" if self.pattern
            else "Two-column data (*.xy)")
        if not path:
            return
        try:
            write_xy(self.curve.x, self.curve.y, path,
                     header=f"{self.curve.title}\n{self.curve.note}")
        except OSError as exc:                      # pragma: no cover
            QMessageBox.warning(self, f"Save the {noun}", str(exc))
            return
        self.directory = str(Path(path).parent)
        self.status.setText(f"Wrote {Path(path).name}")


def _percent(values) -> np.ndarray:
    """A trace scaled so its tallest point is 100."""
    values = np.asarray(values, dtype=float)
    top = float(np.max(values)) if values.size else 0.0
    return 100.0 * values / top if top > 0 else values


def _quantity(label: str) -> str:
    """``"volume"`` from ``"volume (A^3)"``: the name, for the range
    box's caption, which has no room for the units as well."""
    return (label or "").split(" (")[0].strip()


def _units(label: str) -> str:
    """``"A^3"`` from ``"volume (A^3)"``, or ``""``."""
    label = label or ""
    if "(" in label and label.endswith(")"):
        return label[label.rindex("(") + 1:-1]
    return ""


def _stem(curve) -> str:
    """A filename from the block's title, without inventing one."""
    from xtal.workspace import safe_name

    return safe_name(curve.title or "pattern", "pattern").lower()


def _range_entry(tip: str) -> QLineEdit:
    """One end of the x axis, as a box to type in.

    A line edit and not a spin box: a range is two numbers somebody
    reads off a paper and types, and a spin box's arrows invite
    stepping through a degree at a time, which is not how anybody
    chooses one.  It accepts what is typed when the box is left --
    tabbed out of or clicked away from -- or when Return is pressed;
    there is no Apply, because two boxes and a button to make them
    count is three things where two will do.

    **No validator, and that is the whole of why this works.**  It had
    a ``QDoubleValidator``, which looks like the obviously right thing
    to put on a box that takes a number and quietly breaks the one
    case it most needed to handle: ``editingFinished`` is not emitted
    while a validator calls the text ``Intermediate``, and an *empty*
    box is intermediate.  So clearing a box -- which is how somebody
    asks for that end of the axis back -- did nothing at all until the
    *other* box was edited.  Whatever arrives is parsed by
    :func:`_number` instead, which already has to have an answer for
    an empty box and gives the same one to anything else unreadable.
    """
    entry = QLineEdit()
    entry.setToolTip(tip)
    entry.setMaximumWidth(70)
    entry.setAlignment(Qt.AlignRight)
    return entry


def _number(text: str, fallback: float) -> float:
    """What a box says, or the limit it stands for when it says
    nothing."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return float(fallback)
