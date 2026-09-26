"""
xtal.workspace
==============
Where a calculation leaves what it produced.

Running an optimisation makes a trajectory, a log and a final
structure.  Before this they existed only inside a panel until the
window closed, and nothing said *this run belongs to that structure*.
A workspace says it, on disk, in a layout anybody can read::

    <workspace>/workspace.json     the format version, and nothing else
    <workspace>/MFU4l/             one folder per structure
        MFU4l.cif                  a copy, so the workspace is whole
        MFU4l.xtalproj             the session, saved beside it
        uff-optimise-001/
            run.log                what happened, in order
            trajectory.extxyz      every step
            final.cif              the relaxed structure
        uff-single-point-002/
            run.log
    <workspace>/pcu-N59-E32/       a structure that was built, not opened
        pcu-N59-E32.cif            the framework, and the net over it
        mof-build-001/
            run.log                the build that made it
    <workspace>/blocks/            the building blocks drawn here
        my-paddlewheel.xyz         read back by the MOF builder

Four decisions hold the rest of it up.

**It is an ordinary folder, and it is always there.**  A scratch folder
cleaned on exit will one day throw away a six-hour run, and a folder
chosen under ``~/Library/Application Support`` is one nobody can find
in Finder.  So a workspace is a directory in the home folder that can
be opened, copied, backed up and deleted like any other -- and the
application makes the default one on a first run rather than working
without it, which is a reversal: it used to guess at nothing and the
price was runs and builds kept nowhere at all.  Where it goes is
Preferences' answer and the user's to change.

**Nothing in it is hidden, and nothing needs this module to read it.**
Every artefact is a real file with a real name and a format something
else can open.  ``workspace.json`` names the format version, so a
directory can say it is a workspace; it is not an index, and this
module never trusts it over the files themselves.  Deleting the folder
in Finder is a supported way to clean up, and so is adding a file to it
by hand.

**A run folder is named by what made it**, ``<module>-<kind>-<nnn>``,
numbered per structure in the order the runs happened.  The number is
the only state, and it is derived by looking at what is already there
rather than stored.

**The module that runs writes the folder** (:class:`RunFolder`), not
the tree that displays it -- so a run started from the CLI or a script
produces the identical layout and opens in the window.
"""

from __future__ import annotations

import filecmp
import json
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE_FILE = "workspace.json"

#: Where unsaved edits are kept between saves.  A dot-folder, so
#: :meth:`Workspace.entries` -- which skips them -- never mistakes it
#: for a structure, and the tree never shows it.
AUTOSAVE_DIR = ".autosave"
FORMAT_VERSION = 1

#: The one folder in a workspace that is not a structure --
#: see :attr:`Workspace.blocks`.
BLOCKS_DIR = "blocks"

LOG_NAME = "run.log"
TRAJECTORY_NAME = "trajectory.extxyz"
FINAL_NAME = "final.cif"

# Characters that are awkward in a path on one of the two platforms
# this ships on, plus the ones a shell would need quoted.  A structure
# called "Fe(bpy)3 2+" has to become a folder name without becoming
# unrecognisable.
_UNSAFE = re.compile(r'[^A-Za-z0-9._+-]+')
# A run folder is <module>-<kind>-<nnn>.  The module may not contain a
# hyphen and the kind may, which is what keeps the split unambiguous
# from either end -- "uff-single-point-002" is uff, single-point, 2.
# The module's own name is folded into that charset by `next_run`, so
# a module called "dftb+" gets a folder this can still read back.
_RUN_DIR = re.compile(r"^(?P<module>[a-z0-9._+]+)-"
                      r"(?P<kind>[a-z0-9._+-]+?)"
                      r"-(?P<index>\d+)$")


def resolved(path) -> Path | None:
    """A path as the filesystem knows it, for asking "is this the
    same file".

    Resolving settles a symlink and ``/var`` versus ``/private/var``,
    which are one file spelled two ways.  ``None`` for no path at all
    -- a document never saved -- and never the current directory,
    which is what ``Path("")`` resolves to.  A path that cannot be
    resolved (a volume gone, a permission withdrawn) is kept as it is
    spelled rather than dropped, so it still matches itself.

    The tab set and the workspace tree each had their own, and they
    disagreed on exactly that last case.
    """
    if not path:
        return None
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path)


#: What decomposing a name does not reach: letters with no accent to
#: take off, and the Greek alphabet, which is how phases are named --
#: alpha-quartz and beta-cristobalite differ only in the letter.
_SPELLED = {
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o",
    "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "þ": "th",
    "Þ": "Th", "ð": "d", "Ð": "D", "ı": "i",
    **dict(zip(
        "αβγδεζηθικλμνξοπρστυφχψω",
        ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta",
         "theta", "iota", "kappa", "lambda", "mu", "nu", "xi",
         "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi",
         "chi", "psi", "omega"), strict=True)),
    **dict(zip(
        "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ",
        ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta",
         "Theta", "Iota", "Kappa", "Lambda", "Mu", "Nu", "Xi",
         "Omicron", "Pi", "Rho", "Sigma", "Tau", "Upsilon", "Phi",
         "Chi", "Psi", "Omega"), strict=True)),
    "ς": "sigma",
}


def safe_name(text: str, fallback: str = "structure") -> str:
    """A file name that keeps its meaning on macOS and on Windows.

    Accents are taken off rather than the letter with them: the file
    systems cope with "é" but do not agree on how to spell it (macOS
    decomposes, Windows does not), and a name that compares unequal to
    itself is worse than one without the accent.  So "café" is "cafe",
    where it used to be "caf" and the same folder as "cafè".
    """
    text = "".join(_SPELLED.get(c, c) for c in str(text))
    text = "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))
    return _legacy_safe_name(text, fallback)


def _legacy_safe_name(text: str, fallback: str = "structure") -> str:
    """What :func:`safe_name` was before it transliterated: anything
    outside ASCII simply deleted.  Kept because workspaces made then
    have folders named this way, and opening the same file again has
    to find them."""
    cleaned = _UNSAFE.sub("_", str(text)).strip("._")
    return cleaned or fallback


def _numbered(stem: str):
    """``stem``, then ``stem-2``, ``stem-3``, without an end.

    Two callers number a folder past a collision and they have to
    number it the same way, or a structure added twice by two routes
    lands in two folders that only one of them can find again.
    """
    yield stem
    index = 1
    while True:
        index += 1
        yield f"{stem}-{index}"


# ======================================================================
#  ARTEFACTS
# ======================================================================

@dataclass(frozen=True)
class Artifact:
    """One thing in a workspace, and what it is.

    ``kind`` is the question every consumer asks -- the tree picks an
    icon from it, the window picks a viewer from it -- and it is
    deliberately not the extension.  A ``.cif`` that is a run's output
    and a ``.cif`` that is the input want the same viewer and different
    labelling, which an extension cannot express.
    """

    kind: str               # "structure" | "trajectory" | "log" |
                            # "final" | "project" | "image" |
                            # "pattern" |
                            # "report" | "file"
    path: Path
    label: str = ""

    @property
    def name(self) -> str:
        return self.label or self.path.name

    @property
    def exists(self) -> bool:
        return self.path.exists()


def classify(path) -> str:
    """What kind of artefact a file in a run folder is."""
    path = Path(path)
    suffix = path.suffix.lower()
    if path.name == LOG_NAME or suffix == ".log":
        return "log"
    if path.name == "report.json":
        # What the Results panel showed, kept so that it can show it
        # again: see xtal.modules.report.save.
        return "report"
    if suffix in (".extxyz", ".traj"):
        return "trajectory"
    if suffix == ".xtalproj":
        return "project"
    if suffix in (".png", ".svg", ".jpg", ".jpeg"):
        # A plot a run left behind.  Its own kind because the window
        # opens it in something else entirely -- there is no reading a
        # picture into a structure, and dispatching on the extension
        # would have tried.
        return "image"
    if suffix in (".xy", ".xye"):
        # A powder pattern -- measured, or one a run calculated.  It
        # opens in the refinement workbench; open as a structure it
        # was an error message.
        return "pattern"
    if path.stem == "final":
        return "final"
    if suffix in (".cif", ".mcif", ".xyz", ".gen", ".cssr", ".res"):
        return "structure"
    return "file"


@dataclass
class Run:
    """One calculation that has been run against a structure."""

    path: Path
    module: str = ""
    kind: str = ""
    index: int = 0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def label(self) -> str:
        words = self.kind.replace("-", " ") if self.kind else "run"
        return f"{self.module or '?'} {words} {self.index:03d}".strip()

    @property
    def log_path(self) -> Path:
        return self.path / LOG_NAME

    @property
    def trajectory_path(self) -> Path:
        return self.path / TRAJECTORY_NAME

    @property
    def final_path(self) -> Path:
        return self.path / FINAL_NAME

    def artifacts(self) -> list[Artifact]:
        """What the run actually left behind, in a fixed order.

        Read from the directory rather than from a manifest: a run that
        was killed wrote some of these and not others, and the truth
        about which is the directory.
        """
        preferred = [self.final_path, self.trajectory_path,
                     self.log_path]
        out = [Artifact(classify(p), p) for p in preferred
               if p.exists()]
        rest = sorted(self.path.iterdir()) if self.path.is_dir() else []
        for child in rest:
            if child.is_file() and child not in set(preferred):
                out.append(Artifact(classify(child), child))
        return out

    @classmethod
    def at(cls, path) -> Run | None:
        """Read a run folder's name back, or ``None`` if it is not one."""
        path = Path(path)
        match = _RUN_DIR.match(path.name)
        if not match:
            return None
        return cls(path=path, module=match["module"],
                   kind=match["kind"], index=int(match["index"]))


@dataclass
class Entry:
    """One structure in a workspace, and the runs underneath it."""

    path: Path                          # the structure's own folder
    workspace: Workspace | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def structure_path(self) -> Path | None:
        """The copy of the file this entry was made from."""
        for artifact in self.files():
            if artifact.kind == "structure":
                return artifact.path
        return None

    @property
    def project_path(self) -> Path:
        """Where the session for this entry is saved.

        Beside the structure and inside the entry, which is what makes
        a reopened project find its own workspace by looking upwards
        rather than by remembering an absolute path that a moved folder
        would falsify.
        """
        return self.path / f"{self.name}.xtalproj"

    def files(self) -> list[Artifact]:
        """The loose files of the entry -- its structure and its
        project -- and not the runs."""
        if not self.path.is_dir():
            return []
        return [Artifact(classify(p), p)
                for p in sorted(self.path.iterdir()) if p.is_file()]

    def runs(self) -> list[Run]:
        """Every run folder underneath, oldest first."""
        if not self.path.is_dir():
            return []
        found = [Run.at(p) for p in self.path.iterdir() if p.is_dir()]
        return sorted((r for r in found if r is not None),
                      key=lambda r: (r.index, r.name))

    def next_run(self, module: str, kind: str) -> RunFolder:
        """Make the next run folder for this entry.

        Numbered across the whole entry rather than per kind, so the
        folder names sort into the order the runs happened -- which is
        the order anybody looking for "the one I ran after lunch"
        wants.
        """
        # The module keeps no hyphen: it is the separator, and a
        # module called "single-point-energy" would otherwise make a
        # folder name that reads back as a different module.
        module = safe_name(module, "module").lower().replace("-", "_")
        kind = safe_name(kind, "run").lower()
        index = max((r.index for r in self.runs()), default=0) + 1
        # Refusing to share a folder is right; failing is not.  Two
        # runs started together -- a scan in one tab, an optimisation
        # in another -- both read the same maximum, and the second
        # takes the next number rather than a FileExistsError out of
        # a worker thread.
        for _ in range(1000):
            path = self.path / f"{module}-{kind}-{index:03d}"
            try:
                path.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                index += 1
                continue
            return RunFolder(Run(path, module, kind, index))
        raise FileExistsError(f"no free run folder under {self.path}")


# ======================================================================
#  THE WORKSPACE
# ======================================================================

@dataclass(frozen=True)
class FiledBuild:
    """Where :meth:`Workspace.adopt_build` put a build."""

    entry: Entry
    path: Path                      # the one CIF, written from the build
    run: Path | None = None         # the run folder, if it was moved


class NotAWorkspace(ValueError):
    """The directory is not a workspace, and was expected to be one."""


class Workspace:
    """A directory that structures and their calculations live in."""

    def __init__(self, root):
        self.root = Path(root)

    # -- making and finding one ----------------------------------------

    @classmethod
    def create(cls, root) -> Workspace:
        """Make a workspace, or adopt a directory that is already one.

        Adopting rather than refusing is deliberate: "New workspace"
        pointed at a folder that already is one should open it, not
        stop with an error about a file the user has never seen.
        """
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        marker = root / WORKSPACE_FILE
        if not marker.exists():
            marker.write_text(json.dumps(
                {"format": "crystal-builder-workspace",
                 "version": FORMAT_VERSION}, indent=1) + "\n",
                encoding="utf-8")
        return cls(root)

    @classmethod
    def open(cls, root) -> Workspace:
        root = Path(root)
        if not cls.is_workspace(root):
            raise NotAWorkspace(
                f"{root} has no {WORKSPACE_FILE}, so it is a folder "
                f"and not a workspace")
        return cls(root)

    @staticmethod
    def is_workspace(path) -> bool:
        return (Path(path) / WORKSPACE_FILE).is_file()

    @classmethod
    def find(cls, path) -> Workspace | None:
        """The workspace a path is inside, by looking upwards.

        This is how a reopened project finds the workspace it belongs
        to.  Walking up beats storing the root in the project file: a
        workspace that was moved, renamed or copied to another machine
        still answers, and a stored absolute path would not.
        """
        current = Path(path).resolve()
        if current.is_file():
            current = current.parent
        for candidate in (current, *current.parents):
            if cls.is_workspace(candidate):
                return cls(candidate)
        return None

    def _marker_data(self) -> dict:
        """The marker file's contents, or ``{}`` for anything else.

        Valid JSON is not the same as a marker: ``[1, 2]`` or ``null``
        parse, and then every ``.get`` on them raises -- while the
        workspace is being opened, before there is a window to say so
        in, which is the path the degraded window exists to survive.
        """
        try:
            data = json.loads(
                (self.root / WORKSPACE_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def version(self) -> int:
        try:
            return int(self._marker_data().get("version", 0))
        except (TypeError, ValueError):
            return 0

    # -- entries -------------------------------------------------------

    def entries(self) -> list[Entry]:
        """Every structure folder, in name order.

        Read from the directory every time.  A workspace is a few dozen
        folders and the filesystem is the authority on what is in it --
        an index would be a second answer to the same question and the
        one that goes stale when a user moves a folder in Finder.

        A folder that cannot be read is empty rather than fatal.  On
        macOS a workspace in Downloads or Documents is behind a TCC
        prompt that a relaunched application has not been granted yet,
        and ``iterdir`` raises ``PermissionError`` from inside window
        construction -- which took the whole launch down, on the one
        path where there is no window to report it in.
        """
        try:
            children = sorted(self.root.iterdir())
        except OSError:
            return []
        return [Entry(path=p, workspace=self)
                for p in children
                if p.is_dir() and not p.name.startswith(".")]

    def entry(self, name: str) -> Entry | None:
        path = self.root / name
        return Entry(path=path, workspace=self) if path.is_dir() \
            else None

    def entry_for(self, path) -> Entry | None:
        """The entry a path inside the workspace belongs to."""
        try:
            relative = Path(path).resolve().relative_to(
                self.root.resolve())
        except ValueError:
            return None
        parts = relative.parts
        return self.entry(parts[0]) if parts else None

    def autosave_path(self, path) -> Path | None:
        """Where the unsaved edits of the file at ``path`` are kept.

        Mirrors the file's place in the workspace -- ``MOF-5/MOF-5.cif``
        is kept as ``.autosave/MOF-5/MOF-5.xtalproj`` -- so two files
        of one name in two entries are two autosaves, and a project so
        that everything a session holds survives.  **Never the file
        itself**: Save converts and overwriting is silent, and both
        would stop meaning what they say if a timer could write where
        Save writes.  ``None`` for a path outside the workspace.
        """
        root = self.root.resolve()
        try:
            relative = Path(path).resolve().relative_to(root)
        except (ValueError, OSError):
            return None
        if not relative.parts or relative.parts[0] == AUTOSAVE_DIR:
            return None
        return (self.root / AUTOSAVE_DIR / relative).with_suffix(
            ".xtalproj")

    def add_structure(self, source, name: str | None = None) -> Entry:
        """Copy a structure file in, and give it a folder of its own.

        **Copied, not referenced.**  A workspace that points at a file
        the user then edits, renames or deletes is a tree full of
        broken nodes; the copy costs kilobytes and the original path is
        recorded by the caller in ``structure.meta["source"]``.

        Opening the same file twice gets the same entry rather than a
        second one, because that is what "open MFU4l.cif again" means.
        Opening two *different* files that happen to share a name gets
        two, and that is the half this used to get wrong: the name
        alone decided, so the second copy landed on the first and the
        workspace kept one of them without saying so.  Two people's
        MFU4l.cif are two structures.  The bytes are the only thing
        that can tell them apart and a structure file is kilobytes.
        """
        source = Path(source)
        stem = safe_name(name or source.stem, "structure")
        legacy = _legacy_safe_name(name or source.stem, "structure")
        if legacy != stem:
            # A workspace from before accents were kept filed this
            # file under the old spelling; the bytes say whether it is
            # the same one.
            for candidate in _numbered(legacy):
                folder = self.root / candidate
                if not folder.exists():
                    break
                target = folder / source.name
                if target.exists() and filecmp.cmp(source, target,
                                                   shallow=False):
                    return Entry(path=folder, workspace=self)
        for candidate in _numbered(stem):
            folder = self.root / candidate
            target = folder / source.name
            if folder.exists() and target.exists():
                if filecmp.cmp(source, target, shallow=False):
                    return Entry(path=folder, workspace=self)
                # The same name over different bytes.  Try the next.
                continue
            folder.mkdir(parents=True, exist_ok=True)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            return Entry(path=folder, workspace=self)

    @property
    def blocks(self) -> Path:
        """Where building blocks drawn in this workspace are kept.

        One folder and not an entry each, because PORMAKE reads blocks
        by globbing a *directory*: a block per entry would be a
        directory per block to register, and the catalogue takes a
        list of folders rather than a list of files.

        It is still an ordinary directory of the workspace, so
        :meth:`entries` finds it and the tree shows it with every
        block in it as a node that opens -- which is the whole point
        of drawing one here rather than into a folder somewhere else.

        Not created here.  A workspace nobody has drawn a block in
        should not have an empty folder in it explaining that.
        """
        return self.root / BLOCKS_DIR

    def add_document(self, name: str) -> Entry:
        """An entry for a structure that has no file yet.

        A structure built from nothing still has runs to put somewhere.

        The folder of that name if there already is one, which is what
        a module filing every build under its own label wants.  A
        *structure* wants :meth:`new_document` instead -- see there
        for the difference.
        """
        entry = Entry(path=self.root / safe_name(name, "structure"),
                      workspace=self)
        entry.path.mkdir(parents=True, exist_ok=True)
        return entry

    def new_document(self, name: str) -> Entry:
        """An entry no other structure is already living in.

        The difference from :meth:`add_document` is the whole point of
        it being a second method.  Two structures that happen to be
        called the same are still two structures, and the entry a
        built one is filed in holds ``<name>.cif`` -- which is the
        same file ``add_structure`` writes for an opened one.  So a
        phenol built from SMILES into the folder of a ``phenol.cif``
        somebody has open would take that crystal's workspace copy
        and leave the tab open over atoms that are no longer in the
        file underneath it.

        Numbered rather than refused, because a build has already
        happened by the time this is asked: there is a structure to
        put somewhere and no question left to ask about it.
        """
        stem = safe_name(name, "structure")
        candidate = next(c for c in _numbered(stem)
                         if not (self.root / c).exists())
        entry = Entry(path=self.root / candidate, workspace=self)
        entry.path.mkdir(parents=True)
        return entry

    def rename(self, path, name: str) -> Path:
        """Give a file in this workspace a new name, in the same folder.

        A file only: an entry's folder is the structure's name and a
        run's folder is how :meth:`Run.at` reads the run back, so
        renaming either is a tree that no longer says what it held.

        **Never over another file**, which is what ``Path.rename``
        does on POSIX without a word.  A change of case alone is let
        through, because on macOS the "other file" is this one.  The
        file's autosave goes with it, since it is kept by path and
        would otherwise be offered back to nothing.

        Raises ``ValueError`` with a sentence for the status bar.
        """
        path = Path(path)
        name = name.strip()
        if not path.is_file():
            raise ValueError(f"{path.name} is not a file")
        root = self.root.resolve()
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            raise ValueError(f"{path.name} is not in this "
                             f"workspace") from None
        if (len(relative.parts) < 2
                or relative.parts[0] == AUTOSAVE_DIR):
            raise ValueError(f"{path.name} is the workspace's own "
                             f"and keeps its name")
        if not name or name in (".", ".."):
            raise ValueError("a file needs a name")
        if any(c in name for c in "/\\:"):
            raise ValueError(f"'{name}' has a folder separator in it")
        if name.startswith("."):
            raise ValueError(f"'{name}' would hide the file")
        target = path.with_name(name)
        # Compared by name and never as paths: a WindowsPath equals
        # its own name in another case, so ``target == path`` took a
        # change of case for no change and renamed nothing.
        if target.name == path.name:
            return path
        if target.exists() and not target.samefile(path):
            raise ValueError(f"there is already a {name} here")
        saved = self.autosave_path(path)
        path.rename(target)
        moved = self.autosave_path(target)
        if (saved is not None and moved is not None
                and saved != moved and saved.exists()
                and not moved.exists()):
            moved.parent.mkdir(parents=True, exist_ok=True)
            saved.rename(moved)
        return target

    def adopt_build(self, structure, *, run=None,
                    artifacts=()) -> FiledBuild:
        """File a structure built from nothing, and the run that
        built it, as one entry.

        **One CIF, and it is written from the structure.**  A module
        that made its structure by writing a file and reading it back
        -- which is how PORMAKE builds -- has a copy of its own in the
        run folder, and that copy is the framework as PORMAKE left it:
        before the net was drawn over it, and so no longer the thing
        that was built.  Writing ours and dropping theirs is the only
        arrangement where the file in the workspace is the document
        and there is one of it.  ``artifacts`` is what the module said
        it wrote (``JobResult.artifacts``), so this asks the run which
        file that was rather than guessing at its folder.

        **The run moves under the thing it built.**  A run folder is
        opened before the build starts and a build has no name until
        it finishes, so it is written under an entry named for the
        *module* -- right while it is going, wrong once there is a
        framework to name it after.  The placeholder is removed when
        that was the only run in it.

        This lived in the window (``ModuleRunner._file_build``), and
        ``xtal run mof.build --workspace`` therefore left the build
        under the placeholder with PORMAKE's poorer copy beside it.
        Filing is a rule about a folder, not about a window.

        ``new_document`` and not ``add_document``: a build has no
        file, only a title another structure may already be using.
        """
        from xtal.io import FORMATS

        entry = self.new_document(
            str(structure.meta.get("title") or ""))
        path = entry.path / f"{entry.name}.cif"
        FORMATS.write(structure, path)
        # Before the move, while these paths are still where the
        # module left them.
        for artifact in artifacts or ():
            source = Path(artifact)
            if source.is_file() and source.suffix.lower() == ".cif":
                source.unlink()
        moved = None
        source = Path(run) if run is not None else None
        if source is not None and source.is_dir() \
                and source.parent != entry.path:
            placeholder = source.parent
            moved = Path(shutil.move(str(source), str(entry.path)))
            try:
                # Non-empty means another run of the same module is
                # filed there, which is a folder to leave alone.
                placeholder.rmdir()
            except OSError:
                pass
        return FiledBuild(entry=entry, path=path, run=moved)

    # -- session -------------------------------------------------------

    @property
    def session(self) -> dict:
        """What was open in this workspace when it was last left.

        ``{"open": [relative paths], "active": index}``.

        **Advisory, and nothing more.**  A key written by a newer
        version, a marker somebody edited by hand, a file that is no
        longer there -- every one of them reads as "nothing was open",
        because a workspace that will not open until a deleted file is
        put back is worse than one that opens with no tabs.

        This is not an index of what the workspace *contains*.
        :meth:`entries` reads the directory and stays the authority on
        that; this only remembers which of them somebody was looking
        at.
        """
        try:
            stored = self._marker_data()["session"]
            # A string is iterable too, and "a.cif" read as a list is
            # five one-letter paths, one of them "." -- the root.
            if not isinstance(stored["open"], list):
                raise TypeError
            paths = [str(p) for p in stored["open"]]
            active = int(stored.get("active", 0))
        except (LookupError, TypeError, ValueError, AttributeError):
            return {"open": [], "active": 0}
        return {"open": paths, "active": active}

    def session_paths(self) -> list[Path]:
        """The remembered paths that are still there, in order.

        Only files *inside* the workspace: :meth:`set_session` never
        writes any other kind, and a marker from a shared or synced
        folder does not get to name ``/etc/passwd`` as a tab -- an
        absolute right-hand side makes ``root / name`` discard the
        root altogether.
        """
        root = self.root.resolve()
        paths = []
        for name in self.session["open"]:
            path = self.root / name
            try:
                path.resolve().relative_to(root)
            except (ValueError, OSError):
                continue
            if path.is_file():
                paths.append(path)
        return paths

    def set_session(self, open_paths, active: int = 0) -> None:
        """Record what is open, for the next time this is entered.

        Stored **relative to the root and with forward slashes**, so a
        workspace that is moved, renamed or carried to another machine
        still answers -- the same reason :meth:`find` walks upwards
        rather than storing a root anywhere.  A path from outside the
        workspace is dropped rather than stored absolute, which is the
        falsehood this avoids everywhere else.

        A workspace on a disk that has filled or a folder that has gone
        read-only does not get to make closing a tab raise, so a write
        that fails is a session that is not remembered and nothing
        else.
        """
        root = self.root.resolve()
        relative = []
        for path in open_paths:
            try:
                relative.append(
                    Path(path).resolve().relative_to(root).as_posix())
            except (ValueError, OSError):
                continue
        marker = self.root / WORKSPACE_FILE
        data = self._marker_data()
        data.setdefault("format", "crystal-builder-workspace")
        data.setdefault("version", FORMAT_VERSION)
        data["session"] = {"open": relative,
                           "active": max(0, int(active))}
        try:
            marker.write_text(json.dumps(data, indent=1) + "\n",
                              encoding="utf-8")
        except OSError:
            pass

    # Two Workspace objects are the same workspace when they name the
    # same directory, whatever route each was reached by -- and on
    # macOS one of those routes goes through /var and the other
    # through /private/var, which is the same folder spelled two ways.

    def __eq__(self, other) -> bool:
        if not isinstance(other, Workspace):
            return NotImplemented
        return self.root.resolve() == other.root.resolve()

    def __hash__(self) -> int:
        return hash(self.root.resolve())

    def __repr__(self) -> str:              # pragma: no cover
        return f"<Workspace {self.root}>"


# ======================================================================
#  A RUN, AS IT IS BEING WRITTEN
# ======================================================================

class RunLog:
    """``run.log``, written as the run goes.

    Appended and flushed line by line rather than collected and written
    at the end, for the same reason the trajectory is: the log of a run
    that hung is the only evidence of *where* it hung, and a log
    written at the end of a run that never ended is empty.  It is also
    what lets a viewer tail the file while the run is live.
    """

    def __init__(self, path, append: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a" if append else "w",
                                      encoding="utf-8")

    def write(self, text: str = "") -> None:
        self._handle.write(text.rstrip("\n") + "\n")
        self._handle.flush()

    def blank(self) -> None:
        self.write("")

    def heading(self, text: str) -> None:
        self.write(text)
        self.write("-" * len(text))

    def table(self, rows, headers=()) -> None:
        """A fixed-width table, sized to what is in it.

        The typing table is the reason this exists: it is the part of a
        log somebody reads three months later to work out why a number
        was what it was, and a table whose columns do not line up is
        one nobody reads at all.
        """
        rows = [[str(v) for v in row] for row in rows]
        if headers:
            rows = [[str(h) for h in headers], *rows]
        if not rows:
            return
        widths = [max(len(r[i]) for r in rows)
                  for i in range(len(rows[0]))]
        for number, row in enumerate(rows):
            self.write("  ".join(
                value.ljust(width) for value, width
                in zip(row, widths, strict=True)).rstrip())
            if headers and number == 0:
                self.write("  ".join("-" * w for w in widths))

    def close(self) -> None:
        if self._handle is not None and not self._handle.closed:
            self._handle.close()

    @property
    def closed(self) -> bool:
        return self._handle is None or self._handle.closed

    def __enter__(self) -> RunLog:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


@dataclass
class RunFolder:
    """A run folder, open for writing.

    The one place that knows the names inside a run folder.  A module
    asks its entry for one of these, writes into it, and closes it; the
    tree finds the same files afterwards by looking, and the CLI
    produces a folder indistinguishable from the window's.
    """

    run: Run
    _log: RunLog | None = field(default=None, repr=False)
    _trajectory: object = field(default=None, repr=False)

    @property
    def path(self) -> Path:
        return self.run.path

    @property
    def name(self) -> str:
        return self.run.name

    def log(self) -> RunLog:
        """The run log, opened on first use."""
        if self._log is None:
            self._log = RunLog(self.run.log_path)
        return self._log

    def trajectory(self):
        """The trajectory writer, opened on first use.

        Opened lazily because a single point has no trajectory, and an
        empty ``trajectory.extxyz`` beside a run that never had one is
        a file that says something untrue.
        """
        if self._trajectory is None:
            from xtal.io.trajectory import TrajectoryWriter
            self._trajectory = TrajectoryWriter(
                self.run.trajectory_path)
        return self._trajectory

    def write_final(self, structure) -> Path:
        """The structure the run ended at."""
        from xtal.io import FORMATS
        FORMATS.write(structure, self.run.final_path)
        return self.run.final_path

    def close(self) -> None:
        if self._log is not None:
            self._log.close()
        if self._trajectory is not None:
            self._trajectory.close()

    def __enter__(self) -> RunFolder:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def timestamp() -> str:
    """A log-friendly UTC time, to the second."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def readable_option(value) -> str:
    """One option, as a log reads rather than as Python repr()s."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def write_header(log: RunLog, folder: RunFolder, structure=None,
                 title: str = "", fields=(), options=None) -> None:
    """The first block of a run log, whatever it was that ran.

    Shared between the force field and the module registry, because
    the questions somebody asks of a log three months later do not
    depend on which engine wrote it: what version, what structure,
    what was asked for, and with which options.  A second copy of this
    would be the one that stopped recording the option somebody needed.

    Nothing in here may raise.  A log that refuses to open because the
    formula could not be computed has lost the run it was recording.
    """
    from xtal import __version__

    log.write(f"Crystal Builder {__version__}")
    log.write(f"run            {folder.name}")
    if title:
        log.write(f"what           {title}")
    log.write(f"started        {timestamp()}")
    if structure is not None:
        from xtal.core import properties
        try:
            info = properties.info(structure)
            log.write(f"structure      {info.formula} "
                      f"(Z = {info.z}), {structure.n_sites} "
                      f"sites, {info.n_atoms} atoms in the cell")
            log.write(f"space group    {info.space_group} "
                      f"(#{info.space_group_number})")
        except Exception as exc:                    # noqa: BLE001
            log.write(f"structure      (could not summarise: {exc})")
        source = structure.meta.get("source")
        if source:
            log.write(f"source         {source}")
    for name, value in fields:
        log.write(f"{str(name):<15s}{value}")
    for key, value in sorted(dict(options or {}).items()):
        log.write(f"  {key:<12s} {readable_option(value)}")
