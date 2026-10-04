# Crystal Builder

Build, manipulate, analyse and export crystal structures. Read and
write CIF, edit symmetry and bonding, run a force field, DFTB+ or
Zeo++ on the result.

## Crystal Builder 1.0

The first release meant to be relied on. Everything since 0.4.0 is
below; the fixes that close it out were made for one concern above
the rest -- a large cell on a machine short of memory should be
asked about, not crash -- and for files that must never be lost.

## New since 0.4.0

- **Disordered carbon**: *Modules ▸ Build a disordered carbon…*
  makes a zeolite-templated carbon or a schwarzite as one connected,
  terminated sheet that follows a net, at the density asked for, with
  Stone-Wales defects and the rings Gauss-Bonnet fixes said up front.
  `xtal run carbon.build` does the same from a script.
- **Amorphous polymers**: *Modules ▸ Build an amorphous polymer…* packs
  chains of a monomer -- eleven in the library, a starred SMILES, the
  sketch, or one drawn and saved with *Structure ▸ Building blocks ▸
  Save as a monomer…* -- into a periodic box or a membrane at a
  target density, homopolymer or copolymer, at any tacticity, ladders
  such as PIM-1 included. The model is packed, not equilibrated, and
  the report says so.
- **Seeing the chemistry**: *Style ▸ Rings* fills each ring with a
  face coloured by its size; *Colour by* draws bond length,
  coordination, angle, smallest ring or charge as a colour bar; the
  Skeletal style draws a structure as a chemist would on paper, and
  exports to SVG as text and strokes.
- **Functional groups**: found, selected and shown by pattern, and a
  hydrogen replaced by a whole group -- one from the library or one
  you draw -- bonded as built, keeping the space group where the
  substituent allows.
- **Bulk modulus** from an equation of state through a volume scan.
- **Slabs, LAMMPS and PDB**: *Cell ▸ Slab…* cuts along (hkl) with
  vacuum above and carries the bonds; Export writes a LAMMPS data
  file, atom style full, with the bonds as drawn, and *Open…* reads
  one back with its charges and bonds; Export writes a periodic PDB
  for PyMOL, VMD and Mercury; a computed charge (EQeq, Mulliken) is
  written to the CIF's `_atom_site_charge`, where RASPA and Zeo++
  read it. *Cell ▸ Move origin…*, *Select ▸ Advanced selection…* and
  *File ▸ Render in Blender…* join them.
- **A tidier window**: the Modules menu leads with the builders
  (*Build a molecule with the 2D sketcher…* replaces *Molecule from
  SMILES…*); the Force Field panel puts Single point and Optimise
  under the model and folds the atom types away; the Style panel
  gathers the pore controls into one group and hides rows that belong
  to another style; the mouse modes are Ctrl+1 to Ctrl+7.
- **Powder refinement**: a TOPAS-like parameter table on every
  fitting step, a diffractometer's own file (`.rasx`, Bruker `.raw`,
  `.uxd`) read directly, every tick naming its reflection, and zero
  cycles as an evaluation.
- **An AI assistant can work in the window**: *Help ▸ Connect an AI
  assistant…* lets any MCP client drive the open tabs, each change
  one undo step in front of you, and the packaged app carries the
  `xtal` program it connects through.
- **More to open**: *Open Sample ▸ Simple materials* (eighteen
  textbook solids), *Polymers* (polyethylene, alpha-iPP, cellulose
  I-beta), and UiO-67, PCN-224, SIFSIX-3-Ni and SIFSIX-1-Cu from the
  COD. Opening a file already open offers a fresh copy beside it.
- **The MOF builder** states the bonds a framework is built with and
  says when two atoms overlap; a linker is drawn as written where
  nothing prefers an angle, and turned for room before it is turned
  for its faces.
- **Fill pores** can put one guest at a point, or one beside each
  selected atom; the pore sphere can be D_i, D_if or any cavity.

## Fixed for 1.0

- **Saving never destroys the last good file.** A project, a CIF and
  a LAMMPS file are written beside the old one and swapped in only
  once complete. A title outside ASCII (`α-quartz`) survives.
- **Large structures are counted before they are built.** A
  supercell, the cells drawn, a porosity grid and a carbon build are
  estimated first: over a soft limit you are asked, over a hard one
  it is refused with the largest size that fits. *Preferences ▸
  General ▸ Large structures* sets how cautious: Standard (8 GB
  machines), Generous, or Warn only. The supercell dialog no longer
  builds the cell on every spin step.
- **Undo stops hoarding memory**: steps below the top let go of what
  they can rebuild, and the oldest whole-structure steps are released
  once they hold too many atoms, the status bar saying so.
- **A running calculation holds its tab.** An edit made under a
  running optimisation is refused with a message rather than lost
  when the result lands, and a module's result goes to the tab it
  ran on, whichever is in front. Changing workspace asks before
  stopping a calculation.
- **Errors cannot stack**: one crash box at a time, each fault once,
  with *Copy details*; a hard crash leaves its stack in `faults.log`
  beside the log.
- **The CIF reader says what it assumed.** Repeated atom labels are
  renamed so bonds can name their atoms, and said; a cell with a
  missing length is refused by name rather than read as a 1 Å cube;
  a `?` space-group number opens; a file whose symmetry operations
  match no tabulated setting says that they were not used. Disorder
  groups are written back.
- **The builders can be stopped and say the right thing**: Stop
  reaches a carbon build's relaxation; a polymer copolymer is built
  at the density asked for; a ladder monomer with a plain one is
  refused; a monomer with many free bonds no longer takes minutes
  before the first chain.

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
  beyond the POSCAR. Each is on the list for a 1.x release.
- **Style ▸ Rings refuses a graph too dense to search** -- a
  deposited CIF with its symmetry copies written as sites, or a
  close-packed salt -- and says so in the legend. *Prepare for
  simulation* first.

## Reporting something

*Help → Show log file* reveals a rotating log file that records start-up,
plugin failures, external process output and any uncaught exception's
traceback. Attaching it turns "it closed" into something that can be
fixed.
