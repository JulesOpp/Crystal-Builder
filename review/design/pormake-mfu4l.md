# Building MFU-4l: what stops it, and what it would take

> **Written 2026-09-19** against `Crystal-Builder` at commit `3cd15e2` (v0.2.1),
> which is the base of branch `features/deep-review`. Note `origin/main` has
> since moved to `fb38d25`. Every line number, measurement and code reference
> below was true at `3cd15e2` — re-verify before acting on it if the file has
> changed. (`fb38d25` touched only `xtalapp/docks/ff_panel.py` and
> `tests/test_ff_ui.py`; nothing this document cites.)

## Summary

1. Both of Julius's claims are **true and reproducible**. MFU-4l is `pcu`
   (the app says so), its eight nodes per cell alternate in orientation on a
   checkerboard, and each linker end binds **three** Zn, not one.
2. Claim (1) is **not** a bad RMSD fit. The two orientations have
   *bit-identical* RMSD (0.164405 both ways): the objective is exactly
   degenerate, so the builder has no signal at all, not a weak one.
3. The flip is a **relative** property. One node in isolation cannot show it
   — a 90° turn about a cubic axis carries orientation A to B and leaves the
   six linker axes alone. What breaks is the **twist across one edge**: 0° for
   the real A–B alternation, **90°** for the A–A that a single-orbit build
   gives, against a linker that is planar to 0.0000 Å.
4. A working prototype (`review/probes/pormake/09_prototype.py`) reproduces
   MFU-4l's exact checkerboard **with no change to vendored code**, using
   `Builder.build`'s existing `permutations=` argument, which
   `xtal/mof/build.py:338` never passes because it calls `build_by_type`.
5. Claim (2) has **no cheap fix**. One `X` = one point = one direction is
   baked into `LocalStructure`, the Hungarian matching and
   `find_matched_atom_indices`, and into this project's own
   `block.problems()`. Upstream's `ROADMAP.md` concedes it.

Recommendation: **ship the orientation fix (Option A1, size M), and do not
attempt the multi-point fix.** Ship instead an honest refusal plus the
absorbed-linker recipe (Option B1, size S).

---

## 1. The target, measured

`review/probes/pormake/01_target.py`, `02_net.py`, `03_flip.py`,
`10_attachment.py`, `12_linker.py`. All run as
`.venv/bin/python review/probes/pormake/NN_*.py` from the repo root.

### 1.1 What it is

```
$ .venv/bin/python review/probes/pormake/01_target.py
space group : SpaceGroup(Fm-3m #225)
lattice     : Lattice(a=31.0569, ... alpha=90.000, beta=90.000, gamma=90.000)
sites (asym): 10
P1 atoms    : 648
P1 formula  : Counter({'C': 288, 'N': 144, 'H': 96, 'O': 48, 'Zn': 40, 'Cl': 32})
bonds in P1 : 848

coordination by site:
  site  0 Zn1   Zn   mult= 32  CN=[4]  neighbours of one={'Cl': 1, 'N': 3}
  site  1 Cl1   Cl   mult= 32  CN=[1]  neighbours of one={'Zn': 1}
  site  2 Zn2   Zn   mult=  8  CN=[6]  neighbours of one={'N': 6}
  site  3 N1    N    mult= 96  CN=[3]  neighbours of one={'Zn': 1, 'C': 1, 'N': 1}
  site  5 N2    N    mult= 48  CN=[3]  neighbours of one={'Zn': 1, 'N': 2}
  site  8 O1    O    mult= 48  CN=[2]  neighbours of one={'C': 2}
fragments: 1  ->  Counter({('framework', 648): 1})
```

Z = 8 of `C36 H12 Cl4 N18 O6 Zn5` (the CIF's own
`_chemical_formula_sum`). The Kuratowski SBU is **one octahedral Zn2**
(CN 6, all N) plus **four tetrahedral Zn1** (CN 4, N₃Cl), i.e. Zn₅Cl₄N₁₂.
There are **8 SBUs** and **24 linkers** per conventional cell; each linker is
24 atoms, C₁₂N₆O₂H₄ — bis(1,2,3-triazolato)dibenzo[1,4]dioxin.

### 1.2 What net the app says it is — `pcu`, confirmed

`02_net.py` contracts every Zn₅Cl₄ cluster to one vertex and every organic
fragment to one edge, then hands the quotient graph to the app's own
identifier:

```
$ .venv/bin/python review/probes/pormake/02_net.py
number of SBUs: 8
organic fragments: 24 sizes: [24]
  contacts per (SBU, image) for one linker: {(SBU 0, (0,0,0)): 3, (SBU 1, (0,0,0)): 3}
edges: 24
degrees: [6]
NET IDENTIFICATION: pcu -- 6-coordinated, 3-periodic;
  coordination sequence 6, 18, 38, 66, 102, 146, 198, 258, 326, 402;
  point symbol 4^12.6^3   ->  named
```

`rcsr.describe(Net(...), rcsr.catalogue())` returns `pcu`, verdict `named`.
**Julius is right: it is `pcu`.** The 8 SBU centres sit on Wyckoff `8c` of
*Fm-3m*, which is a primitive cubic array of parameter *a*/2 = 15.53 Å.

Note the line that already answers claim (2) in passing: **3 contacts per
linker end**, not 1.

### 1.3 "Every other node is flipped" — confirmed exactly

`03_flip.py` takes the four peripheral Zn1 around each of the eight Zn2 and
prints the tetrahedron they form:

```
orientation A : centres at frac (¼,¼,¼) (¾,¾,¼) (¼,¾,¾) (¾,¼,¾)
  [[-0.577,-0.577,-0.577],[-0.577,0.577,0.577],[0.577,-0.577,0.577],[0.577,0.577,-0.577]]
orientation B : centres at frac (¾,¼,¼) (¼,¾,¼) (¾,¾,¾) (¼,¼,¾)
  [[-0.577,-0.577,0.577],[-0.577,0.577,-0.577],[0.577,-0.577,-0.577],[0.577,0.577,0.577]]

B == -A (as sets)? True

neighbour check (SBUs 15.5 A apart):
    64 ->  65  dist 15.53  same orientation? False
    64 ->  67  dist 15.53  same orientation? False
    64 ->  71  dist 15.53  same orientation? False
    65 ->  64/66/70  dist 15.53  same orientation? False
```

Two orientations, exact inversions of one another, **checkerboard by the
parity of the vertex's integer position**, and *every* `pcu` neighbour is of
the opposite class. The two `8c` sub-orbits are related by the inversion
centre at the origin, which is **not** a lattice translation of *F*.

### 1.4 "The SBU doesn't connect at a single point" — confirmed, with numbers

```
$ .venv/bin/python review/probes/pormake/10_attachment.py
one linker: 24 atoms, Counter({'C': 12, 'N': 6, 'H': 4, 'O': 2})
Zn contacts of this one linker: 6
   N -- Zn(Zn1)  2.010 A     (x4)
   N -- Zn(Zn2)  2.041 A     (x2)
this linker touches 2 SBUs; contacts per end: [3, 3]

  SBU centre at [7.76 7.76 7.76]
    3 attachment atoms, spread 2.189 A
    their centroid is 2.558 A from the SBU centre
      N116  3.022 A from centre, 21.24 deg off the axis
      N264  2.041 A from centre,  0.00 deg off the axis
      N72   3.022 A from centre, 21.24 deg off the axis
```

One triazolate end presents **three N to three different Zn**: the middle N
to the central Zn2 on the 4-fold axis, and the two outer N to two *different*
peripheral Zn1, each 21.24° off that axis, spanning 2.189 Å. The linker is
**rigid and exactly planar**:

```
$ .venv/bin/python review/probes/pormake/12_linker.py
singular values of its atom cloud: [16.452  6.61   0.   ]
r.m.s. deviation from the best plane: 0.0000 A
```

---

## 2. Reproducing the failure

### 2.1 There is no MFU-4l node block, and no MFU-4l edge block

```
$ .venv/bin/python review/probes/pormake/12_linker.py   # tail
any block containing only O?    []
any Kuratowski block with Cl?   []
```

Over the 867 blocks the catalogue reads (`Catalog.default()`, 2403
topologies), the **only** Kuratowski-shaped candidates are `N457`
(`C36H18N18Zn5`, 6-connected) and `N208` (`C36CoH18N18Zn4`). Both are
**chloride-free** — PORMAKE's block is Zn₅(benzotriazolate)₆, not
Zn₅Cl₄(triazolate)₆ — and both have already **absorbed the triazolate and its
fused benzo ring into the node**, putting the `X` on a benzo carbon. There is
no two-connected O₂ block to serve as MFU-4l's dioxin bridge (the smallest
2-connected blocks are `E27` N₂, `E44` C₂, `E19` C₂H₂, `E38` C₄).

So **before any geometry**, the shipped catalogue cannot express MFU-4l's
chemistry. `[important]`

### 2.2 The build completes, and builds the wrong compound

```
$ .venv/bin/python review/probes/pormake/04_build.py
topology pcu: 6-c  ·  Pm-3m
slots: [('Node 1, 6-connected', '0', 6), ('Linker at node 1', '0-0', 2)]
N457: C36H18N18Zn5 6 connections
|X - centroid| = [7.16 7.404 7.047 7.374 7.139 7.436]
  X0..X5 nearest body atom at 0.702-0.818 A
angles between X directions (deg):
[76.0 76.6 77.1 84.7 85.1 86.6 90.4 90.8 91.7 107.9 108.5 109.3 164.7 165.2 165.8]

pormake: == Min RMSD of (node type: 0, node bb: N457): 1.64E-01
pormake: Pre-location at node slot 0 ... RMSD: 1.64E-01
pormake: OBJ: 0.041
pormake: Location at node slot 0 ... RMSD: 1.19E-01
wrote pcu-N457.cif ; bonded 3 joint(s) ; drew 3 net edge(s)
verdict: the framework is pcu, as asked

atoms: 77   max_rmsd: 0.1186   joints: 3
P1 atoms: 77 Counter({'C': 36, 'N': 18, 'H': 18, 'Zn': 5})
lattice: Lattice(a=14.3660, b=14.4210, c=14.5160,
                 alpha=81.042, beta=99.409, gamma=100.238)
```

**Nothing fails.** `BuildOutcome.verdict()` says *"the framework is pcu, as
asked"* and `net_agrees` is `True`. What comes out:

| | real `MFU4l.cif` | `pcu` + `N457` |
|---|---|---|
| atoms in the cell | 648 | 77 |
| nodes in the cell | 8 | 1 |
| cell | cubic *a* = 31.0569, 90/90/90 | **triclinic** 14.37/14.42/14.52, **81.0/99.4/100.2** |
| formula | Zn₄₀Cl₃₂C₂₈₈N₁₄₄O₄₈H₉₆ | Zn₅C₃₆N₁₈H₁₈ |
| chlorides | 32 | **0** |
| linker | 24-atom planar dibenzodioxin | none (blocks fused X–X) |
| node RMSD to the vertex | — | 0.1186 |

Two things to read off. First, the cell comes out **triclinic**: `N457`'s six
`X` directions are 76–110° and 165° apart, not 90/180°, so `Scaler.scale`
deforms the cell to absorb the mismatch rather than reporting it. Second, the
whole build is **one vertex** — `pcu.cgd` is a single line, `NODE 1 6 0 0 0`,
so a single-cell build has literally nowhere to put a second orientation.

### 2.3 Eight vertices, and still no alternation

`05_supercell.py` / `06_orient.py` build `pcu * (2,2,2)` — eight slots, the
count MFU-4l has — and measure each placed node:

```
$ .venv/bin/python review/probes/pormake/05_supercell.py
node slots: [0, 4, 8, 12, 16, 20, 24, 28]
node types: [0 0 0 0 0 0 0 0]   unique: [0]   n_node_types: 1
every node slot's local structure identical? True

$ .venv/bin/python review/probes/pormake/06_orient.py
  centre    8  centroid frac [0.01 0.07 0.01]  [[-0.64,-0.57,0.52], ...]
  centre   85  centroid frac [0.01 0.07 0.51]  [[-0.64,-0.57,0.52], ...]   <- same
  centre  162  centroid frac [0.01 0.57 0.01]  [[-0.64,-0.57,0.52], ...]   <- same
  centre  239  centroid frac [0.01 0.57 0.51]  [[-0.64,-0.57,0.52], ...]   <- same
  centre  316  centroid frac [0.5  0.03 1.  ]  [[-0.63, 0.52,0.57], ...]
  centre  393  centroid frac [0.5  0.03 0.5 ]  [[-0.63, 0.52,0.57], ...]
  centre  470  centroid frac [0.5  0.53 1.  ]  [[-0.63, 0.52,0.57], ...]
  centre  547  centroid frac [0.5  0.53 0.5 ]  [[-0.63, 0.52,0.57], ...]

distinct orientations PORMAKE produced: 2
second is the inversion of the first? False
```

It produced two orientations, but as **stripes along *x***, not a
checkerboard: the four nodes at *x* ≈ 0 share one orientation and the four at
*x* ≈ ½ share the other, so every neighbour along *y* and *z* is **wrong**.
And the two are related by a rotation, not the inversion the crystal has.
That the split happened at all is an accident of `Scaler` relaxation in a
supercell (more free vertices), not a rule the builder applied.

**This is the failure, exactly as described, and it is silent.** `[critical]`

---

## 3. Diagnosing claim (1) — "every other node is flipped"

### 3.1 Where the orientation is chosen

`xtal/mof/pormake/builder.py:286` inside `Builder.build`:

```python
for i in topology.node_indices:
    node_bb = bbs[i]
    target  = topology.local_structure(i)         # :283
    ...
    located_node, perm, rmsd = locator.locate(target, node_bb)   # :286
```

`Locator.locate` (`locator.py:107`) scans a coarse Euler grid; at each trial
it solves the assignment problem (`find_best_permutation`, `locator.py:28`,
Hungarian on the pairwise distance matrix) and then Kabsch-fits
(`find_best_orientation`, `locator.py:59`,
`scipy.spatial.transform.Rotation.align_vectors`), keeping the lowest RMSD.

**It is fitted per vertex, independently.** The only argument that varies with
`i` is `target = topology.local_structure(i)` — the set of unit vectors from
the vertex to its neighbours (`topology.py:259`). The locator never sees a
neighbour's placement, an edge, or another slot's result. The only cross-slot
state in the loop is `slot_min_rmsd[(node_type, bb.name)]`, a reference
minimum used to decide whether to retry.

### 3.2 So which of Julius's two explanations is it? **Neither, quite.**

The brief asks whether the net's vertex set has two orbits the builder
collapses to one, or whether the fit picks the lowest-RMSD orientation per
vertex with no consistency constraint. The measurements say:

- **It is not an orbit-collapse.** `pcu` genuinely has one vertex orbit.
  `Topology.calculate_properties` does `self._node_types =
  self.atoms.get_tags()` (`topology.py:221`), and those tags come straight
  from the `.cgd`'s `NODE` records, so PORMAKE's node types **are** the RCSR
  vertex orbits, faithfully. `pcu` has one, correctly. The `8c` orbit of
  *Fm-3m* is also one orbit. Nothing is being collapsed. What MFU-4l needs is
  a *symmetry-lowered* description of `pcu` in which the single orbit splits
  in two — which is a different net file, not a bug in the typing.

- **It is not "lowest RMSD with no consistency constraint" either**, because
  there is no lowest. The two orientations are **exactly degenerate**:

```
$ .venv/bin/python review/probes/pormake/07_degeneracy.py
N457 best RMSD onto a pcu vertex          : 0.164405
  turned  90 deg about (0,0,1) -> RMSD 0.164405
  turned 180 deg about (0,0,1) -> RMSD 0.164405
  turned 120 deg about (1,1,1) -> RMSD 0.164405
  inverted (make_chiral_building_block) -> RMSD 0.164405
```

  Identical to six decimal places, because the connection points are the only
  thing in the objective and the octahedron maps onto itself under all of
  them. `08_perm_lever.py` enumerates all 720 permutations: **24 of them tie
  at exactly 0.164405**, reaching **8 distinct body orientations**, three
  permutations each (three because `N457`'s body retains only a 3-fold axis;
  an ideal Td Kuratowski block would give 24/12 = **2**, which is precisely
  the flip).

The accurate statement is: **the orientation the structure needs is invisible
to the objective the builder minimises, and the tie is broken arbitrarily.**
Adding a consistency constraint to a degenerate objective is not a tweak —
the information is absent, so it has to be supplied.

### 3.3 The number: the defect lives on the edge, not the vertex

`11_multipoint.py`:

```
a 90 deg turn about x carries A to B?  True
...and leaves the six linker axes alone, so ONE node in
   orientation A is indistinguishable from one in B.

twist the linker must absorb across one edge:
   A -- B  (the real MFU-4l alternation) :   0.0 deg
   A -- A  (what a single-orbit build gives):  90.0 deg
```

This is the finding I would put in front of Julius. **A single node cannot be
"flipped" at all** — the Kuratowski unit is achiral (Td contains σd), so
orientation B is a proper rotation of A. What alternates is which pair of
peripheral Zn faces each edge, and therefore the **plane of the triazolate**
each SBU presents. Across one edge, the real A–B pairing presents coplanar
triazolates (0°); an A–A pairing presents them at **90°**, against a linker
whose 24 atoms are planar to 0.0000 Å. The linker physically cannot bridge it.

So "every other node is flipped" is better stated as: **the orientation is a
two-colouring of the net that must be proper (no edge monochromatic), and
PORMAKE assigns colours vertex by vertex with no edge in view.**

### 3.4 `make_chiral_building_block` is not the lever it looks like

`builder.py:276` and `:313` call it, and `building_block.py:104` just negates
every position. It fires **only** as a fit-quality fallback when
`rmsd / slot_min_rmsd > 1.01`. On MFU-4l the ratio is exactly 1.0, so it never
fires; and if it did, it would fire per vertex on RMSD grounds, which carries
no information about the neighbour. It is also a *global* inversion with no
choice of centre or axis. `[minor]` as a lever; worth knowing it will fight a
fix that changes RMSDs.

---

## 4. Diagnosing claim (2) — "the SBU doesn't connect at a single point"

### 4.1 What exactly assumes one point

Four places, in increasing order of how hard they are to change:

1. **This project's block model.** `xtal/mof/block.py:68` `problems()`:

   ```python
   for atom in marked:
       n = len(graph.bonds_of(atom))
       if n != 1:
           found.append(f"... is a connection point with {n} bond(s), "
                        f"and it needs exactly one to say which way it points")
   ```

   and `pull_in` (`block.py:37`) silently leaves alone any `X` with ≠ 1 bond:
   *"there is no single direction to place it along, and silently picking one
   of two would be worse."* `CONNECTION_DISTANCE = 0.75` (`block.py:29`) is a
   scalar along that one direction.

2. **`LocalStructure`** (`local_structure.py:56`, `normalize_positions` at
   `:81`) reduces a set of positions to **unit direction vectors from their
   centroid**. Denticity, spread and distance are all discarded. MFU-4l's
   2.189 Å spread and the 21.24° fan simply are not representable.

3. **The matching.** `find_best_permutation` (`locator.py:28`) solves a
   *bijection* between *n* block points and *n* target directions. A
   tridentate end needs a 3-to-1 grouping, which is a different combinatorial
   problem.

4. **The bonding step.** `find_matched_atom_indices`, a closure inside
   `Builder.build` at `builder.py:419`, returns **exactly one atom index per
   edge end** (`a1, a2` at `builder.py:525`), and `builder.py:537` then builds
   `LocalStructure(np.array([r1, r1 + d]), [i1, i2])` — a two-point local
   structure for the edge. One `X` in, one bond out.

**The assumption that breaks is (2) and (4), not the distance and not the
RMSD fit.** `CONNECTION_DISTANCE` is fine; 0.75 Å is a marker offset and it
would be 0.75 Å for a bridging attachment too. The RMSD fit is fine as far as
it goes. What is missing is any way to say *"these three atoms are one
attachment"* — the data model has no denticity. `[critical]`

### 4.2 PORMAKE's own workaround, and why it is not enough here

`N457` shows the escape: **absorb the bridging group into the node**. Put all
six triazolates (and their fused benzo rings) inside the node block, and the
node–linker boundary moves out to a plain C–C bond, one point, one direction.
That is how the catalogue's Kuratowski block exists at all.

For MFU-4l this only moves the problem. After absorbing the benzotriazolate,
the remaining edge is the **dioxin bridge**, and `10_attachment.py` shows each
O bonds **2 carbons** — one from each benzo ring, and each benzo ring gives
**two** carbons to the dioxin ring (O1 has multiplicity 48 = 2 per linker; C3
has 96 = 4 per linker = 2 per ring). So the edge is a two-atom O₂ fragment
with a **bidentate end at each side**. Cut anywhere and MFU-4l's attachment is
multi-point:

| cut | node | edge | denticity per end |
|---|---|---|---|
| Zn–N | Zn₅Cl₄ | 24-atom linker | **3** |
| C–O | Zn₅Cl₄(bta)₆ (≈ `N457` + Cl) | O₂ | **2** |
| C–C | Zn₅Cl₄(bta)₆ | dibenzodioxin minus the rings | not a fragment |

The only single-point cut is one that absorbs the *whole* linker into the node
— i.e. a node block that is half the unit cell, with no edge at all. That is
not a building-block decomposition; it is writing the answer down.

### 4.3 It is the *same* defect as claim (1)

The atoms that make the attachment multi-point are exactly the atoms that
carry the flip. The middle N sits on the axis and says nothing about
orientation; the two outer N at 21.24° are bonded to two specific peripheral
Zn, and *which two* is what alternates. Collapse the end to one on-axis point
and you have deleted the only geometric evidence of the node's orientation —
which is why §3.2 finds the objective exactly degenerate.

Stated the other way: **fix (2) and (1) largely fixes itself**, because the
off-axis contacts would enter the objective and a mis-oriented neighbour would
cost RMSD. Fix (1) alone and you still cannot express MFU-4l's chemistry.
This coupling is the main reason I recommend what I do in §6.

---

## 5. Upstream

Researched via the GitHub REST API and `raw.githubusercontent.com`
(the brief's `blob/master/pormake/...` URLs 404 — the default branch is
**`main`** and the package moved to **`src/pormake/`** in `ea235ee`,
2024-12-21). GitHub's HTML issues page paginates; the REST API returned all
24 issues. GitHub code search was rate-limited unauthenticated, so
"no mention of X" below rests on grepping downloaded files, not an exhaustive
repo search.

### 5.1 The issue tracker does not have this

All 24 issues (no PRs) were listed. **Nothing** is about node orientation,
flipped or alternating nodes, vertex orbits, chirality, MFU-4, or multi-point
connections. The four the brief names are off-target:

| # | State | What it is |
|---|---|---|
| [#25](https://github.com/Sangwon91/PORMAKE/issues/25) | open | "MOFDecomposer" — how to decompose a MOF into topology + BBs. One comment pointing at CrystalNets. Not this. |
| [#29](https://github.com/Sangwon91/PORMAKE/issues/29) | open | 2D topologies (`hcb`). Maintainer: PORMAKE "was not specifically designed for 2D topology structures". Not this. |
| [#32](https://github.com/Sangwon91/PORMAKE/issues/32) | open | How to generate random MOF geometries. **Zero comments.** Not this. |
| [#33](https://github.com/Sangwon91/PORMAKE/issues/33) | open | Two types of linkers. **Empty body.** One community comment on enumerating mixed linkers, noting "if the order of linkers doesn't have symmetry, then the permutation would also be important." Adjacent, not this. |

Two others are more use:

- **[#37](https://github.com/Sangwon91/PORMAKE/issues/37)** (closed) — can
  different linkers go on individual slots of one edge type? Maintainer:
  *"Yes, this is fully supported"* — `Builder.build(topology, bbs)` takes a
  **per-slot** list of length `topology.n_slots`, and *"slots are not forced
  to be symmetry-equivalent in terms of assignment."* This is the documented
  escape hatch — documented for **edges only**.
- **[#5](https://github.com/Sangwon91/PORMAKE/issues/5)** — maintainer
  concedes PORMAKE *"cannot take into account the steric effects"* and that
  post-hoc energy optimisation is *"mandatory"*, and calls `node_types`
  *"poor API design"*.

### 5.2 Upstream's `ROADMAP.md` names our exact bug — as MOF-5

The single most useful artefact, **not linked from the issue tracker**:
<https://github.com/Sangwon91/PORMAKE/blob/main/ROADMAP.md>

- **Item 2, "Energetically-correct MOF-5 (mirror-symmetric nodes)"**, status
  *Research*, difficulty *medium–high*. States the current MOF-5 recipe "is
  artificial": on `pcu` there is a single node type so PORMAKE "places one
  identical Zn₄O node building block into every node slot with the same
  orientation", whereas the real clusters across a linker "must be **mirror
  images** of one another", and a single orientation "forces the linkers into
  a strained, twisted arrangement." Proposed fix: **expand to a 2×2×2
  supercell so nodes become individually addressable slots**, then assign
  mirror-related orientations — conceding that encoding the alternating
  pattern as a rule "is awkward". Open question: *"Does the orientation
  optimizer actually converge to the correct mirror pattern?"*
- **Item 3, "Topology symmetry-subgroup descent (toward P1)"**, status
  *Research*, difficulty *high*. Descend maximal subgroups so equivalent slots
  "split into inequivalent ones, generating **new node types and edge
  types**"; notes "MOF-5's alternating pattern is one concrete instance of a
  symmetry-lowered net." Unimplemented.
- **Item 4, "1D / 2D linker-based construction"**, *Exploratory*. Open
  question naming defect (2): *"How should rod / sheet building blocks and
  their connection points be represented? **The `X`-point model assumes
  discrete connection points.**"*

So: **upstream knows about (1), has not fixed it, and its proposed route is
the supercell route.** It knows about (2) only as an open question. This is
worth telling Julius — his diagnosis is independently the same as the
upstream author's, one framework earlier.

### 5.3 Nothing to gain by re-vendoring

`locator.py`: 7 commits, last **functional** change `1fb6ce5` (2020-05-18).
`topology.py`: 14 commits, last functional change `b474c2c` (2020-07-02).
Diffing the 2020 versions against current `main` with docstrings and comments
stripped: `locator.py` differs by **two deleted dead lines**; `topology.py` by
import reordering, three dead-variable removals and one added
`logger.exception`. **The placement algorithm and node typing are behaviourally
byte-identical to 2020.** The vendored 0.2.3 copy needs no update here, and
upstream has fixed nothing. `[strength]` for the vendoring decision.

The `geonho42` fork linked from upstream's README rotates **linkers** to match
each net's space group and adds single-metal-atom nodes. It does **not** touch
node orientation or multi-point connections.

### 5.4 Literature — partial `[uncertain]`

The repository half above is verified. A second agent researching how
**ToBaCCo**, **AuToGraFS** and other reverse-topological builders handle
(a) distinct vertex orbits with different orientations and (b) multi-atom
bridging connection sites, and whether MFU-4l/Kuratowski is reported anywhere
as a hard case, **had not returned when this was written**. I am not going to
guess at it. What I can say from the code and upstream's own ROADMAP is that
the general shapes of the problem have standard names — a *proper
two-colouring of the net* for (1), and *denticity / polydentate connection
sites* for (2) — and that upstream frames (1) as symmetry-subgroup descent,
which is the same machinery this project already has in
`xtal/core/subgroups.py` (the 237-subgroup descent CLAUDE.md benchmarks on
MFU-4l). **Ask Julius whether he wants the literature survey finished before
Phase 1 is scheduled.**

---

## 6. Options

Format per `plan-feature`. `xtal/` imports no Qt; new capability through a
registry; every phase ends runnable and green.

### Defect (1): node orientation

#### Option A1 — per-slot permutations from outside the vendored tree **(recommended)**

`Builder.build(topology, bbs, permutations=...)` already accepts a
`{slot: permutation}` dict (`builder.py:162`, `:187`), routes it to
`locate_with_permutation` (`:254`), **and honours it again after the scaler
relaxation** (`:389-395`) and in the joint bonding (`:455`, `:465`). Our
`xtal/mof/build.py:338` calls `build_by_type`, which has no such parameter.
So the lever exists and is unused.

**This is proven working.** `09_prototype.py` supercells `pcu` to 2×2×2,
enumerates the permutations that tie at the minimum RMSD for each slot,
groups them by the resulting body orientation, and picks by vertex parity:

```
$ .venv/bin/python review/probes/pormake/09_prototype.py
minimum RMSD for this (slot, block): 0.164405
slot  0..28: 24 tied permutations, 8 distinct orientations   (each slot)
vertex parities: {0:0, 4:1, 8:1, 12:0, 16:1, 20:0, 24:0, 28:1}
chosen permutations: {0:[1,5,3,0,4,2], 4:[1,4,5,0,2,3], 8:[0,2,1,4,5,3], ...}

built framework, orientation of each node:
   node at frac [0.01 0.02 0.02]  ->  orientation class 0
   node at frac [0.01 0.01 0.51]  ->  orientation class 1
   node at frac [0.01 0.51 0.01]  ->  orientation class 1
   node at frac [0.01 0.52 0.52]  ->  orientation class 0
   node at frac [0.51 0.01 0.01]  ->  orientation class 1
   node at frac [0.51 0.02 0.52]  ->  orientation class 0
   node at frac [0.51 0.52 0.02]  ->  orientation class 0
   node at frac [0.51 0.51 0.51]  ->  orientation class 1
distinct orientations in the built framework: 2
```

That is MFU-4l's checkerboard, exactly (compare §1.3), **with no vendored
file touched**.

One subtlety a plan must carry: a permutation indexes into
`topology.local_structure(i).positions`, whose order is that slot's
`neighbor_list` order, which is **not** the same at every slot. A fixed tuple
does not mean a fixed orientation. The permutation must be **derived per slot
from the geometry**, as the prototype does.

- **Phase 1 — supercell a net and address its slots** (`xtal/mof/catalog.py`,
  `xtal/mof/build.py`). `Topology.expanded(nx, ny, nz)` beside
  `Topology.net`/`placement`; `Slot` gains a slot index; `BuildRequest` gains
  a `repeat` triple and spells it in `title()` (`pcu-2x2x2-N457`). No
  orientation logic yet — the build must come out identical to today's for
  `repeat = (1,1,1)`. Invariants kept: `xtal/` imports no Qt; one CIF per
  build (`ModuleRunner._file_build`). Tests, `tests/test_mof_builder.py`:
  `test_a_net_repeated_twice_has_eight_times_the_slots`,
  `test_a_build_in_a_repeated_cell_is_the_same_framework_repeated`,
  `test_a_repeat_of_one_is_spelled_the_way_it_always_was`. **Size: S.**
- **Phase 2 — the orientation set of a (slot, block) pair**
  (new `xtal/mof/orient.py`). `tied_permutations(topology, slot, block)`
  returning the permutations within a tolerance of the minimum RMSD, grouped
  by the body orientation they produce (`09_prototype.py` is the reference
  implementation; the 720-permutation sweep needs replacing by enumerating
  the target's proper-rotation stabiliser, which is 24 for an octahedron and
  48 for a cube — the sweep is fine for 6 connection points and is not for
  12). `orientation_classes(...)` returning the distinct classes. Headless,
  no Qt. Tests: `test_an_octahedral_vertex_admits_twenty_four_tied_fits`,
  `test_a_kuratowski_block_reaches_two_body_orientations`,
  `test_a_block_with_no_symmetry_has_one_orientation_only`,
  `test_every_tied_permutation_has_the_same_rmsd_to_six_places`.
  **Size: M.**
- **Phase 3 — a colouring rule, and pass it through**
  (`xtal/mof/orient.py`, `xtal/mof/build.py::_build`, `xtal/modules/mof.py`).
  `assign(topology, blocks, rule)` producing the `{slot: permutation}` dict;
  `_build` switches from `build_by_type` to `make_bbs_by_type` +
  `Builder().build(..., permutations=...)`. Rules: `"as-found"` (today's
  behaviour, the default — **nothing regresses**) and `"alternating"`
  (a proper two-colouring of the quotient graph, which for `pcu` is the
  parity and in general is a bipartiteness check; refuse with a sentence when
  the net is not bipartite). A `Param("orientation", ...)` on the MOF module
  with those two choices, so it reaches the CLI, the Help page and the
  dialog's generated form for free. Tests:
  `test_the_default_rule_builds_exactly_what_it_built_before`,
  `test_alternating_orientations_put_opposite_nodes_on_every_edge`,
  `test_a_net_that_is_not_bipartite_refuses_alternating_by_name`,
  `test_the_rule_is_spelled_into_the_frameworks_title`. **Size: M.**
- **Phase 4 — the MFU-4l recipe, end to end** (`resources/`,
  `tests/test_mof_builder.py`, marked `slow`). A Zn₅Cl₄(bta)₆ block written
  into the repo's block folder, `pcu` × 2, `orientation=alternating`; assert
  the built framework's SBU orientations alternate and that
  `rcsr.describe` still says `pcu`. **Size: M**, and it is the phase that
  will find whatever §4 has left.

**Trade-off.** Cheap, reversible, entirely ours, no vendored edit, and the
default path is untouched. It does **not** make the chemistry right — the
chlorides and the dioxin bridge are still missing (§2.1, §4.2) — so on its own
it produces a correct-*topology* MFU-4 analogue, not MFU-4l. It also costs an
8× larger build (8 nodes, 24 edges) with the `Scaler` optimising 8× the
variables; worth timing in Phase 1 before Phase 3 is scheduled.

#### Option A2 — a symmetry-lowered `.cgd`

Ship `pcu-b.cgd` (a hand-written `pcu` in *Fm-3m* or *Pn-3m* with **two**
`NODE` records at (¼,¼,¼) and (¾,¾,¾)). Then `n_node_types == 2`, the
existing `build_by_type` path takes `{0: block, 1: flipped_block}`, and
**not one line of Python changes anywhere.** This is upstream ROADMAP Item 3's
manual equivalent, and `tests/test_mof_builder.py:468`
(`test_a_net_with_two_node_types_builds_on_both`) already covers the machinery.

**Trade-off.** By far the smallest change and it exercises a path that is
already tested. But it needs a *pre-flipped* copy of the node block as a
second `.xyz` — the user must draw or generate it — and it solves exactly one
net at a time: a new `.cgd` per (net, alternation pattern). It also makes the
catalogue's net list disagree with RCSR, which the app's own net identifier
will then have opinions about (`check_net` would report `pcu` for a topology
the catalogue calls `pcu-b`, and `BuildOutcome.net_agrees` at
`build.py:249` would read `False` — a user-visible false alarm to handle).
**Size: S** for one net, **L** if generated systematically.

#### Option A3 — a consistency term in the fit

Add an inter-vertex objective: place vertex by vertex in BFS order, and at
each vertex choose among the tied orientations the one minimising a penalty
against already-placed neighbours (e.g. the §3.3 twist). This is the
general answer — it handles nets that are not bipartite and blocks whose
orientation set is larger than two.

**Trade-off.** It is the only option that is *right* rather than *told*, and
it is the only one that would extend to the polydentate case. It is also the
one that must live inside `Builder.build`, i.e. **a vendored edit**, and it is
a greedy heuristic on a problem that is genuinely a constraint satisfaction
(colouring). **Size: L.** Not recommended now.

### Defect (2): the single connection point

#### Option B1 — refuse honestly, and document the absorbed-linker recipe **(recommended)**

Do not change the model. Instead:
- `xtal/mof/block.py::problems()` gains a sentence naming the situation when
  a user marks two `X` on atoms that bond the same fragment: *"a connection
  point says one direction, so an attachment that bridges two atoms has to be
  written with the bridging group inside the block"* — pointing at `N457` as
  the worked example.
- `BuildOutcome.verdict()` (`build.py:253`) gains a check it does not have:
  it currently reports the net and the RMSD, and says nothing about whether
  the **cell came out with the symmetry the net has**. The §2.2 build
  produced 81.0/99.4/100.2° on a cubic net and called itself *"pcu, as
  asked"*. A line saying *"the relaxed cell is triclinic where `pcu` is
  cubic; the blocks do not fit this net"* would have made this whole
  investigation five minutes long. **This is the highest value-per-line item
  in the whole document.** `[important]`
- One paragraph in `docs/` on the recipe, with MFU-4l as the example of what
  it cannot reach.

Invariants kept, all of them: `CONNECTION_DISTANCE` untouched; *a connection
point is an `X` and there is no Unmark* untouched; *a dummy atom is a marker,
not chemistry* untouched; no vendored file edited.
Tests: `test_a_block_whose_markers_bridge_one_fragment_says_so`,
`test_a_cubic_net_that_relaxes_to_a_triclinic_cell_is_reported`,
`test_a_build_that_fits_leaves_the_verdict_it_always_left`. **Size: S.**

#### Option B2 — a connection *group*: several `X`, one attachment

Let a block declare that `X4 X5 X6` are one attachment. Concretely: a
`CONNECTION_GROUP` convention in the `.xyz` comment line (PORMAKE's own format
already puts connection indices there — `catalog.py:288` `_connections`),
`BuildingBlock` gaining a grouping, `LocalStructure` gaining a *representative*
direction per group plus the members' offsets, and `find_best_permutation`
matching **groups** rather than points. Then the RMSD objective sees the
21.24° fan, and defect (1) stops being degenerate for free (§4.3).

**Trade-off.** It is the fix that is actually correct and it dissolves both
defects. It also touches `local_structure.py`, `locator.py`,
`building_block.py`, `builder.py`'s `find_matched_atom_indices` closure and
the joint bonding — **five vendored files, in the algorithm's core**. It
breaks `block.problems()`'s "exactly one bond" rule, which CLAUDE.md does not
state as an invariant but `block.py:37`'s docstring defends explicitly. And
`tests/test_mof_vendored.py` compares whole builds against real upstream
PORMAKE by composition, RMSD and net — a changed `LocalStructure`
normalisation would need that recording (`tests/data/pormake_upstream.json`)
re-derived and the divergence explained. **Size: L**, and I would not
schedule it.

**On keeping a vendored change reviewable** (this applies to A3 and B2, and
is why I recommend neither): `PROVENANCE.md` is a list of *every* difference
from upstream 0.2.3, with the measurement that motivated each, and its rule is
explicit — *"Nothing else is reformatted… rewrapping somebody else's code to
our line length is how a vendored tree stops being diffable against the
version it came from"*, with the tree excluded from `ruff` in `pyproject.toml`
for that reason. A change of this size would need: its own `##` section in
`PROVENANCE.md` stating what upstream does, what we do, and the number that
justifies it (the existing `read_cgd` entry is the model — *"103 s down to
0.8 s… the same sites removed in every one of 417 nets"*); the upstream style
kept verbatim around it; and a test in `tests/test_mof_vendored.py` pinning
the new behaviour against a re-derived recording. Given §5.3 — upstream has
not moved on these files since 2020 — the *merge* risk is low; the
*reviewability* cost is what is high.

#### Option B3 — a "bridging" pseudo-atom the block writer inserts

Let the user mark a bridge, and have `write_building_block` emit a **single**
`X` at the centroid of the bridged atoms, at `CONNECTION_DISTANCE` along the
mean direction, recording the real members in a comment tag the *joint
bonding* step reads back (`build.py::bond_joints`, `:524`). PORMAKE sees one
point and is unchanged; the fan is restored after the build when bonds are
made.

**Trade-off.** No vendored edit, and it fixes the *chemistry* of the joint —
`bond_joints` would make all three Zn–N bonds instead of one. It does **not**
fix the geometry: the placement still cannot see the fan, so defect (1)
remains degenerate and the triazolate plane is still unconstrained. It is a
half-measure that will look like a fix and is not. For MFU-4l specifically it
would produce a structure with the right connectivity and 90°-wrong linker
planes. **Size: M.** Not recommended — but worth naming so nobody proposes it
as "the cheap version of B2".

### What I would do

**A1 phases 1–3, plus B1.** Together: the builder gains a real per-slot
orientation control with a tested default that changes nothing, MFU-4l's
alternation becomes expressible and is proven in a test, and — the part that
matters most day to day — a build that does not fit stops calling itself
*"pcu, as asked"*. **A1 Phase 4 and the Zn₅Cl₄ block should be scheduled only
after Julius says whether he wants MFU-4l reconstructed or only its
topology**, because §4.2 says the chemistry needs either a custom block folder
or B2, and B2 is a different order of work.

### Invariants a fix touches

| Invariant | A1 | A2 | B1 | B2 |
|---|---|---|---|---|
| `CONNECTION_DISTANCE = 0.75 Å` (`block.py:29`) | untouched | untouched | untouched | untouched (still one offset per point) |
| "a connection point is an `X` and there is no *Unmark*" | untouched | untouched | untouched | **grouping is new state an `X` would have to remember** — and an `X` "does not remember what it was" is the stated reason there is no Unmark. Needs Julius's ruling. |
| "a dummy atom is a marker, not chemistry" | untouched | untouched | untouched | untouched |
| `PROVENANCE.md` "do not reformat it" | **no vendored edit** | **no vendored edit** | none | five vendored files; see above |
| one batch per selection; edits via `Document.apply` | untouched (build returns a structure, does not edit one) | — | — | — |
| `block.problems()`'s "exactly one bond" | untouched | untouched | **wording added, rule kept** | **rule broken** |

### Verification

```bash
# the phase
.venv/bin/python -m pytest -q tests/test_mof_builder.py tests/test_block_writer.py \
    -o faulthandler_timeout=90
# the vendored comparison, which is the one that will notice an accident
.venv/bin/python -m pytest -q tests/test_mof_vendored.py -o faulthandler_timeout=90
# a person clicking it
XTAL_NO_CONFIRM_CLOSE=1 .venv/bin/python .claude/skills/run-app/drive.py \
    --scratch /tmp/xtal-mof --action module.mof.build --grab mof_build \
    --viewport-shot review/shots/mfu4l-build.png
```
The screenshot must show the Orientation row in the generated form, and the
built framework's Zn₅ clusters visibly alternating. The run log must carry
`Location at node slot N … RMSD` for **eight** slots, not one.

### Docs

Nothing in `docs/TODO.md` or `docs/ROADMAP.md` covers this today (checked:
the only `MFU` hit in TODO.md is line 138, about the pore surface). A1 would
add a ROADMAP phase table; B1's verdict change is a behaviour change worth a
line in CLAUDE.md's invariants — *"a build says whether the cell it relaxed to
still has the net's symmetry"* — because it is precisely the kind of silent
wrong answer the rest of that list exists to prevent.

---

## What I did not get to

- **The literature survey (§5.4).** ToBaCCo, AuToGraFS and whether MFU-4l is
  named anywhere as a hard case for automated construction. The agent had not
  returned. Everything in §5.1–5.3 is verified; §5.4 is not.
- **A Zn₅Cl₄(bta)₆ block.** I did not write one. Everything above uses the
  catalogue's chloride-free `N457`, so the numbers are for an MFU-4 analogue,
  not MFU-4l itself. The degeneracy argument (§3.2) is exact for the ideal Td
  block and does not depend on `N457`; the *counts* (8 orientations, 24 tied
  permutations) are `N457`'s and would be 2 and 24 for an ideal block.
- **Timing.** I did not measure what `Scaler.scale` costs on a 2×2×2 `pcu`
  (32 slots) against the 4-slot single cell. Phase 1 should, before Phase 3
  is committed to. The machine is under memory pressure
  (`sysctl vm.swapusage`), so any timing taken now would be suspect anyway.
- **The app's dialog.** I exercised `xtal/mof/build.py` headlessly and never
  opened `MofBuildDialog`. Whether a `repeat` spinner and an Orientation combo
  fit the 200 px dock/dialog budget is unchecked.
- **Whether `draw_net` and `bond_joints` survive a supercell build.** The
  prototype went through raw PORMAKE, not through `xtal.mof.build.build`, so
  `_representatives` and `_edges_of` (`build.py:647`, `:687`) are unexercised
  against a repeated topology. That is a Phase 1 risk.
- **`XTAL_NO_CONFIRM_CLOSE`/GUI run.** No screenshot was taken; the
  verification block above is a proposal, not a result.

## Probes

All under `review/probes/pormake/`, each dated in its first line. Nothing was
written into the tree; `git status` is clean.

| file | what it measures |
|---|---|
| `01_target.py` | space group, sites, coordination, fragments of `MFU4l.cif` |
| `02_net.py` | contracts SBUs and linkers, identifies the net as `pcu` |
| `03_flip.py` | the two node orientations and the checkerboard |
| `04_build.py` | `N457`'s connection geometry; a real `pcu` build and its outcome |
| `05_supercell.py` | node types and local structures on `pcu` × 2 |
| `06_orient.py` | the orientation of all eight placed nodes |
| `07_degeneracy.py` | the RMSD tie, four ways, to six places |
| `08_perm_lever.py` | all 720 permutations; 24 tie, reaching 8 orientations |
| `09_prototype.py` | **the working fix**: per-slot permutations, checkerboard out |
| `10_attachment.py` | 3 contacts per linker end, 21.24°, 2.189 Å |
| `11_multipoint.py` | the 0° vs 90° twist across one edge |
| `12_linker.py` | linker planarity; what the catalogue does and does not hold |
