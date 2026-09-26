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
from xtal.powder.data import PowderData, PowderError, Radiation

__all__ = ["apply_phase", "fit", "instrument", "pattern", "phase_of",
           "predict", "space_group_symbol", "to_rietx"]

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
    return refinement.fit(pattern(data), telemetry=telemetry, **kwargs)


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
               shoulders: bool = True, flag_ghosts: bool = True):
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
