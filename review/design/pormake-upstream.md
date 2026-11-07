# Upstream PORMAKE: what it knows about the MFU-4l defects

> **Written 2026-09-19** against upstream `Sangwon91/PORMAKE` at branch
> `main` as of that date, and `Crystal-Builder` at `3cd15e2`. Upstream URLs
> and issue states were checked on 2026-09-19 and will drift.

Companion to [pormake-mfu4l.md](pormake-mfu4l.md), which diagnoses the two
defects against the vendored copy. This file records what *upstream* says.

## The headline: it is in their ROADMAP, not their issue tracker

`ROADMAP.md` (not linked from the issue tracker) acknowledges both defects.

- **Item 2 — "Energetically-correct MOF-5 (mirror-symmetric nodes)"**,
  status *Research, medium–high.* States the current MOF-5 recipe "is
  artificial": `pcu` has a single node type, so PORMAKE "places one
  identical Zn4O node building block into every node slot with the same
  orientation", where the real crystal needs clusters across a linker to be
  "**mirror images** of one another"; one orientation "forces the linkers
  into a strained, twisted arrangement." **This is Julius's claim (1),
  described by upstream for MOF-5 and unfixed.** Their proposed route is
  the same one the prototype takes — a supercell so nodes become
  individually addressable — and they concede encoding the alternating
  pattern as a rule "is awkward". Their open question: "Does the
  orientation optimizer actually converge to the correct mirror pattern?"
  (Our answer: no — the objective is degenerate, 0.164405 both ways.)
- **Item 3 — "Topology symmetry-subgroup descent (toward P1)"**, status
  *Research, high.* The general orbit-splitting solution: descend maximal
  subgroups so equivalent slots "split into inequivalent ones, generating
  new node types and edge types". Unimplemented. Notes MOF-5's alternating
  pattern is "one concrete instance of a symmetry-lowered net".
- **Item 4 — "1D / 2D linker-based construction"**, exploratory, concedes
  **"The `X`-point model assumes discrete connection points."** That is
  Julius's claim (2), in upstream's own words.
- **Item 1 — edge linker rotation**, in progress, points at the
  `geonho42` fork. That fork does **linker axial rotation only** — it does
  not touch node orientation or multi-point connections.

## The issue tracker is off-target

All 24 issues (no PRs) were read via the REST API. **None** concerns node
orientation, flipped or alternating nodes, vertex orbits, chirality,
MFU-4, or multi-point connections. The four issues cited in our earlier
research (#25, #29, #32, #33) are a MOF-decomposer request, a 2D-topology
question, an unanswered usage question, and a title-only issue.

More useful than any of them:

- **#37** — maintainer confirms the per-slot escape hatch is real:
  `Builder.build(topology, bbs)` takes a per-slot list of length
  `topology.n_slots` and "Slots are *not* forced to be symmetry-equivalent
  in terms of assignment." Documented for *edges* only; the prototype uses
  it for nodes.
- **#5** — maintainer concedes PORMAKE "cannot take into account the
  steric effects", that post-hoc optimisation is "mandatory", and that
  `node_types` is "poor API design".

## Implementation facts that change the plan

- **Node types are literally the `.cgd` orbits.**
  `Topology.calculate_properties` does `self._node_types =
  self.atoms.get_tags()`; tags come from the RCSR `NODE` records expanded
  by the space group. `pcu.cgd` is one `NODE` line → one orbit → one type.
  There is no orbit-awareness beyond that file.
- **A supercell does not split types.** `pcu * (2,2,2)` gives 8 node slots
  **all still type 0**. Addressable *slots*, not new *types* — so the
  per-slot `bbs` list is the only handle.
- **A custom `.cgd` with two `NODE` records is the supported
  orbit-splitting route**, and is Item 3's manual equivalent.
- **⚠ The automatic chiral fallback will fight a deliberate assignment.**
  `Builder.build` swaps in `make_chiral_building_block()` whenever a slot's
  RMSD exceeds the cached per-type minimum by 1 %. Any fix that pins
  orientations must account for this, or the builder will silently
  re-flip what was pinned. `make_chiral_building_block` negates every
  position — inversion through the origin, no choice of plane or axis.
- **No inter-vertex consistency exists anywhere.** `Locator.locate` sees
  one slot's `LocalStructure` and one block. It never sees a neighbour, an
  edge, or another slot's result.
- **`find_matched_atom_indices` returns exactly one atom index per edge
  end** (a closure in `builder.py`, not `locator.py`). That 1:1 constraint
  is the crux of claim (2); supporting a bridging triazolate would mean
  changing the connection-point data model, `LocalStructure`, the Hungarian
  matching and the bonding step — not a patch to `locate`.

## Re-vendoring would gain nothing

`locator.py` and `topology.py` are **behaviourally identical to 2020**.
Verified by diffing the 2020-07-02 versions against current `main` with
docstrings and comments stripped via `ast.unparse`: `locator.py` differs by
two deleted dead lines; `topology.py` by import order, three dead variables
and one added `logger.exception`. Last functional change to `locator.py`
was `1fb6ce5` (2020-05-18). Upstream has fixed nothing here.

Shipped upstream database: **2406 `.cgd` topologies, 867 building blocks**.

## Corrections to our earlier research

- Upstream's default branch is **`main`**, not `master`, and the package
  moved to **`src/pormake/`** in `ea235ee` (2024-12-21). URLs of the form
  `.../blob/master/pormake/locator.py` now 404.
- `find_matched_atom_indices` is **not** in `locator.py`.

## Not delivered

Literature on ToBaCCo / AuToGraFS and on MFU-4l as a known-hard case was
not obtained. Treat that ground as unresearched rather than clear.
