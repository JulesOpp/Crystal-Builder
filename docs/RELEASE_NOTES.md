# Crystal Builder

Build, manipulate, analyse and export crystal structures. Read and
write CIF, edit symmetry and bonding, run a force field, DFTB+ or
Zeo++ on the result.

## New since 0.1.0

- **Relaxed energy scans** over any coordinate, lattice parameter or
  the volume, holding the coordinate rather than freezing atoms. The
  landscape is drawn clickable, walked in both directions, and every
  point is written to disk as soon as it finishes.
- **More engines**: xTB (GFN2, GFN1 through tblite; GFN-FF through
  xtb), MACE, plain UFF beside UFF4MOF, and Forcite-style optimisers.
- **DFTB+ runs of its own**: band structure with its Brillouin zone,
  projected density of states, Mulliken charges and orbitals, the
  DFTB+ driver for relaxation and MD, and vibrational modes that play.
- **Porosity you can see**: Zeo++ channel networks, accessible volume
  and the accessible surface drawn over the crystal.
- **The MOF builder ships inside the application**, including blocks
  you draw yourself; pores can be filled with guest molecules.
- A **workspace chooser** at start-up, one *Engines* page with a Test
  button per program, a Style panel that reflows, STL export through
  Blender, and non-centred subgroups.
- **Windows**: Stop now ends a program started through a wrapper
  script, and files holding non-ASCII text (a Γ in a band path, an
  accented folder name) are written and read as UTF-8.

## Downloads

| You have | Download |
|---|---|
| A Mac with Apple silicon (M1 and later) | `Crystal-Builder-<version>-arm64.dmg` |
| A Mac with an Intel processor | `Crystal-Builder-<version>-x86_64.dmg` |
| Windows, 64-bit | `Crystal-Builder-<version>-setup.exe` |

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

**MACE is not included.** It needs PyTorch, which is gigabytes and
wants to arrive differently on every platform. The Force Field panel
lists it and greys it out; run from Python to use it:

```bash
pip install 'crystal-builder[gui,mace]'
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

- **A calculation that finishes can occasionally hang the
  application.** There is a lock-order inversion between Qt's
  connection mutex and the GIL in the worker-thread teardown: PySide6
  can free a `QThread`'s Python wrapper during signal delivery, which
  calls back into Python while Qt holds the mutex. It is being worked
  on. If it happens, the log written by *Help → Show log* is the
  useful thing to attach to a report.
- **The version shown in Help → About is the git tag the build was
  made from.** If it reads `0.0.dev0` or `0.0.0`, the build is broken
  and worth reporting.

## Reporting something

*Help → Show log* reveals a rotating log file that records start-up,
plugin failures, external process output and any uncaught exception's
traceback. Attaching it turns "it closed" into something that can be
fixed.
