"""
xtal.mof.merged_nets
====================
The merged nets of Jiang et al., Science 386, 659 (2024), as a table.

Two edge-transitive nets that share a signature net merge into one
minimal net with both kinds of edge: spn and hxg into ``sph``.  The
paper enumerates 353 of them from the 53 three-periodic edge-transitive
nets, merged with another three-periodic one (3p-3p), a layer (3p-2p),
a rod (3p-1p) or a polyhedron (3p-0p).  Its Data S1 lists each with
its parents and how the vertices merge, Data S6 gives each as a
Systre-relaxed ``.cgd``, the SM's tables S9-S12 its edge ratio, Data
S7 the platforms it proposes and Data S8 the MOFs it made.

``scripts/merged_nets.py`` reads those files (in ``JulesWork/``, not
shipped) and writes ``data/merged_nets.json`` and
``data/merged_nets.cgd.gz``.  **Every row is held to its parents by
decomposition**: the script runs :func:`xtal.analysis.components.
components` over each net's own file and records what each set of
edge kinds spans; a test holds every row's record to the parents it
lists, so a transcription slip -- or a net that does not break the
way the paper says -- fails rather than ships.  A three-periodic
parent is held by name.  A layer, rod or polyhedron parent is held by
a component of that periodicity, and a polyhedron by its vertex count
and degrees as well (:data:`POLYHEDRA`), since the RCSR names no
0-periodic net.

Of the 353, 61 are in the RCSR's 2019 file; the rest are offered to
the MOF builder from the paper's own files (:func:`topologies`), a
name in neither PORMAKE nor the RCSR only.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from xtal.core.atom_groups import META_KEY

DATA = Path(__file__).with_name("data")
TABLE = DATA / "merged_nets.json"
NETS = DATA / "merged_nets.cgd.gz"

#: The four ways a merged net is made, by the periodicity of its
#: second parent.
TYPES = ("3p-3p", "3p-2p", "3p-1p", "3p-0p")

#: The paper's citation, for a person.
SOURCE = ("H. Jiang et al., Merged-nets enumeration for the systematic "
          "design of multicomponent reticular structures, Science 386, "
          "659 (2024)")

#: The 0-periodic parents, by vertex count and degrees: the
#: polyhedra the RCSR has no file for.
POLYHEDRA = {
    "tet": (4, (3,)),
    "oct": (6, (4,)),
    "cub": (8, (3,)),
    "cuo": (12, (4,)),
    "rdo": (14, (3, 4)),
}


@dataclass(frozen=True)
class Part:
    """What one set of edge kinds spans, as the script found it."""

    kinds: tuple[int, ...]
    periodicity: int
    name: str = ""
    #: For a 0-periodic piece: its vertex count and degrees.
    shape: tuple = ()


@dataclass(frozen=True)
class MergedNet:
    """One row of the table."""

    name: str
    type: str
    parents: tuple[str, str]
    #: Each parent's coordination, as the paper writes it (``"3,6"``).
    parent_cn: tuple[str, str]
    #: The merged net's vertices, as the paper writes them: a merged
    #: one is ``"6+6=12"``.
    cn: tuple[str, ...]
    #: ``(original, Systre)`` edge ratio, ``None`` where the SM's text
    #: did not give it back (54 rows).  ``"non"`` is the paper's for a
    #: net with more than two edge lengths.
    ratio: tuple | None = None
    #: Platforms Data S7 proposes, as its cluster codes (``"M6a"``).
    proposed: tuple[str, ...] = ()
    #: MOFs made on it: the paper's own (Data S8) and those it cites.
    made: tuple[str, ...] = ()
    parts: tuple[Part, ...] = field(default=(), repr=False)

    @property
    def coordination(self) -> tuple[int, ...]:
        """Each vertex's coordination in the merged net."""
        out = []
        for written in self.cn:
            text = str(written).split("=")[-1]
            out.append(int(text))
        return tuple(out)

    @property
    def merged_cn(self) -> int:
        """The coordination of the vertex the parents share."""
        merged = [c for c in self.cn if "+" in str(c)]
        return int(str(merged[0]).split("=")[-1]) if merged else 0

    def held(self) -> list[str]:
        """Why the recorded parts do not hold the parents, or ``[]``.

        The first parent must be named by some set of edge kinds, and
        the second spanned by a set disjoint from it: by name when it
        is three-periodic; at its periodicity when it is a layer, rod
        or polyhedron -- two kinds, where the symmetry splits the
        layer's edges in two (bok, pyq) -- and a polyhedron with its
        vertex count and degrees.  Disjoint and not the complement,
        because a polyhedron merged through 2-c vertices leaves the
        edges to them in neither parent (dih: dia, cub, and two kinds
        between).
        """
        first, second = self.parents
        names = sorted({p.name for p in self.parts if p.name})
        if not self._all_named(first):
            return [f"{first} is not among {names}"]
        if self.components():
            return []
        if self.type == "3p-3p":
            return [f"no {second} beside {first} among {names}"]
        return [f"no {self.periodicity}-periodic {second} beside "
                f"{first}"]

    @property
    def periodicity(self) -> int:
        """The second parent's periodicity: 3 to 0."""
        return 3 - TYPES.index(self.type)

    def _all_named(self, name: str) -> list[Part]:
        return [p for p in self.parts if p.name == name]

    def _is_second(self, part: Part) -> bool:
        second = self.parents[1]
        if self.type == "3p-3p":
            return part.name == second
        if part.periodicity != self.periodicity:
            return False
        if self.periodicity == 0 and second in POLYHEDRA:
            return tuple(part.shape) == _shape(POLYHEDRA[second])
        return True

    def components(self) -> list[tuple[str, tuple[int, ...]]]:
        """``(parent, edge kinds)`` for both parents, the pair that
        covers the most kinds and then the fewest; ``[]`` when the
        parts hold no such pair."""
        first, second = self.parents
        best = None
        for one in self._all_named(first):
            for two in self.parts:
                if set(one.kinds) & set(two.kinds) \
                        or not self._is_second(two):
                    continue
                size = len(one.kinds) + len(two.kinds)
                key = (-size, len(one.kinds))
                if best is None or key < best[0]:
                    best = (key, one, two)
        if best is None:
            return []
        return [(first, best[1].kinds), (second, best[2].kinds)]

    def sentence(self) -> str:
        made = f"; made: {', '.join(self.made)}" if self.made else ""
        return (f"{self.name} = {self.parents[0]} + {self.parents[1]} "
                f"({self.type}, {'-'.join(map(str, self.coordination))}"
                f"-c){made}")


def _shape(spec) -> tuple:
    count, degrees = spec
    return (count, tuple(degrees))


@lru_cache(maxsize=1)
def table() -> tuple[MergedNet, ...]:
    """Every row, in the paper's order; empty if the table did not
    travel."""
    try:
        rows = json.loads(TABLE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(_row(r) for r in rows)


def _row(r: dict) -> MergedNet:
    return MergedNet(
        r["name"], r["type"], tuple(r["parents"]), tuple(r["parent_cn"]),
        tuple(r["cn"]), tuple(r["ratio"]) if r.get("ratio") else None,
        tuple(r.get("proposed", ())), tuple(r.get("made", ())),
        tuple(Part(tuple(p["kinds"]), p["periodicity"], p.get("name", ""),
                   tuple((p["shape"][0], tuple(p["shape"][1])))
                   if p.get("shape") else ())
              for p in r.get("parts", ())))


def row(name: str) -> MergedNet | None:
    return next((r for r in table() if r.name == name), None)


def by_parent(parent: str) -> tuple[MergedNet, ...]:
    """The merged nets ``parent`` is one of the parents of."""
    return tuple(r for r in table() if parent in r.parents)


@lru_cache(maxsize=1)
def texts() -> dict[str, str]:
    """Name -> the paper's ``.cgd`` for it."""
    try:
        with gzip.open(NETS, "rt", encoding="utf-8") as handle:
            whole = handle.read()
    except OSError:
        return {}
    out = {}
    for block in whole.split("\nEND\n"):
        block = block.strip()
        if not block:
            continue
        text = block + "\nEND\n"
        for line in block.splitlines():
            words = line.split()
            if len(words) >= 2 and words[0].upper() == "NAME":
                out[words[1]] = text
                break
    return out


def entry(name: str):
    """The paper's own :class:`xtal.io.cgd.CgdEntry` for ``name``."""
    from xtal.io.cgd import read_cgd_string

    text = texts().get(name)
    if text is None:
        raise KeyError(f"no merged net called {name!r}")
    return read_cgd_string(text).entries[0]


#: The paper's nets PORMAKE cannot read even by midpoints
#: (:mod:`xtal.mof.midpoints`), by ``scripts/merged_nets.py
#: --rejects``: 8 of the 291 only the paper has.  Each has two edges
#: crossing at one midpoint (thw's 10-c rods along a and c), and
#: PORMAKE's reader merges coinciding edge centres, so its file
#: cannot hold the net.  Without the midpoint reading it was 180.
REJECTS = frozenset({
    "brw", "flw", "rew", "rhe", "spa", "tbw", "tcw", "thw",
})


def topologies(have: frozenset = frozenset()) -> tuple:
    """The paper's nets as catalogue topologies, leaving out every
    name in ``have`` (PORMAKE's, ours and the RCSR's) and the
    :data:`REJECTS`: one name is one net, and the RCSR's file is
    the one the rest of the catalogue already reads."""
    return _topologies(frozenset(have))


@lru_cache(maxsize=4)
def _topologies(have: frozenset) -> tuple:
    from xtal.analysis import rcsr
    from xtal.io.cgd import write_cgd_string
    from xtal.mof.catalog import Topology

    found = []
    for name in sorted(texts()):
        if name in have or name in REJECTS:
            continue
        try:
            written = rcsr.as_net(entry(name))
        except (rcsr.RcsrError, ValueError):
            continue
        text = write_cgd_string([written]).rstrip() + "\n"
        topology = Topology(
            name, None, written.group,
            tuple(node.coordination for node in written.nodes), text,
            len(written.edges))
        topology._cache["layer"] = False
        found.append(topology)
    return tuple(found)


# ----------------------------------------------------------------------
#  Drawing one with its parents as groups
# ----------------------------------------------------------------------

#: Where a drawn net carries its groups for the window to make.
GROUPS_KEY = META_KEY

#: A colour per parent: the first two of the window's orbit colours'
#: hues, picked to be told apart at a glance.
COLOURS = ((214, 96, 77), (67, 147, 195), (120, 180, 90))


def drawn(net, parts=None, scale: float | None = None,
          beads: int | None = None):
    """``net`` (a name in the table, or a :class:`CgdEntry`) drawn as
    :mod:`xtal.build.topology` draws any net, with one group per part:
    that part's edges and the vertices only it touches.  A vertex the
    parts share is in no group, so unticking one parent leaves the
    other whole.  ``parts`` defaults to the row's parents."""
    from xtal.build import topology

    if isinstance(net, str):
        record = row(net)
        source = entry(net)
        if parts is None and record is not None:
            parts = record.components()
    else:
        source = net
    from xtal.analysis import rcsr

    source = rcsr.as_net(source)
    parts = list(parts or [])
    beads = beads or topology.BEADS
    kwargs = {} if scale is None else {"scale": scale}
    structure = topology.structure_for(source, beads=beads, **kwargs)
    labels = {site.label: n for n, site in enumerate(structure.sites)}
    per_edge = beads - 1
    node_lines = {}
    for line, (start, end) in enumerate(source.edges):
        for point in (start, end):
            node_lines.setdefault(_node_of(source, point), set()).add(line)
    groups = []
    for k, (name, kinds) in enumerate(parts):
        kinds = set(kinds)
        sites = []
        for line in kinds:
            for b in range(per_edge):
                label = f"{topology.EDGE_ELEMENT}{line * per_edge + b + 1}"
                if label in labels:
                    sites.append(labels[label])
        for node, lines in node_lines.items():
            label = f"{topology.NODE_ELEMENT}{node + 1}"
            if lines <= kinds and label in labels:
                sites.append(labels[label])
        groups.append((name, COLOURS[k % len(COLOURS)], sorted(sites)))
    structure.meta[GROUPS_KEY] = groups
    return structure


def _node_of(entry, point) -> int:
    """Which node line ``point`` is an image of."""
    import numpy as np

    from xtal.analysis.rcsr import space_group_operations

    p = np.asarray(point, dtype=float)
    for n, node in enumerate(entry.nodes):
        here = np.asarray(node.frac, dtype=float)
        for rot, trans in space_group_operations(entry.group):
            delta = rot @ here + trans - p
            if np.allclose(delta - np.round(delta), 0.0, atol=1e-4):
                return n
    return -1
