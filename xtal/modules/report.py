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
class Report:
    """Everything one run is worth showing, in the order to show it."""

    title: str = ""
    blocks: tuple = ()              # Table | Histogram | Curve
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

    def __bool__(self) -> bool:
        return bool(self.blocks)

    def as_text(self) -> str:
        parts = [self.title] if self.title else []
        parts += [block.as_text() for block in self.blocks]
        if self.note:
            parts.append(self.note)
        return "\n\n".join(p for p in parts if p)
