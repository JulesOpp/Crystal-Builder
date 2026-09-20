"""Phase 6: the angle about a two-connected block's own axis.

Named for the phase and not for a Phase 1 probe, because the numbers
it prints are the ones ``docs/ROADMAP.md`` § 2 carries under *What
Phase 6 changed* and under *A repeated net cannot be told to flip its
neighbours* in ``docs/TODO.md`` -- and both are measured on the four
blocks in ``blocks/``, which no test can reach until Phase 7 ships
them inside the package.

Three questions:

A  what does settling do to the real blocks, and does it leave
   Ni3(HITP)2 -- whose crystal angle is zero -- alone?
B  what is left on ``pcu`` after it, and why;
C  can a repeated net alternate its nodes at all, and what stops
   MOF-5 doing it?
"""
import logging
import pathlib
import tempfile
import warnings

import numpy as np

D = pathlib.Path(__file__).parent
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")
from xtal.mof import Catalog, orient  # noqa: E402
from xtal.mof.attach import pair_cost  # noqa: E402
from xtal.mof.build import (  # noqa: E402
    BuildRequest,
    _build,
    _resolve,
    build,
)

CAT = Catalog.default(topology_dir=str(D / "nets"),
                      also_blocks=[D / "blocks"])
TMP = pathlib.Path(tempfile.mkdtemp())


def placed(*spelled):
    """A framework as the builder leaves it, before it settles."""
    request = BuildRequest.parse(*spelled)
    topology, nodes, edges = _resolve(request, CAT)
    return _build(topology, nodes, edges, None, request.repeat,
                  request.orientation)


def disagreement(framework):
    """The sum of `pair_cost` over every joint of a framework."""
    blocks = framework.info["located_bbs"]
    total = 0.0
    for here, there in orient.fused_points(
            framework.info["topology"], blocks,
            framework.info["permutations"]):
        mine = orient._attachment_at(blocks, *here)
        theirs = orient._attachment_at(blocks, *there)
        if mine is not None and theirs is not None:
            total += pair_cost(mine, theirs, mine.axis)
    return total


def body(positions):
    """A placement's identity: its atoms as an ordered set, about its
    own middle.

    Never column by column -- sorting each coordinate on its own
    destroys the atom correspondence and makes every symmetry-related
    placement look the same, which is the opposite of what is being
    counted here.
    """
    middle = positions.mean(axis=0)
    return tuple(sorted(tuple(np.round(row, 2))
                        for row in positions - middle))


def orientations(framework):
    """How the node slots fall into distinct body placements."""
    topology = framework.info["topology"]
    blocks = framework.info["located_bbs"]
    kinds = {}
    for slot in topology.node_indices:
        slot = int(slot)
        kinds.setdefault(body(np.asarray(
            blocks[slot].atoms.get_positions(), dtype=float)),
            []).append(slot)
    return sorted(len(v) for v in kinds.values())


# ---- A: what settling does ------------------------------------------
print("A  the turn itself")
CASES = (("MFU4l", "pcu", "MFU4l_node", "MFU4l_linker"),
         ("MFU4l", "acs", "MFU4l_node", "MFU4l_linker"),
         ("NiHITP", "hcb", "NiHITP_linker", "NiHITP_node"))
for name, net, node, edge in CASES:
    for rule in ("as-found", "consistent"):
        framework = placed(net, node, edge, "", rule)
        before = disagreement(framework)
        angles = []
        partner = {}
        blocks = framework.info["located_bbs"]
        for a, b in orient.fused_points(framework.info["topology"],
                                        blocks,
                                        framework.info["permutations"]):
            partner[a], partner[b] = b, a
        for slot in orient._turnable(blocks):
            angle, _axis, _origin = orient._axial(blocks, partner, slot)
            angles.append(angle)
        turned = orient.align_edges(framework)
        print(f"   {name:7s} {net:4s} {rule:11s} cost {before:9.6f} ->"
              f" {disagreement(framework):9.6f}  turned {turned}"
              f"  angles {[f'{v:+.3e}' for v in angles]}")

print("\n   through build(), the number the verdict reports")
for name, net, node, edge in CASES:
    for rule in ("as-found", "consistent"):
        folder = TMP / f"{name}-{net}-{rule}"
        folder.mkdir(parents=True)
        outcome = build(BuildRequest.parse(net, node, edge, "", rule),
                        folder, CAT)
        print(f"   {name:7s} {net:4s} {rule:11s} {outcome.n_atoms:4d} "
              f"atoms  {outcome.joints:3d} joints  longest "
              f"{outcome.longest_joint:.3f} A")

# ---- B: what is left on pcu -----------------------------------------
print("\nB  what one angle cannot fix")
framework = placed("pcu", "MFU4l_node", "MFU4l_linker")
orient.align_edges(framework)
joints = len(orient.fused_points(framework.info["topology"],
                                 framework.info["located_bbs"],
                                 framework.info["permutations"]))
left = disagreement(framework)
print(f"   MFU4l pcu settles to {left:.6f} over {joints} joints, "
      f"{left / joints:.6f} each")
print(f"   a 45-degree mismatch costs 2 - sqrt(2) = {2 - 2 ** 0.5:.6f}")
print("   every edge of pcu joins a node to an image of ITSELF, so a")
print("   linker meets the same orientation at both ends; where those")
print("   two faces are a quarter turn apart the closed form can only")
print("   split the difference, and this is that split in a number.")

# ---- C: can a repeated net alternate? --------------------------------
print("\nC  the flip, on a repeated net")
for name, node, edge in (("MFU4l probe", "MFU4l_node", "MFU4l_linker"),
                         ("MOF-5 shipped", "N16", "E14")):
    for rule in ("as-found", "consistent"):
        framework = placed("pcu", node, edge, "2x2x2", rule)
        print(f"   {name:14s} {rule:11s} node orientations "
              f"{orientations(framework)}")
print("   MFU-4l alternates because its points stand for two atoms and")
print("   so present a face; N16's stand for one, every orientation")
print("   costs zero, and the build keeps the fit and says so.")
