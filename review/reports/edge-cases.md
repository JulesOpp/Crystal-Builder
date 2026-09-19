# Edge cases in the headless core (`xtal/`) and the CLI

Nineteen findings from ~1400 lines of probe scripts under
`review/probes/edge/`, all reproducible with `.venv/bin/python`.  Two are
**critical**: `xtal symmetry --symprec -1` segfaults the process, and an
atom label containing a space or a `#` corrupts the saved CIF and
`.xtalproj` — in the `#` case by silently deleting the atom.  The rest
divide into *silent wrong answers* (an overlapped structure scoring a
finite UFF energy and "converging"; `asymmetrize` handing back a subgroup
with the same atom count; a multi-block CIF read as its first block) and
*surprises* (a UTF-8 BOM defeats four of five readers).  Two of the nine
shipped samples — `CFA1.cif` and `Ni2Cl2BTDD.cif` — expand with atoms at
exactly 0 Å, which breaks every symmetry entry point and produces
coordination 28 under perception, with nothing anywhere saying why.
`git status` is clean; nothing tracked was touched.

Probes: `review/probes/edge/p1_cif_read.py`, `p1b_symbols_encoding.py`,
`p2_roundtrip.py`, `p2b_odd_structures.py`, `p2c_label_corruption.py`,
`p3_lattice_symmetry.py`, `p3b_coincident_samples.py`, `p4_bonding.py`,
`p5_forcefield.py`, `p6_process.py`, `p7_cli.sh`, `p8_workspace.py`,
`p9_misc.py`.  All use `tempfile` and clean up after themselves.

---

## 1. `--symprec -1` segfaults the whole process `[critical]`

**What.**  A negative symmetry tolerance is handed straight to spglib,
which dies with SIGSEGV.  No Python exception, no message, exit 139.

**Where.**  `xtal/core/symmetry.py:139` (`detect`, which passes `symprec`
through untouched) and `xtal/cli.py` (`cmd_symmetry`, no validation).
The guard exists — but only in the GUI, at
`xtalapp/dialogs/find_symmetry.py:156` (`if symprec <= 0:`).

**Evidence.**

```
$ .venv/bin/xtal symmetry resources/samples/ZIF-8.cif --symprec -1
Segmentation fault: 11
rc=139
```

For contrast, `--symprec 0` is handled: `error: symmetry detection
failed: spacegroup search failed`, rc 1.

**Why it matters.**  `xtal/` is the headless core and is meant to be
usable without Qt; the only place that checks this input is the one
place that imports Qt.  A segfault is not catchable, so a module, a
scan, a plugin or the GUI itself taking a symprec from a saved session
or a script kills the process and loses whatever was unsaved.  A scan is
described in CLAUDE.md as an overnight job.

**Fix.**  Move the `symprec <= 0` check from the dialog into
`symmetry.detect`, and have the dialog rely on it.

---

## 2. A label with a space or a `#` corrupts the file it is saved into `[critical]`

**What.**  `cif_string` has a `_quote` helper and uses it for the block
name, the creation method, the formula and the symmetry operations —
but **not** for `_atom_site_label`, `_atom_site_type_symbol` or the two
label columns of the bond loop.  A label with a space therefore writes a
row with one field too many; a label starting with `#` comments the rest
of its own line away.

**Where.**  `xtal/io/cif_writer.py:136` (the site row) and `:191` (the
bond row); `_quote` is at `:51` and is not called from either.
`.xtalproj` embeds the same text, so it is corrupted identically.  The
label is user-editable through a bare `QLineEdit` with no validator —
`xtalapp/docks/inspector.py:89` and `:343`, which only `.strip()`s.

**Evidence** (`review/probes/edge/p2c_label_corruption.py`).  Input is a
legal CIF with quoted labels — a file this reader accepts:

```
CASE foreign CIF, label 'Na 1'
  read  -> labels=['Na 1', 'Cl 1'] bonds=[]
  write_cif ok
  re-read RAISED ValueError: .../out.cif:27:0(643): Wrong number of
      values in loop _atom_site_*
  project RAISED ValueError: string:27:0(643): Wrong number of values
      in loop _atom_site_*
```

The row written is `Na 1     Na     0.000000 ...` — unquoted.  The `#`
case is worse because it does not raise:

```
CASE label with a leading #
  read  -> labels=['#Na1', 'Cl1'] bonds=[]
  write_cif ok
  re-read -> n_sites=1 labels=['Cl1'] bonds=0
  project -> n_sites=1
```

An atom went in and did not come out, with `rc=0` and no warning.

**Why it matters.**  This is the `Ctrl+S` path.  A user renames an atom
to `Na 1` in the Inspector, saves, and the workspace copy of their
document is a file nothing — including this application — will ever open
again.  With `#` the save succeeds and the atom is simply gone, which is
the failure mode CLAUDE.md's SPECIAL_POSITION_TOL paragraph is about: no
error, a plausible file, a different crystal.

**Fix.**  Route both label columns and the type symbol through `_quote`,
and give the Inspector's label field a validator that refuses whitespace
and CIF's reserved leading characters (`_ # $ [ ] ;`).

---

## 3. Two shipped samples expand with atoms at 0 Å, and nothing says so `[important]`

**What.**  `CFA1.cif` and `Ni2Cl2BTDD.cif` contain asymmetric-unit sites
that are symmetry images of one another, so `p1.expand` produces atom
pairs at *exactly* zero separation.  Every symmetry entry point then
refuses to run, bond perception returns a chemically impossible graph,
and the force field returns a number.  No door reports the cause.

**Where.**  The sample files themselves; the consequences are in
`xtal/core/symmetry.py:139` (`detect`), `xtal/core/bonding.py:158`
(`perceive`), and `xtal/ff/uff/`.

**Evidence** (`review/probes/edge/p3b_coincident_samples.py`):

```
CFA1: P321, 43 sites, 242 atoms in the cell
  atom pairs closer than 1e-6 A: 18
    atoms 80/87  H/H  d=0.000e+00  from sites 16 (H4A) and 17 (H4B)
  detect       ValueError: symmetry detection failed: too close distance
  wyckoff      ValueError: symmetry detection failed: too close distance
  standardize  ValueError: cell standardisation failed
  duplicate_groups(0.05) -> [[16, 17, 18]]
  preview_merge(0.05)    -> 2 of 43 sites merge -- 242 atoms become 230

Ni2Cl2BTDD: H-3m, 40 sites, 1152 atoms in the cell
  atom pairs closer than 1e-6 A: 360
  detect       ValueError: symmetry detection failed: too close distance
  preview_merge(0.05) -> 27 of 40 sites merge -- 1152 atoms become 378
```

Perception and UFF on the same files (`p4_bonding.py`, `p5_forcefield.py`):

```
  Ni2Cl2BTDD   atoms=1152 bonds=6786 maxcoord=28 frags=127
  MFU4l        atoms=648  bonds=848  maxcoord=6  frags=1     (control)
  Ni2Cl2BTDD   E=6.28154e+06 maxF=2983.21 n=1152
```

After `merge_duplicates(s, 0.05)`: 378 atoms, 342 bonds, max
coordination 6.  So the fix is one menu item away — the user just has no
way of knowing that.

**Why it matters.**  `Ni2Cl2BTDD.cif` is the structure CLAUDE.md names
as the relaxed scan's target ("1152 atoms, 0.44 s an optimiser step") and
docs/TODO.md wants an overnight 7×7 scan of it.  Every one of those
numbers is for a crystal with three copies of most of its atoms.
docs/TODO.md § "Merge duplicates cannot see a site duplicated by its own
group" covers the *converse* case (a site duplicated by its own orbit);
this is the case Merge Duplicates *can* see and nobody is asked to press
it.  The CLI reports it as `error: symmetry detection failed: too close
distance between atoms` (`p7_cli.sh`), which names the symptom and not
the remedy.

**Fix.**  On open, run the zero-distance check that `duplicate_groups`
already implements and put a `meta["warnings"]` entry on the structure —
"3 pairs of atoms coincide; Merge Duplicates will collapse them" — the
same channel the space-group disagreements already use; and make
`detect`'s exception message say it.

---

## 4. The force field ignores any pair closer than 1 µÅ, then reports convergence `[important]`

**What.**  `neighbor_pairs` drops every pair below `min_distance=1e-6`
from the list it returns.  Two atoms on top of each other therefore
contribute *nothing* to the van der Waals or Coulomb sum, and the
optimiser sees zero force on them and declares a minimum.

**Where.**  `xtal/core/neighbors.py:81` (the default) and `:156`
(`keep = dist >= min_distance`).  The docstring of `neighbor_pairs` does
not mention the parameter.

**Evidence** (`review/probes/edge/p5_forcefield.py`), three C/C/O atoms
in a 10 Å cube, two of the carbons coincident:

```
  two C exactly coincident           E=315.024 maxF=345.983 n=3
  two C 1e-6 frac apart              E=315.024 maxF=345.984 n=3
  opt coincident: converged=True steps=1 E=290.1637598116365
                  msg='    1  E =      290.16376  |F|max =    0.00000'
```

The energy is identical to six figures whether the overlap is exact or
not, i.e. the pair is simply absent.  A real overlap should be `+inf`.

**Why it matters.**  The number is finite, the forces are zero, and the
optimiser says *converged*.  Combined with finding 3, an energy of
6.28 × 10⁶ kcal/mol on Ni2Cl2BTDD looks like a bad geometry rather than
a broken one, and a scan over it produces a landscape with no hole in it
anywhere.  CLAUDE.md is emphatic that "an unconverged scan point is not a
number"; a *converged* point over an impossible geometry is worse,
because nothing hatches it.

**Fix.**  Keep the guard but count what it drops, and have the
calculator raise (or add a `warnings` line, the mechanism already used
for "no bonds were perceived") when any pair was discarded as an
overlap.

---

## 5. `asymmetrize` silently returns a subgroup `[important]`

**What.**  `reduce_to_p1` → `asymmetrize` at the default tolerance does
not come back to the group it started from on three of nine samples, and
on `MFU4l` it reports success while handing back a *different space
group* with 8.7× the sites and the same atom count.

**Where.**  `xtal/core/symmetry.py:434` (`asymmetrize`), with
`DEFAULT_SYMPREC = 1e-5` at `:45`.

**Evidence** (`review/probes/edge/p3_lattice_symmetry.py`):

```
### reduce_to_p1 -> asymmetrize round trip
  HKUST1     OK   Fm-3m(6 sites, 624 atoms) -> P1(624) -> Fm-3m(6, 624)
  MFU4l      DIFF Fm-3m(10 sites, 648)     -> P1(648) -> Pmmm(87, 648)
  MIL53      DIFF P63/mmc(7 sites, 104)    -> P1(104) -> P1(104, 104)
  MOF-5      DIFF P1(424 sites, 424)       -> P1(424) -> Fm-3m(7, 424)
  rutile/quartz/halite/dry_ice/UIO66/ZIF-8/zn_oac  OK

### detect() at symprec extremes
  MFU4l   1e-10:Pmmm(#47,87orb) 1e-05:Pmmm(#47,87orb)
          0.01:Fm-3m(#225,10orb) 1:Fm-3m(#225,10orb)
  MIL53   1e-10:P1(#1,104orb)   1e-05:P1(#1,104orb)
          0.01:P6_3/mmc(#194,7orb) 1:P6_3/mmc(#194,7orb)
```

`asymmetrize` returns `ok=True` with the message *"Pmmm (#47): 648 atoms
-> 87 independent sites"*.  Nothing in the report says the file said
Fm-3m.  The verification step (`_regenerates`) passes, correctly — Pmmm
with 87 sites *does* regenerate 648 atoms.

**Why it matters.**  The atom count is the invariant the application
checks and it is preserved, so every automatic guard is satisfied.  What
is lost is the group, silently, at the tolerance that is the default
everywhere.  MOF-5 is the same mechanism in the useful direction (a P1
file recognised as Fm-3m), which is why the behaviour is not obviously
wrong — but a user pressing Reduce to P1 and then Find Symmetry on
MFU-4l gets a structure that will scan, optimise and save as an
orthorhombic crystal.

**Fix.**  When `detect` finds a group that is a proper subgroup of the
structure's current one, say so in `SymmetryReport.warnings` with the
symprec that would recover it — the sweep above shows 0.01 Å does.

---

## 6. `workspace.json` that is valid JSON but not an object raises `[important]`

**What.**  Three readers of the marker file each catch a different set of
exceptions.  A file containing `[1,2,3]` or `null` parses fine and then
`AttributeError`s on `.get`, against the docstring's explicit promise.

**Where.**  `xtal/workspace.py:359` (`version`, catches `OSError,
json.JSONDecodeError`) and `:500` (`session`, adds `LookupError,
TypeError, ValueError`).  `set_session` at `:558` *does* guard with
`if not isinstance(data, dict)`, so the right check exists in one of the
three places.  The `session` docstring says: "a marker somebody edited by
hand … every one of them reads as 'nothing was open'".

**Evidence** (`review/probes/edge/p8_workspace.py`):

```
  not json                  version=0 session={'open': [], 'active': 0}
  empty                     version=0 session={'open': [], 'active': 0}
  a list                    RAISED AttributeError: 'list' object has no
                                   attribute 'get'
  null                      RAISED AttributeError: 'NoneType' object has
                                   no attribute 'get'
```

**Why it matters.**  This is read while a workspace is being opened,
before there is a window to report into — the "degraded window" path
CLAUDE.md describes exists precisely so that a bad folder does not stop
the application, and this defeats it with a traceback.

**Fix.**  Hoist `set_session`'s `isinstance(data, dict)` check into a
single `_marker_data()` helper that all three use.

---

## 7. A session path can escape the workspace `[important]`

**What.**  `set_session` refuses to store a path from outside the root
("the falsehood this avoids everywhere else").  `session_paths` applies
no such rule when reading, so an absolute path in `workspace.json` is
returned verbatim and opened.

**Where.**  `xtal/workspace.py:527` — `self.root / name`, where `Path.__
truediv__` with an absolute right-hand side discards the left.

**Evidence:**

```
  session.open has absolute paths   session={'open': ['/etc/passwd'], ...}
                                    paths=['/etc/passwd']
  session.open not a list           session={'open': ['a','.','c','i','f']}
                                    paths=['.../broken']   # the root itself
```

The second line is the string `"a.cif"` being iterated character by
character; `'.'` then resolves to the workspace directory, which exists,
so a *directory* is offered as a document to open.

**Why it matters.**  A workspace is a folder people share and sync; a
`workspace.json` from elsewhere decides what this application opens at
startup.  It is also the asymmetry pattern of finding 11 — a rule
enforced on the way out and not on the way in.

**Fix.**  In `session_paths`, reject any entry that is absolute or whose
resolved path is not under `self.root`, and require `open` to be a list
of `str`.

---

## 8. A UTF-8 BOM defeats four of the five readers `[important]`

**What.**  Every text file in `xtal/` names `encoding="utf-8"` (verified
by AST over the whole package — 61 call sites, no exceptions outside
vendored PORMAKE, which is a genuine strength).  But `utf-8` is not
`utf-8-sig`, so three invisible bytes at the front of an otherwise
perfect file produce four different and misleading diagnoses.

**Where.**  `xtal/io/cif_reader.py:91`, `xtal/io/xyz.py:37`,
`xtal/io/cssr.py`, `xtal/io/gen.py`.

**Evidence** (`review/probes/edge/p9_misc.py`), the same quartz
structure written by this application and given a BOM:

```
  cif       BOM   ValueError: .../q.cif:1:0(0): expected block header (data_)
  xyz       BOM   ValueError: first line of an XYZ file must be an atom count
  cssr      BOM   ValueError: the first two lines of a CSSR file are the cell
  gen       BOM   ValueError: the first line of a .gen file is the atom count
  xtalproj  BOM   ok sites=2          # a zip, so unaffected
  (CRLF and lone-CR line endings are fine everywhere)
```

A Latin-1 byte in a *value* is a `UnicodeDecodeError` quoting a byte
offset and not naming the file:

```
  UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 14
```

**Why it matters.**  Notepad, Excel, PowerShell `Out-File` and a good
deal of Java crystallography tooling write a BOM as a matter of course,
and plenty of pre-2010 CIFs are Latin-1.  The user is told their file is
malformed in a way that points at the wrong line.  The 2026-09-16 commit
named every encoding; this is the half of that job that reading needs.

**Fix.**  `encoding="utf-8-sig"` on every text *read* (it is a no-op on a
file without a BOM), keep `utf-8` on writes, strip a leading BOM before
handing bytes to gemmi, and catch `UnicodeDecodeError` to re-raise with
the path and a suggestion.

---

## 9. A multi-block CIF is read as its first block, in silence `[important]`

**What.**  `FORMATS.read` returns block one of a many-block CIF with no
warning.  `read_all` is registered for `cif` and for `xyz` — and has no
caller anywhere in `xtal/` or `xtalapp/`.

**Where.**  `xtal/io/registry.py:94` (`read_all`), `xtal/cli.py:33`
(`_load` calls `read`), `xtalapp/documents.py:293` and
`xtalapp/document.py:158` (Open calls `read`).

**Evidence:**

```
  FORMATS.read      -> a=4.9134
  FORMATS.read_all  -> [4.913, 9.913]
  warnings on the first block: None
```

Two different crystals in one file; the second is discarded without
comment.

**Why it matters.**  The registry's own comment beside the `xyz` entry
makes the argument: *"A relaxation is a hundred frames in one file, and
reading only the first of them silently answers a different question."*
The mechanism written to honour that is not wired to any door.
Multi-block CIFs are how the CSD and most refinement software ship a
series of structures.

**Fix.**  Have Open and the CLI call `read_all` and either offer the
blocks or, at minimum, put "this file holds 4 structures; the first was
opened" into `meta["warnings"]`, which the GUI already shows.

---

## 10. Two runs started at once collide instead of numbering `[important]`

**What.**  `Entry.next_run` computes `max(index) + 1` and then
`mkdir(exist_ok=False)`.  Between those two statements another thread
can take the number.

**Where.**  `xtal/workspace.py:275`.

**Evidence** (six threads through a barrier, `p8_workspace.py`):

```
  folders made: ['uff-optimise-001']
  failures:     ["FileExistsError: [Errno 17] File exists: .../uff-optimise-001",
                 ... x5]
```

**Why it matters.**  `mkdir(exist_ok=False)` is the right *choice* — it
refuses to share a folder rather than interleaving two runs' files, and
the process runner handles a shared `cwd` correctly when it is given one
(`p6_process.py`, two children writing the same `out.txt` interleave
cleanly).  But the failure is a bare `FileExistsError` out of a worker
thread, not a second folder.  One tab running a scan while another runs
an optimisation on the same entry is an ordinary thing to do.

**Fix.**  Loop: try the next index, catch `FileExistsError`, increment,
retry a bounded number of times.

---

## 11. The reader accepts a bond the writer refuses `[important]`

**What.**  `read_bonds` takes an `n_pqr` symmetry code without checking
*n* against the group, and `Bond` does not validate it either.  The
writer does check, and raises.  So a file can be opened into a document
that can never be saved.

**Where.**  `xtal/io/cif_reader.py:206` (the `Bond(...)` append, whose
`except ValueError` catches what `Bond.__post_init__` checks, which does
not include `op`) versus `xtal/io/cif_writer.py:275` (`_bond_distance`)
and whatever raises `bond operation N is outside <group>`.

**Evidence** (`p2c_label_corruption.py`), a CIF with `9_555` in a P1
structure:

```
  read  -> labels=['Na1','Cl1'] bonds=[(0, 1, 8)]
  write_cif RAISED ValueError: bond operation 8 is outside P1, which has
      1 operations
  project RAISED ValueError: bond operation 8 is outside P1, which has
      1 operations
```

**Why it matters.**  `read_bonds`'s docstring says the intent exactly —
"a bond loop that has drifted out of step with the atom-site loop is a
file to open without its bonds, not a file to refuse" — and it honours
that for a missing *label* (that row is dropped; verified in
`p1_cif_read.py`) but not for an out-of-range *operation*.  The result
is a document that opens, looks fine, and fails on `Ctrl+S`.

**Fix.**  Check `0 <= op < len(structure.space_group.operations)` in
`read_bonds` and drop the row, alongside the label check already there.

---

## 12. `xtal convert a.cif a.cif` rewrites the input in place `[important]`

**What.**  No check that output and input are the same file.  The
original is replaced by this application's own rendering of it.

**Where.**  `xtal/cli.py:145` (`cmd_convert`).

**Evidence** (`p7_cli.sh`):

```
convert rt.cif rt.cif                       rc=0  (no stderr)
    size before=7348 after=6288
convert rt.cif rt.cif --supercell 2 2 2     rc=0  (no stderr)
    size now=44849
```

**Why it matters.**  It "works" because `_load` reads the whole file
before anything is written, so this is not truncation — it is a lossy
rewrite of somebody's deposited CIF with no prompt and no backup.  All
the refinement metadata a foreign CIF carries is gone (the writer is
deliberately minimal — "no refinement history, no diffractometer
block"), which is right for a conversion and wrong for an overwrite the
user did not ask for.

**Fix.**  Compare `Path(input).resolve() == Path(output).resolve()` and
exit 1 with one line, unless a `--force`/`--in-place` flag is given.

---

## 13. A typo'd `-p name=value` is dropped in silence `[important]`

**What.**  `coerce` drops unknown parameter names.  The CLI accepts
`-p a=b` for a module with no parameter `a`, runs with every default,
and exits 0.

**Where.**  `xtal/params.py:148` — *"Unknown keys are dropped rather than
passed through: they are almost always a stale saved value or a typo in a
script"*.

**Evidence:**

```
-p novalue               rc=1  error: --param wants name=value, not 'novalue'
-p =noname               rc=0
-p a=b                   rc=0
-p steps=notanumber      rc=1  error: could not convert string to float
```

**Why it matters.**  The reasoning in the docstring is right for a saved
session and wrong for a command line: a dialog cannot produce a typo, a
person typing `-p step=5` instead of `steps=5` can, and the run then
reports success having measured something else.  `xtal modules` prints
the valid names, so the CLI knows them.

**Fix.**  Have `cmd_run` diff `_parsed_params` against `action.options`
and refuse an unknown name with the list of valid ones; leave
`params.coerce` as it is for the session path.

---

## 14. Smaller things `[minor]`

* **Dead exception handler.**  `xtal/cli.py:679`'s
  `except FileNotFoundError` is unreachable — `FileNotFoundError` is an
  `OSError`, caught two lines above.  In practice a missing file gets
  gemmi's C++ text (`error: [Errno 2] unable to open() file … for
  reading`) instead of the intended `error: no such file: x.cif`.
* **`.gen` cannot hold zero atoms.**  `FORMATS.write` succeeds and the
  read back raises `ValueError: no element symbol in '0.000000000000'`
  (`p2b_odd_structures.py`).  `cif_reader._declares_sites` goes out of
  its way to support the empty structure File ▸ New makes; `.gen` does
  not, so exporting a new document is a file nothing reads.
* **A read-only run folder is a traceback.**  `ExternalProcess.run`
  resolves the binary carefully and "says so before the run folder is
  touched", then does `self.cwd.mkdir(...)` at
  `xtal/modules/process.py:366` with no handler:
  `PermissionError: [Errno 13] Permission denied: …/run`.  A full disk
  or a read-only workspace gets no sentence.
* **Element parsing is forgiving in one direction only.**  An unknown
  `_atom_site_type_symbol` refuses the *whole file*
  (`ValueError: unknown element symbol: 'Q'` — no row is skipped, no
  partial read), while `Uuo` is silently read as uranium by the
  two-then-one-letter prefix rule at `xtal/core/elements.py:230`.
  `Zn2+`, `O2-`, `D`, `X`, `Ow`, `CA` are all handled correctly.
* **`--supercell 50 50 50` runs for six minutes and writes 688 MB**
  without a word: 102 sites → 12 750 000, no estimate, no confirmation.
  It does complete, which on a machine at 97% swap is more luck than
  design.
* **`safe_name` deletes non-ASCII rather than replacing it**
  (`xtal/workspace.py:94`): `quartz café` → entry `quartz_caf`, so
  `café` and `cafè` name the same folder.  Content de-duplication saves
  it, but the entry names are misleading.
* **CSSR silently rounds the cell** to 4 dp (`25.86584 → 25.8658`,
  `109.6102 → 109.61`) — a format limit, but `keeps` does not mention
  cell precision and the export dialog therefore cannot.
* **`optimize --max-steps 0` exits 2** with `note: the geometry is where
  the optimiser stopped, not a minimum`; `max_steps=-1` raises
  `CalculatorError: the optimiser produced no steps` from a branch
  marked `# pragma: no cover`.  Both defensible, neither documented.

---

## 15. What is solid `[strength]`

Verified, not assumed:

* **A foreign `_geom_bond` loop is not read as bonding.**  A two-row
  refinement distance table with `1_555`/`2_555` codes gives
  `bonds=0`; the same loop with `_xtal_bond_kind` gives the bonds.  A
  row naming a site that is not in the file is dropped and the rest of
  the loop is kept.  (`p1_cif_read.py`, exactly as
  `cif_reader.read_bonds` describes.)
* **CIF and `.xtalproj` round trip every sample and every fixture** —
  9 samples + 4 fixtures, coordinates to `maxfrac=0.0` (quartz `3.3e-7`,
  which is 2/3 at six decimals), space group, operation count, bond
  kinds and meta all preserved; the same again through `for_export`.
  `cssr`/`gen`/`xyz` expand to P1 and drop symmetry and bonds, which is
  exactly what their `keeps` sets declare.  (`p2_roundtrip.py`.)
* **`for_export` is correct and non-destructive**: dummy atom, net edge
  and suppression all removed, the original object untouched, and
  `what_is_dropped` says so in one sentence.
* **The external process runner handles everything thrown at it**
  (`p6_process.py`): missing binary (`MissingProgram: … was not found on
  PATH`), non-zero exit (`rc=3`, `bad.sh exited with status 3`),
  stderr-only output (merged into the log and the tail), cancellation
  mid-run (`rc=-15` in 0.61 s), a child that ignores SIGTERM (`rc=-9`
  after the grace period), cancellation *before* launch (nothing is
  started), and run folders containing spaces, accents, quotes and
  newlines.
* **UFF's warnings are honest and specific**: *"no bonds were perceived,
  so this is a gas of atoms held together by nothing but van der Waals"*;
  *"the cell carries a net charge of +2.000 e; a uniform neutralising
  background is assumed"*; *"electrostatics are on but every site has a
  charge of zero"*; QEq's *"treat them as an estimate to look over, not a
  published result"*.  `Og` is refused with the range it covers; 0 atoms
  and a dummy-only cell give `CalculatorError: there are no atoms to
  compute an energy for`; a lone marker plus a real atom builds fine
  (markers held at the door, as documented).
* **Input validation on the data model is tight.**  `Site` refuses
  non-finite coordinates; `Lattice.from_parameters` refuses a zero or
  negative edge, an angle outside (0,180), non-finite values, and
  geometrically impossible angle triples (`20/20/150`).  `α = 90.0000001`
  and `a = 1 Å` / `a = 200 Å` all behave.
* **Encoding is named at all 61 text-file call sites in `xtal/`**
  (AST check, vendored PORMAKE excluded) — finding 8 is about *which*
  encoding, not about the discipline.
* **The CLI is one line and a non-zero status nearly everywhere**:
  missing file, a directory in place of a file, junk content, an empty
  file, an XYZ named `.cif`, an unregistered extension, no extension,
  an output directory that does not exist or is read-only, an unknown
  engine or method, `--supercell 0 0 0` (`error: na must be >= 1, got
  0`), `--supercell -1 1 1` and `--supercell 1 1 x` (argparse, rc 2).
  No traceback anywhere except the segfault of finding 1.
* **`SPECIAL_POSITION_TOL = 0.05` does what CLAUDE.md says.**  Sites at
  1/3, 2/3 and 1/2 written at four decimals expand to the same atom
  count as the exact values, on a 5 Å cell and on a 30 Å one.
* **`Workspace.find` walking up from `/`, `/nonexistent`, and a path
  whose file does not exist all return `None`** rather than raising, and
  a workspace root named `café crystals`, `結晶` or `näive` works end to
  end including run folders.
* **Space-group settings resolve correctly**: `:1`/`:2` origin choices
  and `:R`/`:H` axes are distinguished (`R -3 c :R` → 12 operations,
  `R -3 c :H` → 36), a Hall symbol wins over an H-M one, a Hall symbol
  written with semicolons is repaired *with a warning saying so*, and a
  file with no symmetry gets `P1` plus
  `"no symmetry information in the file; assuming P1"`.

---

## What I did not get to

* **The GUI side of finding 2.**  I read `inspector.py` and confirmed the
  label field has no validator, but did not drive the real window with
  `run-app/drive.py` to watch a save corrupt a file end to end.  The
  headless reproduction is complete; the GUI confirmation is one
  `--action` away.
* **`xtal/modules/` beyond `process.py`.**  Zeo++, DFTB+ and MACE all
  need binaries or extras this machine does not have, so module *runs*
  were probed only through `XTAL_STUB_MODULE=1`.  `report.py` (861
  lines), `scan.py` (640) and `zeopp.py` (862) got no edge-case probing
  at all — `scan.csv` resume, a scan point whose atom count changes, and
  a report referencing a surface file that moved are all untested here.
* **Bond-order inference.**  I checked that a metal cluster gets no
  bonds (`allow_metal_metal=False` by default, so `orders` returns an
  empty array — correct but perhaps surprising) and that `zn_oac` gets
  orders of 1.0 and 1.5.  I did not probe the carboxylate or aromatic
  ring rules against awkward geometries.
* **`xtal/mof/` and `xtal/build/`.**  Vendored PORMAKE is explicitly
  out of scope for reformatting and I left it alone entirely; the
  `CONNECTION_DISTANCE` invariant and the SMILES builder are unprobed.
* **Whether finding 5 is a defect or a tolerance choice.**  I established
  that MFU-4l needs symprec ≥ 0.01 to come back as Fm-3m and that
  nothing reports the downgrade; I did not measure how far MFU-4l's
  deposited coordinates actually sit from ideal Fm-3m, which is what
  would settle whether the default should move.
* **`xtal/io/trajectory.py`, `pdb.py`, `cube.py`, `cgd.py`, `xy.py`** —
  not exercised.  `cgd.py`'s lack of an independent Systre check is
  already in docs/TODO.md.
* I ran no part of the pytest suite (memory pressure; `sysctl
  vm.swapusage` reported 8.85 GB of 10 GB in use throughout), so I
  cannot say which of these findings an existing test already covers.
