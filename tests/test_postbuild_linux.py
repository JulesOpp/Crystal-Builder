"""
The Linux strip-and-prune pass, ``packaging/postbuild_linux.py``.

Nothing here runs ``readelf`` or ``strip``: neither is on a Mac, and
what they would read is a Linux build.  Every call goes through the
``run`` the functions take, and a :class:`Host` answers it -- from a
table of what each file needs, in ``readelf``'s own words, and by
halving a file it is asked to strip.  The files themselves are real
and small, ELF in their first four bytes only, in the folder
``linux.spec`` leaves.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import postbuild_linux  # noqa: E402

WINDOW = "Crystal Builder"
QT = "_internal/PySide6/Qt"

needs_symlinks = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows runners make no symlinks without developer mode; "
           "this script runs on Linux only")


def dump(*sonames: str, soname: str | None = None) -> str:
    """``readelf -d --wide`` as binutils prints it: NEEDED among the
    other bracketed entries, which are not dependencies."""
    entries = [("NEEDED", f"Shared library: [{name}]")
               for name in sonames]
    if soname:
        entries.append(("SONAME", f"Library soname: [{soname}]"))
    entries += [("RUNPATH", "Library runpath: [$ORIGIN]"),
                ("INIT", "0x6000"), ("NULL", "0x0")]
    tags = {"NEEDED": 1, "SONAME": 14, "RUNPATH": 29, "INIT": 12,
            "NULL": 0}
    lines = ["", f"Dynamic section at offset 0x2d6e8 contains "
                 f"{len(entries)} entries:",
             "  Tag        Type                         Name/Value"]
    for kind, value in entries:
        lines.append(f" 0x{tags[kind]:016x} {f'({kind})':<20} {value}")
    return "\n".join(lines) + "\n"


#: ``readelf -lW`` of a library whose LOAD segments are where the
#: loader wants them: each offset and its address agree modulo the
#: alignment (0x5f0 both, in the writable one).
SEGMENTS = """
Elf file type is DYN (Shared object file)
Entry point 0x0
There are 6 program headers, starting at offset 64

Program Headers:
  Type           Offset   VirtAddr           PhysAddr           FileSiz  MemSiz   Flg Align
  LOAD           0x000000 0x0000000000000000 0x0000000000000000 0x0a2f58 0x0a2f58 R   0x1000
  LOAD           0x0a3000 0x00000000000a3000 0x00000000000a3000 0x2b1c41 0x2b1c41 R E 0x1000
  LOAD           0x355000 0x0000000000355000 0x0000000000355000 0x0c9a70 0x0c9a70 R   0x1000
  LOAD           0x41f5f0 0x00000000004205f0 0x00000000004205f0 0x00fa30 0x0108f8 RW  0x1000
  DYNAMIC        0x428d50 0x0000000000429d50 0x0000000000429d50 0x000220 0x000220 RW  0x8
  GNU_STACK      0x000000 0x0000000000000000 0x0000000000000000 0x000000 0x000000 RW  0x10
"""  # noqa: E501

#: The same library as ``strip`` leaves one ``patchelf`` had rewritten:
#: the writable segment's offset moved and its address did not, and
#: the loader refuses it as "ELF load command address/offset not
#: page-aligned".
MISALIGNED = SEGMENTS.replace(
    "LOAD           0x41f5f0", "LOAD           0x41e9c8")


class Host:
    """``readelf`` and ``strip`` as a Linux build host answers them,
    for files named in ``needs``; anything else is not ELF.  A file
    named in ``misaligned`` comes out of ``strip`` with a segment the
    loader would refuse."""

    def __init__(self, needs: dict[str, tuple[str, ...]],
                 refuses: tuple[str, ...] = (),
                 misaligned: tuple[str, ...] = ()):
        self.needs = needs
        self.refuses = set(refuses)
        self.misaligned = set(misaligned)
        self.stripped: list[str] = []

    def __call__(self, argv, **kwargs):
        path = Path(argv[-1])
        if argv[:2] == ["readelf", "-lW"]:
            broken = (path.name in self.misaligned
                      and path.name in self.stripped)
            return subprocess.CompletedProcess(
                argv, 0, MISALIGNED if broken else SEGMENTS, "")
        if argv[:3] == ["readelf", "-d", "--wide"]:
            if path.name not in self.needs:
                return subprocess.CompletedProcess(
                    argv, 1, "", "readelf: Error: Not an ELF file - it "
                    "has the wrong magic bytes at the start\n")
            return subprocess.CompletedProcess(
                argv, 0, dump(*self.needs[path.name]), "")
        if argv[:2] == ["strip", "--strip-unneeded"]:
            if path.name in self.refuses:
                return subprocess.CompletedProcess(
                    argv, 1, "",
                    f"strip: {path}: file format not recognized\n")
            path.write_bytes(path.read_bytes()[:path.stat().st_size // 2])
            self.stripped.append(path.name)
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(f"not a command this script runs: {argv}")


#: What each file in :func:`collected` links, as a Linux PySide6 6.9
#: has it in outline: the virtual keyboard plugin is the only root of a
#: QtQuick chain, and the PDF image plugin the only root of QtPdf.
NEEDS = {
    WINDOW: ("libz.so.1", "libc.so.6"),
    "xtal": ("libz.so.1", "libc.so.6"),
    "QtWidgets.abi3.so": ("libQt6Widgets.so.6", "libQt6Core.so.6"),
    "libQt6Core.so.6": ("libc.so.6",),
    "libQt6Gui.so.6": ("libQt6Core.so.6",),
    "libQt6Widgets.so.6": ("libQt6Gui.so.6", "libQt6Core.so.6"),
    "libQt6Pdf.so.6": ("libQt6Gui.so.6", "libQt6Core.so.6"),
    "libQt6Qml.so.6": ("libQt6Core.so.6",),
    "libQt6QmlModels.so.6": ("libQt6Qml.so.6", "libQt6Core.so.6"),
    "libQt6Quick.so.6": ("libQt6QmlModels.so.6", "libQt6Qml.so.6",
                         "libQt6Gui.so.6"),
    "libQt6VirtualKeyboard.so.6": ("libQt6Quick.so.6",
                                   "libQt6Qml.so.6"),
    "libqpdf.so": ("libQt6Pdf.so.6", "libQt6Gui.so.6"),
    "libqtvirtualkeyboardplugin.so": ("libQt6VirtualKeyboard.so.6",),
    "libqxcb.so": ("libQt6Gui.so.6",),
}


def _file(path: Path, size: int = 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x7fELF" + bytes(size - 4))
    return path


@pytest.fixture
def collected(tmp_path) -> Path:
    """A ``dist/Crystal Builder`` as ``linux.spec`` leaves it, Qt's
    libraries under ``_internal/PySide6/Qt/lib`` with the top-level
    links PyInstaller 6 makes to them."""
    folder = tmp_path / "dist" / WINDOW
    _file(folder / WINDOW, 4096)
    _file(folder / "xtal", 4096)
    _file(folder / "_internal" / "PySide6" / "QtWidgets.abi3.so")
    for name in NEEDS:
        if name.startswith("libQt6"):
            _file(folder / QT / "lib" / name, 2_000_000)
    _file(folder / QT / "plugins/imageformats/libqpdf.so")
    _file(folder / QT / "plugins/platforminputcontexts"
          / "libqtvirtualkeyboardplugin.so")
    _file(folder / QT / "plugins/platforms/libqxcb.so")
    for name in ("libQt6Core.so.6", "libQt6Pdf.so.6"):
        (folder / "_internal" / name).symlink_to(f"PySide6/Qt/lib/{name}")
    return folder


def _qt_libs(folder: Path) -> set[str]:
    return {p.name for p in (folder / QT / "lib").iterdir()}


def test_needed_reads_the_sonames_readelf_lists(tmp_path):
    """The SONAME and RUNPATH entries are bracketed too; read as
    dependencies, every library would keep itself alive."""
    library = _file(tmp_path / "libQt6Pdf.so.6")
    asked = []

    def run(argv, **kwargs):
        asked.append(argv)
        return subprocess.CompletedProcess(argv, 0, dump(
            "libQt6Gui.so.6", "libQt6Core.so.6", "libstdc++.so.6",
            soname="libQt6Pdf.so.6"), "")

    assert postbuild_linux.needed(library, run=run) == {
        "libQt6Gui.so.6", "libQt6Core.so.6", "libstdc++.so.6"}
    assert asked == [["readelf", "-d", "--wide", str(library)]]


def test_a_file_that_is_not_elf_needs_nothing(tmp_path):
    """A data file with ``.so`` in its name is in the walk; it must
    count as linking nothing rather than stop the build."""
    data = tmp_path / "words.so.txt"
    data.write_text("not a library\n")
    assert postbuild_linux.needed(data, run=Host({})) == set()


def test_a_library_readelf_will_not_read_stops_the_prune(tmp_path):
    """Read as linking nothing, a real library would leave everything
    under it unreachable, and the prune would delete what it holds up.
    Stopping the build is the safe way to be wrong."""
    library = _file(tmp_path / "libQt6Gui.so.6")
    with pytest.raises(RuntimeError, match="libQt6Gui.so.6"):
        postbuild_linux.needed(library, run=Host({}))


@needs_symlinks
def test_an_orphan_nothing_needs_is_removed_and_one_still_needed_is_kept(
        collected, capsys):
    """A Python module that binds QtQuick keeps the whole chain under
    it, however sure the list is: the list says where to look, the
    links say what goes."""
    _file(collected / "_internal" / "PySide6" / "QtQuick.abi3.so")
    needs = dict(NEEDS, **{"QtQuick.abi3.so": ("libQt6Quick.so.6",)})

    postbuild_linux.remove_unused(collected, run=Host(needs))

    left = _qt_libs(collected)
    assert "libQt6Pdf.so.6" not in left
    assert {"libQt6Quick.so.6", "libQt6Qml.so.6",
            "libQt6QmlModels.so.6"} <= left
    assert "libQt6VirtualKeyboard.so.6" not in left
    out = capsys.readouterr().out
    assert "keeping libQt6Quick.so.6: still reachable" in out
    assert "removed libQt6Pdf.so.6" in out


@needs_symlinks
def test_a_candidate_a_remaining_library_needs_is_kept(
        collected, capsys):
    """Reachability decides what goes, but a library left behind that
    names a candidate -- one nothing reaches today and something
    might yet ``dlopen`` -- still holds it, and the log says which."""
    _file(collected / QT / "lib" / "libQt6QmlWorkerScript.so.6")
    needs = dict(NEEDS, **{
        "libQt6QmlWorkerScript.so.6": ("libQt6Qml.so.6",)})

    postbuild_linux.remove_unused(collected, run=Host(needs))

    left = _qt_libs(collected)
    assert {"libQt6Qml.so.6", "libQt6QmlWorkerScript.so.6"} <= left
    assert "libQt6Quick.so.6" not in left
    assert ("keeping libQt6Qml.so.6: libQt6QmlWorkerScript.so.6 "
            "needs it") in capsys.readouterr().out


@needs_symlinks
def test_a_library_reached_through_its_soname_link_passes_it_on(
        collected):
    """A library shipped as ``libQt6Pdf.so.6.9.0`` beside a
    ``libQt6Pdf.so.6`` link is needed by the link's name; walking only
    real files, its own needs would otherwise be keyed by a name
    nothing asks for, and lost."""
    lib = collected / QT / "lib"
    (lib / "libQt6Pdf.so.6").rename(lib / "libQt6Pdf.so.6.9.0")
    (lib / "libQt6Pdf.so.6").symlink_to("libQt6Pdf.so.6.9.0")
    _file(lib / "libQt6Svg.so.6")
    needs = dict(NEEDS, **{"libQt6Pdf.so.6.9.0": ("libQt6Svg.so.6",),
                           "libQt6Svg.so.6": ("libQt6Core.so.6",)})
    del needs["libQt6Pdf.so.6"]

    assert "libQt6Svg.so.6" in postbuild_linux.reachable(
        collected, run=Host(needs))


@needs_symlinks
def test_the_unused_plugins_go_first_so_their_frameworks_become_orphans(
        collected):
    """Before the plugins go, every candidate is reachable from one of
    them; after, the PDF library and the whole QtQuick chain are
    reachable from nothing, and only reachability -- not a count of
    dependents, which QtQuick still has -- sees that."""
    host = Host(NEEDS)
    assert "libQt6Quick.so.6" in postbuild_linux.reachable(
        collected, run=host)

    postbuild_linux.remove_unused(collected, run=host)

    plugins = collected / QT / "plugins"
    assert not (plugins / "imageformats" / "libqpdf.so").exists()
    assert not (plugins / "platforminputcontexts"
                / "libqtvirtualkeyboardplugin.so").exists()
    assert (plugins / "platforms" / "libqxcb.so").exists()
    assert _qt_libs(collected) == {
        "libQt6Core.so.6", "libQt6Gui.so.6", "libQt6Widgets.so.6"}


@needs_symlinks
def test_a_library_that_will_not_strip_is_reported_not_fatal(
        collected, capsys):
    """The cost of a library left unstripped is size, not correctness,
    so it is said and the rest are stripped.  The two programs are
    never touched: each carries PyInstaller's archive of the
    application."""
    host = Host(NEEDS, refuses=("libQt6Gui.so.6",))
    gui = collected / QT / "lib" / "libQt6Gui.so.6"
    before = gui.stat().st_size

    count, saved = postbuild_linux.strip_all(collected, run=host)

    assert gui.stat().st_size == before
    assert "could not strip libQt6Gui.so.6" in capsys.readouterr().out
    assert "libQt6Core.so.6" in host.stripped
    assert count == len(host.stripped)
    assert saved > 0
    assert WINDOW not in host.stripped and "xtal" not in host.stripped


#: Where auditwheel leaves a wheel's vendored libraries: rewritten by
#: ``patchelf``, which ``strip`` then corrupts.
VENDORED = "_internal/numpy.libs/libscipy_openblas64_-abc.so"


@needs_symlinks
def test_libraries_auditwheel_vendored_are_left_unstripped(collected):
    """CI's AppImage died at the first numpy import, the loader
    refusing ``libscipy_openblas64_`` as "ELF load command
    address/offset not page-aligned": ``strip`` had rewritten a file
    ``patchelf`` already had.  A Qt library beside it is still
    stripped."""
    vendored = _file(collected / VENDORED, 4096)
    host = Host(NEEDS)

    postbuild_linux.strip_all(collected, run=host)

    assert vendored.stat().st_size == 4096
    assert "libscipy_openblas64_-abc.so" not in host.stripped
    assert "libQt6Core.so.6" in host.stripped


@needs_symlinks
def test_the_report_counts_the_vendored_libraries_it_left_alone(
        collected, capsys):
    """Without the count, a build log that stripped fewer libraries
    than the last says nothing of why.  A ``.libs`` folder deeper in
    the tree is auditwheel's as well."""
    _file(collected / VENDORED)
    _file(collected / "_internal/scipy/scipy.libs/libgfortran-0.so.5")
    needs = dict(NEEDS, **{
        "libscipy_openblas64_-abc.so": ("libc.so.6",),
        "libgfortran-0.so.5": ("libc.so.6",)})

    assert postbuild_linux.main([str(collected)], run=Host(needs)) == 0

    assert ("left 2 auditwheel-vendored libraries unstripped (patchelf "
            "rewrote them; strip would break them)"
            in capsys.readouterr().out)


def test_segments_that_agree_with_their_addresses_are_not_misaligned(
        tmp_path):
    library = _file(tmp_path / "libQt6Core.so.6")

    def run(argv, **kwargs):
        assert argv == ["readelf", "-lW", str(library)]
        return subprocess.CompletedProcess(argv, 0, SEGMENTS, "")

    assert postbuild_linux.misaligned(library, run=run) == ""


def test_a_segment_whose_offset_and_address_disagree_is_named(tmp_path):
    """The loader's "not page-aligned" is this: a LOAD segment's file
    offset and its address must be equal modulo its alignment."""
    library = _file(tmp_path / "libscipy_openblas64_-abc.so")

    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, MISALIGNED, "")

    said = postbuild_linux.misaligned(library, run=run)

    assert "0x41e9c8" in said and "0x4205f0" in said
    assert "0x1000" in said


def test_a_library_readelf_cannot_read_after_stripping_is_misaligned(
        tmp_path):
    """A stripped file nothing can read is not one to ship."""
    library = _file(tmp_path / "libQt6Core.so.6")

    def run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1, "", "readelf: Error: no program headers\n")

    assert postbuild_linux.misaligned(library, run=run)


@needs_symlinks
def test_a_library_strip_misaligns_is_put_back_as_it_was(collected,
                                                         capsys):
    """The ``.libs`` rule covers the files the evidence named, and no
    more: any other file ``patchelf`` rewrote -- an extension module
    auditwheel pointed at its ``.libs``, a library a wheel's own build
    rewrote -- would come out of ``strip`` refused by the loader, and
    only at a user's first import.  So every stripped file is read
    back, and one the loader would refuse gets its original bytes
    again; the rest stay stripped."""
    gui = collected / QT / "lib" / "libQt6Gui.so.6"
    gui.write_bytes(b"\x7fELF" + b"original" * 1000)
    original = gui.read_bytes()
    core = collected / QT / "lib" / "libQt6Core.so.6"
    host = Host(NEEDS, misaligned=("libQt6Gui.so.6",))

    count, saved = postbuild_linux.strip_all(collected, run=host)

    assert gui.read_bytes() == original
    assert core.stat().st_size == 1_000_000
    out = capsys.readouterr().out
    assert "restored libQt6Gui.so.6" in out
    assert "not page-aligned" in out
    assert count == len(host.stripped) - 1


@needs_symlinks
def test_dangling_links_are_dropped_after_pruning(collected):
    """PyInstaller 6 links a library it collects into a subfolder from
    ``_internal`` as well; removing the library leaves that link
    pointing at nothing, which ``appimagetool`` packs as it is."""
    postbuild_linux.remove_unused(collected, run=Host(NEEDS))

    internal = collected / "_internal"
    assert not (internal / "libQt6Pdf.so.6").is_symlink()
    assert (internal / "libQt6Core.so.6").is_symlink()
    assert (internal / "libQt6Core.so.6").exists()


@needs_symlinks
def test_the_report_says_the_size_before_and_after(collected, capsys):
    """The saving is the reason the step exists, so the log of every
    build says it, measured on disk rather than added up."""
    before = postbuild_linux.total(collected)

    assert postbuild_linux.main([str(collected)], run=Host(NEEDS)) == 0

    after = postbuild_linux.total(collected)
    assert after < before
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"{WINDOW}: {before / 1e6:.0f} MB"
    assert lines[-1] == (f"{WINDOW}: {after / 1e6:.0f} MB "
                         f"({100 * (before - after) / before:.0f}% "
                         f"smaller)")
