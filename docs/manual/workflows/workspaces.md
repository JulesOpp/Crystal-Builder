(workflows-workspaces)=
# Workspaces, entries and run folders

A {term}`workspace` is the folder a session works in: every structure
gets an entry in it and every run is filed under the structure it was
run against, whether the window or the `xtal` command started it.
After this page you can read a workspace from the outside -- in the
Finder, from a shell, from a script -- and know why a file is where
it is.

```{index} single: workspace; on disk
```
```{index} single: entry (workspace)
```
```{index} single: run folder
```

## What a workspace is

A workspace is an ordinary directory, nothing in it is hidden, and
nothing in it needs Crystal Builder to read: every artefact is a real
file with a real name in a format something else can open.  The
application makes a default one on a first run rather than working
without one -- a scratch folder cleaned on exit would one day throw
away a six-hour run, and a folder under `~/Library/Application
Support` is one nobody can find -- and where new workspaces go is a
preference (*Preferences ▸ General*).  Deleting a folder in the Finder
is a supported way to clean up, and so is adding a file by hand.

:::{note}
**The workspace is asked for before anything opens, and everything
lives in it.**  The window opens on the workspace chooser
({doc}`the GUI </quickstart/gui>`), and a file launched from the
Finder that is already inside a workspace skips the question, because
there is only one answer.  On the command line the answer is
`--workspace DIR`; without it a command prints, writes what `-o`
asked for, and files nothing.
:::

## The layout on disk

One folder per structure; one numbered folder per run underneath it;
a marker file at the root.  This is a workspace after the command-line
session of the {doc}`previous page <cli>` -- two single points and a
scan on MOF-5, a relaxation, two scans and two PXRD patterns on
MIL-53, a single point on a second file also called `MOF-5.cif`, and
one framework built from nothing:

```console
$ find ws | sort
ws
ws/MIL-53
ws/MIL-53/MIL-53.cif
ws/MIL-53/pxrd-pxrd-003
ws/MIL-53/pxrd-pxrd-003/pattern.xy
ws/MIL-53/pxrd-pxrd-003/reflections.txt
ws/MIL-53/pxrd-pxrd-003/run.log
ws/MIL-53/pxrd-pxrd-005
[...]
ws/MIL-53/scan-scan-002
ws/MIL-53/scan-scan-002/forward-00.cif
ws/MIL-53/scan-scan-002/forward-01.cif
ws/MIL-53/scan-scan-002/forward-02.cif
ws/MIL-53/scan-scan-002/report.json
ws/MIL-53/scan-scan-002/run.log
ws/MIL-53/scan-scan-002/scan.csv
ws/MIL-53/scan-scan-004
[...]
ws/MIL-53/uff-optimise-001
ws/MIL-53/uff-optimise-001/final.cif
ws/MIL-53/uff-optimise-001/run.log
ws/MIL-53/uff-optimise-001/trajectory.extxyz
ws/MOF-5
ws/MOF-5-2
ws/MOF-5-2/MOF-5.cif
ws/MOF-5-2/uff-single-point-001
ws/MOF-5-2/uff-single-point-001/run.log
ws/MOF-5/MOF-5.cif
ws/MOF-5/scan-scan-003
ws/MOF-5/scan-scan-003/forward-00.cif
ws/MOF-5/scan-scan-003/forward-01.cif
ws/MOF-5/scan-scan-003/forward-02.cif
ws/MOF-5/scan-scan-003/report.json
ws/MOF-5/scan-scan-003/run.log
ws/MOF-5/scan-scan-003/scan.csv
ws/MOF-5/uff-single-point-001
ws/MOF-5/uff-single-point-001/run.log
ws/MOF-5/uff-single-point-002
ws/MOF-5/uff-single-point-002/run.log
ws/pcu-N16-E14
ws/pcu-N16-E14/mof-build-001
ws/pcu-N16-E14/mof-build-001/run.log
ws/pcu-N16-E14/pcu-N16-E14.cif
ws/workspace.json
```

Reading it from the top:

`workspace.json`
: The marker that makes a directory a workspace.  It names the
  format and its version, and nothing else that the files themselves
  do not say -- it is not an index, and the application never trusts
  it over the directory:

  ```json
  {
   "format": "crystal-builder-workspace",
   "version": 1
  }
  ```

  Once the window has worked in a workspace the file also carries a
  `session` key (below).

`MIL-53/`, `MOF-5/`, `MOF-5-2/`, `pcu-N16-E14/`
: One **entry** per structure, named after the file it came from (or
  after what was built).  The entry folder holds a copy of the
  structure -- `MIL-53/MIL-53.cif` -- so that the workspace is whole
  on its own, and, once the window has saved it, the session beside it
  as `MIL-53.xtalproj` ({doc}`Save converts </essentials/file>`).
  None of these entries has a project file yet, because nothing here
  was opened in a window.

`uff-optimise-001/`, `scan-scan-002/`, `pxrd-pxrd-003/` ...
: One **run folder** per calculation, named `<module>-<kind>-<nnn>`
  by what made it -- the UFF engine's optimisation, the scan module's
  run, the PXRD module's pattern -- and numbered across the whole
  entry in the order the runs happened, so the folders sort into the
  order anybody looking for *the one I ran after lunch* wants.  The
  number is derived by looking at what is already there, not stored
  anywhere.  What is inside is the {doc}`next page <reports>`.

`blocks/`
: The one folder in a workspace that is not an entry: a building
  block drawn in the MOF builder is saved here, and the catalogue
  reads it alongside PORMAKE's ({doc}`building blocks
  </frameworks/blocks>`).  It appears when the first block is drawn,
  which is why the tree above has none.

`.autosave/`
: Where the window keeps the unsaved edits of each tab, mirroring the
  file's place in the workspace (`MOF-5/MOF-5.cif` is kept as
  `.autosave/MOF-5/MOF-5.xtalproj`).  A dot-folder, so the tree never
  shows it and never mistakes it for an entry; absent here because the
  command line edits nothing.

## Entries: how a structure gets one

:::{note}
**Every document has an entry, whichever door it came through.**
A file opened from outside is copied in and the tab follows the
copy; where it came from is remembered and still names the tab when
that file is opened again.  *File ▸ New* makes `untitled`, then
`untitled-2`, at once, because a structure with nowhere to be is one
whose first run has nowhere to land.  *Open Sample* copies the
bundled CIF in and opens the copy.  A build is filed as one entry
named after what was built.  On the command line, `--workspace` on
`energy`, `optimize` and `run` does the same copying and filing.
:::

:::{note}
**Entries are de-duplicated by content, never by name.**  Two
people's `MOF-5.cif` are two structures.  The tree above shows it:
`resources/samples/prepared/MOF-5.cif` became `MOF-5/`, and the
deposited `resources/samples/cod/MOF-5.cif` -- same name, different
file -- became `MOF-5-2/`, each holding its own `MOF-5.cif`.  Running
the *same* file twice files both runs under the one entry
(`MOF-5/uff-single-point-001` and `-002`).  Deciding by name alone
would have silently copied the second file over the first.
:::

```{index} single: workspace; de-duplication
```
```{index} single: workspace; builds filed in
```

**A build is filed as one entry, one CIF, one run.**  A module that
builds a structure has no name for it until it finishes, so its run
folder is opened under a placeholder named for the module and moved
under the framework once there is one to name it after; and one CIF
is written from the finished structure -- the framework with its net
drawn over it -- rather than keeping the builder's own intermediate
copy.  The command reports where it went:

```console
$ xtal run mof.build -p topology=pcu -p nodes=N16 -p edges=E14 --workspace ws
PORMAKE: building pcu-N16-E14
[...]
filed as ws/pcu-N16-E14/pcu-N16-E14.cif
53 atoms; the framework is pcu, as asked -- blocks fit to 0.000 A, closest contact 2.33 A, 6 joint(s) bonded
[...]
run folder: ws/pcu-N16-E14/mof-build-001
```

This filing is a rule of the workspace, not of the window, which is
why `xtal run mof.build --workspace` leaves exactly what the MOF
builder's **Build** button leaves.

## Run folders: who writes them

The module that runs writes its own folder -- the engine's recorder
for `energy` and `optimize`, the module registry's for `run` -- and
the tree that displays it only reads.  That is what makes a run
started from a script identical to one started from a panel, and
openable in the window afterwards: the *Workspace* panel
({ref}`panel-file_dock`) shows the folder above as it is, and clicking
a node opens it as what it is -- a structure in a tab, a trajectory
in the transport bar, a log in the {ref}`Log panel <panel-log_dock>`,
a report in the {ref}`Results panel <panel-results_dock>`.

Two things about run folders follow from the window's side:

- **A tab belongs to the workspace it was opened in**, because its
  runs are filed there; changing workspace closes every tab
  ({doc}`files and workspaces </essentials/file>`).
- **A workspace remembers its own tabs.**  `workspace.json` carries a
  `session` key of paths relative to the root, written whenever the
  tabs change, and read when the workspace is opened again.  It is
  advisory: a file that has gone is skipped in silence.  The
  command line neither writes nor reads it.

```{index} single: workspace.json; session key
```
```{index} single: autosave; where kept
```

## Autosaves

:::{note}
**An autosave is a side file, never the document.**  Every two
minutes (*Preferences ▸ General*; 0 is off) each tab edited since the
last tick is written as a project into `.autosave/`, mirroring its
place in the workspace and never where Save writes.  It is deleted
when the document is clean again -- saved, or undone back to the file
-- and when unsaved work is deliberately discarded, so what is left is
exactly the work nobody chose to lose.  It is offered back, never
applied: opening a file with a newer autosave shows a notice bar, and
*Restore* is one undo step.
:::
