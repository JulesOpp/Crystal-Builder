# Handoff: continue the polydentate MOF-builder work at Phase 3

Paste the block below into a new session started in
`/Users/julesoppenheim/GitHub/Crystal-Builder`.

---

```
Continue the MOF-builder work on branch `features/mof-polydentate`.
Phases 1 and 2 have shipped; start at Phase 3.

READ FIRST, in this order:
  - docs/ROADMAP.md section 2 -- the phase table and every number
    Phase 1 measured.  This is the authoritative record.
  - ~/.claude/plans/read-through-the-discussions-validated-floyd.md --
    the full plan, already corrected where the probes contradicted it.
  - probes/polydentate/README.md -- how to re-run any measurement.

WHAT IS ALREADY TRUE
  - `1b7df55` Phase 1: ten probes under probes/polydentate/.  All
    three gating probes passed.
  - Phase 2: `BuildOutcome.verdict()` now carries the fit, the closest
    contact and the joint count, and a test pins that it never claims a
    metric symmetry.  New `xtal.mof.build.closest_contact`.
  - probes/polydentate/blocks/ holds the four blocks already cut out of
    the crystals, verified against Julius's spec:
      MFU4l_node    39 body + 6 X   Zn5Cl4(N3C2)6
      MFU4l_linker  14 body + 2 X   C8O2H4
      NiHITP_node    9 body + 2 X   NiN4H4
      NiHITP_linker 24 body + 3 X   C18H6
    Every attachment is bidentate.  probes/polydentate/nets/hcb.cgd is
    a honeycomb layer in PORMAKE's own dialect in a 3-D cell.

THE RULE THAT SHAPES EVERYTHING
  **No file under xtal/mof/pormake/ is edited.**  Every lever needed
  already exists in PORMAKE's public API -- `Topology.__mul__`,
  `Builder.build(permutations=)`, `make_bbs_by_type`, and
  `framework.info["located_bbs"]`.  PROVENANCE.md stays a clean diff
  against upstream 0.2.3 and tests/test_mof_vendored.py stays green
  unchanged; it is the alarm that will notice an accident.

PHASE 3 -- a connection point may stand for several atoms
  Files: xtal/mof/block.py, xtal/mof/catalog.py, new xtal/mof/attach.py,
  xtal/commands/connections.py, xtalapp/document.py, xtalapp/menus.py.

  - `pull_in`: the anchor becomes the mean of all bonded partners; the
    `len(anchors) != 1 -> continue` guard at block.py:53 becomes
    `== 0 -> continue`.  One member gives bit-identical arithmetic.
  - `problems`: block.py:98-104 loosens from `n != 1` to `n < 1`.  Add
    refusals for an X bonded to another X, for members further apart
    than a new MAX_ATTACHMENT_SPAN, and for an attachment pointing
    inward.  Do NOT refuse two X sharing a member atom.
  - `catalog.read_building_block` (catalog.py:249-285) must parse the
    bond block, with the tolerance at pormake/utils.py:529-531.
  - `MarkOneConnectionPoint`: collapse the selection to one X at its
    centroid carrying every bond the group had to atoms outside it.
    Reuse `measure.centroid` and `AddSites(perceive=False)` exactly as
    `Document.merge_atoms` does.  Menu: "Mark as &one connection
    point", beside mark_connection_points, on two or more atoms.

  THREE MEASURED FACTS THE PHASE MUST HONOUR
  1. `members` is the set of DISTINCT partners of an X, never the bond
     count.  54 shipped connection points carry more than one bond
     record; 52 of them name the same partner twice, across 26 blocks.
     Counting records would take 26 shipped blocks down the new path.
  2. N484 (an X bonded to a hydrogen) and N684 (1.201 and 0.613 A from
     its two partners, against CONNECTION_DISTANCE 0.75) are upstream
     data errors that genuinely read as bidentate.  No geometric
     tolerance separates them cleanly from ours -- N684 sits 0.703 A
     from its members' centroid against our 0.750 -- so pin them in a
     test rather than tuning a threshold to 0.047 A.
  3. tests/test_block_writer.py:167
     `test_a_connection_point_with_two_bonds_is_named` must be
     REWRITTEN, not deleted: two bonds is now a bidentate attachment.
     The refusal that stays is an X with no bonds.

  Invariants: CLAUDE.md's "a connection point is 0.75 A from the atom
  it hangs off" becomes "from the centroid of the atoms it hangs off"
  -- amend it and say why.  "There is no Unmark" is untouched, because
  the grouping is the structure's own bonds and not new state on a
  marker.  One Document.apply, one undo step.

AFTER PHASE 3
  Phase 4 joints, 5 node orientation, 6 linker orientation, 7 MFU-4l,
  8 layer nets + Ni-HITP, 9 interpenetration.  Phase 9 is independent
  of all of them and can be pulled forward.

TWO NUMBERS PHASE 5 WILL NEED, AND THEY ARE NOT GUESSES
  - The rotation-group search needs a tolerance of 1e-3, not 1e-6: a
    block cut from a real crystal is octahedral to a thousandth of a
    degree, and at 1e-6 the search returns only the identity.
  - The tie criterion must be GAP-BASED, never an absolute epsilon.
    The block's own imperfection is ~1e-5 and the real gap is a factor
    of 10^5 (4.6e-06 against 8.2e-01).

HOUSEKEEPING
  - Python is /opt/anaconda3/bin/python.
  - `python -m pytest -q tests/test_mof_builder.py tests/test_block_writer.py
    tests/test_mof_vendored.py tests/test_mof_ui.py` while iterating;
    full suite once before merging.
  - `ruff check .` only, never `ruff format`.  probes/ is excluded.
  - Check `sysctl vm.swapusage` before trusting any timing; this
    machine has been sitting at 12 GB of 13.3 GB in use.
  - The other developer is on `features/deep-review` doing their
    Phase 1 and 2.  Nothing of theirs touches xtal/mof/.  Do not
    modify xtal/analysis/topology.py or rcsr.py -- their item 2.2 is
    interpenetration DETECTION there; ours is generation, in a new
    file xtal/analysis/interpenetrate.py.
```
