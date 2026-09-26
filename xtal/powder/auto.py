"""
xtal.powder.auto
================
The automatic run: peaks, indexing, a Pawley fit of every leading
cell in every leading space group, and a table ranked by how well each
fits -- TOPAS's ``b_indy`` into ``c_paw`` without a person copying the
cell across.

**It stops at the ranked table** unless it is asked to go on: a
Pawley table is an answer a person reads, and a Rietveld fit is an
edit to their structure.  Asked, it goes on only when the structure
is the crystal the table found -- its cell within
:data:`RIETVELD_LENGTH` and :data:`RIETVELD_ANGLE` of a row's, in the
same setting, and its space group in no class the pattern refutes --
and says which of those failed when it does not.  A cell 3 % off is
the same lattice and a different compound more often than it is a
thermal expansion, and refining atoms against the wrong pattern
converges to a plausible wrong answer.

**One Pawley per (cell, class), each a folder of its own**, so a row
of the table opens the fit it was ranked by.  A fit RietX refuses is a
row with its reason, never a missing row: "tried and failed" and "not
tried" read differently in a table meant to be trusted.

Nothing here imports rietx; the steps it runs are the ones the
workbench runs, and the same functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

from xtal.powder.data import PowderData, PowderError, PowderStopped, Radiation
from xtal.powder.index import IndexOptions, IndexResult, IndexRow
from xtal.powder.pawley import PawleyFit, PawleyOptions, pawley
from xtal.powder.peaks import PeakOptions, fit_peaks

__all__ = ["AutoOptions", "AutoResult", "AutoRow", "RIETVELD_ANGLE",
           "RIETVELD_LENGTH", "RWP_TIE", "auto", "ranked",
           "rietveld_match"]

#: How far a structure's cell may be from a Pawley row's for the run
#: to go on into Rietveld: a fraction of each length, and degrees.
RIETVELD_LENGTH = 0.01
RIETVELD_ANGLE = 1.0

#: Two fits whose Rwp are this close, as a fraction, are a tie, and
#: indexing's order breaks it.  A cell and its axes relabelled, or a
#: group and its supergroup where the pattern shows no absence, fit to
#: the fourth digit (rutile's tP cell and the oP one with a and c
#: swapped: 9.49 % both), and ordering them by the fifth digit is
#: ordering by noise.  Indexing's order is its figures of merit and
#: the classes' BIC, which is what a tie should defer to.
RWP_TIE = 0.01


@dataclass(frozen=True)
class AutoOptions:
    """What the automatic run asks.

    ``cells`` is how many of indexing's leading cells are Pawley
    fitted, and ``classes`` how many of each one's leading extinction
    classes -- refuted classes left out.  ``rietveld`` goes on from
    the table to the structure; ``rietveld_options`` is the Rietveld
    step's own.
    """

    peaks: PeakOptions = PeakOptions()
    index: IndexOptions = IndexOptions()
    pawley: PawleyOptions = PawleyOptions()
    cells: int = 5
    classes: int = 3
    rietveld: bool = False
    rietveld_options: object = None


@dataclass
class AutoRow:
    """One Pawley fit of the table: a cell of indexing's in one group.

    ``fit`` is ``None`` where the fit failed, and ``error`` says why.
    ``groups`` is every group of the extinction class it stands for.
    """

    cell_rank: int
    class_rank: int
    bravais: str
    cell: tuple[float, ...]
    space_group: str
    class_symbol: str
    groups: tuple[str, ...]
    fit: PawleyFit | None = None
    error: str = ""
    folder: Path | None = None
    rank: int = 0
    #: every class indexing ranked for this cell, refuted ones too:
    #: what says whether a structure's group is ruled out
    cell_classes: tuple = ()

    @property
    def rwp(self) -> float:
        return self.fit.rwp if self.fit is not None else math.inf

    @property
    def gof(self) -> float:
        return self.fit.gof if self.fit is not None else math.inf

    @property
    def volume(self) -> float:
        if self.fit is not None:
            return self.fit.volume
        from xtal.core.lattice import Lattice

        return float(Lattice.from_parameters(*self.cell).volume)


@dataclass
class AutoResult:
    """Every stage's answer, and the table ranked."""

    peaks: object = None                    # PeakFit
    cells: IndexResult | None = None
    rows: list[AutoRow] = field(default_factory=list)
    #: the Rietveld fit, when the run went on and it finished
    rietveld: object = None
    #: the row the structure matched, when one did
    rietveld_row: AutoRow | None = None
    #: why the run did not go on into Rietveld, when it was asked to
    rietveld_refused: str = ""
    stopped: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def best(self) -> AutoRow | None:
        return self.rows[0] if self.rows and self.rows[0].fit else None


def auto(data: PowderData, radiation: Radiation,
         options: AutoOptions | None = None, structure=None, *,
         cancel=None, say=None, folder: Path | None = None,
         on_frame=None, frame_interval: float = 0.2) -> AutoResult:
    """Peaks, index, Pawley every leading (cell, class), rank; then,
    with ``options.rietveld`` and a ``structure`` that matches a row,
    Rietveld on it.

    ``folder`` is the run's: each stage writes into a sub-folder of
    it.  Stop between stages returns what was reached -- the peaks,
    the cells, the fits finished -- with ``stopped`` set; a Pawley fit
    stopped half way is not a row.
    """
    from xtal.powder.index import index

    options = options or AutoOptions()
    say = say or (lambda _text: None)
    result = AutoResult()

    def stopping() -> bool:
        if cancel is not None and cancel.requested:
            result.stopped = True
        return result.stopped

    say("fitting the peaks")
    result.peaks = fit_peaks(data, radiation, options.peaks)
    result.notes += result.peaks.notes
    if stopping():
        return result
    window = data.window(float(result.peaks.two_theta[0]),
                        float(result.peaks.two_theta[-1]))
    # the classes are what the Pawley fits are in: every cell that is
    # fitted needs its ranked
    index_options = replace(
        options.index,
        rank_groups=max(options.index.rank_groups, options.cells))
    result.cells = index(result.peaks.for_indexing(), window, radiation,
                         index_options, cancel=cancel, say=say)
    result.notes += result.cells.notes
    if stopping() or not result.cells.rows:
        if not result.cells.rows:
            result.notes.append("no cell indexes these lines in the "
                                "lattices searched")
        return result

    planned = [row for cell in result.cells.rows[:options.cells]
               for row in _rows_of(cell, options.classes)]
    for k, row in enumerate(planned, start=1):
        if stopping():
            break
        say(f"Pawley {k} of {len(planned)}: cell {row.cell_rank} in "
            f"{row.space_group}")
        row.folder = _sub(folder, f"pawley-{k:02d}")
        try:
            row.fit = pawley(data, radiation, row.cell, row.space_group,
                             options.pawley, cancel=cancel,
                             folder=row.folder)
        except PowderStopped:
            result.stopped = True
            break
        except PowderError as exc:
            row.error = str(exc)
        result.rows.append(row)
    result.rows = ranked(result.rows)

    if not options.rietveld or result.stopped:
        return result
    if structure is None or not structure.sites:
        result.rietveld_refused = ("no structure to refine: open one "
                                   "and run from its window")
        return result
    row, why = rietveld_match(result.rows, structure)
    if row is None:
        result.rietveld_refused = why
        return result
    result.rietveld_row = row
    from xtal.core.lattice import Lattice
    from xtal.powder.rietveld import RietveldOptions, rietveld

    start = structure.copy()
    # the cell the whole pattern just refined, the atoms where they
    # were in it: what Apply cell does, and a better start than the
    # cell the structure was written with
    start.set_lattice(Lattice.from_parameters(*row.fit.cell))
    say(f"Rietveld on the structure, in the cell of row {row.rank}")
    try:
        result.rietveld = rietveld(
            start, data, radiation,
            options.rietveld_options or RietveldOptions(),
            on_frame=on_frame, frame_interval=frame_interval,
            cancel=cancel, folder=_sub(folder, "rietveld"))
    except PowderStopped:
        result.stopped = True
    return result


def ranked(rows) -> list[AutoRow]:
    """``rows`` best first, their ``rank`` set: by Rwp, fits within
    :data:`RWP_TIE` of each other in indexing's order, and failed fits
    last."""
    done = sorted((r for r in rows if r.fit is not None),
                  key=lambda r: r.rwp)
    out, group = [], []
    for row in done:
        if group and row.rwp > group[0].rwp * (1.0 + RWP_TIE):
            out += sorted(group, key=_indexing_order)
            group = []
        group.append(row)
    out += sorted(group, key=_indexing_order)
    out += sorted((r for r in rows if r.fit is None), key=_indexing_order)
    for k, row in enumerate(out, start=1):
        row.rank = k
    return out


def _indexing_order(row: AutoRow):
    return row.cell_rank, row.class_rank


def rietveld_match(rows, structure) -> tuple[AutoRow | None, str]:
    """``(row, "")``: the best row whose cell is the structure's;
    ``(None, why)`` when none is, or when the pattern refutes the
    structure's space group.

    The row's own group is not asked to be the structure's: Rietveld
    refines in the structure's group, and a pattern that shows none of
    its absences ranks a class without them first -- rutile's
    P4_2/mnm is twelfth on a pattern starting at 20° 2θ, and refuted
    by none.  What rules a structure out is a class the screen
    *refuted*.
    """
    from xtal.powder.index import _numbers
    from xtal.powder.pawley import cell_fits_structure

    number = _structure_number(structure)
    reasons = []
    for row in rows:
        if row.fit is None:
            continue
        why = cell_fits_structure(row.fit, structure,
                                  length=RIETVELD_LENGTH,
                                  angle=RIETVELD_ANGLE)
        if not why and number is not None:
            refuted = [c for c in row.cell_classes
                       if c.refuted and number in _numbers(c)]
            if refuted:
                why = (f"the pattern refutes the structure's "
                       f"{structure.space_group.hm}: its class "
                       f"{refuted[0].symbol} has lines where the data "
                       f"has none, or none where it has lines")
        if not why:
            return row, ""
        reasons.append(f"row {row.rank}: {why}")
    if not reasons:
        return None, "no Pawley fit finished to compare the structure with"
    return None, ("the structure matches no row of the table, so it "
                  "was not refined -- " + "; ".join(reasons[:3]))


def _rows_of(cell: IndexRow, classes: int) -> list[AutoRow]:
    """The (cell, group) pairs to fit for one of indexing's cells:
    its leading surviving classes, or the lattice's own group when
    none was ranked."""
    alive = [c for c in cell.classes or () if not c.refuted]
    common = dict(cell_rank=cell.rank, bravais=cell.bravais,
                  cell=tuple(cell.cell),
                  cell_classes=tuple(cell.classes or ()))
    if not alive:
        return [AutoRow(class_rank=1, space_group=cell.lattice_group,
                        class_symbol="(lattice)", groups=(), **common)]
    return [AutoRow(class_rank=k,
                    space_group=c.representative or cell.lattice_group,
                    class_symbol=c.symbol, groups=c.space_groups,
                    **common)
            for k, c in enumerate(alive[:max(int(classes), 1)],
                                  start=1)]


def _structure_number(structure) -> int | None:
    import gemmi

    group = gemmi.find_spacegroup_by_ops(gemmi.symops_from_hall(
        structure.space_group.hall))
    return None if group is None else group.number


def _sub(folder: Path | None, name: str) -> Path | None:
    if folder is None:
        return None
    path = Path(folder) / name
    path.mkdir(parents=True, exist_ok=True)
    return path
