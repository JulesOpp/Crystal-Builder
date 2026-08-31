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

**It stays small on purpose.**  A row, a table, a histogram.  Not a
layout language: the second module that needs something this cannot say
is the one that gets to add it, against a real use, which is the same
rule the parameter registry was built under.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Row:
    """One labelled number, and what it means.

    ``note`` is the sentence that stops a number being misread -- what
    D_f is, why an area with no probe radius is meaningless -- and it
    is a field rather than a footnote because the row is where somebody
    reads the number and therefore where the caveat has to be.
    """

    label: str
    value: str = ""
    unit: str = ""
    note: str = ""
    #: A short symbol, when the literature has one: ``D_f``, ``ASA``.
    symbol: str = ""

    @classmethod
    def number(cls, label, value, unit="", note="", symbol="",
               decimals: int = 3) -> Row:
        try:
            text = f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):             # pragma: no cover
            text = str(value)
        return cls(label, text, unit, note, symbol)

    def as_text(self, width: int = 34) -> str:
        name = f"{self.label} ({self.symbol})" if self.symbol \
            else self.label
        value = f"{self.value} {self.unit}".strip()
        return f"{name:<{width}s}  {value}"


@dataclass(frozen=True)
class Table:
    """Rows under a heading."""

    title: str = ""
    rows: tuple[Row, ...] = ()
    note: str = ""

    def as_text(self) -> str:
        width = max((len(r.label) + (len(r.symbol) + 3 if r.symbol
                                     else 0) for r in self.rows),
                    default=10)
        lines = [self.title] if self.title else []
        lines += [row.as_text(width) for row in self.rows]
        if self.note:
            lines += ["", self.note]
        return "\n".join(lines)


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
class Report:
    """Everything one run is worth showing, in the order to show it."""

    title: str = ""
    blocks: tuple = ()              # Table | Histogram
    note: str = ""

    @property
    def tables(self) -> list[Table]:
        return [b for b in self.blocks if isinstance(b, Table)]

    @property
    def histograms(self) -> list[Histogram]:
        return [b for b in self.blocks if isinstance(b, Histogram)]

    def __bool__(self) -> bool:
        return bool(self.blocks)

    def as_text(self) -> str:
        parts = [self.title] if self.title else []
        parts += [block.as_text() for block in self.blocks]
        if self.note:
            parts.append(self.note)
        return "\n\n".join(p for p in parts if p)
