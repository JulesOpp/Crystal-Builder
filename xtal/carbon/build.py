"""
xtal.carbon.build
=================
A disordered carbon, from a recipe: a net, a density, how much of the
sheet to keep, its layers, its defects, its edges -- and a seed, so the
same recipe is the same carbon.

The steps, each its own module:

1. the net, distorted, and the sheet round it at the scale the density
   asks for (:mod:`.surface`);
2. remeshed evenly at 2.46 A and given Stone-Wales defects
   (:mod:`.mesh`);
3. cut into ribbons that make one piece per layer (:mod:`.ribbons`);
4. dualised to carbon, pruned and terminated, the bonds stated
   (:mod:`.lattice`);
5. relaxed with UFF **at the solved cell**: the density is the input,
   and a cell left free would make it an output.

**The rings are partly fixed before anything random happens.**  On a
closed sheet the sum of six minus each ring size is six times the
Euler characteristic, which for a sheet round a net is twice its
V - E per cell (:func:`gauss_bonnet_need`): a dia cell's sheet has 96
more heptagon-equivalents than pentagons, whatever the seed.  The
Stone-Wales defects are pairs on top of that, which is why they, and
not a free five:six:seven ratio, are what a recipe sets.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from xtal.carbon import lattice as lt
from xtal.carbon import mesh as ms
from xtal.carbon import ribbons
from xtal.carbon import surface as sf


@dataclass
class Recipe:
    """Everything a build is made from.  The defaults aim at the
    example ZTC: dia, as FAU's supercages are, 2 x 2 x 2, at its
    density and its edge chemistry."""

    net: str = "dia"
    repeat: tuple = (2, 2, 2)
    density: float = 0.42           # g/cm3 of carbon
    radius_ratio: float = 0.25      # strut radius over edge length
    coverage: float = 0.42          # share of the sheet kept
    layers: int = 1
    interlayer: float = 3.35        # Angstrom
    sigma_vertex: float = 0.6       # Angstrom
    sigma_edge: float = 0.4         # Angstrom
    stone_wales: float = 6.0        # pairs per 100 rings
    hydrogen: float = 0.07          # H/C
    fluorine: float = 0.29          # F/C
    oxygen: float = 0.044           # O/C
    ether: float = 0.8              # of the oxygen
    hydroxyl: float = 0.18
    carbonyl: float = 0.02
    relax: str = "uff"              # "uff" or "none"
    relax_steps: int = 300
    seed: int = 0

    def ratios(self) -> lt.Ratios:
        return lt.Ratios(self.hydrogen, self.fluorine, self.oxygen,
                         self.ether, self.hydroxyl, self.carbonyl)


@dataclass
class Built:
    """A build and what is worth saying about it."""

    structure: object
    recipe: Recipe
    census: dict
    euler: int
    gauss_bonnet: int
    density: float                  # g/cm3 of carbon, as built
    ratios: dict                    # H/C, F/C, O/C
    edge_fraction: float
    bare_edges: int
    defects: int
    pieces: int
    periodicity: int
    edge_length: float
    closest_contact: float
    closed_carbons: int = 0         # the closed sheet's, every layer
    layer: np.ndarray = None        # which layer each atom is in
    short: dict = field(default_factory=dict)
    relaxed: str = ""
    notes: list = field(default_factory=list)

    def lines(self) -> list[str]:
        cell = self.structure.lattice.parameters[:3]
        rings = ", ".join(f"{n}: {c}" for n, c in self.census.items())
        out = [
            f"{self.recipe.net} x {'x'.join(map(str, self.recipe.repeat))}"
            f", cell {cell[0]:.2f} x {cell[1]:.2f} x {cell[2]:.2f} A, "
            f"net edge {self.edge_length:.2f} A",
            f"carbon density {self.density:.3f} g/cm3, "
            f"{len(self.structure.sites)} atoms",
            "H/C {:.3f}, F/C {:.3f}, O/C {:.3f}".format(
                self.ratios["H/C"], self.ratios["F/C"],
                self.ratios["O/C"]),
            f"edge carbons {self.edge_fraction:.0%}, "
            f"{self.bare_edges} left bare",
            f"rings {rings}",
            f"sheet chi {self.euler} per layer: sum(6 - n) = "
            f"{self.gauss_bonnet} on the closed sheet, "
            f"{self.defects} Stone-Wales pairs added",
            f"{self.pieces} piece(s), percolating in "
            f"{self.periodicity} directions",
            f"closest non-bonded contact {self.closest_contact:.2f} A",
        ]
        if self.relaxed:
            out.append(self.relaxed)
        return out + list(self.notes)


def gauss_bonnet_need(net: str, repeat=(1, 1, 1)) -> int:
    """Six chi of the closed sheet round ``net`` over ``repeat`` cells:
    the sum of six minus each ring size it must have, negative for
    heptagons."""
    _lattice, vertices, edges = sf.net_of(net)
    cells = int(np.prod(repeat))
    return 6 * sf.expected_euler(len(vertices), len(edges)) * cells


def build(recipe: Recipe, say=None, check=None) -> Built:
    """Make the carbon a recipe describes.  ``say`` is told each step,
    for a progress line, and ``check`` is called between them, so a
    run's Stop is honoured at the next step rather than at the end."""
    quiet = say or (lambda _text: None)
    check = check or (lambda: None)

    def say(text):
        check()
        quiet(text)

    rng = np.random.default_rng(recipe.seed)
    lattice, vertices, edges = sf.net_of(recipe.net)
    lattice, vertices, edges = sf.repeated(lattice, vertices, edges,
                                           recipe.repeat)
    distortion = sf.Distortion.draw(rng, len(vertices), len(edges))

    say("solving the cell for the density")
    solved = sf.solve_scale(
        lattice, vertices, edges, density=recipe.density,
        radius_ratio=recipe.radius_ratio, coverage=recipe.coverage,
        layers=recipe.layers, interlayer=recipe.interlayer,
        distortion=distortion, sigma_vertex=recipe.sigma_vertex,
        sigma_edge=recipe.sigma_edge)
    field_ = sf.Field(solved.skeleton, solved.width)
    target = solved.carbons
    # The ethers take carbons' places, so the sheet keeps that many
    # more for the carbon left to be the density's.
    target += recipe.ratios().wanted(target)["ether"]

    meshes, defects = [], 0
    for k, level in enumerate(solved.levels):
        say(f"remeshing layer {k + 1} of {len(solved.levels)}")
        mesh = sf.march(field_, level, _remesh_grid(solved.width))
        mesh = ms.remesh(mesh, field_, level)
        pairs = int(round(recipe.stone_wales * mesh.n_vertices / 100))
        mesh, made = ms.stone_wales(mesh, pairs, rng, field_, level)
        defects += made
        meshes.append(mesh)
    euler = meshes[0].euler()
    closed_need = sum(ms.gauss_bonnet(m)[0] for m in meshes)

    say("cutting the ribbons")
    noise = ribbons.Noise(solved.skeleton.lattice.matrix,
                          0.8 * solved.skeleton.edge_length, rng)
    # One rng draw for the anchors' sides, shared by every layer, so
    # the ribbons of a bilayer lie over each other.
    anchor_seed = int(rng.integers(2 ** 31))
    spines = [ribbons.Spines(m, solved.skeleton, solved.radius + offset,
                             np.random.default_rng(anchor_seed), noise)
              for m, offset in zip(meshes, sf.layer_offsets(
                  recipe.layers, recipe.interlayer), strict=True)]
    sheets, _half_width = ribbons.cut(meshes, spines, noise, target)
    sheet = ribbons.merge(sheets)

    say("terminating the edges")
    done = lt.terminate(sheet, recipe.ratios(), rng)
    structure = lt.structure_of(
        done, title=f"carbon on {recipe.net} (seed {recipe.seed})")
    structure.meta["source"] = "xtal.carbon"

    relaxed = ""
    notes = []
    if recipe.relax == "uff":
        say("relaxing with UFF at the solved cell")
        relaxed = _relax(structure, recipe.relax_steps)
    if done.short:
        notes.append("too few edge carbons for " + ", ".join(
            f"{n} {kind}" for kind, n in done.short.items())
            + ": raise the edge share (lower coverage) or ask for less")

    counts = Counter(done.elements)
    carbons = max(counts["C"], 1)
    volume = structure.lattice.volume
    from xtal.core import rings as ring_census
    return Built(
        structure=structure, recipe=recipe,
        census=ring_census.census(structure, max_size=10),
        euler=euler, gauss_bonnet=closed_need,
        density=counts["C"] / volume / sf.ATOMS_PER_GCC,
        ratios={"H/C": counts["H"] / carbons,
                "F/C": counts["F"] / carbons,
                "O/C": counts["O"] / carbons},
        edge_fraction=done.edge_carbons / max(sheet.n_atoms, 1),
        bare_edges=done.bare, defects=defects,
        pieces=sum(lt.pieces(s.n_atoms, s.bonds) for s in sheets),
        periodicity=min(lt.periodicity(s.n_atoms, s.bonds, s.images)
                        for s in sheets),
        edge_length=solved.skeleton.edge_length,
        closest_contact=closest_contact(structure),
        closed_carbons=sum(m.n_triangles for m in meshes),
        layer=_layers(done, sheets),
        short=done.short, relaxed=relaxed, notes=notes)


def _layers(done, sheets) -> np.ndarray:
    """Which layer each atom is in: a carbon by the sheet it came
    from, a termination by the atom it hangs from -- its bond is
    written as (parent, itself) when it is placed, so one pass in
    order reaches every parent first."""
    out = [k for k, sheet in enumerate(sheets)
           for _ in range(sheet.n_atoms)]
    for a, b in done.bonds.tolist():
        if b == len(out):
            out.append(out[a])
    return np.array(out, int)


def _remesh_grid(width: float) -> float:
    """The marching step for a sheet about to be remeshed: as coarse as
    keeps its topology, because every triangle the march makes is one
    the remesh has to collapse -- at a 1 A grid, 147 000 of them on a
    dia 2 x 2 x 2 for 6000 kept."""
    return min(2.2, max(sf.GRID_SPACING, 1.4 * width))


def _relax(structure, steps: int) -> str:
    """UFF at a fixed cell, positions only; the bonds are the stated
    ones and are never touched."""
    from xtal.ff import optimize
    from xtal.ff.registry import ENGINES

    calculator = ENGINES.build("uff", structure)
    result = optimize.run(calculator, structure, method="lbfgs",
                          max_steps=steps)
    # Written as the optimiser gives them, unwrapped, the way its own
    # command applies them: the stated graph follows an atom across a
    # cell face through the expansion, and wrapping one back by hand
    # left its bonds pointing at the far side of the cell.
    for site, frac in zip(structure.sites, result.frac, strict=True):
        site.frac = np.asarray(frac, float)
    from xtal.core.structure import Change
    structure.touch(Change.POSITIONS)
    state = "converged" if result.converged else "not converged"
    return (f"UFF at the solved cell: {result.steps} steps, {state}, "
            f"max force {result.max_force:.2f} kcal/mol/A")


def closest_contact(structure) -> float:
    """The shortest distance between two atoms neither bonded nor
    sharing a neighbour: what a sheet folded onto itself, or two
    layers too close, would show."""
    from scipy.spatial import cKDTree

    from xtal.core import bonding, p1

    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    near: list = [set() for _ in range(cell.n_atoms)]
    for b in graph.bonds:
        near[b.i].add(b.j)
        near[b.j].add(b.i)
    second = [set(n) | {k for m in n for k in near[m]} for n in near]
    shifts = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1)
                       for c in (-1, 0, 1)])
    matrix = structure.lattice.matrix
    images = (cell.frac[None] + shifts[:, None]).reshape(-1, 3) @ matrix
    tree = cKDTree(images)
    home = cell.frac @ matrix
    best = np.inf
    for i, found in enumerate(tree.query_ball_point(home, 4.0)):
        for index in found:
            j = index % cell.n_atoms
            if j == i or j in second[i]:
                continue
            best = min(best, float(np.linalg.norm(images[index] - home[i])))
    return best
