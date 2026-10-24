"""Area 4: bond perception edge cases."""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402

from fixtures import ALL  # noqa: E402
from xtal.core import bonding, p1  # noqa: E402
from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.site import Site  # noqa: E402
from xtal.core.structure import Structure  # noqa: E402
from xtal.io import read_cif  # noqa: E402

ROOT = HERE.parents[3]


def last():
    return traceback.format_exc().strip().splitlines()[-1]


def show(tag, s):
    try:
        cell = p1.expand(s)
        bonds = bonding.perceive(s)
        g = bonding.graph(s)
        coord = g.coordination()
        lengths = [b.distance for b in bonds]
        frags = g.fragments()
        print(f"  {tag:<34} atoms={cell.n_atoms} bonds={len(bonds)} "
              f"maxcoord={coord.max() if len(coord) else 0} "
              f"dmin={min(lengths) if lengths else float('nan'):.4f} "
              f"frags={len(frags)} kinds={sorted({f.kind for f in frags})}")
    except Exception:
        print(f"  {tag:<34} RAISED {last()}")


print("### two atoms coincident")
s = Structure(lattice=Lattice.cubic(8.0),
              sites=[Site(element="C", frac=[0.2, 0.2, 0.2]),
                     Site(element="C", frac=[0.2, 0.2, 0.2])],
              space_group="P1")
show("C + C at the same point", s)
s2 = s.copy()
s2.sites[1].element = "O"
show("C + O at the same point", s2)

print()
print("### a single atom in a big cell")
for a in (5.0, 40.0, 200.0):
    one = Structure(lattice=Lattice.cubic(a),
                    sites=[Site(element="C", frac=[0.5, 0.5, 0.5])],
                    space_group="P1")
    show(f"one C, a={a}", one)
    na = Structure(lattice=Lattice.cubic(a),
                   sites=[Site(element="Na", frac=[0.5, 0.5, 0.5])],
                   space_group="P1")
    show(f"one Na, a={a}", na)

print()
print("### the four fixtures")
for name, f in ALL.items():
    show(name, f())

print()
print("### shipped samples")
for p in sorted((ROOT / "resources" / "samples").glob("*.cif")):
    show(p.stem, read_cif(p))

print()
print("### halite: what does an ionic crystal bond to?")
h = ALL["halite"]()
cell = p1.expand(h)
bonds = bonding.perceive(h)
pairs = {}
for b in bonds:
    key = tuple(sorted((cell.elements[b.i], cell.elements[b.j])))
    pairs.setdefault(key, []).append(b.distance)
for key, ls in sorted(pairs.items()):
    print(f"  {key}: {len(ls)} bonds, {min(ls):.3f}-{max(ls):.3f} A")
print(f"  coordination: {bonding.graph(h).coordination()}")

print()
print("### dry ice: molecules across the cell boundary")
d = ALL["dry_ice"]()
g = bonding.graph(d)
frs = g.fragments()
print(f"  {len(frs)} fragments: "
      f"{[(len(f), f.kind) for f in frs]}")

print()
print("### bond orders on a metal cluster")
cluster = Structure(
    lattice=Lattice.cubic(20.0),
    sites=[Site(element="Fe", frac=[0.5, 0.5, 0.5]),
           Site(element="Fe", frac=[0.5 + 2.48 / 20, 0.5, 0.5]),
           Site(element="Fe", frac=[0.5, 0.5 + 2.48 / 20, 0.5]),
           Site(element="Fe", frac=[0.5, 0.5, 0.5 + 2.48 / 20])],
    space_group="P1")
show("Fe4 cluster", cluster)
try:
    o = bonding.orders(cluster)
    print(f"  orders = {np.round(o, 3)}")
except Exception:
    print(f"  orders RAISED {last()}")
try:
    zn = read_cif(ROOT / "resources" / "samples" / "zn_oac.cif")
    o = bonding.orders(zn)
    print(f"  zn_oac orders: {len(o)} bonds, "
          f"unique={sorted(set(np.round(o, 3).tolist()))}")
except Exception:
    print(f"  zn_oac orders RAISED {last()}")
