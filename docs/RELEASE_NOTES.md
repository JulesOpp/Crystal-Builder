# Crystal Builder

Build, manipulate, analyse and export crystal structures. Read and
write CIF, edit symmetry and bonding, run a force field, DFTB+ or
Zeo++ on the result.

## New since 0.3.0

- **Powder refinement.** Open a measured `.xy` in the refinement
  workbench: fit peaks, index the pattern, then Pawley and Rietveld,
  with the atoms moving live in the viewport. *Rietveld with
  energies* adds the Force Field panel's engine to the fit, and a
  Pareto sweep traces the trade between the two. RietX does the
  physics and is bundled.
- **Prepare for simulation**: *Structure ▸ Prepare for simulation…*
  and `xtal prepare` turn a deposited CIF into a model a calculation
  can run on (duplicate sites merged, primitive cell, disorder
  ordered, solvent out, hydrogens) and say what each step chose.
  Anything that adds chemistry the file never located is left off
  unless asked for. *Open Sample ▸ Prepared for simulation* has the
  COD frameworks already done.
- **Simple materials** in *Open Sample*: eighteen textbook solids --
  graphene, graphite, diamond, silicon, NaCl, CsCl, CaF2, Al2O3,
  TiO2, SrTiO3, ZnO, quartz, iron, copper, and the zeolites LTA, MFI,
  FAU and SOD -- all but graphene the COD's depositions, cited, for
  learning the program on a crystal you already know.
- **Faster porosity**: surface area and accessible volume read off
  the distance grid, with no Zeo++ needed, and the pore surface is
  drawn over channels only.
- **An AI assistant can drive the builder**: a session API, coded
  diagnostics and a skill that ship with the package, with every
  edit one undo step logged to the structure's entry.
- **An AI assistant can work in the window**: *Help ▸ Connect an AI
  assistant…* lets any MCP client drive the open tabs, each change
  one undo step in front of you, and the packaged app carries the
  `xtal` program it connects through. Its answers are sized for a
  model (MOF-5's inspection is 4 kB, not 170), and the skill's rules
  are now the program's: a relaxation that would change the bonding
  says so, a scan says how many relaxations it is before it starts,
  and a file opened into a workspace it is not in says where it
  stayed.
- **The user manual ships with the application**: *Help ▸ User
  Manual* opens it, no network needed.
- Smaller things: *Select ▸ Bonds between elements…*, *Rename…* in
  the workspace panel, MACE-MP-MOF0 as a model choice, and nets
  searchable by their RCSR transitivity.

## Fixed in 0.4.0

- A Force Field run lands on the tab it was started on, not the one
  in front when it finishes.
- A scan holding a coordinate and the volume together converges.
- Nothing stays selected after a delete.
- ORB-v3 and MatterSim in double precision really are double
  precision. EQeq handles every metal's oxidation states.
- Engines are found where Homebrew and conda put them, including when
  the app is launched from the Finder.
- A program started by a calculation does not outlive it.
- Deuterium is computed as hydrogen.
- After atoms move, a bond keeps its stated order.
- Windows: renaming a file by its case alone works.

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
