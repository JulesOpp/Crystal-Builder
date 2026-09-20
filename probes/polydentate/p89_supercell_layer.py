"""P8: does a supercell survive our own net drawing, and what does the
scaler cost?   P9: does a 2-periodic net keep its stacking axis?"""
import logging, time, warnings
import numpy as np
D = __file__.rsplit("/", 1)[0]
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")
from xtal.mof.pormake import BuildingBlock, Topology, Builder     # noqa: E402
from xtal.mof.catalog import database_root                        # noqa: E402
import importlib                                               # noqa: E402
B = importlib.import_module("xtal.mof.build")                    # noqa: E402

node = BuildingBlock(f"{D}/blocks/MFU4l_node.xyz")
edge = BuildingBlock(f"{D}/blocks/MFU4l_linker.xyz")
pcu = str(database_root() / "topologies" / "pcu.cgd")

print("P8: pcu, one cell vs 2x2x2")
for rep in ((1, 1, 1), (2, 2, 2)):
    topo = Topology(pcu)
    if rep != (1, 1, 1):
        topo = topo * rep
    t = time.perf_counter()
    fw = Builder().build_by_type(topo, {0: node}, {(0, 0): edge})
    dt = time.perf_counter() - t
    scaled = fw.info["topology"]
    print(f"  {rep}: slots {topo.n_slots:3d}  nodes {topo.n_nodes:2d}"
          f"  atoms {len(fw.atoms):4d}  build {dt:6.2f}s"
          f"  cell {np.round(scaled.atoms.cell.cellpar()[:3], 2)}")
    # our own post-processing, the part the review never exercised
    edges = B._edges_of(scaled)
    blocks = fw.info["located_bbs"]
    reps = B._representatives(scaled, blocks)
    print(f"       _edges_of -> {len(edges):3d} edges,"
          f" _representatives -> {len(reps)} node slots  OK")

print("\nP9: hcb in a 3D cell -- does the stacking axis survive scaling?")
hcb = Topology(f"{D}/nets/hcb.cgd")
print(f"  slots {hcb.n_slots}  nodes {hcb.n_nodes}  edges {hcb.n_edges}"
      f"  node types {hcb.n_node_types}  cn {hcb.unique_cn}")
ni_node = BuildingBlock(f"{D}/blocks/NiHITP_node.xyz")
ni_link = BuildingBlock(f"{D}/blocks/NiHITP_linker.xyz")
fw2 = Builder().build_by_type(hcb, {0: ni_link}, {(0, 0): ni_node})
par = fw2.info["topology"].atoms.cell.cellpar()
print(f"  built {len(fw2.atoms)} atoms "
      f"{fw2.atoms.get_chemical_formula()}")
print(f"  cell before 1.000 1.000 10.000 90 90 120")
print(f"  cell after  {np.round(par, 3)}")
print(f"  c unchanged? {abs(par[2] - 10.0) < 1e-6}")
