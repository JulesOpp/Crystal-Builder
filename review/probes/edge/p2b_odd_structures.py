"""Area 2b: degenerate structures through every writer."""
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))

from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.site import Site  # noqa: E402
from xtal.core.structure import Bond, Structure  # noqa: E402
from xtal.io import FORMATS  # noqa: E402


def make(sites, sg="P1", a=6.0):
    return Structure(lattice=Lattice.cubic(a), sites=sites,
                     space_group=sg)


def cases():
    yield "0 atoms", make([])
    yield "1 atom", make([Site(element="Na", frac=[0.1, 0.2, 0.3])])
    yield "dummy only", make([Site(element="X", frac=[0.5, 0.5, 0.5])])
    yield ("label with a space",
           make([Site(element="Na", frac=[0, 0, 0], label="Na 1"),
                 Site(element="Cl", frac=[.5, .5, .5], label="Cl 1")]))
    yield ("label with a quote",
           make([Site(element="Na", frac=[0, 0, 0], label="Na'1"),
                 Site(element="Cl", frac=[.5, .5, .5], label='Cl"1')]))
    yield ("label that is a comment",
           make([Site(element="Na", frac=[0, 0, 0], label="#Na1")]))
    yield ("label empty",
           make([Site(element="Na", frac=[0, 0, 0], label="")]))
    yield ("coords 0.99999999 / 1.0 / -0.0",
           make([Site(element="Na", frac=[0.99999999, 1.0, -0.0]),
                 Site(element="Cl", frac=[-1e-9, 0.5, 2.5])]))
    b = make([Site(element="Na", frac=[0, 0, 0]),
              Site(element="Cl", frac=[.5, .5, .5])])
    b.bonds.append(Bond(i=0, j=1, image=(9, 0, 0), order=1.0,
                        kind="explicit", op=0))
    yield "bond image beyond 4 cells", b
    c = make([Site(element="Na", frac=[0, 0, 0]),
              Site(element="Cl", frac=[.5, .5, .5])], sg="Fm-3m")
    c.bonds.append(Bond(i=0, j=1, image=(0, 0, 0), order=1.0,
                        kind="explicit", op=500))
    yield "bond op past the group", c


def describe(s):
    return (f"n={len(s.sites)} sg={s.space_group.short_name} "
            f"labels={[x.label for x in s.sites]} "
            f"frac={[[round(float(v), 8) for v in x.frac] for x in s.sites]} "
            f"bonds={[(b.i, b.j, b.image, b.op) for b in s.bonds]}")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        for name, s in cases():
            print("=" * 66)
            print(f"CASE {name}: {describe(s)}")
            for fmt, ext in (("cif", ".cif"), ("xtalproj", ".xtalproj"),
                             ("cssr", ".cssr"), ("gen", ".gen"),
                             ("xyz", ".xyz")):
                out = tmp / f"probe{ext}"
                try:
                    FORMATS.write(s, out, fmt)
                except Exception:
                    ln = traceback.format_exc().strip().splitlines()[-1]
                    print(f"  {fmt:<9} WRITE RAISED {ln}")
                    continue
                try:
                    back = FORMATS.read(out, fmt)
                    print(f"  {fmt:<9} -> {describe(back)}")
                except Exception:
                    ln = traceback.format_exc().strip().splitlines()[-1]
                    print(f"  {fmt:<9} READ  RAISED {ln}")
                    if fmt == "cif":
                        print("   ---- file ----")
                        print("   " + out.read_text(
                            encoding="utf-8").replace("\n", "\n   "))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
