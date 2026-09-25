# Installation

Crystal Builder is installed either as a packaged application, which
needs no Python, or from source into a Python environment, which is
what the machine-learned engines need.  Either way, the external
programs it can run are found on your machine rather than shipped,
and *Preferences ▸ Engines* is where they are pointed at.

## The packaged application

```{index} single: installation; packaged application
```

Download the build for your machine from the repository's *Releases*
page, <https://github.com/JulesOpp/Crystal-Builder/releases>:

| You have | Download |
|---|---|
| A Mac with Apple silicon (M1 and later) | `Crystal-Builder-<version>-arm64.dmg` |
| A Mac with an Intel processor | `Crystal-Builder-<version>-x86_64.dmg` |
| Windows, 64-bit | `Crystal-Builder-<version>-setup.exe` |

The Mac builds need **macOS 12.3 (Monterey) or later**.  There is no
universal Mac build: VTK publishes no universal2 wheel, so the two are
built separately.  Pick the one that matches your Mac -- *About This
Mac* says which -- because an Intel build cannot be made to run on
Apple silicon by Rosetta, which translates the other direction.  For
release 0.3.0 the downloads are about 200 MB (arm64), 230 MB (x86_64)
and 125 MB (Windows).

On macOS, open the disk image and drag *Crystal Builder* into
*Applications*.  On Windows, run the installer: it is per-user, needs
no administrator rights and installs under your own AppData, so it
works on a managed machine.  It offers `.cif` and `.xtalproj` file
associations; `.cif` is unticked by default, because a `.cif` on a
working machine usually already belongs to VESTA or Mercury.
Double-clicking a structure then opens it whether the application is
running or not.

### Opening it the first time

Neither build is code-signed yet, so both operating systems say so
the first time, each in its own way.  Nothing below is a way around a
security warning; it is what the warning is for, and how to answer it
if you trust where you got the file.

**macOS.**  Double-clicking gives *"Crystal Builder" cannot be opened
because the developer cannot be verified*.  Either:

1. Right-click (or Control-click) the application in *Applications*,
   choose **Open**, then **Open** again in the dialog; or
2. After the refusal, open *System Settings ▸ Privacy & Security*,
   scroll to the message about Crystal Builder and click **Open
   Anyway**.

macOS remembers the choice and ordinary double-clicking works
afterwards.  If the application was quarantined in a way that will
not clear, the equivalent from a terminal is:

```bash
xattr -dr com.apple.quarantine "/Applications/Crystal Builder.app"
```

**Windows.**  SmartScreen shows *Windows protected your PC*.  Click
**More info**, then **Run anyway**.

### What is in the download, and what is not

Bundled and working, with nothing to install:

- **The MOF builder.**  PORMAKE {cite}`lee2021pormake` is vendored
  into the application, with its 867 building blocks and the RCSR
  topologies, so a framework from a net, a node and a linker needs
  nothing else.
- **RDKit and rdeditor**, so *Build from SMILES* and the molecule
  sketcher both work.
- **matplotlib** {cite}`hunter2007matplotlib`, for the PXRD pattern
  window.

**MACE, ORB-v3 and MatterSim are not included.**  They need PyTorch,
which is gigabytes and wants to arrive differently on every platform.
The Force Field panel lists them and greys them out; to use them, run
from a source install (below).

**Zeo++, DFTB+, tblite and xtb are found, never carried.**  They have
their own licences and citation terms, and several are conda
packages.  Install them however you normally would and point at them
in *Preferences ▸ Engines* (see {ref}`external-programs`).

**Plugins installed with `pip` do not load in a packaged build.**  A
frozen application has no `pip` and nowhere to install one to, so the
shipped build runs its own modules only.  *Preferences ▸ Engines*
names a folder that is added to the import path at start-up --
`~/Library/Application Support/CrystalBuilder/packages` on macOS,
`%APPDATA%\CrystalBuilder\packages` on Windows -- and a package that
is pure Python can be put there with `pip install --target`.  It is
not reliable for a package with compiled dependencies, such as
PyTorch, which has to match the build's exact Python version and ABI.

:::{note}
*Help ▸ About Crystal Builder* shows the version the build was made
from.  If it reads `0.0.dev0` or `0.0.0`, the build is broken and
worth reporting.
:::

## A source install

```{index} single: installation; from source
```

The source install is for anybody who wants the machine-learned
engines, a plugin, or the `xtal` command line.  It needs Python 3.11
or later.  The core installs four packages -- numpy, scipy, gemmi
{cite}`wojdyr2022gemmi` and spglib {cite}`togo2024spglib` -- and
everything else is an *extra*:

```bash
git clone https://github.com/JulesOpp/Crystal-Builder
cd Crystal-Builder
python -m pip install -e ".[gui,ase,build,sketch,pxrd]"
crystal-builder
```

`crystal-builder` opens the window; `crystal-builder quartz.cif`
opens it on a file, and `python -m xtalapp.main` is the same thing.
`crystal-builder --selftest` opens a sample, draws the 3D view to a
file and checks the version, which is the quickest way to find out
whether an environment works.

| Extra | Package | What it buys |
|---|---|---|
| `gui` | PySide6, VTK | The window itself |
| `ase` | ASE {cite}`larsen2017ase` | The MOF builder; PORMAKE is written over it |
| `build` | RDKit | *Insert molecule*, a molecule from a SMILES string, and the fragment library |
| `sketch` | rdeditor | Drawing the molecule instead of typing it |
| `pxrd` | matplotlib | The PXRD pattern window: zoom, an overlaid measured pattern, vector export |
| `mace` | mace-torch | The MACE engine {cite}`batatia2022mace`.  Brings PyTorch |
| `orb` | orb-models | The ORB-v3 engine {cite}`rhodes2025orbv3`.  Brings PyTorch |
| `mattersim` | mattersim | The MatterSim engine {cite}`yang2024mattersim`.  Brings PyTorch |
| `docs` | Sphinx and friends | Building this manual |
| `dev` | all of the above but the ML engines, plus pytest, ruff, PyInstaller | Working on the code |

A feature whose extra is missing greys its own menu entry out and
names the extra, and *Preferences ▸ Engines* lists every package with
the command to type for the Python the application is running in.
Type that command rather than `pip install 'crystal-builder[orb]'`:
the package is not on PyPI, so the bare name resolves only against
the metadata written when the checkout was last installed, and an
extra added since is refused with *does not provide the extra*.

The three machine-learned engines are their own lines because each
pins PyTorch its own way.  `mace` and `mattersim` will not go into
one environment through pip -- mattersim asks for e3nn 0.5 where MACE
pins 0.4.4 -- and *Preferences ▸ Engines* says how to have both.  On
Python 3.13, `orb` has to build its pinned dm-tree, which under
CMake 4 needs `CMAKE_POLICY_VERSION_MINIMUM=3.5` set in the
environment.

:::{warning}
PySide6 must stay below 6.10, and the bound in `pyproject.toml` is
load-bearing.  From 6.10.0, VTK's Qt bridge repaints forever: the
window comes up, the 3D view stays empty, and the application never
responds again.  The test suite cannot catch this, because it never
opens a real GL context; `crystal-builder --selftest` can.
:::

(external-programs)=
## External programs

```{index} single: Preferences; Engines
```
```{index} single: Zeo++; installing
```
```{index} single: DFTB+; installing
```
```{index} single: xTB; installing
```

Crystal Builder shells out to these programs and finds them itself;
none is shipped.  Each is looked for at the path set in Preferences,
then at an environment variable, then on `PATH`:

| Program | Powers | Environment variable |
|---|---|---|
| Zeo++, the binary `network` {cite}`willems2012zeopp` | Pore diameters, surface area, accessible volume, pore size distribution | `XTAL_ZEOPP` |
| DFTB+, `dftb+` {cite}`hourahine2020dftbplus` | The DFTB+ engine and the entries under *Modules ▸ DFTB+* | `XTAL_DFTB` |
| `waveplot`, ships with DFTB+ | *Modules ▸ DFTB+ ▸ Orbital* | `XTAL_WAVEPLOT` |
| `modes`, ships with DFTB+ | *Modules ▸ DFTB+ ▸ Vibrational modes* | `XTAL_MODES` |
| The Slater-Koster parameters, a folder of `.skf` files from dftb.org | Every DFTB+ run; the pairs present are checked before anything is launched | `DFTB_PREFIX` |
| tblite | GFN1-xTB and GFN2-xTB in the xTB engine; GFN2 under a periodic cell is tblite's alone | `XTAL_TBLITE` |
| xtb {cite}`bannwarth2021xtb` | GFN-FF, which tblite does not implement | `XTAL_XTB` |
| Blender, with the Atomic Blender add-on | *File ▸ Export as STL* | -- (`/Applications/Blender.app` is looked in on its own) |

*Preferences ▸ Engines* ({ref}`Preferences… <cmd-preferences>`,
{kbd}`Ctrl+,`) has a row per program ({numref}`fig-preferences-engines`).
Under each field a status line says whether the program was found
and, if not, exactly where it looked -- *Not found.  Looked at
XTAL_ZEOPP, which is not set and on PATH* -- with where to get it.
**Browse…** names the file; **Test** runs the program for a moment
and shows what it printed, because a binary can be found and still
not work (one built for the other architecture, say).  A change here
reaches the *Modules* menu at once: a greyed-out entry lights up
without a restart.

:::{figure} /figures/quickstart/preferences-engines.png
:name: fig-preferences-engines
:width: 100%

*Preferences ▸ Engines* on a machine with none of the programs
installed.  Each row says where it looked and where the program comes
from.
:::

The same page lists the Python packages under *Python packages*,
with an install command on a source checkout and a note in a packaged
build that there is no `pip` to run it with, and, under *Your own
nets and blocks*, the two folders of `.cgd` nets and `.xyz` building
blocks the MOF builder reads alongside PORMAKE's own.
