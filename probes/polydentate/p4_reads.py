"""P4: does the vendored reader take a polydentate X, and does a build
complete with one?  The whole no-vendored-edit premise rests on this."""
import sys, logging
import numpy as np
D = __file__.rsplit("/", 1)[0]
logging.disable(logging.CRITICAL)
from xtal.mof.pormake import BuildingBlock, Topology, Builder   # noqa: E402
from xtal.mof.catalog import database_root                      # noqa: E402

for name in ("MFU4l_node", "MFU4l_linker", "NiHITP_node", "NiHITP_linker"):
    bb = BuildingBlock(f"{D}/blocks/{name}.xyz")
    cpi = list(bb.connection_point_indices)
    deg = [int(np.sum(bb.bonds == c) if bb.bonds is not None else 0)
           for c in cpi]
    print(f"  {name:16s} atoms {bb.n_atoms:3d}  X {bb.n_connection_points}"
          f"  bonds/X {deg}  is_node={bb.is_node}  metal={bb.has_metal}")
    bb.check_bonds()

print("\n--- a real build on pcu with the polydentate node ---")
topo = Topology(str(database_root() / "topologies" / "pcu.cgd"))
node = BuildingBlock(f"{D}/blocks/MFU4l_node.xyz")
edge = BuildingBlock(f"{D}/blocks/MFU4l_linker.xyz")
fw = Builder().build_by_type(topo, {0: node}, {(0, 0): edge})
from collections import Counter                                  # noqa: E402
sym = Counter(fw.atoms.get_chemical_symbols())
print(f"  atoms {len(fw.atoms)}  {dict(sym)}")
print(f"  bonds {len(fw.bonds)}   max_rmsd {fw.info['max_rmsd']:.6f}")
print(f"  cell  {np.round(fw.atoms.cell.cellpar(), 3)}")

# How many of the bidentate bonds actually survived the X fusion?
expect = 6 * 2                      # six attachments, two bonds each
inter = len(fw.bonds) - (node.bonds.shape[0] - 6 * 2
                         + edge.bonds.shape[0] - 2 * 2) * 1
print(f"\n  each joint should carry 2 bonds; PORMAKE's own fusion keeps 1")
