"""
Wrap the built Linux bundle in a Debian package.

    python packaging/makedeb.py dist/crystal-builder [dist/]

**``dpkg-deb`` and not ``fpm``, and not a ``debian/`` directory.**
There is no source package to integrate with and nothing for a build
system to compile: PyInstaller has already produced one opaque folder
of its own Python, Qt and VTK, and this writes the metadata around it.
``--root-owner-group`` is why ``fakeroot`` is not needed either.

Where it goes, and why:

* **``/opt/crystal-builder/``** -- the whole onedir bundle, untouched.
  A frozen tree is not a library, and unpacking it into ``/usr/lib``
  to satisfy a policy written for source packages would be a fiction:
  dpkg's file list for it is not something anything reads.
* **``/usr/bin/crystal-builder`` and ``/usr/bin/xtal``** -- two
  one-line wrappers, because ``/opt`` is not on PATH and this is the
  smallest thing that puts it there.  The CLI one matters: an AI
  assistant's client runs ``xtal mcp``, and a packaged install has no
  pip to have put one on PATH.
* **``/usr/share/applications/crystal-builder.desktop``** -- the
  display name ("Crystal Builder"), the icon and the file types.  The
  executable keeps the lowercase name a shell can type.
* **``/usr/share/icons/hicolor/...``** -- the app icon as PNGs at
  every size the theme asks for plus the ``.svg``, and the two
  document icons under ``mimetypes/``.  Rendered here from the same
  SVGs ``build_icons.py`` rasterises for macOS and Windows, with the
  same Qt renderer, rather than committed as a third copy.
* **``/usr/share/mime/packages/crystal-builder.xml``** -- ``.cif`` as
  ``chemical/x-cif`` and ``.xtalproj`` as ``application/x-xtalproj``.
  Registering a type is not stealing an association: on Linux the
  default handler is per-user and this only makes the application one
  of the things a user can choose, which is the same decision as
  ``LSHandlerRank: Alternate`` in ``macos.spec``.
* **No maintainer scripts.**  dpkg's triggers already run
  ``update-mime-database``, ``update-desktop-database`` and the icon
  cache rebuild when these directories change, and the shared-mime-info
  / desktop-file-utils / hicolor-icon-theme packages that own the
  triggers are the ones that should.

``Depends:`` is deliberately short.  The bundle carries its Python,
Qt, VTK and their libraries; what PyInstaller leaves to the machine
is the C library and the handful of system libraries Qt and VTK link
against, which is the list CI installs on a Linux runner before it
can ``import QtGui`` at all.  The glibc floor is read off the bundle's
own binaries and not the build host: the newest ``GLIBC_x.y`` symbol
any ELF asks for is the oldest system the application can start on,
and apt refuses anything older with a sentence rather than letting it
fail at start-up.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PACKAGE = "crystal-builder"
HOMEPAGE = "https://github.com/JulesOpp/Crystal-Builder"
MAINTAINER = "Jules Oppenheim <JulesOpp@users.noreply.github.com>"

#: The square sizes a hicolor theme looks for under ``apps/``.  512 is
#: what a file manager shows in a preview; 16 is the title bar, and is
#: the size ``app-small.svg`` was drawn for.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)

#: The document icons, by SVG stem and the MIME type they decorate.
#: A MIME icon's file name is its type with the slash spelled ``-``.
DOCUMENT_ICONS = {
    "cif": "chemical-x-cif",
    "xtalproj": "application-x-xtalproj",
}
DOCUMENT_SIZES = (16, 24, 32, 48, 64, 128, 256)

#: What the bundle does not carry.  The same list the Linux test job
#: installs before Qt can be imported, plus the two the C++ runtime
#: is in.  Everything else -- fontconfig, freetype, the image formats,
#: the Qt plugins and their xcb cousins -- PyInstaller collects into
#: the bundle, and a line here for one of them would only be a way for
#: apt to disagree with what is actually shipped.
SYSTEM_LIBRARIES = [
    "libgcc-s1",
    "libstdc++6",
    "libegl1",
    "libgl1",
    "libdbus-1-3",
    "libxkbcommon-x11-0",
    "libxcb-cursor0",
    "libxcb-icccm4",
    "libxcb-image0",
    "libxcb-keysyms1",
    "libxcb-randr0",
    "libxcb-render-util0",
    "libxcb-shape0",
    "libxcb-xfixes0",
    "libxcb-xinerama0",
]

DESKTOP = """\
[Desktop Entry]
Type=Application
Name=Crystal Builder
GenericName=Crystal Structure Builder
Comment=Build, manipulate, analyse and export crystal structures
Exec=crystal-builder %F
Icon=crystal-builder
Terminal=false
Categories=Science;Chemistry;Physics;
Keywords=crystal;CIF;crystallography;chemistry;structure;MOF;
MimeType=chemical/x-cif;application/x-xtalproj;
StartupNotify=true
StartupWMClass=Crystal Builder
"""

MIME_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="chemical/x-cif">
    <comment>Crystallographic Information File</comment>
    <glob pattern="*.cif"/>
    <icon name="chemical-x-cif"/>
  </mime-type>
  <mime-type type="application/x-xtalproj">
    <comment>Crystal Builder project</comment>
    <glob pattern="*.xtalproj"/>
    <icon name="application-x-xtalproj"/>
  </mime-type>
</mime-info>
"""

GUI_WRAPPER = """\
#!/bin/sh
# The application is the self-contained folder under /opt; this is
# what puts it on PATH.  The display name is the .desktop entry's.
exec /opt/crystal-builder/crystal-builder "$@"
"""

CLI_WRAPPER = """\
#!/bin/sh
# `xtal`, the headless CLI and the stdio door an AI assistant's client
# runs (`xtal mcp`), from the same bundle as the window.
exec /opt/crystal-builder/xtal "$@"
"""


def architecture() -> str:
    """The Debian architecture name for this build.

    ``dpkg --print-architecture`` when it is there, because it is the
    authority on the machine the package is being made on; the mapping
    is the fallback for a build host without dpkg, which is not a
    build host this is expected on.
    """
    try:
        run = subprocess.run(["dpkg", "--print-architecture"],
                             capture_output=True, text=True, check=True)
        return run.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return {"x86_64": "amd64", "aarch64": "arm64",
                "armv7l": "armhf"}.get(os.uname().machine, "amd64")


def _is_elf(path: Path) -> bool:
    """Whether ``path`` starts with the ELF magic number."""
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def _elf_facts(path: Path) -> tuple[Path, dict] | None:
    """``readelf -d -V`` once: what this ELF needs and its glibc.

    One subprocess and not two, because the same few thousand files
    are asked otherwise: ``-d`` carries the ``DT_NEEDED`` and
    ``SONAME`` entries the Qt pruning walks, and ``-V`` the
    ``GLIBC_x.y`` symbol versions the ``Depends`` floor comes from.
    """
    try:
        run = subprocess.run(["readelf", "-d", "-V", str(path)],
                             capture_output=True, text=True)
    except OSError:
        return None
    if run.returncode != 0:
        return None
    soname = re.search(
        r"\(SONAME\)\s+Library soname: \[([^\]]+)\]", run.stdout)
    return path, {
        "needed": re.findall(
            r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", run.stdout),
        "soname": soname.group(1) if soname else None,
        "glibc": {(int(major), int(minor))
                  for major, minor in re.findall(
                      r"GLIBC_(\d+)\.(\d+)", run.stdout)},
    }


def elf_facts(folder: Path) -> dict[Path, dict]:
    """Every ELF under ``folder`` and its facts, read in parallel."""
    binaries = [path for path in folder.rglob("*")
                if path.is_file() and _is_elf(path)]
    facts: dict[Path, dict] = {}
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for found in pool.map(_elf_facts, binaries):
            if found is not None:
                facts[found[0]] = found[1]
    return facts


def _host_glibc() -> str | None:
    """The build host's glibc, for when readelf is not installed."""
    try:
        run = subprocess.run(["ldd", "--version"],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    first = run.stdout.splitlines()[0] if run.stdout else ""
    found = re.search(r"(\d+\.\d+)\s*$", first)
    return found.group(1) if found else None


def glibc_floor(facts: dict[Path, dict]) -> str | None:
    """The oldest glibc the bundle can run on, or ``None``.

    The build host's own glibc is not the answer: every wheel in the
    bundle is a manylinux one built against something older, so a
    floor read from the host would refuse systems the application
    would run on.  What counts is the newest ``GLIBC_x.y`` symbol
    version any ELF in the bundle asks for.  Falls back to the host's
    version when there is nothing to read, which over-restricts
    rather than lying.
    """
    versions: set[tuple[int, int]] = set()
    for fact in facts.values():
        versions |= fact["glibc"]
    if not versions:
        return _host_glibc()
    return ".".join(str(part) for part in max(versions))


def depends(facts: dict[Path, dict]) -> list[str]:
    """The ``Depends:`` field, as a list of package names."""
    floor = glibc_floor(facts)
    libc = "libc6" if floor is None else f"libc6 (>= {floor})"
    return [libc, *SYSTEM_LIBRARIES]


#: The two Qt plugins PACKAGING.md 4 names, and the only two things
#: in the bundle linking whole chains of Qt that nothing else wants:
#: a PDF rendered as an image, and an on-screen keyboard for touch
#: devices.  The same removal ``postbuild.py`` makes on macOS, for
#: the same reason.  The ``_internal`` is PyInstaller 6's onedir
#: layout and not a choice: everything the analysis collected lives
#: there, and the executables beside it.
DEAD_QT_PLUGINS = (
    "_internal/PySide6/Qt/plugins/imageformats/libqpdf.so",
    "_internal/PySide6/Qt/plugins/platforminputcontexts/"
    "libqtvirtualkeyboardplugin.so",
)


def prune_qt(folder: Path, facts: dict[Path, dict]) -> tuple[int, int]:
    """Delete the dead Qt plugins, then every Qt library they orphan.

    The cascade is the point, and it is checked rather than assumed:
    removing the virtual-keyboard plugin orphans
    ``libQt6VirtualKeyboardQml``, whose removal orphans
    ``libQt6Quick``, whose removal orphans the QtQml family -- and
    QtPdf goes with the PDF image plugin.  A library is deleted only
    when no remaining ELF in the bundle names it in a ``DT_NEEDED``
    entry, which is the check ``postbuild.py`` runs with ``otool`` on
    macOS: a plugin added later keeps whatever it links, and a
    library something still refers to is never touched.  Returns
    ``(files deleted, bytes freed)``.
    """
    entries: dict[str, dict] = {}
    needed_by: dict[str, set[Path]] = {}
    for path, fact in facts.items():
        for need in fact["needed"]:
            needed_by.setdefault(need, set()).add(path)
        if not path.name.startswith("libQt6"):
            continue
        name = fact["soname"] or path.name
        entry = entries.setdefault(name, {"files": set(), "size": 0})
        entry["files"].add(path)
        if not path.is_symlink():
            entry["size"] += path.stat().st_size

    dead: set[Path] = set()
    freed = 0
    for relative in DEAD_QT_PLUGINS:
        path = folder / relative
        if path.is_file():
            dead.add(path)
            freed += path.stat().st_size

    changed = True
    while changed:
        changed = False
        for name, entry in entries.items():
            if entry["files"] <= dead:
                continue
            alive = any(
                referrer not in dead and referrer.resolve() not in dead
                for referrer in needed_by.get(name, ()))
            if not alive:
                dead |= entry["files"]
                freed += entry["size"]
                changed = True

    for path in dead:
        path.unlink(missing_ok=True)
    return len(dead), freed


def debian_version(version: str) -> str:
    """``version`` as a Debian version string, or a refusal.

    ``setuptools-scm`` gives ``1.0.1.dev3+gabcdef``, whose dots and
    ``+`` are legal in a Debian upstream version.  A hyphen would be
    read as the revision separator and a colon as an epoch, and
    quietly shipping a package whose version means something else is
    worse than not shipping one.
    """
    if re.fullmatch(r"[0-9][A-Za-z0-9.+~]*", version):
        return version
    raise SystemExit(
        f"{version!r} is not a Debian version: it needs to start with "
        "a digit and hold only [A-Za-z0-9.+~].")


def strip_tree(folder: Path) -> int:
    """``strip --strip-unneeded`` every ELF file in the staged copy.

    Not PyInstaller's ``strip=True``: that runs before the tree is
    assembled, so a failure is a failed build rather than one line of
    warning, and the same work would be done twice for a debug run
    that never reaches here.  A file strip refuses is left as it was
    and named; nothing in the bundle is load-bearing on its symbols.
    """
    stripped = 0
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as handle:
            if handle.read(4) != b"\x7fELF":
                continue
        try:
            run = subprocess.run(["strip", "--strip-unneeded", str(path)],
                                 capture_output=True, text=True)
        except OSError as exc:
            print(f"strip is not available ({exc}); leaving the rest "
                  "unstripped", file=sys.stderr)
            break
        if run.returncode != 0:
            print(f"strip left {path.name}: "
                  f"{run.stderr.strip()[:200]}", file=sys.stderr)
        else:
            stripped += 1
    return stripped


def write_icons(stage: Path) -> None:
    """The hicolor theme's icons, rendered from the SVGs with Qt.

    The same renderer and the same source-of-truth SVGs as
    ``build_icons.py``; the sizes differ because a theme looks for
    PNGs at named sizes rather than an icon container.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent / "icons"))
    import build_icons  # noqa: E402

    here = Path(__file__).resolve().parent
    app = build_icons.application()          # held until the last render
    for size in ICON_SIZES:
        into = stage / "usr/share/icons/hicolor" / f"{size}x{size}" / "apps"
        into.mkdir(parents=True, exist_ok=True)
        build_icons.render(
            build_icons.source_for(here / "icons" / "app.svg", size),
            size, into / f"{PACKAGE}.png")

    scalable = stage / "usr/share/icons/hicolor/scalable/apps"
    scalable.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(here / "icons" / "app.svg",
                    scalable / f"{PACKAGE}.svg")

    for stem, mime in DOCUMENT_ICONS.items():
        for size in DOCUMENT_SIZES:
            into = (stage / "usr/share/icons/hicolor"
                    / f"{size}x{size}" / "mimetypes")
            into.mkdir(parents=True, exist_ok=True)
            build_icons.render(here / "icons" / f"{stem}.svg",
                               size, into / f"{mime}.png")
    del app


def write_wrappers(stage: Path) -> None:
    """The two lines on PATH, at ``/usr/bin``."""
    into = stage / "usr/bin"
    into.mkdir(parents=True, exist_ok=True)
    for name, text in (("crystal-builder", GUI_WRAPPER),
                       ("xtal", CLI_WRAPPER)):
        path = into / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)


def write_desktop(stage: Path) -> None:
    """The desktop entry, which is where the display name lives."""
    into = stage / "usr/share/applications"
    into.mkdir(parents=True, exist_ok=True)
    (into / f"{PACKAGE}.desktop").write_text(DESKTOP, encoding="utf-8")


def write_mime(stage: Path) -> None:
    """The two MIME types, for the file manager and the Open With list."""
    into = stage / "usr/share/mime/packages"
    into.mkdir(parents=True, exist_ok=True)
    (into / f"{PACKAGE}.xml").write_text(MIME_XML, encoding="utf-8")


def write_copyright(stage: Path) -> None:
    """``/usr/share/doc``'s copyright, in the machine-readable format.

    The licence text is the repository's own ``LICENSE``, indented as
    the format asks, so the file a Debian tool reads and the file the
    repository has cannot drift apart.
    """
    license_path = Path(__file__).resolve().parent.parent / "LICENSE"
    body = []
    for line in license_path.read_text(encoding="utf-8").splitlines():
        body.append(f" {line}" if line.strip() else " .")

    into = stage / "usr/share/doc" / PACKAGE
    into.mkdir(parents=True, exist_ok=True)
    (into / "copyright").write_text("\n".join([
        "Format: https://www.debian.org/doc/packaging-manuals/"
        "copyright-format/1.0/",
        "Upstream-Name: Crystal Builder",
        f"Source: {HOMEPAGE}",
        "",
        "Files: *",
        "Copyright: 2026 Jules Oppenheim",
        "License: MIT",
        *body,
        "",
    ]), encoding="utf-8")


def installed_size(stage: Path) -> int:
    """The installed size in KiB, which is what ``Installed-Size`` is.

    Measured over the staged tree and not the bundle: the icons and
    the wrappers are files too, and dpkg compares this number against
    its own count of the unpacked files.
    """
    total = 0
    for path in stage.rglob("*"):
        if path.is_file() and not path.is_symlink() \
                and "DEBIAN" not in path.relative_to(stage).parts:
            total += path.stat().st_size
    return (total + 1023) // 1024


def write_control(stage: Path, version: str, arch: str,
                  facts: dict[Path, dict]) -> None:
    """The ``DEBIAN/control`` file, every field of it."""
    control = "\n".join([
        f"Package: {PACKAGE}",
        f"Version: {version}",
        "Section: science",
        "Priority: optional",
        f"Architecture: {arch}",
        f"Maintainer: {MAINTAINER}",
        f"Homepage: {HOMEPAGE}",
        f"Installed-Size: {installed_size(stage)}",
        "Depends: " + ", ".join(depends(facts)),
        "Description: build, manipulate, analyse and export crystal "
        "structures",
        " Crystal Builder is a desktop application for crystal"
        " structures:",
        " opening CIFs, symmetry and topology, MOFs and molecules,"
        " force-field",
        " optimisation, pore analysis and PXRD, with export to the"
        " formats",
        " around it.",
        " .",
        " This package carries the application as a PyInstaller bundle,"
        " with",
        " its own Python, Qt and VTK, under /opt/crystal-builder.  The",
        " system libraries it wants are the ones Depends names.",
        "",
    ])
    (stage / "DEBIAN" / "control").write_text(control, encoding="utf-8")


def make(bundle_dir: Path, into: Path, version: str) -> Path:
    """Write the .deb and return where it went."""
    arch = architecture()
    out = into / f"{PACKAGE}_{version}_{arch}.deb"
    out.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        (stage / "DEBIAN").mkdir(parents=True)
        # symlinks=True: PyInstaller 6 links duplicated libraries
        # rather than copying them, and following a link here would
        # both double the size and change what is installed.
        shutil.copytree(bundle_dir, stage / "opt" / PACKAGE,
                        symlinks=True)

        folder = stage / "opt" / PACKAGE
        print(f"stripped {strip_tree(folder)} ELF files")
        facts = elf_facts(folder)
        files, freed = prune_qt(folder, facts)
        print(f"pruned {files} dead Qt files, {freed / 1e6:.0f} MB")
        write_icons(stage)
        write_wrappers(stage)
        write_desktop(stage)
        write_mime(stage)
        write_copyright(stage)
        write_control(stage, debian_version(version), arch, facts)

        command = ["dpkg-deb", "--root-owner-group", "--build",
                   "--compression=xz",
                   f"--threads-max={os.cpu_count() or 1}",
                   str(stage), str(out)]
        run = subprocess.run(command, capture_output=True, text=True)
        if run.returncode != 0:
            print(run.stderr or run.stdout, file=sys.stderr)
            raise subprocess.CalledProcessError(
                run.returncode, command, run.stdout, run.stderr)
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not 1 <= len(argv) <= 2:
        print("usage: makedeb.py dist/crystal-builder [dist/]",
              file=sys.stderr)
        return 2
    if sys.platform != "linux":
        print("a .deb is built on Linux, by dpkg-deb", file=sys.stderr)
        return 1

    app = Path(argv[0]).resolve()
    into = Path(argv[1]).resolve() if len(argv) > 1 else app.parent
    if not app.is_dir():
        print(f"{app} is not there", file=sys.stderr)
        return 1
    into.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bundle  # noqa: E402

    out = make(app, into, bundle.version())
    print(f"{out.name}  {out.stat().st_size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
