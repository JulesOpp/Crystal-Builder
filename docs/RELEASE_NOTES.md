# Crystal Builder

Build, manipulate, analyse and export crystal structures. Read and
write CIF, edit symmetry and bonding, run a force field, DFTB+ or
Zeo++ on the result.

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

Bundled and working, with nothing to install: **RDKit**, so *Build
from SMILES* and the molecule sketcher both work, and **rdeditor**,
which is the sketcher's canvas.

**The MOF builder (PORMAKE) is not included.** It is 44 packages and
about 889 MB — `jax` and `pymatgen` among them — which is larger than
the rest of the application put together. The entry greys out saying
so. Net identification, the RCSR index and the `.cgd` reader are this
project's own code and keep working; only the builder dialog is
affected. *Preferences → Engines* explains the two routes to
having it, and recommends running from Python:

```bash
pip install 'crystal-builder[gui,mof]'
crystal-builder
```

**Zeo++ and DFTB+ are found, never carried.** They have their own
licences and citation terms, and DFTB+ is a conda package. Install
either one however you normally would and point at it in
*Preferences → Engines*, which says what it looked for and
where. `XTAL_ZEOPP`, `DFTB_PREFIX` and `PATH` all still work.

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
