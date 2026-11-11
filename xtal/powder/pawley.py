"""
xtal.powder.pawley
==================
Pawley: one cell and space group fitted to the whole pattern, every
reflection's intensity a free number -- TOPAS's ``c_paw`` step, and
the test a cell from indexing has to pass before a structure is put
in it.

rietx fits (``mode="pawley"`` over its Le Bail scaffold); what is
decided here is what a person sets -- the range, the background's
order, which of zero, displacement, cell and the sample's size and
strain broadening are free -- and what the answer is: the R-factors,
the refined cell with its esds, and the reflection list.

**The cell's esds are rietx's and nothing wider.**  A Bragg-Brentano
cell also carries a systematic error of order 1e-4 that no esd
reports (rietx's own ``INDEX_CELL_SYSTEMATIC_UNQUANTIFIED``); the
fit's notes say so when rietx does.

**Nothing here touches a structure.**  Putting the refined cell onto
an open structure, or starting a structure from it, is the window's
-- one undoable edit through the Document -- and
:func:`cell_fits_structure` is the question it asks first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from xtal.powder.data import PowderData, PowderError, Radiation

__all__ = ["DEFAULT_CELL_RANGE", "DEFAULT_ITERATIONS",
           "DEFAULT_TOLERANCE", "EVALUATED", "METHODS", "STALLED_RATIO",
           "PawleyFit", "PawleyOptions", "Reflection", "StartOffset",
           "cell_fits_structure", "parse_cell", "parse_hold", "pawley",
           "start_lines", "start_offset"]

#: rietx's own: a stage's most iterations, and the relative fall in χ²
#: its last stage stops at -- so the boxes at their defaults change
#: nothing a fit did before they were there.
DEFAULT_ITERATIONS = 100
DEFAULT_TOLERANCE = 1e-9

#: A fit's status when it ran no cycles: evaluated at the values it
#: was handed, nothing moved and nothing to converge.
EVALUATED = "evaluated"

#: How far a cell may move from where it started, as a fraction of
#: each length (and of a right angle, for an angle).  Bounded, a cell
#: that wanders off is stopped at the edge and refused; unbounded,
#: Le Bail started 0.5-2 % off took rutile 85 % long and gave
#: fluorapatite a negative c, both "converged".
DEFAULT_CELL_RANGE = 0.025

#: A Pawley fit whose Rwp is this many times its own Le Bail pass's has
#: stalled: free intensities can always do at least as well as
#: partitioned ones, so a fit worse than that stopped with its lines
#: misplaced.  ZSM-5 ended at 26 % against Le Bail's 7 %.
STALLED_RATIO = 1.1

#: How a whole-pattern fit without atoms finds its intensities, by
#: rietx's mode name.
METHODS = {"pawley": "Pawley", "lebail": "Le Bail"}


@dataclass(frozen=True)
class PawleyOptions:
    """What the Pawley step asks (TOPAS ``c_paw.inp``).

    ``background_terms`` is the Chebyshev polynomial's length --
    TOPAS's ``bkg`` line with that many coefficients.  ``zero`` and
    ``displacement`` are the two ways a line moves with angle
    (constant, and cos θ); they are correlated, and freeing both on a
    short range can trade one for the other.  ``size`` and ``strain``
    are TOPAS's ``CS_L``/``CS_G`` and ``Strain_L``/``Strain_G``.
    ``hold_cell`` names the cell numbers held at the value given
    (``"a"``, ``"beta"``) while the others the group leaves free
    refine -- TOPAS's ``a 4.59`` beside ``b @ 9.23``.  ``method`` is
    ``"pawley"`` (every intensity a least-squares variable) or
    ``"lebail"`` (the intensities re-partitioned from the observed
    pattern between cycles, and never variables): the same plan either
    way, so the two are compared on one footing.  ``max_iterations``
    and ``tolerance`` are every stage's (TOPAS's iters and
    convergence criterion); 0 iterations evaluates at the values
    given, fitting nothing.  ``cell_range`` is how far the cell may
    move from the one given, a fraction of each length
    (``DEFAULT_CELL_RANGE``); 0 leaves it unbounded.

    ``lebail_first`` runs a Le Bail fit over the same plan before a
    Pawley one and starts Pawley from its cell and profile.  A Pawley
    fit makes every intensity a variable, and with the lines misplaced
    those shrink where the lines are not and the cell stops moving: it
    found quartz from 0.1 % off and not from 0.2 %.  Le Bail finds the
    lines in seconds, and its Rwp is the bar the Pawley fit must clear
    (``STALLED_RATIO``).
    """

    start: float | None = None
    finish: float | None = None
    background_terms: int = 8
    zero: bool = False
    displacement: bool = True
    hold_cell: tuple[str, ...] = ()
    size: bool = True
    strain: bool = True
    method: str = "pawley"
    max_iterations: int = DEFAULT_ITERATIONS
    tolerance: float = DEFAULT_TOLERANCE
    cell_range: float = DEFAULT_CELL_RANGE
    lebail_first: bool = True

    def free(self, radiation: Radiation) -> tuple[str, ...]:
        """The rietx groups freed, in the bridge's words.

        The background and the widths are always free: a Pawley fit
        that could not fit them would put every misfit into the
        intensities.  A capillary has no specimen displacement to
        refine, so it is not freed for a synchrotron whatever the box
        says.
        """
        out = ["background", "profile"]
        if self.zero:
            out.append("zero")
        if self.displacement and not radiation.is_synchrotron:
            out.append("displacement")
        out.append("cell")
        if self.size:
            out.append("size")
        if self.strain:
            out.append("strain")
        return tuple(out)


@dataclass(frozen=True)
class Reflection:
    """One reflection of the fit: TOPAS's ``hkl_m_d_th2 I`` row."""

    hkl: tuple[int, int, int]
    d: float
    two_theta: float
    multiplicity: int
    intensity: float


@dataclass
class PawleyFit:
    """A Pawley fit, and the curves to draw it with.

    The curves are on the grid the fit ran on.  ``space_group`` is the
    extended symbol the fit used, setting included.
    """

    cell: tuple[float, float, float, float, float, float]
    cell_esd: tuple[float, float, float, float, float, float]
    space_group: str
    rwp: float
    rp: float
    rexp: float
    gof: float
    status: str
    two_theta: np.ndarray
    y_obs: np.ndarray
    y_calc: np.ndarray
    y_background: np.ndarray
    reflections: list[Reflection]
    radiation: Radiation
    zero: float = 0.0
    displacement: float = 0.0
    #: ``{path: (value, esd)}`` of every number refined, rietx's paths
    refined: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    #: ``"pawley"`` or ``"lebail"``: how the intensities were found
    method: str = "pawley"
    #: the set after the fit, for the next run to start from
    parameters: object = None
    #: the Rwp of the Le Bail pass a Pawley fit started from, or None
    lebail_rwp: float | None = None
    #: rietx's diagnostics as ``(code, level, message)``: ``notes`` has
    #: their messages, and these are what groups a hundred of one kind
    #: into a line (``xtal.modules.powder.pawley_note_lines``)
    diagnostics: list = field(default_factory=list)

    @property
    def converged(self) -> bool:
        return self.status in ("converged", EVALUATED)

    @property
    def stalled(self) -> bool:
        """A Pawley fit that ended clearly worse than the Le Bail pass
        before it: stopped with its lines misplaced, whatever rietx's
        status says."""
        return self.lebail_rwp is not None and \
            self.rwp > STALLED_RATIO * self.lebail_rwp

    @property
    def stalled_note(self) -> str:
        """What to say of a stalled fit, or ``""``."""
        if not self.stalled:
            return ""
        return (f"Pawley ended at Rwp {100 * self.rwp:.2f} %, worse than "
                f"the {100 * self.lebail_rwp:.2f} % of the Le Bail fit "
                f"it started from: it stalled with its lines misplaced, "
                f"and its cell is not to be trusted.  Fit this cell by "
                f"Le Bail instead")

    @property
    def evaluated(self) -> bool:
        return self.status == EVALUATED

    @property
    def method_name(self) -> str:
        return METHODS.get(self.method, self.method)

    @property
    def volume(self) -> float:
        from xtal.core.lattice import Lattice

        return float(Lattice.from_parameters(*self.cell).volume)

    @property
    def ticks(self) -> np.ndarray:
        return np.array([r.two_theta for r in self.reflections])


def parse_cell(text) -> tuple[float, float, float, float, float, float]:
    """``"a b c"`` (angles 90) or ``"a b c alpha beta gamma"``."""
    words = str(text or "").replace(",", " ").split()
    try:
        numbers = [float(w) for w in words]
    except ValueError:
        raise PowderError(
            f"{text!r} is not a cell -- three lengths, or three lengths "
            f"and three angles") from None
    if len(numbers) == 3:
        numbers += [90.0, 90.0, 90.0]
    if len(numbers) != 6:
        raise PowderError(
            f"a cell is three lengths, or three lengths and three "
            f"angles; {len(numbers)} numbers were given")
    if min(numbers[:3]) <= 0 or not all(0 < v < 180 for v in numbers[3:]):
        raise PowderError(f"{text!r} is not a cell")
    return tuple(numbers)


def parse_hold(text) -> tuple[str, ...]:
    """Cell numbers to hold: ``"a, beta"``, or ``"cell"`` for all six.

    The Greek letters are read too, as the form writes them.
    """
    from xtal.powder.cell import NAMES

    greek = {"α": "alpha", "β": "beta", "γ": "gamma"}
    words = str(text or "").replace(",", " ").split()
    out = []
    for word in words:
        word = greek.get(word, word.lower())
        if word in ("cell", "all"):
            return NAMES
        if word not in NAMES:
            raise PowderError(f"{word!r} is not a cell number -- a b c "
                              f"alpha beta gamma, or cell")
        out.append(word)
    return tuple(out)


def pawley(data: PowderData, radiation: Radiation, cell, space_group: str,
           options: PawleyOptions | None = None, *, parameters=None,
           cancel=None, folder=None) -> PawleyFit:
    """Fit ``cell`` (six numbers, or text :func:`parse_cell` reads) in
    ``space_group`` to ``data``.

    ``parameters`` is the :class:`~xtal.powder.parameters.ParameterSet`
    to start from, whose flags say what is refined; ``None`` starts
    from rietx's preset with the boxes of ``options`` as the flags.
    The background has as many terms as ``options`` asks either way.

    ``cancel`` is a job's :class:`~xtal.modules.job.Cancellation`;
    Stop raises :class:`~xtal.powder.data.PowderStopped`, because half
    a Pawley fit is not a cell anybody should apply.
    """
    from xtal.powder import bridge

    options = options or PawleyOptions()
    if options.method not in METHODS:
        raise PowderError(f"{options.method!r} is not a method -- "
                          f"{' or '.join(METHODS)}")
    window = data.window(options.start or None, options.finish or None)
    symbol = bridge.space_group_named(space_group)
    if not isinstance(cell, str):
        cell = " ".join(str(float(v)) for v in cell)
    start = bridge.start_from(parameters, options, radiation, window)
    given = parse_cell(cell)
    common = dict(hold_cell=options.hold_cell,
                  cancel=bridge.cancel_token(cancel),
                  iterations=options.max_iterations,
                  tolerance=options.tolerance,
                  cell_range=options.cell_range or None,
                  bounds_about=given)
    lebail_rwp = None
    begin = given
    if options.method == "pawley" and options.lebail_first \
            and options.max_iterations != 0:
        first, found, start = bridge.pawley(
            window, radiation, given, symbol, start=start,
            folder=None if folder is None else Path(folder) / "lebail",
            mode="lebail", **common)
        lebail_rwp = float(found.statistics.rwp)
        begin = tuple(float(getattr(first.structure.phases[0].cell,
                                    n).value)
                      for n in ("a", "b", "c", "alpha", "beta", "gamma"))
    refinement, result, after = bridge.pawley(
        window, radiation, begin, symbol, start=start, folder=folder,
        mode=options.method, **common)
    evaluated = options.max_iterations == 0
    refined = refinement.structure.phases[0].cell
    names = ("a", "b", "c", "alpha", "beta", "gamma")
    values = {p.path: p for p in result.parameters}

    def instrument_value(path):
        found = values.get(path)
        return float(found.value) if found is not None else 0.0

    stats = result.statistics
    fitted = PawleyFit(
        cell=tuple(float(getattr(refined, n).value) for n in names),
        cell_esd=tuple(0.0 if evaluated
                       else float(getattr(refined, n).stderr or 0.0)
                       for n in names),
        space_group=symbol, rwp=float(stats.rwp), rp=float(stats.rp),
        rexp=float(stats.rexp), gof=float(stats.gof),
        status=EVALUATED if evaluated else str(result.status),
        two_theta=np.asarray(result.two_theta),
        y_obs=np.asarray(result.y_obs), y_calc=np.asarray(result.y_calc),
        y_background=np.asarray(result.y_background),
        reflections=[Reflection(*row)
                     for row in bridge.reflections(refinement)],
        radiation=radiation,
        zero=instrument_value("instrument.zero_shift"),
        displacement=instrument_value(
            "instrument.geometry.sample_displacement"),
        refined={} if evaluated else bridge.refined_values(result),
        notes=[d.message for d in result.diagnostics],
        diagnostics=[(str(d.code), str(d.level), d.message)
                     for d in result.diagnostics],
        method=options.method, parameters=after, lebail_rwp=lebail_rwp)
    if lebail_rwp is not None:
        fitted.notes.insert(0, f"started from a Le Bail fit over the same "
                               f"plan, Rwp {100 * lebail_rwp:.2f} %")
    if fitted.stalled:
        fitted.notes.insert(0, fitted.stalled_note)
    return fitted


def start_lines(cell, space_group: str, radiation: Radiation,
                lo: float, hi: float) -> list[Reflection]:
    """The reflections the typed start allows between ``lo`` and
    ``hi``, at the primary line, before any fit: what a person checks
    a start against.  Pawley alone finds a cell only from about 0.1 %
    off, and drawn only after the fit, a wrong start cost minutes to
    discover.  Multiplicity 0 and intensity NaN: nothing has fitted
    them.  ``cell`` is six numbers or text :func:`parse_cell` reads.
    """
    from xtal.powder import bridge

    if isinstance(cell, str):
        cell = parse_cell(cell)
    symbol = bridge.space_group_named(space_group)
    return [Reflection(hkl, d, two_theta, 0, float("nan"))
            for hkl, d, two_theta in bridge.cell_reflections(
                cell, symbol, radiation, lo, hi)]


@dataclass(frozen=True)
class StartOffset:
    """How far the peaks in use are from a start's lines, in 2θ.

    ``median`` and ``worst`` are each peak's distance to its nearest
    line; ``width`` the peaks' median FWHM.  ``far`` is the worst
    beyond a peak width: a line that far off sits on another peak's
    flank, and the fit may not walk it back.
    """

    median: float
    worst: float
    width: float
    peaks: int

    @property
    def far(self) -> bool:
        return self.worst > self.width


def start_offset(peaks, lines) -> StartOffset | None:
    """:class:`StartOffset` of ``peaks`` (a
    :class:`~xtal.powder.peaks.PeakFit`, the lines in use) from
    ``lines`` (:func:`start_lines`); ``None`` with either empty.

    A line is matched at every emission line the peaks were fitted
    with, not the primary alone: rietx leaves some Kα2 shoulders in use
    as peaks of their own, and rutile's at 62.93° is 0.17° -- five
    widths -- from the nearest Kα1 line of the very cell it came from.
    """
    used = [p for p in peaks.peaks if p.use]
    waves = [float(w) for w, _weight in (peaks.emission or ())] \
        or [float(peaks.wavelength)]
    d = np.array([float(r.d) for r in lines])
    at = np.sort(np.concatenate([
        2.0 * np.degrees(np.arcsin(np.clip(w / (2.0 * d), 0.0, 1.0)))
        for w in waves])) if d.size else d
    if not used or not at.size:
        return None
    x = np.array([p.two_theta for p in used])
    k = np.clip(np.searchsorted(at, x), 1, at.size - 1) if at.size > 1 \
        else np.zeros(x.size, dtype=int)
    near = np.abs(x - at[k])
    if at.size > 1:
        near = np.minimum(near, np.abs(x - at[k - 1]))
    widths = [p.fwhm for p in used if p.fwhm > 0]
    return StartOffset(median=float(np.median(near)),
                       worst=float(near.max()),
                       width=float(np.median(widths)) if widths
                       else float("inf"),
                       peaks=len(used))


def cell_fits_structure(fit: PawleyFit, structure, *,
                        length: float = 0.05, angle: float = 2.0) -> str:
    """Why this cell cannot go onto ``structure``, or ``""`` if it can.

    Putting a cell on a structure keeps its fractional coordinates, so
    it is only meaningful for the *same lattice in the same setting*:
    the same crystal system and centring, and every length and angle
    within a few percent of what the structure has (``length``, a
    fraction, and ``angle``, degrees).  A cell indexed
    with its axes in another order passes every figure of merit and
    would shear the structure into nonsense.
    """
    import gemmi

    fitted = gemmi.find_spacegroup_by_name(fit.space_group)
    group = structure.space_group
    theirs = gemmi.find_spacegroup_by_ops(gemmi.symops_from_hall(
        group.hall))
    if fitted is None or theirs is None:
        return "the space groups cannot be compared"
    if fitted.crystal_system_str() != theirs.crystal_system_str():
        return (f"the fit is {fitted.crystal_system_str()} and the "
                f"structure {theirs.crystal_system_str()}")
    if fitted.centring_type() != theirs.centring_type():
        return (f"the fit is {fitted.centring_type()}-centred and the "
                f"structure {theirs.centring_type()}-centred")
    own = [float(v) for v in structure.lattice.parameters]
    for name, new, old in zip("abc", fit.cell[:3], own[:3], strict=True):
        if abs(new - old) > length * old:
            return (f"{name} is {new:.3f} Å in the fit and {old:.3f} Å "
                    f"in the structure -- another setting, or another "
                    f"cell")
    for name, new, old in zip(("α", "β", "γ"), fit.cell[3:], own[3:],
                              strict=True):
        if abs(new - old) > angle:
            return (f"{name} is {new:.2f}° in the fit and {old:.2f}° in "
                    f"the structure")
    return ""
