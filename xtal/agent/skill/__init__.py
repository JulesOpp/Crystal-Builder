"""
xtal.agent.skill
================
The skill an AI assistant reads before driving Crystal Builder, and
the two things to do with it: find it, and copy it where an assistant
looks.

It ships **inside the package** so the text always describes the API
installed beside it -- a skill that names a verb this version does not
have is worse than none, because the agent believes it.  A test holds
every name in ``SKILL.md`` and ``references/`` to the code.

Claude Code reads skills from ``~/.claude/skills/<name>/`` (every
project) and ``<project>/.claude/skills/<name>/`` (one project).
"""

from __future__ import annotations

import filecmp
import shutil
from importlib.resources import files
from pathlib import Path

NAME = "crystal-builder"


def source() -> Path:
    """The shipped skill's folder: ``SKILL.md`` and ``references/``."""
    return Path(str(files(__name__)))


def shipped_files() -> list[Path]:
    """Every file of the skill, relative to :func:`source`."""
    root = source()
    return sorted(p.relative_to(root) for p in root.rglob("*.md"))


def target(user: bool = True, project=None) -> Path:
    """Where :func:`install` would put the skill."""
    if project is not None:
        return Path(project).expanduser() / ".claude" / "skills" / NAME
    return Path.home() / ".claude" / "skills" / NAME


def install(user: bool = True, project=None,
            force: bool = False) -> Path:
    """Copy the skill into place, and say where.

    An installed copy that differs from this version's is refused
    unless ``force``: somebody may have edited it, and replacing a
    person's edits in silence is not what "install" means.  One that
    is already identical is left alone.
    """
    root = source()
    destination = target(user=user, project=project)
    differing = [
        name for name in shipped_files()
        if (destination / name).exists()
        and not filecmp.cmp(root / name, destination / name,
                            shallow=False)]
    if differing and not force:
        raise FileExistsError(
            f"{destination} holds a different copy of "
            f"{', '.join(str(n) for n in differing)}; pass --force "
            f"(force=True) to replace it with this version's")
    for name in shipped_files():
        (destination / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination / name)
    return destination
