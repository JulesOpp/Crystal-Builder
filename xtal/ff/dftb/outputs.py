"""
xtal.ff.dftb.outputs
====================
Reading what DFTB+ writes when it is asked for more than an energy.

One reader per file, each taking text and giving back arrays -- no
paths, no processes -- so each is tested against output captured from
DFTB+ 24.1 (``tests/data/dftb``) and none needs the binary.  The
formats are DFTB+'s own and undocumented beyond the source, so every
reader says in its docstring what it relies on, and refuses rather
than guesses when that is not there.

Units are what DFTB+ wrote unless the name says otherwise:
``band.out`` and the projected densities are in eV, ``detailed.out``
gives both and eV is taken, ``md.out`` energies are Hartree and are
converted, and ``vibrations.tag`` frequencies are Hartree and come
back in cm^-1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

HARTREE_EV = 27.211386245988
HARTREE_WAVENUMBER = 219474.6313632
BOHR = 0.52917721090380

_FLOAT = r"-?\d+(?:\.\d*)?(?:[eEdD][-+]?\d+)?"


def _float(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "E"))


# ======================================================================
#  EIGENVALUES
# ======================================================================

@dataclass(frozen=True)
class Eigenvalues:
    """``band.out``: ``energies[spin, k, band]`` in eV, the occupations
    beside them, and each k-point's weight."""

    energies: np.ndarray = field(default_factory=lambda: np.zeros((0,)))
    occupations: np.ndarray = field(
        default_factory=lambda: np.zeros((0,)))
    weights: np.ndarray = field(default_factory=lambda: np.zeros((0,)))

    @property
    def n_spin(self) -> int:
        return self.energies.shape[0]

    @property
    def n_kpoints(self) -> int:
        return self.energies.shape[1]

    @property
    def n_bands(self) -> int:
        return self.energies.shape[2]


_KPT = re.compile(r"^\s*KPT\s+(\d+)\s+SPIN\s+(\d+)\s+KWEIGHT\s+(\S+)")


def read_bands(text: str) -> Eigenvalues:
    """Every ``KPT n SPIN s KWEIGHT w`` block and the ``index energy
    occupation`` rows under it."""
    blocks: dict[tuple, list] = {}
    weights: dict[int, float] = {}
    current = None
    for line in text.splitlines():
        head = _KPT.match(line)
        if head:
            k, spin = int(head.group(1)), int(head.group(2))
            current = blocks.setdefault((spin, k), [])
            weights[k] = _float(head.group(3))
            continue
        parts = line.split()
        if current is not None and len(parts) >= 3:
            current.append((_float(parts[1]), _float(parts[2])))
    if not blocks:
        raise ValueError("no KPT blocks: this is not a band.out")
    spins = sorted({s for s, _k in blocks})
    kpoints = sorted({k for _s, k in blocks})
    bands = {len(rows) for rows in blocks.values()}
    if len(bands) != 1:
        raise ValueError("band.out has k-points with different band "
                         "counts")
    shape = (len(spins), len(kpoints), bands.pop())
    energies, occupations = np.zeros(shape), np.zeros(shape)
    for (spin, k), rows in blocks.items():
        values = np.array(rows)
        energies[spins.index(spin), kpoints.index(k)] = values[:, 0]
        occupations[spins.index(spin), kpoints.index(k)] = values[:, 1]
    return Eigenvalues(energies, occupations,
                       np.array([weights[k] for k in kpoints]))


def read_dos(text: str) -> tuple[np.ndarray, np.ndarray]:
    """A ``dos_<label>.out``: ``(energies, weights)`` flattened over
    k-points, each state's weight already times its k-point's.

    The format is ``band.out``'s with the region's share of each state
    where the occupation was.  Broadening is not DFTB+'s job -- see
    :func:`broaden`.
    """
    energies, weights = [], []
    kweight = None
    for line in text.splitlines():
        head = re.match(r"^\s*KPT\s+\d+\s+SPIN\s+\d+\s+KWEIGHT\s+(\S+)",
                        line)
        if head:
            kweight = _float(head.group(1))
            continue
        parts = line.split()
        if kweight is not None and len(parts) >= 2:
            energies.append(_float(parts[0]))
            weights.append(_float(parts[1]) * kweight)
    if kweight is None:
        raise ValueError("no KPT blocks: this is not a projected "
                         "density of states")
    return np.array(energies), np.array(weights)


def broaden(energies, weights, grid, sigma: float) -> np.ndarray:
    """Gaussians of width ``sigma`` eV, summed onto ``grid``."""
    energies = np.asarray(energies, dtype=float)
    weights = np.asarray(weights, dtype=float)
    grid = np.asarray(grid, dtype=float)
    sigma = max(float(sigma), 1e-6)
    out = np.zeros_like(grid)
    norm = 1.0 / (sigma * np.sqrt(2 * np.pi))
    # In chunks: a dense mesh is tens of thousands of states over a
    # grid of thousands of points, and the whole outer product at once
    # is a gigabyte for no reason.
    for start in range(0, len(energies), 2048):
        e = energies[start:start + 2048]
        w = weights[start:start + 2048]
        out += (w[:, None] * np.exp(
            -0.5 * ((grid[None, :] - e[:, None]) / sigma) ** 2)
                ).sum(axis=0)
    return out * norm


# ======================================================================
#  DETAILED.OUT
# ======================================================================

_FERMI = re.compile(rf"Fermi level:\s*({_FLOAT})\s*H\s*({_FLOAT})\s*eV")


def fermi_level(text: str) -> float | None:
    """The Fermi level in eV, or ``None``.  The last one printed, which
    in a run of several steps is the geometry the run ended at."""
    found = _FERMI.findall(text)
    return _float(found[-1][1]) if found else None


def mulliken_charges(text: str) -> np.ndarray | None:
    """Every atom's gross charge in e, from ``Atomic gross charges``.

    Positive is electrons lost.  ``None`` when the block is not there,
    which is what an input without ``MullikenAnalysis`` gives.
    """
    lines = text.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if "Atomic gross charges" not in lines[index]:
            continue
        charges = []
        for row in lines[index + 2:]:
            parts = row.split()
            if len(parts) < 2 or not parts[0].isdigit():
                break
            charges.append(_float(parts[1]))
        return np.array(charges)
    return None


# ======================================================================
#  A RELAXATION, AS IT RUNS
# ======================================================================

@dataclass
class StepReader:
    """DFTB+'s standard output, a line at a time, into steps.

    Fed from :class:`~xtal.modules.process.ExternalProcess`'s
    ``on_line``; calls ``on_step(step, energy_kcal, max_force)`` once a
    step has printed both its energy and its largest force, the force
    in kcal/mol/A.  A lattice step prints a lattice force as well and it
    is folded into the same number, because the plot has one axis and
    both have to be small.
    """

    on_step: object = None
    step: int = -1
    energy: float | None = None
    force: float | None = None
    lattice_force: float | None = None
    steps: list = field(default_factory=list)

    _STEP = re.compile(r"Geometry step:\s*(\d+)")
    _ENERGY = re.compile(rf"Total (?:Mermin free )?energy:\s*({_FLOAT})"
                         r"\s*H", re.IGNORECASE)
    _FORCE = re.compile(rf"^\s*Maximal force component:\s*({_FLOAT})")
    _LATTICE = re.compile(
        rf"^\s*Maximal Lattice force component:\s*({_FLOAT})")

    def __call__(self, line: str) -> None:
        found = self._STEP.search(line)
        if found:
            self._close()
            self.step = int(found.group(1))
            return
        found = self._ENERGY.search(line)
        if found:
            self.energy = _float(found.group(1))
            return
        found = self._FORCE.search(line)
        if found:
            self.force = _float(found.group(1))
            return
        found = self._LATTICE.search(line)
        if found:
            self.lattice_force = _float(found.group(1))
            if self.force is not None:
                self._close()

    def finish(self) -> None:
        self._close()

    def _close(self) -> None:
        if self.step < 0 or self.energy is None or self.force is None:
            return
        from xtal.ff.dftb.calculator import HARTREE
        force = max(self.force, self.lattice_force or 0.0)
        entry = (self.step, self.energy * HARTREE,
                 force * HARTREE / BOHR)
        if not self.steps or self.steps[-1][0] != self.step:
            self.steps.append(entry)
            if self.on_step is not None:
                self.on_step(*entry)
        self.energy = self.force = self.lattice_force = None


# ======================================================================
#  MOLECULAR DYNAMICS
# ======================================================================

@dataclass(frozen=True)
class MdLog:
    """``md.out``: per written step, time in fs and energies in
    kcal/mol."""

    steps: np.ndarray
    potential: np.ndarray
    total: np.ndarray
    temperature: np.ndarray


def read_md(text: str, time_step: float = 1.0) -> MdLog:
    steps, potential, total, temperature = [], [], [], []
    from xtal.ff.dftb.calculator import HARTREE
    for line in text.splitlines():
        if line.startswith("MD step:"):
            steps.append(int(line.split(":")[1]))
        elif line.startswith("Potential Energy:"):
            potential.append(_float(line.split()[2]) * HARTREE)
        elif line.startswith("Total MD Energy:"):
            total.append(_float(line.split()[3]) * HARTREE)
        elif line.startswith("MD Temperature:"):
            temperature.append(_float(line.split()[-2]))
    n = min(len(steps), len(potential), len(total), len(temperature))
    if not n:
        raise ValueError("no MD steps: this is not an md.out")
    return MdLog(np.array(steps[:n]) * float(time_step),
                 np.array(potential[:n]), np.array(total[:n]),
                 np.array(temperature[:n]))


def read_xyz_frames(text: str) -> list[np.ndarray]:
    """Every frame of a multi-frame ``geo_end.xyz``, as cartesian
    positions in Angstrom.

    DFTB+ writes charges and velocities after the coordinates; only
    the first three numbers are positions.
    """
    lines = text.splitlines()
    frames, index = [], 0
    while index < len(lines):
        head = lines[index].strip()
        if not head:
            index += 1
            continue
        count = int(head.split()[0])
        rows = lines[index + 2:index + 2 + count]
        if len(rows) < count:
            break
        frames.append(np.array([[_float(v) for v in row.split()[1:4]]
                                for row in rows]))
        index += 2 + count
    return frames


# ======================================================================
#  VIBRATIONAL MODES
# ======================================================================

@dataclass(frozen=True)
class Modes:
    """Frequencies in cm^-1 -- negative for an imaginary mode, the way
    ``modes`` prints them -- and ``displacements[mode, atom, 3]``, each
    mode normalised to a largest atom displacement of one."""

    frequencies: np.ndarray
    displacements: np.ndarray

    @property
    def imaginary(self) -> np.ndarray:
        return self.frequencies < 0


def read_tagged(text: str) -> dict:
    """A DFTB+ tagged file: ``name :type:rank:shape`` then values."""
    out: dict[str, np.ndarray] = {}
    name, shape, values = None, (), []

    def close():
        if name is None:
            return
        array = np.array(values, dtype=float)
        if len(shape) > 1:
            # Fortran order: the first index varies fastest.
            array = array.reshape(shape, order="F")
        out[name] = array

    for line in text.splitlines():
        head = re.match(r"^(\w+)\s*:(\w+):(\d+):?([\d,]*)", line)
        if head:
            close()
            name = head.group(1)
            shape = tuple(int(v) for v in head.group(4).split(",")
                          if v)
            values = []
            continue
        values.extend(_float(v) for v in line.split())
    close()
    return out


def read_modes(tag_text: str) -> Modes:
    """``vibrations.tag``, as written when ``modes`` is asked to
    display the modes: ``frequencies`` in Hartree, and ``eigenmodes``
    one mode a column.

    ``eigenmodes`` and not ``eigenmodes_scaled``, whatever the names
    suggest.  Measured on carbon dioxide's antisymmetric stretch: in
    ``eigenmodes`` each oxygen moves 0.375 of the carbon's distance,
    which is 12/32 and conserves momentum -- a cartesian displacement;
    in ``eigenmodes_scaled`` it is 0.433, the square root of that
    ratio's worth more, which is the mass-weighted vector.  Animating
    the second moves the molecule's centre of mass."""
    tags = read_tagged(tag_text)
    if "frequencies" not in tags:
        raise ValueError("no frequencies: this is not vibrations.tag")
    frequencies = tags["frequencies"].ravel() * HARTREE_WAVENUMBER
    n_modes = len(frequencies)
    vectors = tags.get("eigenmodes")
    if vectors is None:
        raise ValueError("vibrations.tag holds no eigenmodes; modes "
                         "writes them only when DisplayModes is set")
    vectors = np.asarray(vectors).reshape((-1, n_modes), order="F")
    n_atoms = vectors.shape[0] // 3
    displacements = vectors.T.reshape(n_modes, n_atoms, 3)
    largest = np.linalg.norm(displacements, axis=2).max(axis=1)
    largest[largest == 0] = 1.0
    return Modes(frequencies, displacements / largest[:, None, None])
