"""
xtal.mof.partition
==================
Pore-space partition: which partitioner fits which acs framework.

An ``acs`` framework (MIL-88, MOF-235) is M3O(RCO2)6 trimers joined by
a dicarboxylate, with hexagonal channels along *c*.  Bu and Feng's
pacs frameworks put a C3 pyridyl on the channel axis in every trimer
layer, its three nitrogens on the open sites of the three trimers
round it; the trimer becomes 9-connected and the net is ``nia-d``.

Which partitioner fits is a matter of two lengths, and both are exact
in the deposited structures (COD 4134050-4134054, 4518868-4518869):

* the **partitioner sets a**.  Its nitrogen sits on the metal's
  open-site line and its centre on the channel axis, so
  ``a / sqrt(3) = r_L + d(M-N) + r_M`` -- donor radius, dative bond,
  trimer centre to metal.  Held to 0.01 A on all six.
* the **linker sets c**, given *a*.  Trimer centres a linker apart
  are ``l`` apart and sit a/sqrt(3) off the axis and c/2 apart in
  height, so ``c = 2 sqrt(l^2 - a^2/3)``.  Held to 0.02 A.

``l`` comes from the blocks: twice the node's centre-to-point reach
plus the linker's point-to-point span, for a straight joint.  What is
left free is how far the linker climbs out of the trimer plane,
``phi = asin(c / 2l)``; the crystals have it at 33.6-46.8 degrees.  A
pair whose phi falls outside :data:`PHI_WINDOW` is refused by name,
as is one with ``l <= a / sqrt(3)`` (the linker cannot reach the next
layer at all) and one whose partitioner layers would be closer than
:data:`MIN_LAYER_GAP`.

Nothing here builds; a build on ``nia-d`` is the confirmation, and its
scaler is what finally sets the cell.  This is the instant answer the
dialog shows while a person chooses, and the requirement the
inverse-design search is handed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from xtal.mof.attach import DATIVE_MN

#: Linker elevation out of the trimer plane, degrees, that a build is
#: offered for.  The deposited pacs frameworks span 33.6-46.8; the
#: window allows the carboxylate hinge some way beyond either end and
#: no further, since MIL-88B's closed form (56 degrees) is the hinge
#: at the end of its travel.
PHI_WINDOW = (28.0, 52.0)

#: The middle of the observed elevations, which a fit is ranked by.
PHI_IDEAL = 38.0

#: Elevations this close count as the same fit, degrees, and the
#: catalogue's order decides between them.  tpt and tpb on a Ni trimer
#: with BDC are 0.5 and 0.15 degrees off ideal, which says nothing; tpb
#: is the one whose central C-H meets the framework at 1.52 A, and tpt
#: is the one the pacs literature is built on.
PHI_TIE = 2.0

#: Partitioner layers are c/2 apart.  Closer than a pi-stack and the
#: rings meet; nothing deposited is under 7 A.
MIN_LAYER_GAP = 3.4


@dataclass(frozen=True)
class Partitioner:
    """A pyridyl that partitions a channel.

    ``smiles`` stars each donor nitrogen (``[n+]`` so it sanitises
    with its fourth bond); the star is the connection point, on the
    lone-pair line.  ``radius`` is the donor nitrogens' distance from
    their centroid as embedded once by :func:`measure` and stored, so
    ranking needs no RDKit; a test holds the two equal.
    """

    name: str
    full_name: str
    smiles: str
    radius: float
    topicity: int = 3


_PY = "c1cc[n+](*)cc1"

#: The tritopic partitioners of the pacs literature, and the extended
#: one a larger linker asks for, in the order a tie is broken: the
#: most used first.
PARTITIONERS = (
    Partitioner("tpt", "2,4,6-tri(4-pyridyl)-1,3,5-triazine",
                f"*[n+]1ccc(cc1)-c1nc(nc(n1)-{_PY})-{_PY}", 5.58),
    Partitioner("tpb", "1,3,5-tri(4-pyridyl)benzene",
                f"*[n+]1ccc(cc1)-c1cc(cc(c1)-{_PY})-{_PY}", 5.67),
    Partitioner("tripp", "2,4,6-tri(4-pyridyl)pyridine",
                f"*[n+]1ccc(cc1)-c1cc(cc(n1)-{_PY})-{_PY}", 5.63),
    Partitioner("tppb", "1,3,5-tris(4'-(4-pyridyl)phenyl)benzene",
                "*[n+]1ccc(cc1)-c1ccc(cc1)-c1cc(cc(c1)-c1ccc(cc1)"
                f"-{_PY})-c1ccc(cc1)-{_PY}", 9.98),
)


def partitioner(name: str) -> Partitioner:
    for p in PARTITIONERS:
        if p.name == name:
            return p
    known = ", ".join(p.name for p in PARTITIONERS)
    raise KeyError(f"no partitioner {name!r}; known: {known}")


def measure(smiles: str) -> float:
    """Embed a starred SMILES and return its donors' mean distance
    from their centroid.  Needs the ``build`` extra."""
    from xtal.build.molecule import from_smiles

    molecule = from_smiles(smiles)
    cart = np.asarray(molecule.cart, dtype=float)
    donors = [_partner(molecule.bonds, x) for x in molecule.connections]
    centre = cart[donors].mean(axis=0)
    return float(np.mean([np.linalg.norm(cart[d] - centre)
                          for d in donors]))


def _partner(bonds, point: int) -> int:
    for i, j, *_ in bonds:
        if point in (i, j):
            return j if i == point else i
    raise ValueError(f"connection point {point} is bonded to nothing")


@dataclass(frozen=True)
class Node:
    """What the arithmetic needs of a trimer block.

    ``reach`` is the oxide to carboxylate-point distance, averaged;
    ``radius`` the oxide to metal; ``metal`` the element on the open
    sites.
    """

    name: str
    metal: str
    radius: float
    reach: float

    @property
    def dative(self) -> float:
        return DATIVE_MN[self.metal]


def node_geometry(block) -> Node:
    """A trimer block's lengths, from a catalogue ``BuildingBlock``.

    The axial points of a nine-connected twin are left out of the
    reach: they hang off a metal, not a carboxylate.
    """
    from xtal.mof.trimer import Block, TrimerError, trimers

    plain = Block(list(block.symbols), np.asarray(block.positions),
                  list(block.bonds), list(block.connections))
    found = trimers(plain)
    if len(found) != 1:
        raise TrimerError(f"{block.name} is not an M3O trimer")
    core = found[0]
    centre = plain.positions[core.oxide]
    metals = [plain.symbols[m] for m in core.metals]
    radius = float(np.mean([np.linalg.norm(plain.positions[m] - centre)
                            for m in core.metals]))
    reach = [np.linalg.norm(plain.positions[x] - centre)
             for x in plain.connections
             if plain.symbols[_partner(plain.bonds, x)] not in DATIVE_MN]
    # The open site the partitioner takes; a mixed-metal trimer
    # (Mg2Ti, Co2V) is written with the divalent metal there.
    metal = max(set(metals), key=metals.count)
    return Node(block.name, metal, radius, float(np.mean(reach)))


def linker_span(block) -> float:
    """A two-connected linker's point-to-point distance."""
    if len(block.connections) != 2:
        raise ValueError(f"{block.name} has {len(block.connections)} "
                         f"connection points; a linker has two")
    a, b = block.connections
    return float(np.linalg.norm(np.asarray(block.positions[a])
                                - np.asarray(block.positions[b])))


@dataclass(frozen=True)
class Fit:
    """One partitioner with one trimer and one linker, predicted.

    ``reason`` says why it cannot be built, or is empty.  ``strain``
    is how far the elevation sits from :data:`PHI_IDEAL`, in degrees;
    a refused fit sorts after every buildable one.
    """

    partitioner: str
    node: str
    linker: str
    a: float
    c: float
    length: float
    phi: float
    reason: str = ""
    notes: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.reason

    @property
    def strain(self) -> float:
        return abs(self.phi - PHI_IDEAL) if self.ok else math.inf

    def sentence(self) -> str:
        if not self.ok:
            return f"{self.partitioner}: {self.reason}"
        return (f"{self.partitioner}: a {self.a:.2f} A, c {self.c:.2f} "
                f"A, linker {self.phi:.0f} degrees out of the trimer "
                f"plane")


def cell_a(node: Node, radius: float) -> float:
    """The cell edge a partitioner of donor radius ``radius`` sets."""
    return math.sqrt(3.0) * (radius + node.dative + node.radius)


def predict(node: Node, linker_name: str, span: float,
            p: Partitioner) -> Fit:
    """Decision 1's closed form for one partitioner, trimer and linker."""
    a = cell_a(node, p.radius)
    length = 2.0 * node.reach + span
    off_axis = a / math.sqrt(3.0)
    base = dict(partitioner=p.name, node=node.name, linker=linker_name,
                a=a, length=length)
    if length <= off_axis:
        return Fit(**base, c=math.nan, phi=math.nan,
                   reason=f"too wide for {linker_name}: the trimers "
                          f"would sit {off_axis:.1f} A off the axis "
                          f"and the linker reaches {length:.1f} A")
    c = 2.0 * math.sqrt(length ** 2 - off_axis ** 2)
    phi = math.degrees(math.asin(c / (2.0 * length)))
    low, high = PHI_WINDOW
    reason = ""
    if c / 2.0 < MIN_LAYER_GAP:
        reason = (f"its layers would be {c / 2:.1f} A apart, closer "
                  f"than a pi-stack")
    elif phi < low:
        reason = (f"too wide for {linker_name}: the linker would lie "
                  f"{phi:.0f} degrees out of the trimer plane, flatter "
                  f"than a carboxylate hinge goes ({low:.0f})")
    elif phi > high:
        reason = (f"too small for {linker_name}: the linker would "
                  f"stand {phi:.0f} degrees out of the trimer plane, "
                  f"steeper than a carboxylate hinge goes "
                  f"({high:.0f})")
    return Fit(**base, c=c, phi=phi, reason=reason)


def rank(node: Node, linker_name: str, span: float,
         candidates=PARTITIONERS) -> list[Fit]:
    """Every candidate partitioner, buildable first, least strained
    first."""
    order = {p.name: k for k, p in enumerate(candidates)}
    fits = [predict(node, linker_name, span, p) for p in candidates]
    return sorted(fits, key=lambda f: (not f.ok, _bucket(f),
                                       order[f.partitioner]))


def _bucket(fit: Fit) -> float:
    return math.floor(fit.strain / PHI_TIE) if fit.ok else math.inf


@dataclass(frozen=True)
class SpanRequirement:
    """What a linker must span: ``span`` within ``tolerance``, A."""

    span: float
    low: float
    high: float

    def sentence(self) -> str:
        return (f"a linker spanning {self.span:.2f} A between its "
                f"connection points ({self.low:.2f}-{self.high:.2f})")


def linker_requirement(node: Node, p: Partitioner, *,
                       pocket: float | None = None) -> SpanRequirement:
    """The reverse: the linker a chosen partitioner asks for.

    With no ``pocket`` the span puts the linker at :data:`PHI_IDEAL`;
    with one, the span that makes the partitioner layers ``pocket``
    apart (c/2).  ``low`` and ``high`` are the spans that put it at
    either end of :data:`PHI_WINDOW` -- or, for a pocket, the same
    span, since a pocket height is a target and not a range.
    """
    off_axis = cell_a(node, p.radius) / math.sqrt(3.0)

    def span_at(phi):
        return off_axis / math.cos(math.radians(phi)) - 2.0 * node.reach

    if pocket is not None:
        exact = math.hypot(off_axis, pocket) - 2.0 * node.reach
        return SpanRequirement(exact, exact, exact)
    low, high = PHI_WINDOW
    return SpanRequirement(span_at(PHI_IDEAL), span_at(low),
                           span_at(high))


def rank_linkers(node: Node, p: Partitioner, linkers) -> list[Fit]:
    """Every two-connected linker in ``linkers`` (catalogue blocks)
    against one partitioner, buildable and least strained first.

    A two-connected block with a metal in it is a node, whatever its
    count says -- CuHTTP's CuS4 is one -- and is left out.
    """
    fits = []
    for block in linkers:
        if len(block.connections) != 2 or block.has_metal:
            continue
        fits.append(predict(node, block.name, linker_span(block), p))
    return sorted(fits, key=lambda f: (not f.ok, f.strain, f.linker))



# ----------------------------------------------------------- the build

#: What ``partition`` is set to for the ranker's first choice.
AUTO = "auto"

#: The net a partitioned acs is built on: ``nia-d``'s graph at the
#: pacs frameworks' proportions (``xtal/mof/library/topologies``).
NET = "pacs"


def block_name(p: Partitioner) -> str:
    """What a partitioner's building block is called in a run."""
    return f"pacs-{p.name}"


def partitioned(request, catalog, folder):
    """``(request, catalog, fit)``: an ``acs`` request rewritten onto
    :data:`NET`, with the blocks it needs written into ``folder``.

    The node is the trimer's nine-connected twin, the partitioner the
    second node, the linker the trimer-to-trimer edge, and the edge
    from trimer to partitioner is left empty -- a dative joint.  A
    partitioner the arithmetic refuses is refused here by the same
    sentence, never built strained.
    """
    from dataclasses import replace

    from xtal.mof.build import MofError
    from xtal.mof.catalog import Catalog, CatalogError
    from xtal.mof.trimer import TrimerError, twin_name, write_twin

    if request.topology != "acs":
        raise MofError(f"pore-space partition is of an acs framework; "
                       f"this build is on {request.topology}")
    nodes = set(request.nodes.values())
    edges = set(request.edges.values())
    if len(nodes) != 1:
        raise MofError("a partitioned acs has one trimer node; name it")
    if len(edges) != 1:
        raise MofError("a partitioned acs needs one linker between "
                       "its trimers; name it")
    node_name, linker_name = nodes.pop(), edges.pop()
    try:
        node_block = catalog.building_block(node_name)
        linker = catalog.building_block(linker_name)
        node = node_geometry(node_block)
    except (CatalogError, TrimerError) as exc:
        raise MofError(str(exc)) from None
    span = linker_span(linker)

    if request.partition == AUTO:
        fits = rank(node, linker_name, span)
        if not fits[0].ok:
            raise MofError("no partitioner fits: " + "; ".join(
                f.sentence() for f in fits))
        fit = fits[0]
    else:
        try:
            chosen = partitioner(request.partition)
        except KeyError as exc:
            raise MofError(str(exc.args[0])) from None
        fit = predict(node, linker_name, span, chosen)
        if not fit.ok:
            raise MofError(fit.sentence())
    chosen = partitioner(fit.partitioner)

    folder = Path(folder) / "blocks"
    folder.mkdir(parents=True, exist_ok=True)
    if node_block.n_connections == 9:
        twin = node_name
    else:
        try:
            write_twin(node_block.path, folder)
        except TrimerError as exc:
            raise MofError(f"{node_name}: {exc}") from None
        twin = twin_name(node_name)
    _write_partitioner(chosen, folder, catalog)

    catalog = Catalog(catalog.topology_dirs, catalog.bb_dirs + (folder,))
    rewritten = replace(request, topology=NET,
                        nodes={0: twin, 1: block_name(chosen)},
                        edges={(0, 0): linker_name},
                        partition=chosen.name)
    return rewritten, catalog, fit


def _write_partitioner(p: Partitioner, folder: Path, catalog) -> None:
    """The partitioner's block, from its SMILES -- or the one a person
    already put in the catalogue under the same name, which wins."""
    from xtal.build import chem
    from xtal.mof.build import MofError
    from xtal.mof.catalog import CatalogError

    try:
        catalog.building_block(block_name(p))
        return
    except CatalogError:
        pass
    if not chem.installed():
        raise MofError(f"building {p.name} from its SMILES needs the "
                       f"'build' extra (RDKit)")
    from xtal.build.molecule import from_smiles
    from xtal.io.atomic import write_text
    from xtal.mof.block import block_string

    molecule = from_smiles(p.smiles, name=p.name)
    write_text(folder / f"{block_name(p)}.xyz",
               block_string(molecule.to_structure()))


def measured_dative(structure) -> list[float]:
    """Every metal-to-nitrogen bond length in a built framework, A."""
    from xtal.core import bonding, p1

    cell = p1.expand(structure)
    matrix = np.asarray(structure.lattice.matrix)
    out = []
    for bond in bonding.graph(structure).bonds:
        pair = {cell.elements[bond.i], cell.elements[bond.j]}
        if "N" in pair and pair & set(DATIVE_MN):
            d = (cell.frac[bond.j] + np.asarray(bond.image)
                 - cell.frac[bond.i]) @ matrix
            out.append(float(np.linalg.norm(d)))
    return out
