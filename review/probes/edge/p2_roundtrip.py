"""Area 2: write -> read round trips for every sample and fixture."""
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
from xtal.io import FORMATS, for_export, read_cif, write_cif  # noqa: E402

ROOT = HERE.parents[3]
SAMPLES = sorted((ROOT / "resources" / "samples").glob("*.cif"))


def summary(s):
    return dict(
        n_sites=len(s.sites),
        sg=s.space_group.short_name,
        sgnum=s.space_group.number,
        ops=s.space_group.order,
        cell=tuple(round(v, 6) for v in s.lattice.parameters),
        elements=[x.element for x in s.sites],
        bonds=len(s.bonds),
        kinds=sorted({b.kind for b in s.bonds}),
    )


def maxcoord(a, b):
    if len(a.sites) != len(b.sites):
        return None
    fa = np.array([s.frac for s in a.sites])
    fb = np.array([s.frac for s in b.sites])
    d = fa - fb
    d -= np.round(d)
    return float(np.abs(d).max())


def compare(tag, before, after):
    sa, sb = summary(before), summary(after)
    diffs = {k: (sa[k], sb[k]) for k in sa if sa[k] != sb[k]}
    mc = maxcoord(before, after)
    ok = not diffs and (mc is None or mc < 1e-5)
    print(f"  {tag:<28} {'OK ' if ok else 'DIFF'} "
          f"maxfrac={mc if mc is None else round(mc, 8)}")
    for k, (x, y) in diffs.items():
        print(f"      {k}: {x!r} -> {y!r}")


def cell_positions(s):
    from xtal.core import p1
    c = p1.expand(s)
    return c.n_atoms, sorted(c.elements)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        items = [(p.stem, read_cif(p)) for p in SAMPLES]
        items += [(n, f()) for n, f in ALL.items()]
        for name, s in items:
            print("=" * 66)
            print(f"{name}: {summary(s)}")
            for fmt, ext in (("cif", ".cif"), ("xtalproj", ".xtalproj"),
                             ("cssr", ".cssr"), ("gen", ".gen"),
                             ("xyz", ".xyz")):
                out = tmp / f"{name}{ext}"
                try:
                    FORMATS.write(s, out, fmt)
                    back = FORMATS.read(out, fmt)
                    compare(fmt, s, back)
                except Exception:
                    line = traceback.format_exc().strip().splitlines()[-1]
                    print(f"  {fmt:<28} RAISED {line}")
            # for_export through CIF
            try:
                ex = for_export(s)
                out = tmp / f"{name}-export.cif"
                write_cif(ex, out)
                back = read_cif(out)
                compare("cif(for_export)", ex, back)
            except Exception:
                line = traceback.format_exc().strip().splitlines()[-1]
                print(f"  {'cif(for_export)':<28} RAISED {line}")
            # the P1 cell survives a CIF round trip?
            try:
                out = tmp / f"{name}-p1.cif"
                write_cif(s, out)
                n0, e0 = cell_positions(s)
                n1, e1 = cell_positions(read_cif(out))
                mark = "OK " if (n0, e0) == (n1, e1) else "DIFF"
                print(f"  {'p1 atom count':<28} {mark} "
                      f"{n0} -> {n1}")
            except Exception:
                line = traceback.format_exc().strip().splitlines()[-1]
                print(f"  {'p1 atom count':<28} RAISED {line}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
