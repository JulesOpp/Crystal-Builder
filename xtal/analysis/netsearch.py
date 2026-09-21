"""
xtal.analysis.netsearch
=======================
Finding a net by what somebody knows about it.

The MOF builder and the Net builder list the same few thousand nets,
and their names are three letters of no mnemonic value, so a search
by name alone is a search for people who did not need one.  What a
chemist knows is the rest of the row MOF+ prints: **the coordination**
("a 3,6 net"), **the space group number**, and **the transitivity**
-- how many kinds of vertex, edge, face and tile.  This is those four
fields, parsed once and matched against a :class:`NetFacts` per row,
so that both lists answer a query the same way.

**The transitivity is half known, and says so.**  p and q are the
``NODE`` and ``EDGE`` lines of an RCSR entry, because the RCSR writes
every net at its maximum symmetry; r and s belong to the net's natural
tiling, which nothing here has.  A pattern may name all four, ``*``
matches anything, and a number where the value is unknown matches
nothing: a list that answered "faces: 2" with every net would be
claiming knowledge it does not have.

**A layer answers to its plane group number** -- hcb is 17 -- and not
to the space group it is built in, because 17 is what the RCSR prints
beside it.  The 2D and 3D boxes are what keep the two numberings from
meeting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import gemmi

from xtal.analysis.rcsr import plane_group_number
from xtal.io.cgd import CgdEntry

__all__ = [
    "NetFacts",
    "NetQuery",
    "NetQueryError",
    "facts_of_entry",
    "space_group_number",
]

#: p, q, r, s: vertices, edges, faces, tiles.
TRANSITIVITY_FIELDS = 4


class NetQueryError(ValueError):
    """A search field that cannot be read, and which one it was."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class NetFacts:
    """What a list row can be searched by."""

    name: str
    dimension: int
    #: One per vertex kind, in file order; repeats are kept.
    coordinations: tuple[int, ...]
    group: str
    #: 1-230 for a 3-D net, 1-17 for a layer; ``None`` for a symbol
    #: nobody recognises, which is still listed and never matched by
    #: number.
    number: int | None
    #: Vertex and edge transitivity; ``None`` where not known.
    p: int | None
    q: int | None

    @property
    def transitivity(self) -> tuple[int | None, ...]:
        return (self.p, self.q, None, None)

    def summary(self) -> str:
        """The line both net lists show beside the name: coordination,
        group and number, and transitivity as the RCSR prints it --
        ``3-c  ·  p6mm (17)  ·  [1 1]``."""
        counts = ", ".join(f"{c}-c" for c in self.coordinations)
        group = (f"{self.group} ({self.number})"
                 if self.number is not None else self.group)
        known = " ".join("?" if v is None else str(v)
                         for v in (self.p, self.q))
        return f"{counts}  ·  {group}  ·  [{known}]"


def space_group_number(symbol: str) -> int | None:
    """The number of a space group symbol, ``None`` if it is none.

    ``I41/amd:2`` is 141: the origin choice is part of how a net was
    written, not of which group it is in.
    """
    try:
        found = gemmi.find_spacegroup_by_name(symbol.strip())
    except (RuntimeError, ValueError):          # pragma: no cover
        return None
    return found.number if found is not None else None


def facts_of_entry(entry: CgdEntry) -> NetFacts:
    """An RCSR entry's row.

    p is the ``NODE`` lines and q the ``EDGE`` lines; an entry with no
    edges written has q unknown rather than zero, because a net with
    no edges is not what it is.
    """
    if entry.dimension == 2:
        number = plane_group_number(entry.group)
    else:
        number = space_group_number(entry.group)
    return NetFacts(
        name=entry.name,
        dimension=entry.dimension,
        coordinations=tuple(n.coordination for n in entry.nodes),
        group=entry.group,
        number=number,
        p=len(entry.nodes) or None,
        q=len(entry.edges) or None)


# ======================================================================
#  THE QUERY
# ======================================================================

_SEPARATORS = re.compile(r"[\s,;]+")


@dataclass(frozen=True)
class NetQuery:
    """The four MOF+ fields, read.  An empty query matches everything.
    """

    name: str = ""
    coordinations: frozenset[int] = frozenset()
    exclusive: bool = False
    #: Inclusive ranges; a single number is a range of one.
    numbers: tuple[tuple[int, int], ...] = ()
    #: p, q, r, s, each a number or ``None`` for ``*``.
    transitivity: tuple[int | None, ...] = (None,) * TRANSITIVITY_FIELDS

    @classmethod
    def parse(cls, name: str = "", coordination: str = "",
              exclusive: bool = False, number: str = "",
              transitivity: str = "") -> NetQuery:
        """Read what was typed; :class:`NetQueryError` names the field
        that could not be read."""
        return cls(name=name.strip().lower(),
                   coordinations=_coordinations(coordination),
                   exclusive=bool(exclusive),
                   numbers=_numbers(number),
                   transitivity=_transitivity(transitivity))

    @property
    def empty(self) -> bool:
        return self == NetQuery(exclusive=self.exclusive)

    def matches(self, facts: NetFacts) -> bool:
        if self.name and self.name not in facts.name.lower():
            return False
        if self.coordinations:
            present = set(facts.coordinations)
            if self.exclusive:
                if present != self.coordinations:
                    return False
            elif not self.coordinations <= present:
                return False
        if self.numbers:
            if facts.number is None or not any(
                    low <= facts.number <= high
                    for low, high in self.numbers):
                return False
        return all(wanted is None or wanted == known
                   for wanted, known in zip(self.transitivity,
                                            facts.transitivity,
                                            strict=True))


def _coordinations(text: str) -> frozenset[int]:
    """``3,6``, ``3 6`` or ``3,6-c``: the RCSR's spelling is typed as
    readily as a list."""
    text = re.sub(r"-?c\b", " ", text.lower())
    found = set()
    for token in _tokens(text):
        if not token.isdigit() or int(token) < 1:
            raise NetQueryError(
                "coordination",
                f"{token!r} is not a coordination number; write them "
                "like 3,6")
        found.add(int(token))
    return frozenset(found)


def _numbers(text: str) -> tuple[tuple[int, int], ...]:
    """``225``, ``191,194`` or ``221-230``."""
    ranges = []
    for token in _tokens(text):
        low, dash, high = token.partition("-")
        if not low.isdigit() or (dash and not high.isdigit()):
            raise NetQueryError(
                "number",
                f"{token!r} is not a space group number or a range "
                "like 221-230")
        low_n = int(low)
        high_n = int(high) if dash else low_n
        if not 1 <= low_n <= high_n <= 230:
            raise NetQueryError(
                "number",
                f"{token!r}: space groups are numbered 1 to 230, and a "
                "range runs low to high")
        ranges.append((low_n, high_n))
    return tuple(ranges)


def _transitivity(text: str) -> tuple[int | None, ...]:
    """``1 1 * *``, ``1,2``, ``[1 1 1 1]`` or packed, ``11**``.

    Packed means one character a field, which is how the RCSR prints
    it; a net with eleven kinds of edge has to be written with
    spaces.  Fields left off the end are ``*``.
    """
    text = text.strip().strip("[]()").strip()
    if not text:
        return (None,) * TRANSITIVITY_FIELDS
    tokens = _tokens(text)
    if len(tokens) == 1:
        tokens = list(tokens[0])
    if len(tokens) > TRANSITIVITY_FIELDS:
        raise NetQueryError(
            "transitivity",
            f"transitivity has four fields at most (p q r s), not "
            f"{len(tokens)}")
    fields: list[int | None] = []
    for token in tokens:
        if token == "*":
            fields.append(None)
        elif token.isdigit() and int(token) >= 1:
            fields.append(int(token))
        else:
            raise NetQueryError(
                "transitivity",
                f"{token!r} is not a count or *; write it like 1 2 * *")
    fields += [None] * (TRANSITIVITY_FIELDS - len(fields))
    return tuple(fields)


def _tokens(text: str) -> list[str]:
    return [t for t in _SEPARATORS.split(text.strip()) if t]
