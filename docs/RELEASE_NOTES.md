# Crystal Builder

Build, manipulate, analyse and export crystal structures. Read and
write CIF, edit symmetry and bonding, run a force field, DFTB+ or
Zeo++ on the result.

## New since 0.2.1

- **Three more machine-learned potentials**: ORB-v3 and MatterSim
  beside MACE, and **EQeq charges** for the force field.
  *Preferences → Engines* lists every package a feature needs, with
  an install command that works for the Python it is running in.
- **A library of real frameworks**: sixteen MOFs from the
  Crystallography Open Database (CC0), under *From the COD* in Open
  Sample.
- **The MOF builder builds chelating blocks.** A connection point can
  be several atoms (*Mark as one connection point*), so MFU-4l and
  Ni3(HITP)2 build from their own nodes. Symmetric nodes are turned
  so that the faces across every edge agree, which builds MOF-5 with
  its clusters alternating. Blocks and nets can be searched by name,
  denticity and MOF+ fields, and the RCSR's layer nets can be built
  and stacked.
- **Interpenetration**: *Structure ▸ Interpenetrate…*, or ask the MOF
  builder for it. Copies closer than a bond are refused by name.
- **More file formats**: POSCAR/CONTCAR, mmCIF, pymatgen's JSON, and
  ASE trajectories in the playback bar.
- **Work is not lost.** Every two minutes, edited tabs are autosaved
  to a side file, and a newer autosave is offered back when the file
  is opened. Quitting asks before it stops a running calculation.
  Each workspace reopens the tabs it had.
- **The first minute**: a start pane while no tab is open, a wider
  viewport in the first window, and a reason given for anything
  greyed out, converted or refused.
- **Faster and leaner**: a cell relaxation step is one evaluation, a
  drag on MFU-4l is a third quicker, the pore surface takes a quarter
  of the memory, and Ball and stick (occupancy) turns as fast as
  plain Ball and stick. A structure with no view of its own now
  opens in that style, and the optimiser starts on *Smart*.

## Fixed in 0.3.0

- **A finished calculation no longer hangs or aborts the
  application.** The worker-thread teardown race listed as a known
  issue in 0.2 is fixed.
- Stop works under an engine that computes in this process.
- During playback, editing commands stay greyed out.
- A symmetry copy of a bond joins the atoms it found, not their
  wrapped positions. A label the CIF grammar cannot carry bare no
  longer damages the file. A file whose own symmetry repeats its
  atoms says so when it opens.
- A repeated net is drawn through every cell it tiles, without
  diagonals across the box.

## Downloads

| You have | Download |
|---|---|
| A Mac with Apple silicon (M1 and later) | `Crystal-Builder-<version>-arm64.dmg` |
| A Mac with an Intel processor | `Crystal-Builder-<version>-x86_64.dmg` |
| Windows, 64-bit | `Crystal-Builder-<version>-setup.exe` |

The Mac builds need **macOS 12.3 (Monterey) or later**.

There is no universal Mac build, and that is not an oversight: VTK
publishes no universal2 wheel, so the two have to be built separately.
Pick the one that matches your Mac — About This Mac says which. An
Intel build cannot be made to run on Apple silicon by Rosetta, which
translates the other direction.

## Opening it the first time

**Neither build is code-signed yet**, so both operating systems will
say so, in the way each of them says it. Nothing here is a way around
a security warning; it is what the warning is for and how to answer it
if you trust where you got the file.

**macOS.** Double-clicking gives *"Crystal Builder" cannot be opened
because the developer cannot be verified*. Right-click (or
Control-click) the app in Applications and choose **Open**, then
**Open** again in the dialog. macOS remembers the choice and normal
double-clicking works afterwards. If the app was quarantined in a way
that will not clear, the equivalent from a terminal is:

```bash
xattr -dr com.apple.quarantine "/Applications/Crystal Builder.app"
```

**Windows.** SmartScreen shows *Windows protected your PC*. Click
**More info**, then **Run anyway**. The installer is per-user: it
needs no administrator rights and installs under your own AppData, so
it works on a managed machine.

A Developer ID certificate for macOS and a code-signing certificate
for Windows are what remove both of these. They are on the list.

## File associations

The installer offers `.cif` and `.xtalproj` associations. `.cif` is
**unticked by default** and macOS registers it as an alternate handler
rather than the owner, because a `.cif` on a working machine usually
already belongs to VESTA or Mercury and quietly taking it is not a
friendly thing for an installer to do. Tick it if you want it.

Double-clicking a structure works both when the application is closed
and when it is already open.

## What is in the download, and what is not

Bundled and working, with nothing to install:

- **The MOF builder.** PORMAKE is vendored into the application — its
  867 building blocks and the RCSR topologies included — so a
  framework from a net, a node and a linker needs nothing else.
- **RDKit and rdeditor**, so *Build from SMILES* and the molecule
  sketcher both work.
- **matplotlib**, for the PXRD pattern window: zooming, overlaying a
  measured `.xy` file, and exporting the figure as a vector.

**MACE, ORB-v3 and MatterSim are not included.** They need PyTorch,
which is gigabytes and wants to arrive differently on every platform.
The Force Field panel lists them and greys them out; run from Python
to use them (*Preferences → Engines* gives the exact command):

```bash
pip install 'crystal-builder[gui,mace]'   # or [gui,orb], [gui,mattersim]
crystal-builder
```

**Zeo++, DFTB+, tblite and xtb are found, never carried.** They have
their own licences and citation terms, and several are conda packages.
Install them however you normally would and point at them in
*Preferences → Engines*, which says what it looked for and where, and
has a Test button for each. `XTAL_ZEOPP`, `XTAL_TBLITE`, `XTAL_XTB`,
`DFTB_PREFIX` and `PATH` all still work.

**Plugins installed with `pip` do not load in a packaged build.** A
frozen application has no `pip` and nowhere to install one to, so the
shipped build runs in-tree modules only. *Preferences → Engines*
offers a folder that is added to the import path at
start-up, which works for pure-Python packages. Run from Python if you
need more than that.

## Known issues

- **The version shown in Help → About is the git tag the build was
  made from.** If it reads `0.0.dev0` or `0.0.0`, the build is broken
  and worth reporting.

## Reporting something

*Help → Show log* reveals a rotating log file that records start-up,
plugin failures, external process output and any uncaught exception's
traceback. Attaching it turns "it closed" into something that can be
fixed.
