"""P9b: can the stacking axis simply be set after the build?"""
import logging, warnings
import numpy as np
D = __file__.rsplit("/", 1)[0]
logging.disable(logging.CRITICAL); warnings.filterwarnings("ignore")
from xtal.mof.pormake import BuildingBlock, Topology, Builder    # noqa: E402

hcb = Topology(f"{D}/nets/hcb.cgd")
fw = Builder().build_by_type(
    hcb, {0: BuildingBlock(f"{D}/blocks/NiHITP_linker.xyz")},
    {(0, 0): BuildingBlock(f"{D}/blocks/NiHITP_node.xyz")})
at = fw.atoms
z = at.get_positions()[:, 2]
print(f"built: {len(at)} atoms {at.get_chemical_formula()}")
print(f"  z spread of the layer: {z.max() - z.min():.4f} A")
print(f"  cell as built: {np.round(at.cell.cellpar(), 3)}")

SPACING = 3.23835
cell = np.array(at.cell)
cell[2] = cell[2] / np.linalg.norm(cell[2]) * SPACING
cart = at.get_positions() - [0, 0, z.mean()]
at.set_cell(cell)
at.set_positions(cart)
at.wrap()
print(f"\n  after setting c to {SPACING}: {np.round(at.cell.cellpar(), 3)}")
print(f"  real Ni3(HITP)2:   [21.552 21.552  3.238  90.  90. 120.]")
a = at.cell.cellpar()[0]
print(f"\n  a: built {a:.3f} vs real 21.552  ({100*(a/21.552357-1):+.1f}%)")
z2 = at.get_positions()[:, 2]
print(f"  z spread after wrap: {z2.max() - z2.min():.4f} A"
      f"   (layer stays flat: {z2.max() - z2.min() < 0.01})")
