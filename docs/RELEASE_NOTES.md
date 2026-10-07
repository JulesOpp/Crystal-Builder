# Crystal Builder

Build, manipulate, analyse and export crystal structures. Read and
write CIF, edit symmetry and bonding, run a force field, DFTB+ or
Zeo++ on the result.

## Crystal Builder 1.0

The first stable release. The 0.x previews were put out to be used
and argued with, and what their testers found is in here; they have
been retired in its favour.

## What it does

- **Structures in and out**: CIF with its bonds, a project
  (`.xtalproj`) that keeps the view, measurements and runs beside the
  crystal, and export to LAMMPS (atom style full, with the bonds as
  drawn), periodic PDB for PyMOL, VMD and Mercury, POSCAR and XYZ. A
  computed charge (EQeq, Mulliken) goes into the CIF's
  `_atom_site_charge`, where RASPA and Zeo++ read it.
- **Symmetry and cells**: space groups and their subgroups,
  Standardize, primitive and supercells, *Cell ▸ Slab…* along (hkl)
  with vacuum and the bonds carried, *Cell ▸ Move origin…*, and
  *Structure ▸ Prepare for simulation…*, which merges duplicates,
  orders disorder, removes solvent and adds hydrogens in one undo
  step that says what it chose.
- **Bonding you stay in charge of**: bonds change only when you press
  *Recalculate Bonds* -- never on load, on an edit or after an
  optimisation -- and a bond type set by hand always wins.
- **Builders**: a MOF from a net, a node and a linker (PORMAKE, with
  its 867 blocks and the RCSR nets); a molecule drawn in the 2D
  sketcher, metals built with their coordination shape; a disordered
  carbon (zeolite-templated or schwarzite) as one terminated sheet
  that follows a net; an amorphous polymer packed into a box or a
  membrane from eleven library monomers or your own; guests placed
  in the pores; a hydrogen replaced by a whole functional group.
- **Calculations**: UFF with UFF4MOF, xTB, DFTB+ (with band
  structures and densities of states), and MACE, ORB-v3 and MatterSim
  from Python; optimisation that keeps the space group; scans that
  hold a distance, angle or cell volume and write each point as it
  finishes; a bulk modulus from an equation of state; porosity with
  Zeo++ or our own faster grid, with the pores drawn where they are.
- **Powder diffraction**: a pattern from the structure, and a
  refinement workbench (peaks, indexing, Pawley, Rietveld, Rietveld
  with energies) against a measured `.xy` or a diffractometer's own
  file (`.rasx`, Bruker `.raw`, `.uxd`, `.xrdml`), with a TOPAS-like
  parameter table.
- **Seeing the chemistry**: ball-and-stick, polyhedra, and a Skeletal
  style drawn as a chemist would on paper; *Style ▸ Rings* fills each
  ring by size; *Colour by* bond length, coordination, angle, smallest
  ring or charge; atom groups (*View ▸ Group selected atoms…*,
  Ctrl+G) to name, colour and hide a set of atoms, made for you from
  a CIF's SHELX disorder PARTs.
- **An AI assistant can work in the window**: *Help ▸ Connect an AI
  assistant…* lets any MCP client drive the open tabs, each change
  one undo step in front of you.
- **Samples to start from**: textbook solids, polymers, and MOFs from
  the COD, under *File ▸ Open Sample*.

## Made to be dependable

- **Saving never destroys the last good file.** Every file is written
  beside the old one and swapped in only once complete, and an
  autosave every two minutes is offered back after a crash.
- **Large structures are counted before they are built.** Over a
  soft limit you are asked, over a hard one it is refused with the
  largest size that fits; *Preferences ▸ General ▸ Large structures*
  sets how cautious (Standard for 8 GB machines, Generous, or Warn
  only). Undo lets go of what it can rebuild.
- **A running calculation holds its tab**: an edit made under it is
  refused with a message rather than lost, a result goes to the tab
  it ran on, and quitting or changing workspace asks before stopping
  it.
- **The CIF reader says what it assumed**: repeated labels renamed, a
  missing cell refused by name, unmatched symmetry operations
  reported.
- **Errors are one box at a time**, with *Copy details* and *Send
  feedback…*; a hard crash leaves its stack in `faults.log`.

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
- **RDKit and the 2D sketcher**, so *Build a molecule with the 2D
  sketcher…* and every window that draws a molecule work.
- **matplotlib**, for the PXRD pattern window: zooming, overlaying a
  measured `.xy` file, and exporting the figure as a vector.
- **The refinement workbench.** RietX is bundled, so Pawley and
  Rietveld fits need nothing else.
- **The carbon and polymer builders**, with the monomer library.
- **The `xtal` program** beside the application, which an AI
  assistant connects through.

*Help ▸ About* links the third-party notices: the software and data
the download carries, and the licence of each.

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
- **The builds are not code-signed** (see *Opening it the first
  time*). Signing is planned for a 1.0.x release.
- **A CIF whose symmetry operations match no tabulated setting** is
  read in the tabulated group its space-group symbol names, and the
  reader says so. Building the group from the file's own operations
  is planned.
- **On a very large structure the window pauses** while an autosave
  or a whole-structure operation runs, because both run on the
  window's own thread. The size limits keep this short; moving them
  off it is planned.
- **A polymer model is packed, not equilibrated.** Its density and
  contacts are right; its chains have not relaxed at their own scale,
  which takes molecular dynamics this application does not run.
- **What 1.0 does not do**, so nobody looks for it: adsorption
  (GCMC, Henry coefficients) -- write the CIF, with its charges, for
  RASPA; molecular dynamics with the machine-learned engines (DFTB+'s
  own MD is there); fetching structures from the COD, CoRE MOF or the
  Materials Project; input files for VASP, Quantum ESPRESSO or CP2K
  beyond the POSCAR. Each is on the list for after 1.0.
- **Style ▸ Rings refuses a graph too dense to search** -- a
  deposited CIF with its symmetry copies written as sites, or a
  close-packed salt -- and says so in the legend. *Prepare for
  simulation* first.

## Reporting something

*Help → Send Feedback…* is the quickest way: it composes the email,
with the end of the log for a bug, and opens it in your mail client.

*Help → Show log file* reveals a rotating log file that records start-up,
plugin failures, external process output and any uncaught exception's
traceback. Attaching it turns "it closed" into something that can be
fixed.
