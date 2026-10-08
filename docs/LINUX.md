# Crystal Builder on Linux

Design record for the Linux download. Written 2026-10-08 against
`v1.0.0`; branch `feature/linux-appimage`.

## Goal

A packaged Linux download for x86_64, on the same footing as the
macOS DMG and the Windows installer: built and self-tested in CI on
every release, attached to the draft release beside them. One file
the user makes executable and double-clicks.

## Where things stand

- The headless core and the window are already portable. The
  app-data folder (`xtalapp/applog.py::app_data`, Qt's generic data
  location, `~/.local/share/CrystalBuilder`), the AI-assistant
  discovery folder and launcher (`xtal/agent/discovery.py`, with a
  Linux branch held equal to `app_data` by
  `tests/test_applog.py`), the server's socket options, external
  program lookup, install commands and the "Show in File Manager"
  label all have a Linux branch or a sensible default.
- No test skips on Linux. The suite ran green on `ubuntu-latest`
  under `QT_QPA_PLATFORM=offscreen` from 2026-09-03 to 2026-09-07,
  when Linux left the matrix (`ad886fc`) because nothing was
  released for it. The apt step it needed is still in `ci.yml`,
  dormant.
- Every dependency has a manylinux x86_64 wheel for Python 3.12.
  The floors: PySide6 6.9.3 `manylinux_2_28`, VTK 9.7
  `manylinux_2_17`.
- Nothing is published for Linux; the README and the manual's
  installation page name only the DMG and `setup.exe`.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Tier | A packaged download | A source install already works for those who want it; the download is what makes Linux a platform |
| Architecture | x86_64 only | What most Linux desktops run; ARM needs glibc 2.39+ for PySide6's aarch64 wheel and an ARM runner |
| Artefact | AppImage | One file, no install, runs on most distros: the closest match to the DMG and `setup.exe` |
| Build route | PyInstaller folder, then our own AppDir layout, then `appimagetool` | One packaging system across all three platforms; `bundle.py`, the selftest and the `xtal` launcher are reused unchanged |
| Build host | GitHub's `ubuntu-22.04` runner | Sets the glibc floor at 2.35: Ubuntu 22.04+, Debian 12+, Fedora 36+, Mint 21+ |

Rejected: `linuxdeploy` with its Qt plugin (it expects a C++ Qt
install and fights PySide6's wheel layout, and two tools choosing
the bundled libraries is how AppImages break); `python-appimage`
without PyInstaller (a second packaging system, and the launcher,
selftest and exclusions redone); a tarball (no desktop entry, and
the user installs Qt's libraries); `.deb` (one distro family);
Flatpak (a sandbox at odds with DFTB+, Zeo++ and Blender as
external programs).

## 1. The application

- `xtalapp/application.py` sets the window icon from the bundled
  icon and `setDesktopFileName("io.github.julesopp.CrystalBuilder")`,
  so the running window is matched to the `.desktop` entry: Wayland
  and GNOME show the right icon and group the windows. Harmless on
  macOS and Windows.
- A double-clicked `.cif` or `.xtalproj` arrives on the command
  line, which `xtalapp/main.py` already opens. No change.
- Wording: "the usual Homebrew and conda folders"
  (`xtal/modules/process.py`, `xtalapp/external.py`) becomes "the
  usual Homebrew, conda and system folders"; docstrings that say
  "Finder or Explorer" say "the file manager".
- `xtal/modules/blender.py` also looks in `/usr/bin/blender` and
  `/snap/bin/blender`.
- Not done: the login-shell PATH that `xtalapp/shellenv.py` adopts
  for a Dock launch. A launch from a `.desktop` entry inherits the
  session's PATH on the common desktops. Revisit if a user reports
  a program that is on their shell's PATH and not found.

## 2. Packaging

- `packaging/linux.spec`: two `Analysis` (`xtalapp/main.py`,
  `xtal/cli.py`), a windowed `Crystal Builder` executable and a
  console `xtal`, one `COLLECT`, all from `bundle.py` as the other
  specs are. `discovery.launcher()` and `bundle.launcher_path()`
  already look for `xtal` beside the application on Linux.
- `packaging/postbuild_linux.py`: `strip --strip-unneeded` over
  every `.so`, and the same pruning of unused Qt modules as
  `postbuild.py` does on macOS (QtQuick, QtQml, QtPdf,
  QtVirtualKeyboard), decided from `readelf -d` NEEDED entries
  instead of `otool -L`. Prints the size before and after.
- `packaging/appimage.py`: lays out `CrystalBuilder.AppDir/`:
  - `usr/lib/crystal-builder/`: the `COLLECT` folder;
  - `AppRun`: sets `QT_QPA_PLATFORM` to `wayland;xcb` unless the
    user set it, then runs `usr/lib/crystal-builder/Crystal Builder`
    with the arguments it was given;
  - `io.github.julesopp.CrystalBuilder.desktop`: `Name=Crystal
    Builder`, `Exec=AppRun %F`, `Icon`, `Categories=Science;Chemistry;`,
    `MimeType=chemical/x-cif;application/x-crystal-builder-project;`;
  - the icon: `app.svg` and a 256 px PNG rendered from it;
  - `usr/share/mime/packages/crystal-builder.xml`: both types,
    `.xtalproj` and `.cif` as `chemical/x-cif`. A desktop that
    already knows `.cif` from `chemical-mime-data` keeps its own
    definition; one that does not learns it from ours.

  `appimagetool`, downloaded in CI from its official GitHub release
  and checked against a pinned SHA-256, packs
  `Crystal_Builder-<version>-x86_64.AppImage`.
- Libraries. The build host installs Qt's xcb, xkbcommon and
  fontconfig libraries so PyInstaller collects them into the
  bundle. glibc, libGL, libEGL and the Wayland and X11 client
  libraries stay with the user's system (the AppImage project's
  exclude list); bundling those is what breaks AppImages across
  distros.
- File associations and a menu entry. An AppImage does not
  register them itself. The manual points to AppImageLauncher or
  Gear Lever, which read the `.desktop` file inside. No installer
  script of our own.

## 3. CI

- Test matrix: `ubuntu-latest · py3.12` returns, with the dormant
  apt step plus `libosmesa6` and `mesa-utils` so the GL tests run
  instead of skipping. The comment that explains why Linux left is
  replaced with one that says why it is back: something is
  released for it now.
- Bundle job: a `linux-x86_64` row on `ubuntu-22.04` runs the
  build, `postbuild_linux.py` and `appimage.py`, then the selftest
  from the AppImage itself under `xvfb-run` with Mesa's llvmpipe:
  the 3D view draws, and the launcher check prints
  `xtal launcher: … answers, version …; mcp answers`. The selftest
  image and the AppImage are uploaded as artifacts.
- Release job: attaches the AppImage to the draft release beside
  the DMG and `setup.exe`.

## 4. Documentation

- README and `docs/manual/quickstart/installation.md`: a Linux
  section: download, `chmod +x`, run; the glibc floor in plain
  words ("Ubuntu 22.04 or newer, Debian 12, Fedora 36 or newer");
  `QT_QPA_PLATFORM=xcb` if the window does not open under Wayland;
  menu entries through AppImageLauncher or Gear Lever.
- Fixed in passing: `%APPDATA%` → `%LOCALAPPDATA%` in the README and
  the installation page (the code uses `LOCALAPPDATA`), and the
  README's claim that packaged builds lack the MOF builder.
- `docs/PACKAGING.md`: a Linux section, and the release checklist
  item below.

## 5. Testing

Unit tests, run on every platform:

- `appimage.py`: the AppDir layout (the `.desktop` keys, the MIME
  types, `AppRun` executable and honouring a user's
  `QT_QPA_PLATFORM`, the icon present).
- `postbuild_linux.py`: the pruning decision from canned `readelf`
  output.
- `linux.spec`: parsed as `tests/test_packaging_launcher.py` parses
  the other two (two `EXE`, `xtal` console, both in `COLLECT`).
- The window icon and desktop file name are set.

CI proves the build, the selftest image under X11 with software GL,
and the launcher. It cannot prove Wayland on a real desktop or a
real GPU driver. Before a release is announced: run the AppImage on
a throwaway x86_64 cloud VM with a desktop, open a sample, rotate
it, and switch on Preferences ▸ AI assistant. This is a checklist
item in `PACKAGING.md`, not a CI job.

## Not in scope

ARM; Flatpak; `.deb`; RHEL 9 and other systems with glibc older
than 2.35; a self-hosted runner.
