"""
xtal.powder.pawley
==================
Pawley: one cell and space group fitted to the whole pattern, every
reflection's intensity a free number -- TOPAS's ``c_paw`` step, and
the test a cell from indexing has to pass before a structure is put
in it.

RietX fits (``mode="pawley"`` over its Le Bail scaffold); what is
decided here is what a person sets -- the range, the background's
order, which of zero, displacement, cell and the sample's size and
strain broadening are free -- and what the answer is: the R-factors,
the refined cell with its esds, and the reflection list.

**The cell's esds are RietX's and nothing wider.**  A Bragg-Brentano
cell also carries a systematic error of order 1e-4 that no esd
reports (RietX's own ``INDEX_CELL_SYSTEMATIC_UNQUANTIFIED``); the
fit's notes say so when RietX does.

**Nothing here touches a structure.**  Putting the refined cell onto
an open structure, or starting a structure from it, is the window's
-- one undoable edit through the Document -- and
:func:`cell_fits_structure` is the question it asks first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.powder.data import PowderData, PowderError, Radiation

__all__ = ["PawleyFit", "PawleyOptions", "Reflection",
           "cell_fits_structure", "parse_cell", "parse_hold", "pawley"]


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
    refine -- TOPAS's ``a 4.59`` beside ``b @ 9.23``.
    """

    start: float | None = None
    finish: float | None = None
    background_terms: int = 8
    zero: bool = False
    displacement: bool = True
    hold_cell: tuple[str, ...] = ()
    size: bool = True
    strain: bool = True

    def free(self, radiation: Radiation) -> tuple[str, ...]:
        """The RietX groups freed, in the bridge's words.

        A capillary has no specimen displacement to refine, so it is
        not freed for a synchrotron whatever the box says.
        """
        out = []
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
    #: ``{path: (value, esd)}`` of every number refined, RietX's paths
    refined: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def converged(self) -> bool:
        return self.status == "converged"

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
           options: PawleyOptions | None = None, *, cancel=None,
           folder=None) -> PawleyFit:
    """Fit ``cell`` (six numbers, or text :func:`parse_cell` reads) in
    ``space_group`` to ``data``.

    ``cancel`` is a job's :class:`~xtal.modules.job.Cancellation`;
    Stop raises :class:`~xtal.powder.data.PowderStopped`, because half
    a Pawley fit is not a cell anybody should apply.
    """
    from xtal.powder import bridge

    options = options or PawleyOptions()
    window = data.window(options.start or None, options.finish or None)
    symbol = bridge.space_group_named(space_group)
    if not isinstance(cell, str):
        cell = " ".join(str(float(v)) for v in cell)
    refinement, result = bridge.pawley(
        window, radiation, parse_cell(cell), symbol,
        background_terms=options.background_terms,
        free=options.free(radiation), hold_cell=options.hold_cell,
        folder=folder,
        cancel=bridge.cancel_token(cancel))
    refined = refinement.structure.phases[0].cell
    names = ("a", "b", "c", "alpha", "beta", "gamma")
    values = {p.path: p for p in result.parameters}

    def instrument_value(path):
        found = values.get(path)
        return float(found.value) if found is not None else 0.0

    stats = result.statistics
    return PawleyFit(
        cell=tuple(float(getattr(refined, n).value) for n in names),
        cell_esd=tuple(float(getattr(refined, n).stderr or 0.0)
                       for n in names),
        space_group=symbol, rwp=float(stats.rwp), rp=float(stats.rp),
        rexp=float(stats.rexp), gof=float(stats.gof),
        status=str(result.status),
        two_theta=np.asarray(result.two_theta),
        y_obs=np.asarray(result.y_obs), y_calc=np.asarray(result.y_calc),
        y_background=np.asarray(result.y_background),
        reflections=[Reflection(*row)
                     for row in bridge.reflections(refinement)],
        radiation=radiation,
        zero=instrument_value("instrument.zero_shift"),
        displacement=instrument_value(
            "instrument.geometry.sample_displacement"),
        refined=bridge.refined_values(result),
        notes=[d.message for d in result.diagnostics])


def cell_fits_structure(fit: PawleyFit, structure) -> str:
    """Why this cell cannot go onto ``structure``, or ``""`` if it can.

    Putting a cell on a structure keeps its fractional coordinates, so
    it is only meaningful for the *same lattice in the same setting*:
    the same crystal system and centring, and every length and angle
    within a few percent of what the structure has.  A cell indexed
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
        if abs(new - old) > 0.05 * old:
            return (f"{name} is {new:.3f} Å in the fit and {old:.3f} Å "
                    f"in the structure -- another setting, or another "
                    f"cell")
    for name, new, old in zip(("α", "β", "γ"), fit.cell[3:], own[3:],
                              strict=True):
        if abs(new - old) > 2.0:
            return (f"{name} is {new:.2f}° in the fit and {old:.2f}° in "
                    f"the structure")
    return ""
