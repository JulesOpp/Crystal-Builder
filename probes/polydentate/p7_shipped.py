"""P7: is any shipped block polydentate today, and how wide are ours?

If none of the 867 is, the "nothing regresses" guard is provably never
armed for them.  The spans fix MAX_ATTACHMENT_SPAN.
"""
import logging, warnings
import numpy as np
D = __file__.rsplit("/", 1)[0]
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")
from xtal.mof.pormake import BuildingBlock                       # noqa: E402
from xtal.mof.catalog import database_root                       # noqa: E402

files = sorted((database_root() / "bbs").glob("*.xyz"))
poly, nobonds, bad = 0, 0, []
for f in files:
    bb = BuildingBlock(str(f))
    if bb.bonds is None or len(bb.bonds) == 0:
        nobonds += 1
        continue
    for c in bb.connection_point_indices:
        deg = int(np.sum(bb.bonds == c))
        if deg > 1:
            poly += 1
            bad.append((f.stem, int(c), deg))
print(f"shipped blocks: {len(files)}")
print(f"  with no bond block at all : {nobonds}")
print(f"  connection points with >1 bond: {poly}  {bad[:5]}")

print("\nours:")
for name in ("MFU4l_node", "MFU4l_linker", "NiHITP_node", "NiHITP_linker"):
    bb = BuildingBlock(f"{D}/blocks/{name}.xyz")
    spans = []
    for c in bb.connection_point_indices:
        mem = [int(j) for i, j in bb.bonds for j in (i, j)] and None
        rows = [r for r in bb.bonds if c in r]
        members = [int(r[0] if r[1] == c else r[1]) for r in rows]
        p = bb.atoms.positions[members]
        spans.append(float(np.linalg.norm(p[0] - p[1])))
        off = float(np.linalg.norm(bb.atoms.positions[c] - p.mean(axis=0)))
    print(f"  {name:16s} member span {min(spans):.3f}-{max(spans):.3f} A"
          f"   X sits {off:.3f} A from the members' centroid")
