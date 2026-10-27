"""
xtal.fullerene.catalogue
========================
The cages a person can ask for by size: every isomer from C20 to C40
and every isolated-pentagon (IPR) one from C60 to C100, each as its
canonical spiral and the order of its point group.

The table is ``data/spirals.json``, written by
``scripts/fullerene_spirals.py`` and never enumerated here: growing
IPR C78's spirals takes fourteen seconds and C100's minutes.  An
isomer is numbered in spiral order, the Atlas of Fullerenes' own --
among all isomers to C40, among the IPR ones from C60.

**A point group is named only where it was checked by hand** (the
famous cages, below); the order of every isomer's group is in the
table, and a test holds each name to it.  Anything else is
"isomer k of K".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources

from xtal.fullerene.spiral import FullereneError

__all__ = ["Isomer", "GROUP_ORDER", "NAMED", "DEFAULTS", "sizes",
           "isomers", "isomer", "default"]

#: The order of each point group named below, reflections included.
GROUP_ORDER = {"Ih": 120, "Td": 24, "D6h": 24, "D6d": 24, "D5h": 20,
               "D5d": 20, "D3h": 12, "D2d": 8, "D3": 6, "D2": 4,
               "C2v": 4}

#: The point groups checked by hand, by size and isomer number, from
#: the Atlas (Fowler and Manolopoulos 1995) and the IPR literature.
NAMED = {
    20: {1: "Ih"},
    24: {1: "D6d"},
    26: {1: "D3h"},
    28: {1: "D2", 2: "Td"},
    30: {1: "D5h", 2: "C2v", 3: "C2v"},
    36: {14: "D2d", 15: "D6h"},
    40: {39: "D5d", 40: "Td"},
    60: {1: "Ih"},
    70: {1: "D5h"},
    72: {1: "D6d"},
    74: {1: "D3h"},
    76: {1: "D2", 2: "Td"},
    78: {1: "D3", 2: "C2v", 3: "C2v", 4: "D3h", 5: "D3h"},
    80: {1: "D5d", 2: "D2", 3: "C2v", 4: "D3", 5: "C2v", 6: "D5h",
         7: "Ih"},
    84: {22: "D2", 23: "D2d", 24: "D6h"},
}

#: The isomer a size opens on, where it is not the first: the one
#: people mean by the formula.
DEFAULTS = {28: 2, 36: 15, 40: 40, 80: 7, 84: 22}


@dataclass(frozen=True)
class Isomer:
    """One cage of the table."""

    n: int
    number: int
    of: int
    spiral: tuple[int, ...]
    order: int
    ipr: bool
    #: True when the table holds every isomer of this size, False when
    #: only the IPR ones (so "isomer 3" is the third IPR one).
    complete: bool

    @property
    def group(self) -> str:
        """The point group, where it was checked by hand, else ""."""
        return NAMED.get(self.n, {}).get(self.number, "")

    @property
    def name(self) -> str:
        """``C60-Ih``, or ``C32 isomer 4`` where no group is named."""
        if self.group:
            return f"C{self.n}-{self.group}"
        return f"C{self.n} isomer {self.number}"

    @property
    def label(self) -> str:
        """What the form lists: the number, its group or the order of
        its group, and whether it is the IPR count."""
        kind = "IPR isomer" if not self.complete else "isomer"
        what = self.group or f"|G| = {self.order}"
        return f"{kind} {self.number} of {self.of} ({what})"


@cache
def _table() -> dict:
    data = resources.files("xtal.fullerene").joinpath(
        "data/spirals.json")
    return json.loads(data.read_text())


def sizes() -> tuple[int, ...]:
    """Every size the table has, smallest first."""
    return tuple(sorted(int(n) for n in _table()["cages"]))


def isomers(n: int) -> tuple[Isomer, ...]:
    """The table's cages of ``n`` atoms, in spiral order."""
    entry = _table()["cages"].get(str(n))
    if entry is None:
        listed = sizes()
        raise FullereneError(
            f"the table has no C{n}: it holds every isomer from "
            f"C{listed[0]} to C{_table()['all_upto']} and the IPR "
            f"ones from C{_table()['ipr_from']} to C{listed[-1]}; a "
            f"spiral can be typed for any other size")
    rows = entry["isomers"]
    return tuple(Isomer(n=n, number=row["number"], of=len(rows),
                        spiral=tuple(row["spiral"]), order=row["order"],
                        # No cage below C60 can isolate its
                        # pentagons, so the IPR rows are exactly the
                        # IPR cages.
                        ipr=entry["ipr"], complete=not entry["ipr"])
                 for row in rows)


def isomer(n: int, number: int) -> Isomer:
    """Isomer ``number`` of C``n``, counted from 1."""
    found = isomers(n)
    if not 1 <= number <= len(found):
        raise FullereneError(f"C{n} has isomers 1 to {len(found)} in "
                             f"the table, not {number}")
    return found[number - 1]


def default(n: int) -> Isomer:
    """The isomer C``n`` means when nobody says which."""
    return isomer(n, DEFAULTS.get(n, 1))
