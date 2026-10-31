# Crystal Builder

Build, manipulate, analyse and export crystal structures. Read and
write CIF, edit symmetry and bonding, run a force field, DFTB+ or
Zeo++ on the result.

## Crystal Builder 1.1

Everything since 1.0, released on 2026-10-07. Install it over 1.0;
your workspaces and preferences carry over.

### New builders

- **Modules ▸ Carbon builder**, from 0D to 3D in one submenu:
  - **Fullerenes** from their face spirals: every isomer up to C40
    and the isolated-pentagon ones from C60 to C100, optionally
    hydrogenated (CnHn), relaxed with UFF.
  - **Nanotubes** from (n,m) and a length: periodic, or finite with
    hydrogen-capped ends; carbon or BN; the bond length from covalent
    radii unless you give one.
  - **Graphene** of any two elements, any supercell or the
    rectangular cell, stacked AA, AB, ABC or AA′ as bulk or a slab,
    and **twisted bilayers** at a commensurate angle, with the
    nearest angles under the size limit listed for the one you type.
  - *Disordered carbon…* moves into the same submenu.
- **Reticular design in the MOF builder**: partitioned pores (pacs),
  with linkers suggested by the distance they span and new ones
  invented; zeolitic supertetrahedral frameworks; merged nets; rod
  SBUs (MOF-74, Ni2Cl2BTDD and Zn(BDP), cut from Co(BDP)'s rod), each
  rod saying whether its neighbours are one hand or alternate; and a
  hand-off to TopCryst. Co(BDP) joins the COD samples.

### Calculations

- **Thermochemistry** under any engine (*Force Field ▸
  Thermochemistry…*): harmonic, quasi-RRHO and ideal-gas free
  energies from a Gamma-point Hessian (MACE's own where it has one),
  phonons with phonopy (bundled), an IR spectrum that names the charge
  model it came from, and the quasi-harmonic F(V, T) over a volume
  scan. An imaginary mode is counted and never summed, and the
  summary says so.

### Files and data

- **SHELX `.res` and `.ins` files open** like a CIF, each non-zero
  PART an atom group, with occupancies and free variables resolved.
- **Export data…** on every histogram in the Results panel: the pore
  size distribution as a CSV with its cumulative column, and the
  carbon builder's ring sizes.
- A `.xy` file written with decimal commas (`10,00  100,5`) is refused
  by name instead of read as four columns of nonsense.

### Seeing the structure

- **View ▸ Along (hkl)…** looks straight onto a lattice plane; the
  dialog stays open so (100), (110), (111) can be stepped through.
  `xtal render --view "(1,1,0)"` does the same.
- **Find symmetry** names the sites that sit off the special
  positions of the group it found, with how far, and offers to snap
  them on.

### The AI assistant

- **Every change it makes is labelled and can be taken back in one
  click**: the *Agent changes* strip names its latest request, with
  Revert, Restore and History, and the assistant is told when you
  reverted its work or edited in between.
- **It can read and change how a tab looks**: style, ring filling,
  Colour by, polyhedra, labels, display range, colours and opacities.
- **Chat clients such as Claude Desktop get the same playbook** that
  Claude Code reads, served over MCP.

### Platforms and the window

- **Linux: an AppImage for x86_64 (Ubuntu 22.04+, Debian 12+, Fedora
  36+).** One file: make it executable and double-click it. See
  *Linux* under *Opening it the first time*. With thanks to Jose Ivan
  (@jigonzalez930209).
- **Help ▸ Check for Updates…** asks GitHub for the latest release
  and offers to open its page. Nothing is downloaded or installed for
  you.
- **Shortcuts** (Ctrl for ⌘ on Windows and Linux): Export is ⌘E,
  Optimise geometry ⌘M, New workspace ⌘⇧N, and Measure selection
  moves to ⌘⇧M; Single point energy no longer has one. The workspace chooser answers ⌘N, ⌘O and ⌘Q before
  any window is open.

### Fixed

- A framework with a bond longer than 6 Å was built but could not be
  saved (Jose Ivan).
- Bond lengths in `inspect`, `xtal bonds` and saved projects are
  measured where the atoms are now, not where they were when the
  bonds were found.
- Rietveld with energies says when a free cell has moved its lines
  out of the peak windows it compiled, and reading the background no
  longer leaves two steps in the fit's history.
- Two crashes: one on closing a window (Windows), and one after a
  dialog refilled a list that had greyed entries.
- The View menu's Orthographic and Labels ticks follow the tab in
  front.
- rietx is written in lowercase, at its author's request.

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
| Linux, x86_64 | `Crystal_Builder-<version>-x86_64.AppImage` |

The Mac builds need **macOS 12.3 (Monterey) or later**. The Linux
AppImage needs **glibc 2.35 or newer** (`ldd --version` shows it):
Ubuntu 22.04 or newer, Debian 12 or newer, Fedora 36 or newer. RHEL 9
and its rebuilds (glibc 2.34) and openSUSE Leap 15 (2.31) are not
supported.

There is no universal Mac build, and that is not an oversight: VTK
publishes no universal2 wheel, so the two have to be built separately.
Pick the one that matches your Mac — About This Mac says which. An
Intel build cannot be made to run on Apple silicon by Rosetta, which
translates the other direction.

## Opening it the first time

**The macOS and Windows builds are not code-signed yet**, so both
operating systems will say so, in the way each of them says it.
Nothing here is a way around a security warning; it is what the
warning is for and how to answer it if you trust where you got the
file.

**macOS.** Double-clicking gives *"Crystal Builder" cannot be opened
because the developer cannot be verified*. Close the warning, open
*System Settings ▸ Privacy & Security*, scroll down to *Security*,
and click **Open Anyway** beside the message about Crystal Builder,
then confirm with your password. macOS remembers the choice and
normal double-clicking works afterwards. If the app was quarantined
in a way that will not clear, the equivalent from a terminal is:

```bash
xattr -dr com.apple.quarantine "/Applications/Crystal Builder.app"
```

**Windows.** SmartScreen shows *Windows protected your PC*. Click
**More info**, then **Run anyway**. The installer is per-user: it
needs no administrator rights and installs under your own AppData, so
it works on a managed machine.

A Developer ID certificate for macOS and a code-signing certificate
for Windows are what remove both of these. They are on the list.

**Linux.** Make the AppImage executable and run it:

```bash
chmod +x Crystal_Builder-*.AppImage
./Crystal_Builder-*.AppImage
```

or mark it executable in its properties in your file manager and
double-click it. On a Wayland desktop the window runs on XWayland,
because the 3D view draws on X11 only; a Wayland session without
XWayland is not supported, and a `QT_QPA_PLATFORM` you set yourself
always wins.
Settings are in `~/.config/CrystalBuilder/CrystalBuilder.conf`; the
log is in `~/.local/share/CrystalBuilder`.

## File associations

The installer offers `.cif` and `.xtalproj` associations. `.cif` is
**unticked by default** and macOS registers it as an alternate handler
rather than the owner, because a `.cif` on a working machine usually
already belongs to VESTA or Mercury and quietly taking it is not a
friendly thing for an installer to do. Tick it if you want it.

Double-clicking a structure works both when the application is closed
and when it is already open.

On Linux the AppImage makes no menu entry or file associations of its
own; AppImageLauncher or Gear Lever adds a menu entry, and the file
types where the integrator installs them.

## What is in the download, and what is not

Bundled and working, with nothing to install:

- **The MOF builder.** PORMAKE is vendored into the application — its
  867 building blocks and the RCSR topologies included — so a
  framework from a net, a node and a linker needs nothing else.
- **RDKit and the 2D sketcher**, so *Build a molecule with the 2D
  sketcher…* and every window that draws a molecule work.
- **matplotlib**, for the PXRD pattern window: zooming, overlaying a
  measured `.xy` file, and exporting the figure as a vector.
- **The refinement workbench.** rietx is bundled, so Pawley and
  Rietveld fits need nothing else.
- **The carbon and polymer builders**, with the monomer library and
  the fullerene isomers.
- **phonopy**, for phonons and the quasi-harmonic free energy.
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
- **What 1.1 does not do**, so nobody looks for it: adsorption
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
