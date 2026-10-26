"""
xtal.nanotube.build
===================
A recipe to a structure: the tube rolled, its ends made, its bonds
stated, and what was built measured for the report.

**Periodic or finite.**  A periodic tube is a whole number of
translational periods along c, so "length" is rounded to one; a finite
tube is cut to the length asked for, and every atom the cut leaves
hanging by one bond is dropped, again and again, so no edge atom is
held by a single bond.  Capped puts one hydrogen on each two-coordinate
atom that is left, along the bond the cut took away, at UFF's natural
X-H length -- the same length :mod:`xtal.ff.hydrogens` uses, so the
hydrogen starts where the force field it is relaxed in wants it.

**Too thin is refused on geometry, not chemistry.**  Rolling shortens
every bond to a chord and brings atoms across the tube together.  A
build is refused when a bond is crushed below 90% of its length, or
when two unbonded atoms come within the application's own bonding
distance -- Recalculate bonds would then bond them, and the tube would
not be the one asked for.

**The bond follows the elements unless one is typed** (Julius,
2026-10-26): the two elements' aromatic bond from Pyykkö's covalent
radii, :func:`xtal.core.pyykko.aromatic_bond` -- 1.42 A for C-C, 1.47
A for B-N.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from xtal.core import elements, pyykko
from xtal.nanotube import geometry

__all__ = ["ENDS", "Recipe", "Built", "NanotubeError", "checked",
           "build", "hydrogen_length", "electronic_character"]

ENDS = ("periodic", "capped", "bare")

#: A rolled bond shorter than this share of the bond is refused.
CRUSHED = 0.90

#: A rolled bond shorter than this share of the bond is noted.
COMPRESSED = 0.97

#: Below this diameter the (n - m) mod 3 rule is unreliable: sigma-pi
#: hybridisation (Blase et al., PRL 72, 1878 (1994)).
THIN_FOR_ZONE_FOLDING = 7.0

#: The bond lengths a recipe may give, A: the form's old spinbox
#: range, kept now the box is text and nothing else holds it.
BOND_RANGE = (0.8, 3.0)


class NanotubeError(ValueError):
    """A recipe that cannot be built, said in one sentence."""


@dataclass(frozen=True)
class Recipe:
    """The form's values."""

    n: int = 10
    m: int = 10
    ends: str = "periodic"
    length: float = 20.0
    element_a: str = "C"
    element_b: str = "C"
    #: None is the elements' own bond, from Pyykkö's radii; the form
    #: hands text, "" for none, which :func:`checked` reads.
    bond: float | str | None = None
    vacuum: float = 12.0

    @property
    def bond_length(self) -> float:
        """The bond the tube is rolled from: the one given, or the two
        elements' aromatic bond from Pyykkö's radii.

        With no bond given, the elements must be ones :func:`checked`
        accepts: a word that is no element raises KeyError here,
        where :func:`checked` refuses it by name."""
        given = _given_bond(self.bond)
        if given is not None:
            return given
        return pyykko.aromatic_bond(*self.symbols)

    @property
    def from_radii(self) -> bool:
        """Whether the bond is the radii's rather than one given."""
        return _given_bond(self.bond) is None

    @property
    def symbols(self) -> tuple[str, str]:
        """The two elements, spelled properly where they can be."""
        return tuple(elements.canonical_symbol(str(s)) or str(s)
                     for s in (self.element_a, self.element_b))

    @property
    def chirality(self) -> geometry.Chirality:
        return geometry.Chirality(self.n, self.m, self.bond_length)

    @property
    def periodic(self) -> bool:
        return self.ends == "periodic"

    @property
    def periods(self) -> int:
        """Periods a periodic tube stacks: the length, rounded."""
        return max(1, round(self.length / self.chirality.t_length))

    @property
    def is_bn(self) -> bool:
        return {self.element_a, self.element_b} == {"B", "N"}

    @property
    def title(self) -> str:
        kind = "BN nanotube" if self.is_bn else "nanotube"
        return f"({self.n},{self.m}) {kind}"


def checked(recipe: Recipe) -> Recipe:
    """The recipe with its elements spelled properly, or a
    :class:`NanotubeError` saying what is wrong with it."""
    if recipe.n < 1 or recipe.m < 0:
        raise NanotubeError(f"a nanotube needs n >= 1 and m >= 0; "
                            f"({recipe.n},{recipe.m}) was given")
    if recipe.ends not in ENDS:
        raise NanotubeError(f"ends must be one of {', '.join(ENDS)}, "
                            f"not {recipe.ends!r}")
    symbols = []
    for text in (recipe.element_a, recipe.element_b):
        symbol = elements.canonical_symbol(str(text))
        if symbol is None or elements.is_dummy(symbol):
            raise NanotubeError(f"{str(text).strip()!r} is not an "
                                f"element")
        symbols.append(symbol)
    # No element is refused for want of a radius: Pyykkö covers all
    # 118 and the radii take D as H, which a test sweeps.
    return replace(recipe, element_a=symbols[0], element_b=symbols[1],
                   bond=_given_bond(recipe.bond))


def _given_bond(value) -> float | None:
    """A bond given as a number or the form's text, in A; None when
    none was given."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            bond = float(text)
        except ValueError:
            raise NanotubeError(f"the bond length must be a number, "
                                f"not {text!r}") from None
    else:
        bond, text = float(value), f"{float(value):g}"
    low, high = BOND_RANGE
    if not low <= bond <= high:
        raise NanotubeError(f"the bond length must be {low} to {high} "
                            f"A, not {text}")
    return bond


@dataclass
class Built:
    """What came out, and what the report says about it."""

    recipe: Recipe
    structure: object
    periods: int
    length: float
    hydrogens: int
    shortest_bond: float
    closest_contact: float
    electronic: str
    notes: tuple = field(default_factory=tuple)

    @property
    def chirality(self) -> geometry.Chirality:
        return self.recipe.chirality

    def lines(self) -> list[str]:
        c = self.chirality
        return [f"{self.recipe.title}: {c.diameter:.2f} A across, "
                f"{c.theta:.2f} degrees from zigzag",
                f"{len(self.structure.sites)} atoms, "
                f"{self.length:.2f} A long",
                *self.notes]


@dataclass
class _Atoms:
    """What :func:`xtal.carbon.lattice.structure_of` reads."""

    matrix: np.ndarray
    elements: list
    frac: np.ndarray
    bonds: np.ndarray
    images: np.ndarray


def build(recipe: Recipe, say=None) -> Built:
    """Roll the tube the recipe describes and make its ends."""
    from xtal.carbon.lattice import structure_of

    recipe = checked(recipe)
    say = say or (lambda _text: None)
    c = recipe.chirality
    rolled = geometry.roll(c)
    symbols = (recipe.element_a, recipe.element_b)
    shortest = geometry.shortest_bond(c, rolled)
    _refuse_if_too_thin(recipe, rolled, symbols, shortest)
    say(f"rolled one period: {len(rolled.cart)} atoms, "
        f"{c.t_length:.3f} A")
    if recipe.periodic:
        cart, sub, bonds, images, periods = _periodic(recipe, rolled)
        length = periods * c.t_length
        extra_h = np.zeros((0, 3))
        carriers = np.zeros(0, int)
        height = length
    else:
        cart, sub, bonds, cut = _finite(recipe, rolled)
        images = np.zeros((len(bonds), 3), int)
        periods = 0
        z = cart[:, 2]
        length = float(z.max() - z.min())
        if recipe.ends == "capped":
            extra_h, carriers = _caps(cart, cut, symbols, sub)
        else:
            extra_h, carriers = np.zeros((0, 3)), np.zeros(0, int)
        # The box is measured over every atom, the caps included, so the
        # gap between images along c is the vacuum asked for, atom
        # centre to atom centre, as it is across (a = d + vacuum).
        # Measured over the framework alone, each end's hydrogens
        # reached 1.08 A into the gap.
        every_z = np.concatenate([z, extra_h[:, 2]])
        bottom = every_z.min() - recipe.vacuum / 2
        cart = cart - [0.0, 0.0, bottom]
        extra_h = extra_h - [0.0, 0.0, bottom]
        height = float(every_z.max() - every_z.min()) + recipe.vacuum
    side = c.diameter + recipe.vacuum
    matrix = np.diag([side, side, height])
    names = [symbols[s] for s in sub] + ["H"] * len(extra_h)
    everything = np.vstack([cart, extra_h]) + [side / 2, side / 2, 0.0]
    n_frame = len(cart)
    h_bonds = np.column_stack([carriers,
                               n_frame + np.arange(len(carriers))])
    all_bonds = np.vstack([bonds, h_bonds]) if len(h_bonds) else bonds
    all_images = np.vstack([images, np.zeros((len(h_bonds), 3), int)])
    frac, all_images = _in_cell(everything @ np.linalg.inv(matrix),
                                all_bonds, all_images)
    structure = structure_of(
        _Atoms(matrix=matrix, elements=names, frac=frac,
               bonds=all_bonds, images=all_images),
        title=recipe.title)
    notes = _notes(recipe, shortest)
    return Built(recipe=recipe, structure=structure, periods=periods,
                 length=length, hydrogens=len(extra_h),
                 shortest_bond=shortest,
                 closest_contact=_closest_unbonded(structure,
                                                   1.1 * c.a),
                 electronic=electronic_character(recipe),
                 notes=tuple(notes))


def _in_cell(frac, bonds, images):
    """``frac`` wrapped into [0, 1), and each bond's image moved with
    its two atoms.

    :func:`xtal.carbon.lattice.structure_of` wraps the positions it is
    given but re-reads the images only against its own expansion's
    re-wrap, so a bond to an atom that started outside the cell -- a
    bottom hydrogen below z = 0 in a small vacuum, or, with no vacuum,
    the atom at angle zero on the far face -- was stated across the
    cell, 13 to 23 A long.  Wrapping here leaves it nothing to move.
    """
    wrapped = np.mod(frac, 1.0)
    # np.mod of a tiny negative number is 1.0, which structure_of
    # would send to 0.0 behind the image's back.
    wrapped[wrapped >= 1.0] = 0.0
    offset = np.round(frac - wrapped).astype(int)
    if len(bonds):
        images = images + offset[bonds[:, 1]] - offset[bonds[:, 0]]
    return wrapped, images


def _closest_unbonded(structure, reach: float) -> float:
    """The closest two atoms of the built structure come that no
    stated bond joins, periodic images included; ``inf`` when no pair
    is within ``reach``.

    Measured over everything built, not the rolled wall: a ragged cut
    leaves coves whose two caps point into the same half-hexagon, about
    1.24 bonds apart, and the wall alone reported a second neighbour
    nearly half as far again.  ``reach`` need only be the wall's second
    neighbour, which every tube has and rolling only shortens.
    """
    from scipy.spatial import cKDTree

    from xtal.core import p1

    cell = p1.expand(structure)
    matrix = structure.lattice.matrix
    # Images are made only as far as ``reach`` from the cell, per axis
    # by the cell's own height, so a periodic tube is checked across
    # the top of its cell and a finite one, isolated by the vacuum,
    # costs nothing more; a cell thinner than ``reach`` still gets
    # every image that can matter.
    volume = abs(np.linalg.det(matrix))
    heights = [volume / np.linalg.norm(np.cross(matrix[(k + 1) % 3],
                                                matrix[(k + 2) % 3]))
               for k in range(3)]
    margin = np.array([reach / h for h in heights])
    counts = np.ceil(margin).astype(int)
    points, owners, shifts = [], [], []
    for shift in np.ndindex(*(2 * counts + 1)):
        shift = np.array(shift) - counts
        frac = cell.frac + shift
        near = np.all((frac > -margin) & (frac < 1 + margin), axis=1)
        points.append(frac[near] @ matrix)
        owners.append(np.nonzero(near)[0])
        shifts.append(np.tile(shift, (int(near.sum()), 1)))
    points = np.vstack(points)
    owners = np.concatenate(owners)
    shifts = np.vstack(shifts)
    found = cKDTree(cell.frac @ matrix).sparse_distance_matrix(
        cKDTree(points), reach, output_type="ndarray")
    i = found["i"].astype(np.int64)
    j = owners[found["j"]].astype(np.int64)
    image = shifts[found["j"]]
    bonds = structure.perceived.bonds
    first = np.array([b.i for b in bonds], dtype=np.int64)
    second = np.array([b.j for b in bonds], dtype=np.int64)
    across = np.array([b.image for b in bonds], dtype=np.int64)
    across = across.reshape(-1, 3)
    # One integer per (atom, atom, image), so every pair is looked up
    # among the bonds at once: a Python loop over the pairs was most of
    # the time on a big tube.  The base is the widest image either side
    # holds, so the key cannot overflow below about 10^8 atoms.
    base = 2 * int(max(np.abs(image).max(initial=0),
                       np.abs(across).max(initial=0))) + 1
    n = cell.n_atoms

    def key(a, b, img):
        cells = ((img[:, 0] * base + img[:, 1]) * base + img[:, 2]
                 + (base ** 3) // 2)
        return (a * n + b) * base ** 3 + cells

    bonded = np.concatenate([key(first, second, across),
                             key(second, first, -across)])
    unbonded = ~np.isin(key(i, j, image), bonded)
    unbonded &= (i != j) | np.any(image != 0, axis=1)
    distances = found["v"][unbonded]
    return float(distances.min()) if len(distances) else math.inf


def hydrogen_length(symbol: str) -> float:
    """UFF's natural X-H single bond for an sp2 ``symbol`` -- what
    Add Hydrogens would put the hydrogen at.  An element with no
    resonant or sp2 type takes its first UFF type, and one with no UFF
    type at all the sum of the two covalent radii."""
    from xtal.ff.uff import params, terms

    types = params.types_for(symbol)
    for name in (f"{symbol}_R", f"{symbol}_2"):
        if name in types:
            return terms.natural_bond_length(name, "H_", 1.0)
    if types:
        return terms.natural_bond_length(types[0], "H_", 1.0)
    return elements.covalent_radius(symbol) \
        + elements.covalent_radius("H")


def electronic_character(recipe: Recipe) -> str:
    """The textbook classification, for the report only."""
    if recipe.is_bn:
        return ("semiconducting, wide gap (every BN tube: Rubio, "
                "Corkill and Cohen 1994)")
    if (recipe.element_a, recipe.element_b) != ("C", "C"):
        return "not classified"
    n, m = recipe.n, recipe.m
    if n == m:
        text = "metallic (armchair)"
    elif (n - m) % 3 == 0:
        text = ("small-gap: zone folding gives a metal, curvature "
                "opens a gap under 0.1 eV")
    else:
        text = "semiconducting"
    if recipe.chirality.diameter < THIN_FOR_ZONE_FOLDING:
        text += ("; the rule is unreliable this thin: sigma-pi "
                 "hybridisation")
    return text


def _refuse_if_too_thin(recipe, rolled, symbols, shortest) -> None:
    from xtal.core.bonding import BondRules

    c = recipe.chirality
    across = f"a ({c.n},{c.m}) tube is {c.diameter:.1f} A across"
    rules = BondRules()
    cutoffs = np.array([[rules.cutoff(a, b)[1] for b in symbols]
                        for a in symbols])
    # A bond this short fails on the flat sheet, before any rolling:
    # its second neighbours, sqrt(3) bonds apart and on one
    # sublattice, are within bonding distance, so every tube would be
    # refused, and saying that one is too thin sends a person to make
    # it wider, which cannot help.
    bond = recipe.bond_length
    second = math.sqrt(3.0) * bond
    limit = float(max(cutoffs[0, 0], cutoffs[1, 1]))
    if second < limit:
        raise NanotubeError(
            f"at a {bond:.2f} A bond even the flat sheet puts "
            f"second neighbours {second:.2f} A apart, within bonding "
            f"distance ({limit:.2f} A)")
    if shortest < CRUSHED * bond:
        raise NanotubeError(
            f"{across}: rolled, a bond is compressed to "
            f"{shortest:.2f} A, {100 * shortest / bond:.0f}% "
            f"of {bond:.2f} A")
    clash = geometry.bonding_clash(c, rolled, cutoffs)
    if clash is not None:
        distance, limit = clash
        raise NanotubeError(
            f"{across}: rolled, two unbonded atoms come "
            f"{distance:.2f} A apart, within bonding distance "
            f"({limit:.2f} A)")


def _notes(recipe, shortest) -> list[str]:
    notes = []
    bond = recipe.bond_length
    if shortest < COMPRESSED * bond:
        squeeze = 100 * (1 - shortest / bond)
        notes.append(f"rolling compresses bonds by up to "
                     f"{squeeze:.0f}%; relax before trusting the "
                     f"geometry")
    if recipe.from_radii:
        for symbol in dict.fromkeys(recipe.symbols):
            if not pyykko.has_double_radius(symbol):
                notes.append(f"Pyykkö gives no double-bond radius for "
                             f"{symbol}; its single-bond radius was "
                             f"used")
    return notes


def _periodic(recipe, rolled):
    """``periods`` copies stacked along z, bonds across the top
    wrapped to image (0, 0, 1)."""
    periods = recipe.periods
    t = recipe.chirality.t_length
    n = len(rolled.cart)
    cart = np.vstack([rolled.cart + [0.0, 0.0, k * t]
                      for k in range(periods)])
    sub = np.tile(rolled.sublattice, periods)
    bonds, images = [], []
    for k in range(periods):
        for (i, j), image in zip(rolled.bonds, rolled.images,
                                 strict=True):
            target = k + int(image)
            bonds.append((k * n + i, (target % periods) * n + j))
            images.append((0, 0, target // periods))
    return (cart, sub, np.array(bonds, int), np.array(images, int),
            periods)


def _finite(recipe, rolled):
    """The atoms with 0 <= z < length, less any left hanging by one
    bond; and each cut bond as (kept atom, where its partner was)."""
    c = recipe.chirality
    t = c.t_length
    n = len(rolled.cart)
    count = math.ceil(recipe.length / t) + 2
    cart = np.vstack([rolled.cart + [0.0, 0.0, (k - 1) * t]
                      for k in range(count)])
    sub = np.tile(rolled.sublattice, count)
    pairs = []
    for k in range(count):
        for (i, j), image in zip(rolled.bonds, rolled.images,
                                 strict=True):
            other = k + int(image)
            if 0 <= other < count:
                pairs.append((k * n + i, other * n + j))
    pairs = np.array(pairs, int)
    keep = (cart[:, 2] >= 0.0) & (cart[:, 2] < recipe.length)
    while True:
        both = keep[pairs[:, 0]] & keep[pairs[:, 1]]
        degree = np.bincount(pairs[both].ravel(), minlength=len(cart))
        hanging = keep & (degree < 2)
        if not hanging.any():
            break
        keep &= ~hanging
    both = keep[pairs[:, 0]] & keep[pairs[:, 1]]
    degree = np.bincount(pairs[both].ravel(), minlength=len(cart))
    if not (keep & (degree == 3)).any():
        # Nothing left, or a ring of two-coordinate atoms: not a tube.
        raise NanotubeError(
            f"a finite ({c.n},{c.m}) tube must be longer than "
            f"{recipe.length:.2f} A: in a piece that short no atom "
            f"keeps all three of its bonds")
    one = keep[pairs[:, 0]] ^ keep[pairs[:, 1]]
    renumber = -np.ones(len(cart), int)
    renumber[keep] = np.arange(int(keep.sum()))
    cut = []
    for i, j in pairs[one]:
        inside, outside = (i, j) if keep[i] else (j, i)
        cut.append((renumber[inside], cart[outside] - cart[inside]))
    return cart[keep], sub[keep], renumber[pairs[both]], cut


def _caps(cart, cut, symbols, sub):
    """One hydrogen along each cut bond, at UFF's X-H length."""
    positions, carriers = [], []
    for atom, direction in cut:
        length = hydrogen_length(symbols[sub[atom]])
        positions.append(cart[atom]
                         + direction / np.linalg.norm(direction) * length)
        carriers.append(atom)
    return np.array(positions).reshape(-1, 3), np.array(carriers, int)
