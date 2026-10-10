"""
Prune and strip the built Linux folder, before it becomes an AppDir.

    python packaging/postbuild_linux.py "dist/Crystal Builder"

The Linux half of what ``postbuild.py`` does for the macOS bundle, and
for the same two reasons: the wheels' shared libraries carry symbol
tables nothing at run time reads, and two Qt plugins nobody here can
use hold a chain of Qt modules in the download.

**Unused Qt goes first, then the strip**, so no time is spent
stripping what is about to be deleted.  ``linux.spec`` leaves
PyInstaller's own ``strip`` off: on Linux it is a bare ``strip`` run
on each library as it is collected, before anything is pruned, and it
reports nothing.  ``--strip-unneeded`` is the form distributions strip
shared libraries with: it keeps every symbol relocation needs and the
dynamic symbol table whole -- which is where a Python extension's
``PyInit_*`` and every exported Qt and VTK function are looked up --
and drops the rest.  Each stripped file is read back, and one the
loader would refuse is put back as it was (:func:`misaligned`).  As on
macOS, the selftest the caller runs against the AppImage is what
proves the result still draws.

What is pruned is decided from ``readelf -d``'s ``NEEDED`` entries,
where macOS reads ``otool -L``.  Qt loads its plugins with ``dlopen``,
which no ``NEEDED`` entry records, so a plugin is never pruned for
being unreached; only the two named in :data:`UNUSED_PLUGINS` go.

Nothing is signed: an AppImage has no signature to invalidate.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: The two programs ``linux.spec`` makes.  Each is PyInstaller's
#: bootloader with the application's archive appended, so they are
#: walked for what they link and never stripped: ``strip`` drops what
#: it does not recognise as part of the ELF image, which here is the
#: whole application.
PROGRAMS = ("Crystal Builder", "xtal")

#: Where PySide6 keeps the Qt libraries, below wherever PyInstaller put
#: the package (``_internal/`` in PyInstaller 6).  Everything found
#: here is a library that something else must reach; everything else
#: in the folder is a root.
QT_LIB = ("PySide6", "Qt", "lib")

#: Qt plugins this application cannot use, and the reason each one is
#: refused.  Qt finds plugins by scanning a directory, so a missing
#: optional plugin is simply never offered.  The same two as macOS,
#: for the same reason: each is the only thing in the folder that links
#: a chain of Qt modules -- QtPdf, and QtQuick, QtQml and
#: QtVirtualKeyboard -- so removing it orphans the chain.
UNUSED_PLUGINS = {
    "PySide6/Qt/plugins/imageformats/libqpdf.so":
        "renders a PDF as an image; this application shows CIFs",
    "PySide6/Qt/plugins/platforminputcontexts/"
    "libqtvirtualkeyboardplugin.so":
        "an on-screen keyboard for touch devices",
}

#: Qt modules that become unreachable once the plugins above are gone,
#: by the names ``postbuild.py`` uses; :func:`soname` is the file each
#: is on Linux.  Nothing is deleted on the strength of this list alone:
#: :func:`remove_unused` keeps a candidate anything that runs can still
#: reach, or anything left in the folder names.  The list only says
#: where to look.
ORPHAN_CANDIDATES = (
    "QtPdf", "QtQuick", "QtQml", "QtQmlModels", "QtQmlMeta",
    "QtVirtualKeyboard", "QtVirtualKeyboardQml",
)

ELF_MAGIC = b"\x7fELF"

_NEEDED = re.compile(r"\(NEEDED\)\s+Shared library: \[(.+?)\]")


def soname(module: str) -> str:
    """``QtQuick`` -> ``libQt6Quick.so.6``."""
    return f"libQt6{module[len('Qt'):]}.so.6"


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == ELF_MAGIC
    except OSError:
        return False


def libraries(root: Path):
    """Every shared library in the folder, links not followed.

    By name and then by content: a Python extension is ``.so``, a
    system library ``.so.1`` or ``.so.6.9.0``, and a data file with
    ``.so.`` in its name is neither.
    """
    for path in sorted(root.rglob("*")):
        if (path.is_file() and not path.is_symlink()
                and (path.name.endswith(".so") or ".so." in path.name)
                and is_elf(path)):
            yield path


def total(root: Path) -> int:
    """Bytes on disk, following nothing."""
    return sum(p.stat().st_size for p in root.rglob("*")
               if p.is_file() and not p.is_symlink())


def find(root: Path, relative: str) -> Path | None:
    """``relative`` wherever PyInstaller put it under ``root``.

    Searched for rather than joined on, so that the answer does not
    depend on whether this PyInstaller puts the libraries in
    ``_internal/`` or beside the programs.
    """
    found = sorted(root.rglob(relative))
    return found[0] if found else None


def needed(path: Path, run=subprocess.run) -> set[str]:
    """The sonames ``path`` names in its ``NEEDED`` entries.

    Only ``NEEDED``: ``SONAME`` and ``RUNPATH`` are bracketed in the
    same way, and read as dependencies, every library would keep
    itself.
    """
    if not is_elf(path):
        return set()
    result = run(["readelf", "-d", "--wide", str(path)],
                 capture_output=True, text=True)
    if result.returncode != 0:
        # Taken as linking nothing, this library's dependencies would
        # look unreachable and be deleted from under it.
        raise RuntimeError(
            f"readelf could not read {path}: "
            f"{result.stderr.strip().splitlines()[-1:]}")
    return set(_NEEDED.findall(result.stdout))


def graph(root: Path, run=subprocess.run):
    """``(roots, libs, names)``: the sonames the roots need, what each
    Qt library needs (by its real file), and which real file each name
    a library is needed by stands for.

    A library shipped as ``libQt6Pdf.so.6.9.0`` is needed as
    ``libQt6Pdf.so.6``, the link beside it, so the walk -- which
    follows no links -- answers for the names of the links that
    resolve to it as well as its own.
    """
    roots: set[str] = set()
    libs: dict[Path, set[str]] = {}
    programs = [root / name for name in PROGRAMS
                if (root / name).is_file()]
    for path in programs + list(libraries(root)):
        wants = needed(path, run=run)
        if path.parent.parts[-len(QT_LIB):] == QT_LIB:
            libs[path.resolve()] = wants
        else:
            roots |= wants

    names = {real.name: real for real in libs}
    for path in root.rglob("*"):
        if path.is_symlink() and path.resolve() in libs:
            names.setdefault(path.name, path.resolve())
    return roots, libs, names


def reachable(root: Path, run=subprocess.run) -> set[str]:
    """Which sonames are reachable from something that runs.

    **Reachability and not a reference count**, as on macOS: QtQuick,
    QtQml, QtQmlModels and QtVirtualKeyboard link each other, so once
    the keyboard plugin that was their only root is gone, each still
    has a dependent and a count keeps the whole dead chain.

    The roots are everything that is not a Qt library: the two
    programs, the Python extension modules, every plugin Qt might
    ``dlopen``, and the non-Qt libraries.
    """
    return _closure(*graph(root, run=run))


def _closure(roots: set[str], libs: dict[Path, set[str]],
             names: dict[str, Path]) -> set[str]:
    seen: set[str] = set()
    queue = list(roots)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        if name in names:
            queue.extend(libs[names[name]])
    return seen


def remove_unused(root: Path, run=subprocess.run) -> int:
    """Drop the plugins, then every candidate nothing that runs can
    still reach.  Returns the bytes removed."""
    removed = 0

    for relative, reason in UNUSED_PLUGINS.items():
        plugin = find(root, relative)
        if plugin is None or not plugin.is_file():
            print(f"  {Path(relative).name}: already absent")
            continue
        removed += plugin.stat().st_size
        plugin.unlink()
        print(f"  removed {plugin.name} ({reason})")

    roots, libs, names = graph(root, run=run)
    live = _closure(roots, libs, names)
    doomed: dict[Path, str] = {}
    for module in ORPHAN_CANDIDATES:
        name = soname(module)
        if name not in names:
            continue
        if name in live:
            print(f"  keeping {name}: still reachable")
        else:
            doomed[names[name]] = name

    # A library that stays names what it needs whether or not anything
    # reaches it today, and a Qt library can be dlopen'ed by name; the
    # macOS rule, that a candidate something remaining links is kept,
    # holds here too.  Keeping one may keep what it names in turn.
    held = True
    while held:
        held = False
        for owner, wants in sorted(libs.items()):
            if owner in doomed:
                continue
            for want in sorted(wants):
                real = names.get(want)
                if real in doomed:
                    print(f"  keeping {doomed.pop(real)}: "
                          f"{owner.name} needs it")
                    held = True

    for real, name in sorted(doomed.items()):
        removed += real.stat().st_size
        real.unlink()
        print(f"  removed {name}, which nothing reaches")

    dangling = drop_dangling_links(root)
    if dangling:
        print(f"  removed {dangling} links to what was removed")
    return removed


def drop_dangling_links(root: Path) -> int:
    """Remove every symlink whose target is gone.  Returns the count.

    PyInstaller 6 links a library it collects into a package's
    subfolder from ``_internal/`` as well, so deleting the library
    leaves a link to nothing -- which ``appimagetool`` packs as it is,
    for a user's file manager to find broken.
    """
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() and not path.exists():
            path.unlink()
            count += 1
    return count


def vendored(root: Path, path: Path) -> bool:
    """Whether ``path`` is in a folder auditwheel vendored a wheel's
    dependencies into: ``numpy.libs``, ``scipy.libs``, at any depth.

    GNU ``strip`` over a file ``patchelf`` has rewritten can corrupt
    its program headers, and the loader then refuses it -- "ELF load
    command address/offset not page-aligned" -- which is how CI's
    AppImage died at the first numpy import.  These folders are not
    the only files ``patchelf`` touched: auditwheel also rewrites the
    extension modules that load from them (``_multiarray_umath``'s
    RPATH), and PySide6's own build rewrites its Qt libraries.  The
    rule is what the evidence required, no more: the loader refused
    OpenBLAS from ``numpy.libs``, and ``_multiarray_umath``, stripped,
    loaded.  Anything else ``strip`` misaligns is caught after the
    fact by :func:`misaligned` and put back.
    """
    return any(part.endswith(".libs")
               for part in path.relative_to(root).parts[:-1])


def misaligned(path: Path, run=subprocess.run) -> str:
    """What the loader would refuse in ``path``, or ``""``.

    The loader maps each LOAD segment a page at a time, so a
    segment's offset in the file and its address must be equal modulo
    its alignment; one that is not is "ELF load command
    address/offset not page-aligned".  A file ``readelf -lW`` cannot
    read is refused too.
    """
    result = run(["readelf", "-lW", str(path)],
                 capture_output=True, text=True)
    if result.returncode != 0:
        return (f"readelf could not read it: "
                f"{result.stderr.strip().splitlines()[-1:]}")
    for line in result.stdout.splitlines():
        fields = line.split()
        if not fields or fields[0] != "LOAD":
            continue
        offset, address = int(fields[1], 16), int(fields[2], 16)
        align = int(fields[-1], 16)
        if align > 1 and offset % align != address % align:
            return (f"a LOAD segment at offset {offset:#x}, address "
                    f"{address:#x}, alignment {align:#x} is not "
                    "page-aligned")
    return ""


def strip_all(root: Path, run=subprocess.run) -> tuple[int, int]:
    """``strip --strip-unneeded`` over every library auditwheel did not
    vendor, each read back and put back as it was if the loader would
    now refuse it.  Returns (files, bytes saved)."""
    saved = 0
    count = 0
    left = 0
    with tempfile.TemporaryDirectory(prefix="unstripped-") as kept:
        backup = Path(kept) / "original"
        for path in libraries(root):
            if vendored(root, path):
                left += 1
                continue
            before = path.stat().st_size
            shutil.copy2(path, backup)
            result = run(["strip", "--strip-unneeded", str(path)],
                         capture_output=True, text=True)
            # A library that refuses to strip is left as it is rather
            # than failing the build: the cost is size, not
            # correctness.
            if result.returncode != 0:
                print(f"  could not strip {path.name}: "
                      f"{result.stderr.strip().splitlines()[-1:]}")
                continue
            # The .libs rule names the files that broke, not every
            # file patchelf has rewritten; one strip breaks the same
            # way would load nowhere, and say so only at a user's
            # first import.
            wrong = misaligned(path, run=run)
            if wrong:
                shutil.copy2(backup, path)
                print(f"  restored {path.name} unstripped: {wrong}")
                continue
            after = path.stat().st_size
            if after < before:
                saved += before - after
                count += 1
    if left:
        print(f"  left {left} auditwheel-vendored libraries unstripped "
              f"(patchelf rewrote them; strip would break them)")
    return count, saved


def main(argv=None, run=subprocess.run) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2

    folder = Path(argv[0]).resolve()
    if not folder.is_dir():
        print(f"{folder} is not there", file=sys.stderr)
        return 1

    before = total(folder)
    print(f"{folder.name}: {before / 1e6:.0f} MB")

    dropped = remove_unused(folder, run=run)
    print(f"removed {dropped / 1e6:.0f} MB of unused Qt")

    count, saved = strip_all(folder, run=run)
    print(f"stripped {count} libraries, saving {saved / 1e6:.0f} MB")

    after = total(folder)
    print(f"{folder.name}: {after / 1e6:.0f} MB "
          f"({100 * (before - after) / before:.0f}% smaller)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
