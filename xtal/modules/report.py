"""
xtal.modules.report
===================
What a module has to show, as data rather than as widgets.

:class:`~xtal.modules.job.JobResult` carried a sentence and a geometry,
and said in its own docstring that tables and plots were deliberately
not there yet -- that the first module with one would get to decide the
shape.  Zeo++ is that module: three pore diameters is a table, a pore
size distribution is a histogram, and printing either into the status
bar would be throwing the answer away.

So the shape is three small frozen records and nothing else.

**A report is presentation, not results.**  Every number in one has
already been computed and written into the run folder; this is the
arrangement of them, so a module says *what is worth looking at* and in
what order, and the panel decides what that looks like on screen.  A
module that only wants a sentence still returns nothing here.

**No Qt, no colours, no widths.**  The same report prints as text from
the CLI (:meth:`Report.as_text`), renders into a dock, and is asserted
by a headless test.  A field that only means something to a QTableWidget
would break all three.

**It stays small on purpose.**  A row, a table, a histogram, and --
since PXRD, which is the module that took the rule up on its offer --
a curve.  Not a layout language: the next module that needs something
this cannot say is the one that gets to add it, against a real use,
which is the same rule the parameter registry was built under.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import numpy as np

#: What a table's columns are when nobody says otherwise, which is
#: every table written before there was a reason to say.  One row is
#: one quantity, which is the shape a pore-diameter or a build summary
#: has.
QUANTITY_COLUMNS = ("Quantity", "Value", "Unit")


@dataclass(frozen=True)
class Row:
    """One line of a table.

    Two shapes, and the second earned its way in.  The first is *one
    labelled quantity* -- ``label``, ``value``, ``unit`` -- which is
    what a pore diameter or a build summary is, and what every table
    here was until PXRD.  A reflection list is not that: **No.**,
    **hkl**, **d**, **2-theta** and **I** are five different
    quantities across one row, and squeezing them into a label would
    put four numbers in a column headed *Quantity*.

    So ``cells`` is the general form, the three fields above are the
    common one, and :attr:`texts` is what a renderer reads -- one
    string per column, whichever way the row was written.

    ``note`` is the sentence that stops a number being misread -- what
    D_f is, why an area with no probe radius is meaningless -- and it
    is a field rather than a footnote because the row is where
    somebody reads the number and therefore where the caveat has to
    be.
    """

    label: str = ""
    value: str = ""
    unit: str = ""
    note: str = ""
    #: A short symbol, when the literature has one: ``D_f``, ``ASA``.
    symbol: str = ""
    #: One string per column, for a table whose columns are its own.
    cells: tuple[str, ...] = ()

    @classmethod
    def number(cls, label, value, unit="", note="", symbol="",
               decimals: int = 3) -> Row:
        try:
            text = f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):             # pragma: no cover
            text = str(value)
        return cls(label, text, unit, note, symbol)

    @classmethod
    def of(cls, *cells, note: str = "") -> Row:
        """A row of a table with columns of its own."""
        return cls(cells=tuple(str(c) for c in cells), note=note)

    @property
    def name(self) -> str:
        return f"{self.label} ({self.symbol})" if self.symbol \
            else self.label

    @property
    def texts(self) -> tuple[str, ...]:
        """What this row shows, one string per column."""
        return self.cells or (self.name, self.value, self.unit)

    def as_text(self, widths=()) -> str:
        cells = self.texts
        if not widths:                              # pragma: no cover
            widths = tuple(len(c) for c in cells)
        return "  ".join(
            _pad(text, width) for text, width
            in zip(cells, widths, strict=False)).rstrip()


def is_number(text: str) -> bool:
    """Whether a cell is a quantity rather than a word.

    Which is the whole of how a column decides its alignment: numbers
    right so the decimal points line up, words left.  Derived from the
    cell rather than declared per column, because a column of hkl
    indices is neither and the answer that reads best is the one the
    content gives.
    """
    try:
        float(str(text).strip())
    except (TypeError, ValueError):
        return False
    return True


def _pad(text: str, width: int) -> str:
    return (f"{text:>{width}s}" if is_number(text)
            else f"{text:<{width}s}")


@dataclass(frozen=True)
class Table:
    """Rows under a heading, in named columns."""

    title: str = ""
    rows: tuple[Row, ...] = ()
    note: str = ""
    #: The column headings.  Three by default -- see
    #: :data:`QUANTITY_COLUMNS` -- and a table that says otherwise is
    #: one whose rows carry :attr:`Row.cells`.
    columns: tuple[str, ...] = QUANTITY_COLUMNS

    @property
    def named_columns(self) -> bool:
        """Whether the columns are this table's own.

        The default three are a *convention* rather than a heading a
        reader needs: a panel that drew ``Quantity | Value | Unit``
        over three pore diameters would be labelling the obvious.
        """
        return tuple(self.columns) != QUANTITY_COLUMNS

    def widths(self) -> tuple[int, ...]:
        return tuple(
            max([len(head)] + [len(r.texts[i]) for r in self.rows
                               if i < len(r.texts)])
            for i, head in enumerate(self.columns))

    def as_text(self) -> str:
        lines = [self.title] if self.title else []
        widths = self.widths()
        if self.named_columns:
            lines.append("  ".join(
                f"{head:<{width}s}" for head, width
                in zip(self.columns, widths, strict=True)).rstrip())
        lines += [row.as_text(widths) for row in self.rows]
        if self.note:
            lines += ["", self.note]
        return "\n".join(lines)

    def as_csv(self) -> str:
        """The grid, and nothing else, for a spreadsheet.

        The heading row and the cells: not the title and not the note,
        because a file whose first line is a sentence is one every
        reader has to be told to skip.  What the note says belongs in
        the report it was read from, and a reflection list opened in
        Excel is a reflection list.

        Here rather than in the panel that offers the button, so that
        the same table exports the same file from the CLI and from a
        headless test -- the rule this whole module is written to.
        """
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        if self.named_columns:
            writer.writerow(self.columns)
        for row in self.rows:
            writer.writerow(row.texts)
        return out.getvalue()


@dataclass(frozen=True)
class Histogram:
    """Bars against a continuous axis, and optionally a curve over
    them.

    Two series rather than one because a pore size distribution is two
    things a reader needs together: how many sample points landed at
    each diameter, which is the sampling, and the derivative of the
    cumulative distribution, which is the distribution as a paper plots
    it.  Either alone invites the wrong reading of the other.
    """

    title: str = ""
    x: np.ndarray = field(default_factory=lambda: np.zeros(0))
    y: np.ndarray = field(default_factory=lambda: np.zeros(0))
    x_label: str = ""
    y_label: str = ""
    #: The optional overlaid curve, on its own scale.
    curve: np.ndarray | None = None
    curve_label: str = ""
    note: str = ""
    #: Where to draw a vertical rule and what to call it -- the free
    #: sphere diameter over a pore size distribution says, at a glance,
    #: which of those pores anything can actually reach.
    markers: tuple[tuple[float, str], ...] = ()

    @property
    def n_bins(self) -> int:
        return len(self.x)

    def as_text(self, rows: int = 24) -> str:
        """The histogram as characters, for a log and for a CLI.

        Not a picture, but enough of one to see where the peak is --
        which is what makes a run readable in a terminal and a log
        worth keeping.
        """
        if not self.n_bins:
            return f"{self.title}: nothing to plot"
        top = float(np.max(self.y)) or 1.0
        step = max(1, self.n_bins // max(rows, 1))
        lines = [self.title] if self.title else []
        for start in range(0, self.n_bins, step):
            chunk = self.y[start:start + step]
            height = float(np.max(chunk))
            bar = "#" * int(round(28 * height / top))
            lines.append(f"{self.x[start]:8.2f}  {bar}")
        if self.x_label:
            lines.append(f"          {self.x_label}")
        return "\n".join(lines)


@dataclass(frozen=True)
class Curve:
    """A continuous trace against a continuous axis, and its ticks.

    The third block, and the module that earned it is PXRD -- which is
    the rule this file set for itself: the second module that needs
    something this cannot say gets to add it, against a real use.  A
    calculated powder pattern is not a histogram.  Its x axis is an
    angle rather than a bin edge, there are ten thousand points rather
    than forty, and drawing it as bars would be a picture of the
    sampling grid.

    ``series`` is more than one trace on one axis because that is the
    whole question a pattern is looked at to answer: does the
    measurement match the calculation.  Each is ``(label, y)`` over
    the shared ``x``, so an overlay read from a file is resampled onto
    the calculated grid by whoever adds it rather than by the panel.

    ``tick_sets`` are combs drawn under the trace: ``(label,
    positions)``, the same shape as ``series`` and for the same
    reason.  More than one because the reflections a structure
    *allows* and the ones its space group *forbids* are two different
    statements about the same axis, and a reader deciding whether an
    extra peak means an impurity or a wrong space group needs to see
    which comb it sits over.  They are here rather than as a block of
    their own because a comb without the curve it belongs to is not a
    thing anybody wants, and because their y is not on the trace's
    scale at all.
    """

    title: str = ""
    x: np.ndarray = field(default_factory=lambda: np.zeros(0))
    y: np.ndarray = field(default_factory=lambda: np.zeros(0))
    x_label: str = ""
    y_label: str = ""
    #: Further traces over the same ``x``: ``(label, y)``.
    series: tuple[tuple[str, np.ndarray], ...] = ()
    #: Combs under the trace: ``(label, positions)``.
    tick_sets: tuple[tuple[str, np.ndarray], ...] = ()
    note: str = ""

    @property
    def n_points(self) -> int:
        return len(self.x)

    @property
    def n_ticks(self) -> int:
        return sum(len(positions) for _label, positions
                   in self.tick_sets)

    def all_series(self) -> list[tuple[str, np.ndarray]]:
        """Every trace including the first, labelled.

        One list so that a renderer, an exporter and a legend do not
        each have to remember that ``y`` is a series too.
        """
        first = [(self.y_label or self.title or "y", self.y)]
        return first + [(label, values) for label, values in self.series]

    def as_text(self, rows: int = 20, width: int = 44) -> str:
        """The trace as characters, for a log and for a CLI.

        Sampled down to the width rather than plotted point by point:
        ten thousand points through a 44-column terminal is the same
        picture either way, and taking the maximum of each bucket is
        what keeps a sharp peak from falling between two samples and
        disappearing.
        """
        if self.n_points < 2:
            return f"{self.title}: nothing to plot"
        y = np.asarray(self.y, dtype=float)
        top = float(np.max(y)) or 1.0
        step = max(1, self.n_points // max(rows, 1))
        lines = [self.title] if self.title else []
        for start in range(0, self.n_points, step):
            height = float(np.max(y[start:start + step]))
            bar = "#" * int(round(width * height / top))
            lines.append(f"{self.x[start]:8.2f}  {bar}")
        if self.x_label:
            lines.append(f"          {self.x_label}")
        return "\n".join(lines)


@dataclass(frozen=True)
class Bands:
    """A band structure: energies along a path through the zone.

    The fourth block, earned by DFTB+.  Not a curve with many series:
    its x axis is a distance along a path with named corners, the
    energies are relative to a Fermi level that has to be drawn, and
    which window of energy is worth looking at is the reader's choice
    rather than the data's -- a hundred bands of which eight are near
    the gap.

    ``energies[spin, k, band]`` in eV relative to ``fermi``'s own zero,
    so ``fermi`` records where zero was and the plot draws its line at
    zero.  ``ticks`` are ``(x, label)`` at the named points.
    """

    title: str = ""
    x: np.ndarray = field(default_factory=lambda: np.zeros(0))
    energies: np.ndarray = field(
        default_factory=lambda: np.zeros((1, 0, 0)))
    ticks: tuple = ()
    fermi: float = 0.0
    window: tuple = (-6.0, 6.0)
    note: str = ""
    #: Fractional k per point, for the exported table.
    kpoints: np.ndarray | None = None

    def gap(self) -> tuple[float, float] | None:
        """``(highest occupied, lowest empty)`` in eV relative to the
        Fermi level, or ``None`` when a band crosses it -- a metal."""
        below = self.energies[self.energies <= 0.0]
        above = self.energies[self.energies > 0.0]
        if not len(below) or not len(above):
            return None
        top, bottom = float(below.max()), float(above.min())
        crossing = np.any((self.energies.min(axis=1) < 0.0)
                          & (self.energies.max(axis=1) > 0.0))
        return None if crossing else (top, bottom)

    def as_text(self) -> str:
        spins, n_k, n_bands = self.energies.shape
        lines = [self.title] if self.title else []
        lines.append(f"{n_bands} bands at {n_k} k-points"
                     + (f", {spins} spins" if spins > 1 else "")
                     + f"; Fermi level {self.fermi:.3f} eV")
        gap = self.gap()
        lines.append("no gap: a band crosses the Fermi level"
                     if gap is None
                     else f"gap {gap[1] - gap[0]:.3f} eV")
        lines.append("path " + " ".join(label for _x, label
                                        in self.ticks))
        return "\n".join(lines)

    def as_dat(self) -> str:
        """``x  k1 k2 k3  E1 ... En`` per k-point, per spin block."""
        rows = []
        head = "# x(1/A)" + ("  k1 k2 k3" if self.kpoints is not None
                             else "") + "  energies (eV, E_F = 0)"
        rows.append(head)
        rows.append("# ticks: " + "  ".join(
            f"{x:.5f}={label}" for x, label in self.ticks))
        for spin in range(self.energies.shape[0]):
            if spin:
                rows.append("")
            for k, x in enumerate(self.x):
                parts = [f"{x:.6f}"]
                if self.kpoints is not None:
                    parts += [f"{v:.6f}" for v in self.kpoints[k]]
                parts += [f"{e:.5f}" for e in self.energies[spin, k]]
                rows.append("  ".join(parts))
        return "\n".join(rows) + "\n"

    def as_csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        n_bands = self.energies.shape[2]
        writer.writerow(["spin", "x"] + [f"band{b + 1}"
                                         for b in range(n_bands)])
        for spin in range(self.energies.shape[0]):
            for k, x in enumerate(self.x):
                writer.writerow([spin + 1, f"{x:.6f}"]
                                + [f"{e:.5f}"
                                   for e in self.energies[spin, k]])
        return out.getvalue()


@dataclass(frozen=True)
class Dos:
    """A density of states, total and projected, against energy.

    Energies in eV relative to the Fermi level, like :class:`Bands`,
    and drawn with energy up the page so that when a run has both the
    two share an axis side by side -- which is how a band structure
    and its density of states are read.  ``partial`` is ``(label, y)``
    per element, or per element and shell; ``total`` is their sum.
    """

    title: str = ""
    energies: np.ndarray = field(default_factory=lambda: np.zeros(0))
    total: np.ndarray = field(default_factory=lambda: np.zeros(0))
    partial: tuple = ()
    fermi: float = 0.0
    sigma: float = 0.1
    window: tuple = (-6.0, 6.0)
    note: str = ""

    def as_text(self) -> str:
        lines = [self.title] if self.title else []
        lines.append(f"{len(self.energies)} points, Gaussian "
                     f"broadening {self.sigma:g} eV, Fermi level "
                     f"{self.fermi:.3f} eV")
        lines.append("projected onto " + ", ".join(
            label for label, _y in self.partial))
        return "\n".join(lines)

    def as_dat(self) -> str:
        head = ["E-E_F(eV)", "total"] + [label.replace(" ", "_")
                                         for label, _y in self.partial]
        rows = ["# " + "  ".join(head)]
        for i, energy in enumerate(self.energies):
            rows.append("  ".join(
                [f"{energy:.4f}", f"{self.total[i]:.6f}"]
                + [f"{y[i]:.6f}" for _label, y in self.partial]))
        return "\n".join(rows) + "\n"


@dataclass(frozen=True)
class Modes:
    """Vibrational modes: a frequency each, and how each atom moves.

    Carries the geometry it was computed at -- ``elements`` and
    ``cart`` of the P1 cell, and the ``lattice`` -- because what is
    worth doing with a mode is watching it, and a mode's displacements
    mean nothing without the positions they are displacements of.
    ``displacements[mode, atom, 3]`` is normalised to a largest atom
    displacement of one; negative frequencies are imaginary.
    """

    title: str = ""
    frequencies: np.ndarray = field(default_factory=lambda: np.zeros(0))
    displacements: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 0, 3)))
    elements: tuple = ()
    cart: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    lattice: np.ndarray | None = None
    note: str = ""

    @property
    def n_modes(self) -> int:
        return len(self.frequencies)

    #: How far below zero a frequency has to be to be called imaginary.
    #: A free molecule's rotations and translations are zero in
    #: principle and come out tens of cm^-1 either side of it from
    #: finite differences -- relaxed CO2 gave -39 -- and a table that
    #: flagged those would tell somebody to relax a structure that is
    #: relaxed.
    IMAGINARY_BELOW = -50.0

    def is_imaginary(self, frequency: float) -> bool:
        return float(frequency) < self.IMAGINARY_BELOW

    @property
    def n_imaginary(self) -> int:
        return int(np.count_nonzero(
            np.asarray(self.frequencies) < self.IMAGINARY_BELOW))

    def as_text(self) -> str:
        lines = [self.title] if self.title else []
        lines.append(f"{self.n_modes} modes, {self.n_imaginary} "
                     f"imaginary")
        lines += [f"{n + 1:5d}  {f:10.2f} cm-1"
                  + ("  imaginary" if self.is_imaginary(f) else "")
                  for n, f in enumerate(self.frequencies)]
        return "\n".join(lines)

    def as_dat(self) -> str:
        rows = ["# mode  frequency(cm-1)  then dx dy dz per atom"]
        for n, frequency in enumerate(self.frequencies):
            rows.append(f"{n + 1:5d}  {frequency:12.4f}  " + "  ".join(
                f"{v: .6f}" for v in self.displacements[n].ravel()))
        return "\n".join(rows) + "\n"


@dataclass(frozen=True)
class Zone:
    """The first Brillouin zone of a cell, with a path through it.

    Drawn so that the letters on a band structure's axis mean
    something: which corner Gamma, X and L are, and which way the path
    runs.  ``lattice`` is the real-space matrix, from which the panel
    works out the zone (:func:`xtal.analysis.kpath.brillouin_zone`) --
    the block holds what was run, not a picture of it.
    """

    title: str = ""
    lattice: np.ndarray = field(default_factory=lambda: np.eye(3))
    points: tuple = ()              # (label, (k1, k2, k3)) fractional
    runs: tuple = ()                # runs of labels, as a BandPath

    def as_text(self) -> str:
        path = ",".join("".join(run) for run in self.runs)
        return f"{self.title}\npath {path}" if self.title \
            else f"path {path}"


@dataclass(frozen=True)
class Surface:
    """A quantity over a grid of two axes, and the files behind it.

    The sixth block, earned by the relaxed scan, which is the rule
    this file set itself: the second module needing something the
    existing blocks cannot say gets to add one, against a real use.
    An energy landscape is not a :class:`Curve` with many series.  Its
    second axis is continuous rather than a list of labels, the
    quantity lives in colour rather than in height, each cell carries
    whether it converged, and behind each is a structure somebody will
    want to open.

    ``z`` is NaN wherever a point did not finish, and that is load
    bearing.  A hole plotted as a zero is the deepest point of every
    landscape it appears in, so the renderer has to be handed
    something it cannot mistake for a number.

    ``paths`` is a file per cell -- the relaxed structure at that
    point -- or an empty string where there is none.  It is what makes
    the picture clickable, and it is in the block rather than
    reconstructed by the panel because only the run knew where it
    wrote them.

    ``note`` says what was held fixed while the landscape was taken.
    A profile that does not say that cannot be read, and half the
    confusion in the literature this was built for comes from plots
    that leave it out.
    """

    title: str = ""
    x: np.ndarray = field(default_factory=lambda: np.zeros(0))
    y: np.ndarray = field(default_factory=lambda: np.zeros(0))
    #: ``(len(y), len(x))`` -- row major, y down the rows, as an
    #: image is indexed and as ``numpy`` would have it anyway.
    z: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    x_label: str = ""
    y_label: str = ""
    z_label: str = ""
    #: ``(len(y), len(x))`` of bool; False is drawn apart rather than
    #: coloured, because an unconverged point is not a measurement.
    converged: np.ndarray | None = None
    #: ``(len(y), len(x))`` of str.
    paths: tuple[tuple[str, ...], ...] = ()
    #: Further sheets of the same grid: ``(label, z)``.  A scan walked
    #: in both directions is two, and they are kept apart because
    #: where they differ is the hysteresis.
    sheets: tuple[tuple[str, np.ndarray], ...] = ()
    note: str = ""

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.y), len(self.x))

    @property
    def n_points(self) -> int:
        return int(np.size(self.z))

    @property
    def n_finished(self) -> int:
        return int(np.count_nonzero(np.isfinite(self.z)))

    def all_sheets(self) -> list[tuple[str, np.ndarray]]:
        """Every sheet including the first, labelled."""
        first = [(self.z_label or self.title or "z", self.z)]
        return first + [(label, values) for label, values
                        in self.sheets]

    def path_at(self, row: int, column: int) -> str:
        """The file behind one cell, or ``""``.

        Bounds-checked rather than indexed, because a landscape is
        drawn from one array and clicked through another and a scan
        that was stopped has fewer of the second.
        """
        if row < 0 or column < 0 or row >= len(self.paths):
            return ""
        line = self.paths[row]
        return line[column] if column < len(line) else ""

    def as_text(self, width: int = 9) -> str:
        """The grid as characters, for a log and for a CLI.

        The numbers themselves rather than a picture of them: a
        landscape is usually a handful of points across, they matter
        individually, and a reader in a terminal wants to see which
        cell is lowest and which never finished.
        """
        if not self.n_points:
            return f"{self.title}: nothing to plot"
        lines = [self.title] if self.title else []
        if self.y_label or self.x_label:
            lines.append(f"{self.y_label} down, {self.x_label} across")
        header = " " * width + "".join(
            f"{v:>{width}.4g}" for v in self.x)
        lines.append(header)
        for row, down in enumerate(self.y):
            cells = []
            for column in range(len(self.x)):
                value = self.z[row, column]
                if not np.isfinite(value):
                    cells.append(f"{'--':>{width}}")
                    continue
                mark = ""
                if (self.converged is not None
                        and not self.converged[row, column]):
                    mark = "?"
                cells.append(f"{f'{value:.4g}{mark}':>{width}}")
            lines.append(f"{down:>{width}.4g}" + "".join(cells))
        if self.converged is not None and not np.all(self.converged):
            lines.append("? did not reach the tolerance;  "
                         "-- did not finish")
        if self.note:
            lines.append(self.note)
        return "\n".join(lines)

    def as_csv(self) -> str:
        """One row per cell, which is what a spreadsheet wants.

        Not the grid as a matrix: a matrix loses which axis is which
        the moment it is pasted anywhere, and the cell's file has
        nowhere to go in it.
        """
        out = io.StringIO()
        writer = csv.writer(out)
        labels = [label for label, _values in self.all_sheets()]
        writer.writerow([self.x_label or "x", self.y_label or "y",
                         *labels, "converged", "file"])
        for row in range(len(self.y)):
            for column in range(len(self.x)):
                values = [f"{values[row, column]:.10g}"
                          for _label, values in self.all_sheets()]
                converged = ("" if self.converged is None
                             else str(bool(
                                 self.converged[row, column])))
                writer.writerow([
                    f"{self.x[column]:.10g}", f"{self.y[row]:.10g}",
                    *values, converged, self.path_at(row, column)])
        return out.getvalue()


@dataclass(frozen=True)
class Report:
    """Everything one run is worth showing, in the order to show it."""

    title: str = ""
    #: Table | Histogram | Curve | Bands | Dos | Modes | Zone
    #: | Surface
    blocks: tuple = ()
    note: str = ""

    @property
    def tables(self) -> list[Table]:
        return [b for b in self.blocks if isinstance(b, Table)]

    @property
    def histograms(self) -> list[Histogram]:
        return [b for b in self.blocks if isinstance(b, Histogram)]

    @property
    def curves(self) -> list[Curve]:
        return [b for b in self.blocks if isinstance(b, Curve)]

    @property
    def bands(self) -> list[Bands]:
        return [b for b in self.blocks if isinstance(b, Bands)]

    @property
    def doses(self) -> list[Dos]:
        return [b for b in self.blocks if isinstance(b, Dos)]

    @property
    def modes(self) -> list[Modes]:
        return [b for b in self.blocks if isinstance(b, Modes)]

    @property
    def zones(self) -> list[Zone]:
        return [b for b in self.blocks if isinstance(b, Zone)]

    @property
    def surfaces(self) -> list[Surface]:
        return [b for b in self.blocks if isinstance(b, Surface)]

    def __bool__(self) -> bool:
        return bool(self.blocks)

    def as_text(self) -> str:
        parts = [self.title] if self.title else []
        parts += [block.as_text() for block in self.blocks]
        if self.note:
            parts.append(self.note)
        return "\n\n".join(p for p in parts if p)
