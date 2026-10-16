"""
xtal.mof.linkers
================
Linkers by what they span: the inverse-design half of the builder.

Every size-matching mode -- a pore partitioner, a merged net's pair of
edges, a window a supertetrahedral net leaves open -- ends in the same
question: *which molecule puts its connection points this far apart?*
A :class:`Requirement` says what is wanted and :func:`suggest`
answers it from two places:

* **the catalogue**, every block measured as it is read
  (:func:`profile`) -- PORMAKE's 867, our own and the workspace's;
* **an isoreticular series** generated from SMILES (:func:`series`):
  cores, spacers and donors put together, each embedded once by
  ``scripts/linker_series.py`` and its spans stored in
  ``data/linker_series.json``.  Stored, like the partitioners' radii,
  so asking costs no RDKit and no seconds; only *using* a generated
  linker embeds it (:func:`write_block`), and a slow test re-embeds the
  table to hold it to its SMILES.

Two numbers describe a block here.  A two-connected one has a
**span**, point to point, which is what an edge's length is made of.
Any other has a **radius**, each donor atom's distance from the
donors' centroid, which is what a node's reach is made of -- the same
number :func:`xtal.mof.partition.measure` takes of a partitioner.

Numpy, json and strings: RDKit only where a molecule is built.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

#: What a connection point hangs off.  ``aryl``: an aromatic carbon,
#: as every PORMAKE carboxylate edge has it (the COO is the node's).
#: ``pyridyl``: a pyridine nitrogen, as a partitioner or a pillar has
#: it.  ``any`` matches both.
DONORS = ("aryl", "pyridyl", "any")

#: The series table, written by ``scripts/linker_series.py``.
SERIES = Path(__file__).with_name("data") / "linker_series.json"


@dataclass(frozen=True)
class Requirement:
    """What a linker must be.

    ``value`` is a span (topicity 2) or a donor radius (3 and up), in
    A, with ``low``-``high`` the range that still builds.  ``why`` is
    the sentence that produced it, for a person.
    """

    topicity: int
    value: float
    low: float
    high: float
    donor: str = "any"
    why: str = ""

    @property
    def measure(self) -> str:
        return "span" if self.topicity == 2 else "donor radius"

    def sentence(self) -> str:
        donor = "" if self.donor == "any" else f"{self.donor} "
        return (f"a {self.topicity}-connected {donor}linker with a "
                f"{self.measure} of {self.value:.2f} A "
                f"({self.low:.2f}-{self.high:.2f})")

    def admits(self, candidate: Candidate) -> bool:
        return (candidate.topicity == self.topicity
                and self.donor in ("any", candidate.donor)
                and self.low <= candidate.value <= self.high)


@dataclass(frozen=True)
class Candidate:
    """A molecule that might meet a :class:`Requirement`.

    ``source`` is ``"catalogue"`` (``name`` is a block) or
    ``"series"`` (``smiles`` builds it).
    """

    name: str
    topicity: int
    donor: str
    value: float
    source: str
    smiles: str = ""
    formula: str = ""


@dataclass(frozen=True)
class Suggestion:
    candidate: Candidate
    miss: float

    def sentence(self, requirement: Requirement) -> str:
        c = self.candidate
        where = "catalogue" if c.source == "catalogue" else "generated"
        return (f"{c.name} ({where}): {requirement.measure} "
                f"{c.value:.2f} A, {self.miss:+.2f} from "
                f"{requirement.value:.2f}")


# ------------------------------------------------------- the catalogue

def profile(block) -> Candidate | None:
    """A catalogue block as a :class:`Candidate`, or ``None`` for one
    with a metal in it (a node, whatever its count) or fewer than two
    points."""
    n = len(block.connections)
    if n < 2 or block.has_metal:
        return None
    positions = np.asarray(block.positions, dtype=float)
    points = list(block.connections)
    partners = [_partner(block.bonds, x) for x in points]
    if any(p is None for p in partners):
        return None
    elements = {block.symbols[p] for p in partners}
    donor = ("pyridyl" if elements == {"N"}
             else "aryl" if elements == {"C"} else "other")
    if n == 2:
        value = float(np.linalg.norm(positions[points[0]]
                                     - positions[points[1]]))
    else:
        value = _radius(positions[partners])
    return Candidate(block.name, n, donor, value, "catalogue",
                     formula=_formula(block))


def _partner(bonds, point):
    for i, j, *_ in bonds:
        if point in (i, j):
            return j if i == point else i
    return None


def _radius(donors: np.ndarray) -> float:
    centre = donors.mean(axis=0)
    return float(np.mean(np.linalg.norm(donors - centre, axis=1)))


def _formula(block) -> str:
    counts: dict[str, int] = {}
    for s in block.body_symbols:
        counts[s] = counts.get(s, 0) + 1
    return "".join(f"{s}{n if n > 1 else ''}"
                   for s, n in sorted(counts.items()))


# ---------------------------------------------------------- the series

#: Units a chain is made of, read from the donor inward.  ``P`` is
#: 1,4-phenylene, ``E`` ethynylene.
_UNITS = {"P": "c2ccc(cc2)", "E": "C#C"}

#: Arms, from the core outward, as unit strings.  Every arm a
#: carboxylate edge has ends on a phenylene, because the node's
#: carboxylate carbon is bonded to an aromatic one in every PORMAKE
#: edge.
_ARMS = ("", "P", "E", "PP", "EP", "PEP", "PPP")

#: Two-connected cores: the middle of a symmetric linker.
_LINEAR = {"P": "phenylene", "E": "ethynylene", "PP": "biphenylene",
           "": "a bond"}

#: Three-connected cores, ``{name: (ring text with R for each arm)}``.
_TRIGONAL = {
    "benzene": "c1c({R})cc({R})cc1{R}",
    "triazine": "c1({R})nc({R})nc({R})n1",
    "pyridine": "c1c({R})cc({R})nc1{R}",
}

#: Four-connected cores: what fills a supertetrahedral net's 4-ring
#: window (:mod:`xtal.mof.decorate`).  The ethylene is
#: tetra(4-pyridyl)ethylene's, the benzene 1,2,4,5's, the methane
#: the one tetrahedral core, for a puckered window.
_TETRAGONAL = {
    "ethylene": "C({R})({R})=C({R}){R}",
    "benzene": "c1c({R})c({R})cc({R})c1{R}",
    "methane": "C({R})({R})({R}){R}",
    # meso-substituted porphyrin: TPyP with pyridyl arms, the
    # tightening agent of In-sod-ZMOF-320.  Ring closures past 9 so an
    # arm's own (1 to 3) cannot close the macrocycle's.
    "porphyrin": ("c%10cc%11nc%10c({R})c%10ccc([nH]%10)c({R})"
                  "c%10ccc(n%10)c({R})c%10ccc([nH]%10)c%11{R}"),
}

#: Six-connected: a 6-ring window's filler.
_HEXAGONAL = {
    "benzene": "c1({R})c({R})c({R})c({R})c({R})c1{R}",
}

#: Topicity -> the cores of that many arms, and the letter a
#: generated name starts with.
_BRANCHED = {3: ("T", _TRIGONAL), 4: ("Q", _TETRAGONAL),
             6: ("H", _HEXAGONAL)}


def series() -> list[tuple[str, int, str, str]]:
    """Every generated linker as ``(name, topicity, donor, smiles)``.

    Two-connected: an aryl edge is ``*`` + phenylenes and ethynylenes
    + ``*``, starting and ending on a phenylene; a pyridyl one is two
    4-pyridyls with the same between them.  Three-, four- and
    six-connected: a core with equal arms, each ending on a donor.
    """
    out = []
    for core in _LINEAR:
        for arm in _ARMS:
            chain = arm + core + arm[::-1]
            if not chain:
                continue
            if chain[0] == "P" and chain[-1] == "P":
                out.append((f"L-{chain}-aryl", 2, "aryl",
                            _linear(chain, "aryl")))
            out.append((f"L-{chain}-py", 2, "pyridyl",
                        _linear(chain, "pyridyl")))
    for topicity, (letter, cores) in _BRANCHED.items():
        for core, ring in cores.items():
            for arm in _ARMS:
                for donor in ("aryl", "pyridyl"):
                    if donor == "aryl" and not arm.endswith("P"):
                        continue
                    if topicity > 3 and len(arm) > 2:
                        # A window filler is a few A across; three
                        # units on four arms is a cage of its own.
                        continue
                    name = f"{letter}-{core}-{arm or '0'}-{donor[:2]}"
                    out.append((name, topicity, donor,
                                _trigonal(ring, arm, donor)))
    # One spelling per chain: a palindrome reached from two cores
    # (PP from core P with arm P, and from core PP with none).
    seen, unique = set(), []
    for item in out:
        if item[3] not in seen:
            seen.add(item[3])
            unique.append(item)
    return unique


def _linear(chain: str, donor: str) -> str:
    body = "".join(_UNITS[u] for u in chain)
    if donor == "aryl":
        return "*" + body + "*"
    return "*[n+]1ccc(cc1)" + body + "c1cc[n+](*)cc1"


def _trigonal(ring: str, arm: str, donor: str) -> str:
    end = "c3cc[n+](*)cc3" if donor == "pyridyl" else ""
    # From the core outward; an aryl arm's last phenylene carries the
    # point itself, para to where it joins.
    units = "".join(_UNITS[u] for u in arm)
    if donor == "aryl":
        branch = units + "*"
    else:
        branch = units + end
    return ring.format(R=branch)


@lru_cache(maxsize=1)
def stored() -> tuple[Candidate, ...]:
    """The series as measured, from :data:`SERIES`; empty if the table
    did not travel."""
    try:
        rows = json.loads(SERIES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(Candidate(r["name"], r["topicity"], r["donor"],
                           r["value"], "series", r["smiles"],
                           r.get("formula", ""))
                 for r in rows)


def measure_smiles(smiles: str) -> tuple[float, str]:
    """``(value, formula)`` for one starred SMILES: its span when it
    has two points, its donor radius otherwise.  Needs RDKit."""
    from xtal.build.molecule import from_smiles

    molecule = from_smiles(smiles)
    cart = np.asarray(molecule.cart, dtype=float)
    points = list(molecule.connections)
    if len(points) == 2:
        value = float(np.linalg.norm(cart[points[0]] - cart[points[1]]))
    else:
        donors = [_partner(molecule.bonds, x) for x in points]
        value = _radius(cart[donors])
    return value, molecule.formula


# ------------------------------------------------------------- asking

def candidates(catalog=None) -> list[Candidate]:
    """Every catalogue block that is a linker, and the whole series."""
    found = []
    if catalog is not None:
        for block in catalog.building_blocks():
            c = profile(block)
            if c is not None:
                found.append(c)
    return found + list(stored())


def suggest(requirement: Requirement, catalog=None, n: int = 8,
            pool=None) -> list[Suggestion]:
    """The ``n`` candidates nearest ``requirement``, inside its range,
    nearest first.  ``pool`` overrides where they come from."""
    pool = candidates(catalog) if pool is None else pool
    fits = [Suggestion(c, c.value - requirement.value)
            for c in pool if requirement.admits(c)]
    fits.sort(key=lambda s: (abs(s.miss), s.candidate.source != "catalogue",
                             s.candidate.name))
    return fits[:n]


def nearest_misses(requirement: Requirement, catalog=None, n: int = 3,
                   pool=None) -> list[Suggestion]:
    """When nothing is inside the range: the closest outside it, so a
    person learns how far off the nearest real molecule is."""
    pool = candidates(catalog) if pool is None else pool
    near = [Suggestion(c, c.value - requirement.value) for c in pool
            if c.topicity == requirement.topicity
            and requirement.donor in ("any", c.donor)]
    near.sort(key=lambda s: abs(s.miss))
    return near[:n]


def write_block(candidate: Candidate, folder) -> Path:
    """Write a series candidate as a building block named after it.
    Needs RDKit.  A catalogue candidate is already a block."""
    if candidate.source != "series":
        raise ValueError(f"{candidate.name} is already a block")
    from xtal.build.molecule import from_smiles
    from xtal.io.atomic import write_text
    from xtal.mof.block import block_string

    molecule = from_smiles(candidate.smiles, name=candidate.name)
    path = Path(folder) / f"{candidate.name}.xyz"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, block_string(molecule.to_structure()))
    return path


def within(value: float, tolerance: float) -> tuple[float, float]:
    """``(low, high)`` a symmetric tolerance makes of ``value``."""
    return value - abs(tolerance), value + abs(tolerance)

