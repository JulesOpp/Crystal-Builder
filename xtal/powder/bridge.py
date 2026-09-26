"""
xtal.powder.bridge
==================
The one module that imports RietX.

Everything that crosses between this application and RietX crosses
here: a :class:`~xtal.core.structure.Structure` becomes a RietX phase
and a refined phase comes back onto the same sites, a
:class:`~xtal.powder.data.Radiation` becomes one of RietX's instrument
presets, and a :class:`~xtal.powder.data.PowderData` becomes its
pattern.  The rest of :mod:`xtal.powder` imports this lazily, inside
the functions that need it, so that importing the package costs
nothing on a machine without the ``refine`` extra.

**A phase is built from the sites, not from a CIF.**  Writing a CIF
and reading it back through ``Structure.from_cif`` would work, and it
would also hand the order of the atoms to two parsers.  Rietveld
writes a refined position back onto a site *by index*; if one of
those parsers dropped a site, merged two, or sorted them, every
position after that point would land on the wrong atom and the
structure would look refined.  So the atoms go across in the order of
``structure.sites``, dummies left out and remembered, and
:func:`apply_phase` puts them back by the same list.

**Nothing RietX writes lands in the working directory.**  A fit
records itself into ``./.rietx/runs`` unless it is told otherwise,
which in this application would be wherever the process was started
from -- the user's home, or inside the app bundle.  :func:`fit` is
the only way a fit is run from here, and it always says where
(a run folder) or that nowhere (``telemetry=False``).
"""

from __future__ import annotations

import math
from pathlib import Path

import gemmi
import numpy as np
import rietx as rx

from xtal.core import elements as el
from xtal.powder.data import (
    PowderData,
    PowderError,
    PowderStopped,
    Radiation,
)

__all__ = ["RIETVELD_PRESETS", "PatternTerm", "apply_phase",
           "cancel_token", "extinction_classes", "fit", "free_cell_paths",
           "index_pattern", "instrument", "lattice_lines", "pattern",
           "observed_peak", "pattern_term", "pawley", "peak_list",
           "phase_of", "plan_notes", "predict", "reflections",
           "refined_values", "rietveld", "rietveld_plan",
           "space_group_named", "space_group_symbol", "to_rietx"]

#: B = 8π²U.  RietX refines B, as TOPAS does; a CIF and this
#: application's sites carry U.
_B_PER_U = 8.0 * math.pi ** 2

#: The B RietX gives a site when nothing better is known.  A site with
#: no displacement parameter is not at absolute zero; 0.5 A^2 is
#: RietX's own default and a typical room-temperature value for a
#: framework atom.
DEFAULT_BISO = 0.5


# ======================================================================
#  STRUCTURE
# ======================================================================

def space_group_symbol(structure) -> str:
    """The extended Hermann-Mauguin symbol RietX resolves the group by.

    From the operations rather than from ``hm``, because the short
    symbol does not say which origin or which axes: ``P 4/n m m`` is
    two different sets of positions, and RietX reads the bare symbol
    as the first.  gemmi names the setting the operations actually are
    (``P 4/n m m:2``), which is what RietX's own ``get_spacegroup``
    looks up.
    """
    group = structure.space_group
    found = gemmi.find_spacegroup_by_ops(
        gemmi.symops_from_hall(group.hall))
    if found is None:
        raise PowderError(
            f"{group.hm} in this setting is not one RietX can name -- "
            f"Symmetry > Standardize first")
    return found.xhm()


def phase_of(structure, name: str = "") -> tuple[rx.Phase, list[int]]:
    """``(phase, site_indices)``: the structure as one RietX phase.

    ``site_indices[k]`` is the site the phase's ``k``-th atom came
    from.  Dummy atoms are markers, not scatterers, and are left out
    -- the list is how their absence is remembered, so nothing is
    written back onto them.
    """
    lattice = structure.lattice
    a, b, c, alpha, beta, gamma = (float(v) for v in lattice.parameters)
    cell = rx.Cell(a=rx.Parameter(value=a), b=rx.Parameter(value=b),
                   c=rx.Parameter(value=c),
                   alpha=rx.Parameter(value=alpha),
                   beta=rx.Parameter(value=beta),
                   gamma=rx.Parameter(value=gamma))
    atoms: list[rx.Atom] = []
    indices: list[int] = []
    taken: set[str] = set()
    for index, site in enumerate(structure.sites):
        if el.is_dummy(site.element):
            continue
        label = site.label or f"{site.element}{index + 1}"
        if label in taken:
            # RietX addresses atoms by label in its parameter paths,
            # so two sites called O1 would be one parameter.
            label = f"{label}_{index + 1}"
        taken.add(label)
        u = site.u_equivalent
        biso = DEFAULT_BISO if not u else float(u) * _B_PER_U
        x, y, z = (float(v) for v in site.frac)
        atoms.append(rx.Atom(
            label=label, species=site.element,
            x=rx.Parameter(value=x), y=rx.Parameter(value=y),
            z=rx.Parameter(value=z),
            occ=rx.Parameter(value=float(site.occupancy), min=0.0,
                             max=1.5),
            biso=rx.Parameter(value=biso, min=0.0, max=25.0)))
        indices.append(index)
    if not atoms:
        raise PowderError(
            "there are no atoms to refine -- a cell and a space group "
            "place the peaks, but Rietveld needs what scatters")
    phase = rx.Phase(
        name=name or structure.meta.get("title", "") or "phase",
        space_group=space_group_symbol(structure), cell=cell,
        atoms=atoms)
    return phase, indices


def to_rietx(structure, name: str = "") -> tuple[rx.Structure, list[int]]:
    """The structure as a one-phase RietX structure, and its index map."""
    phase, indices = phase_of(structure, name)
    return rx.Structure(phases=[phase]), indices


def apply_phase(structure, phase: rx.Phase, indices: list[int]):
    """A copy of ``structure`` carrying a refined phase's numbers.

    The cell, and on every site the phase came from its position,
    occupancy and displacement.  **The sites themselves are never
    added, removed or reordered, and the bonds are carried untouched**
    -- a refinement moves atoms; what they are and what they are
    bonded to is the user's.  A phase with a different number of
    atoms from the map is refused rather than written partway.
    """
    from xtal.core.lattice import Lattice

    if len(phase.atoms) != len(indices):
        raise PowderError(
            f"the refined phase has {len(phase.atoms)} atoms and the "
            f"structure gave {len(indices)}")
    out = structure.copy()
    cell = phase.cell
    out.set_lattice(Lattice.from_parameters(
        cell.a.value, cell.b.value, cell.c.value,
        cell.alpha.value, cell.beta.value, cell.gamma.value))
    for atom, index in zip(phase.atoms, indices, strict=True):
        site = out.sites[index]
        out.set_frac(index, np.array(
            [atom.x.value, atom.y.value, atom.z.value], dtype=float))
        site.occupancy = float(atom.occ.value)
        if site.u_aniso is None:
            site.u_iso = float(atom.biso.value) / _B_PER_U
    return out


# ======================================================================
#  INSTRUMENT AND PATTERN
# ======================================================================

def instrument(radiation: Radiation) -> rx.Instrument:
    """RietX's preset for this radiation.

    A laboratory tube is flat-plate Bragg-Brentano with its Kα doublet
    (or Kα1 alone); a synchrotron is a capillary at the one
    wavelength given.  The wavelengths, the Kα2/Kα1 ratio and the
    polarisation are the preset's, which is the point of using one.
    """
    if radiation.is_synchrotron:
        return rx.Instrument.debye_scherrer(float(radiation.wavelength))
    return rx.Instrument.bragg_brentano(
        radiation=radiation.preset,
        monochromator_two_theta=radiation.monochromator_two_theta)


def pattern(data: PowderData) -> rx.PatternData:
    return rx.PatternData(
        two_theta=data.two_theta.tolist(),
        intensity=data.intensity.tolist(),
        sigma=None if data.sigma is None else data.sigma.tolist())


# ======================================================================
#  RUNNING
# ======================================================================

def fit(refinement: rx.Refinement, data: PowderData, *,
        folder: Path | None = None, **kwargs):
    """``refinement.fit``, with its recording sent to ``folder``.

    ``folder`` is a run folder, and RietX's run record goes into a
    ``rietx`` directory inside it; ``None`` records nothing.  Either
    way nothing is written under the working directory, which is where
    RietX writes when it is not told.
    """
    kwargs.pop("telemetry", None)
    telemetry = False if folder is None else str(Path(folder) / "rietx")
    try:
        return refinement.fit(pattern(data), telemetry=telemetry,
                              **kwargs)
    except rx.RefinementCancelled:
        raise PowderStopped("stopped") from None


def predict(structure, radiation: Radiation, two_theta) -> np.ndarray:
    """The pattern RietX calculates for a structure, unrefined.

    Scale, background and profile are the preset's defaults, so the
    numbers are a shape and not counts; it is what the tests simulate
    a "measured" pattern from, and what a structure looks like before
    a fit has touched it.
    """
    rx_structure, _indices = to_rietx(structure)
    refinement = rx.Refinement(rx_structure, instrument(radiation),
                               history=False)
    return np.asarray(refinement.predict(np.asarray(two_theta,
                                                    dtype=float)))


# ======================================================================
#  PEAKS
# ======================================================================

def emission_lines(radiation: Radiation) -> list[tuple[float, float]]:
    """``[(wavelength, weight), ...]``, the primary line first at 1."""
    lines = instrument(radiation).source.lines
    out = [(float(line.wavelength.value), float(line.weight.value))
           for line in lines]
    out[0] = (out[0][0], 1.0)
    return out


def pick_peaks(data: PowderData, radiation: Radiation, *,
               shoulders: bool = True, flag_ghosts: bool = False):
    """``(peak_list, grid, envelope)``: RietX's peak search.

    ``grid`` and ``envelope`` are the 2θ points detection kept and the
    background it drew under them, which is what a fitted line is
    measured from.
    """
    from rietx.indexing import pick

    native, det, _fits = pick.pick_peaks_with_state(
        pattern(data), instrument(radiation), shoulders=shoulders,
        flag_contamination=flag_ghosts)
    return native, np.asarray(det.two_theta), np.asarray(det.envelope)


def observed_peak(two_theta: float, two_theta_esd: float, area: float,
                  area_esd: float, fwhm: float, eta: float,
                  wavelength: float, *, group: int = 0, flags=(),
                  origin: str = "fitted", chi2_red: float = 1.0):
    """One line as RietX's indexing engines read it.

    For a line this application fitted or a person placed, rather than
    one RietX's detector found.  ``q`` is 1/d^2 and its esd follows
    from the position's; a line with no esd yet (placed, not fitted)
    is given 0.01 deg and flagged ``sigma_assumed``, RietX's own word
    for that.
    """
    from rietx.schemas.indexing import ObservedPeak

    flags = list(flags)
    if not (two_theta_esd > 0 and np.isfinite(two_theta_esd)):
        two_theta_esd = 0.01
        flags.append("sigma_assumed")
    theta = np.radians(two_theta / 2.0)
    q = (2.0 * np.sin(theta) / wavelength) ** 2
    dq = 2.0 * np.sin(2.0 * theta) / wavelength ** 2 * np.radians(1.0)
    return ObservedPeak(
        two_theta=float(two_theta), two_theta_esd=float(two_theta_esd),
        intensity=float(area),
        intensity_esd=float(area_esd) if np.isfinite(area_esd) else 0.0,
        q=float(q), q_esd=float(abs(dq) * two_theta_esd),
        fwhm=float(fwhm), eta=float(eta), group=int(group),
        n_in_group=1, chi2_red=float(chi2_red), flags=flags,
        origin=origin)


def peak_list(lines, wavelength: float, two_theta_min: float,
              two_theta_max: float):
    """RietX's peak list from lines made by :func:`observed_peak`."""
    from rietx.schemas.indexing import PeakList

    return PeakList(peaks=list(lines), wavelength=float(wavelength),
                    two_theta_min=float(two_theta_min),
                    two_theta_max=float(two_theta_max),
                    source="positions", diagnostics=[])


def fit_peaks_at(data: PowderData, radiation: Radiation, positions):
    """``(peak_list, grid, envelope)`` for lines at named positions."""
    from rietx.indexing import pick

    rx_pattern, rx_instrument = pattern(data), instrument(radiation)
    try:
        native = pick.fit_peaks(rx_pattern, rx_instrument,
                                list(positions))
    except ValueError as exc:
        raise PowderError(str(exc)) from None
    det = pick.detect_peaks(rx_pattern, rx_instrument)
    return native, np.asarray(det.two_theta), np.asarray(det.envelope)


# ======================================================================
#  INDEXING
# ======================================================================

def cancel_token(cancellation=None) -> rx.CancelToken:
    """RietX's token, set when ``cancellation`` is.

    RietX reads its own token between units of work; the job's
    :class:`~xtal.modules.job.Cancellation` is what Stop sets.  Linking
    the two rather than handing RietX ours keeps the question of what
    a token must answer (``bool``, ``is_set``) upstream's.
    """
    token = rx.CancelToken()
    if cancellation is not None:
        cancellation.when_cancelled(token.cancel)
    return token


def index_pattern(peak_list, data: PowderData, radiation: Radiation, *,
                  systems, centrings, shift_allowance: float = 0.0,
                  max_volume: float | None = None,
                  max_axis: float = 25.0, budget: float = 60.0,
                  prior_space_groups=(), cancel=None, on_stage=None):
    """RietX's cell search over the lattices named.

    ``systems`` and ``centrings`` are RietX's own words (``"tetragonal"``,
    ``{"tetragonal": ("P",)}``).  ``budget`` is the whole run's ceiling,
    search and validation together; 0 is none at all -- RietX's
    ``full`` preset, since leaving its ceiling unset hands the run to
    its ``quick`` preset's two minutes instead.
    ``on_stage(label, index, total)`` is called as each unit of search
    or validation starts.
    """
    from rietx.indexing import SearchSpec

    spec = SearchSpec(
        systems=tuple(systems), centrings=dict(centrings),
        shift_allowance_deg=float(shift_allowance),
        max_volume=max_volume, max_d_axis=float(max_axis),
        total_budget_seconds=float(budget) if budget else None,
        prior_spacegroups=tuple(prior_space_groups))

    def events(event):
        kind = event.get("kind")
        body = event.get("data", {})
        if on_stage is None:
            return
        if kind == "stage_start":
            on_stage(str(body.get("stage", "")),
                     int(body.get("index", 0)),
                     int(body.get("n_stages", 0)))
        elif kind == "stage_end" and body.get("validation"):
            # After the last validation RietX sweeps the leading cells
            # for sub- and supercells, announcing nothing and reading
            # the clock only between cells: 9 s past a 60 s budget on
            # a MOF pattern, with the last validation still on screen.
            # Until another stage starts, that sweep is what is running.
            on_stage("ambiguity:", int(body.get("index", 0)),
                     int(body.get("n_stages", 0)))

    lo, hi = data.range
    # A candidate whose covariance is singular (a line list short of
    # the metric's freedoms) fills its esds with NaN, and says so in
    # its own diagnostics; numpy's warning about it says nothing more.
    with np.errstate(invalid="ignore"):
        return rx.index_pattern(
            peak_list, data=pattern(data),
            instrument=instrument(radiation), spec=spec,
            preset=None if budget else "full",
            two_theta_limits=(lo, hi), events=events, cancel=cancel)


def extinction_classes(peak_list, data: PowderData, radiation: Radiation,
                       candidate, cancel=None):
    """RietX's ranking of the extinction classes a cell admits."""
    lo, hi = data.range
    return rx.determine_extinction_symbol(
        pattern(data), candidate, instrument(radiation),
        peaks=peak_list, two_theta_limits=(lo, hi), cancel=cancel)


def lattice_lines(cell, system: str, centring: str, wavelength: float,
                  two_theta_min: float, two_theta_max: float):
    """``(hkl, two_theta)``: every line a lattice allows in a range.

    One entry per distinct line, not per orbit -- what a person
    compares against the peaks to judge a cell by eye.
    """
    from rietx.indexing.fom import predicted_lines

    hkl, q = predicted_lines(tuple(float(v) for v in cell), system,
                             centring, float(wavelength),
                             float(two_theta_max), float(two_theta_min))
    s = np.clip(float(wavelength) * np.sqrt(np.asarray(q)) / 2.0,
                0.0, 1.0)
    return np.asarray(hkl), 2.0 * np.degrees(np.arcsin(s))


# ======================================================================
#  PAWLEY
# ======================================================================

#: What each Pawley option frees, as RietX's parameter globs.  The
#: profile's Caglioti and Lorentzian terms are always free: a Pawley
#: fit that could not fit the widths would put every misfit into the
#: intensities.
_PAWLEY_FREES = {
    "zero": ["instrument.zero_shift"],
    "displacement": ["instrument.geometry.sample_displacement"],
    "cell": [],                 # free_cell_paths: one by one
    "size": ["phases.*.lor_size", "phases.*.gauss_size"],
    "strain": ["phases.*.lor_strain", "phases.*.gauss_strain"],
}


def _with_background(radiation: Radiation, terms: int) -> rx.Instrument:
    return instrument(radiation).model_copy(update={
        "background": rx.BackgroundChebyshev.with_terms(
            max(int(terms), 1))})


def free_cell_paths(refinement, hold=()) -> list[str]:
    """The cell numbers RietX lets move, less the ones held.

    Asked of RietX's own table rather than of the group, so that what
    is freed is exactly what it ties: ``b`` on a tetragonal cell is
    RietX's to follow ``a``, and naming it here would be refused.
    """
    hold = set(hold)
    return [row.path for row in refinement.parameters()
            if ".cell." in row.path and not row.locked
            and row.tie is None and row.path.rsplit(".", 1)[1] not in hold]


def refined_values(result) -> dict[str, tuple[float, float]]:
    """``{path: (value, esd)}`` of every number a fit refined."""
    return {p.path: (float(p.value), float(p.stderr or 0.0))
            for p in result.parameters}


def pawley(data: PowderData, radiation: Radiation, cell, space_group: str,
           *, background_terms: int = 8, free=("zero", "cell"),
           hold_cell=(), folder: Path | None = None, cancel=None,
           mode: str = "pawley"):
    """``(refinement, result)``: a Pawley fit of one cell to ``data``,
    or with ``mode="lebail"`` a Le Bail fit over the same plan.

    The phase is RietX's own Le Bail scaffold -- a cell, a group and a
    dummy atom it never refines -- and the plan is its
    ``pawley_default`` order (background, positions, widths), with
    each stage present only when what it frees was asked for.
    ``hold_cell`` names cell numbers (``"a"``, ``"beta"``) held at the
    value given while the rest of the cell refines.
    """
    from rietx.schemas.structure import lebail_scaffold

    free = set(free)
    unknown = free - set(_PAWLEY_FREES)
    if unknown:
        raise PowderError(f"cannot free {', '.join(sorted(unknown))}")
    structure = lebail_scaffold(space_group, tuple(cell), name="pawley")
    ins = _with_background(radiation, background_terms)
    refinement = rx.Refinement(structure, ins, history=False)
    positions = [path for key in ("zero", "displacement")
                 if key in free for path in _PAWLEY_FREES[key]]
    stages = [rx.Stage("bkg", ["instrument.background.*"])]
    if positions:
        stages.append(rx.Stage("zero", positions))
    cell_paths = free_cell_paths(refinement, hold_cell) \
        if "cell" in free else []
    if cell_paths:
        stages.append(rx.Stage("cell", cell_paths))
    stages.append(rx.Stage("profile_w", ["instrument.profile.w"]))
    stages.append(rx.Stage("profile", [
        "instrument.profile.u", "instrument.profile.v",
        "instrument.profile.x", "instrument.profile.y"]))
    sample = [path for key in ("size", "strain") if key in free
              for path in _PAWLEY_FREES[key]]
    if sample:
        stages.append(rx.Stage("sample_profile", sample))
    try:
        result = fit(refinement, data, folder=folder, mode=mode,
                     plan=rx.RefinementPlan(stages=stages),
                     cancel=cancel)
    except (ValueError, KeyError) as exc:
        raise PowderError(f"RietX refused the fit: {exc}") from None
    return refinement, result


def reflections(refinement):
    """``[(hkl, d, two_theta, multiplicity, intensity), ...]`` of the
    last fit, the primary emission line's only."""
    return [((row.h, row.k, row.l), float(row.d), float(row.two_theta),
             int(row.multiplicity), float(row.intensity))
            for row in refinement.reflection_table() if row.line == 0]


def space_group_named(name: str) -> str:
    """A typed space group as the extended symbol RietX resolves.

    ``C2221``, ``C 2 2 21`` and ``20`` all name one group; RietX looks
    groups up by gemmi's extended symbol, which also says the setting.
    """
    found = gemmi.find_spacegroup_by_name(str(name).strip())
    if found is None:
        raise PowderError(f"{name!r} is not a space group")
    return found.xhm()


# ======================================================================
#  RIETVELD
# ======================================================================

#: What each Rietveld box frees, as RietX's globs.  The cell is freed
#: number by number (:func:`free_cell_paths`), and the profile's
#: Caglioti terms go in two stages, W first, as McCusker orders them.
_RIETVELD_FREES = {
    "background": ["instrument.background.*"],
    "zero": ["instrument.zero_shift"],
    "displacement": ["instrument.geometry.sample_displacement"],
    "cell": [],
    "profile": ["instrument.profile.u", "instrument.profile.v",
                "instrument.profile.x", "instrument.profile.y"],
    "size": _PAWLEY_FREES["size"],
    "strain": _PAWLEY_FREES["strain"],
    "positions": ["phases.*.atoms.*.dof.*"],
    "biso": ["phases.*.atoms.*.biso", "phases.*.atoms.*.adp.*"],
    "occupancy": ["phases.*.atoms.*.occ"],
    "preferred_orientation": ["phases.*.preferred_orientation.r"],
}

#: RietX's own plans a person may pick instead of the boxes.  The
#: Pawley and Le Bail ones are left out: they free nothing a structure
#: has.
RIETVELD_PRESETS = ("mccusker_structural", "mccusker_default",
                    "lab_bragg_brentano", "lab_sample_refine")


def rietveld_plan(refinement, free, hold_cell=()) -> rx.RefinementPlan:
    """The boxes as a plan in McCusker's order: scale and background,
    the line positions, the cell, the widths, then the structure --
    coordinates, displacements, occupancies, texture last."""
    cell = free_cell_paths(refinement, hold_cell) if "cell" in free \
        else []
    return rx.RefinementPlan(stages=[
        rx.Stage(name, paths) for name, paths in _box_stages(free, cell)])


def _box_stages(free, cell) -> list[tuple[str, list[str]]]:
    """``[(stage, paths)]`` the boxes free, ``cell`` the cell's paths:
    the plan, and what its note names, from one list."""
    free = set(free)
    unknown = free - set(_RIETVELD_FREES)
    if unknown:
        raise PowderError(f"cannot free {', '.join(sorted(unknown))}")

    def paths(*keys):
        return [p for k in keys if k in free for p in _RIETVELD_FREES[k]]

    stages = [("scale_bkg", ["phases.*.scale", *paths("background")])]
    if paths("zero", "displacement"):
        stages.append(("zero_disp", paths("zero", "displacement")))
    if cell:
        stages.append(("cell", list(cell)))
    if "profile" in free:
        stages.append(("profile_w", ["instrument.profile.w"]))
        stages.append(("profile", paths("profile")))
    if paths("size", "strain"):
        stages.append(("sample_profile", paths("size", "strain")))
    for key in ("positions", "biso", "occupancy",
                "preferred_orientation"):
        if key in free:
            stages.append((key, paths(key)))
    return stages


#: A stage's name, as the plan's note says it.
_STAGE_WORDS = {
    "scale_bkg": "scale and background", "zero": "zero error",
    "zero_disp": "zero and specimen displacement",
    "disp": "specimen displacement", "cell": "cell",
    "profile_w": "peak width W", "profile": "peak shape U V X Y",
    "sample_profile": "size and strain",
    "lines_axial": "Kα2 ratio and axial divergence",
    "extra_components": "background humps",
    "coordinates": "atom positions", "positions": "atom positions",
    "biso": "displacement parameters", "occupancy": "occupancies",
    "preferred_orientation": "preferred orientation",
    "extinction": "extinction", "roughness": "surface roughness",
}

#: Stages that free something only where the model declares it, which
#: nothing this application builds does, except texture when an axis
#: is typed.
_DECLARED_ONLY = {"extra_components", "extinction", "roughness"}


def plan_notes(plan: str, free=()) -> str:
    """What a Rietveld plan does, in the order it does it.

    ``plan`` is one of :data:`RIETVELD_PRESETS`, described from RietX's
    own ``PLAN_INFO`` and its stages; empty is the plan the ``free``
    boxes make.  Whether the atoms move is said outright: two of
    RietX's four plans free none, which is easy to miss from a name.
    """
    if plan:
        preset = getattr(rx.RefinementPlan, plan)()
        names = [stage.name for stage in preset.stages]
        info = rx.PLAN_INFO[plan]
        head = f"{info.title}.  {info.description.replace('**', '')}"
        tail = info.when_to_use
    else:
        names = [name for name, _paths in _box_stages(
            free, ["cell"] if "cell" in set(free) else [])]
        head = "The boxes below, freed in McCusker's order."
        tail = ""
    shown = [n for n in names if n not in _DECLARED_ONLY
             and (n != "preferred_orientation" or not plan)]
    order = " → ".join(_STAGE_WORDS.get(n, n) for n in shown)
    moves = any(n in ("coordinates", "positions") for n in names)
    lines = [head, f"Stages: {order}.",
             "The atoms move." if moves else
             "The atoms stay where they are."]
    if plan == "lab_sample_refine":
        lines.append("No calibrated instrument is loaded here, so the "
                     "instrument's widths stay at RietX's defaults and "
                     "the size and strain absorb them.")
    if tail:
        lines.append(tail)
    return "\n".join(lines)


class _Frames:
    """RietX's ``eval`` events, turned into frames a person can watch.

    An event carries the free values and nothing drawn from them, so a
    second model of the same phase -- the shadow -- is set to those
    values and asked for its pattern.  Only accepted steps, and no more
    often than ``interval`` seconds or three times what the last frame
    cost, whichever is longer: a frame is 5 ms on rutile and 0.7 s on
    MFU-4l, so a fixed interval would double a framework's fit to
    watch it, and this caps watching at a quarter.
    """

    def __init__(self, shadow, grid, on_frame, interval: float):
        self.shadow, self.grid = shadow, grid
        # A coordinate is refined as a step along its site's allowed
        # directions from where the atom *is* (``dof``), so a shadow
        # handed the same step twice walks twice as far.  Every frame
        # puts the atoms back where the fit started them first.
        self.start = _fractions(shadow.structure.phases[0])
        self.on_frame, self.interval = on_frame, float(interval)
        self.paths: list[str] = []
        self.stage = ""
        self.last = -math.inf
        self.cost = 0.0

    def __call__(self, event) -> None:
        import time

        kind, body = event.get("kind"), event.get("data", {})
        if kind == "stage_start":
            self.paths = list(body.get("free_paths", ()))
            self.stage = str(body.get("stage", ""))
            return
        if kind != "eval" or not body.get("accepted"):
            return
        now = time.monotonic()
        if now - self.last < max(self.interval, 3.0 * self.cost):
            return
        values = body.get("values") or ()
        if len(values) != len(self.paths):
            return
        phase = self.shadow.structure.phases[0]
        for atom, (x, y, z) in zip(phase.atoms, self.start, strict=True):
            atom.x.value, atom.y.value, atom.z.value = x, y, z
        try:
            self.shadow.set_values({p: float(v) for p, v in
                                    zip(self.paths, values, strict=True)})
            y_calc = np.asarray(self.shadow.predict(self.grid))
        except (ValueError, KeyError):
            # a value a transform put on its bound: skip the frame,
            # the fit itself is not affected
            return
        self.last = time.monotonic()
        self.cost = self.last - now
        self.on_frame(self.stage, y_calc, _fractions(phase),
                      _cell_of(phase))


def _fractions(phase) -> np.ndarray:
    return np.array([[a.x.value, a.y.value, a.z.value]
                     for a in phase.atoms], dtype=float)


def _cell_of(phase) -> tuple[float, ...]:
    cell = phase.cell
    return tuple(float(getattr(cell, n).value) for n in
                 ("a", "b", "c", "alpha", "beta", "gamma"))


def rietveld(structure, data: PowderData, radiation: Radiation, *,
             free=(), hold_cell=(), plan: str = "",
             background_terms: int = 8, preferred_axis=None,
             on_frame=None, frame_interval: float = 0.2,
             folder: Path | None = None, cancel=None):
    """``(refinement, result, indices)``: a Rietveld fit of a structure.

    ``plan`` names one of :data:`RIETVELD_PRESETS`, or is empty for the
    plan the ``free`` boxes make.  ``preferred_axis`` is the
    March-Dollase direction as three integers, ``None`` for none.
    ``on_frame(stage, y_calc, fractions, cell)`` is called from the
    fitting thread as it goes; ``fractions`` is one row per atom of the
    phase, in the order of ``indices``.
    """
    def build():
        rx_structure, indices = to_rietx(structure)
        if preferred_axis is not None:
            rx_structure.phases[0].preferred_orientation = \
                rx.PreferredOrientation(axis=tuple(int(v) for v in
                                                   preferred_axis))
        return rx.Refinement(rx_structure,
                             _with_background(radiation, background_terms),
                             history=False), indices

    refinement, indices = build()
    if plan:
        if plan not in RIETVELD_PRESETS:
            raise PowderError(f"{plan!r} is not one of RietX's Rietveld "
                              f"plans")
        chosen = plan
    else:
        chosen = rietveld_plan(refinement, free, hold_cell)
    events = None
    if on_frame is not None:
        shadow, _same = build()
        events = _Frames(shadow, data.two_theta, on_frame, frame_interval)
    try:
        result = fit(refinement, data, folder=folder, mode="rietveld",
                     plan=chosen, events=events, cancel=cancel)
    except (ValueError, KeyError) as exc:
        raise PowderError(f"RietX refused the fit: {exc}") from None
    return refinement, result, indices


# ======================================================================
#  THE PATTERN AS A TERM
# ======================================================================

#: The paths a pattern term frees: every atom along the directions its
#: site allows.  A site's ``x``, ``y``, ``z`` are locked in RietX and
#: follow from these.
_TERM_ATOMS = "phases.*.atoms.*.dof.*"


class PatternTerm:
    """χ² of a fitted refinement as a function of its atoms, and of its
    cell when asked -- the pattern half of Rietveld with energies.

    RietX's solver takes no cost of anyone else's, so the minimiser
    here is ours and RietX is asked only for what it computes best:
    the weighted residual and its analytic Jacobian, from the model it
    compiles for a fit (``least_squares._make_residual`` and
    ``_jacobian_for``, which are private -- a test holds the gradient
    against central differences, and breaks if they change meaning).
    Everything else the refinement fitted -- scale, background, zero,
    the peak shape -- is held where it is.

    The variables are RietX's own vector ``theta`` over the free
    paths: a step along each allowed direction, in fractions, and the
    free cell numbers, in Å and degrees.  Both are identity transforms
    and every tie is linear, so the atoms' fractions and the cell are
    affine in ``theta`` and :attr:`frac_basis` and :attr:`cell_basis`
    are constant.  **The model is compiled once**, with its hkl list
    and peak windows frozen at the start, as RietX freezes them within
    a stage: good for the atoms, which move no line, and for a cell
    that moves a few hundredths of an Å.
    """

    def __init__(self, refinement: rx.Refinement, data: PowderData,
                 cell: bool = False, extra_parameters: int = 0):
        from rietx.model.forward import compile_model
        from rietx.optimize import least_squares
        from rietx.params.vector import ParameterTable

        table = ParameterTable(refinement.structure, refinement.instrument)
        table.set_vary(list(table.free_paths), False)
        table.set_vary([_TERM_ATOMS], True)
        if cell:
            table.set_vary(free_cell_paths(refinement, ()), True)
        self.paths = list(table.free_paths)
        if not self.paths:
            raise PowderError("no atom here may move: every site is on a "
                              "position its symmetry fixes")
        self._table = table
        self._model = compile_model(
            refinement.structure, refinement.instrument, pattern(data),
            mode="rietveld", moving_paths=set(table.moving_paths))
        self._residual = least_squares._make_residual(self._model, table)
        self._jacobian = least_squares._jacobian_for(self._model, table,
                                                     "numpy")
        self.theta0 = np.asarray(table.x0(), dtype=float)
        self.n_atoms = len(refinement.structure.phases[0].atoms)
        self.two_theta = np.asarray(self._model.tt, dtype=float)
        self.y_obs = np.asarray(self._model.y_obs, dtype=float)
        self._weight = 1.0 / np.asarray(self._model.sigma, dtype=float)
        self._parameters = len(self.paths) + int(extra_parameters)
        self.frac0, self.cell0 = self._decode(self.theta0)
        # affine, so one step per column is the whole derivative
        step = 1e-3
        self.frac_basis = np.zeros((len(self.paths), self.n_atoms, 3))
        self.cell_basis = np.zeros((len(self.paths), 6))
        for k in range(len(self.paths)):
            theta = self.theta0.copy()
            theta[k] += step
            frac, cells = self._decode(theta)
            self.frac_basis[k] = (frac - self.frac0) / step
            self.cell_basis[k] = (cells - self.cell0) / step
        self._at, self._value = None, None

    def _decode(self, theta) -> tuple[np.ndarray, np.ndarray]:
        values = self._table.decode(np.asarray(theta, dtype=float))
        frac = np.array([[values[f"phases.0.atoms.{k}.{axis}"]
                          for axis in "xyz"]
                         for k in range(self.n_atoms)], dtype=float)
        cells = np.array([values[f"phases.0.cell.{name}"] for name in
                          ("a", "b", "c", "alpha", "beta", "gamma")],
                         dtype=float)
        return frac, cells

    def fractions(self, theta) -> np.ndarray:
        """The phase's atoms at ``theta``, one row each."""
        step = np.asarray(theta, dtype=float) - self.theta0
        return self.frac0 + np.tensordot(step, self.frac_basis, axes=1)

    def cell(self, theta) -> np.ndarray:
        """``(a, b, c, alpha, beta, gamma)`` at ``theta``."""
        step = np.asarray(theta, dtype=float) - self.theta0
        return self.cell0 + step @ self.cell_basis

    def __call__(self, theta) -> tuple[float, np.ndarray]:
        """``(chi2, gradient)`` at ``theta``."""
        theta = np.asarray(theta, dtype=float)
        if self._at is None or not np.array_equal(theta, self._at):
            residual = np.asarray(self._residual(theta), dtype=float)
            jacobian = np.asarray(self._jacobian(theta), dtype=float)
            self._value = (float(residual @ residual),
                           2.0 * (jacobian.T @ residual))
            self._at = theta.copy()
        return self._value

    def y_calc(self, theta) -> np.ndarray:
        return np.asarray(self._model.evaluate(
            self._table.decode(np.asarray(theta, dtype=float))),
            dtype=float)

    def statistics(self, theta) -> dict[str, float]:
        """Rwp, Rp, Rexp and GoF at ``theta``, over the data alone."""
        y_calc = self.y_calc(theta)
        w = self._weight ** 2
        obs = self.y_obs
        chi2 = float(np.sum(w * (obs - y_calc) ** 2))
        scale = float(np.sum(w * obs ** 2))
        dof = max(len(obs) - self._parameters, 1)
        return {"rwp": math.sqrt(chi2 / scale) if scale else 0.0,
                "rp": float(np.sum(np.abs(obs - y_calc))
                            / max(float(np.sum(np.abs(obs))), 1e-300)),
                "rexp": math.sqrt(dof / scale) if scale else 0.0,
                "gof": math.sqrt(chi2 / dof)}


def pattern_term(structure, data: PowderData, radiation: Radiation, *,
                 free=(), background_terms: int = 8, preferred_axis=None,
                 cell: bool = False, folder: Path | None = None,
                 cancel=None):
    """``(term, result, indices, refinement)``: the pattern as a
    function of the atoms, after a Rietveld fit of everything else.

    The fit frees what ``free`` names -- the Rietveld step's boxes,
    less the atoms and the cell, which are the term's -- so the scale,
    background and peak shape are the pattern's before the atoms are
    asked to move.
    """
    held = {"positions", "cell", "occupancy"}
    refinement, result, indices = rietveld(
        structure, data, radiation,
        free=tuple(k for k in free if k not in held),
        background_terms=background_terms, preferred_axis=preferred_axis,
        folder=folder, cancel=cancel)
    term = PatternTerm(refinement, data, cell=cell,
                       extra_parameters=len(refined_values(result)))
    return term, result, indices, refinement
