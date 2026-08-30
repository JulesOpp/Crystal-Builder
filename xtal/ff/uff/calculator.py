"""
xtal.ff.uff.calculator
======================
Structure in, energy and forces out.

The expensive half of a force field is not the arithmetic, it is
deciding *what to add up*: typing every atom, walking the bond graph
for angles and torsions, and enumerating pairs across periodic images.
All of that happens once, in :meth:`UFFCalculator.__init__`, and then
the geometry moves under a fixed topology -- which is what makes an
optimisation of a few hundred steps affordable.

Two things are allowed to go stale and are looked after:

* the **van der Waals pair list**, built with a skin and rebuilt when
  an atom has travelled more than half of it.  The potential is shifted
  to zero at the cutoff so that a rebuild never moves the energy by a
  step -- an optimiser reads a step as progress and stops.
* the **charges**, when they come from charge equilibration, which
  depends on geometry.  They are equilibrated once at the starting
  geometry and held; re-solving every step would make the energy
  non-conservative, and the forces would no longer be the gradient of
  anything.

Excluded pairs are the usual ones: bonded (1-2) and geminal (1-3)
neighbours have no van der Waals or Coulomb interaction, because the
bond and angle terms already describe them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.core import bonding, neighbors, p1
from xtal.ff import ewald
from xtal.ff.api import Calculator, CalculatorError, Result
from xtal.ff.registry import ENGINES, Engine
from xtal.ff.uff import params, terms, typer

DEFAULT_VDW_CUTOFF = 12.0
DEFAULT_SKIN = 2.0


@dataclass(frozen=True)
class UFFOptions:
    """Everything about the calculation that is not the structure."""

    coulomb: bool = False
    charges: str = "site"           # "site" | "qeq" | "zero"
    dielectric: float = 1.0
    vdw: bool = True
    vdw_cutoff: float = DEFAULT_VDW_CUTOFF
    skin: float = DEFAULT_SKIN
    ewald_accuracy: float = ewald.DEFAULT_ACCURACY

    def to_dict(self) -> dict:
        return {"coulomb": self.coulomb, "charges": self.charges,
                "dielectric": self.dielectric, "vdw": self.vdw,
                "vdw_cutoff": self.vdw_cutoff}


@dataclass
class Topology:
    """What the force field found to add up."""

    bonds: terms.BondTerm
    angles: terms.AngleTerm
    torsions: terms.TorsionTerm
    inversions: terms.InversionTerm
    excluded: set = field(default_factory=set)
    # The same pairs as ``excluded``, packed one int64 each, so the
    # pair list can test half a million candidates against them in one
    # ``np.isin`` instead of building half a million tuples.
    excluded_codes: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=np.int64))

    def counts(self) -> dict:
        return {"bonds": len(self.bonds), "angles": len(self.angles),
                "torsions": len(self.torsions),
                "inversions": len(self.inversions)}

    def summary(self) -> str:
        return ", ".join(f"{v} {k}" for k, v in self.counts().items())


class UFFCalculator(Calculator):
    """The Universal Force Field over a structure's P1 cell."""

    name = "uff"
    label = "UFF"
    provides_forces = True
    provides_stress = True

    def __init__(self, structure, options: UFFOptions | None = None,
                 rules: bonding.BondRules | None = None):
        self.options = options or UFFOptions()
        self.structure = structure
        self.cell = p1.expand(structure)
        if self.cell.n_atoms == 0:
            raise CalculatorError(
                "there are no atoms to compute an energy for")
        self.graph = bonding.graph(structure, rules)
        self.typing = typer.assign(structure, rules)
        self.warnings: list[str] = []

        self._adjacency = _adjacency(self.graph)
        self._type_ids, self._vdw_x, self._vdw_d = self._vdw_tables()
        self.topology = self._build_topology()
        self.charges = self._charges()
        self._pairs_built_at: np.ndarray | None = None
        self._vdw: terms.VanDerWaalsTerm | None = None
        self._coulomb_pairs = None
        self._coulomb_excluded = None
        self._ewald = None
        self._check_topology()

    # -- what the panel asks about -------------------------------------

    @property
    def n_atoms(self) -> int:
        return self.cell.n_atoms

    @property
    def types(self) -> tuple[str, ...]:
        return self.typing.names

    def summary(self) -> str:
        return (f"{self.n_atoms} atoms, {self.topology.summary()}"
                + (f", {len(self.typing.unsure())} uncertain types"
                   if self.typing.unsure() else ""))

    # ==================================================================
    #  TOPOLOGY
    # ==================================================================

    def _vdw_tables(self):
        """``(type id per atom, x table, D table)``.

        A real structure has of the order of ten distinct atom types
        and hundreds of thousands of pairs, so the combining rules are
        worked out once per *pair of types* and then indexed.  Doing it
        once per pair of atoms -- two parameter lookups and two square
        roots, in Python -- was a fifth of the cost of a rebuild.
        """
        names = self.typing.names
        distinct = sorted(set(names))
        index = {name: k for k, name in enumerate(distinct)}
        ids = np.array([index[name] for name in names], dtype=int)
        n = len(distinct)
        x = np.zeros((n, n))
        d = np.zeros((n, n))
        for a in range(n):
            for b in range(a, n):
                x[a, b], d[a, b] = terms.vdw_pair(distinct[a],
                                                  distinct[b])
                x[b, a], d[b, a] = x[a, b], d[a, b]
        return ids, x, d

    def _build_topology(self) -> Topology:
        names = self.typing.names
        orders = self.typing.bond_orders
        bonds = self._bond_terms(names, orders)
        angles, geminal = self._angle_terms(names, orders)
        torsions = self._torsion_terms(names, orders)
        inversions = self._inversion_terms(names)

        excluded = {_pair_key(b.i, b.j, b.image)
                    for b in self.graph.bonds}
        excluded |= geminal
        return Topology(bonds, angles, torsions, inversions, excluded,
                        _codes_of(excluded, self.n_atoms))

    def _bond_terms(self, names, orders) -> terms.BondTerm:
        i, j, shift, r0, k = [], [], [], [], []
        for index, bond in enumerate(self.graph.bonds):
            a, b = names[bond.i], names[bond.j]
            length = terms.natural_bond_length(a, b, orders[index])
            i.append(bond.i)
            j.append(bond.j)
            shift.append(bond.image)
            r0.append(length)
            k.append(terms.bond_force_constant(a, b, length))
        return terms.BondTerm(
            _ints(i), _ints(j), _shifts(shift, len(i)),
            np.array(r0, dtype=float), np.array(k, dtype=float))

    def _angle_terms(self, names, orders):
        """Every neighbour-atom-neighbour triple, and the 1-3 pairs
        they imply.

        The 1-3 pairs come out of the same walk because they are the
        same information: two atoms with a common neighbour, at the
        specific pair of images that made them geminal.  Working them
        out separately is how an implementation ends up excluding a
        pair in one cell and not its copy in the next.
        """
        i_out, j_out, k_out = [], [], []
        si_out, sk_out = [], []
        force, c0, c1, c2, form = [], [], [], [], []
        geminal = set()

        for centre in range(self.n_atoms):
            partners = self._adjacency[centre]
            if len(partners) < 2:
                continue
            theta0 = params.get(names[centre]).theta0
            shape = terms.angle_form(theta0)
            cos0 = np.cos(np.radians(theta0))
            sin0_2 = max(1.0 - cos0 ** 2, 1e-8)
            k2 = 1.0 / (4.0 * sin0_2)
            k1 = -4.0 * k2 * cos0
            k0 = k2 * (2.0 * cos0 ** 2 + 1.0)

            for a in range(len(partners)):
                for b in range(a + 1, len(partners)):
                    (ia, ta, bond_a) = partners[a]
                    (ib, tb, bond_b) = partners[b]
                    i_out.append(ia)
                    j_out.append(centre)
                    k_out.append(ib)
                    si_out.append(ta)
                    sk_out.append(tb)
                    force.append(terms.angle_force_constant(
                        names[ia], names[centre], names[ib], theta0,
                        orders[bond_a], orders[bond_b]))
                    c0.append(k0)
                    c1.append(k1)
                    c2.append(k2)
                    form.append(shape)
                    geminal.add(_pair_key(ia, ib, tb - ta))

        n = len(j_out)
        return terms.AngleTerm(
            _ints(i_out), _ints(j_out), _ints(k_out),
            _shifts(si_out, n), _shifts(sk_out, n),
            np.array(force, dtype=float), np.array(c0, dtype=float),
            np.array(c1, dtype=float), np.array(c2, dtype=float),
            np.array(form, dtype=int)), geminal

    def _torsion_terms(self, names, orders) -> terms.TorsionTerm:
        """Dihedrals about every bond that has a barrier.

        The barrier is worked out for the *bond* and only then split
        between the torsions around it, so the test that skips a bond
        entirely happens before the two nested loops -- which is what
        keeps a six-coordinate metal oxide from enumerating hundreds of
        thousands of dihedrals that all turn out to be worth zero.
        """
        i_out, j_out, k_out, l_out = [], [], [], []
        si, sk, sl = [], [], []
        barrier, periodicity, cosphi0 = [], [], []

        for index, bond in enumerate(self.graph.bonds):
            j, k = bond.i, bond.j
            t_jk = np.array(bond.image, dtype=float)
            near, far = self._adjacency[j], self._adjacency[k]
            v, n, cos0 = terms.torsion_parameters(
                names[j], names[k], orders[index], len(near),
                len(far))
            if v == 0.0:
                continue
            v /= (len(near) - 1) * (len(far) - 1)

            for (i, t_ji, _b1) in near:
                if i == k and np.array_equal(t_ji, t_jk):
                    continue
                for (m, t_kl, _b2) in far:
                    t_jl = t_jk + t_kl
                    if m == j and np.allclose(t_jl, 0.0):
                        continue
                    if i == m and np.allclose(t_ji, t_jl):
                        continue
                    i_out.append(i)
                    j_out.append(j)
                    k_out.append(k)
                    l_out.append(m)
                    si.append(t_ji)
                    sk.append(t_jk)
                    sl.append(t_jl)
                    barrier.append(v)
                    periodicity.append(n)
                    cosphi0.append(cos0)

        count = len(j_out)
        return terms.TorsionTerm(
            _ints(i_out), _ints(j_out), _ints(k_out), _ints(l_out),
            _shifts(si, count), _shifts(sk, count),
            _shifts(sl, count), np.array(barrier, dtype=float),
            np.array(periodicity, dtype=int),
            np.array(cosphi0, dtype=float))

    def _inversion_terms(self, names) -> terms.InversionTerm:
        centre, j, k, m = [], [], [], []
        sj, sk, sm = [], [], []
        force, c0, c1, c2 = [], [], [], []

        for atom in range(self.n_atoms):
            partners = self._adjacency[atom]
            if len(partners) != 3:
                continue
            neighbour_types = {names[p[0]] for p in partners}
            strength, k0, k1, k2 = terms.inversion_parameters(
                names[atom], neighbour_types)
            if strength == 0.0:
                continue
            for out in range(3):
                plane = [partners[x] for x in range(3) if x != out]
                centre.append(atom)
                j.append(plane[0][0])
                k.append(plane[1][0])
                m.append(partners[out][0])
                sj.append(plane[0][1])
                sk.append(plane[1][1])
                sm.append(partners[out][1])
                force.append(strength)
                c0.append(k0)
                c1.append(k1)
                c2.append(k2)

        n = len(centre)
        return terms.InversionTerm(
            _ints(centre), _ints(j), _ints(k), _ints(m),
            _shifts(sj, n), _shifts(sk, n), _shifts(sm, n),
            np.array(force, dtype=float), np.array(c0, dtype=float),
            np.array(c1, dtype=float), np.array(c2, dtype=float))

    def _check_topology(self) -> None:
        unsure = self.typing.unsure()
        if unsure:
            # Worded without reference to any particular interface:
            # this is core code, and the CLI shows it too.
            self.warnings.append(
                f"{len(unsure)} atom(s) have a type the typer is not "
                f"sure of; look at them before trusting the numbers")
        if not len(self.topology.bonds) and self.n_atoms > 1:
            self.warnings.append(
                "no bonds were perceived, so this is a gas of atoms "
                "held together by nothing but van der Waals")

    # ==================================================================
    #  CHARGES
    # ==================================================================

    def _charges(self) -> np.ndarray:
        if not self.options.coulomb:
            return np.zeros(self.n_atoms)
        if self.options.charges == "qeq":
            from xtal.ff.uff import qeq
            charges, note = qeq.equilibrate(
                self.cell, self.typing.names)
            if note:
                self.warnings.append(note)
            return charges
        if self.options.charges == "zero":
            return np.zeros(self.n_atoms)

        charges = np.array(
            [self.structure.sites[int(s)].charge or 0.0
             for s in self.cell.site_idx], dtype=float)
        if not np.any(charges):
            self.warnings.append(
                "electrostatics are on but every site has a charge of "
                "zero, so the Coulomb term contributes nothing; set "
                "charges on the sites or switch to QEq")
        elif abs(charges.sum()) > 1e-6:
            self.warnings.append(
                f"the cell carries a net charge of {charges.sum():+.3f}"
                f" e; a uniform neutralising background is assumed")
        return charges

    # ==================================================================
    #  EVALUATION
    # ==================================================================

    def compute(self, positions, matrix) -> Result:
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        matrix = np.asarray(matrix, dtype=float).reshape(3, 3)
        if len(positions) != self.n_atoms:
            raise CalculatorError(
                f"expected {self.n_atoms} positions, got "
                f"{len(positions)}")

        total = 0.0
        grad = np.zeros_like(positions)
        breakdown = {}
        for name, term in (("bond", self.topology.bonds),
                           ("angle", self.topology.angles),
                           ("torsion", self.topology.torsions),
                           ("inversion", self.topology.inversions)):
            energy, g = term.energy_and_gradient(positions, matrix)
            breakdown[name] = energy
            total += energy
            grad += g

        if self.options.vdw:
            self._refresh_pairs(positions, matrix)
            energy, g = self._vdw.energy_and_gradient(positions,
                                                      matrix)
            breakdown["van der Waals"] = energy
            total += energy
            grad += g

        if self.options.coulomb and np.any(self.charges):
            self._refresh_pairs(positions, matrix)
            energy, g = ewald.energy_and_gradient(
                positions, matrix, self.charges, self._coulomb_pairs,
                excluded=self._coulomb_excluded, setup_=self._ewald,
                dielectric=self.options.dielectric)
            breakdown["electrostatic"] = energy
            total += energy
            grad += g

        return Result(total, -grad, breakdown)

    def _refresh_pairs(self, positions, matrix) -> None:
        """Rebuild the neighbour lists if an atom has outrun the skin.

        Half the skin, not the whole of it: two atoms can approach each
        other from opposite directions, so each of them only has to
        move half the distance for a pair that was outside the built
        radius to be inside the cutoff.
        """
        if self._pairs_built_at is not None:
            moved = np.linalg.norm(positions - self._pairs_built_at,
                                   axis=1).max()
            if moved < 0.5 * self.options.skin:
                return
        self._build_pairs(positions, matrix)

    def _build_pairs(self, positions, matrix) -> None:
        from xtal.core.lattice import Lattice

        lattice = Lattice(matrix)
        frac = positions @ np.linalg.inv(matrix)
        radius = self.options.vdw_cutoff + self.options.skin
        pairs = neighbors.neighbor_pairs(frac, lattice, radius)
        if len(pairs):
            codes = pair_codes(pairs.i, pairs.j, pairs.image,
                               self.n_atoms)
            keep = ~np.isin(codes, self.topology.excluded_codes)
        else:
            keep = np.zeros(0, dtype=bool)
        i, j, image = pairs.i[keep], pairs.j[keep], pairs.image[keep]

        ids = self._type_ids
        x = self._vdw_x[ids[i], ids[j]]
        d = self._vdw_d[ids[i], ids[j]]
        cutoff = self.options.vdw_cutoff
        ratio6 = (x / cutoff) ** 6
        self._vdw = terms.VanDerWaalsTerm(
            i, j, image.astype(float), x, d, cutoff=cutoff,
            shift_energy=d * (ratio6 ** 2 - 2.0 * ratio6))

        if self.options.coulomb:
            self._coulomb_pairs = (i, j, image.astype(float))
            self._coulomb_excluded = self._excluded_pairs(pairs, keep)
            self._ewald = ewald.setup(
                matrix, real_cutoff=self.options.vdw_cutoff,
                accuracy=self.options.ewald_accuracy)
        self._pairs_built_at = positions.copy()

    def _excluded_pairs(self, pairs, keep):
        drop = ~keep
        return (pairs.i[drop], pairs.j[drop],
                pairs.image[drop].astype(float))


# ======================================================================
#  HELPERS
# ======================================================================

def _adjacency(graph) -> list[list[tuple]]:
    """``atom -> [(neighbour, translation, bond index)]``.

    The bond index is why this is built here rather than taken from
    :class:`~xtal.core.bonding.BondGraph`: the bond orders the typer
    inferred are stored per bond, and every angle and torsion needs to
    get back to them.
    """
    out: list[list[tuple]] = [[] for _ in range(graph.n_atoms)]
    for index, bond in enumerate(graph.bonds):
        shift = np.array(bond.image, dtype=float)
        out[bond.i].append((bond.j, shift, index))
        out[bond.j].append((bond.i, -shift, index))
    return out


# Lattice translations are packed into eight bits per axis, which is a
# cutoff reaching 127 cells in one direction: further than any real
# calculation and far enough that the check below has never fired.
SHIFT_LIMIT = 127
_SHIFT_BASE = 2 * SHIFT_LIMIT + 1


def canonical_pairs(i, j, shift):
    """``(i, j, shift)`` named the same way from either end.

    The array form of :func:`_pair_key`'s convention, and it has to
    stay exactly that: lower index first, and for an atom paired with
    its own periodic image, the lexicographically positive
    translation.
    """
    i = np.asarray(i, dtype=np.int64).ravel()
    j = np.asarray(j, dtype=np.int64).ravel()
    shift = np.asarray(shift, dtype=np.int64).reshape(-1, 3)

    swapped = i > j
    low = np.where(swapped, j, i)
    high = np.where(swapped, i, j)
    shift = np.where(swapped[:, None], -shift, shift)

    # Self-pairs: +t and -t describe the same contact, so take one.
    same = low == high
    if same.any():
        flip = same & ~neighbors.lexicographically_positive(shift)
        shift = np.where(flip[:, None], -shift, shift)
    return low, high, shift


def pair_codes(i, j, shift, n_atoms: int) -> np.ndarray:
    """One int64 per pair, equal exactly when :func:`_pair_key` is.

    Built for the same reason the neighbour search was rewritten: the
    exclusion test runs once per pair, there are half a million pairs
    in a five-thousand-atom cell, and constructing a tuple for each of
    them cost a third of the time in a rebuild.
    """
    low, high, shift = canonical_pairs(i, j, shift)
    if len(shift) and np.abs(shift).max() > SHIFT_LIMIT:
        raise ValueError(
            f"a lattice translation of more than {SHIFT_LIMIT} cells "
            f"cannot be packed into a pair code")
    limit = np.int64(2) ** 62 // (_SHIFT_BASE ** 3)
    if n_atoms and n_atoms ** 2 > limit:
        raise ValueError(
            f"{n_atoms} atoms is too many to pack a pair code for")

    code = low * np.int64(n_atoms) + high
    for axis in range(3):
        code = code * _SHIFT_BASE + (shift[:, axis] + SHIFT_LIMIT)
    return code


def _codes_of(keys, n_atoms: int) -> np.ndarray:
    """Pair codes for a set of :func:`_pair_key` tuples, sorted so
    ``np.isin`` can binary-search them."""
    if not keys:
        return np.zeros(0, dtype=np.int64)
    listed = list(keys)
    i = np.fromiter((k[0] for k in listed), dtype=np.int64,
                    count=len(listed))
    j = np.fromiter((k[1] for k in listed), dtype=np.int64,
                    count=len(listed))
    shift = np.array([k[2] for k in listed], dtype=np.int64)
    return np.unique(pair_codes(i, j, shift, n_atoms))


def _pair_key(i: int, j: int, shift) -> tuple:
    """A pair named the same way whichever end it is read from.

    Matches the convention of :func:`xtal.core.neighbors.neighbor_pairs`
    -- lower index first, and for an atom paired with its own periodic
    image, the lexicographically positive translation -- so exclusions
    built from the bond graph match the pairs the neighbour search
    hands back.
    """
    shift = tuple(int(round(float(v))) for v in shift)
    if i < j:
        return (i, j, shift)
    if i > j:
        return (j, i, tuple(-v for v in shift))
    flipped = tuple(-v for v in shift)
    return (i, j, max(shift, flipped))


def _ints(values) -> np.ndarray:
    return np.array(values, dtype=int) if values else np.zeros(0, int)


def _shifts(values, n: int) -> np.ndarray:
    if not n:
        return np.zeros((0, 3))
    return np.array(values, dtype=float).reshape(n, 3)


def build(structure, **options) -> UFFCalculator:
    """Registry entry point: keyword options in, calculator out."""
    rules = options.pop("rules", None)
    return UFFCalculator(structure, UFFOptions(**options), rules)


ENGINES.register(Engine(
    name="uff",
    label="UFF",
    description="Universal Force Field (Rappe et al. 1992) -- covers "
                "the whole periodic table, native and in-process",
    build=build,
    provides=frozenset({"forces", "stress", "charges", "periodic"}),
))
