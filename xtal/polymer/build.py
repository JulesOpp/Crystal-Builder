"""
xtal.polymer.build
==================
A recipe made into a structure: grown, pushed off or compressed, its
bonds stated, and the numbers that say what it is.

The steps:

1. every chain grown at once (:func:`xtal.polymer.pack.grow`), at the
   recipe's start density;
2. if that is below the target, compressed to it, otherwise pushed
   off where it stands (:mod:`xtal.polymer.pushoff`) -- positions
   only, every bond and angle held;
3. written as a P1 structure whose bonds are the chains' own, stated
   as the stored graph the way a MOF build's are
   (:func:`xtal.mof.build.state_bonds`), so nothing is ever perceived;
4. measured (:mod:`xtal.polymer.stats`).

**A membrane is the film grown between the walls with vacuum on c.**
The film is centred on c; no bond crosses that face, because nothing
grew across it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

import numpy as np

from xtal.polymer import pack, pushoff, stats
from xtal.polymer.pack import Recipe


@dataclass(frozen=True)
class Built:
    """A packed model and what is worth saying about it."""

    structure: object
    recipe: Recipe
    chains: tuple
    density: float
    closest: float              # fraction of the van der Waals sum
    closest_distance: float     # A
    speared: int
    shape: stats.Shape
    meso: float | None
    grown_at: float
    relaxed_steps: int
    seconds: float

    def lines(self) -> list[str]:
        recipe = self.recipe
        names = " / ".join(dict.fromkeys(m.name or m.formula
                                         for m in recipe.monomers))
        a, b, c = self.structure.lattice.parameters[:3]
        out = [
            f"{recipe.chains} chains of {recipe.length} {names}, "
            f"{recipe.sequence.composition}"
            + (f", {recipe.sequence.tacticity}"
               if any(m.handed for m in recipe.monomers) else "")
            + (f" ({self.meso:.0%} meso dyads)" if self.meso is not None
               else "")
            + f": {len(self.structure.sites)} atoms",
            f"cell {a:.2f} x {b:.2f} x {c:.2f} A, P1",
        ]
        if recipe.periodic == "membrane":
            out.append(
                f"a membrane {recipe.thickness:g} A thick, periodic in "
                f"a and b, with {recipe.vacuum:g} A of vacuum on c")
            out.append(f"density {self.density:.3f} g/cm3 in the film "
                       f"(asked {recipe.density:g})")
        else:
            out.append(f"density {self.density:.3f} g/cm3 "
                       f"(asked {recipe.density:g})")
        if self.grown_at < recipe.density:
            out.append(f"grown at {self.grown_at:.3g} g/cm3 and "
                       f"compressed to the target by minimisation")
        else:
            out.append("grown at the target density")
        out.append(f"closest non-bonded contact {self.closest_distance:.2f}"
                   f" A, {self.closest:.2f} of the van der Waals sum")
        shape = self.shape
        line = (f"<R^2>^1/2 {np.sqrt(shape.r2):.1f} A, Rg "
                f"{shape.rg:.1f} A")
        if shape.c_n is not None:
            line += (f", C_{shape.bonds} {shape.c_n:.2f} over the "
                     f"chains' segments of {shape.bonds} backbone bonds "
                     f"(freely rotating {shape.c_free:.2f})")
        out.append(line)
        if self.speared:
            out.append(
                f"{self.speared} bond(s) pass through a ring: a knot "
                f"no relaxation undoes -- build again with another "
                f"seed, or at a lower start density")
        out.append(
            "packed, not equilibrated: the density and contacts are a "
            "starting model's, and the chains have not relaxed at their "
            "own scale -- how entangled they are is a question for "
            "molecular dynamics")
        if any(m.is_ladder for m in recipe.monomers):
            out.append(
                "a ladder polymer's measured density is reached in the "
                "literature by MD compression (Larsen, Lin and Colina's "
                "21-step protocol); this one was squeezed by "
                "minimisation alone")
        return out


def build(recipe: Recipe, say=None, check=None) -> Built:
    """Make the model ``recipe`` describes.  ``say`` is told each step
    and ``check`` is called between steps; it stops the build by
    raising."""
    say = say or (lambda _text: None)
    check = check or (lambda: None)
    started = time.monotonic()
    recipe.check()
    starts = recipe.starts()
    for k, start in enumerate(starts):
        try:
            chains = pack.grow(replace(recipe, start_density=start), say,
                               check)
            break
        except pack.Jammed:
            if k + 1 == len(starts):
                raise
            say(f"jammed at {start:.3g} g/cm3; growing again at "
                f"{starts[k + 1]:.3g}")
    grown_at = start
    recipe_grown = replace(recipe, start_density=grown_at)

    elements, cart, bonds, groups, slices, rings = _assemble(chains)
    box = recipe_grown.box()
    target = recipe.box(recipe.density)
    membrane = recipe.periodic == "membrane"
    if membrane:
        target[2] = box[2]
    periodic = (True, True, not membrane)
    walls = (0.0, recipe.thickness) if membrane else None
    if grown_at < recipe.density:
        say(f"compressing to {recipe.density:g} g/cm3")
        result = pushoff.compress(elements, cart, bonds, groups, box,
                                  target, periodic, walls,
                                  recipe.relax_steps, check, say)
    else:
        say("pushing off the overlaps growth left")
        result = pushoff.push_off(elements, cart, bonds, box, periodic,
                                  walls, recipe.relax_steps,
                                  check=check)
    cart = result.cart
    check()

    cell = target.copy()
    if membrane:
        cell[2] = recipe.thickness + recipe.vacuum
        cart = cart + np.array([0.0, 0.0, 0.5 * recipe.vacuum])
    structure = _structure(elements, cart, bonds, cell, recipe)
    volume = (float(np.prod(target[:2])) * recipe.thickness if membrane
              else float(np.prod(target)))
    return Built(
        structure=structure, recipe=recipe, chains=tuple(chains),
        density=stats.density(elements, volume),
        closest=result.closest, closest_distance=result.closest_distance,
        speared=stats.speared(cart, bonds, rings, cell, periodic),
        shape=stats.shape(chains, lambda k: cart[slices[k]]),
        meso=_meso(chains, recipe), grown_at=grown_at,
        relaxed_steps=result.steps,
        seconds=time.monotonic() - started)


def _assemble(chains):
    """Every chain's atoms end to end: ``(elements, cart, bonds,
    groups, slices, rings)`` -- ``groups`` the unit each atom moves
    with when compressed (a cap with the unit it caps), ``slices`` each
    chain's atoms, ``rings`` every unit's rings in model indices."""
    elements: list[str] = []
    positions = []
    bonds: list[tuple[int, int, float]] = []
    groups: list[int] = []
    slices = []
    rings = []
    unit_count = 0
    for chain in chains:
        symbols, cart, own = chain.atoms()
        start = len(elements)
        elements.extend(symbols)
        positions.append(cart)
        bonds.extend((start + i, start + j, o) for i, j, o in own)
        slices.append(slice(start, start + len(symbols)))
        offset = start
        sizes = []
        for unit in chain.units:
            body = len(unit.monomer.body)
            rings.extend(tuple(offset + k for k in ring)
                         for ring in stats.rings(unit.monomer))
            sizes.append(body)
            offset += body
        here = np.repeat(np.arange(len(sizes)) + unit_count, sizes)
        # The caps come last in a chain's atoms, the head's first.
        first = len(chain.units[0].monomer.head_members)
        caps = len(symbols) - len(here)
        tail = [unit_count + len(sizes) - 1] * (caps - first)
        groups.extend([*here.tolist(), *[unit_count] * first, *tail])
        unit_count += len(sizes)
    return (tuple(elements), np.vstack(positions), tuple(bonds),
            np.array(groups, dtype=np.int64), slices, rings)


def _meso(chains, recipe: Recipe) -> float | None:
    """The fraction of dyads two units of one hand, where growth chose
    the hands; ``None`` where the sequence fixed them."""
    if (recipe.sequence.tacticity != "atactic"
            or not any(m.handed for m in recipe.monomers)):
        return None
    same = total = 0
    for chain in chains:
        hands = [u.monomer.mirror for u in chain.units]
        same += sum(a == b for a, b in zip(hands, hands[1:], strict=False))
        total += len(hands) - 1
    return same / total if total else None


def _structure(elements, cart, bonds, cell, recipe: Recipe):
    """A P1 structure of the atoms in an orthorhombic ``cell``, its
    bonds stated as the stored graph."""
    from xtal.core import p1
    from xtal.core.bonding import BondRules
    from xtal.core.lattice import Lattice
    from xtal.core.site import Site
    from xtal.core.structure import CellBond, Structure

    matrix = np.diag(np.asarray(cell, dtype=float))
    unwrapped = np.asarray(cart, dtype=float) / np.asarray(cell)
    frac = np.mod(unwrapped, 1.0)
    frac[frac >= 1.0] = 0.0
    sites = [Site(e, np.array(f)) for e, f in zip(elements, frac,
                                                  strict=True)]
    for k, site in enumerate(sites):
        site.label = f"{site.element}{k + 1}"
    structure = Structure(lattice=Lattice(matrix), sites=sites)
    names = ", ".join(dict.fromkeys(m.name or m.formula
                                    for m in recipe.monomers))
    structure.meta["title"] = (f"{names} {recipe.periodic} "
                               f"{recipe.chains}x{recipe.length}")
    structure.meta["source"] = "xtal.polymer"
    cell_atoms = p1.expand(structure)
    found = {}
    for i, j, _order in bonds:
        # The image is whatever the unwrapped bond crosses, read
        # against where the cell stores the two atoms.
        image = np.round((unwrapped[j] - unwrapped[i])
                         - (cell_atoms.frac[j] - cell_atoms.frac[i]))
        vector = (cell_atoms.frac[j] + image
                  - cell_atoms.frac[i]) @ matrix
        bond = CellBond(int(i), int(j), tuple(int(v) for v in image),
                        float(np.linalg.norm(vector)))
        a, b, img = bond.key()
        found[(a, b, img)] = CellBond(a, b, img, bond.distance)
    rules = BondRules.from_dict(structure.bond_rules)
    structure.set_perceived(sorted(found.values(),
                                   key=lambda b: (b.i, b.j, b.image)),
                            rules.signature(), cell_atoms)
    return structure
