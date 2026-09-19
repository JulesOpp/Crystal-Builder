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

Probes: `review/probes/registry/` (`interpenetration.py`,
`mmcif_via_gemmi.py`, `ase_engine_split.py`, `gemmi_mmcif.py`).
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
independent identical nets in the crystal — plus, in the
Blatov/Proserpio classification, a **class** saying what symmetry
relates the nets to one another (Class Ia: related by full
translations only; Class II: related by a point operation; and so on).

**Recommendation: report the fold and the per-component periodicity.
Do not attempt the class, and do not attempt self-penetration.** The
class needs the relating operation found and named; self-penetration
needs ring perception. Both are a different and much larger piece of
work, and neither is what a person opening a CIF is asking.

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
framework". A proper entanglement test (Hopf ring net, or ToposPro's
separation test) is out of scope and should be named as such rather
than half-done.

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
wrong order. Revisit generation **after** item 1 lands, at which point
the connection-point model will have been rethought anyway and the
answer may be cheaper.

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

*(Taken before EQeq because the shared-base question is the one that
changes the sizes.)*

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
