"""
xtal.powder.cell
================
Which of a cell's six numbers a space group leaves free.

A cubic cell is one length; a monoclinic one is three lengths and the
angle about its unique axis.  A refinement form that offered six boxes
for every group would take ``a = 4.59, b = 4.60`` for a tetragonal
cell and hand RietX a lattice its own ties then overwrite -- the fit
would run on a cell the person never typed.  So the form offers the
free numbers and derives the rest, and a refinement frees or holds the
free ones one by one, as TOPAS's ``a @ 4.59`` against ``a 4.59`` does.

RietX ties the same numbers itself (``b`` follows ``a`` on a cubic
cell); this module says so without importing it, because the form has
to know before any fit has been asked for.
"""

from __future__ import annotations

__all__ = ["NAMES", "constraints", "complete", "free_names", "system_of"]

#: The six numbers, in the order a cell is written.
NAMES = ("a", "b", "c", "alpha", "beta", "gamma")

_ALL_FREE = (None,) * 6


def _group(space_group):
    import gemmi

    text = str(space_group or "").strip()
    if not text:
        return None
    return gemmi.find_spacegroup_by_name(text)


def system_of(space_group) -> str:
    """The crystal system, or ``""`` for a group nobody knows."""
    group = _group(space_group)
    return group.crystal_system_str() if group is not None else ""


def constraints(space_group) -> tuple:
    """What each of a, b, c, alpha, beta, gamma is in this group.

    ``None`` is free; a name is *equal to* that number; a float is
    fixed at that value.  A group that cannot be named leaves all six
    free, which is triclinic's answer and never refuses a cell.
    """
    group = _group(space_group)
    if group is None:
        return _ALL_FREE
    system = group.crystal_system_str()
    if system == "triclinic":
        return _ALL_FREE
    if system == "monoclinic":
        # gemmi's qualifier starts with the unique axis: "b1", "c".
        axis = (group.qualifier or "b")[0]
        angle = {"a": 3, "b": 4, "c": 5}.get(axis, 4)
        out = [None, None, None, 90.0, 90.0, 90.0]
        out[angle] = None
        return tuple(out)
    if system == "orthorhombic":
        return (None, None, None, 90.0, 90.0, 90.0)
    if system == "tetragonal":
        return (None, "a", None, 90.0, 90.0, 90.0)
    if system == "trigonal" and group.ext == "R":
        # rhombohedral axes: one length and one angle
        return (None, "a", "a", None, "alpha", "alpha")
    if system in ("trigonal", "hexagonal"):
        return (None, "a", None, 90.0, 90.0, 120.0)
    if system == "cubic":
        return (None, "a", "a", 90.0, 90.0, 90.0)
    return _ALL_FREE


def free_names(space_group) -> tuple[str, ...]:
    """The numbers a person sets, and a refinement frees or holds."""
    return tuple(name for name, rule in zip(NAMES, constraints(space_group),
                                            strict=True) if rule is None)


def complete(values, space_group) -> tuple[float, ...]:
    """All six numbers from ``values`` (a mapping, or six numbers), the
    group's ties and fixed angles applied over whatever was given."""
    if not isinstance(values, dict):
        values = dict(zip(NAMES, (float(v) for v in values), strict=True))
    out = {}
    for name, rule in zip(NAMES, constraints(space_group), strict=True):
        if rule is None:
            out[name] = float(values[name])
        elif isinstance(rule, str):
            out[name] = out[rule]
        else:
            out[name] = float(rule)
    return tuple(out[name] for name in NAMES)
