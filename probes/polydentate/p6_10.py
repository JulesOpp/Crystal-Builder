"""P6: how often does pass 1 silently mirror a node block?
P10: is rewriting a placed block's positions safe before write_cif?"""
import logging, tempfile, warnings, os
import numpy as np
D = __file__.rsplit("/", 1)[0]
logging.disable(logging.CRITICAL); warnings.filterwarnings("ignore")
from xtal.mof.pormake import BuildingBlock, Topology, Builder    # noqa: E402
from xtal.mof.catalog import database_root                       # noqa: E402

ROOT = database_root()


def chirality(bb):
    """Signed volume of three connection-point directions."""
    q = bb.local_structure().atoms.positions
    return float(np.linalg.det(q[:3])) if len(q) >= 3 else 0.0


print("P6: does the builder mirror a node block?")
node = BuildingBlock(f"{D}/blocks/MFU4l_node.xyz")
edge = BuildingBlock(f"{D}/blocks/MFU4l_linker.xyz")
mirrored = 0
tried = []
for net in ("pcu", "bcu", "fcu", "reo", "soc", "the", "nbo", "acs"):
    p = ROOT / "topologies" / f"{net}.cgd"
    if not p.exists():
        continue
    try:
        topo = Topology(str(p))
        if topo.unique_cn[0] != node.n_connection_points:
            continue
        fw = Builder().build_by_type(topo, {0: node}, {(0, 0): edge})
    except Exception as exc:
        tried.append((net, f"skipped: {type(exc).__name__}"))
        continue
    before = chirality(node)
    flips = 0
    for i in topo.node_indices:
        placed = fw.info["located_bbs"][int(i)]
        if np.sign(chirality(placed)) != np.sign(before):
            flips += 1
    mirrored += flips
    tried.append((net, f"{topo.n_nodes} nodes, {flips} mirrored"))
for n, m in tried:
    print(f"   {n:5s} {m}")
print(f"   total mirrored placements: {mirrored}")

print("\nP10: rewriting positions, then write_cif")
topo = Topology(str(ROOT / "topologies" / "pcu.cgd"))
fw = Builder().build_by_type(topo, {0: node}, {(0, 0): edge})
before_order = list(fw.atoms.get_chemical_symbols())
pos = fw.atoms.get_positions()
pos[:16] += np.array([0.0, 0.0, 0.05])        # nudge one block
fw.atoms.set_positions(pos)
fw.atoms.wrap()
with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "x.cif")
    fw.write_cif(out)
    ok = os.path.exists(out) and os.path.getsize(out) > 0
    print(f"   file written: {ok}"
          f"   size {os.path.getsize(out) if ok else 0} bytes")
print(f"   atom order unchanged: "
      f"{before_order == list(fw.atoms.get_chemical_symbols())}")
longest = max(np.linalg.norm(fw.atoms.get_distance(int(i), int(j), mic=True))
              for i, j in fw.bonds)
print(f"   longest bond {longest:.3f} A  (write_cif KeyErrors above 6.0)")
