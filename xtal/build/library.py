"""
xtal.build.library
==================
The molecules worth not typing twice.

``CN(C)C=O`` is DMF and ``[*:1]c1ccc([*:2])cc1`` is the strut of half
the frameworks in the field, and neither is a thing anybody should be
retyping from memory.  So they are in a JSON file that ships with the
package, read through :mod:`importlib.resources` -- which finds it in
a wheel, in a zip and in a source checkout without any of them being a
special case, and is why this is not ``Path(__file__).parent``.

**Listing the library needs no RDKit.**  The whole of an entry is
text, so the picker fills whether or not the extra is installed, and
the extra is wanted only when something is actually built.  A library
that could not be *looked at* without a 400 MB dependency would be a
library people found out about after installing it.

**How many connection points an entry has is counted from the string,
not parsed out of it.**  ``*`` in SMILES is a dummy atom and is
nothing else -- it has no meaning as punctuation, inside brackets or
out -- so counting the character is exactly right and needs no
chemistry.  It is what lets the box that pastes into a cell offer the
solvents and hide the linkers without asking RDKit anything.

Adding a fragment is a line in ``data/fragments.json``.  Nothing here
knows the names, and nothing anywhere else has a list of them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

#: Where the file lives, as a package resource rather than a path.
PACKAGE = "xtal.build.data"
FILE = "fragments.json"


class LibraryError(ValueError):
    """The shipped library is missing or unreadable."""


@dataclass(frozen=True)
class Entry:
    """One named molecule: what it is called, and what it is."""

    name: str
    smiles: str
    category: str = ""
    description: str = ""

    @property
    def n_connections(self) -> int:
        """How many connection points the string carries.  See the
        module docstring for why counting the character is exact."""
        return self.smiles.count("*")

    @property
    def is_block(self) -> bool:
        """Whether this is a building block rather than a molecule --
        which is the question the two builder entries differ on."""
        return self.n_connections > 0

    def summary(self) -> str:
        """The line a picker shows beside the name."""
        marked = (f"{self.n_connections} connection point(s)"
                  if self.is_block else self.smiles)
        return f"{marked}  ·  {self.description}".rstrip(" ·")


@lru_cache(maxsize=1)
def entries() -> tuple[Entry, ...]:
    """Everything in the library, in the order the file lists it.

    Read once.  It is 26 entries and a few kilobytes, and a lazier
    arrangement would be more code than the file it is saving.
    """
    from importlib import resources

    try:
        text = (resources.files(PACKAGE) / FILE).read_text(
            encoding="utf-8")
        listed = json.loads(text)["fragments"]
    except (OSError, ValueError, KeyError,
            ModuleNotFoundError) as exc:
        raise LibraryError(
            f"the fragment library ({PACKAGE}/{FILE}) could not be "
            f"read: {exc}") from None
    return tuple(
        Entry(name=str(item.get("name", "")),
              smiles=str(item.get("smiles", "")),
              category=str(item.get("category", "")),
              description=str(item.get("description", "")))
        for item in listed if item.get("smiles"))


def categories() -> tuple[str, ...]:
    """The categories in use, in the order they first appear.

    File order rather than alphabetical: the file groups solvents
    before linkers because that is the order somebody looks for them
    in, and sorting would throw that away.
    """
    seen: list[str] = []
    for entry in entries():
        if entry.category and entry.category not in seen:
            seen.append(entry.category)
    return tuple(seen)


def find(name: str) -> Entry | None:
    """One entry by name, case-insensitively, or ``None``."""
    wanted = str(name or "").strip().lower()
    for entry in entries():
        if entry.name.lower() == wanted:
            return entry
    return None


def matching(connection_points: bool = True) -> tuple[Entry, ...]:
    """The entries a box will accept.

    ``connection_points=False`` is the box that pastes into the open
    cell, which refuses a starred string -- see
    :func:`xtal.build.from_smiles` -- so offering it the linkers would
    be offering it entries that answer with a refusal.
    """
    if connection_points:
        return entries()
    return tuple(e for e in entries() if not e.is_block)
