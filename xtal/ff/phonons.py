"""
xtal.ff.phonons
===============
Phonons through phonopy: displacements reduced by symmetry, a
supercell for a small cell, and a q-mesh.

The arithmetic of a Hessian does not change -- every engine still
answers :meth:`Calculator.compute` with forces, and phonopy is handed
them -- but the number of evaluations does.  phonopy displaces only
the atoms the space group does not already relate, along only the
directions their site symmetry leaves distinct, and rebuilds every
other column from the operations: MOF-5's primitive cell needs 19
displacements where :func:`xtal.ff.vibrations.hessian` makes 637, which
takes MACE from nine minutes to seventeen seconds.  That is the whole
reason this is worth an extra (``phonons``), found by ``find_spec``
and imported only when asked.

**A small cell is given a supercell.**  The acoustic and low optic
branches across the zone are what a solid's entropy is made of, and
Gamma alone samples none of them.  ``supercell="auto"`` repeats the
cell until every perpendicular width is at least :data:`MIN_WIDTH`,
and its atom count goes through :func:`xtal.core.limits.check_phonons`
-- in here, so the CLI and an agent meet the refusal too.  With a
supercell, the frequencies the thermochemistry sums are a Gamma-centred
q-mesh's; the mode table and the IR spectrum are Gamma's either way.

**The supercell carries the graph.**  The engine is built over it, and
an engine reads bonds -- UFF types every atom by them -- so it is made
from :func:`xtal.core.bonding.flat_with_graph` with each bond taken to
every copy of its first atom.  Perceiving it afresh would re-bond what
the user took away, as a scan's points would without
:func:`xtal.ff.scan.hold_bonding`.

**phonopy is told every unit.**  It is given our P1 cell as its
primitive (``primitive_matrix`` explicit: phonopy 4 changed the default
and warned on every structure), the isotope's own mass for each atom,
and forces in eV/A; its THz come back as wavenumbers.  A marker is not
handed to it at all: the engine still sees the whole supercell and
holds the markers back itself.

Frozen atoms are not offered here: phonopy's symmetry assumes every
atom may move, and the Gamma path is what can hold some still.  A
molecule in a box gains nothing from crystal symmetry and always takes
the Gamma path too.
"""

from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass, replace

import numpy as np

from xtal.core import bonding, limits, molecule, p1
from xtal.core import elements as el
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Structure
from xtal.ff import vibrations
from xtal.ff.api import CalculatorStopped

#: A cell narrower than this between opposite faces (A) is repeated.
MIN_WIDTH = 10.0

#: The q-mesh, as phonopy's length: points along each reciprocal axis
#: are about this over the cell length.  100 is phonopy's own default
#: for thermal properties.
MESH = 100.0

#: kcal/mol per eV, and wavenumbers per THz.
KCAL_PER_EV = 23.060547830619
CM_PER_THZ = 33.35640951981521

#: Below this the sites' masses count as the element's own: a site
#: whose mass differs (deuterium) can break the symmetry the q-mesh is
#: reduced by, though never the force constants'.
_SAME_MASS = 1e-6


def installed() -> bool:
    """``find_spec``, never an import."""
    return importlib.util.find_spec("phonopy") is not None


def install_hint() -> str:
    return ("install the phonons extra for symmetry-reduced "
            "displacements and a q-mesh")


def said(verdict) -> str:
    """A size verdict as a sentence of its own."""
    text = verdict.sentence
    return f"{text[:1].upper()}{text[1:]}."


def parse_supercell(value) -> str | tuple[int, int, int]:
    """``"auto"``, ``"gamma"`` or three repeats, from what a person
    typed (``"2 2 1"``, ``"2x2x1"``) or a tuple."""
    if isinstance(value, (tuple, list, np.ndarray)):
        words = [str(v) for v in value]
    else:
        text = str(value or "auto").strip().lower()
        if text in ("auto", "gamma"):
            return text
        words = text.replace("x", " ").replace(",", " ").split()
    try:
        counts = tuple(int(w) for w in words)
    except ValueError:
        counts = ()
    if len(counts) != 3 or min(counts) < 1:
        raise ValueError(f"a supercell is auto, gamma or three whole "
                         f"repeats, not {value!r}")
    return counts


def auto_supercell(matrix, width: float = MIN_WIDTH
                   ) -> tuple[int, int, int]:
    """The smallest diagonal repeat with every perpendicular width at
    least ``width``."""
    widths = molecule._perpendicular_widths(np.asarray(matrix, float))
    return tuple(max(1, math.ceil(width / w - 1e-9)) for w in widths)


def supercell_of(structure, supercell="auto") -> tuple[int, int, int]:
    """The repeats ``supercell`` asks for on ``structure``."""
    chosen = parse_supercell(supercell)
    if chosen == "gamma":
        return (1, 1, 1)
    if chosen == "auto":
        return auto_supercell(structure.lattice.matrix)
    return chosen


@dataclass(frozen=True)
class Plan:
    """What a phonopy run on a structure will cost, before it runs."""

    supercell: tuple[int, int, int]
    atoms: int                      # in the supercell, markers left out
    displacements: int
    verdict: limits.Verdict

    @property
    def evaluations(self) -> int:
        """One per displaced supercell, and one at the reference for
        the energy."""
        return self.displacements + 1


def plan(structure, supercell="auto", *, delta: float = vibrations.DELTA,
         profile=None) -> Plan:
    """The supercell, its size verdict and how many displacements
    phonopy wants -- symmetry found, nothing evaluated."""
    repeats = supercell_of(structure, supercell)
    real = _real_cell(structure)[0]
    verdict = limits.check_phonons(real.n_atoms, repeats, profile)
    if verdict.refused:
        return Plan(repeats, verdict.estimate, 0, verdict)
    phonon = _phonopy(structure, repeats)
    phonon.generate_displacements(distance=float(delta))
    return Plan(repeats, verdict.estimate,
                len(phonon.supercells_with_displacements), verdict)


def phonopy_vibrations(build, structure, *, supercell="auto",
                       mesh=MESH,
                       delta: float = vibrations.DELTA, cancel=None,
                       progress=None, record=None, profile=None,
                       save=None) -> vibrations.Vibrations:
    """The modes of the crystal ``structure``, by phonopy.

    ``build(structure)`` makes the engine's calculator over the
    supercell it is given (``ENGINES.build`` with the engine's name and
    options bound).  ``progress(done, total)`` hears each evaluation,
    and ``record(index, displacement, forces)`` each displaced
    supercell's forces in phonopy's own atom order, eV/A.  Stop is
    checked before every evaluation and raises
    :class:`~xtal.ff.api.CalculatorStopped`.  Raises ``ValueError``
    with the size sentence when the supercell is over the hard limit.
    ``mesh`` is phonopy's length, or three counts to hold the mesh
    itself fixed -- what a quasi-harmonic run does, so that every
    volume is summed over the same points.
    ``save`` is where phonopy's own ``phonopy_params.yaml`` (the cell,
    the displacements, the force constants) is written, for anyone who
    wants its bands or DOS from the same run.
    """
    repeats = supercell_of(structure, supercell)
    real, kept = _real_cell(structure)
    verdict = limits.check_phonons(real.n_atoms, repeats, profile)
    if verdict.refused:
        raise ValueError(said(verdict))

    phonon = _phonopy(structure, repeats)
    phonon.generate_displacements(distance=float(delta))
    displaced = phonon.supercells_with_displacements
    big = _supercell_with_graph(structure, repeats)
    reference = p1.expand(big)
    matrix = np.asarray(big.lattice.matrix, float)
    cart = np.asarray(reference.cart, float)
    atoms = np.array([i for i, e in enumerate(reference.elements)
                      if not el.is_dummy(e)], dtype=int)
    ours = atoms[_match(phonon.supercell.scaled_positions,
                        reference.frac[atoms], matrix)]
    calculator = build(big)
    total = len(displaced) + 1
    done = 0

    def evaluate(positions):
        nonlocal done
        if getattr(cancel, "requested", False):
            raise CalculatorStopped("stopped between displacements")
        result = calculator.compute(positions, matrix)
        done += 1
        if progress is not None:
            progress(done, total)
        return result

    energy = float(evaluate(cart).energy) / float(np.prod(repeats))
    perfect = np.asarray(phonon.supercell.positions, float)
    forces = []
    for index, cell in enumerate(displaced):
        step = np.asarray(cell.positions, float) - perfect
        # Displacements are hundredths of an angstrom; anything a
        # lattice vector long is phonopy wrapping a moved atom.
        frac = step @ np.linalg.inv(matrix)
        step = (frac - np.round(frac)) @ matrix
        moved = cart.copy()
        moved[ours] += step
        got = np.asarray(evaluate(moved).forces, float)[ours]
        got = got / KCAL_PER_EV
        got -= got.mean(axis=0)
        forces.append(got)
        if record is not None:
            record(index, step, got)
    phonon.forces = np.array(forces)
    phonon.produce_force_constants(show_drift=False)
    phonon.symmetrize_force_constants()
    if save is not None:
        from xtal.io import atomic

        with atomic.replacing(save) as partial:
            phonon.save(filename=str(partial),
                        settings={"force_constants": True})

    gamma = _gamma_hessian(phonon)
    mesh_frequencies = mesh_weights = q_mesh = None
    if int(np.prod(repeats)) > 1:
        asked = (float(mesh) if np.ndim(mesh) == 0
                 else [int(v) for v in mesh])
        phonon.run_mesh(asked, is_gamma_center=True,
                        is_mesh_symmetry=_symmetric_masses(real))
        sampled = phonon.mesh
        freqs = np.asarray(sampled.frequencies, float) * CM_PER_THZ
        weights = np.asarray(sampled.weights, float)
        weights = weights / weights.sum()
        mesh_frequencies = freqs.ravel()
        mesh_weights = np.repeat(weights, freqs.shape[1])
        q_mesh = tuple(int(v) for v in phonon.mesh_numbers)

    return vibrations.from_hessian(
        structure, gamma, kind="crystal", free=kept, energy=energy,
        evaluations=done, method="phonopy", supercell=tuple(repeats),
        q_mesh=q_mesh, mesh_frequencies=mesh_frequencies,
        mesh_weights=mesh_weights)


# ======================================================================
#  THE CELLS
# ======================================================================

def _real_cell(structure):
    """The P1 cell without its markers, and which P1 atoms it kept."""
    cell = p1.expand(structure)
    kept = np.array([i for i in range(cell.n_atoms)
                     if not el.is_dummy(cell.elements[i])], dtype=int)
    return replace(cell, frac=cell.frac[kept],
                   site_idx=cell.site_idx[kept],
                   op_idx=cell.op_idx[kept], tau=cell.tau[kept],
                   elements=tuple(cell.elements[i] for i in kept),
                   occupancy=cell.occupancy[kept],
                   labels=tuple(cell.labels[i] for i in kept),
                   _index={}), kept


def _symmetric_masses(real) -> bool:
    """Whether every atom weighs what its element does."""
    masses = vibrations.masses_of(real.elements)
    plain = vibrations.masses_of(_plain(real.elements))
    return bool(np.all(np.abs(masses - plain) < _SAME_MASS))


def _plain(symbols) -> list[str]:
    """Each isotope as its element: phonopy's symmetry is the energy
    surface's, and the masses are given to it separately."""
    from xtal.ff.isotopes import ISOTOPES

    return [ISOTOPES.get(e, e) for e in symbols]


def _phonopy(structure, repeats):
    """A ``Phonopy`` over the real atoms of the P1 cell, which is its
    own primitive."""
    from phonopy import Phonopy
    from phonopy.structure.atoms import PhonopyAtoms

    real, _kept = _real_cell(structure)
    unit = PhonopyAtoms(
        symbols=_plain(real.elements),
        cell=np.asarray(structure.lattice.matrix, float),
        scaled_positions=np.mod(np.asarray(real.frac, float), 1.0),
        masses=vibrations.masses_of(real.elements))
    return Phonopy(unit, supercell_matrix=np.diag(repeats),
                   primitive_matrix=np.eye(3), log_level=0)


def _gamma_hessian(phonon) -> np.ndarray:
    """The unit cell's Gamma Hessian, kcal/mol/A^2, from phonopy's
    force constants: each atom's row summed over every image of its
    partner, which is what moving every image of an atom together --
    as :func:`xtal.ff.vibrations.hessian` does -- measures.  Summed
    here rather than asked of phonopy, whose call for it changed
    between versions."""
    fc = np.asarray(phonon.force_constants, float)
    p2s = np.asarray(phonon.primitive.p2s_map, int)
    s2p = np.asarray(phonon.primitive.s2p_map, int)
    home = {int(s): k for k, s in enumerate(p2s)}
    partner = np.array([home[int(s)] for s in s2p])
    n = len(p2s)
    out = np.zeros((n, n, 3, 3))
    for k, row in enumerate(p2s):
        np.add.at(out[k], partner, fc[row])
    return out.transpose(0, 2, 1, 3).reshape(3 * n, 3 * n) \
        * KCAL_PER_EV


def _match(phonopy_frac, frac, matrix) -> np.ndarray:
    """For each phonopy supercell atom, the index of the same atom in
    ours, through the periodic boundary."""
    from scipy.spatial import cKDTree

    def folded(x):
        x = np.mod(np.asarray(x, float), 1.0)
        x[x >= 1.0] = 0.0
        return x

    tree = cKDTree(folded(frac), boxsize=1.0)
    distance, index = tree.query(folded(phonopy_frac))
    shortest = float(np.min(np.linalg.norm(matrix, axis=1)))
    if np.any(distance * shortest > 0.01) or \
            len(set(index.tolist())) != len(index):
        raise RuntimeError("phonopy's supercell does not match ours")
    return index


def _supercell_with_graph(structure, repeats) -> Structure:
    """``repeats`` of the P1 cell, every bond -- explicit, perceived,
    suppressed -- taken to each copy of its first atom.

    Nothing is cut: the partner of an atom in copy ``s`` across image
    ``t`` is in copy ``(s + t) mod n``, through image
    ``(s + t) // n``, counted from each site's own coordinate."""
    one = bonding.flat_with_graph(structure)
    n = np.asarray(repeats, int)
    if np.all(n == 1):
        return one
    copies = [np.array(s) for s in np.ndindex(*n)]
    position = {tuple(s): k for k, s in enumerate(copies)}
    count = one.n_sites

    sites = []
    for s in copies:
        for site in one.sites:
            moved = site.copy()
            moved.frac = (np.asarray(site.frac, float) + s) / n
            moved.label = ""
            moved.wyckoff = None
            sites.append(moved)

    def carried(i, j, image, s):
        target = s + np.asarray(image, int)
        home = np.mod(target, n)
        return (position[tuple(s)] * count + i,
                position[tuple(home)] * count + j,
                tuple(int(v) for v in (target - home) // n))

    bonds = []
    for bond in one.bonds:
        for s in copies:
            i, j, image = carried(bond.i, bond.j, bond.image, s)
            bonds.append(replace(bond, i=i, j=j, image=image))

    stored = one.perceived
    zero = np.zeros((count, 3), dtype=int)
    perceived = []
    for bond in bonding.rebase(stored.bonds, stored.tau, zero):
        for s in copies:
            i, j, image = carried(bond.i, bond.j, bond.image, s)
            perceived.append(replace(bond, i=i, j=j, image=image))

    out = Structure(lattice=one.lattice.transform(np.diag(n)),
                    sites=sites, space_group=SpaceGroup.p1(),
                    bonds=bonds, bond_rules=dict(one.bond_rules),
                    meta=dict(one.meta))
    out.ensure_labels()
    cell = p1.expand(out)
    out.set_perceived(
        bonding.rebase(perceived, np.zeros((len(sites), 3), dtype=int),
                       cell.tau),
        stored.signature, cell)
    return out
