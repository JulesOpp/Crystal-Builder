"""
Write ``xtal/fullerene/data/spirals.json``: every fullerene isomer
from C20 to C40 and every isolated-pentagon (IPR) one from C60 to the
largest size asked for, each as its canonical spiral with the order
of its point group.

Not shipped, and slow -- the application never enumerates, it reads
the file.  Every face spiral that closes is grown face by face, a
branch cut the moment the boundary cannot take the next face (or, for
IPR, the moment two pentagons touch), and the spirals that are their
own cage's canonical one are kept: each cage once, numbered in the
order of its spiral, which is the Atlas of Fullerenes' numbering.

    python scripts/fullerene_spirals.py            # the shipped table
    python scripts/fullerene_spirals.py --upto 90  # IPR up to C90

``tests/test_fullerene_spiral.py`` re-runs it for the small sizes and
compares.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xtal.fullerene import spiral  # noqa: E402

OUT = ROOT / "xtal" / "fullerene" / "data" / "spirals.json"

#: Every isomer up to here; above it, IPR only.
ALL_UPTO = 40

#: The first size with an IPR isomer.
IPR_FROM = 60


def grown(n: int, ipr: bool):
    """Every pentagon spiral of ``n`` atoms that winds up into a
    cage, as tuples of pentagon places counted from 1."""
    count = spiral.faces(n)
    found = []
    sizes = [0] * count
    room = [0] * count

    def place(face, size, boundary, pentagons):
        # The new face joins the newest and the oldest open face, and
        # on round the boundary while the faces it meets fill up --
        # spiral._wind, one face at a time, with a copy of the
        # boundary to back out of.
        if pentagons + (size == 5) > 12 \
                or 12 - pentagons - (size == 5) > count - face - 1:
            return
        sizes[face], room[face] = size, size
        boundary = list(boundary)
        met = set()
        changed = []

        def join(other):
            if other in met:
                return False
            met.add(other)
            room[face] -= 1
            room[other] -= 1
            changed.append(other)
            return True

        ok = join(boundary[-1]) and join(boundary[0])
        while ok and room[boundary[0]] == 0:
            boundary.pop(0)
            ok = bool(boundary) and join(boundary[0])
        while ok and boundary and room[boundary[-1]] == 0:
            boundary.pop()
            ok = bool(boundary) and join(boundary[-1])
        ok = ok and room[face] >= 0 \
            and all(room[f] >= 0 for f in changed)
        if ok and ipr and size == 5:
            ok = all(sizes[f] != 5 for f in met)
        if ok:
            boundary.append(face)
            if face + 1 == count - 1:
                _close(boundary, pentagons + (size == 5))
            else:
                for nxt in (5, 6):
                    place(face + 1, nxt, boundary,
                          pentagons + (size == 5))
        for other in changed:
            room[other] += 1

    def _close(boundary, pentagons):
        last = 12 - pentagons
        if last not in (0, 1):
            return
        size = 5 if last else 6
        if len(boundary) != size \
                or any(room[f] != 1 for f in boundary):
            return
        if ipr and size == 5 and any(sizes[f] == 5 for f in boundary):
            return
        found.append(tuple(i + 1 for i in range(count - 1)
                           if sizes[i] == 5)
                     + ((count,) if size == 5 else ()))

    for first in (5, 6):
        for second in (5, 6):
            if ipr and first == second == 5:
                continue
            sizes[0], room[0] = first, first - 1
            sizes[1], room[1] = second, second - 1
            pentagons = (first == 5) + (second == 5)
            for third in (5, 6):
                place(2, third, [0, 1], pentagons)
    return found


def is_canonical(rotation, key) -> int:
    """How many starts give ``key`` if no start gives an earlier
    spiral, else 0.  A start is dropped at the first pentagon that
    comes later than ``key``'s, which is most of them."""
    count = len(rotation)
    hits = 0
    for first, around in enumerate(rotation):
        for second in around:
            for sense in (1, -1):
                verdict = _compare(rotation, first, second, sense, key,
                                   count)
                if verdict < 0:
                    return 0
                hits += verdict == 0
    return hits


def _compare(rotation, first, second, sense, key, count):
    """-1, 0 or 1 as the spiral from this start comes before, equals
    or comes after ``key``; 1 for one that does not close.  A start
    that is later is dropped at once; one that is earlier still has
    to close before it counts, since a walk that runs into itself is
    no spiral at all."""
    order, seen = [], set()
    state = {"pentagons": 0, "verdict": None}

    def take(face):
        # Places count from 1, so a face's place is the length of the
        # order once it is in.
        order.append(face)
        seen.add(face)
        if state["verdict"] is not None:
            return None
        k = state["pentagons"]
        if len(rotation[face]) == 5:
            state["pentagons"] += 1
            if len(order) < key[k]:
                state["verdict"] = -1
            elif len(order) > key[k]:
                return 1
        elif k < 12 and len(order) == key[k]:
            return 1
        return None

    for face in (first, second):
        if take(face) is not None:
            return 1
    oldest = 0
    while len(order) < count:
        while all(f in seen for f in rotation[order[oldest]]):
            oldest += 1
        hub, newest = order[oldest], order[-1]
        if newest not in rotation[hub]:
            return 1
        face = spiral._after(rotation, hub, newest, sense)
        if face in seen:
            return 1
        if take(face) is not None:
            return 1
    return state["verdict"] or 0


def isomers(n: int, ipr: bool) -> list[dict]:
    """The cages of ``n`` atoms, each once, in spiral order."""
    rows = []
    for key in sorted(set(grown(n, ipr))):
        rotation = spiral.wind(n, key)
        order = is_canonical(rotation, key)
        if order:
            rows.append({"spiral": list(key), "order": order})
    for number, row in enumerate(rows, 1):
        row["number"] = number
    return rows


def table(upto: int, say=print) -> dict:
    out = {"source": "scripts/fullerene_spirals.py", "all_upto": ALL_UPTO,
           "ipr_from": IPR_FROM, "ipr_upto": upto, "cages": {}}
    sizes = [(n, False) for n in range(20, ALL_UPTO + 1, 2) if n != 22]
    sizes += [(n, True) for n in range(IPR_FROM, upto + 1, 2)]
    for n, ipr in sizes:
        start = time.perf_counter()
        rows = isomers(n, ipr)
        if rows:
            out["cages"][str(n)] = {"ipr": ipr, "isomers": rows}
        say(f"C{n} {'IPR' if ipr else 'all'}: {len(rows)} isomers, "
            f"{time.perf_counter() - start:.1f} s")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--upto", type=int, default=100)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    data = table(args.upto)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
