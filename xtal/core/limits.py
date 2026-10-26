"""
xtal.core.limits
================
How big a thing may get before it is asked about or refused.

One module, so that the window, the CLI and an agent's Session read
the same numbers.  Every estimate here is **arithmetic, made before
anything is built**: a supercell is the cell's atoms times ``|det P|``,
a drawing the atoms times the volume of the range, a porosity grid the
product of its shape.  The measurements that set the table: MFU-4l's
drawn scene costs 5.8 KB an atom, a 20x20x20 supercell preview of it
was 5.2 M atoms and 2.8 GB rebuilt on every spin step, its porosity
grid at 0.2 A 3.8 M points and about 2.2 GB, and a 3x3x3 carbon build
53 s and 0.84 GB -- each of them a crash on an 8 GB machine under
memory pressure, with nothing said first.

Two levels, soft and hard.  Over the soft limit the person is asked
(or, headless, told); over the hard one the thing is refused, and the
sentence says what *would* fit.  Which numbers apply is a **profile**,
not a dozen settings: *Standard* for an 8 GB-class machine, *Generous*
for 16 GB and up (every limit doubled), and *Warn only*, which still
says everything and refuses nothing.  The window sets the profile from
Preferences > General > Large structures (:func:`use`); a headless
caller gets Standard unless it passes or sets another.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Sites the undo history may hold in whole-structure steps (a
#: supercell, Reduce to P1, a change of group) before its oldest such
#: steps are let go.  Steps were capped only by count, two hundred of
#: them, and an MFU-4l 3x3x3 held 43 MB a step: a long session on a
#: big cell kept gigabytes of crystals nobody would undo back to.
UNDO_ATOMS = 2_000_000

#: The most recent steps, which are never let go whatever they hold.
UNDO_KEEP = 5

STANDARD, GENEROUS, WARN_ONLY = "standard", "generous", "warn_only"
PROFILES = (STANDARD, GENEROUS, WARN_ONLY)

#: (soft, hard) under Standard.  Generous doubles both; Warn only
#: keeps Standard's soft limit and has no hard one.
BUDGETS = {
    "drawn": (100_000, 400_000),
    "supercell": (50_000, 200_000),
    "grid": (1_500_000, 4_000_000),
    "carbon": (10_000, 30_000),
    # What this budget guards is the window holding the tube, as the
    # supercell's does: the atoms built.  It does not guard the
    # rolling, which a finite tube does over whole periods -- a
    # (200,199) piece of about 4,000 atoms rolls 477,604 a period and
    # took 18.5 s and 0.8 GB, on a worker thread, under this budget.
    "nanotube": (50_000, 200_000),
    # A phonopy supercell is evaluated once per displacement, so its
    # size is an engine's single point many times over: 2,000 atoms
    # is a few seconds a point under an ML engine on a laptop.
    "phonons": (2_000, 8_000),
    # An analytic Hessian holds the force graph for every row, and the
    # graph grows with the atoms (HESSIAN_MB_PER_ATOM): 300 is 4 GB of
    # it beside the model.
    "hessian": (100, 300),
}

#: What an analytic Hessian's retained graph costs, MB a P1 atom:
#: MIL-53's 104 atoms under MACE-MPA-0 in float64 on the CPU went
#: from 1.6 GB after one evaluation to 2.9 GB, a row at a time.
#: MACE's own vmapped ``get_hessian`` peaked at 7.1 GB, which is why
#: it is not what runs.
HESSIAN_MB_PER_ATOM = 13

OK, WARN, REFUSE = "ok", "warn", "refuse"

_current = STANDARD


def profile_of(name) -> str:
    """``name`` if it is a profile, else Standard: a settings file
    edited by hand, or written by a later version, must not stop the
    window from starting."""
    return name if name in PROFILES else STANDARD


def use(profile) -> None:
    """Make ``profile`` the one every check below applies by default.
    The window calls it at start and when Preferences changes it."""
    global _current
    _current = profile_of(profile)


def current() -> str:
    return _current


def bounds(budget: str, profile: str | None = None) -> tuple:
    """``(soft, hard)`` for ``budget``; ``hard`` is None under Warn
    only."""
    profile = profile_of(profile or _current)
    soft, hard = BUDGETS[budget]
    if profile == GENEROUS:
        return 2 * soft, 2 * hard
    if profile == WARN_ONLY:
        return soft, None
    return soft, hard


@dataclass(frozen=True)
class Verdict:
    """What a size check found.  ``sentence`` is empty when it is
    fine, and otherwise says the estimate and what would fit."""

    level: str
    estimate: int
    sentence: str = ""

    @property
    def refused(self) -> bool:
        return self.level == REFUSE

    @property
    def warned(self) -> bool:
        return self.level != OK


def count(n: float) -> str:
    """A count as a sentence says it: 52,000 or 1.4 M."""
    n = int(round(n))
    if n >= 1_000_000:
        return f"{n / 1e6:.1f} M"
    return f"{n:,}"


def _judge(budget, estimate, profile, what, fits) -> Verdict:
    """The verdict on ``estimate``.  ``what`` is the sentence's
    subject with a ``{}`` for the count, and ``fits(limit)`` names
    what would come in under ``limit``."""
    soft, hard = bounds(budget, profile)
    estimate = int(round(estimate))
    if estimate <= soft:
        return Verdict(OK, estimate)
    if hard is not None and estimate > hard:
        return Verdict(REFUSE, estimate, (
            f"{what.format(count(estimate))}, over the {count(hard)} "
            f"the Large structures setting allows; {fits(hard)}"))
    return Verdict(WARN, estimate, (
        f"{what.format(count(estimate))}, over the {count(soft)} "
        f"that is comfortable; {fits(soft)}"))


def _cube_that_fits(per_cell: float, limit: float,
                    cells: str = "") -> str:
    k = int(math.floor((limit / max(per_cell, 1)) ** (1 / 3) + 1e-9))
    if k < 1:
        return f"one cell alone is {count(per_cell)} atoms"
    return f"{k} x {k} x {k}{cells} is the largest that fits"


# ======================================================================
#  ESTIMATES
# ======================================================================

def drawn_atoms(n_atoms: int, ranges) -> int:
    """Atoms drawn for a display range: the cell's atoms times the
    range's volume in cells.  The closing faces are left out, which
    is a few percent on anything big enough to matter."""
    volume = 1.0
    for lo, hi in ranges:
        volume *= max(float(hi) - float(lo), 0.0)
    return int(round(n_atoms * volume))


def multiplier(p) -> int:
    """``|det P|`` for three counts or a 3x3 matrix."""
    p = np.asarray(p, dtype=float)
    if p.shape == (3,):
        p = np.diag(p)
    return int(round(abs(float(np.linalg.det(p.reshape(3, 3))))))


def supercell_atoms(n_atoms: int, p) -> int:
    """Atoms in the cell ``p`` builds from one of ``n_atoms``."""
    return n_atoms * multiplier(p)


def grid_points(lattice, spacing: float) -> int:
    """Points in a porosity grid at ``spacing``."""
    from xtal.analysis import grid
    return int(np.prod(grid.shape_for(lattice, spacing)))


def carbon_atoms(recipe) -> int:
    """Atoms a carbon build of ``recipe`` comes out with: the cells
    times one cell's carbon, solved for the density as the build
    solves it (about a second), with the terminations on top."""
    from xtal.carbon import surface as sf
    lattice, vertices, edges = sf.net_of(recipe.net)
    solved = sf.solve_scale(
        lattice, vertices, edges, density=recipe.density,
        radius_ratio=recipe.radius_ratio, coverage=recipe.coverage,
        layers=recipe.layers, interlayer=recipe.interlayer)
    terminations = recipe.hydrogen + recipe.fluorine + recipe.oxygen
    cells = int(np.prod(recipe.repeat))
    return int(round(cells * solved.carbons * (1 + terminations)))


def nanotube_atoms(recipe) -> int:
    """Atoms a nanotube build of ``recipe`` comes out with, without
    rolling it.  Exact for a periodic tube.  For a finite one: the
    sheet's atoms over the length, an edge's worth more for the
    atoms a cut leaves either side, and the caps.  That is an upper
    bound, measured on tubes from (5,0) to (15,15) at 3 to 120 A, and
    on long-period chiral tubes such as (40,39), whose 291 A period
    is far longer than the piece cut from it."""
    c = recipe.chirality
    if recipe.periodic:
        return c.atoms_per_period * recipe.periods
    edge = 2 * (c.n + c.m)
    caps = 2 * edge if recipe.ends == "capped" else 0
    return math.ceil(c.atoms_per_period * recipe.length / c.t_length) \
        + edge + caps


# ======================================================================
#  CHECKS
# ======================================================================

def check_drawn(n_atoms: int, ranges, profile=None) -> Verdict:
    return _judge("drawn", drawn_atoms(n_atoms, ranges), profile,
                  "the picture would draw {} atoms",
                  lambda limit: _cube_that_fits(n_atoms, limit,
                                                " cells"))


def check_supercell(n_atoms: int, p, profile=None) -> Verdict:
    return _judge("supercell", supercell_atoms(n_atoms, p), profile,
                  "the new cell would have {} atoms",
                  lambda limit: _cube_that_fits(n_atoms, limit))


def check_grid(lattice, spacing: float, profile=None) -> Verdict:
    def fits(limit):
        step = max(0.05, math.ceil(spacing / 0.05) * 0.05)
        while grid_points(lattice, step) > limit and step < 5.0:
            step += 0.05
        return (f"at {step:.2f} A it would have "
                f"{count(grid_points(lattice, step))}")
    return _judge("grid", grid_points(lattice, spacing), profile,
                  "the grid would have {} points", fits)


def check_carbon(recipe, profile=None) -> Verdict:
    estimate = carbon_atoms(recipe)
    per_cell = estimate / max(int(np.prod(recipe.repeat)), 1)
    return _judge("carbon", estimate, profile,
                  "the build would have {} atoms",
                  lambda limit: _cube_that_fits(per_cell, limit))


def check_nanotube(recipe, profile=None) -> Verdict:
    c = recipe.chirality

    def fits(limit):
        if recipe.periodic:
            # Whole periods: a length is rounded to the nearest one,
            # so naming the continuous length that fits named one
            # that rounds up past the limit.  k T rounds back to k.
            k = int(limit // c.atoms_per_period)
            if k < 1:
                return (f"one period alone is "
                        f"{count(c.atoms_per_period)} atoms")
            periods = "period" if k == 1 else "periods"
            return (f"{k} {periods}, {k * c.t_length:.0f} A, is the "
                    f"longest that fits")
        # A finite tube needs no whole period, and a chiral one's can
        # be over a thousand angstroms.  Floor, not round: half an
        # angstrom up is a ring's worth of atoms past the limit.
        edges = 6 * (c.n + c.m)
        longest = math.floor(
            (limit - edges) * c.t_length / c.atoms_per_period)
        if longest < recipe.bond:
            return (f"at ({c.n},{c.m}) even a tube one bond long "
                    f"would be over it")
        return f"about {longest} A is the longest that fits"
    return _judge("nanotube", nanotube_atoms(recipe), profile,
                  "the tube would have {} atoms", fits)


def check_phonons(n_atoms: int, p, profile=None) -> Verdict:
    return _judge("phonons", supercell_atoms(n_atoms, p), profile,
                  "the phonon supercell would have {} atoms",
                  lambda limit: _cube_that_fits(n_atoms, limit)
                  + ", or Gamma only needs none")


def check_hessian(n_atoms: int, profile=None) -> Verdict:
    """An analytic Hessian over ``n_atoms`` free atoms.  Over the hard
    limit the finite differences are the way: they hold one
    evaluation's memory at a time."""
    return _judge("hessian", n_atoms, profile,
                  "an analytic Hessian over {} atoms would hold about "
                  + f"{n_atoms * HESSIAN_MB_PER_ATOM / 1024:.1f} GB",
                  lambda limit: f"up to {count(limit)} atoms fit, and "
                  "finite differences need no more than one "
                  "evaluation does")
