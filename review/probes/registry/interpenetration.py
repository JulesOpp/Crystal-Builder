# Written 2026-09-19 against Crystal-Builder source commit 3cd15e2 (v0.2.1).
#
# Can interpenetration be detected today with what is already in the
# tree?  The claim under test: `bonding.graph(structure).fragments()`
# gives the components, and `xtal.analysis.topology.Net` already
# carries `periodicity()` (rank of the cycle lattice) and
# `multiplicity()` (the saturation index, whose docstring calls it
# "the interpenetration number of a net described in a doubled cell").
# Nothing below is new mathematics; it is ten lines of glue over
# both.  Run with .venv/bin/python.
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

from xtal.analysis.topology import Edge, Net
from xtal.core import bonding, p1
from xtal.io import FORMATS

ROOT = Path(__file__).resolve().parents[3]


def frameworks(structure):
    """(degree, [one Net per 3-periodic component], other counts).

    The whole candidate algorithm.
    """
    graph = bonding.graph(structure)
    nets, molecules, low = [], 0, 0
    for frag in graph.fragments():
        index = {a: k for k, a in enumerate(frag.atoms)}
        edges = tuple(
            Edge(index[b.i], index[b.j], tuple(int(v) for v in b.image))
            for b in graph.bonds if b.i in index)
        if not edges:
            molecules += 1
            continue
        net = Net(len(frag.atoms), edges)
        d = net.periodicity()
        if d == 3:
            nets.append(net)
        elif d == 0:
            molecules += 1
        else:
            low += 1
    # A component may itself be several copies in disguise -- one
    # quotient-graph component whose cycle lattice is a sublattice of
    # index m is m separate frameworks in the crystal.
    degree = sum(n.multiplicity() for n in nets)
    return degree, nets, molecules, low


def report(path):
    s = FORMATS.read(path)
    t0 = time.perf_counter()
    cell = p1.expand(s)
    t1 = time.perf_counter()
    bonding.perceive(s)                 # warm: how much is perception
    t2 = time.perf_counter()
    degree, nets, molecules, low = frameworks(s)
    t3 = time.perf_counter()
    print(f"{path.name:18s} {cell.n_atoms:5d} atoms  "
          f"{degree}-fold  nets={len(nets)} "
          f"mult={[n.multiplicity() for n in nets]} "
          f"molecules={molecules} low-d={low}   "
          f"expand {1000*(t1-t0):6.1f} ms  perceive {1000*(t2-t1):7.1f} ms"
          f"  detect {1000*(t3-t2):6.1f} ms")


if __name__ == "__main__":
    args = [Path(a) for a in sys.argv[1:]]
    if not args:
        args = sorted((ROOT / "resources" / "samples").glob("*.cif"))
    for p in args:
        try:
            report(p)
        except Exception as exc:                    # noqa: BLE001
            print(f"{p.name:18s} FAILED: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- the
# positive controls.  None of the nine samples is interpenetrated, so
# the detector above is only half checked by them: they prove it does
# not cry wolf.  These two prove it fires.
def controls():
    print()
    # (1) The saturation-index half, which is the case a component
    # count alone gets WRONG.  One vertex, joined to its own image two
    # cells along in x and one cell along in y and z: the quotient
    # graph is connected, and the crystal holds two independent pcu
    # nets offset by half the a axis.  This is `multiplicity`'s own
    # docstring example, at rank 3.
    doubled = Net(1, (Edge(0, 0, (2, 0, 0)),
                      Edge(0, 0, (0, 1, 0)),
                      Edge(0, 0, (0, 0, 1))))
    print(f"pcu in a doubled a axis:      components=1  "
          f"periodicity={doubled.periodicity()}  "
          f"multiplicity={doubled.multiplicity()}   <- 2-fold, from "
          f"ONE component")

    plain = Net(1, (Edge(0, 0, (1, 0, 0)),
                    Edge(0, 0, (0, 1, 0)),
                    Edge(0, 0, (0, 0, 1))))
    print(f"pcu in its own cell:          components=1  "
          f"periodicity={plain.periodicity()}  "
          f"multiplicity={plain.multiplicity()}")

    # (2) The component half: two copies of MOF-5's framework in one
    # cell, the second a half-cell along the body diagonal, bonded
    # only to itself.  Built from the bond list rather than by
    # perception on purpose -- perception would join the copies, which
    # is the difference between interpenetration and a clash.
    s = FORMATS.read(ROOT / "resources" / "samples" / "MOF-5.cif")
    graph = bonding.graph(s)
    n = p1.expand(s).n_atoms
    edges = [Edge(b.i, b.j, tuple(int(v) for v in b.image))
             for b in graph.bonds]
    edges += [Edge(b.i + n, b.j + n, tuple(int(v) for v in b.image))
              for b in graph.bonds]
    both = Net(2 * n, tuple(edges))
    parts = both.components()
    print(f"MOF-5 framework, twice:       "
          f"components={len(parts)}  "
          f"periodicity={[p.periodicity() for p in parts]}  "
          f"multiplicity={[p.multiplicity() for p in parts]}  "
          f"-> degree {sum(p.multiplicity() for p in parts if p.periodicity() == 3)}")
    # And the two are the same net, which is what "2-fold
    # interpenetrated dia" as opposed to "two different frameworks"
    # means -- the app can already say so:
    t0 = time.perf_counter()
    try:
        keys = [p.key(budget=200000) for p in parts]
        print(f"    same net?  {keys[0] == keys[1]}  "
              f"({1000 * (time.perf_counter() - t0):.0f} ms for both)")
    except Exception as exc:                        # noqa: BLE001
        # This is a RESULT, not a probe bug: Net.key walks the net and
        # refuses a graph this size.  "Are the two components the same
        # net?" therefore cannot be asked of the ATOM graph -- it has
        # to be asked of the simplified node-and-linker net, which is
        # the one `net_of` reads and the user draws.
        print(f"    same net?  Net.key refused: {exc}")


if __name__ == "__main__":
    controls()
