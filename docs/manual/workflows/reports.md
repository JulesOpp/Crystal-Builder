(workflows-reports)=
# What a run leaves behind

Every run leaves a folder that can be dated, attributed and read
without the application: a log, and whatever the calculation produced
-- a trajectory and a relaxed structure, one CIF per scan point, a
pattern, a report the Results panel can put back on screen.  After
this page you know which file holds what, and can read a run folder
from a shell or a Python script.

```{index} single: run.log
```
```{index} single: trajectory.extxyz
```
```{index} single: final.cif
```
```{index} single: run folder; contents
```

## The run log

`run.log` is written *as the run goes*, so a run that was stopped, or
crashed, or ran out of disk still leaves the part that happened.  Its
header and footer are the same whatever ran; the middle is the
engine's or the module's own.  The header answers the questions
somebody asks three months later -- what version, what structure,
what was asked for, with which options -- and for an engine run it
goes on to the atom types the result rests on:

```text
Crystal Builder 0.3.1.dev49+g0db248ed6.d20260926
run            uff-single-point-001
what           single point
started        2026-09-26 04:02:46 UTC
structure      C24H12O13Zn4 (Z = 2), 106 sites, 106 atoms in the cell
space group    P1 (#1)
source         resources/samples/prepared/MOF-5.cif
engine         uff  (UFF)
  charges      site
  coulomb      off
  parameter_set uff4mof
  skin         2
  vdw_cutoff   12

Atom types
----------
site  type   means                                 orbit  sure?    why
----  -----  ------------------------------------  -----  -------  ---------------------------------------------------------------
Zn1   Zn3f2  tetrahedral Zn(II), framework-fitted  x1     likely   4 neighbours, tetrahedral, in a framework node
[...]
O1    O_3_f  sp3 oxygen, framework oxide           x1     certain  bridges 4 framework metals -- the oxide at the centre of a node
[...]

Topology
--------
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

Energy
------
torsion            646.7626
angle              330.0816
bond               259.6529
van der Waals      118.6581
inversion            0.0000
total             1355.1552

max force      110.00889 kcal/mol/A
rms force      80.79335 kcal/mol/A
```

A module run's header lists the action and every parameter it was
given, in alphabetical order, whether or not it was changed from the
default; its footer is a *Result* block with the summary, a note if
the run was stopped or failed, the files it wrote, and when it
finished:

```text
Crystal Builder 0.3.1.dev49+g0db248ed6.d20260926
run            scan-scan-003
what           Energy scan: Relaxed scan
started        2026-09-26 04:02:54 UTC
structure      C24H12O13Zn4 (Z = 2), 106 sites, 106 atoms in the cell
space group    P1 (#1)
source         resources/samples/prepared/MOF-5.cif
module         scan.run
  axis1        volume
  axis1_start  4250
  axis1_steps  3
  axis1_stop   4350
[...]
  seed         previous
  tolerance    0.05

3 points on UFF (uff4mof)
Relaxed scan holding volume at each of 3 values, with the cell relaxed, holding volume, seeded from the previous point.
[1/3] volume 4250: 1027.7003 kcal/mol
[2/3] volume 4300: 1030.7287 kcal/mol
[3/3] volume 4350: 1035.3346 kcal/mol
wrote scan.csv and one CIF per point

Result
------
3 of 3 points relaxed
wrote report.json
wrote scan.csv
wrote forward-00.cif
wrote forward-01.cif
wrote forward-02.cif
finished       2026-09-26 04:02:54 UTC
```

## An engine run: three files

`xtal energy` leaves the log alone.  `xtal optimize`, and the Force
Field panel's **Optimise geometry**, leave three files:

`run.log`
: The header above, then a *Steps* block with one line per iteration,
  then the result, the final energy breakdown, and the footer:

  ```text
  Steps
  -----
      0  E =      585.19490  |F|max =  124.99406
      1  E =      537.15051  |F|max =  125.26689
      2  E =      510.28481  |F|max =   73.03694
  [...]

  Result
  ------
  converged after 266 steps: -224.8117 kcal/mol to 360.3832, |F|max 0.0417 kcal/mol/A

  torsion               140.1602
  angle                 115.4671
  bond                   80.3940
  [...]
  ```

`trajectory.extxyz`
: Every step as an extended-XYZ frame, the cell and the energy on
  each frame's comment line, so it opens in OVITO, VMD and ASE as
  well as in the window's transport bar:

  ```text
  38
  Lattice="11.19120700 0.00000000 0.00000000 -9.09664449 6.51875549 0.00000000 -3.47125545 -2.48051375 10.34604037" Properties=species:S:1:pos:R:3 step=0 energy=585.19490263 max_force=124.99406406
  O        2.09759950    -0.67426225     9.60947471
  [...]
  ```

  The MIL-53 relaxation on the {doc}`command-line page <cli>`
  converged after 266 steps and its trajectory has 267 frames: the
  starting geometry and one per step.

`final.cif`
: The structure the run ended at, written by Crystal Builder with the
  cell, symmetry and sites.  `-o` on the command line writes the same
  structure a second time wherever you asked.

## A module run: its own files

Each module writes what its answer is made of, and names it in the
log's footer.  From the tree on the {doc}`previous page <workspaces>`:

- **`scan.run`** -- `scan.csv` (one row per point: the target and
  achieved value, branch, energy, whether it converged, steps,
  pre-relaxation steps, `|F|max`, the six cell parameters, and the
  file), one CIF per point (`forward-00.cif` ... and, when both
  directions are walked, `reverse-00.cif` ...), and `report.json`.
  What the columns mean is on the {doc}`scans page
  </structure/scans>`.
- **`pxrd.simulate`** -- `pattern.xy` (2θ and intensity, two columns
  under a comment header) and `reflections.txt` ({doc}`PXRD
  </porosity/pxrd>`).
- **`mof.build`** -- only `run.log` stays in the run folder: the
  framework itself is the entry's CIF one level up, because a build is
  filed as a structure ({doc}`workspaces <workspaces>`).

:::{note}
**A scan point is written the moment it finishes**, not gathered up
and saved at the end.  A scan is an overnight job, and Stop, a crash
or a full disk has to leave a landscape behind rather than lose one.
An unconverged point is not a number: `no` in the table, `False` in
the CSV, NaN and hatched in the panel -- never a zero.
:::

## `report.json` and the Results panel

```{index} single: report.json
```
```{index} single: Results panel; reopening a report
```

A report is what the {ref}`Results panel <panel-results_dock>` shows
after a run: tables, profiles, a landscape.  It is presentation, but
for a scan it is also the only place the landscape exists as a picture
somebody can click through, so a module whose report is worth
reopening writes it into its run folder as `report.json`.  Not every
module does -- a block of vibrational modes is tens of megabytes of
numbers already on disk in their own format -- and at present the
relaxed scan is the module that writes one.  The files a profile or a
landscape points at are stored relative to the folder, so a workspace
that has been moved still opens.

To put a landscape back on screen after the panel, or the
application, was closed:

1. Find the run folder in the *Workspace* panel
   ({ref}`panel-file_dock`).
2. Double-click its `report.json`.  The Results panel opens, headed
   by the run it came from -- *scan scan 003* for the folder above.

A file that is not a report this program wrote is refused, with that
sentence shown in the window rather than the file opened.

## Reading a run folder from a script

The files are ordinary: the CIFs read with any CIF reader, `scan.csv`
with the `csv` module, `report.json` with `json`.  The core also reads
them back as the window does.  Both of the following were run from a
folder containing the workspace of the previous page.

Listing a workspace, and reading a scan's CSV and report:

```python
import csv
import json
from pathlib import Path

from xtal.modules.report import load
from xtal.workspace import Workspace

workspace = Workspace.open("ws")
for entry in workspace.entries():
    print(entry.name, [run.name for run in entry.runs()])

run = workspace.entry("MOF-5").runs()[-1]
print(run.label, [(a.kind, a.path.name) for a in run.artifacts()])

with open(run.path / "scan.csv", newline="") as f:
    for row in csv.DictReader(f):
        print(row["volume target"], row["energy (kcal/mol)"],
              row["converged"], row["file"])

report = load(run.path / "report.json")
print(report.title, [type(block).__name__ for block in report.blocks])
profile = report.curves[0]
print(profile.title, profile.x_label, profile.y_label)
print(list(profile.x), [round(y, 4) for y in profile.y])
print([Path(p).name for p in profile.paths[0]])

raw = json.loads((run.path / "report.json").read_text())
print(raw["version"], raw["report"]["fields"]["title"])
```

```text
MIL-53 ['uff-optimise-001', 'scan-scan-002', 'pxrd-pxrd-003', 'scan-scan-004', 'pxrd-pxrd-005']
MOF-5 ['uff-single-point-001', 'uff-single-point-002', 'scan-scan-003']
MOF-5-2 ['uff-single-point-001']
pcu-N16-E14 ['mof-build-001']
scan scan 003 [('log', 'run.log'), ('structure', 'forward-00.cif'), ('structure', 'forward-01.cif'), ('structure', 'forward-02.cif'), ('report', 'report.json'), ('file', 'scan.csv')]
4250 1027.700309 True forward-00.cif
4300 1030.728741 True forward-01.cif
4350 1035.334583 True forward-02.cif
Relaxed scan ['Table', 'Curve', 'Curve']
Energy profile volume (A^3) E - E(min) (kcal/mol)
[np.float64(4250.0), np.float64(4300.0), np.float64(4350.0)] [np.float64(0.0), np.float64(3.0284), np.float64(7.6343)]
['forward-00.cif', 'forward-01.cif', 'forward-02.cif']
1 Relaxed scan
```

`Workspace.entries()` and `Entry.runs()` read the directory, not a
manifest, so a run that was killed lists the files it did write.
`Run.artifacts()` classifies each file by its role (`log`,
`trajectory`, `final`, `structure`, `report`, `image`, `file`), which
is what the tree picks an icon by.  `load` gives the report back as
the objects the panel draws -- `tables`, `curves`, `surfaces` and so
on -- with the file paths made absolute again; the raw JSON is
`{"version": 1, "report": {...}}` with every block tagged by its
class name.

Reading a trajectory back:

```python
from xtal.io.trajectory import read_trajectory

trajectory = read_trajectory("ws/MIL-53/uff-optimise-001/trajectory.extxyz")
print(trajectory.n_frames, trajectory.n_atoms)
first, last = trajectory.frames[0], trajectory.frames[-1]
print(first.info)
print(last.info)
print(last.to_structure())
```

```text
267 38
{'step': 0, 'energy': 585.19490263, 'max_force': 124.99406406}
{'step': 266, 'energy': 360.38317139, 'max_force': 0.04174343}
Structure(C16Cr2H10O10, P1, 38 sites, V=754.77 A^3)
```

Whether these Python entry points are a stable interface is the
subject of the {doc}`next page <scripting>`.
