"""
xtal.powder.index
=================
Indexing: which unit cells explain the fitted lines -- TOPAS's
``b_indy`` step, and the table its ``.ndx`` is.

RietX searches (``rietx.index_pattern``: three engines that fail
differently, their agreement the confidence) and ranks each cell's
extinction classes (``determine_extinction_symbol``).  What is decided
here is how a person asks -- which of the fourteen Bravais lattices,
which space groups -- and what the answer looks like as rows.

**There is no winner unless RietX names one.**  ``best_or_none`` is
``None`` whenever the engines disagree, the figures of merit disagree,
or the pattern could not validate the cell, and it is ``None`` far
more often than the right cell is missing from the top of the list.
:attr:`IndexResult.best` is that answer and nothing softer; every row
carries its confidence and the reasons it is not higher, and the table
shows them rather than a guess.

**A space group is a list of classes, never one group.**  A powder
pattern shows the extinction symbol; groups sharing one differ only
by elements that produce no absences.  A space-group selection
therefore *filters classes* -- keeps those holding a chosen group --
and restricts the search to the lattices those groups are on.  Groups
are compared by number, so ``C2221`` matches the class RietX lists as
``A 21 2 2`` in the setting its cell came out in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from xtal.powder.data import PowderData, PowderError, Radiation

__all__ = ["BRAVAIS", "GroupClass", "IndexOptions", "IndexResult",
           "IndexRow", "bravais_of_group", "index", "lines_of",
           "parse_bravais",
           "parse_space_groups"]

#: The fourteen Bravais lattices, as TOPAS's ``Bravais_*_sgs`` choose
#: them and in the order a person reads them: ``(symbol, [(RietX
#: system, centring), ...])``.  ``hP`` is two of RietX's systems
#: because the hexagonal and trigonal-P metrics are one lattice --
#: TOPAS's ``Bravais_Trigonal_Hexagonal_sgs`` is one line too.
BRAVAIS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("aP", (("triclinic", "P"),)),
    ("mP", (("monoclinic", "P"),)),
    ("mC", (("monoclinic", "C"),)),
    ("oP", (("orthorhombic", "P"),)),
    ("oC", (("orthorhombic", "C"),)),
    ("oI", (("orthorhombic", "I"),)),
    ("oF", (("orthorhombic", "F"),)),
    ("tP", (("tetragonal", "P"),)),
    ("tI", (("tetragonal", "I"),)),
    ("hP", (("hexagonal", "P"), ("trigonal", "P"))),
    ("hR", (("trigonal", "R"),)),
    ("cP", (("cubic", "P"),)),
    ("cI", (("cubic", "I"),)),
    ("cF", (("cubic", "F"),)),
)

_SYSTEM_LETTER = {"triclinic": "a", "monoclinic": "m",
                  "orthorhombic": "o", "tetragonal": "t",
                  "trigonal": "h", "hexagonal": "h", "cubic": "c"}


def parse_bravais(text) -> frozenset[str]:
    """``"oP, oC mP"`` as a set; empty or ``"all"`` is all fourteen,
    and ``"none"`` -- every box unticked -- is none, which the search
    then refuses rather than reading as "any"."""
    known = {symbol for symbol, _lattices in BRAVAIS}
    words = str(text or "").replace(";", ",").replace(" ", ",")
    chosen = {w.strip() for w in words.split(",") if w.strip()}
    if not chosen or chosen == {"all"}:
        return frozenset(known)
    if chosen == {"none"}:
        return frozenset()
    by_lower = {s.lower(): s for s in known}
    out = set()
    for word in chosen:
        if word.lower() not in by_lower:
            raise PowderError(
                f"{word!r} is not a Bravais lattice; have "
                f"{', '.join(s for s, _l in BRAVAIS)}")
        out.add(by_lower[word.lower()])
    return frozenset(out)


def parse_space_groups(text) -> tuple:
    """Space groups named by symbol or number, as gemmi's groups.

    Commas separate them, since a symbol has spaces in it: ``"C2221,
    Ccc2"``, ``"C 2 2 21, 37"``.
    """
    import gemmi

    out = []
    for word in str(text or "").replace(";", ",").split(","):
        word = word.strip()
        if not word:
            continue
        group = gemmi.find_spacegroup_by_name(word)
        if group is None:
            raise PowderError(f"{word!r} is not a space group")
        out.append(group)
    return tuple(out)


def bravais_of_group(group) -> str:
    """The Bravais lattice a gemmi space group is on (``"oC"``).

    An A- or B-centred setting is C-centred on other axes, and RietX
    searches the C setting.
    """
    centring = group.centring_type()
    if centring in ("A", "B"):
        centring = "C"
    return _SYSTEM_LETTER[group.crystal_system_str()] + centring


@dataclass(frozen=True)
class IndexOptions:
    """What the indexing step asks (TOPAS ``b_indy.inp``).

    ``space_groups`` is a comma-separated list or empty.
    ``zero_error`` is the systematic 2θ allowance the matching must
    span, TOPAS's ``index_zero_error``; 0 lets RietX measure one from
    line pairs or assume its own.  ``max_volume`` 0 takes the envelope
    from the data.  ``longest_axis`` bounds the search's d(100); 50 A
    holds a framework's cell, where RietX's own 25 A does not, and
    lowering it for a small cell saves most of the time.  ``budget``
    is the whole run's ceiling in seconds.
    ``rank_groups`` is how many of the top cells get their extinction
    classes ranked -- one Le Bail fit per class each.
    """

    bravais: frozenset[str] = frozenset(s for s, _l in BRAVAIS)
    space_groups: str = ""
    zero_error: float = 1.0
    max_volume: float = 0.0
    longest_axis: float = 50.0
    budget: float = 60.0
    rank_groups: int = 3


@dataclass
class GroupClass:
    """One extinction class: a symbol and every group sharing it."""

    symbol: str
    space_groups: tuple[str, ...]
    delta_bic: float
    refuted: bool
    conditions: tuple[str, ...] = ()
    #: the group RietX fitted the class as, in the cell's setting
    representative: str = ""


@dataclass
class IndexRow:
    """One candidate cell, as the table shows it.

    ``classes`` is ``None`` when its extinction classes were not
    ranked (below ``rank_groups``, or stopped first) and a list --
    possibly empty under a space-group selection -- when they were.
    """

    rank: int
    system: str
    centring: str
    cell: tuple[float, float, float, float, float, float]
    cell_esd: tuple[float, float, float, float, float, float]
    volume: float
    fom: tuple[str, float] | None
    n_indexed: int
    n_lines: int
    confidence: str
    caveats: tuple[str, ...]
    lebail_rwp: float | None
    found_by: tuple[str, ...]
    #: the lattice's absence-free group (``P 4/m m m``), what a cell
    #: is fitted in before its absences are known
    lattice_group: str = ""
    classes: list[GroupClass] | None = None
    native: Any = None

    @property
    def bravais(self) -> str:
        return _SYSTEM_LETTER[self.system] + self.centring

    @property
    def unindexed(self) -> int:
        return self.n_lines - self.n_indexed

    @property
    def gof(self) -> float | None:
        """The figure of merit, as TOPAS's indexing GOF: higher is a
        cell that explains the line positions better."""
        return None if self.fom is None else float(self.fom[1])

    @property
    def gof_per_unindexed(self) -> float | None:
        """GoF over (unindexed lines + 1), TOPAS's second ordering: a
        cell that leaves lines unexplained pays for each.  The one is
        so a cell indexing everything is not a division by zero."""
        gof = self.gof
        return None if gof is None else gof / (self.unindexed + 1)

    @property
    def fit_group(self) -> str:
        """The group to fit this cell in next: the top surviving
        class's, or the lattice's own when no class was ranked."""
        alive = [c for c in self.classes or () if not c.refuted]
        if alive and alive[0].representative:
            return alive[0].representative
        return self.lattice_group

    @property
    def space_groups(self) -> str:
        """The top surviving class's groups, or why there are none."""
        if self.classes is None:
            return ""
        alive = [c for c in self.classes if not c.refuted]
        if not alive:
            return "no class fits" if self.classes else \
                "none of the groups asked for"
        return ", ".join(alive[0].space_groups)


@dataclass
class IndexResult:
    """The ranked cells, and what the search did and did not cover."""

    rows: list[IndexRow]
    best: int | None
    stopped: bool
    systems_searched: tuple[str, ...]
    complete: dict[str, bool]
    wavelength: float
    two_theta_range: tuple[float, float]
    notes: list[str] = field(default_factory=list)


def _lattices(bravais: frozenset[str], groups) -> dict[str, list[str]]:
    """``{system: [centrings]}`` to search, a group list narrowing it."""
    chosen = set(bravais)
    if groups:
        wanted = {bravais_of_group(g) for g in groups}
        if not chosen & wanted:
            raise PowderError(
                "none of the space groups asked for is on a Bravais "
                "lattice that is ticked ("
                + ", ".join(sorted(wanted)) + " would be)")
        chosen &= wanted
    out: dict[str, list[str]] = {}
    for symbol, lattices in BRAVAIS:
        if symbol in chosen:
            for system, centring in lattices:
                out.setdefault(system, []).append(centring)
    if not out:
        raise PowderError("tick at least one Bravais lattice")
    return out


def index(peak_list, data: PowderData, radiation: Radiation,
          options: IndexOptions | None = None, *, cancel=None,
          say=None) -> IndexResult:
    """Search for the cells that index ``peak_list``, and rank them.

    ``peak_list`` is RietX's own (``PeakFit.for_indexing()``, the
    unticked lines already out) and ``data`` the pattern cropped to the
    range the peaks were fitted over, which is what a candidate is
    validated against.  ``cancel`` is a job's
    :class:`~xtal.modules.job.Cancellation`: Stop returns the cells
    reached so far, never nothing.
    """
    from xtal.powder import bridge

    options = options or IndexOptions()
    groups = parse_space_groups(options.space_groups)
    lattices = _lattices(options.bravais, groups)
    token = bridge.cancel_token(cancel)
    say = say or (lambda _text: None)

    def on_stage(label, k, total):
        what, _sep, where = label.partition(":")
        verb = "validating" if what == "validate" else \
            "agreeing on" if what == "consensus" else f"searching ({what})"
        say(f"{verb} {where}, {k} of {total}")

    native = bridge.index_pattern(
        peak_list, data, radiation,
        systems=[s for s in _SEARCH_ORDER if s in lattices],
        centrings={s: tuple(c) for s, c in lattices.items()},
        shift_allowance=options.zero_error,
        max_volume=options.max_volume or None,
        max_axis=options.longest_axis, budget=options.budget,
        prior_space_groups=[g.hm for g in groups], cancel=token,
        on_stage=on_stage)
    best = native.best_or_none()
    rows = [_row(k, c) for k, c in enumerate(native.candidates, start=1)]
    numbers = {g.number for g in groups}
    for row in rows[:max(int(options.rank_groups), 0)]:
        if token.is_set():
            break
        say(f"ranking the extinction classes of cell {row.rank}")
        screen = bridge.extinction_classes(peak_list, data, radiation,
                                           row.native, cancel=token)
        if token.is_set():
            break
        row.classes = [c for c in map(_class, screen.candidates)
                       if not numbers or _numbers(c) & numbers]
    notes = [d.message for d in native.diagnostics]
    return IndexResult(
        rows=rows,
        best=next((k for k, c in enumerate(native.candidates)
                   if c is best), None),
        stopped=bool(cancel is not None and cancel.requested),
        systems_searched=tuple(native.systems_searched),
        complete=dict(native.search_complete),
        wavelength=float(native.wavelength), two_theta_range=data.range,
        notes=notes)


#: RietX's own order, cheapest metric first -- a budget that runs out
#: then costs the expensive systems, which is RietX's intent.
_SEARCH_ORDER = ("cubic", "hexagonal", "trigonal", "tetragonal",
                 "orthorhombic", "monoclinic", "triclinic")

#: The figures of merit shown, the first defined one: M20 and F_N need
#: twenty lines, and a short list falls back to RietX's own panel.
_FOM_ORDER = ("m20", "f_n", "m_sym", "m_rev")


def _row(rank: int, candidate) -> IndexRow:
    fom = next(((name, candidate.fom_value(name)) for name in _FOM_ORDER
                if candidate.fom_value(name) is not None), None)
    lebail = candidate.lebail
    return IndexRow(
        rank=rank, system=candidate.system, centring=candidate.centring,
        cell=tuple(float(v) for v in candidate.cell),
        cell_esd=tuple(float(v) for v in candidate.cell_esd),
        volume=float(candidate.volume), fom=fom,
        n_indexed=int(candidate.n_indexed),
        n_lines=int(candidate.n_lines),
        confidence=str(candidate.confidence),
        caveats=tuple(candidate.confidence_caveats),
        lebail_rwp=None if lebail is None else float(lebail.rwp),
        found_by=tuple(candidate.found_by),
        lattice_group=str(candidate.lattice_group), native=candidate)


def _class(candidate) -> GroupClass:
    return GroupClass(
        symbol=candidate.symbol,
        space_groups=tuple(candidate.space_groups),
        delta_bic=float(candidate.delta_bic),
        refuted=bool(candidate.refuted),
        conditions=tuple(candidate.conditions),
        representative=str(candidate.representative))


def _numbers(group_class: GroupClass) -> set[int]:
    import gemmi

    out = set()
    for name in group_class.space_groups:
        group = gemmi.find_spacegroup_by_name(name)
        if group is not None:
            out.add(group.number)
    return out


def lines_of(row: IndexRow, wavelength: float, two_theta_range):
    """Every line ``row``'s lattice allows in a range, as 2θ.

    The lattice's lines and not a space group's: absences are what the
    extinction classes are for, and a comb that already left some out
    would hide the line a class is refuted by.
    """
    from xtal.powder import bridge

    lo, hi = two_theta_range
    _hkl, two_theta = bridge.lattice_lines(row.cell, row.system,
                                           row.centring, wavelength,
                                           lo, hi)
    return two_theta
