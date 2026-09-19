"""Area 3: lattice extremes, symprec extremes, P1 <-> asymmetrize."""
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402

from fixtures import ALL  # noqa: E402
from xtal.core import p1  # noqa: E402
from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.site import Site  # noqa: E402
from xtal.core.structure import Structure  # noqa: E402
from xtal.core.symmetry import asymmetrize, detect, reduce_to_p1  # noqa: E402
from xtal.io import read_cif, write_cif  # noqa: E402

ROOT = HERE.parents[3]
SAMPLES = sorted((ROOT / "resources" / "samples").glob("*.cif"))


def last(exc=None):
    return traceback.format_exc().strip().splitlines()[-1]


def lattices():
    yield "alpha=90.0000001", (5.0, 5.0, 5.0, 90.0000001, 90.0, 90.0)
    yield "gamma=179", (5.0, 5.0, 5.0, 90.0, 90.0, 179.0)
    yield "gamma=179.9999", (5.0, 5.0, 5.0, 90.0, 90.0, 179.9999)
    yield "gamma=180", (5.0, 5.0, 5.0, 90.0, 90.0, 180.0)
    yield "a=200", (200.0, 200.0, 200.0, 90.0, 90.0, 90.0)
    yield "a=1", (1.0, 1.0, 1.0, 90.0, 90.0, 90.0)
    yield "a=0", (0.0, 5.0, 5.0, 90.0, 90.0, 90.0)
    yield "a=-5", (-5.0, 5.0, 5.0, 90.0, 90.0, 90.0)
    yield "impossible angles 20/20/150", (5.0, 5.0, 5.0, 20.0, 20.0, 150.0)
    yield "alpha=0", (5.0, 5.0, 5.0, 0.0, 90.0, 90.0)
    yield "nan a", (float("nan"), 5.0, 5.0, 90.0, 90.0, 90.0)


def part_lattices():
    print("### Lattice.from_parameters")
    for name, pars in lattices():
        try:
            lat = Lattice.from_parameters(*pars)
            back = tuple(round(float(v), 6) for v in lat.parameters)
            print(f"  {name:<28} vol={lat.volume!r:<22} "
                  f"params={back} rh={lat.is_right_handed}")
        except Exception:
            print(f"  {name:<28} RAISED {last()}")


def part_tiny_huge():
    print()
    print("### a structure in an extreme cell: expand + detect")
    for name, a in (("a=1 A", 1.0), ("a=200 A", 200.0)):
        s = Structure(lattice=Lattice.cubic(a),
                      sites=[Site(element="Na", frac=[0, 0, 0]),
                             Site(element="Cl", frac=[.5, .5, .5])],
                      space_group="Fm-3m")
        try:
            cell = p1.expand(s)
            info = detect(s)
            print(f"  {name:<10} p1 atoms={cell.n_atoms} "
                  f"detect={info.short_name} (#{info.number})")
        except Exception:
            print(f"  {name:<10} RAISED {last()}")


def part_symprec():
    print()
    print("### detect() at symprec extremes")
    items = [(p.stem, read_cif(p)) for p in SAMPLES] + \
            [(n, f()) for n, f in ALL.items()]
    for name, s in items:
        row = [f"  {name:<12}"]
        for sp in (1e-10, 1e-5, 1e-2, 1.0):
            try:
                info = detect(s, symprec=sp)
                row.append(f"{sp:g}:{info.short_name}({info.number})")
            except Exception:
                row.append(f"{sp:g}:RAISE({last()[:38]})")
        print(" ".join(row))


def part_roundtrip():
    print()
    print("### reduce_to_p1 -> asymmetrize round trip")
    items = [(p.stem, read_cif(p)) for p in SAMPLES] + \
            [(n, f()) for n, f in ALL.items()]
    for name, s in items:
        try:
            n0 = p1.expand(s).n_atoms
            flat = reduce_to_p1(s)
            back, report = asymmetrize(flat)
            n1 = p1.expand(back).n_atoms
            same_group = back.space_group.number == s.space_group.number
            mark = "OK  " if (n0 == n1 and same_group) else "DIFF"
            print(f"  {name:<12} {mark} "
                  f"{s.space_group.short_name}({len(s.sites)} sites, "
                  f"{n0} atoms) -> P1({len(flat.sites)}) -> "
                  f"{back.space_group.short_name}({len(back.sites)} "
                  f"sites, {n1} atoms)")
        except Exception:
            print(f"  {name:<12} RAISED {last()}")


def part_four_dp():
    print()
    print("### sites on 0.5, 1/3, 2/3 written at 4 dp")
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        s = Structure(
            lattice=Lattice.from_parameters(5, 5, 8, 90, 90, 120),
            sites=[Site(element="Si", frac=[1 / 3, 2 / 3, 0.5]),
                   Site(element="O", frac=[0.5, 0.5, 0.5])],
            space_group="P6_3/mmc")
        n0 = p1.expand(s).n_atoms
        p = tmp / "a.cif"
        write_cif(s, p)
        # now the same coordinates truncated to four decimals
        text = p.read_text(encoding="utf-8")
        rounded = s.copy()
        for site in rounded.sites:
            site.frac = [float(f"{v:.4f}") for v in site.frac]
        n1 = p1.expand(rounded).n_atoms
        print(f"  exact 1/3,2/3,1/2 -> {n0} atoms; "
              f"4 dp (0.3333,0.6667,0.5) -> {n1} atoms")
        got = [ln for ln in text.splitlines()
               if ln.startswith(("Si", "O"))]
        print(f"  written rows: {got}")
        # and a 30 A cell, where 4 dp is 0.003 A
        big = Structure(
            lattice=Lattice.from_parameters(30, 30, 30, 90, 90, 120),
            sites=[Site(element="Zn", frac=[0.3333, 0.6667, 0.5])],
            space_group="P6_3/mmc")
        exact = big.copy()
        exact.sites[0].frac = [1 / 3, 2 / 3, 0.5]
        print(f"  30 A cell, Zn at 4 dp -> "
              f"{p1.expand(big).n_atoms} atoms; exact -> "
              f"{p1.expand(exact).n_atoms} atoms "
              f"(SPECIAL_POSITION_TOL={p1.SPECIAL_POSITION_TOL})")
    except Exception:
        print(f"  RAISED {last()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def part_coincident():
    print()
    print("### two atoms exactly on top of each other")
    s = Structure(lattice=Lattice.cubic(6.0),
                  sites=[Site(element="Na", frac=[0.1, 0.1, 0.1]),
                         Site(element="Na", frac=[0.1, 0.1, 0.1])],
                  space_group="P1")
    try:
        cell = p1.expand(s)
        print(f"  p1.expand -> {cell.n_atoms} atoms")
        info = detect(s)
        print(f"  detect -> {info.short_name} (#{info.number})")
    except Exception:
        print(f"  RAISED {last()}")
    s2 = s.copy()
    s2.sites[1].element = "Cl"
    try:
        print(f"  Na+Cl coincident: p1 -> {p1.expand(s2).n_atoms}, "
              f"detect -> {detect(s2).short_name}")
    except Exception:
        print(f"  Na+Cl coincident RAISED {last()}")


if __name__ == "__main__":
    np.seterr(all="warn")
    part_lattices()
    part_tiny_huge()
    part_symprec()
    part_roundtrip()
    part_four_dp()
    part_coincident()
