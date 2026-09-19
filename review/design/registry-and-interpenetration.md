# Tier-2 registry additions, and the interpenetration design note

> **Written 2026-09-19** against `Crystal-Builder` at commit `3cd15e2`
> (v0.2.1), which is the base of branch `features/deep-review`. Note
> `origin/main` has since moved to `fb38d25`. Every line number,
> measurement and code reference below was true at `3cd15e2` —
> re-verify before acting on it if the file has changed.
>
> External sources (papers, package versions, licences) carry the date
> they were accessed. A licence or version claim goes stale silently;
> check it again before acting on it.

**Summary (5 lines).**

1. **Interpenetration detection is already written.** `Net.multiplicity()`
   (`xtal/analysis/topology.py:243`) is documented in the tree as "the
   interpenetration number", `Net.components()` splits catenated nets,
   `rcsr._shape` already prints "2-fold interpenetrated", and two tests
   pin it. What is missing is that it only runs on the net **the user
   drew**. Running it on the chemistry is ~25 lines and 1–57 ms on the
   nine samples (measured). **Detection S; generation L, and it does not
   belong in the MOF builder yet.**
2. **mmCIF is not a `FORMATS` entry**, because mmCIF files are `.cif` and
   `by_extension` dispatches on the suffix alone. It is a branch in
   `read_cif_all`, and gemmi — already a hard dependency — does all of
   it: an 8-line reader over the existing `_from_small_structure` reads
   cell, symmetry, occupancy and ADPs out of a PDBx file (probe below).
   **S.** POSCAR is a harder *registry* problem than a parsing one: VASP
   files have no extension at all.
3. **EQeq is the same linear solve the tree already does.** `qeq._solve`
   is already non-iterative and reusable verbatim; what changes is where
   `chi` and `J` come from and that the off-diagonal is Ewald-summed.
   The obstacle is not the maths, it is that the charge-source choice is
   written in **three** places that no test ties together.
4. **A shared `ASECalculatorEngine` is worth it: 141 of the 219 code
   lines in `xtal/ff/mace/calculator.py` are generic over any ASE
   calculator** (measured, probe below). It does not conflict with
   factoring finding 6 — that is about *external-binary* engines, a
   different base — but both should land as one `xtal/ff/api.py` pass.
5. **MOFid and a curated MOF set are both licence questions, not code
   questions** — and the nine CIFs already shipped have the problem
   first: three of them carry CCDC download headers and there is no
   `PROVENANCE.md` beside them, unlike the vendored PORMAKE.

Probes: `review/probes/registry/` — `interpenetration.py`,
`mmcif_via_gemmi.py`, `ase_engine_split.py`. Each carries a one-line
header saying when and against which commit it was written.
Nothing in the tree was modified; `git status` is clean.

---

# Part A — Interpenetration (idea 14)

> *"I am interested, but need more information on the implementation."*
> — Julius, PR #1

This is the one item where he asked for information rather than a
verdict, so it goes first and it is the longest section. The short
version: **you have already built the hard half and did not notice.**

## A.1 What the word means, and which one he wants

Three things get called the same thing and they are not the same
problem:

| | What it is | What it costs to detect |
|---|---|---|
| **Interpenetration (catenation)** | Two or more **independent** nets, not bonded to each other, that cannot be pulled apart — rings of one thread rings of another | Cheap: a component count plus a lattice index |
| **Self-penetration** | **One** net whose own shortest rings are threaded by its own edges | Expensive: needs ring perception, Hopf ring net |
| **Polycatenation / polythreading** | Lower-dimensional motifs (chains, sheets) entangled into a higher-dimensional array | Needs per-component periodicity rank, which you can get |

The standard report is *n*-fold interpenetration — the number of
independent identical nets in the crystal, written **Z** — plus, in
the Blatov/Proserpio classification (Baburin, Blatov, Carlucci, Ciani
& Proserpio, *J. Solid State Chem.* **178** (2005) 2452,
[doi:10.1016/j.jssc.2005.05.023]; the parameter list is on ToposPro's
own manual page, accessed 2026-09-19), a **class**:

| Class | The nets are related by | Z | PICVR |
|---|---|---|---|
| **I** | translations only (a non-lattice vector) | `Zt` | `Zt` |
| **II** | space-group symmetry operations only | `Zn` | **1** |
| **III** | both | `Zt × Zn` | `Zt` |

**PICVR** is the ratio of the primitive interpenetration cell's volume
to the crystal's, and it is the piece of that table this application
already computes — see A.6. Class II admits only Z ∈ {2, 3, 4, 6},
because a single symmetry element has to generate all the nets.

**Recommendation: report Z and the per-component periodicity. Do not
attempt the class, and do not attempt self-penetration.** The class
needs the relating operations found and named against the space group;
self-penetration needs ring perception and a Hopf ring net. Both are a
different and much larger piece of work, and neither is what a person
opening a CIF is asking.

## A.2 What is already in the tree — this is the finding

`xtal/analysis/topology.py` already carries every piece:

```
xtal/analysis/topology.py:204  Net.voltages()      the cycle lattice
xtal/analysis/topology.py:236  Net.periodicity()   "0, 1, 2 or 3 -- the rank of the net's own lattice"
xtal/analysis/topology.py:243  Net.multiplicity()  the saturation index
xtal/analysis/topology.py:255  Net.components()    connected pieces, renumbered
```

`multiplicity()`'s own docstring (`:250`) says what it is:

> "...which is 2 in that example, and **is the interpenetration number
> of a net described in a doubled cell**."

and `components()`'s (`:256`):

> "an **interpenetrated framework is two copies of one net** and saying
> so needs each of them named."

It goes further. `xtal/analysis/rcsr.py:758 _shape()` already
**prints** the answer:

```python
if multiplicity > 1:
    return f"{_fold(multiplicity)} interpenetrated, {shape}"
```

`NetReport.copies` (`rcsr.py:789`) sums it across components, and
`rcsr.describe` (`:912`) splits into components before identifying,
"because a framework that carries two interpenetrating nets is two
answers and not one". Two tests pin the behaviour:

- `tests/test_net_identification.py:258`
  `test_a_net_described_in_a_doubled_cell_is_not_two_nets`
- `tests/test_net_identification.py:268`
  `test_two_separate_nets_are_reported_separately` — which asserts
  `"2-fold interpenetrated pcu" in report.sentence()`

So **the Net panel already tells a user their framework is 2-fold
interpenetrated** — as long as they have drawn the net themselves,
edge by edge, in Draw net mode. That is the whole gap. The feature
Julius is asking for is "tell me without making me draw it".

## A.3 The algorithm, in ten lines

Yes, `fragments()` plus a periodic-image check is enough, and the
periodic-image check is already inside `fragments()`: the BFS at
`xtal/core/bonding.py:629` carries an integer `offsets` dict and
flags `periodic` when an edge closes onto a different image. What it
does **not** do is keep the closing vectors, so it cannot tell a 1-D
chain from a 3-D framework, and it cannot see the doubled-cell case
at all. `Net` can do both. So the glue is: hand each fragment's edges
to `Net` and ask it.

```
# review/probes/registry/interpenetration.py
graph = bonding.graph(structure)            # the chemical bond graph
for frag in graph.fragments():              # connected components, periodicity-aware
    index = {a: k for k, a in enumerate(frag.atoms)}
    edges = [Edge(index[b.i], index[b.j], b.image)
             for b in graph.bonds if b.i in index]
    if not edges:                           # a lone atom: a guest ion
        molecules += 1; continue
    net = Net(len(frag.atoms), tuple(edges))
    d = net.periodicity()                   # rank of the cycle lattice: 0/1/2/3
    if d == 3:   frameworks.append(net)     # a framework
    elif d == 0: molecules += 1             # solvent, a guest, a counter-ion
    else:        low_dimensional += 1       # a chain (1) or a sheet (2)
degree = sum(n.multiplicity() for n in frameworks)
```

Ten lines, no new mathematics, no new dependency. The
`multiplicity()` sum on the last line is the part a naive component
count gets wrong: a framework written in a doubled cell is **one**
component of the quotient graph and **two** frameworks in the
crystal.

### Measured, on the nine shipped samples

```
$ .venv/bin/python review/probes/registry/interpenetration.py
CFA1.cif             242 atoms  1-fold  nets=1 mult=[1] molecules=0   detect    3.1 ms
HKUST1.cif           624 atoms  1-fold  nets=1 mult=[1] molecules=0   detect    5.2 ms
MFU4l.cif            648 atoms  1-fold  nets=1 mult=[1] molecules=0   detect    5.6 ms
MIL53.cif            104 atoms  1-fold  nets=1 mult=[1] molecules=0   detect    0.9 ms
MOF-5.cif            424 atoms  1-fold  nets=1 mult=[1] molecules=0   detect    3.5 ms
Ni2Cl2BTDD.cif      1152 atoms  1-fold  nets=1 mult=[1] molecules=126 detect   56.5 ms
UIO66.cif            432 atoms  1-fold  nets=1 mult=[1] molecules=0   detect   10.5 ms
ZIF-8.cif            102 atoms  1-fold  nets=1 mult=[1] molecules=0   detect    1.0 ms
zn_oac.cif           210 atoms  1-fold  nets=1 mult=[1] molecules=0   detect    1.8 ms
```

Two things to read off that. **Ni2Cl2BTDD's 126 solvent molecules are
separated from the framework for free** — the periodicity rank does
it, and that is the same answer a user wants from "how much solvent is
in this pore". And **57 ms on 1152 atoms is the worst case in the
tree**, which is well inside what the Net panel's existing refresh
discipline already tolerates.

None of the nine is interpenetrated, so those rows only prove the
detector does not cry wolf. Three positive controls prove it fires
(same probe):

```
pcu in a doubled a axis:      components=1  periodicity=3  multiplicity=2   <- 2-fold, from ONE component
pcu in its own cell:          components=1  periodicity=3  multiplicity=1
MOF-5 framework, twice:       components=2  periodicity=[3, 3]  multiplicity=[1, 1]  -> degree 2
    same net?  Net.key refused: walking this net of 424 vertices did not finish; it is too large or too tangled to key
```

## A.4 What it cannot tell you, and say so in the UI

That last line is a result, not a probe bug, and it decides the
design. `Net.key` walks the graph and refuses 424 vertices. So on the
**atom** graph the app can count the frameworks and say how periodic
each is, and it **cannot** answer "are they the same net?" or "which
net is it?" — those need the simplified node-and-linker net, which is
exactly what `net_of`/the Net panel already read and what the user
draws. The two layers stay separate, and the property should say only
what its layer can prove.

The second honest limit is larger and is the one the literature
argues about. **A component count is not an entanglement test.** Two
3-periodic components in one cell could be:

- genuinely interpenetrated (rings threaded — the real case), or
- two frameworks that merely share a cell and could be pulled apart by
  a rigid translation (rare, but it is what "co-crystallised
  frameworks" means), or
- **one framework the bond perception split in half**, which on a real
  CIF is far more likely than either.

That third one is the important one here, because CLAUDE.md is
explicit that bonds are the user's: *"Bonds are recalculated only when
the user presses Recalculate Bonds."* A structure opened with no bonds
perceived has **n** components, one per atom, and an interpenetration
property computed over it would report nonsense with total confidence.

**So: the property is computed from the bond graph, is worded as a
statement about the bond graph, and says when there are no bonds.** Not
"this crystal is 1-fold"; "the bonds as drawn make one 3-periodic
framework".

The rigorous entanglement test is the **Hopf ring net** (Alexandrov,
Blatov & Proserpio, *Acta Cryst.* **A68** (2012) 484,
[doi:10.1107/S0108767312019034], accessed 2026-09-19): nodes are the
barycentres of catenating rings, edges are Hopf links found by
fan-triangulating each smallest ring and counting edge-surface
crossings with odd parity. It is what distinguishes interpenetration
from polycatenation and is the only thing that finds
**self**-penetration. It needs ring perception, and it is out of scope
— name it in the docstring as what the property does not do, rather
than half-do it.

Two cheap partial answers are worth having instead:

- **PICVR > 1 is already proof of entanglement in the translational
  case.** If the multiplicity is greater than one, the nets are
  translates of one another by a non-lattice vector and by
  construction occupy the same primitive cell — they cannot be pulled
  apart. So the doubled-cell branch of the algorithm needs no extra
  test at all; only the several-components branch does.
- **Identical topology is the definition, and is worth checking where
  it is affordable.** ToposPro requires all Z nets to have the same
  topology before calling it interpenetration, and MOFid warns (only
  warns) when its components have different formulas. On the atom
  graph, the cheap proxies are the atom count and the formula per
  component; the real check needs the simplified net.

### What the other tools do, and where this would sit

*(Accessed 2026-09-19.)*

| Tool | Components | Multiplicity / PICVR | Class | Entanglement |
|---|:-:|:-:|:-:|:-:|
| **ToposPro** (Blatov, *Cryst. Growth Des.* **14** (2014) 3576) | yes | yes | yes | yes (HRN) |
| **Systre / Gavrog** | yes (`connectedComponents`) | yes (`Component.multiplicity` = `basis.determinant()`) | no | no |
| **CrystalNets.jl** (*SciPost Chem.* **1**, 005 (2022)) | yes | yes (one entry per `vmap`) | no | no |
| **pymatgen `StructureGraph`** | dimensionality only (`get_structure_components`, Larsen 2019) | **no** | no | no |
| **MOFid** `.catN` | yes | **no** | no | no |
| **Zeo++ `-strinfo`** | yes, with dimensionality | no | no | no |
| **Crystal Builder today** | **yes** (`Net.components`) | **yes** (`Net.multiplicity`) | no | no |

Two things to read off that. **The app is already level with Systre
and CrystalNets.jl on the part that matters, and ahead of MOFid** —
MOFid's `catN` is literally `components − 1`
(`Deconstructor::CheckCatenation` calls `Separate()` and counts), so
it undercounts any structure written in a cell smaller than its
primitive interpenetration cell, which is exactly the case
`Net.multiplicity` was written to catch. `pymatgen` cannot do it at
all.

And **`Zeo++ -strinfo` is a free cross-check that this application can
already run.** Zeo++ is already an integrated `Program`
(`xtal/modules/zeopp.py`), and `-strinfo` identifies and counts the
framework components and their dimensionality. `_argv`
(`zeopp.py:225`) does not use it today. It needs the binary where the
in-tree route needs nothing, so it is not the implementation — but it
is a good way to validate the implementation against somebody else's
code on the first day, and a good candidate for a `@pytest.mark.slow`
test if a vendored binary is available.

## A.5 Where it goes: a property, not a `MODULES` entry

**A property shown in the panel.** Not a `MODULES` entry, for four
reasons drawn from the project's own rules:

1. `add-module`'s own table says `MODULES` is for "something that runs
   and leaves artefacts". This leaves nothing: one integer and a
   sentence. `writes_run_folder=False` exists, but a module that
   returns a one-row report and no folder is a dialog and a menu walk
   for a number that could just be on screen.
2. It costs 1–57 ms. Nobody should have to start a job for that.
3. The answer changes **only** when the bonds change, which is
   `Change.CHEMISTRY` — and `Document` already has the cache for
   exactly this shape:
   ```python
   # xtalapp/document.py:1198 — net_identification
   return self._structure.cached("net_identification",
                                 lambda: rcsr.describe(self.net()),
                                 invalidated_by=CHEMISTRY)
   ```
   A `Document.framework_report()` is the same three lines with a
   different lambda.
4. There is already a panel whose entire job is "what is the shape of
   this framework" — the Net panel (`xtalapp/docks/net.py`), which
   already refreshes on `CHEMISTRY` only and only while visible
   (`:121`, `:131`). That discipline exists because identification is
   expensive; this is cheaper and inherits it for free.

**Concretely.** Put the computation in `xtal/analysis/` (headless, no
Qt, testable) — the natural home is a new
`xtal/analysis/frameworks.py`, or `topology.py` beside `net_of`, since
it is the same `Net` type. Surface it in **two** places:

- **The Net panel**, above the existing "No net has been drawn"
  message. Today a user who has not drawn a net sees only `EMPTY`
  (`docks/net.py:43`). Replacing that dead end with "The bonds make
  one 3-periodic framework and 126 separate molecules. Draw a net to
  name it." is a strictly better empty state and is where somebody
  asking about interpenetration is already looking.
- **`StructureInfo`** (`xtal/core/properties.py:117`) — one more field
  and one more line in `text()`, which the Info dock renders with no
  changes of its own. Caveat: `properties.info()` is called on *every*
  structure change including a drag, and the detect cost is bonds-only
  work; so either it goes behind the same `cached(..., CHEMISTRY)`
  seam or it stays out of `StructureInfo`. **Prefer the Net panel
  only, for v1.** Adding it to `StructureInfo` is a second, smaller
  decision once the number is trusted.

## A.6 The number to show, and what a normal crystal gets

**Definition.** The *degree of interpenetration* is the number of
independent 3-periodic frameworks in one crystallographic cell:

```
degree = sum(net.multiplicity() for net in components if net.periodicity() == 3)
```

That is the standard *n*-fold: a 2-fold interpenetrated `dia` has
degree 2. It counts **both** ways a crystal can hold two frameworks —
two disconnected components, and one component whose cycle lattice is
an index-2 sublattice (the doubled-cell case). Reporting components
alone would miss the second; reporting multiplicity alone would miss
the first. The probe's last line sums both and is the whole
definition.

**This is not an approximation, and it lines up exactly with the
literature.** `multiplicity()` is the saturation index of the cycle
lattice; Gao, Wang, Guo & Sun (*npj Comput. Mater.* **6**, 143 (2020),
[doi:10.1038/s41524-020-00409-0], accessed 2026-09-19) give it as
`m = |det S̃|` for `S̃` the reduced basis of the cycle vectors, call it
the net's **multiplicity**, and identify it with Blatov's **PICVR**.
Systre computes the same number as `Component.multiplicity` and prints
it when the quotient graph is one component (`basis.determinant()` in
`PeriodicGraph.java`). Reading the class table above with that
identity: **the multiplicity recovers `Zt` exactly and cannot see
`Zn`** — a purely symmetry-related pair of nets (Class II) has
PICVR = 1 and shows up as two separate *components* instead. Summing
multiplicity over components therefore gets both halves and gives Z,
which is why the sum is the definition rather than either term.

**For a non-interpenetrated crystal the answer is 1, and the UI must
not print "1-fold interpenetrated".** That phrasing is wrong and
looks like a finding. The tree already gets this right and the
wording should be copied: `rcsr._shape` (`:758`) prepends the fold
**only** when `multiplicity > 1`, and otherwise says nothing about it.
So:

| Case | What the panel says |
|---|---|
| One framework | `one 3-periodic framework` |
| Two, same net | `2-fold interpenetrated` |
| Framework + solvent | `one 3-periodic framework, and 126 molecules` |
| Chains or sheets | `three 1-periodic chains` (polycatenation is not claimed) |
| No bonds perceived | `no bonds have been perceived; press Recalculate Bonds` |
| Only molecules | `no periodic framework: 4 molecules` |

## A.7 Generation, honestly

### What has actually been done

The 2016 method the earlier research found is an **AIChE Annual
Meeting 2016 talk (paper 436g)**, not a journal paper, and its journal
form is **Sezginel, Feng & Wilmer, "Discovery of hypothetical
hetero-interpenetrated MOFs with arbitrarily dissimilar topologies and
unit cell shapes", *CrystEngComm* **19** (2017) 4497**,
[doi:10.1039/C7CE00290D]. The code is **IPMOF**
(<https://github.com/kbsezginel/IPMOF>, Python 3.5). Its method,
which is the atom-by-atom collision check with an acceleration:

1. Build a **grid of Lennard-Jones insertion energies** (1 Å spacing
   for screening) over the passive framework's cell, with UFF or
   DREIDING parameters.
2. Enumerate poses of the active framework — the 24 ninety-degree
   rotations × a translation grid.
3. Sum trilinearly interpolated insertion energies over every atom of
   the active framework, with a 12 Å cutoff and a 50 Å replication
   cutoff for the multi-cell collision test.
4. Accept or reject on three thresholds: per-atom energy, per-structure
   energy, and energy **density** (so cells of different size compare).

18 structures out of a large screen; ~3.5 minutes per pair.
Concurrently, **Kwon, Park, Zhou & Kim, *Chem. Commun.* **53** (2017)
1953**, [doi:10.1039/C6CC08940B] screened a database for partners that
can hetero-interpenetrate a target. Experimental follow-up:
*Nature Chem.* (2023), [doi:10.1038/s41557-023-01277-z].

**Since 2016, essentially nothing has been added.** What exists:

- **hMOF's own trick**, the one behind MOFid's `cat1`/`cat2`/`cat3`:
  displace a copy of the framework along the **cell body diagonal** —
  `(½,½,½)` for 2-fold, `(⅓,⅓,⅓)+(⅔,⅔,⅔)` for 3-fold — then reject on
  overlap. That is Class Ia interpenetration with the FIV along [111],
  and it is *one guess*, not a search. It is what
  **GHP-MOFassemble** (*Commun. Chem.* **6** (2023) 222,
  [doi:10.1038/s42004-023-01090-2]) re-implemented for its generated
  MOFs in 2023, which is the most recent thing found.
- **ToBaCCo** does generate catenated frameworks, but only because its
  *template* CIF has more than one connected component
  (`ciftemplate2graph.py` sets `catenation = True` when
  `nx.connected_components` finds several, and `merge_catenated_cifs`
  recombines the builds). The ~3000 shipped RCSR templates are
  single-component, so out of the box it does not. It never invents an
  interpenetration vector.
- **PORMAKE — the library this application vendors — has no
  catenation code at all**, and would need an interpenetrated
  blueprint for the same reason.
- The rigorous route is **Baburin, *Acta Cryst.* **A72** (2016) 366**,
  [doi:10.1107/S2053273316002692] (preprint
  <https://arxiv.org/pdf/1805.01773>): enumerate index-*n* supergroups
  *G* ⊃ *H* subject to a site-symmetry condition, with the theorem
  that interpenetrating nets can never be related by a mirror, nor by
  any axis meeting a vertex or an edge. This *derives* the patterns
  rather than guessing translations, and nobody has implemented it in
  a tool a chemist can run.
- Modern generative MOF models (MOFDiff, MOFFlow, MOFGPT, LEGO-MOF)
  do **not** model interpenetration.

*(Sources accessed 2026-09-19.)*

### Why it is a different order of work

Generation is **much** harder than detection, and they are not the
same feature wearing two hats.

Detection is a graph question with an exact integer answer, over data
the app already holds. Generation is a **geometry** question with no
exact answer:

1. **Which offset?** Placing a second copy of a framework means
   choosing a translation (and possibly a rotation) that puts it in
   the voids of the first without any atom pair too close. The search
   space is continuous, the objective is a hard-sphere feasibility
   test, and there is generally either no solution or a continuum of
   them.
2. **Which nets can interpenetrate at all** is a property of the net,
   not of the structure: `dia`, `pcu`, `srs`, `ths` do; many do not.
   Deciding it in advance is a topology question the app cannot answer
   today (`Net.key` refuses anything atom-sized).
3. **The result is a hypothetical structure, not a measurement.** That
   is a different promise from anything else in the app. Every current
   builder (`net`, `build`, `mof`) makes something the user asked for
   by name; a generated interpenetrated framework is a *guess* that it
   is physically sensible, and MOF-5's own history — the IRMOF-9/-10
   pairs — is precisely that a framework interpenetrates or does not
   depending on synthesis conditions no geometric check sees.

**Does it belong in the MOF builder?** Not yet, and for a reason that
has nothing to do with interpenetration: `review/PRIORITIES.md` §1
records Julius's own verdict that the MOF builder *cannot build
MFU-4l* — flipped nodes on a `pcu` net, and an SBU that does not meet
its linker at a single point — and that fixing that "takes
precedence". Adding a second, harder geometry problem on top of a
builder that cannot yet build the application's own stress case is the
wrong order — and `review/design/pormake-mfu4l.md` (landed at
`d6d8b22`) shows item 1 is smaller than it looked, with a working
prototype that needs no change to vendored code, so the wait is short.
Revisit generation **after** item 1 lands, at which point the
connection-point model will have been rethought anyway and the answer
may be cheaper.

If it is ever picked up, the shape is a `MODULES` entry
(`kind="build"`, `needs_structure=True`, returns a `structure`), not a
force-field or analysis path: it makes a new crystal, which is exactly
what `xtal/modules/mof.py` and `xtal/modules/net.py` already are.

## A.8 Sizes

| Half | Size | Why |
|---|:-:|---|
| **Detection** | **S** | ~25 lines in `xtal/analysis/`, ~10 in `Document`, ~15 in the Net panel's empty state, plus a test file of ~10 sentences. Every hard piece exists and is tested. One day. |
| Detection, also in `StructureInfo` | S (+) | One field, one line, one caching decision. Do it second. |
| Blatov class / self-penetration | L | Needs the relating operation named, or ring perception and a Hopf ring net. Not recommended. |
| **Generation** | **L** | A continuous geometric search, a feasibility test, and a new promise about what the output *is*. Blocked behind PORMAKE item 1 regardless. |

**Recommendation to Julius: build detection, ship it in the Net panel,
and leave generation until the MOF builder can build MFU-4l.** The
detection half is a day and turns a feature the code already contains
into one a user can see.

---

# Part B — sizing the registry additions

## How a format, an engine and a module reach the UI today

Worth stating once, because it is what makes these sizes small and it
is also where each of them stops being small.

**A `FORMATS` entry touches one file.** `xtal/io/registry.py`'s own
docstring promises it: *"Adding a format is registering a `Format`.
Nothing else in the application learns about it."* Measured — every
consumer reads the registry rather than a list:

| Consumer | Where |
|---|---|
| Open dialog filters | `xtalapp/documents.py:195` `[f.filter_string() for f in FORMATS.readable()]` |
| Export dialog | `xtalapp/dialogs/export.py:98` `FORMATS.writable()` |
| Workspace file tree | `xtalapp/docks/filetree.py:38` `structure_globs()` |
| Fill-pores guest picker | `xtalapp/dialogs/fill_pores.py:159` |
| CLI `xtal formats` | `xtal/cli.py:490` |
| Drag-and-drop, Save, run filing | `document.py:316`, `module_runner.py:533`, `workspace.py:702` |

**An `ENGINES` entry touches five.** Measured by grepping everything
`mace` reaches outside its own package:

```
xtal/ff/__init__.py:22      from xtal.ff.mace.calculator import ...
xtalapp/layout.py:122       engines=["uff", "xtb", "mace"]      <- hand-written; a test pins it
pyproject.toml:107          mace = ["mace-torch>=0.3.14", "ase>=3.22"]
pyproject.toml:129          "xtal.ff.mace",                      <- setuptools packages list
```

plus the new `xtal/ff/<name>/{__init__,calculator}.py` and
`tests/test_<name>.py`. `tests/test_ff_ui.py:624`
`test_every_engine_that_is_registered_can_be_chosen` is what makes the
`layout.py` line non-optional, and it exists because MACE shipped
unreachable once.

---

## B.1 Formats via `FORMATS` (idea 7) — *"Yes we should add"*

**Exemplars.** `xtal/io/gen.py` (152 lines) is the one to copy — it is
"expand to P1, write a header, write the atoms, read it back", with
the P1 decision argued in the docstring. `tests/test_gen.py` (99
lines, 12 tests) and `tests/test_cssr.py` (138 lines, 15 tests) are
the test shape: sentence names, one test per thing the format could
get wrong, and one `test_the_registry_knows_the_extension`.

### B.1.1 mmCIF / PDBx — **S**, and gemmi removes nearly all of it

**gemmi is already a hard dependency** (`pyproject.toml:26`,
`"gemmi>=0.6"`; 0.7.5 in the review venv), and the CIF reader is
already built on it: `read_cif_all` (`xtal/io/cif_reader.py:88`) does
`gemmi.make_small_structure_from_block(block)` and hands the result to
`_from_small_structure(small, block, path)` (`:115`), which is the 40
lines that turn a gemmi `SmallStructure` into an `xtal` `Structure`.

gemmi reads mmCIF through a *different* door —
`make_structure_from_block` gives a macromolecular `Structure` — and
ships the bridge between them, `mx_to_sx_structure`. So the whole
reader is that bridge plus the existing 40 lines. Measured:

```
$ .venv/bin/python review/probes/registry/mmcif_via_gemmi.py
atoms       4
lattice     [10.0, 20.0, 30.0, 90.0, 90.0, 90.0]
space group SpaceGroup(P212121 #19)
elements    ['C', 'N', 'O']
labels      ['N', 'CA', 'C', 'O']
u_iso       [0.1393, 0.152, 0.1646, 0.1773]
meta        {'title': 'TEST', 'format': 'mmcif'}
writer      1025 chars
```

The reader in that probe is **eight lines**. Cell, space group,
element, label and isotropic ADP all survive; the writer is gemmi's
`Structure.make_mmcif_document()`, another three.

**How much work gemmi removes: essentially all of the parsing, and all
of the format's 60-odd relevant PDBx categories.** What is left is the
seam.

**The seam is the problem, not the parsing.** mmCIF files are named
`.cif`, and `FormatRegistry.by_extension` dispatches on
`Path(path).suffix.lower()` alone (`xtal/io/registry.py:70`). `.cif`
is already taken. Measured:

```
$ .venv/bin/python -c "from xtal.io import read_cif; read_cif('mm.cif')"
ValueError: no structure found in mm.cif
```

So **mmCIF is not a new `FORMATS` entry — it is a branch inside
`read_cif_all`/`read_cif_string`.** The test is one line, because the
two dialects use different tag spellings:

```python
has_core  = block.find_loop("_atom_site_label")     # already there, _declares_sites
has_pdbx  = block.find_loop("_atom_site.Cartn_x")   # the new one
```

**Files.** `xtal/io/cif_reader.py` (a `_from_mmcif_block` helper and
two call sites), `xtal/io/cif_writer.py` *or* nothing — see below.
No new module, no registry entry, no `pyproject` change, **no
packaging implication at all** (gemmi is already collected as an
ordinary import).

**`keeps`.** Do not change `cif`'s. Writing mmCIF is a separate
question from reading it and is much weaker value: an mmCIF written
from a small-molecule structure loses the bond loop this project's own
CIF carries (`_xtal_bond_*`), and gemmi's mx writer has nowhere to put
a marker, a net edge or a suppression. CLAUDE.md is explicit that
*"`xtal.io.export.for_export` is the one door out"* — so if mmCIF
writing ships it is an export-only `Format` named `mmcif` with
extensions `(".mmcif", ".pdbx")` and
`keeps=frozenset({"occupancy", "adp"})`, and **not** `symmetry`
unless somebody checks what gemmi writes for `_symmetry.*` on a
non-P1 cell. **Recommendation: read-only in v1.** Reading somebody
else's PDBx is the use case; writing one is not.

**Tests** (`tests/test_mmcif.py`):
- `test_an_mmcif_block_is_read_as_a_structure`
- `test_a_core_cif_is_still_read_by_the_core_path` (the regression
  that matters: the branch must not change any existing file)
- `test_the_cell_and_the_space_group_come_through`
- `test_the_isotropic_displacement_parameters_come_through`
- `test_a_file_with_neither_dialect_is_still_refused_by_name`
- `test_a_multi_model_mmcif_reads_the_first_model_and_says_so`

**Size: S.** Half a day. The largest single win in this list per hour
spent.

### B.1.2 POSCAR / CONTCAR — **S to write, M because of the registry**

Parsing is `gen.py` again: a comment line, a scale, three lattice
rows, a species line, a counts line, `Direct`/`Cartesian`, then the
coordinates. No dependency: **do not** take a dependency on pymatgen
or ase for this. Roughly 150 lines plus ~120 of tests.

**The registry is the cost.** VASP's files have no extension:

```
$ .venv/bin/python -c "from xtal.io import FORMATS; FORMATS.by_extension('POSCAR')"
ValueError: no format is registered for 'that file'
```

`Path('POSCAR').suffix` is `''`. Three consumers assume an extension —
`by_extension` (`registry.py:70`), `Format.filter_string`
(`registry.py:42`, which builds `*{ext}` globs) and
`filetree.structure_globs` (`docks/filetree.py:35`). So POSCAR forces a
`Format` change:

```python
#: Exact file names this format claims, for formats that have no
#: extension.  VASP writes POSCAR, CONTCAR, CHGCAR and XDATCAR.
filenames: tuple[str, ...] = ()
```

checked in `by_extension` **before** the suffix (`Path(path).name` in
`fmt.filenames`), added to `filter_string`'s globs, and added to
`structure_globs`. That is ~15 lines across `registry.py` and
`filetree.py` and one test —
`test_a_format_with_no_extension_is_found_by_its_file_name` — and it
is a change to shared code, which is why this is the one of the four
that is not purely additive. The alternative (register only `.vasp`
/ `.poscar`) makes the app unable to open a file called `POSCAR`,
which is what VASP users actually have.

**`keeps`: `frozenset()`.** POSCAR has no space group field, no
occupancies, no ADPs, no charges, no bonds. Written in P1 for the same
reason `gen.py` and `cssr.py` are, and the docstring should say so in
the same words. `CONTCAR` is the same format and is a second entry in
`filenames`, not a second `Format`.

**Tests** (`tests/test_poscar.py`, copying `test_gen.py`): the
whole-cell rule, direct vs cartesian, the scale line (a **negative**
scale means "this is the target volume", which is the one trap in the
format and is worth its own test), the species line being optional in
VASP 4 format (it is not — VASP 4 has counts and no names, and that is
either refused with a sentence or read with elements from the comment
line; pick refusal), and the by-name lookup.

**Size: S for the format, M for the pair** — the registry change is
the part that needs a decision.

### B.1.3 pymatgen `Structure` JSON — **S, and it needs no pymatgen**

pymatgen's `Structure.as_dict()` is plain JSON with a documented
shape: `@module`/`@class`, a `lattice.matrix`, and a `sites` list of
`{"species": [{"element": ..., "occu": ...}], "abc": [...], "label":
..., "properties": {...}}`. Reading and writing it is `json` and
nothing else — **no optional extra**, and importantly no 400 MB
dependency for a file format. `pymatgen` is in `bundle.EXCLUDES`
(`packaging/bundle.py`) precisely so it never comes back; a reader
that imported it would undo that.

**`keeps`: `frozenset({"occupancy", "charges"})`.** The species list
carries partial occupancy natively, which is more than CSSR, GEN or
XYZ manage. Charges ride in `site.properties["charge"]` by convention
— write them there and read them back. No symmetry (a pymatgen
`Structure` is P1 by construction; `SymmetrizedStructure` is a
different class and is out of scope), no ADPs, no bonds.

**Risks to write down in the docstring**, in this project's voice:
pymatgen's `abc` are fractional and its `xyz` are cartesian and both
may be present and may disagree after a round trip through somebody
else's code — take `abc`, and say why. And `@module`/`@class` should
be **written** so pymatgen's `MontyDecoder` accepts the file, and
**checked** on read with a sentence rather than assumed.

**Extension:** `.json` is far too generic to claim. Use
`(".pmg.json",)` — but note `Path("x.pmg.json").suffix` is `".json"`,
so this hits the same `by_extension` limitation as POSCAR and wants
the same `filenames`/suffix-chain fix. Simpler: `(".pmgjson",)`, or
accept `.json` with a content sniff in `read`. **This needs a decision
from Julius**; it is a naming choice, not an engineering one.

**Size: S** (~120 lines + ~100 of tests), conditional on the
extension decision.

### B.1.4 ASE `.traj` — **M, and it is not really a `FORMATS` entry**

This is the one of the four that does not fit the registry's shape.

**It needs the `ase` extra.** `.traj` is ASE's binary `ulm` container;
there is no reading it without `ase.io.trajectory`. `ase` is already
an optional extra (`pyproject.toml:73`) and is in practice always
present for the MOF builder, so the cost is the availability check,
not the dependency. But **`Format` has no `check`** — `Module` and
`Engine` both carry an `Availability`, and `Format` does not. A
registered format that raises `ImportError` on read is not how
anything else in this app handles a missing extra, so `.traj` either
adds an `available: Callable | None` field to `Format` (and the Open
dialog and file tree learn to skip or grey unavailable formats) or it
is registered conditionally at import, which is a different and worse
precedent.

**The deeper mismatch: a `.traj` is a trajectory, not a structure.**
The registry's own docstring already draws this line for `.xy`:
*"Every format in it reads and writes a structure, and `.xy` is a
diffraction pattern."* A trajectory is N structures, which `read_all`
covers — but the thing a user wants from a `.traj` is the transport
bar, and that is `xtal/io/trajectory.py`, which has **no registry of
its own**: `read_trajectory` (`trajectory.py:340`) is hard-wired to
extended XYZ (`path.read_text(...)` then `read_frames`). So `.traj`
support means both:

1. a `FORMATS` entry with `read_all` (so Open and the file tree see
   it), and
2. a dispatch in `read_trajectory`, called from
   `xtalapp/docks/trajectory.py:204`, plus the energies-per-frame
   mapping into `Frame.energy`.

**`keeps`: `frozenset({"charges"})`** — an ASE `Atoms` carries
`initial_charges` and nothing else on this list; no symmetry, no
occupancy, no ADPs, no bonds.

**Packaging:** `ase` is already collected (it is no longer in
`EXCLUDES`, and `bundle.py` records the 26 MB and what it buys), so
this adds nothing to the download. It is **not** in `xtalapp/extras.py`
`EXTRAS`, which lists only rdkit, rdeditor and matplotlib — if a
greyed-out `.traj` should explain itself on the Preferences ▸ Engines
page, `ase` gains an `Extra` row there too.

**Size: M.** The format is small; `Format.available` and the
trajectory dispatch are the work, and `Format.available` is a shared-code
decision.

### B.1.5 Formats: summary

| Format | Size | Dependency | Copies | Needs a decision? |
|---|:-:|---|---|---|
| mmCIF / PDBx (read) | **S** | none (gemmi is already required) | `cif_reader._from_small_structure` | write support: yes/no |
| mmCIF (write) | S | none | `cif_writer` | recommend: not in v1 |
| POSCAR / CONTCAR | S + M | none | `xtal/io/gen.py` | `Format.filenames` — yes |
| pymatgen JSON | S | none (**not** pymatgen) | `xtal/io/gen.py` + `json` | the extension — yes |
| ASE `.traj` | M | `ase` extra | `xtal/io/trajectory.py` | `Format.available` — yes |

---

## B.2 EQeq / EQeq+C (idea 6) — *"Yes we should add"*

*Sources for the method, all accessed 2026-09-19: Wilmer, Kim & Snurr,
J. Phys. Chem. Lett. 2012, 3, 2506, [doi:10.1021/jz3008485]; the
reference implementation at <https://github.com/lsmo-epfl/EQeq> (and
the deprecated <https://github.com/numat/EQeq>), both **GPL-2.0**;
Martin-Noble et al., J. Chem. Theory Comput. 2015, 11(7), 3364,
[doi:10.1021/acs.jctc.5b00037], whose method lives in its Supporting
Information scripts; and the 2338-MOF benchmark, Ongari et al., JCTC
2019, 15(1), 382, [doi:10.1021/acs.jctc.8b00669], open access at
<https://pmc.ncbi.nlm.nih.gov/articles/PMC6328974/>.*

### B.2.1 What is already there, and it is more than the brief assumed

Two corrections to the framing before the sizing.

**(1) The existing "QEq" is already a single non-iterative linear
solve, with the same shape EQeq needs.** `xtal/ff/uff/qeq.py` is 145
lines and `_solve` (`qeq.py:126`) builds an `n x n` system whose first
`n-1` rows say "these two atoms have equal electronegativity" and
whose last row is `sum q = total_charge`, then calls `np.linalg.solve`
once. The reference EQeq assembles the same system with the
constraint row **first** rather than last, and solves it once with a
hand-rolled dense solver. **`_solve` is reusable verbatim**, and the
app's version is already better in one respect: EQeq's C++ hardcodes
`Qtot = 0` with a comment saying it *could* be non-zero, whereas
`equilibrate(..., total_charge=)` is already a parameter here.

**(2) `xtal/ff/ewald.py` exists but `qeq.py` does not use it, and the
interface it exposes is not the one EQeq wants.**
`qeq._interaction_matrix` (`qeq.py:93`) sums a *shielded*
Ohno–Klopman integral over real-space images inside a 12 Å cutoff:

```python
contribution = COULOMB_EV / np.sqrt(r ** 2 + screening ** 2)
contribution[r > cutoff] = 0.0
```

`xtal/ff/ewald.py` (229 lines: `setup`, `energy_and_gradient`,
`madelung`) is the UFF electrostatics *term* — energies and gradients
for fixed charges. EQeq needs the Ewald-summed `1/r` kernel as an
`N x N` **matrix element**, with the real-space `erfc`, the reciprocal
sum, the self term and the background each contributing to `A[i][j]`
rather than to a scalar. `ewald.setup()` and `EwaldSetup` (the alpha
and k-vector choice) are directly reusable; `energy_and_gradient` is
not. A new `ewald.pair_matrix(positions, matrix, setup)` is the only
genuinely new numerics in this item — call it 60–90 lines.

Three details from the reference implementation that change what gets
written:

- **The off-diagonal is not bare `1/r`.** It is
  `lambda * (k/2) * (1/R + exp(-a^2 R^2) * (2a - a^2 R - 1/R))` with
  `k = 14.4 eV.A` and `a = sqrt(J_i J_j)/k` — an orbital-overlap
  correction that makes the kernel finite as `R -> 0`, which is what
  the app's `screening` term is doing by a different route. The
  diagonal is the bare hardness plus the atom's interaction with its
  own images.
- **The reference sums images over a cubic box, not a sphere**
  (`mR = 2` → 5×5×5 real cells, `mK = 2` → 5×5×5 reciprocal), and its
  own README lists spherical cutoffs and Ewald auto-tuning as *not
  implemented*. `ewald.setup(accuracy=)` here already does better;
  do not copy the cubic box.
- **It is `O(N^3)` in time and `O(N^2)` in memory** — a dense solve.
  `qeq.MAX_ATOMS = 2000` already exists for exactly this reason, with
  a docstring saying so, and the same limit applies unchanged.

### B.2.2 Parameters: 484 numbers, and they are NIST's, not the repo's

Measured by downloading and counting `ionizationdata.dat` from the
reference repository (accessed 2026-09-19, 6,058 bytes):

- **84 lines = 84 elements**, H (Z=1) through Po (Z=84). Nothing above
  Po: no Rn, no Fr, no Ra, no actinides.
- **12 tab-separated columns:** `Z`, symbol, a data-quality flag, the
  electron affinity, then IP₁…IP₈.
- **484 numeric values in total.** Per column: EA 71, IP₁ 84, IP₂ 77,
  IP₃ 62, IP₄ 48, IP₅ 43, IP₆ 37, IP₇ 33, IP₈ 29. Missing entries are
  `na`/`np`; the thirteen lanthanides Pr–Lu carry a literal `<0.5`
  placeholder for EA that the loader coerces to 0.5 eV.
- A **second, tiny file**, `chargecenters.dat`: **seven** integer
  oxidation states — `Mg 2, V 4, Co 2, Ni 2, Cu 2, Zn 2, Zr 4` —
  everything else defaulting to 0.

Compare `porosity.ZEO_RADII`: **111 entries, one number each**. So the
EQeq table is about 4.4× the size — still a file a person can check,
not a database.

**The licence question decides where the numbers come from, and the
answer is good.** The reference implementation is **GPL-2.0** (both
`numat/EQeq` and `lsmo-epfl/EQeq`; Open Babel's port too), and this
project is **MIT** (`pyproject.toml:9`). Copying that repository's
data file wholesale is the kind of thing that wants a lawyer. It does
not have to happen: the upstream README names its own sources, and
both are public reference compilations —

- **electron affinities:** Andersen et al., *J. Phys. Chem. Ref.
  Data* 1999, <https://doi.org/10.1063/1.556047>
- **ionisation potentials:** Moore, NSRDS-NBS 34, 1970,
  <https://nvlpubs.nist.gov/nistpubs/Legacy/NSRDS/nbsnsrds34.pdf>

so the table is **regenerable from NIST/JPCRD data, none of it
fitted**. That is a stronger position than `ZEO_RADII`, which had to
be transcribed out of a C++ source because it existed nowhere else.

**Recommendation:** build the table from the NIST sources, record that
in the module docstring the way `ZEO_RADII`'s provenance is recorded,
and keep a test that compares it against the published EQeq file *as a
cross-check of the transcription* — reading a GPL file in a test that
does not ship is a different thing from vendoring it, but if even that
is uncomfortable, pin the check to NIST's own numbers. **This is a
decision for Julius**, and it is the only licensing question in this
item.

**Packaging.** 484 numbers is package data, not a dict in a module.
`xtal/ff/charges/data/ionisation.json` with a line in
`[tool.setuptools.package-data]` **and** the matching line in
`packaging/bundle.py PACKAGE_DATA` — `tests/test_packaging.py:228`
`test_the_package_data_globs_still_match_pyproject` compares the two
literally, so a mismatch fails a test rather than shipping a build
whose charge method has no parameters.

### B.2.3 The other knobs

From the reference `main.cpp` (accessed 2026-09-19). Each becomes a
`Param` or a constant with a docstring; none is a preference.

| Knob | Default | What it is |
|---|---|---|
| `lambda` | 1.2 | dielectric screening on the Coulomb kernel (ε_eff ≈ 1.67) |
| `hI0` | −2.0 eV | hydrogen's zeroth ionisation potential, **overriding** the experimental EA of +0.754 eV |
| `chargePrecision` | 3 | decimals in the output, re-summed to neutrality after rounding |
| `method` | `"ewald"` | else `"nonperiodic"`, else direct lattice sums |
| `mR`, `mK` | 2, 2 | cubic image boxes — replace with `ewald.setup(accuracy=)` |
| `eta` | 50 | the Ewald splitting parameter, in an unusual convention |
| `k` | 14.4 eV·Å | `e²/4πε₀`; the app already has this as `qeq.COULOMB_EV = 14.399645` |

`hI0` is the interesting one and belongs in the docstring rather than
in the UI: **it is why EQeq needs no iteration at all.** Rappé and
Goddard's QEq iterates because hydrogen's Coulomb term is made
charge-dependent to stop runaway hydride formation; EQeq replaces that
with one global constant that disfavours H⁻ outright, and `lambda`
restores the stability that costs. `qeq.py`'s existing note — *"Hydrogen
has no charge-dependent hardness here, which is what keeps QEq's O–H
and C–H charges smaller than these"* — is about exactly this, and
EQeq is the principled answer to it.

### B.2.4 EQeq+C is cheaper than it sounds — it does not touch the solve

This is the finding that changes the size. Read from the paper's
Supporting Information scripts (`calculate_EQeq+C_charges_v3.5.py`,
ACS figshare collection, accessed 2026-09-19), not from the abstract:

**EQeq+C is a post-hoc additive charge shift.** EQeq runs first,
unmodified. Then:

```
q_k(+C) = q_k(EQeq) + sum over k' != k of  T[k,k'] * B[k,k']
T[k,k']  = D[Z_k] - D[Z_k']                       # a per-element parameter difference
B[k,k']  = exp( -alpha * (R[k,k'] - r_k - r_k') ) # Pauling bond-order / distance
```

with `r` the covalent radii and `R` summed over the 27 adjacent
images. It **does not change the diagonal hardness, the
electronegativity, or the linear system**; `T` is antisymmetric so
total charge is conserved exactly; and it needs **no bond graph, no
bond orders and no connectivity perception** — it is a smooth
distance-based sum over all pairs.

That matters here for one reason CLAUDE.md makes explicit: *"A force
field or optimiser never changes the bonding or the atoms."* A charge
correction that needed perceived bonds would be arguing with that
invariant. This one does not touch bonding at all.

**Extra parameters:** one `D_Z` per element (carbon fixed at 0 as the
reference), one global `alpha` in Å⁻¹, and covalent radii — which
`xtal/core/elements.py` already has from gemmi. The published ATMO set
is `alpha = 2.1` with six fitted elements (H, N, O, Se, Te, V). **The
MOF parameter set is in the paywalled main paper and I could not read
it**; the SI PDF is figures only and there is no GitHub repository
(the two Python 2 SI scripts are the whole reference implementation,
with no licence statement).

**So EQeq+C is ~40 lines on top of EQeq — and it is blocked on a table
nobody has published openly.** Either Julius has institutional access
to the JCTC paper and reads the MOF `D_Z` set out of it, or the
correction ships with the ATMO parameters and a warning that they were
not fitted to frameworks, which is worse than not shipping it.
**Decision needed.**

### B.2.5 Why it is worth doing anyway: the Cu result

The 2338-MOF benchmark (Ongari 2019, open access) gives the numbers to
quote in the panel's caveat and in the manual:

| EQeq variant | MAD vs DDEC (e) | structures failed |
|---|---:|---:|
| oxidation centres, experimental parameters | **0.131** | 46 |
| zero charge centre, experimental parameters | 0.144 | 119 |
| oxidation centres, def2 parameters | 0.148 | 30 |

and four failure modes that belong in the docstring because they are
this application's own subject matter:

1. **Copper is environment-insensitive.** With charge centre +2, every
   Cu in the 2338-MOF set comes out at **0.88 ± 0.06 e** — HKUST-1's
   paddlewheel included. This is precisely the pathology EQeq+C exists
   to fix.
2. **Alkali metals diverge** with a zero charge centre.
3. **F and Cl functional groups** are systematically overcharged.
4. **Perchlorates** are wrong regardless of parameters.

And EQeq+C's own measured gain, per the same review: **34–68 % lower
MAD on most of 12 MOFs — but 54 % worse on ZIF-8**, which the authors
put down to no ZIFs being in the training set. ZIF-8 is one of this
application's shipped samples. That asymmetry is exactly the kind of
thing `qeq.py`'s existing "there is always a caveat" discipline is
built for.

### B.2.6 How the user chooses — and the fault this exposes

The charge source is a `Param` choice on the UFF engine
(`xtal/ff/uff/calculator.py:644`):

```python
Param("charges", "Charges from", "choice", default="site",
      choices=(("site", "The sites"), ("qeq", "Equilibrate (QEq)"),
               ("zero", "All zero")),
      help="Only used when electrostatics are on."),
```

**That list is written in three places and no test ties them
together:**

| Where | What it says |
|---|---|
| `xtal/ff/uff/calculator.py:644` | the `Param` `choices` tuple |
| `xtalapp/docks/ff_panel.py:89` | `CHARGE_SOURCES`, a hand-built list |
| `xtal/cli.py:569` | `choices=["site", "qeq", "zero"]` |

```
$ grep -rn CHARGE_SOURCES --include='*.py' .
xtalapp/docks/ff_panel.py:89:CHARGE_SOURCES = [
xtalapp/docks/ff_panel.py:202:        for label, value in CHARGE_SOURCES:
```

Nothing else. This is `review/reports/factoring.md`'s central finding
— *"the same decision written down twice, and every pair I checked has
drifted"* — in a place that report did not check, and **adding EQeq is
what will expose it**: two new entries added in two of three places
gives a panel and a CLI that silently disagree about what the engine
accepts.

**So the answer to "a `Param` on the engine, or a preference?" is: a
`Param`, as now — and the work is to make the two copies read it.**
`CHARGE_SOURCES` becomes `OPTIONS["charges"].values_and_labels()`
(`xtal/params.py:81` already provides it), and the CLI's `choices=`
becomes the same call, with one test built as a partition the way
`test_every_engine_that_is_registered_can_be_chosen` is. **Do this
first, as its own commit, before adding any entry.**

Not a preference: a preference is a machine-wide default, and which
charge model a calculation used belongs to *that calculation's*
record — `xtal/ff/record.py` and `JobResult` are what carry it into a
run folder.

### B.2.7 A second door, and it is the more valuable one

`xtal/commands/ff.py:176 SetCharges` already exists — *"Write computed
charges onto the sites. Equilibrated charges are worth keeping"* — and
it is an undoable `Document` edit. EQeq exists in the literature
because RASPA users need framework charges, not because UFF needed a
better electrostatics term, so the entry point matters: **EQeq should
be reachable without turning UFF electrostatics on.**

One caveat found while checking that the charges would survive a save.
They will not, in the CIF:

```python
# xtal/io/cif_writer.py:307 _type_symbol
"""Only whole-number charges are written: a fractional charge is a
computed quantity (a QEq or Mulliken charge), not part of the
structure, and CIF has no honest place for it here."""
```

That is a deliberate decision and it is right about `_atom_site_type_symbol`.
But it means `cif`'s `keeps` set containing `"charges"`
(`xtal/io/__init__.py:59`) is **true only for integer oxidation
states**, and an EQeq charge written onto sites and saved is lost. If
computed charges are meant to survive, that needs either an
`_atom_site_charge` numeric column (which CIF does have, distinct from
the type symbol) or the project format. **Worth raising with Julius
separately — it is a pre-existing gap the export dialog currently
overstates.**

The honest shape is therefore a small `MODULES` entry
(`writes_run_folder=False`, returning a `Report` of one `Table` —
label, element, charge — and applying `SetCharges`), *plus* the engine
`Param`. Both call the same `xtal/ff/charges/eqeq.py`.

### B.2.8 Files, tests, size

**Add:** `xtal/ff/charges/{__init__,eqeq.py}`, `xtal/ff/charges/data/`
(the table), `ewald.pair_matrix`, optionally `xtal/modules/charges.py`.
**Change:** `xtal/ff/uff/calculator.py` (`_charges` at `:353`, two new
branches; the `Param` at `:644`), `xtalapp/docks/ff_panel.py:89`,
`xtal/cli.py:569`, `pyproject.toml` package-data,
`packaging/bundle.py PACKAGE_DATA`.
**Exemplar:** `xtal/ff/uff/qeq.py` for the solve and for the honesty
of its docstring; `xtal/analysis/porosity.py ZEO_RADII` +
`tests/test_porosity.py:335` for the transcribed table and its check.
**No optional extra, no new dependency, no GPL code** — numpy and
scipy do all of it, and the numbers come from NIST.

**Tests** (`tests/test_eqeq.py`):
- `test_the_charges_sum_to_the_total_charge_that_was_asked_for`
- `test_symmetry_equivalent_atoms_get_equal_charges` (on `halite` or
  `rutile` — the one that catches an Ewald sign error)
- `test_the_ewald_pair_matrix_agrees_with_a_direct_lattice_sum`
  (the check that must exist, in the same spirit as `ewald.madelung`,
  which is already there *"for checking the sum"*)
- `test_the_ionisation_table_matches_the_published_one`
- `test_hydrogen_uses_the_overriding_electron_affinity_not_the_measured_one`
- `test_an_element_above_polonium_is_a_sentence_not_a_crash`
  (the table stops at Z=84, and a structure with U or Th in it is not
  hypothetical in this field)
- `test_eqeq_plus_c_conserves_the_total_charge`
- `test_the_panel_and_the_cli_offer_what_the_engine_offers`

**Size: M, not S.** `review/PRIORITIES.md` sizes it S on the strength
of "the Ewald sum is already there". The solve is free, the table is
transcription from public data, and EQeq+C is 40 lines — but the Ewald
**pair matrix** is new numerics that must be checked against a direct
sum, and the three-copy choice list has to be fixed first or the entry
lands half-reachable. **Two to three days**, of which one is the
three-copy fix and that fix is worth doing on its own. EQeq+C is a
further **S**, blocked on the MOF parameter table.

## B.3 More ML potentials as `ENGINES` (idea 4) — *"Yes we should add"*

### B.3.1 Are they one engine or five?

**Measured.** `review/probes/registry/ase_engine_split.py` classifies
every function in `xtal/ff/mace/calculator.py` by reading it and
asking "would this line be identical for a different ASE-calculator
model?":

```
$ .venv/bin/python review/probes/registry/ase_engine_split.py
    12 lines  generic    installed
    27 lines  MACE-only  available
    17 lines  generic    _device
    45 lines  MACE-only  _load_model
    29 lines  generic    implements_stress
     5 lines  generic    forget_models
    18 lines  generic    MACECalculator.__init__
    21 lines  generic    MACECalculator._make_atoms
     2 lines  generic    MACECalculator.n_atoms
     6 lines  MACE-only  MACECalculator.summary
    32 lines  generic    MACECalculator.compute
     5 lines  generic    build

xtal/ff/mace/calculator.py: 472 lines total
  generic (any ASE calculator): 141
  MACE-only:                    78
```

**141 of 219 code lines — 64% — are "drive an ASE calculator", not
"drive MACE".** The 141 includes everything that can actually be got
wrong and that CLAUDE.md cares about: the eV→kcal/mol factor
(`KCAL_PER_EV`), the P1 atom ordering the optimiser maps forces back
through, the `scale_atoms=False` cell handling that makes the analytic
stress agree with `numeric_stress`, the model cache and its lock
(*"the Force Field panel runs on a worker thread"*), and the
`implements_stress` fallback. Every one of those is a bug each new
engine would otherwise re-introduce.

**What is genuinely per-engine** is 78 lines: `_load_model` (the
import and the constructor call), `available` (is the package there,
and will this model download or is the file missing), `summary` (one
sentence), and the module-level data — the model chooser, the licence
set, and the `Param` tuple.

**So: one shared base, and a thin module per engine.** Concretely, in
`xtal/ff/api.py` beside `Calculator`:

```python
class ASECalculator(Calculator):
    """A model that answers through an ASE calculator, over a P1 cell."""
    KCAL_PER_EV = 23.060547830619026
    def _load(self): raise NotImplementedError   # the one seam
```

with `_make_atoms`, `compute`, `n_atoms`, `numeric_stress` fallback
and the cache in the base, and `_load` as **the same seam the tests
already replace** — CLAUDE.md names it: *"`_load_model` is the seam
its tests replace"*. Keeping that name and that contract is what lets
`tests/test_mace.py`'s stand-in fixture become a shared
`conftest_ff.py` helper that every new engine's tests reuse.

Per-engine module then shrinks to roughly: a docstring, `MODEL_CHOICES`,
`OPTIONS`, `available`, `_load`, `summary`, `ENGINES.register(...)`.
Call it **80–120 lines**, against MACE's 472.

### B.3.2 Does it conflict with factoring finding 6?

**No — they are two different bases, and they should land together.**

`review/reports/factoring.md` §6 is about the **external-binary**
engines: xTB (540 lines) and DFTB+ (473) share 119 identical lines and
the same method names because both mean "write an input, launch a
binary, read forces back". Its proposed fix is an `ExternalCalculator`
base holding `n_atoms`, `summary`, the `calls`/`seconds` accounting,
the positions/matrix guard and `_Log`.

`ASECalculator` is the in-process sibling: "hand a geometry to a
Python object, read energy, forces and stress back". The two share the
*outer* layer only — `n_atoms`, `summary`, the calls/seconds
accounting, the positions/matrix guard — which is exactly the part
finding 6 also found duplicated **into MACE** (it names
`mace/calculator.py:360` as the third copy of the `__init__`
prologue).

So the clean shape is three levels, not two:

```
Calculator                (xtal/ff/api.py, exists)
  +-- _CalculatorBase     n_atoms, summary, calls/seconds, the guard, _Log   <- finding 6's "shared prologue"
        +-- ExternalCalculator   write input / launch / parse                 <- xtb, dftb
        +-- ASECalculator        Atoms once, move geometry under it           <- mace, orb, sevennet, ...
```

Finding 6 also names a live drift that this fixes for free: four
engines answer "which keyword arguments do I accept?" three different
ways (`{p.name for p in OPTIONS}` in dftb, `{f.name for f in
fields(...)}` in xtb and mace, and no filtering at all in uff, where
an unknown key is a `TypeError`). `Engine.coerce()` already exists at
`xtal/ff/registry.py:68` and nothing calls it; `Engine.__call__`
(`:71`) already centralises the one thing engines must not each decide
(holding markers back). **Making `__call__` coerce deletes the
filtering from three engines and is the single cheapest line in this
whole document.**

**Recommendation: do the base first, then add engines.** Adding five
engines onto today's shape means five more copies of the 141 generic
lines and five more chances to get the stress conversion wrong.

### B.3.3 Per engine

**The shape is identical for all of them**, and it is the shape the
`add-module` skill already describes:

1. `xtal/ff/<name>/{__init__.py,calculator.py}` — the docstring, the
   model chooser, `OPTIONS`, `available`, `_load`, the registration.
2. `xtal/ff/__init__.py` — one import line.
3. `xtalapp/layout.py:122` — add the name to
   `engines=["uff", "xtb", "mace", ...]`. **Non-optional**:
   `tests/test_ff_ui.py:624` asserts the registered set and the
   offered set are the same partition, and it exists because MACE
   shipped unreachable.
4. `pyproject.toml` — the extra, **and** the
   `[tool.setuptools] packages` list, which names every engine package
   individually (`"xtal.ff.uff", "xtal.ff.dftb", "xtal.ff.xtb",
   "xtal.ff.mace"`) because `xtal.ff` imports each calculator at
   import, so a wheel missing one cannot import `xtal.ff` at all.
5. `tests/test_<name>.py` — copy `tests/test_mace.py`.

**Packaging.** None of these should go in `COLLECT`
(`packaging/bundle.py:183`, currently `rdkit`, `rdeditor`,
`qdarktheme`, `matplotlib`). `mace` is not there either, and
`pyproject.toml`'s comment says why in terms that apply verbatim to
every torch-backed model: *"torch, which is gigabytes of wheel and
platform-specific about how it wants to arrive (CPU, CUDA, mps)"*. A
bundled build lists them and greys them out, exactly as it does MACE
and DFTB+. **There is no `importlib`-only reachability problem here**
— an engine is imported by name from `xtal/ff/__init__.py`, so
PyInstaller sees it; the invisible-to-PyInstaller trap the add-module
skill warns about is for **dialogs** named in
`xtalapp/dialogs/__init__.py` `_BY_NAME`, and an engine that ships a
custom dialog would hit it. None of these needs one: the generated
form from `OPTIONS` is enough (model, device, precision).

**Tests must not load a torch stack in the suite process.** The trick
is already written and is not optional — CLAUDE.md's "Aborted runs"
section is about exactly this, and `tests/test_mace.py`'s docstring
records the cost: *"227 shared libraries on top of the seven hundred
the rest of the suite has already loaded"*. Copy both halves:
`stand_in` (a cheap ASE calculator monkeypatched over `_load`, which
covers every arithmetic test) and `in_a_fresh_interpreter`
(`test_mace.py:47`, a `subprocess.run([sys.executable, "-c", ...])`
returning JSON) for the one test that must touch the real model — the
stress-versus-`numeric_stress` check, which `xtal/ff/xtb/calculator.py`
explains is the one claim that must never be taken on trust.

### B.3.4 The five engines, and what each costs

*All package facts accessed 2026-09-19; pin nothing on them without
re-checking, since these projects release monthly.*

| | ORB-v3 | SevenNet | UMA | eSEN-30M-OAM | MatterSim |
|---|---|---|---|---|---|
| pip | `orb-models` 0.7.0 | `sevenn` 0.13.0 | `fairchem-core` 2.22.0 | `fairchem-core[torch-extras]==1.10.0` | `mattersim` 1.2.5 |
| Python | **≥3.12** | ≥3.10 | ≥3.11,<3.15 | ≥3.9,<3.13 | **≥3.12** |
| torch | ≥2.8,<3.0 | not declared | **`~=2.13.0` hard pin** | **`==2.4.0`** | ≥2.2.0, no cap |
| torch-geometric | no | yes (pure-python) | no | **yes, compiled** (scatter/sparse/cluster) | yes |
| Weights | S3, auto, **no auth** | GitHub + in-wheel, auto | HF, **gated, manual approval + token** | HF, **gated**, manual download by path | GitHub raw, auto, **no auth** |
| Code licence | Apache-2.0 | MIT | MIT | MIT | MIT |
| **Weights licence** | **Apache-2.0** | **MIT** | FAIR Chemistry License v1 (bespoke; "commercial" not mentioned) | **OMat24 License — "research use"** | **MIT** |
| Stress | yes (conservative and direct) | yes | **task-dependent — see below** | yes | yes, always |
| CPU-only | yes | yes (its D3 variants are CUDA-only) | yes | yes | yes (its README advises CPU over MPS on Apple Silicon) |

**Yes, they are all ASE-calculator-shaped.** Every one exposes a
standard `ase.calculators.calculator.Calculator` with
`implemented_properties`, which is exactly what `MACECalculator`
already drives. The construction line differs and nothing else does:

```python
# ORB-v3  (>=0.6: the module MOVED and the loader now returns a pair)
from orb_models.forcefield import pretrained
from orb_models.forcefield.inference.calculator import ORBCalculator
model, adapter = pretrained.orb_v3_conservative_inf_omat(device="cpu",
                                                         precision="float32-high")
calc = ORBCalculator(model, atoms_adapter=adapter, device="cpu")

# SevenNet
from sevenn.calculator import SevenNetCalculator
calc = SevenNetCalculator(model="7net-omni", modal="mpa")   # modal= is REQUIRED for multi-fidelity

# UMA
from fairchem.core import pretrained_mlip, FAIRChemCalculator
calc = FAIRChemCalculator(pretrained_mlip.get_predict_unit("uma-s-1p2p1",
                                                           device="cpu"),
                          task_name="odac")                 # odac is the MOF task

# MatterSim
from mattersim.forcefield import MatterSimCalculator
calc = MatterSimCalculator(device="cpu")

# MACE-MP-MOF0 — no keyword; a file by path
from mace.calculators import MACECalculator
calc = MACECalculator(model_paths="mofs_v2.model", device="cpu",
                      default_dtype="float64")
```

**That is `_load` and nothing else**, which is what the 64% measurement
predicted. Five of these are 10–20 lines each behind a shared base.

**Four things that decide the plan.**

**(1) They cannot share one environment, and three of them cannot
share one with MACE.**

- `mace-torch` pins `e3nn==0.4.4`; `sevenn` needs `e3nn>=0.5.0`.
  **Mutually exclusive.**
- `fairchem-core` v2 pins `torch~=2.13.0`; eSEN-30M-OAM needs
  `fairchem-core==1.10.0` and `torch==2.4.0`, and **both install into
  the same `fairchem.core` namespace**. So UMA and eSEN-OAM are also
  mutually exclusive.
- `orb-models>=0.6` and `mattersim>=1.2.5` both require **Python
  3.12+**; fairchem v2 requires 3.11+. Python 3.12 is the only version
  where all current releases install at all — which is what the
  review venv already is (3.12, arm64).

  This does **not** break the registry — `ENGINES` entries are
  independent and each `check` is a `find_spec` — but it does mean
  `pyproject.toml` must never define a `[dev]`-style extra that
  installs more than one of them, and the extras' comments must say
  why, in the same voice as the existing `mace` comment. **A user
  installs one.** The engine list greying out four of five entries is
  the normal state and is exactly what the existing
  `Availability(False, "...pip install ...")` convention already
  renders.

**(2) UMA's stress is the trap, and it is the MOF task that has
it.** `FAIRChemCalculator` emits stress only for tasks trained with
stress labels. `odac` — the MOF task, and the only reason to reach for
UMA here — **was not**, so `get_stress()` raises unless you pass
`InferenceSettings(predict_untrained_stress={"odac"})`, and the
stresses you then get are autograd through a head never fitted to DFT
stress. `xtal/ff/xtb/calculator.py` already refuses to claim a stress
it has not checked, and CLAUDE.md records why. **UMA must ship with
`provides` **not** containing `"stress"`, or with a per-model claim
the way `mace.implements_stress` does it.** That existing function
generalises straight to this.

**(3) Licences differ and two of them are restrictive.** MACE already
sets the precedent — `ASL_MODELS` (`mace/calculator.py:127`) names the
non-MIT models in the combo label *before* the choice is made, because
*"MACE `print`s 'you accept the terms of the license' as it downloads,
which is a poor moment to find out, and this application is the thing
doing the downloading."* The same discipline applies here and is
stricter, because two of these are worse than ASL:

- **eSEN-30M-OAM's weights are "research use"** under Meta's OMat24
  License. Matbench Discovery labels them "Meta Research". The OMat24
  *dataset* is CC-BY-4.0 and that does **not** extend to the
  checkpoints.
- **UMA's weights are gated `manual`** on HuggingFace — a human
  approves the request, and the form asks for legal name, date of
  birth, country and affiliation. There is no way for this application
  to fetch them on a user's behalf, and it should not try: the entry
  greys out with "sign in to HuggingFace and request access at
  <https://huggingface.co/facebook/UMA>", which is the same shape as
  the DFTB+ Slater-Koster message.
- **ORB-v3, SevenNet and MatterSim are Apache-2.0 / MIT / MIT for code
  *and* weights, download without any account, and are therefore the
  three to do first.**

**(4) MACE-MP-MOF0 (idea 19, *"Sure"*) is not a `MODEL_CHOICES`
entry.** It is not in `mace_mp_urls`, has no keyword, and is loaded by
path from <https://github.com/ddmms/data/tree/main/mace-mof-0>
(`mofs_v2.model`, ~31 MB, **CC BY 4.0 with a mandatory citation**).
The existing `CUSTOM` / `model_path` branch already handles it
(`mace/calculator.py:154 available()` checks the file is there), so
"support" is a **documentation** change plus, at most, a named entry
that fills `model_path` from a download. `review/PRIORITIES.md` sizes
it S; that is right, and most of the S is the download-and-cite
question, not code.

### B.3.5 Which models, and the evidence for choosing them

The benchmark that should drive the order is **MOFSimBench** (Kraß,
Huang, Moosavi) — arXiv:2507.11806 (16 Jul 2025), published as *npj
Comput. Mater.* 2026, 12:4, <https://doi.org/10.1038/s41524-025-01872-3>;
repo <https://github.com/AI4ChemS/mofsim-bench>. Accessed 2026-09-19.

**The 89% / 62% claim in `review/PRIORITIES.md` is verified against
the preprint**, which says in terms that the best models achieve 89%
against UFF4MOF's 62%. **Read the metric before quoting it**: it is
Figure 3b of the *structural optimisation* task — the percentage of
100 structures that both completed an atom+cell relaxation **and**
landed within ±10% of the DFT cell volume. It is not "volume accuracy"
in general, and it folds two failure modes (a crash or an unsupported
element, and a >10% volume error) into one number. *Caveat: the
published npj version is reported to revise these to 94% / 66%; I have
not been able to read the published version behind its paywall, so
**quote the preprint's 89/62 or check the npj figure yourself** —
do not cite 94/66 on this document's authority.*

Rankings, from the preprint:

- **Overall best: eSEN-30M-OAM**, with **orb-v3-conservative-inf-omat**
  a close second and **MatterSim-v1-5M** consistently top three.
- Optimisation: eSEN-OAM and orb-v3-omat tied at 89%; **orb-d3-v2
  worst at 39%**; the non-conservative models failed to converge in
  5000 steps for 85–96% of structures. The paper's reading —
  conservative force formulations give a smoother PES — is a useful
  thing to put in the engine descriptions.
- Bulk modulus MAE: eSEN-OAM 2.60 GPa < MACE-MP-MOF0 3.16 <
  GRACE-2L-OMAT 3.23; heat capacity MAE: orb-v3-omat 0.018 J/K/g best.
- **MACE-MP-MOF0 is not the winner on MOFs.** It has a low outlier
  rate but **28 of the 100 structures are unsupported** for lack of
  elemental coverage, and the general models beat it on the subset
  where it is defined. That is worth saying out loud, because
  `PRIORITIES.md` §19 already flags a tension between ideas 4 and 19
  and this resolves it: **the general uMLIPs win; MOF0 is the
  phonon/QHA specialist.**
- **UMA is not in MOFSimBench at all** — which, given `odac` is UMA's
  own MOF task, is a genuine gap rather than an omission to read past.
- **Every model was benchmarked with a consistent D3 correction**
  (ASE `SumCalculator` + `TorchDFTD3Calculator(xc="pbe",
  damping="bj")`) where it had none built in. So the numbers above are
  for *model + D3*, not bare models. If this application ships these
  engines without the same dispersion treatment, it will not reproduce
  them — and `torch-dftd` is then a further dependency. **Decision
  needed: does an `ENGINES` entry own its dispersion correction?**
  MACE's `mace_mp(dispersion=True)` already raises the same question
  and the tree currently answers it by not exposing the option.

**Recommended order**, on licence cleanliness first and benchmark
second:

1. **ORB-v3** — best-ranked of the permissively licensed ones,
   Apache-2.0 weights, no account, stress in both variants.
2. **MatterSim** — MIT throughout, no account, always gives stress,
   and it wins the MOFSimBench host-guest task outright (it beats
   both the fine-tuned MACE-DAC-1 and UFF+DDEC on CO₂/H₂O interaction
   energies), which is the task closest to what this application's
   users do next.
3. **SevenNet** — MIT, no account, but **cannot share an environment
   with MACE** (`e3nn`), so its extra's comment has to say so.
4. **UMA** — after the others, because of the gate and the `odac`
   stress hole.
5. **eSEN-30M-OAM** — best on the benchmark, **and research-use-only
   weights on a pinned `torch==2.4.0` and compiled PyG extensions.**
   Hardest to install, most restrictive licence. Last, if at all.

### B.3.6 Sizes

| Piece | Size | Note |
|---|:-:|---|
| `ASECalculator` base in `xtal/ff/api.py` | **M** | ~150 lines moved, not written; `mace/calculator.py` shrinks to ~150; `tests/test_mace.py` must stay green unchanged, which is the check that the move was a move |
| `Engine.__call__` calls `self.coerce()` | **S** | deletes three copies of option filtering (factoring §6); one line plus three deletions |
| `ExternalCalculator` base (factoring §6) | **M** | xTB + DFTB+; do it in the same pass as the above |
| **Each engine, after the base** | **S** | ~100 lines + `xtal/ff/__init__.py` + `layout.py` + two `pyproject.toml` lines + a test file copied from `test_mace.py` |
| Each engine, on today's shape | **M** | ~350 lines, of which 141 are a copy of code that already exists twice |
| MACE-MP-MOF0 | **S** | documentation and a named entry over the existing `CUSTOM` path |

**So: one M for the base, then five S.** Doing it the other way round
is five M's and five chances to get the stress conversion wrong.


---

## B.4 MOFid / MOFkey (idea 13) and a curated MOF set (idea 12)

> **13.** *"Yes"*
> **12.** *"Depends on licensing and the size of databases. A small
> database of curated MOFs could also be useful. MOF-#, NU-#, HKUST-#,
> etc."*

He is right that this is a licensing question. It is **also** a
licensing question about the nine files already in the tree, and that
is where to start.

### B.4.1 MOFid: it is not a library, and the shape that works is not the obvious one

*(All verified 2026-09-19 against <https://github.com/snurr-group/mofid>
and the PyPI/GitHub APIs.)*

**`pip install mofid` does not work — there is no `mofid` on PyPI.**
`https://pypi.org/pypi/mofid/json` is a 404, as are `mofid-python`,
`pymofid`, `mofkey`. There is no conda-forge feedstock. The repo's
`setup.py` (`version='1.1.0'`, `license='GNU'`) packages only the
`Python/` directory, and the documented install is `make init` (which
**builds a vendored full copy of Open Babel with CMake**, C++17,
GCC 11 recommended), then `python set_paths.py`, then `pip install .`.

**Worse for a desktop application: the install is not relocatable.**
`set_paths.py` writes a generated `Python/paths.py` holding **absolute
paths** of the build tree, and the Python layer then shells out to
`os.path.join(openbabel_path, 'build', 'bin', 'obabel')`. The issue
"Remove `set_paths.py` requirement" has been open since 2019. There is
no way to ship that in a PyInstaller bundle.

Two premises worth correcting:

- **The patched Open Babel is history.** MOFid 1.0 (2019) did vendor a
  patched OB 2.4.90 — it *added* the `-xg` CIF bond-writing option.
  That patch was **upstreamed**: OB 3.1.1 contains it, and a
  blob-level diff of MOFid's vendored tree against upstream 3.1.1
  finds only four differing files, none of them chemistry
  (`obutil.h` gains `#include <ctime>` for GCC 12; the rest are test
  and data files). `cifformat.cpp`, `mol.cpp`, `bond.cpp`,
  `kekulize.cpp` are byte-identical. **The source no longer needs a
  fork; the build system still insists on its own in-tree build**,
  because `sbu.cpp` `setenv`s `BABEL_DATADIR`/`BABEL_LIBDIR` at
  compile-baked paths.
- **Java is required, and the jar ships.** `Python/id_constructor.py`
  asserts `java` is on PATH at import, and invokes
  `Resources/Systre-experimental-20.8.0.jar` (1,651,077 bytes, the
  upstream Gavrog release) with a 30-second timeout "because it hangs
  on certain CGD files", against a 2.3 MB `RCSRnets.arc`.

**Licences:** MOFid **GPL-2.0**; the Open Babel it vendors
**GPL-2.0-only** (no "or later"); Systre/Gavrog **Apache-2.0**;
`RCSRnets.arc` has **no stated licence**. Crystal Builder is **MIT**.
So linking any of it in is out; invoking `sbu` as a separate process
is the arm's-length route people use, and it is a judgement call
rather than a settled one.

**Is that acceptable here? No — but there is a route that is.** The
project already has a precedent for exactly this shape and it is a
good one: **`Export Net for Systre...`** (`xtalapp/menus.py:128`) does
not run Systre. It writes a `.cgd` and tells the user to run Systre on
it, "a second opinion on the Net panel". Nothing Java, nothing GPL,
nothing bundled. MOFid gets the same answer by default.

But there is a better option than the default, and it is the finding:

**MOFid has an Emscripten/WASM build that needs no Java and no
compiler.** <https://snurr-group.github.io/web-mofid/> runs the whole
thing client-side, **replacing Java Systre with webGavrog (JS)**.
Contents: `sbu.wasm` 4.41 MB, `sbu.data` 9.21 MB (the preloaded OB
data directory plus `RCSRnets.arc`), `sbu.js` 0.23 MB,
`webGavrog/main.js` 0.41 MB — **≈14 MB for a complete, self-contained
MOFid engine**, with `_analyzeMOFc` as the exported entry point.

The catches are real and should be stated: the `web-mofid` repository
has **no LICENSE file** (so it inherits GPL-2 from MOFid by
derivation, unstated), was last pushed **2021-09-01**, and there is an
open upstream issue "Inconsistent output between local mofid and
webmofid". Running WASM would also mean QtWebEngine, which this
application deliberately excludes (`packaging/bundle.py EXCLUDES`
lists `PySide6.QtWebEngineCore` and four siblings, and the comment
says *"The application uses exactly four Qt modules"*). So it is not
free either — but a 14 MB WASM blob with no Java is a far more
plausible thing to ship than a CMake build of Open Babel, and it is
worth knowing exists.

**What `catN` actually is, since the app's own answer is better.**
`Deconstructor::CheckCatenation()` calls `Separate()` on the
simplified net and returns the component count; Python then does
`cat = str(int(line[8]) - 1)`. That is: `catN` where `N = components −
1`, with **no multiplicity term**, and a single-character parse that
misreads any structure with ten or more nets. Systre is used only for
the *topology symbol*, not for the count. Section A.6 of this document
describes a number that is strictly better on the same input.

**Recommendation.** Do **not** integrate MOFid. Do two things instead:

1. **MOFkey-shaped identification, ours.** A MOFkey is
   `<metals>.<InChIKey skeleton per linker>.MOFkey-v1.<topology>` —
   metals sorted by atomic number, the first 14 characters of each
   linker's InChIKey, sorted. The app already has the two hard pieces:
   `graph.fragments()` gives the linkers and
   `rcsr.describe(document.net())` gives the topology. The missing
   piece is InChIKey, which is **RDKit**, already an optional extra
   (`build`). That is a real S-sized feature that gives Julius what he
   wants from idea 13 — "naming and dedup" — without GPL, Java, or a
   14 MB blob.
2. **Deduplication does not need MOFid at all.** CLAUDE.md already
   records that *"`add_structure` de-duplicates by content, never by
   name"* with `filecmp.cmp(..., shallow=False)`. A structural hash
   would be a genuine improvement over a byte comparison, and the
   existing `Net.key()` canonical form is one — for the net. For the
   whole structure, `mofchecker`'s structure-graph hash is the
   published idea and it is MIT.

**Size: S** for a MOFkey-shaped identifier over what already exists;
**L and not recommended** for MOFid itself.

### B.4.2 The curated set: the licence problem starts at home

**What is in `resources/samples/` today — nine files, 164 KB, and no
provenance file at all.**

```
$ for f in resources/samples/*.cif; do ...; done
CFA1.cif                36204 raw    9827 gz
HKUST1.cif               4489 raw    1209 gz
MFU4l.cif               19763 raw    5430 gz
MIL53.cif                1933 raw     806 gz
MOF-5.cif               34813 raw    2751 gz
Ni2Cl2BTDD.cif           4570 raw    1955 gz
UIO66.cif               25259 raw    2421 gz
ZIF-8.cif                7348 raw    1866 gz
zn_oac.cif              33851 raw    8268 gz
                       168230 raw   32823 gz (as one stream)
```

`packaging/bundle.py RESOURCES` records the budget as
*"File > Open Sample, and what --selftest opens. 164 KB"* — accurate
to the byte. There is **no size test**:
`tests/test_packaging.py:246 test_nothing_enormous_is_collected_by_accident`
asserts only that the four `OMITTED` folders do not ship.

Three things fall out of reading those files.

**(1) Three of the nine carry CCDC headers.** Measured:

```
$ grep -il "licen|copyright|CCDC|deposit" resources/samples/*.cif
resources/samples/Ni2Cl2BTDD.cif
resources/samples/MFU4l.cif
resources/samples/zn_oac.cif
```

`MFU4l.cif` contains `_database_code_depnum_ccdc_archive 'CCDC 776578'`
and the line *"2010-05-10 deposited with the CCDC. 2025-02-04
downloaded from the CCDC."*; `Ni2Cl2BTDD.cif` has
`_database_code_CSD POSWUS` and `_audit_creation_method CSD-ConQuest-V1`;
`zn_oac.cif` has `_ccdc_geom_bond_type`. Three more
(`MOF-5`, `UIO66`, `HKUST1`) are `_audit_creation_method RASPA-1.0`,
i.e. from the RASPA distribution, itself CSD-derived.

CCDC's own support article *"Can I redistribute data from the CSD?"*
says the licence *"does not allow external sharing of original data
from the CSD, such as making bulk CIF files available to others
outside your organization"*, and — checked — **states no threshold for
a small number of structures**. There is no documented safe harbour.
`MFU4l.cif` is the application's own stress case and is in the
shipped bundle and in the signed macOS download.

**This is not a reason to panic and it is a reason to act**: the
project already has the right machinery for it one directory over.
`xtal/mof/pormake/PROVENANCE.md` exists because vendored code needs
its origin and its licence recorded, and
`tests/test_packaging.py:164
test_the_vendored_licence_and_provenance_are_collected` makes sure it
travels. **`resources/samples/PROVENANCE.md` is the same file for the
same reason and it is missing.** Writing it forces the question per
file, which is the useful part.

**(2) Two of the nine files ship but are not in the menu.**
`xtalapp/samples.py SAMPLES` has **seven** entries; the folder has
nine files; `bundle.project_datas()` iterates the folder, so
`MIL53.cif` and `UIO66.cif` are in every download and reachable from
nowhere. `MIL53.cif` is interesting: its
`_audit_creation_method` is `'Crystal Builder 0.1.1.dev10+g72879303e'`
— **the application built it**, so it is the one sample whose
provenance is unambiguously the project's own. And UiO-66 is on
Julius's own list of what a curated set should contain. **Adding two
`Sample` entries is a five-line change and grows the set by 22% for
nothing.**

**(3) The size question is settled and it is not the constraint.**
Measured: nine real MOF CIFs are 164 KB raw, 32 KB gzipped, averaging
18.7 KB each. Scaling: **50 curated P1 CIFs is roughly 1–2.5 MB raw
and 200–400 KB gzipped**; symmetry-reduced rather than P1 is 5–25×
smaller again (MIL-47 is 1.7 KB in its own space group and 8.7 KB
expanded). Against the vendored PORMAKE database already in the
wheel — **3271 files and 2.8 MB, about 13 MB installed** — 50 CIFs is
noise. **Optimise for provenance, not for bytes**, and ship them in
the bundle rather than downloading: a download needs a server, a URL
that stays up, and a first-run network call, all of which this
application has carefully avoided everywhere else.

### B.4.3 Where clean CIFs come from — see the sibling document

**Another reviewer has answered this half properly and in more depth
than I did**, and where we disagree they are right. See
**`review/design/mof-database-licensing.md`** (committed at `d6d8b22`,
after this document was begun). Its conclusions, which supersede my
own sourcing notes:

- **Source from COD (CC0), and regenerate what COD lacks**,
  RASPA2-style with an `_audit_creation_method` and a `_citation_*`
  block. RASPA2 is MIT and ships 108 such files; that is the community
  norm and it is the legally right shape.
- **All six headline MOFs are in COD** — MOF-5 1516287, HKUST-1
  4002052, ZIF-8 7249359, UiO-66 4512072, MIL-101(Cr) 4000663,
  NU-1000 7230579, each downloaded and parsed with gemmi. **This
  corrects my own note above**: my search found no COD entry for
  NU-1000 or MIL-101 and concluded COD's coverage was patchy. It is
  not; I looked badly.
- **CoRE MOF 2019 should be avoided**, not preferred: 94.2 % of its
  files are refcode-named and therefore CSD-derived, which makes its
  CC BY tag doubtful. CoRE MOF **2025**'s SI subset (99.8 %
  journal-SI-derived) is the legitimate CC BY fallback.
- **Ship a `DATA_LICENSES` / provenance file** naming each structure's
  source, COD ID, citation and licence.

Two things from my own reading that are worth carrying across as
cautions rather than corrections:

- **COD's public-domain dedication is not on every file.** COD
  4118891 (ZIF-8) and 4340010 carry *"All data on this site have been
  placed in the public domain by the contributors."* COD **2300380**,
  an IUCr-sourced HKUST-1 entry, carries instead *"The file may be
  used within the scientific community so long as proper attribution
  is given to the journal article"* — a use restriction, not CC0.
  Neither document's recommended entry is that one, but the lesson
  holds: **read the header of every file you take**, rather than
  relying on the site-level claim.
- **Raw COD downloads carry refinement data.** COD 2300380 is
  **1,019,557 bytes** because it embeds a full powder profile; the
  sibling document measures the same effect on UiO-66 (286 KB) and
  NU-1000 (301 KB) from `_refln` loops. Stripping to cell + symmetry +
  `_atom_site` removes ~99.7 % of it. Curating means stripping.

The two documents agree on the size answer, from independent
measurements: **~30 structures is 200–700 KB raw and 50–150 KB
gzipped** (theirs, on stripped COD files) against my ~1–2.5 MB raw /
200–400 KB gzipped (on unstripped P1 files). Either way it is noise,
and **the constraint is provenance, not bytes.**

### B.4.4 The recommendation

This one needs a recommendation on licensing more than on code, so
here it is, in order:

1. **Write `resources/samples/PROVENANCE.md` first** — before any new
   file is added. One row per file: where it came from, what its
   header says, and the citation. Model it on
   `xtal/mof/pormake/PROVENANCE.md`, and add it to
   `packaging/bundle.py RESOURCES` so it travels, with a test beside
   `test_the_vendored_licence_and_provenance_are_collected`. **S.**
   This is the whole job's foundation and it is half a day.
2. **Add the two orphans to `samples.SAMPLES`** — `MIL53.cif` (built
   by this application, so provenance-clean) and `UIO66.cif`. **S,
   five lines.**
3. **Decide the sourcing rule**, and make it a rule rather than a
   judgement per file. `review/design/mof-database-licensing.md`
   proposes the right one: *every sample either (a) comes from **COD**
   with its public-domain header quoted, (b) is **regenerated** from
   the paper with an `_audit_creation_method` and a `_citation_*`
   block, RASPA2-style, or (c) was built by Crystal Builder.* CoRE MOF
   **2025**'s SI subset is the CC BY fallback with a NOTICE; anything
   with a CCDC header does not ship. **This is the decision only
   Julius can make**, and it has a cost: it puts the current
   `MFU4l.cif` in question, and MFU-4l is the application's benchmark.
   A COD entry or a regenerated file has to be found for it before the
   rule can be applied retroactively.
4. **Then grow to 20–30**, from the allowed sources — the sibling
   document has already located COD IDs for the six that matter most —
   one `Sample`
   entry each with the same one-sentence "why it is here" the seven
   existing entries have — that writing is what makes them a curated
   set rather than a folder. Target the list Julius named: MOF-5,
   HKUST-1, **UiO-66**, ZIF-8, **NU-1000**, **MIL-101**, MIL-53,
   MOF-74/CPO-27, IRMOF-9 or -10 (**an interpenetrated one**, which
   Part A now has a reason to want), and the project's own MFU-4l,
   CFA-1 and Ni₂Cl₂(BTDD). **M**, and most of the M is sourcing and
   writing, not code: `samples.py` needs no new machinery and
   `bundle.py` needs no change at all.

**Size: S for the provenance file and the two orphans; M for the
curated set; L and not recommended for MOFid.** And the gate on all of
it is a decision, not an engineer.

---

# Every item, sized

`S` ≈ a day or less · `M` ≈ two to five days · `L` ≈ longer, or with a
research question inside it.

| # | Item | Size | Dependency | Copies / exemplar | Decision needed from Julius first? |
|---|---|:-:|---|---|---|
| **A** | **Interpenetration — detection** | **S** | none | `Net.multiplicity` + `Net.components` (`topology.py:243`, `:255`); surfaced like `docks/net.py` | No |
| A′ | Interpenetration in `StructureInfo` too | S | none | `properties.py:117` | No — do it second |
| A″ | Interpenetration — **generation** | **L** | none | IPMOF (2017) is the only method | **Yes** — and it is blocked behind PORMAKE item 1 anyway |
| A‴ | Blatov class / self-penetration (HRN) | L | none | ToposPro | Not recommended |
| **1a** | **mmCIF / PDBx, read** | **S** | **none** (gemmi is already required) | `cif_reader._from_small_structure` | No |
| 1b | mmCIF, write | S | none | `cif_writer` | **Yes** — recommend not in v1 |
| **1c** | **POSCAR / CONTCAR** | **S**+**M** | none | `xtal/io/gen.py` | **Yes** — `Format.filenames`, a shared-code change |
| **1d** | **pymatgen `Structure` JSON** | **S** | **none** (not pymatgen) | `gen.py` + `json` | **Yes** — which extension |
| **1e** | **ASE `.traj`** | **M** | `ase` extra | `xtal/io/trajectory.py` | **Yes** — `Format.available`, and the trajectory dispatch |
| **2a** | Charge-source list read from the `Param` | **S** | none | `test_every_engine_that_is_registered_can_be_chosen` | No — **do this first** |
| **2b** | **EQeq** | **M** | none (numpy/scipy) | `xtal/ff/uff/qeq.py`; `ZEO_RADII` for the table | **Yes** — transcribe the table from NIST rather than the GPL-2.0 repo |
| **2c** | EQeq+C | S | none | 40 lines over EQeq | **Yes** — the MOF `D_Z` table is behind a paywall |
| **3a** | `Engine.__call__` coerces options | **S** | none | `Engine.coerce` already exists, uncalled | No — cheapest line here |
| **3b** | **`ASECalculator` base** | **M** | none | 141 of 219 lines already in `mace/calculator.py` | No — **do this before any new engine** |
| 3c | `ExternalCalculator` base (factoring §6) | M | none | xtb + dftb | No — same pass as 3b |
| **3d** | **ORB-v3** | S after 3b | `orb-models` extra | `xtal/ff/mace/` | No — **Apache-2.0, no account: do first** |
| **3e** | **MatterSim** | S after 3b | `mattersim` extra | same | No — MIT, no account, always gives stress |
| **3f** | **SevenNet** | S after 3b | `sevenn` extra | same | No — MIT, but **cannot coexist with mace** (`e3nn`) |
| 3g | UMA | S after 3b | `fairchem-core` extra | same | **Yes** — HuggingFace manual gate, and `odac` has no trained stress |
| 3h | eSEN-30M-OAM | M | `fairchem-core==1.10` + compiled PyG | same | **Yes** — **research-use-only weights**; best on the benchmark |
| 3i | MACE-MP-MOF0 (idea 19) | S | existing `mace` extra | the existing `CUSTOM` / `model_path` path | **Yes** — download-and-cite (CC BY 4.0, mandatory citation) |
| **4a** | **`resources/samples/PROVENANCE.md`** | **S** | none | `xtal/mof/pormake/PROVENANCE.md` | No — **do this first of all** |
| 4b | Add `MIL53` and `UIO66` to the menu | S | none | `xtalapp/samples.py SAMPLES` | No — five lines |
| **4c** | **A curated MOF set (20–30)** | **M** | none | `samples.py`; **COD (CC0)** per `review/design/mof-database-licensing.md` | **Yes** — the sourcing rule, and what to do about `MFU4l.cif` |
| 4d | MOFid / MOFkey via MOFid itself | **L** | GPL-2.0, Java, a CMake OB build | — | **Not recommended** |
| **4e** | **A MOFkey-shaped identifier of our own** | **S** | `rdkit` (existing `build` extra) | `graph.fragments()` + `rcsr.describe` | No |

**Six decisions are the gate on nine items**, and they are worth
answering together rather than one at a time:

1. **`Format` grows `filenames` and `available`** — or POSCAR and
   `.traj` do not happen. (1c, 1e)
2. **Which extension `.json` structures claim.** (1d)
3. **Is transcribing 484 NIST numbers, checked against a GPL-2.0
   repo's file, acceptable?** (2b)
4. **Does an `ENGINES` entry own a dispersion correction?** MOFSimBench's
   numbers are all model+D3, and MACE already has the option hidden.
   (3d–3i)
5. **Do research-use-only and manually-gated model weights belong in a
   greyed-out engine list at all?** (3g, 3h)
6. **What is the sourcing rule for a shipped structure — and does it
   apply retroactively to `MFU4l.cif`?** (4a, 4c)

**If only three things get built**, they should be:
**A (detection)**, **1a (mmCIF)** and **3b + 3d (the ASE base and
ORB-v3)** — the first turns code that already exists into a visible
feature, the second is a whole file format for half a day because
gemmi is already paid for, and the third stops the next five engines
each costing four times what they should.

---

# What I did not get to

- **I did not run the test suite.** The machine's swap is near full
  and CLAUDE.md is explicit about what a full run costs here; every
  measurement above comes from a targeted probe or from reading. The
  probes import `xtal` and touch nothing else. `git status` is clean.
- **No positive real interpenetrated structure was tested**, because
  the tree has none. The three controls in
  `review/probes/registry/interpenetration.py` are synthetic (a
  doubled-cell `pcu`, and MOF-5's framework duplicated). Before
  building A, get one real 2-fold structure — IRMOF-9 or IRMOF-10, or
  a `cat1` entry from hMOF — and check the detector against a
  published fold.
- **`Net.key` on the atom graph was not pursued past its refusal.** It
  refuses 424 vertices, so "are the two frameworks the same net?" is
  unanswered on the chemistry and I did not measure where its budget
  actually runs out.
- **The mmCIF probe used a hand-written four-atom PDBx file**, not a
  real PDB entry, because fetching one was out of scope. Before
  building 1a, run it on a real `.cif` from the PDB and on a
  multi-model entry.
- **I did not prototype the POSCAR reader**, so "150 lines" is from
  the shape of `gen.py`, not from writing it.
- **EQeq's numerics were not implemented or checked.** The claim that
  `qeq._solve` is reusable comes from reading both; the Ewald pair
  matrix is the piece I would expect to cost more than the estimate.
- **The EQeq+C MOF parameter table was not obtained** (paywalled), and
  the EQeq erratum (JPCL 2012, 3, 2897) was not read. The ATMO
  parameters quoted are from the SI script's docstring.
- **The published MOFSimBench figures were not read** — only the
  arXiv preprint. The 89% / 62% figures are verified against the
  preprint; a report that the journal version revises them to
  94% / 66% is **second-hand and should not be cited on this
  document's authority.**
- **No MLIP was installed or run.** Every package claim in B.3.4 is
  from PyPI/GitHub/HuggingFace metadata read on 2026-09-19, not from
  an install, and install sizes are estimates. These projects release
  monthly; re-check before pinning.
- **The licensing half of B.4 was done better elsewhere and I have
  deferred to it.** `review/design/mof-database-licensing.md`, landed
  at `d6d8b22` while this was being written, has COD IDs for all six
  headline MOFs, the RASPA2 precedent, per-file size measurements and
  a survey of what other projects ship. My own search concluded COD
  lacked NU-1000 and MIL-101; that was wrong, and B.4.3 now says so.
  What survives from my side is the state of `resources/samples/`
  today (B.4.2), which that document does not cover.
- **The remaining legal questions should not be answered by a
  reviewer**, and both documents reach the same list: whether EU/UK
  database right bites on ~30 structures extracted from a curated
  collection; whether CCDC's contractual ban binds someone who never
  accepted the terms; and the copyright status of a CIF deposited as
  journal supporting information. They want one conversation with
  somebody qualified, and then a line in `PROVENANCE.md`.
