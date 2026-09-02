"""
xtal.ff.hydrogens
=================
Putting back the hydrogens an X-ray structure never had.

X-rays scatter off electrons, so the one atom with almost none is the
one a refinement usually leaves out.  Everything downstream then works
from a molecule that is missing a quarter of its atoms: the typer sees
a benzene carbon with two neighbours and a methyl carbon with one and
says so in its reason; the energy is computed over a structure that
does not exist; and a relaxation moves the heavy atoms to compensate
for the hydrogens that are not pushing back.  Putting them back is the
single most useful thing that can happen before an energy is believed.

Four decisions make that a computation rather than a guess.

**The coordination decides where.**  A three-coordinate sp3 carbon has
one direction left in its tetrahedron; a two-coordinate sp2 carbon has
one left in its plane; a one-coordinate sp3 carbon has three, on a
cone.  Which of those a given atom is, is a question
:mod:`xtal.ff.uff.typer` already answers -- and answers with a
sentence saying why -- so this module reads the typing rather than
looking at the geometry a second time.

**The valence decides how many.**  ``elements.VALENCE`` less the bond
orders already used, where the orders are the ones the typer inferred.
The table covers the main group and that is the right scope: nobody
wants hydrogens guessed onto a metal, and an element it has no entry
for is left alone *and reported*, not skipped in silence.  An atom
with no bonds at all is left alone too -- there is no coordination to
complete, and a bare oxygen in a cell is as likely to be an ion as a
water molecule.

**The force field decides how far.**
``terms.natural_bond_length(type, "H_", 1.0)`` puts C-H at 1.109 and
O-H at 0.990, so the hydrogen arrives already sitting at the minimum
of the potential it is about to be relaxed in.  Those are the neutron
distances.  X-ray hydrogens refine about 0.1 A short, because what is
being fitted is the centroid of a bonding electron cloud rather than a
nucleus; that is a real difference and it is offered
(:data:`X_RAY_SHORTENING`), not defaulted to.

**Symmetry decides how many there really are.**  This works in site
space like every other edit, so one hydrogen added to a site of
multiplicity four is four hydrogens in the cell, and two hydrogens
placed either side of a mirror plane are *one* site, not two.  Both
have to be true of the number reported -- "12 hydrogens on 2 sites" --
or the preview is a lie about what the button does.

**A dummy atom is not chemistry**, so it is held back at the door --
:func:`xtal.ff.markers.hold_back`, the same door the engines use.
``X`` marks a position: the centre of a ring, the vertex of a net.  A
bond somebody drew to one would otherwise spend valence at the atom it
came from, and the hydrogen that atom is actually missing would never
be offered.  Nothing has to put the markers back -- unlike a module,
this hands back coordinates for new atoms rather than a structure --
and the command adds those to the structure the user still has,
markers and all.

What is deliberately not here: a torsion that is actually determined.
A hydroxyl, a methyl and an amine have every angle fixed by the
coordination and nothing at all fixing the rotation, so they are placed
staggered against the heaviest atom two bonds away, that assumption is
written into the report, and a relaxation is left to settle it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.core import bonding, elements, p1
from xtal.core.site import Site
from xtal.ff import markers
from xtal.ff.uff import params, terms, typer

#: Hydrogens refined against X-ray data sit about this much closer to
#: their neighbour than the nucleus really is.  Offered, never assumed.
X_RAY_SHORTENING = 0.10

#: How many directions each hybridisation has to share out, bonds and
#: lone pairs together.  This is the steric number, and it is why water
#: comes out bent: sp3 oxygen has four directions, two of them taken by
#: lone pairs the model never draws.
IDEAL_DIRECTIONS = {"sp": 2, "sp2": 3, "sp3": 4}

#: Two placed hydrogens closer than this (Angstrom) are the same atom
#: seen twice through the symmetry.  Far above the noise of an exact
#: operation and far below the shortest H...H distance in anything
#: real, which is about 1.7 A.
SAME_ATOM_TOL = 0.05

_DEGENERATE = 1e-8
#: Sentinel: this atom was left alone for being a metal.  Collected
#: into a single line rather than repeated per atom.
_METAL = "\x00metal"


@dataclass(frozen=True)
class HydrogenPlan:
    """What adding hydrogens would do, before it is done.

    A plan is computed from a structure and never mutates it, which is
    what lets the dialog show the count while the user is still
    deciding and the command reuse the same answer when they say yes.
    """

    sites: tuple[Site, ...] = ()
    #: Atoms in the cell, not sites: the orbit count, which is the
    #: number the user is actually about to add.
    n_atoms: int = 0
    n_parents: int = 0
    notes: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    multiplicity: tuple[int, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.sites)

    def message(self) -> str:
        if not self.sites:
            return "no hydrogens to add"
        sites = ("1 site" if len(self.sites) == 1
                 else f"{len(self.sites)} sites")
        parents = ("1 atom" if self.n_parents == 1
                   else f"{self.n_parents} atoms")
        return (f"added {self.n_atoms} hydrogen"
                f"{'' if self.n_atoms == 1 else 's'} to {parents} "
                f"({sites} in the asymmetric unit)")

    def report(self) -> str:
        """The message, then every assumption that went into it."""
        lines = [self.message()]
        if self.notes:
            lines.append("")
            lines.extend(self.notes)
        if self.skipped:
            lines.append("")
            lines.append("left alone:")
            lines.extend(f"  {s}" for s in self.skipped)
        return "\n".join(lines)


# ======================================================================
#  THE PLAN
# ======================================================================

def plan(structure, rules: bonding.BondRules | None = None,
         xray: bool = False) -> HydrogenPlan:
    """Where the missing hydrogens of ``structure`` would go.

    ``xray`` shortens every bond by :data:`X_RAY_SHORTENING`, for
    comparing against a structure whose other hydrogens were refined
    against X-ray data.
    """
    structure, _kept = markers.hold_back(structure)
    cell = p1.expand(structure)
    if cell.n_atoms == 0:
        return HydrogenPlan()
    graph = bonding.graph(structure, rules)
    typing = typer.assign(structure, rules)
    geometry = typer.Geometry(cell, graph)
    used = _orders_used(graph, typing)
    lattice = structure.lattice
    ops = structure.space_group.operations

    sites: list[Site] = []
    multiplicity: list[int] = []
    notes: list[str] = []
    skipped: list[str] = []
    taken: list[np.ndarray] = []        # orbits already accounted for
    parents = 0

    metals: list[str] = []
    for index, site in enumerate(structure.sites):
        atom = _representative(cell, index)
        if atom is None:
            continue
        name = site.label or f"{site.element}{index}"
        wanted, why = _how_many(site, atom, cell, geometry, typing,
                                used)
        if wanted <= 0:
            if why == _METAL:
                metals.append(site.element)
            elif why:
                skipped.append(f"{name}: {why}")
            continue

        type_name = typing.types[atom].name
        directions, note = _directions(atom, geometry, cell,
                                       type_name, wanted)
        if not len(directions):
            skipped.append(f"{name}: {note}")
            continue
        note = "; ".join(w for w in (why, note) if w)
        length = terms.natural_bond_length(type_name, "H_", 1.0)
        if xray:
            length = max(length - X_RAY_SHORTENING, 0.1)

        # Built from the site's own coordinates and not from the cell
        # atom's: the cell is wrapped into [0,1) and the site may not
        # be, and a hydrogen that came back on the far side of the box
        # from the atom it belongs to is correct as a crystal and
        # useless as a molecule.
        added = 0
        for direction in directions:
            frac = site.frac + lattice.to_frac(direction * length)
            orbit = _orbit(frac, ops, lattice)
            if _already_there(frac, taken, lattice):
                continue
            taken.append(orbit)
            sites.append(Site("H", frac, occupancy=site.occupancy))
            multiplicity.append(len(orbit))
            added += 1
        if not added:
            continue
        parents += 1
        detail = f" ({note})" if note else ""
        notes.append(f"{name}: {added} hydrogen"
                     f"{'' if added == 1 else 's'} at "
                     f"{length:.3f} A{detail}")

    if metals:
        listed = ", ".join(sorted(set(metals)))
        skipped.append(
            f"{len(metals)} metal site(s) ({listed}) -- what a metal "
            f"is missing is a coordination number and not a valence, "
            f"so no hydrogen is guessed onto one")

    return HydrogenPlan(
        sites=tuple(sites),
        n_atoms=int(sum(multiplicity)),
        n_parents=parents,
        notes=tuple(notes),
        skipped=tuple(skipped),
        multiplicity=tuple(multiplicity),
    )


def _orders_used(graph, typing) -> np.ndarray:
    """Bond order already spent at each atom of the cell.

    The orders are the typer's, which is the point: they are the same
    numbers the energy will be computed with, so an aromatic carbon is
    judged to be carrying 3.0 and not 2.
    """
    out = np.zeros(graph.n_atoms)
    for k, bond in enumerate(graph.bonds):
        order = float(typing.bond_orders[k])
        out[bond.i] += order
        out[bond.j] += order
    return out


def _representative(cell, index: int) -> int | None:
    """The atom of the cell that *is* this site.

    Any image of the site would give the same orbit of hydrogens, but
    the identity one keeps the new coordinates in the setting the user
    is looking at.
    """
    atoms = cell.indices_of_site(index)
    if not len(atoms):
        return None
    for atom in atoms:
        if int(cell.op_idx[atom]) == 0:
            return int(atom)
    return int(atoms[0])                            # pragma: no cover


def _how_many(site, atom: int, cell, geometry, typing,
              used) -> tuple[int, str]:
    """``(hydrogens wanted, why not)`` for one atom.

    Refusals are returned rather than raised: a structure is a mixture
    of atoms that need hydrogens, atoms that do not and atoms nobody
    should guess at, and the useful answer covers the first while
    naming the third.
    """
    element = site.element
    if element in ("H", "D"):
        return 0, ""
    try:
        metal = elements.element(element).is_metal
    except ValueError:                              # pragma: no cover
        return 0, f"{element} is not an element this can reason about"
    if metal:
        # Sodium is in the valence table with a valence of one, and a
        # sodium hydride is not what anybody meant.  Reported, but
        # collected into one line by the caller: a framework has
        # hundreds of metal atoms and a line each would bury
        # everything worth reading.
        return 0, _METAL
    valence = elements.VALENCE.get(element)
    if valence is None:
        return 0, (f"no valence is tabulated for {element}, so how "
                   f"many hydrogens it is missing is not something "
                   f"this can work out")
    if geometry.coordination(atom) == 0:
        return 0, ("no neighbours, so there is no coordination to "
                   "complete")
    missing = int(round(valence - used[atom]))
    if missing <= 0:
        return 0, ""

    hybridisation = terms.hybridisation(typing.types[atom].name)
    ideal = IDEAL_DIRECTIONS.get(hybridisation)
    if ideal is None:
        return 0, (f"typed {typing.types[atom].name}, which has no "
                   f"hybridisation to complete")
    free = ideal - geometry.coordination(atom)
    if free <= 0:
        return 0, (f"already has {geometry.coordination(atom)} "
                   f"neighbours, which is every direction "
                   f"{typing.types[atom].name} has")
    if missing > free:
        return free, (f"missing {missing} hydrogens by valence but "
                      f"has room for {free}; {free} placed")
    return missing, ""


# ======================================================================
#  WHERE THEY GO
# ======================================================================

def _directions(atom: int, geometry, cell, type_name: str,
                count: int) -> tuple[np.ndarray, str]:
    """``count`` unit vectors completing this atom's coordination.

    The existing bonds are fixed and the rest of the ideal geometry is
    built around them, at the equilibrium angle the force field itself
    uses for the type -- 109.47 for an sp3 carbon, 104.51 for an sp3
    oxygen, 120 for anything trigonal.  So a water oxygen comes out
    bent and not linear, which is the whole reason the angle is read
    from the type instead of from the coordination number.
    """
    existing = _unit(geometry.vectors(atom))
    theta = np.radians(params.get(type_name).theta0)
    n = len(existing)

    if n == 1:
        axis = existing[0]
        reference, note = _stagger_reference(atom, geometry, cell,
                                             axis)
        slots = max(IDEAL_DIRECTIONS.get(
            terms.hybridisation(type_name), n + count) - 1, count)
        return _cone(axis, theta, slots, reference)[:count], note
    if n == 2:
        return _from_two(existing, theta, count)
    if n >= 3:
        return _from_many(existing, count)
    return np.zeros((0, 3)), "no neighbours to build a direction from"


def _cone(axis: np.ndarray, theta: float, slots: int,
          reference: np.ndarray) -> np.ndarray:
    """``slots`` directions at ``theta`` from ``axis``, evenly spaced.

    ``reference`` is where the azimuth starts, and it is what makes a
    methyl staggered rather than eclipsed: the first direction is put
    opposite the heaviest atom two bonds away, and the others follow it
    round.
    """
    e1 = _normalize(-reference)
    e2 = np.cross(axis, e1)
    if np.linalg.norm(e2) < _DEGENERATE:            # pragma: no cover
        e1 = _perpendicular(axis)
        e2 = np.cross(axis, e1)
    e2 = _normalize(e2)
    out = []
    for k in range(max(slots, 1)):
        psi = 2.0 * np.pi * k / max(slots, 1)
        out.append(np.cos(theta) * axis
                   + np.sin(theta) * (np.cos(psi) * e1
                                      + np.sin(psi) * e2))
    return np.array([_normalize(d) for d in out])


def _from_two(existing: np.ndarray, theta: float,
              count: int) -> tuple[np.ndarray, str]:
    """One or two directions opposite a pair of existing bonds."""
    bisector = existing[0] + existing[1]
    if np.linalg.norm(bisector) < _DEGENERATE:
        # The two bonds are collinear, so "opposite both" is a whole
        # circle of directions and any of them is as good.
        bisector = _perpendicular(existing[0])
    bisector = _normalize(-bisector)
    if count == 1:
        return bisector[None, :], ""
    normal = np.cross(existing[0], existing[1])
    if np.linalg.norm(normal) < _DEGENERATE:        # pragma: no cover
        normal = _perpendicular(bisector)
    normal = _normalize(normal)
    half = theta / 2.0
    pair = np.array([np.cos(half) * bisector + np.sin(half) * normal,
                     np.cos(half) * bisector - np.sin(half) * normal])
    return np.array([_normalize(d) for d in pair])[:count], ""


def _from_many(existing: np.ndarray,
               count: int) -> tuple[np.ndarray, str]:
    """The one direction left when three bonds are already there."""
    total = existing.sum(axis=0)
    if np.linalg.norm(total) < _DEGENERATE:
        return (np.zeros((0, 3)),
                "its three bonds are flat and symmetric, which leaves "
                "no direction for a fourth")
    return _normalize(-total)[None, :][:count], ""


def _stagger_reference(atom: int, geometry, cell,
                       axis: np.ndarray) -> tuple[np.ndarray, str]:
    """Which way is "eclipsed", and how sure we are.

    A terminal group's torsion is genuinely undetermined: the
    coordination fixes every angle at the atom and nothing whatever
    fixes the rotation about the bond it hangs from.  The convention
    here is the one a chemist would draw -- staggered against the
    heaviest atom two bonds away -- and it is reported as an
    assumption, because that is what it is.
    """
    partner = geometry.partners(atom)[0]
    best, best_mass, name = None, -1.0, ""
    for other, vector in zip(geometry.partners(partner),
                             geometry.vectors(partner), strict=True):
        if other == atom:
            continue
        perpendicular = vector - float(vector @ axis) * axis
        if np.linalg.norm(perpendicular) < 1e-6:
            continue                    # straight along the bond
        mass = elements.mass(cell.elements[other])
        if mass > best_mass:
            best, best_mass = perpendicular, mass
            name = cell.labels[other] or cell.elements[other]
    if best is None:
        return (_perpendicular(axis),
                "the rotation about this bond is undetermined and was "
                "chosen arbitrarily")
    return (_normalize(best),
            f"staggered against {name}; the rotation about this bond "
            f"is undetermined and a relaxation will settle it")


# ======================================================================
#  SYMMETRY
# ======================================================================

def _orbit(frac, ops, lattice) -> np.ndarray:
    """The distinct positions this one would generate.

    The same coincidence test :mod:`xtal.core.p1` applies, and for the
    same reason: a hydrogen that lands on a mirror plane is one atom,
    and generating it twice would double it in the cell.
    """
    generated = _wrap(np.array([op.apply(frac) for op in ops]))
    keep: list[np.ndarray] = []
    for point in generated:
        if not _near(point, keep, lattice, p1.SPECIAL_POSITION_TOL):
            keep.append(point)
    return np.array(keep)


def _already_there(frac, taken: list, lattice) -> bool:
    """Has some earlier hydrogen's orbit already put an atom here?

    Two hydrogens either side of a mirror plane are one site, not two,
    and adding both would put two atoms on top of each other in the
    cell -- the failure that makes a structure look right and count
    wrong.
    """
    for orbit in taken:
        if _near(frac, list(orbit), lattice, SAME_ATOM_TOL):
            return True
    return False


def _near(frac, points, lattice, tol: float) -> bool:
    if not len(points):
        return False
    d = np.asarray(points) - np.asarray(frac)
    d -= np.round(d)
    return bool((np.linalg.norm(d @ lattice.matrix, axis=1)
                 < tol).any())


# ======================================================================
#  SMALL VECTOR HELPERS
# ======================================================================

def _wrap(frac):
    w = np.mod(np.asarray(frac, dtype=float), 1.0)
    return np.where(np.abs(w - 1.0) < 1e-12, 0.0, w)


def _normalize(v):
    v = np.asarray(v, dtype=float)
    norm = np.linalg.norm(v)
    return v / norm if norm > _DEGENERATE else v


def _unit(vectors) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=float)
    if not len(vectors):
        return vectors
    return np.array([_normalize(v) for v in vectors])


def _perpendicular(v) -> np.ndarray:
    """Any unit vector at right angles to ``v``."""
    other = (np.array([1.0, 0.0, 0.0])
             if abs(float(v[0])) < 0.9 else np.array([0.0, 1.0, 0.0]))
    return _normalize(np.cross(v, other))
