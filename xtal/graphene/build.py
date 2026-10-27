"""
xtal.graphene.build
===================
A recipe to a structure: honeycomb sheets, stacked, their bonds
stated and nothing perceived.

**A sheet is two atoms in a hexagonal cell**, a = sqrt(3) bonds,
element A at (1/3, 2/3) and B at (2/3, 1/3).  Each A is bonded to the
B in its own cell and in the cells at -a1 and +a2, and nothing else
is: every bond is written down here, with the cell it crosses into,
and the stored graph is exactly those.  **Nothing joins two layers**
-- a 3.35 A gap is no bond, and a Recalculate bonds that thought
otherwise would be the person's to press.

**A supercell is an integer transform of that cell** (``M``, rows the
new vectors in the old), so the rectangular cell -- a1 and a1 + 2 a2,
four atoms a layer, right angles -- is the same code as an n x m
repeat.  An atom is a lattice translation of one of the two sites,
and a bond's partner is found the same way and wrapped into the new
cell with the image it crossed.

**Stacking** is the lateral shift of each layer: A unshifted, B by
one bond (a third of the way along a1 - a2), C by two; AA' is AA with
the two elements swapped on every other layer, h-BN's own stacking.
Bulk repeats the sequence along c, so the layer count must be a whole
number of its periods; a slab is the layers with vacuum above.

**The spacing follows the elements unless one is typed**: graphite's
3.35 A, and h-BN's 3.33 A for B and N.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace

import numpy as np

from xtal.carbon import honeycomb
from xtal.core import pyykko

__all__ = ["STACKINGS", "STACKS", "Recipe", "Built", "GrapheneError",
           "checked", "build", "cell_matrix", "atoms_per_layer"]

#: Stacking -> the sequence of lateral shifts, in thirds of a bond's
#: worth of shift, and whether every other layer swaps its elements.
STACKINGS = {
    "AA": ((0,), False),
    "AB": ((0, 1), False),
    "ABC": ((0, 1, 2), False),
    "AA'": ((0, 0), True),
}

STACKS = ("bulk", "slab")

#: Graphite's interlayer spacing (Bernal, AB), A.
GRAPHITE_SPACING = 3.35

#: Hexagonal boron nitride's, A.
HBN_SPACING = 3.33

#: The spacings a recipe may give, A.
SPACING_RANGE = (1.0, 20.0)


class GrapheneError(ValueError):
    """A recipe that cannot be built, said in one sentence."""


@dataclass(frozen=True)
class Recipe:
    """The form's values."""

    element_a: str = "C"
    element_b: str = "C"
    #: None is the elements' own bond, from Pyykkö's radii; the form
    #: hands text, "" for none, which :func:`checked` reads.
    bond: float | str | None = None
    layers: int = 1
    stacking: str = "AB"
    #: None is the elements' own spacing; text "" likewise.
    spacing: float | str | None = None
    stack: str = "slab"
    vacuum: float = 15.0
    cells_a: int = 1
    cells_b: int = 1
    rectangular: bool = False

    @property
    def symbols(self) -> tuple[str, str]:
        return (self.element_a, self.element_b)

    @property
    def bond_length(self) -> float:
        given = honeycomb.given_bond(self.bond, GrapheneError)
        if given is not None:
            return given
        return pyykko.aromatic_bond(*self.symbols)

    @property
    def from_radii(self) -> bool:
        return honeycomb.given_bond(self.bond, GrapheneError) is None

    @property
    def interlayer(self) -> float:
        """The spacing between layers: the one given, else h-BN's for
        B and N and graphite's for anything else."""
        given = _given_spacing(self.spacing)
        if given is not None:
            return given
        if set(self.symbols) == {"B", "N"}:
            return HBN_SPACING
        return GRAPHITE_SPACING

    @property
    def spacing_source(self) -> str:
        if _given_spacing(self.spacing) is not None:
            return "as given"
        if set(self.symbols) == {"B", "N"}:
            return "h-BN's"
        if set(self.symbols) == {"C"}:
            return "graphite's"
        return "graphite's; nothing better is known here"

    @property
    def is_bn(self) -> bool:
        return set(self.symbols) == {"B", "N"}

    @property
    def title(self) -> str:
        if self.element_a == self.element_b:
            name = ("graphene" if self.element_a == "C"
                    else f"{self.element_a} honeycomb")
        elif self.is_bn:
            name = "h-BN"
        else:
            name = f"{self.element_a}{self.element_b} honeycomb"
        if self.layers == 1:
            return f"{name}, one layer"
        if self.stack == "bulk":
            return f"{self.stacking} {name}, bulk"
        return f"{self.layers}-layer {self.stacking} {name}"


def _given_spacing(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        spacing = float(text)
    except ValueError:
        raise GrapheneError(f"the layer spacing must be a number, not "
                            f"{text!r}") from None
    low, high = SPACING_RANGE
    if not low <= spacing <= high:
        raise GrapheneError(f"the layer spacing must be {low} to {high} "
                            f"A, not {text}")
    return spacing


def checked(recipe: Recipe) -> Recipe:
    """The recipe with its elements spelled properly, or a
    :class:`GrapheneError` saying what is wrong with it."""
    symbols = [honeycomb.element_symbol(text, GrapheneError)
               for text in (recipe.element_a, recipe.element_b)]
    stacking = re.sub(r"\s+", "", str(recipe.stacking)).upper() \
        .replace("’", "'").replace("PRIME", "'")
    if stacking not in STACKINGS:
        raise GrapheneError(f"stacking must be one of "
                            f"{', '.join(STACKINGS)}, not "
                            f"{recipe.stacking!r}")
    if recipe.stack not in STACKS:
        raise GrapheneError(f"stack must be one of {', '.join(STACKS)}, "
                            f"not {recipe.stack!r}")
    if recipe.layers < 1:
        raise GrapheneError("a sheet needs at least one layer")
    if recipe.cells_a < 1 or recipe.cells_b < 1:
        raise GrapheneError("the repeat must be at least 1 x 1")
    if stacking == "AA'" and symbols[0] == symbols[1]:
        raise GrapheneError(
            "AA' stacks each layer's A over the next layer's B, which "
            "is AA when the two elements are the same")
    period = len(STACKINGS[stacking][0])
    if recipe.stack == "bulk" and recipe.layers % period:
        lower = recipe.layers - recipe.layers % period
        nearest = (f"{lower} or {lower + period}" if lower
                   else f"{period}")
        raise GrapheneError(
            f"{stacking} repeats every {period} layers, so a bulk "
            f"stack needs a multiple of {period}: {nearest}, not "
            f"{recipe.layers}")
    out = replace(recipe, element_a=symbols[0], element_b=symbols[1],
                  stacking=stacking,
                  bond=honeycomb.given_bond(recipe.bond, GrapheneError),
                  spacing=_given_spacing(recipe.spacing))
    return out


def cell_matrix(recipe: Recipe) -> np.ndarray:
    """``M``: the new cell's two in-plane vectors in the hexagonal
    cell's, rows."""
    base = np.array([[1, 0], [1, 2]]) if recipe.rectangular \
        else np.eye(2, dtype=int)
    return np.diag([recipe.cells_a, recipe.cells_b]) @ base


def atoms_per_layer(recipe: Recipe) -> int:
    return 2 * int(round(abs(np.linalg.det(cell_matrix(recipe)))))


@dataclass
class Built:
    """What came out, and what the report says about it."""

    recipe: Recipe
    structure: object
    a: float
    b: float
    c: float
    gamma: float
    atoms_per_layer: int
    closest_contact: float
    notes: tuple = field(default_factory=tuple)

    def lines(self) -> list[str]:
        return [f"{self.recipe.title}: "
                f"{len(self.structure.sites)} atoms, "
                f"a {self.a:.3f} A, b {self.b:.3f} A, c {self.c:.3f} A",
                *self.notes]


#: Each A's three B neighbours: the hexagonal cell they are in.
_NEIGHBOURS = ((0, 0), (-1, 0), (0, 1))

#: The two sites, fractional in the hexagonal cell.
_SITES = np.array([[1 / 3, 2 / 3], [2 / 3, 1 / 3]])

#: One stacking step's lateral shift, fractional: a bond's length
#: along a1 - a2, which puts this layer's A over the last one's B.
_STEP = np.array([1 / 3, -1 / 3])


def build(recipe: Recipe, say=None) -> Built:
    """Lay the sheets out and state their bonds."""
    from xtal.carbon.build import closest_contact
    from xtal.carbon.lattice import structure_of

    recipe = checked(recipe)
    say = say or (lambda _text: None)
    a = math.sqrt(3.0) * recipe.bond_length
    hexagonal = np.array([[a, 0.0], [-a / 2.0, a * math.sqrt(3) / 2.0]])
    m = cell_matrix(recipe)
    inverse = np.linalg.inv(m)
    plane = m @ hexagonal

    # The hexagonal cells inside the new one: every translation t
    # whose fractional position t M^-1 is in [0, 1).
    corners = np.array([[0, 0], m[0], m[1], m[0] + m[1]])
    low, high = corners.min(axis=0), corners.max(axis=0)
    cells = [np.array((i, j)) for i in range(low[0], high[0] + 1)
             for j in range(low[1], high[1] + 1)]
    cells = [t for t in cells
             if np.all((f := t @ inverse) > -1e-9) and np.all(f < 1 - 1e-9)]
    per_layer = 2 * len(cells)
    if per_layer != atoms_per_layer(recipe):     # pragma: no cover
        raise GrapheneError("the supercell lost a cell")

    shifts, swap = STACKINGS[recipe.stacking]
    spacing = recipe.interlayer
    layers = recipe.layers
    if recipe.stack == "bulk":
        c = layers * spacing
    else:
        c = (layers - 1) * spacing + recipe.vacuum
    matrix = np.zeros((3, 3))
    matrix[:2, :2] = plane
    matrix[2, 2] = c

    index = {}
    names, frac = [], []
    for layer in range(layers):
        shift = _STEP * shifts[layer % len(shifts)]
        swapped = swap and layer % 2 == 1
        z = (layer * spacing + (0 if recipe.stack == "bulk"
                                else recipe.vacuum / 2.0)) / c
        for t in cells:
            for site in (0, 1):
                index[(layer, site, tuple(t))] = len(names)
                names.append(recipe.symbols[site ^ swapped])
                xy = (t + _SITES[site] + shift) @ inverse
                frac.append([*xy, z])
    frac = np.array(frac)

    bonds, images = [], []
    for layer in range(layers):
        for t in cells:
            here = index[(layer, 0, tuple(t))]
            for step in _NEIGHBOURS:
                there = (t + np.array(step)) @ inverse
                wrapped = np.floor(there + 1e-9).astype(int)
                home = np.rint((there - wrapped) @ m).astype(int)
                bonds.append((here, index[(layer, 1, tuple(home))]))
                images.append((*wrapped, 0))
    say(f"{recipe.title}: {len(names)} atoms, {len(bonds)} bonds")
    # A site plus a stacking shift can land past a face.  Wrapped
    # into the cell, each bond's image moves with its two atoms, or
    # it would be stated across the cell.
    bonds = np.array(bonds, int)
    whole = np.floor(frac + 1e-9).astype(int)
    # A rounding error short of a face is on it: left at -1e-10,
    # structure_of's own wrap would put it back at the far face
    # without its bonds.
    frac = np.clip(frac - whole, 0.0, None)
    images = np.array(images, int) + whole[bonds[:, 1]] \
        - whole[bonds[:, 0]]
    structure = structure_of(
        honeycomb.Atoms(matrix=matrix, elements=names, frac=frac,
                        bonds=bonds, images=images),
        title=recipe.title)

    notes = []
    if recipe.stack == "slab" and layers > 1:
        notes.append("a slab: no bond joins two layers, and the "
                     "vacuum is above the top one")
    lengths = np.linalg.norm(plane, axis=1)
    cosine = plane[0] @ plane[1] / (lengths[0] * lengths[1])
    return Built(recipe=recipe, structure=structure,
                 a=float(lengths[0]), b=float(lengths[1]), c=float(c),
                 gamma=float(np.degrees(np.arccos(np.clip(cosine, -1,
                                                          1)))),
                 atoms_per_layer=per_layer,
                 closest_contact=closest_contact(structure),
                 notes=tuple(notes))
