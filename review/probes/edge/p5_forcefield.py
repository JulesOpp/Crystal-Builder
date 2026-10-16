"""Area 5: UFF engine and optimiser edge cases."""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402

from fixtures import ALL  # noqa: E402
from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.site import Site  # noqa: E402
from xtal.core.structure import Structure  # noqa: E402
from xtal.ff import optimize  # noqa: E402
from xtal.ff.registry import ENGINES  # noqa: E402


def last():
    return traceback.format_exc().strip().splitlines()[-1]


def build(tag, s, **kw):
    try:
        calc = ENGINES.build("uff", s, **kw)
    except Exception:
        print(f"  {tag:<32} BUILD {last()}")
        return None
    try:
        r = calc.compute()
        print(f"  {tag:<32} E={r.energy!r} maxF={r.max_force!r} "
              f"n_atoms={calc.n_atoms}")
    except Exception:
        print(f"  {tag:<32} COMPUTE {last()}")
    return calc


def cell(a=10.0):
    return Lattice.cubic(a)


print("### elements UFF has no parameters for")
for sym in ("Og", "X", "Fr", "Cf", "D"):
    s = Structure(lattice=cell(), space_group="P1",
                  sites=[Site(element=sym, frac=[0.2, 0.2, 0.2]),
                         Site(element="C", frac=[0.35, 0.2, 0.2])])
    build(f"{sym} + C", s)

print()
print("### degenerate structures")
build("0 atoms", Structure(lattice=cell(), space_group="P1", sites=[]))
build("1 atom (C)", Structure(lattice=cell(), space_group="P1",
                              sites=[Site(element="C",
                                          frac=[.5, .5, .5])]))
build("only a dummy", Structure(lattice=cell(), space_group="P1",
                                sites=[Site(element="X",
                                            frac=[.5, .5, .5])]))
nb = Structure(lattice=cell(30.0), space_group="P1",
               sites=[Site(element="Ar", frac=[0.1, 0.1, 0.1]),
                      Site(element="Ar", frac=[0.6, 0.6, 0.6])])
build("no bonds at all (2 Ar)", nb)

print()
print("### charged sites with electrostatics on")
ch = Structure(lattice=cell(8.0), space_group="P1",
               sites=[Site(element="Na", frac=[0, 0, 0], charge=1.0),
                      Site(element="Cl", frac=[.5, .5, .5],
                           charge=-1.0)])
build("Na+/Cl- charges off", ch)
build("Na+/Cl- electrostatics=True", ch, electrostatics=True)
ch2 = ch.copy()
ch2.sites[0].charge = 1.0
ch2.sites[1].charge = 1.0
build("both +1 (non-neutral cell)", ch2, electrostatics=True)

print()
print("### non-finite coordinates")
for bad in (float("nan"), float("inf")):
    s = Structure(lattice=cell(), space_group="P1",
                  sites=[Site(element="C", frac=[bad, 0.2, 0.2]),
                         Site(element="C", frac=[0.35, 0.2, 0.2])])
    build(f"frac x = {bad}", s)

print()
print("### optimiser on a NaN-energy structure")
s = Structure(lattice=cell(), space_group="P1",
              sites=[Site(element="C", frac=[float("nan"), .2, .2]),
                     Site(element="C", frac=[0.35, 0.2, 0.2])])
try:
    calc = ENGINES.build("uff", s)
    res = optimize.run(calc, s, max_steps=20)
    print(f"  run on NaN -> converged={res.converged} "
          f"steps={res.steps} E={res.energy!r} {res.summary()}")
except Exception:
    print(f"  run on NaN -> {last()}")

print()
print("### max_steps=0 and negative")
q = ALL["quartz"]()
for n in (0, -1, 1):
    try:
        calc = ENGINES.build("uff", q)
        res = optimize.run(calc, q, max_steps=n)
        print(f"  max_steps={n:<3} converged={res.converged} "
              f"steps={res.steps} dE={res.energy_change:.6g} "
              f"msg={res.message!r}")
    except Exception:
        print(f"  max_steps={n:<3} {last()}")

print()
print("### optimiser on a structure with no bonds / one atom")
for tag, st in (("1 C", Structure(lattice=cell(), space_group="P1",
                                  sites=[Site(element="C",
                                              frac=[.5, .5, .5])])),
                ("2 Ar", nb)):
    try:
        calc = ENGINES.build("uff", st)
        res = optimize.run(calc, st, max_steps=5)
        print(f"  {tag:<6} converged={res.converged} steps={res.steps} "
              f"E={res.energy!r} msg={res.message!r}")
    except Exception:
        print(f"  {tag:<6} {last()}")

print()
print("### coincident atoms under UFF")
co = Structure(lattice=cell(), space_group="P1",
               sites=[Site(element="C", frac=[0.2, 0.2, 0.2]),
                      Site(element="C", frac=[0.2, 0.2, 0.2]),
                      Site(element="O", frac=[0.32, 0.2, 0.2])])
build("two C exactly coincident", co)

print()
print("### the samples with zero-distance pairs")
from xtal.io import read_cif  # noqa: E402

for nm in ("Ni2Cl2BTDD", "CFA1", "MFU4l"):
    s = read_cif(HERE.parents[3] / "resources" / "samples" / f"{nm}.cif")
    build(nm, s)

print()
print("### numbers")
np.set_printoptions(precision=4)
