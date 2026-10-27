"""
xtal.fullerene.build
====================
A recipe to a structure: a fullerene cage, alone in a box, its bonds
stated and nothing perceived.

**The cage is the table's or a typed spiral's.**  A size and an isomer
number pick a row of :mod:`xtal.fullerene.catalogue`; a spiral typed
as its twelve pentagon places builds any cage that has one, below the
:data:`MAX_ATOMS` this builder takes, and is named after the table's
row when it is one of them.

**One element.**  Every cage has twelve pentagons and a pentagon is an
odd ring, so two elements cannot alternate round it the way B and N
do on a sheet: two are refused saying so.

**The geometry is a shape, then UFF** (by default): topological
coordinates and springs (:mod:`xtal.fullerene.geometry`) put the atoms
on a closed surface at the bond asked for, and UFF relaxes them over
the stated graph in a fixed box.  UFF types every carbon of a bare
cage C_R, so its bonds come out the same length where C60's alternate
1.40 and 1.45 A; the report says so.  Hydrogenated puts one hydrogen
on every atom, pointing out of the cage -- C60H60 -- at UFF's sp3 X-H
length, and the cage's bond is then the single bond.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

import numpy as np

from xtal.carbon import honeycomb
from xtal.core import pyykko
from xtal.fullerene import catalogue, geometry, spiral
from xtal.fullerene.spiral import FullereneError

__all__ = ["RELAX", "MAX_ATOMS", "Recipe", "Built", "FullereneError",
           "checked", "build", "parse_spiral"]

RELAX = ("uff", "none")

#: The largest cage a typed spiral may build.  Every fullerene below
#: C380 has a spiral, and the springs and the canonical spiral are
#: quadratic-ish in the faces: C500 is a few seconds.
MAX_ATOMS = 500


@dataclass(frozen=True)
class Recipe:
    """The form's values."""

    n: int = 60
    #: Counted from 1 in the table's order; 0 is the size's default.
    isomer: int = 0
    #: Twelve pentagon places, counted from 1; "" is the table's row.
    spiral: str = ""
    element: str = "C"
    #: None is the element's own bond, from Pyykkö's radii; the form
    #: hands text, "" for none, which :func:`checked` reads.
    bond: float | str | None = None
    hydrogenate: bool = False
    relax: str = "uff"
    relax_steps: int = 500
    vacuum: float = 12.0

    @property
    def bond_length(self) -> float:
        """The cage's bond: the one given, or the element's from
        Pyykkö's radii -- aromatic for a bare cage, single for one
        with a hydrogen on every atom."""
        given = honeycomb.given_bond(self.bond, FullereneError)
        if given is not None:
            return given
        if self.hydrogenate:
            return 2.0 * pyykko.SINGLE[_radius_key(self.element)] / 100.0
        return pyykko.aromatic_bond(self.element, self.element)

    @property
    def from_radii(self) -> bool:
        return honeycomb.given_bond(self.bond, FullereneError) is None


def _radius_key(symbol: str) -> str:
    return "H" if symbol == "D" else symbol


def parse_spiral(text: str) -> tuple[int, ...]:
    """Twelve pentagon places from the form's text: commas or spaces
    between them."""
    words = [w for w in re.split(r"[\s,;]+", str(text).strip()) if w]
    try:
        places = tuple(int(w) for w in words)
    except ValueError:
        raise FullereneError(
            f"a spiral is twelve whole numbers, the pentagons' places; "
            f"{text.strip()!r} is not") from None
    if len(places) != 12:
        raise FullereneError(f"a spiral names twelve pentagons, not "
                             f"{len(places)}")
    return places


def checked(recipe: Recipe) -> Recipe:
    """The recipe with its element spelled properly, or a
    :class:`FullereneError` saying what is wrong with it."""
    words = [w for w in re.split(r"[\s,/;]+", str(recipe.element).strip())
             if w]
    if len(words) > 1:
        raise FullereneError(
            "a fullerene takes one element: its twelve pentagons are "
            "odd rings, so two elements cannot alternate round it")
    element = honeycomb.element_symbol(words[0] if words else "",
                                       FullereneError)
    spiral.check_size(recipe.n)
    if recipe.n > MAX_ATOMS:
        raise FullereneError(f"C{recipe.n} is over the {MAX_ATOMS} "
                             f"atoms this builder takes")
    if recipe.relax not in RELAX:
        raise FullereneError(f"relax must be one of {', '.join(RELAX)}, "
                             f"not {recipe.relax!r}")
    if recipe.spiral.strip():
        spiral.pentagons_of(recipe.n, parse_spiral(recipe.spiral))
    else:
        catalogue.isomer(recipe.n, recipe.isomer or
                         catalogue.default(recipe.n).number)
    return replace(recipe, element=element,
                   bond=honeycomb.given_bond(recipe.bond, FullereneError))


@dataclass
class Built:
    """What came out, and what the report says about it."""

    recipe: Recipe
    structure: object
    #: The table's row, or None for a typed spiral that is in no row.
    isomer: catalogue.Isomer | None
    spiral: tuple
    order: int
    pentagon_pairs: int
    hydrogens: int
    shortest_bond: float
    longest_bond: float
    diameter: float
    closest_contact: float
    relaxed: str = ""
    notes: tuple = field(default_factory=tuple)

    @property
    def ipr(self) -> bool:
        return self.pentagon_pairs == 0

    @property
    def title(self) -> str:
        return title_of(self.recipe, self.isomer)

    def lines(self) -> list[str]:
        out = [f"{self.title}: {len(self.structure.sites)} atoms, "
               f"{self.diameter:.2f} A across",
               f"bonds {self.shortest_bond:.3f} to "
               f"{self.longest_bond:.3f} A"]
        if self.relaxed:
            out.append(self.relaxed)
        return out + list(self.notes)


def title_of(recipe: Recipe, isomer) -> str:
    """``C60-Ih``, ``Si60-Ih``, ``C60H60-Ih``, or the size and
    "isomer k" where no group is named."""
    formula = f"{recipe.element}{recipe.n}"
    if recipe.hydrogenate:
        formula += f"H{recipe.n}"
    if isomer is None:
        return formula
    if isomer.group:
        return f"{formula}-{isomer.group}"
    kind = "IPR isomer" if not isomer.complete else "isomer"
    return f"{formula} {kind} {isomer.number}"


def build(recipe: Recipe, say=None) -> Built:
    """Wind the cage up, place its atoms, cap and relax it."""
    from xtal.carbon.build import closest_contact
    from xtal.carbon.lattice import structure_of

    recipe = checked(recipe)
    say = say or (lambda _text: None)
    notes = []
    isomer, places, order = _cage_of(recipe, notes)
    rotation = spiral.wind(recipe.n, places)
    atoms, bonds = spiral.cage(rotation)
    pairs = sum(1 for f, around in enumerate(rotation)
                if len(around) == 5
                for g in around if g > f and len(rotation[g]) == 5)
    say(f"{title_of(recipe, isomer)}: {len(atoms)} atoms, "
        f"{len(bonds)} bonds")

    bond = recipe.bond_length
    cage = geometry.positions(len(atoms), bonds, bond)
    names = [recipe.element] * len(atoms)
    all_bonds = list(bonds)
    xyz = cage
    if recipe.hydrogenate:
        caps = _hydrogens(cage, bonds, _xh_length(recipe.element))
        xyz = np.vstack([cage, caps])
        names += ["H"] * len(caps)
        all_bonds += [(k, len(atoms) + k) for k in range(len(caps))]
    extent = float(np.ptp(xyz, axis=0).max())
    side = extent + recipe.vacuum
    matrix = np.eye(3) * side
    frac = (xyz - (xyz.max(axis=0) + xyz.min(axis=0)) / 2.0) / side + 0.5
    structure = structure_of(
        honeycomb.Atoms(matrix=matrix, elements=names, frac=frac,
                        bonds=np.array(all_bonds, int),
                        images=np.zeros((len(all_bonds), 3), int)),
        title=title_of(recipe, isomer))

    relaxed = ""
    if recipe.relax == "uff":
        say("relaxing with UFF in a fixed box")
        relaxed = _relax(structure, recipe.relax_steps)
        if recipe.element == "C" and not recipe.hydrogenate:
            notes.append("UFF types every carbon C_R, so the bonds come "
                         "out about equal; C60's alternate 1.40 and "
                         "1.45 A")
    if pairs:
        notes.append(f"{pairs} pentagon-pentagon "
                     f"{'bond' if pairs == 1 else 'bonds'}: not an "
                     f"isolated-pentagon cage")

    cart = np.array([s.frac for s in structure.sites]) @ matrix
    edges = np.array(bonds)
    lengths = np.linalg.norm(cart[edges[:, 0]] - cart[edges[:, 1]], axis=1)
    shell = cart[:len(atoms)]
    across = np.linalg.norm(shell[:, None] - shell[None], axis=2).max()
    return Built(recipe=recipe, structure=structure, isomer=isomer,
                 spiral=tuple(places), order=order,
                 pentagon_pairs=pairs,
                 hydrogens=len(names) - len(atoms),
                 shortest_bond=float(lengths.min()),
                 longest_bond=float(lengths.max()),
                 diameter=float(across),
                 closest_contact=closest_contact(structure),
                 relaxed=relaxed, notes=tuple(notes))


def _cage_of(recipe: Recipe, notes):
    """The table's row (or None), the spiral to wind and the order of
    the cage's point group."""
    if not recipe.spiral.strip():
        row = catalogue.isomer(recipe.n, recipe.isomer
                               or catalogue.default(recipe.n).number)
        return row, row.spiral, row.order
    places = tuple(sorted(parse_spiral(recipe.spiral)))
    canonical, order = spiral.canonical(spiral.wind(recipe.n, places))
    if canonical != places:
        notes.append("the spiral typed is not the cage's canonical "
                     "one, which is "
                     + " ".join(str(p) for p in canonical))
    if recipe.n in catalogue.sizes():
        for row in catalogue.isomers(recipe.n):
            if row.spiral == canonical:
                return row, canonical, order
    return None, canonical, order


def _hydrogens(cage, bonds, length) -> np.ndarray:
    """One hydrogen per atom, ``length`` out along the way the atom
    leans away from its three neighbours -- outward on a convex cage."""
    n = len(cage)
    total = np.zeros_like(cage)
    count = np.zeros(n)
    for a, b in bonds:
        total[a] += cage[b]
        total[b] += cage[a]
        count[a] += 1
        count[b] += 1
    out = cage - total / count[:, None]
    radial = cage - cage.mean(axis=0)
    flip = np.einsum("ij,ij->i", out, radial) < 0
    out[flip] *= -1
    weak = np.linalg.norm(out, axis=1) < 1e-6
    out[weak] = radial[weak]
    out /= np.linalg.norm(out, axis=1)[:, None]
    return cage + length * out


def _xh_length(symbol: str) -> float:
    """UFF's natural X-H bond for an sp3 ``symbol``, else the sp2 one
    the nanotube's caps use."""
    from xtal.ff.uff import params, terms

    name = f"{symbol}_3"
    if name in params.types_for(symbol):
        return terms.natural_bond_length(name, "H_", 1.0)
    return honeycomb.hydrogen_length(symbol)


def _relax(structure, steps: int) -> str:
    """UFF in the fixed box, positions only, over the stated bonds."""
    from xtal.core.structure import Change
    from xtal.ff import optimize
    from xtal.ff.registry import ENGINES

    calculator = ENGINES.build("uff", structure)
    result = optimize.run(calculator, structure, method="lbfgs",
                          max_steps=steps)
    for site, frac in zip(structure.sites, result.frac, strict=True):
        site.frac = np.asarray(frac, float)
    structure.touch(Change.POSITIONS)
    state = "converged" if result.converged else "not converged"
    return (f"UFF in a fixed box: {result.steps} steps, {state}, "
            f"max force {result.max_force:.2f} kcal/mol/A")
