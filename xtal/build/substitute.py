"""
xtal.build.substitute
=====================
A hydrogen replaced by a group: an amino on a ring, a methoxy, a
nitro -- or a fluorine, or a chlorine: any atom on one bond
(:data:`TERMINAL`).  A ZTC's edges are 634 C-F and 116 C-H, and
which of the two a group replaces is the same question.

There was no way to do this.  Changing the hydrogen's element and
adding atoms one at a time cannot get past the first heavy atom: the
second has no bond to hang off, and every one of them has to be put
somewhere by hand.  Here the whole group is placed in one go, where
chemistry says it goes, and turned where it has room.

**Where it goes.**  The group's attaching atom sits on the line the
hydrogen was on, :func:`~xtal.core.bonding.bond_distance` from the
atom the hydrogen hung off -- so an NH2 on a ring carbon is 1.47 A out
along the old C-H, not 1.09.  The group's own bond to its connection
point is laid along that line, which fixes everything but the turn
about it.

**How it is turned.**  For the most room
(:func:`xtal.build.clearance.clearest_angle`), sampled round a full
turn, with the group's own images one cell over counted: a nitro next
to a carboxylate twists out of the ring plane because that is where
it fits.  The ring itself is never turned -- that would move atoms
nobody selected.

**What it is bonded to.**  Its own bonds, and the one to the atom the
hydrogen was on, and nothing else: the edit is
:func:`apply`, which holds the stored graph through the removal and
the addition rather than perceiving anything.  Bonds change when the
user asks.

The groups are the library's ``Group`` category, so adding one is a
line in ``data/fragments.json``.  They are embedded by RDKit, which is
the ``build`` extra; nothing else here needs it.  Qt-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from xtal.build.clearance import CLEAR, Surroundings, clearest_angle, turn
from xtal.core import bonding, p1
from xtal.core import elements as el
from xtal.core.neighbors import min_image_vector

#: What a group can also be called: the formula a chemist writes on a
#: ring, which is what an agent or a person types before a name.
ALIASES = {"NH2": "Amino", "OH": "Hydroxy", "OMe": "Methoxy",
           "OCH3": "Methoxy", "NO2": "Nitro", "F": "Fluoro",
           "Cl": "Chloro", "Br": "Bromo", "Me": "Methyl",
           "CH3": "Methyl", "Ph": "Phenyl"}

#: How far out from the group's middle anything is looked for, over
#: and above the group's own size.
_REACH = CLEAR + 2.0

#: What a group can replace: an atom on one bond, which is where a
#: group's own single bond to its connection point goes.  A carbonyl
#: oxygen is also on one bond, but on a double one, and a group put
#: there would leave its carbon a bond short.
TERMINAL = frozenset({"H", "D", "F", "Cl", "Br", "I"})


class SubstituteError(ValueError):
    """A group that cannot be made, said in a sentence."""


@dataclass(frozen=True)
class Group:
    """One substituent, ready to be put on an atom.

    ``cart`` is the group's atoms without its connection point, with
    the attaching atom at the origin; ``outward`` is the unit vector
    from the attaching atom *away* from where the connection point
    was -- the direction the group points once it is on.
    """

    name: str
    elements: tuple[str, ...]
    cart: np.ndarray
    bonds: tuple                        # (i, j, order) within the group
    attach: int
    outward: np.ndarray

    @property
    def n_atoms(self) -> int:
        return len(self.elements)

    @property
    def formula(self) -> str:
        counts: dict[str, int] = {}
        for symbol in self.elements:
            counts[symbol] = counts.get(symbol, 0) + 1
        return "".join(f"{k}{v}" if v > 1 else k
                       for k, v in sorted(counts.items()))


def names() -> tuple[str, ...]:
    """The library's groups, by name, in the order it lists them."""
    from xtal.build import library

    return tuple(e.name for e in library.entries()
                 if e.category == "Group" and e.n_connections == 1)


def group(spec: str, name: str = "") -> Group:
    """A group by library name, by alias (``NH2``), or as a SMILES
    string with one connection point (``[*:1]OC``) -- called ``name``
    when one is given, as a group drawn and saved is."""
    from xtal.build import library

    text = str(spec).strip()
    entry = library.find(ALIASES.get(text, text))
    smiles = entry.smiles if entry is not None else text
    if smiles.count("*") != 1:
        raise SubstituteError(
            f"{text!r} is not a group: a group is one of "
            f"{', '.join(names())}, or a SMILES string with exactly one "
            f"connection point")
    called = name or (entry.name if entry is not None else text)
    return _embedded(smiles, called)


def save_group(folder, name: str, smiles: str):
    """Write a drawn group to ``folder`` as ``<name>.smi`` -- the
    SMILES and its name on one line, the format every cheminformatics
    tool reads -- and return the path.  Refused unless it is a group
    (:func:`group`), so a file that is there can be used."""
    from pathlib import Path

    from xtal.workspace import safe_name

    called = str(name).strip() or str(smiles).strip()
    group(smiles, name=called)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe_name(called, 'group')}.smi"
    path.write_text(f"{str(smiles).strip()}\t{called}\n",
                    encoding="utf-8")
    return path


def saved_groups(folder) -> list[tuple[str, str]]:
    """``(name, smiles)`` of every group :func:`save_group` wrote to
    ``folder``, by name; nothing when there is no folder.  A line that
    does not read is passed over: it is a file somebody can fix, not
    a reason the dialog should not open."""
    from pathlib import Path

    folder = Path(folder) if folder else None
    if folder is None or not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.smi")):
        try:
            line = path.read_text(encoding="utf-8").strip().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        parts = line[0].split(None, 1) if line else []
        if parts and parts[0].count("*") == 1:
            name = parts[1].strip() if len(parts) > 1 else path.stem
            found.append((name, parts[0]))
    return sorted(found, key=lambda pair: pair[0].lower())


@lru_cache(maxsize=64)
def _embedded(smiles: str, name: str) -> Group:
    from xtal.build import from_smiles

    molecule = from_smiles(smiles, name=name)
    point = molecule.connections[0]
    partners = [j if i == point else i for i, j, _order in
                molecule.bonds if point in (i, j)]
    if len(partners) != 1:                          # pragma: no cover
        raise SubstituteError(f"{name}: its connection point is bonded "
                              f"to {len(partners)} atoms, not one")
    keep = [k for k in range(molecule.n_atoms) if k != point]
    index = {old: new for new, old in enumerate(keep)}
    cart = np.asarray(molecule.cart, dtype=float)
    attach = index[partners[0]]
    outward = cart[partners[0]] - cart[point]
    outward /= float(np.linalg.norm(outward))
    body = cart[keep] - cart[partners[0]]
    bonds = tuple((index[i], index[j], order)
                  for i, j, order in molecule.bonds
                  if i != point and j != point)
    return Group(name=name,
                 elements=tuple(molecule.elements[k] for k in keep),
                 cart=body, bonds=bonds, attach=attach,
                 outward=outward)


@dataclass(frozen=True)
class Placement:
    """One terminal atom, the atom it hung off, and where the group
    went."""

    atom: int                           # P1 atom replaced
    parent: int                         # P1 atom it was bonded to
    cart: np.ndarray                    # the group's atoms, placed
    room: float                         # the closest approach it has
    element: str = "H"                  # what was replaced


@dataclass(frozen=True)
class Plan:
    group: Group
    placements: tuple
    #: Atoms asked for that cannot be substituted, each with why.
    skipped: tuple = ()

    def replaced(self, count: int | None = None) -> str:
        """``"18 H"``, or ``"40 atoms (F, H)"`` -- what went, said
        ``count`` times over (an orbit's worth) when given."""
        kinds = sorted({p.element for p in self.placements})
        count = len(self.placements) if count is None else count
        if len(kinds) == 1:
            return f"{count} {kinds[0]}"
        return f"{count} atoms ({', '.join(kinds)})"

    def message(self) -> str:
        head = (f"replaced {self.replaced()} with "
                f"{self.group.name} ({self.group.formula})")
        if self.placements:
            closest = min(p.room for p in self.placements)
            head += f"; closest approach {closest:.2f} A"
        return head


def plan(structure, group: Group, atoms=(), per_ring: bool = False,
         representatives: bool = False) -> Plan:
    """Where ``group`` goes, for each terminal atom asked for.  Changes
    nothing.

    ``atoms`` are P1 atoms; each must be one of :data:`TERMINAL` with
    exactly one neighbour, and anything else is named in
    :attr:`Plan.skipped`.  The group goes along the old bond, as it
    does for a hydrogen.
    ``per_ring`` ignores them and takes one hydrogen of every aromatic
    ring instead -- the one whose group has the most room.

    ``representatives`` is for a cell with symmetry: each atom stands
    for its site, so every image of that site is out of the
    surroundings (they are all going) and the group is placed once, on
    the image named.  The groups are placed one after another, and
    each is measured against the ones already placed.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    lattice = structure.lattice
    cart = lattice.to_cart(cell.frac)
    skipped: list[str] = []

    def name(atom: int) -> str:
        return cell.labels[atom] or cell.elements[atom]

    def parent_of(atom: int):
        if cell.elements[atom] not in TERMINAL:
            skipped.append(f"{name(atom)} is not a hydrogen or a "
                           f"halogen")
            return None
        partners = graph.neighbors(atom)
        if len(partners) != 1:
            skipped.append(f"{name(atom)} has {len(partners)} bonds, "
                           f"not one")
            return None
        return int(partners[0])

    if per_ring:
        candidates = []
        for ring in bonding.aromatic_rings(cell, graph):
            hydrogens = [h for member in ring
                         for h in graph.neighbors(member)
                         if cell.elements[h] == "H"
                         and len(graph.neighbors(h)) == 1]
            candidates.append(sorted(set(hydrogens)))
        targets = sorted({h for ring in candidates for h in ring})
    else:
        candidates = None
        targets = sorted({int(a) for a in atoms})
    # What is being taken out, and so is not in anybody's way.  One
    # per ring takes out one hydrogen of each ring, not all of them,
    # so there it is only ever the one being replaced.
    going = set() if per_ring else set(targets)
    if representatives and not per_ring:
        going = {int(k) for t in targets
                 for k in cell.indices_of_site(int(cell.site_idx[t]))}
    solid = np.array([k for k in range(cell.n_atoms)
                      if k not in going
                      and not el.is_dummy(cell.elements[k])], dtype=int)
    placed: list[np.ndarray] = []

    def place(hydrogen: int, parent: int) -> Placement:
        here = cart[hydrogen]
        at = here + min_image_vector(cell.frac[hydrogen],
                                     cell.frac[parent], lattice)
        axis = here - at
        axis /= float(np.linalg.norm(axis))
        reach = bonding.bond_distance(cell.elements[parent],
                                      group.elements[group.attach])
        origin = at + reach * axis
        body = origin + group.cart @ _aligning(group.outward, axis).T
        others = solid[(solid != parent) & (solid != hydrogen)]
        environment = np.vstack([cart[others], *placed]) \
            if placed else cart[others]
        moving = np.array([k for k in range(group.n_atoms)
                           if k != group.attach], dtype=int)
        if not len(moving):
            return Placement(hydrogen, parent, body, float("inf"),
                             cell.elements[hydrogen])
        size = float(np.max(np.linalg.norm(body - origin, axis=1)))
        surroundings = Surroundings(environment, lattice.matrix,
                                    centre=origin, reach=size + _REACH)
        angle, room = clearest_angle(surroundings, body[moving], axis,
                                     origin, 0.0, keep_clear=False)
        return Placement(hydrogen, parent,
                         turn(body, axis, origin, angle), room,
                         cell.elements[hydrogen])

    placements: list[Placement] = []
    if per_ring:
        for ring in candidates:
            options = [place(h, parent_of(h)) for h in ring]
            if not options:
                continue
            best = max(options, key=lambda p: (p.room, -p.atom))
            placements.append(best)
            placed.append(best.cart)
    else:
        for hydrogen in targets:
            parent = parent_of(hydrogen)
            if parent is None:
                continue
            chosen = place(hydrogen, parent)
            placements.append(chosen)
            placed.append(chosen.cart)
    return Plan(group, tuple(placements), tuple(skipped))


def apply(structure, plan: Plan) -> list[int]:
    """Make the substitution on ``structure``, in place: every
    hydrogen's site out, every group's atoms in, bonded to themselves
    and to the atom the hydrogen was on.  Returns the new sites.

    One expansion for the lot -- a hundred rings is one edit, not a
    hundred -- and the stored graph is *held* through both halves
    (:func:`~xtal.core.bonding.hold_through_removal`,
    :func:`~xtal.core.bonding.hold_perception`), so nothing anywhere
    in the crystal is perceived again.  The group's bonds are explicit,
    as a pasted molecule's are, and the one to its parent names the
    parent's symmetry operation, so it holds in a cell with a group.
    """
    from xtal.core.site import Site
    from xtal.core.structure import Bond

    group = plan.group
    bonding.prepare_hold(structure)
    before = p1.expand(structure)
    parents = [(int(before.site_idx[p.parent]),
                int(before.op_idx[p.parent])) for p in plan.placements]
    removed = sorted({int(before.site_idx[p.atom])
                      for p in plan.placements})
    structure.remove_sites(removed)
    bonding.hold_through_removal(structure, before, removed)
    gone = np.asarray(removed, dtype=int)

    def renumbered(site: int) -> int:
        return site - int(np.count_nonzero(gone < site))

    lattice = structure.lattice
    fresh, taken = [], []
    for placement in plan.placements:
        for symbol, xyz in zip(group.elements, placement.cart,
                               strict=True):
            label = structure.suggest_label(symbol, taken=taken)
            taken.append(label)
            fresh.append(Site(symbol, lattice.to_frac(xyz), label=label))
    indices = structure.add_sites(fresh)
    bonding.hold_perception(structure)

    ops = structure.space_group.operations
    bonds = list(structure.bonds)
    n = group.n_atoms
    for k, (site, op) in enumerate(parents):
        first = indices[k * n:(k + 1) * n]
        frac = [np.asarray(structure.sites[i].frac, dtype=float)
                for i in first]
        for i, j, order in group.bonds:
            image = tuple(int(v) for v in np.round(frac[i] - frac[j]))
            bonds.append(Bond(first[i], first[j], image, order))
        parent = renumbered(site)
        target = ops[op].apply(np.asarray(structure.sites[parent].frac,
                                          dtype=float))
        image = tuple(int(v) for v in
                      np.round(frac[group.attach] - target))
        bonds.append(Bond(first[group.attach], parent, image, 1.0,
                          op=op))
    structure.set_bonds(bonds)
    return indices


def _aligning(a, b) -> np.ndarray:
    """The rotation taking unit vector ``a`` onto unit vector ``b``."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    axis = np.cross(a, b)
    sine = float(np.linalg.norm(axis))
    cosine = float(np.dot(a, b))
    if sine < 1e-9:
        if cosine > 0:
            return np.eye(3)
        # Opposite: half a turn about anything perpendicular.
        other = (np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9
                 else np.array([0.0, 1.0, 0.0]))
        axis = np.cross(a, other)
        axis /= float(np.linalg.norm(axis))
        return 2.0 * np.outer(axis, axis) - np.eye(3)
    axis /= sine
    cross = np.array([[0.0, -axis[2], axis[1]],
                      [axis[2], 0.0, -axis[0]],
                      [-axis[1], axis[0], 0.0]])
    return (np.eye(3) + sine * cross
            + (1.0 - cosine) * cross @ cross)


def closest_approach(structure, sites) -> float:
    """The closest any atom of these sites comes to an atom it is not
    bonded to, every image of every site counted.  ``inf`` when
    nothing is within reach.

    Measured on the result and not taken from the plan, because the
    plan cannot see everything: in a cell with a group, each group is
    placed once and the group puts the rest, and those copies are only
    there to be measured once the edit is made.
    """
    from xtal.core.neighbors import neighbor_pairs

    cell = p1.expand(structure)
    new = np.isin(cell.site_idx, np.asarray(list(sites), dtype=int))
    if not new.any():
        return float("inf")
    pairs = neighbor_pairs(cell.frac, structure.lattice, _REACH,
                           min_distance=0.0)
    if not len(pairs):
        return float("inf")
    bonded = {(b.i, b.j, tuple(b.image)) for b in bonding.graph(
        structure).bonds}
    bonded |= {(j, i, tuple(-v for v in image))
               for i, j, image in bonded}
    closest = float("inf")
    for k in np.flatnonzero(new[pairs.i] | new[pairs.j]):
        i, j = int(pairs.i[k]), int(pairs.j[k])
        image = tuple(int(v) for v in pairs.image[k])
        if (i, j, image) in bonded or el.is_dummy(cell.elements[i]) \
                or el.is_dummy(cell.elements[j]):
            continue
        closest = min(closest, float(pairs.distance[k]))
    return closest
