# Troubleshooting

When something refuses, the application usually says why, in the
status bar, in a greyed-out entry's tooltip, or in a note under the
control.  This page collects those sentences and the known
limitations of this release, and says what to do about each.

```{index} single: troubleshooting
```

## Starting up

**The application will not open.**  On macOS, *"Crystal Builder"
cannot be opened because the developer cannot be verified*; on
Windows, *Windows protected your PC*.  Neither build is code-signed
yet.  {doc}`installation` says how to open it the first time.

**Help ▸ About says `0.0.dev0` or `0.0.0`.**  The build is broken --
the version is the tag it was made from, and a build that carries
none is missing its metadata.  Report it.

**The window comes up, the 3D view stays empty, and nothing responds.**
On a source install this is PySide6 6.10 or later: VTK's Qt bridge
repaints forever at 100 % of a core.  Install a PySide6 below 6.10,
which is the bound `pyproject.toml` declares, and run
`crystal-builder --selftest` to confirm the view draws.

**The window opened with no workspace.**  The folder the chooser was
given could not be made or written, and the window opens anyway
rather than not at all.  Runs and builds then have nowhere to land;
the status bar says so when one finishes.  *File ▸ Open Workspace…*
or *File ▸ New Workspace…* fixes it.

## Greyed-out entries

**A module entry is greyed out.**  Hover it: the tooltip is the
reason.  For an external program it reads like *Zeo++ is not
installed, or not on PATH (XTAL_ZEOPP is not set).  It is at
https://www.zeoplusplus.org/* -- every place that was looked in is
named, because a path that was set and is a typo looks exactly like
one that was never set.  *Preferences ▸ Engines* has a **Browse…** and
a **Test** button for each program, and a change there lights the
entry up without a restart.  Under {ref}`external-programs` is the
table of what each program powers.

**A menu entry names an extra.**  *Insert molecule*, the sketcher,
the pattern window and the MOF builder each need a Python package,
and grey out naming it (`build`, `sketch`, `pxrd`, `ase`).  On a
source install, *Preferences ▸ Engines* gives the exact command for
the Python the application is running in.  In a packaged build all
four are already there; the three machine-learned engines are not,
and cannot be added to a packaged build -- run from Python for those.

**Everything editing is greyed out.**  A trajectory is being played:
the atoms on screen are a frame, not the structure.  *Adopt this
frame* in the Trajectory panel keeps the geometry as one undoable
edit; closing the trajectory brings the structure back.

## Running things

**"a module is already running -- stop it first".**  One module run
at a time.  The Modules panel has the Stop button.

**"… needs a structure open".**  The entry acts on the tab in front,
and there is none.

**"close the trajectory first -- these atoms are a frame being
played, not the structure".**  As above: adopt the frame or close
the trajectory.

**"could not copy into the workspace: …".**  A file opened from
outside is copied into the workspace, and the workspace folder could
not be written.  The tab still opens, but nothing is kept; switch to
a workspace you can write to.

**The optimiser stopped before converging.**  The note under the
report says which half -- the forces or the cell -- is still above its
tolerance, and the geometry is where it got to, not a minimum.  Press
**Optimise** again to carry on.  A run whose line search found nowhere
downhill to go says that rather than looking like the step limit.

**"n site(s) have a type the typer is not sure of".**  UFF has no
row fitted for that environment -- an octahedral zinc, say, or the
nickel of a trimer.  The row can be overridden from the drop-down in
the Force Field panel's table; the energy is a plausible number
either way, which is why the note exists.

**The relaxed cell moved a long way.**  A cell relaxed under UFF is a
UFF cell, and the panel says to use it as a starting geometry.  A
build from the MOF builder starts from PORMAKE's scaled cell, which
is a fit and can be far from the relaxed one; the first build in this
chapter loses 45 % of its volume.

**A scan was stopped and cannot be carried on.**  `scan.csv` in the
run folder holds every finished point, but there is no resume in this
release; a stopped scan is restarted ({doc}`/structure/scans`).

**The application crashed and its program is still running.**  Stop,
{kbd}`Ctrl+C` and a normal quit all end a run's external program.  A
crash of the application itself does not; end the `network`, `dftb+`
or `xtb` process by hand.

## xTB

**GFN2-xTB or GFN1-xTB crashes on a periodic cell.**  The GFN
methods are one binary each, and it is not by choice: tblite 0.3.0
runs GFN1 and GFN2 under a cell; tblite 0.6.0 segfaults on GFN2;
xtb refuses periodic GFN2 (*Multipoles not available with PBC*) and
segfaults on periodic GFN1.  So GFN1 and GFN2 go to tblite, GFN-FF to
xtb, and GFN2 needs a tblite that works.  Both crashes are the
programs' own ({doc}`/energy/xtb`).

## Symmetry

**Find symmetry finds only P1.**  Raise the tolerance.  The dialog
re-detects as you change it; 0.1 Å is its default, and where this
chapter's relaxed build declared itself.

**"This cell is not in the standard setting of …".**  Adopting the
group with *Re-express the cell in the standard setting first* ticked
will move the atoms into that setting, and the view resets to frame
the new cell.  Untick the box to keep the cell as it is.

**The net vanished after Find symmetry.**  Re-expressing the cell
drops the drawn net.  Draw it again with *Draw net*: one edge expands
over the orbit, so it is usually one click per kind of edge.

**Merge duplicates says "no duplicates" but atoms have doubled.**  A
site far enough off a special position for the group to generate two
of it is invisible to *Merge duplicate sites…*, which compares a site
against *other* sites' images and never against its own, at any
tolerance.  *Standardise cell* is what snaps a site onto its
position ({doc}`/essentials/symmetry`).

## Interface

**Panels are lost or squeezed.**  *Window ▸ Reset layout* puts every
panel back where it starts.

**The Move panel's buttons are live with nothing selected**, and
**the Trajectory panel's labels overlap when it is narrower than
about 440 px.**  Both are known in this release and neither does
harm; widen the panel, or select something first.

**Screen readers have little to read.**  The input widgets carry no
accessible names in this release; the tooltips are most of the text.

## Installing the machine-learned engines

**`pip install 'crystal-builder[orb]'` says it does not provide the
extra.**  The package is not on PyPI; install the checkout by path,
as *Preferences ▸ Engines* prints it.

**Installing `orb` stops while building dm-tree.**  On Python 3.13
with CMake 4, set `CMAKE_POLICY_VERSION_MINIMUM=3.5` in the
environment and run the install again.

**`mace` and `mattersim` will not install together.**  mattersim asks
for e3nn 0.5 where MACE pins 0.4.4, and runs on 0.4.4.  Install `mace`
first, then the command *Preferences ▸ Engines* gives for MatterSim,
which leaves mattersim's own dependencies out.

## Reporting something

*Help ▸* {ref}`Show Log <cmd-show_log>` reveals a rotating log file
that records start-up, plug-in failures, external process output and
any uncaught exception's traceback.  Attaching it to a report turns
"it closed" into something that can be fixed.  The version to quote
is in *Help ▸ About Crystal Builder*.
