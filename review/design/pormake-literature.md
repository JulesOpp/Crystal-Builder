# Has anyone built MFU-4l automatically? No.

> **Written 2026-09-19.** Literature and tool survey; sources checked on
> that date. Companion to [pormake-mfu4l.md](pormake-mfu4l.md) (the
> diagnosis) and [pormake-upstream.md](pormake-upstream.md) (what upstream
> knows). This file resolves the `[uncertain]` marker §5.4 carried.

## The headline

**No tool, paper or database entry was found in which MFU-4 or MFU-4l is
built by an automated topology-based generator, and no paper names it as a
known failure case.** Searched: ToBaCCo (1.0 and 3.0), PORMAKE, AuToGraFS,
Boyd–Woo/TOBASCCO, MOFBuilder, pyCOFBuilder, hMOF and the hypothetical-MOF
screening literature.

Corroborating negatives, not merely absence of evidence:

- ToBaCCo's `nodes_database` (45 entries) contains **no** Kuratowski or
  triazolate node at all — they are carboxylate/N-donor nodes.
- Chung & Lah's 2026 review, the most thorough survey of generator
  limitations available (Israel J. Chem., 10.1002/ijch.70028), **never
  mentions MFU-4, MFU-4l, Kuratowski or triazolate** — full text keyword
  scanned.
- The Volkmer group's own computational work on MFU-4l (New J. Phys. 2013,
  10.1088/1367-2630/15/11/115004) built its models from the experimental
  structure, not from a generator.

If Crystal Builder builds it, that is a first. **A good position, not a bad
one** — and worth a line in the release notes.

## Why MOF-5 survives a naive builder and MFU-4l does not

The sharpest insight from the survey, and it explains why upstream's
ROADMAP frames this around MOF-5 while MFU-4l is the harder case:

- **MOF-5**: the connection point sits at the **carboxylate carbon**, and
  the two Zn4O orientations put that carbon in *identical* positions — they
  differ only in where the O and Zn atoms sit. A single-`X` builder is
  therefore **accidentally right** up to the node's internal atoms.
- **MFU-4l**: the connection is a **triazolate N–N unit bridging the
  central octahedral Zn and one peripheral tetrahedral Zn**. The contact is
  two-point and orientation-carrying, so the same orientation error becomes
  a real **connectivity** error.

That is exactly the pairing Julius named: his claims (1) and (2) are one
defect, and MOF-5 hides it while MFU-4l exposes it.

## Is the problem named in the literature?

Partially, and the named version is weaker than ours.

- **"Topology–chemistry mismatch" / "structural demons" (class D3)** —
  Chung & Lah 2026. Closest named diagnosis: *"most generators check only
  coordination number when placing an SBU on a net"*, with a call for
  *"using vertex and edge site symmetry as construction-time filters rather
  than post-hoc descriptors"*. **But its scope is whether a block belongs on
  a vertex at all — not consistent relative orientation between neighbouring
  vertices.** Ours is the stronger, unaddressed version.
- **Symmetry-guided topology filtering** — Darù et al., Adv. Mater. 2025,
  10.1002/adma.202414617. Filters candidate topologies by point-group
  compatibility (MOF-841: 15 candidates reduced to `flu`). It selects a
  topology and hands off to ToBaCCo for the CIF; it does not discuss
  multi-orbit nets.
- **No established reticular-chemistry term** exists for the two-colouring
  / alternating-orientation problem. "Decoration" already means
  augmentation, not colouring. Searched without success: "orientation
  consistency", "binary decoration of a net", "alternating decoration",
  "local site symmetry compatibility".

**The correct crystallographic framing** (the surveyor's synthesis, not a
citation): MFU-4l requires a *symmetry-lowering ordered decoration* of a
vertex-transitive net. `pcu` has transitivity [1 1], but the structure
realises it in a **klassengleiche subgroup with a doubled cell**, splitting
the single vertex orbit into two. The algorithmic task is to compute vertex
orbits **of the target structure's space group** rather than of the
maximum-symmetry net embedding, choose a per-orbit block *and orientation*
from the site-symmetry coset, and propagate by the space-group operators —
instead of P1 plus independent per-vertex Kabsch, which is what every tool
surveyed actually does.

That framing matters here: **Crystal Builder already has subgroup descent**
(CLAUDE.md's 237-subgroup MFU-4l descent, `xtal/core/symmetry.py`), which is
the machinery upstream's ROADMAP Item 3 says it lacks.

## Precedents for bolting a constraint onto independent fitting

- **π-d PORMAKE** (Chong et al., ChemRxiv 2024, 10.26434/chemrxiv-2024-kzdm3)
  — a PORMAKE fork *"with additional features to enforce co-planarity in
  placing the edges"*. Direct precedent: same independent-fit limitation,
  patched with an inter-block constraint.
- **MOFBuilder** — attaches **"XOO" atoms (connection point + bonded
  atoms)** per edge and optionally adds *"virtual edges for bridge-type
  nodes"*. The nearest thing to a polydentate connection primitive in any
  general builder.
- **AuToGraFS v3** — *"Hungarian assignment + Kabsch, proper rotations only
  — chiral building blocks are never silently mirrored."* Worth contrasting
  with PORMAKE, whose chiral fallback **does** silently mirror (see
  [pormake-upstream.md](pormake-upstream.md)).

## MFU-4l facts worth having in one place

- **MFU-4**: Biswas et al., Dalton Trans. 2009, 6487, 10.1039/B904280F.
  [Zn5Cl4(BBTA)3]·3DMF.
- **MFU-4l**: Denysenko et al., Chem. Eur. J. 2011, 17, 1837,
  10.1002/chem.201001872. [Zn5Cl4(BTDD)3], solved from 3D electron
  diffraction tomography. CCDC 971402.
- **Kuratowski SBU**: Biswas et al., Inorg. Chem. 2010, 49, 7424 — the
  non-planar K(3,3) graph the unit is named for.
- **Topology `pcu`**, independently confirmed: *"MFU-4 and MFU-4l are
  isoreticular to MOF-5 and the IRMOF series with pcu topology"*, and *"the
  Zn5Cl4 SBU adopts Td symmetry with a connectivity of six"* (NU-6000/NU-6001,
  Nature Materials 2026, 10.1038/s41563-026-02662-y).
- **Orientation is a design variable, not an artefact** — same paper: *"By
  rotating the coordinated arms of the linkers by 90° along the triazole
  direction"*, *"flipping the coordinated arms … aligns with node symmetry
  to preserve the overall topology"*.
- Family: CFA-1 (`acs`), CFA-7 (two-fold interpenetrated `pcu`) — and
  `CFA1.cif` is one of the shipped samples this review found has coincident
  atoms.

## Stated gaps

Flagged rather than guessed, and they should stay open:

- No literature sentence states that alternate Kuratowski nodes are rotated
  90° relative to one another. The Td + 6-connected + fcc + two-cavity
  evidence supports it; **our own measurement of the CIF is the primary
  evidence** (see [pormake-mfu4l.md](pormake-mfu4l.md)).
- Whether MFU-4l appears in CoRE MOF / QMOF / ARC-MOF: **unknown**, not
  determinable from public interfaces.
- "ZEOMICS", "SBUbuilder", "fmof", and "MOFgen" as a topology builder: no
  primary sources found. Do not cite without independent confirmation.
