"""
Strip the built macOS bundle, then sign it.

    python packaging/postbuild.py "dist/Crystal Builder.app"

**This is not a tidying step; it is most of the download.**  The VTK
wheel ships its dylibs with their full symbol tables: in
``libvtkCommonCore.dylib``, 54.7 MB of a 98.4 MB file is one
``__LINKEDIT`` segment.  Stripping that library alone saves more than
the entire application's own code weighs.

PyInstaller's own ``strip=True`` does not do it.  On macOS it runs
``strip -S``, which removes *debug* symbols, and these libraries have
none to remove -- what they have is a local symbol table, which is
``-x``.  Measured on ``libvtkCommonCore.dylib``: ``-S`` leaves it at
98.4 MB, ``-x`` takes it to 45.6.  So the specs leave ``strip`` off,
because it costs minutes of build time for nothing, and this runs
afterwards instead.

``-x`` removes local symbols and keeps every exported one, which is
what dynamic linking resolves against and what a Python extension's
``PyInit_*`` is.  VTK's rendering back ends register themselves
through C++ static initialisers rather than by symbol lookup, so they
are unaffected.  Nothing about that is obvious enough to trust, which
is why the caller runs ``--selftest`` against the result: it opens a
structure and draws it, and a stripped-too-far VTK cannot.

**Signing comes after stripping and not before.**  ``strip`` rewrites
the file, so a signature made first is invalidated by the very next
step -- ``strip`` says so in a warning that is easy to scroll past,
and the result on Apple silicon is a bundle that will not launch at
all.  Ad-hoc (``-s -``) is what this does; a Developer ID is a
separate decision recorded in the release notes.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

#: What gets stripped.  The main executable is left alone
#: deliberately: it is PyInstaller's bootloader, it is a few hundred
#: kilobytes, and it is the one file where being wrong means the
#: application does not start at all rather than fails a check.
SUFFIXES = (".so", ".dylib")

#: Qt plugins this application cannot use, and the reason each one is
#: refused.  Qt finds plugins by scanning a directory, so a missing
#: optional plugin is simply never offered; nothing looks one up by
#: name and fails.
#:
#: These two are worth more than they look.  Each is the *only* thing
#: in the bundle that links a chain of frameworks, so removing the
#: plugin orphans the chain: the PDF image reader is what drags in
#: QtPdf, and the on-screen keyboard is what drags in the whole of
#: QtQuick, QtQml and QtVirtualKeyboard.  Together that is about
#: 25 MB reachable from two files nothing in a desktop
#: crystallography application will ever call.
UNUSED_PLUGINS = {
    "PySide6/Qt/plugins/imageformats/libqpdf.dylib":
        "renders a PDF as an image; this application shows CIFs",
    "PySide6/Qt/plugins/platforminputcontexts/"
    "libqtvirtualkeyboardplugin.dylib":
        "an on-screen keyboard for touch devices",
}

#: Frameworks that become unreachable once the plugins above are
#: gone.  Nothing is deleted on the strength of this list alone --
#: :func:`dependents` re-checks each one against everything still in
#: the bundle, and a framework something turns out to link is kept and
#: reported.  The list only says where to look.
ORPHAN_CANDIDATES = (
    "QtPdf", "QtQuick", "QtQml", "QtQmlModels", "QtQmlMeta",
    "QtVirtualKeyboard", "QtVirtualKeyboardQml",
)


def strippable(root: Path):
    """Every shared library under the bundle."""
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            if path.suffix in SUFFIXES or ".dylib." in path.name:
                yield path


def total(root: Path) -> int:
    """Bytes on disk, following nothing."""
    return sum(p.stat().st_size for p in root.rglob("*")
               if p.is_file() and not p.is_symlink())


def strip_all(root: Path) -> tuple[int, int]:
    """``strip -x`` over the tree.  Returns (files, bytes saved)."""
    saved = 0
    count = 0
    for path in strippable(root):
        before = path.stat().st_size
        # `strip` warns that it invalidates the signature; it is
        # right, and the re-sign below is the answer.  A library that
        # refuses to strip is left as it is rather than failing the
        # build: the cost is size, not correctness.
        result = subprocess.run(
            ["strip", "-x", str(path)],
            capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  could not strip {path.name}: "
                  f"{result.stderr.strip().splitlines()[-1:]}")
            continue
        after = path.stat().st_size
        if after < before:
            saved += before - after
            count += 1
    return count, saved


def mach_o(root: Path):
    """Every Mach-O file in the tree, by content rather than by name.

    Qt's framework binaries have no extension at all, so a search by
    suffix misses exactly the files this needs to look inside.
    """
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            with path.open("rb") as handle:
                magic = handle.read(4)
        except OSError:
            continue
        # Little-endian 64-bit, and the fat/universal header.
        if magic in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            yield path


def links(path: Path) -> set[str]:
    """The Qt frameworks this binary names, by their short names.

    PyInstaller rewrites Qt's install names down to a bare
    ``@rpath/QtSvg``, not the ``@rpath/QtSvg.framework/Versions/A/QtSvg``
    the wheel ships.  Matching on ``QtSvg.framework/`` therefore finds
    nothing and cheerfully reports that every framework is unused,
    which is a convincing way to delete something load-bearing.
    """
    listed = subprocess.run(
        ["otool", "-L", str(path)], capture_output=True, text=True)
    found = set()
    for line in listed.stdout.splitlines()[1:]:
        name = line.strip().split(" ")[0]
        if name.startswith("@rpath/Qt"):
            found.add(name[len("@rpath/"):])
    return found


def reachable(root: Path) -> set[str]:
    """Which Qt frameworks are reachable from something that runs.

    **Reachability and not a reference count**, and the difference is
    not academic here.  QtQuick, QtQml, QtQmlModels, QtQmlMeta and
    QtVirtualKeyboard all link *each other*, so once the virtual
    keyboard plugin that was their only live root is gone, every one
    of them still has a dependent and a count-based pass keeps the
    whole dead cycle -- while reporting, quite truthfully and quite
    uselessly, that each is still linked by another.

    The roots are everything that is not itself a Qt framework: the
    bootloader, the Python extension modules, the plugins Qt will
    actually load, and the non-Qt dylibs.
    """
    libs = root / "Contents" / "Frameworks" / "PySide6" / "Qt" / "lib"
    binaries = list(mach_o(root))

    edges = {}
    roots: set[str] = set()
    for path in binaries:
        if libs in path.parents:
            # Key a framework by its short name, e.g. "QtQuick".
            owner = next(p for p in path.parents
                         if p.name.endswith(".framework"))
            edges.setdefault(owner.name[:-len(".framework")],
                             set()).update(links(path))
        else:
            roots |= links(path)

    seen: set[str] = set()
    queue = list(roots)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        queue.extend(edges.get(name, ()))
    return seen


def remove_unused(root: Path) -> int:
    """Drop the plugins, then every candidate framework nothing that
    runs can still reach.  Returns the bytes removed."""
    removed = 0

    for relative, reason in UNUSED_PLUGINS.items():
        plugin = root / "Contents" / "Frameworks" / relative
        if not plugin.is_file():
            print(f"  {Path(relative).name}: already absent")
            continue
        removed += plugin.stat().st_size
        plugin.unlink()
        print(f"  removed {Path(relative).name} ({reason})")

    live = reachable(root)
    libs = root / "Contents" / "Frameworks" / "PySide6" / "Qt" / "lib"
    for name in ORPHAN_CANDIDATES:
        framework = libs / f"{name}.framework"
        if not framework.is_dir():
            continue
        if name in live:
            print(f"  keeping {name}: still reachable")
            continue
        removed += sum(p.stat().st_size
                       for p in framework.rglob("*")
                       if p.is_file() and not p.is_symlink())
        shutil.rmtree(framework)
        print(f"  removed {name}.framework, which nothing reaches")

    dangling = drop_dangling_links(root)
    if dangling:
        print(f"  removed {dangling} links to what was removed")
    return removed


def drop_dangling_links(root: Path) -> int:
    """Remove every symlink whose target is gone.  Returns the count.

    PyInstaller links each framework into ``Contents/Frameworks`` and
    ``Contents/Resources`` by its short name, so deleting a framework
    leaves two links to nothing.  ``codesign --verify --strict`` then
    fails with a bare "No such file or directory" naming the bundle,
    not the link, and ``spctl`` rejects the application.
    """
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() and not path.exists():
            path.unlink()
            count += 1
    return count


def declared_minimum(bundle: Path) -> tuple[int, ...]:
    """``LSMinimumSystemVersion`` from the bundle's Info.plist."""
    with (bundle / "Contents" / "Info.plist").open("rb") as handle:
        version = plistlib.load(handle)["LSMinimumSystemVersion"]
    return version_tuple(version)


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def required_minimum(path: Path) -> tuple[int, ...] | None:
    """The oldest macOS a Mach-O file says it loads on.

    ``minos`` in ``LC_BUILD_VERSION``, or ``version`` in the older
    ``LC_VERSION_MIN_MACOSX``; the highest of them in a fat file.
    """
    listed = subprocess.run(
        ["otool", "-l", str(path)], capture_output=True, text=True)
    found = []
    command = None
    for line in listed.stdout.splitlines():
        words = line.split()
        if words[:1] == ["cmd"]:
            command = words[1]
        elif (command == "LC_BUILD_VERSION" and words[:1] == ["minos"]
              or command == "LC_VERSION_MIN_MACOSX"
              and words[:1] == ["version"]):
            found.append(version_tuple(words[1]))
    return max(found) if found else None


def too_new(bundle: Path) -> list[tuple[Path, tuple[int, ...]]]:
    """Every binary that needs a newer macOS than the bundle declares.

    **This is the check that the selftest cannot be.**  numpy and
    scipy publish two arm64 wheels, one for macOS 14 linked against
    the new Accelerate and one for macOS 12 on OpenBLAS, and pip
    takes the one that suits the machine it runs on.  A macOS 14
    runner therefore builds a bundle that dies importing numpy on
    macOS 13 (``Symbol not found: _cblas_caxpy$NEWLAPACK$ILP64``),
    and passes its own selftest, because the runner is macOS 14.
    """
    floor = declared_minimum(bundle)
    return [(path, needed) for path in mach_o(bundle)
            if (needed := required_minimum(path)) and needed > floor]


def sign(bundle: Path) -> None:
    """Ad-hoc signature over the whole bundle.

    Required on Apple silicon, where an unsigned bundle does not
    launch.  It is still Gatekeeper-blocked for anybody who did not
    build it, which the release notes explain.
    """
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(bundle)],
        check=True, capture_output=True, text=True)
    subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(bundle)],
        check=True, capture_output=True, text=True)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2

    bundle = Path(argv[0]).resolve()
    if not bundle.is_dir():
        print(f"{bundle} is not there", file=sys.stderr)
        return 1

    before = total(bundle)
    print(f"{bundle.name}: {before / 1e6:.0f} MB")

    count, saved = strip_all(bundle)
    print(f"stripped {count} libraries, saving {saved / 1e6:.0f} MB")

    dropped = remove_unused(bundle)
    print(f"removed {dropped / 1e6:.0f} MB of unused Qt")

    offenders = too_new(bundle)
    if offenders:
        floor = ".".join(map(str, declared_minimum(bundle)))
        print(f"{len(offenders)} binaries need a newer macOS than the "
              f"{floor} Info.plist declares:", file=sys.stderr)
        for path, needed in offenders[:20]:
            print(f"  {'.'.join(map(str, needed))}  "
                  f"{path.relative_to(bundle)}", file=sys.stderr)
        return 1

    sign(bundle)
    after = total(bundle)
    print(f"{bundle.name}: {after / 1e6:.0f} MB signed "
          f"({100 * (before - after) / before:.0f}% smaller)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
