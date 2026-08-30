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

Four decisions hold the rest of it up.

**The user picks it, and the application never guesses.**  A scratch
folder cleaned on exit will one day throw away a six-hour run, and a
folder chosen under ``~/Library/Application Support`` is one nobody can
find in Finder.  So a workspace is an ordinary directory the user chose
and can open, copy, back up and delete like any other.

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

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE_FILE = "workspace.json"
FORMAT_VERSION = 1

LOG_NAME = "run.log"
TRAJECTORY_NAME = "trajectory.extxyz"
FINAL_NAME = "final.cif"

# Characters that are awkward in a path on one of the two platforms
# this ships on, plus the ones a shell would need quoted.  A structure
# called "Fe(bpy)3 2+" has to become a folder name without becoming
# unrecognisable.
_UNSAFE = re.compile(r'[^A-Za-z0-9._+-]+')
_RUN_DIR = re.compile(r"^(?P<module>[a-z0-9]+)-(?P<kind>[a-z0-9-]+?)"
                      r"-(?P<index>\d+)$")


def safe_name(text: str, fallback: str = "structure") -> str:
    """A file name that keeps its meaning on macOS and on Windows."""
    cleaned = _UNSAFE.sub("_", str(text)).strip("._")
    return cleaned or fallback


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
                            # "final" | "project" | "file"
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
    if suffix in (".extxyz", ".traj"):
        return "trajectory"
    if suffix == ".xtalproj":
        return "project"
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
        module = safe_name(module, "module").lower()
        kind = safe_name(kind, "run").lower()
        index = max((r.index for r in self.runs()), default=0) + 1
        path = self.path / f"{module}-{kind}-{index:03d}"
        path.mkdir(parents=True, exist_ok=False)
        return RunFolder(Run(path, module, kind, index))


# ======================================================================
#  THE WORKSPACE
# ======================================================================

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
                 "version": FORMAT_VERSION}, indent=1) + "\n")
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

    @property
    def version(self) -> int:
        try:
            data = json.loads(
                (self.root / WORKSPACE_FILE).read_text())
        except (OSError, json.JSONDecodeError):
            return 0
        return int(data.get("version", 0))

    # -- entries -------------------------------------------------------

    def entries(self) -> list[Entry]:
        """Every structure folder, in name order.

        Read from the directory every time.  A workspace is a few dozen
        folders and the filesystem is the authority on what is in it --
        an index would be a second answer to the same question and the
        one that goes stale when a user moves a folder in Finder.
        """
        if not self.root.is_dir():
            return []
        return [Entry(path=p, workspace=self)
                for p in sorted(self.root.iterdir())
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

    def add_structure(self, source, name: str | None = None) -> Entry:
        """Copy a structure file in, and give it a folder of its own.

        **Copied, not referenced.**  A workspace that points at a file
        the user then edits, renames or deletes is a tree full of
        broken nodes; the copy costs kilobytes and the original path is
        recorded by the caller in ``structure.meta["source"]``.

        Opening the same file twice gets the same entry rather than a
        second one, because that is what "open MFU4l.cif again" means.
        """
        source = Path(source)
        entry = Entry(path=self.root / safe_name(
            name or source.stem, "structure"), workspace=self)
        entry.path.mkdir(parents=True, exist_ok=True)
        target = entry.path / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return entry

    def add_document(self, name: str) -> Entry:
        """An entry for a structure that has no file yet.

        A structure built from nothing still has runs to put somewhere.
        """
        entry = Entry(path=self.root / safe_name(name, "structure"),
                      workspace=self)
        entry.path.mkdir(parents=True, exist_ok=True)
        return entry

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
