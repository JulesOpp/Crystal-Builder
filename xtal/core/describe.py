"""
xtal.core.describe
==================
What to say about one atom, in as few lines as it takes.

The viewport's tooltip is the caller this exists for, and the reason
the wording lives here rather than in the widget is the reason
everything else lives here: a sentence about an atom is made of the
cell, the site and the force field's reading of them, none of which
needs a display to be right.

**What goes in it is the decision.**  A tooltip that always says the
same four things is one people learn to ignore, so this says what the
current view is *about*: the label and element always, the force
field's type and its reasoning when the force field is on screen, and
U_eq when the picture is being drawn from the displacement parameters.
The caller passes what its view is showing -- it knows, and this
module has no way to ask -- and this decides nothing about that and
everything about the wording.
"""

from __future__ import annotations

from xtal.core import elements as el

#: Long enough to say why, short enough to read without moving the
#: mouse off the atom.  The typer's reasons run to a sentence and a
#: half for a coordination it had to argue itself into, and the
#: argument is worth having in the panel rather than under the cursor.
REASON_LIMIT = 90


def atom(structure, cell, index: int, atom_type=None,
         thermal: bool = False) -> str:
    """One atom, in the words the current view has earned.

    ``atom_type`` is the :class:`~xtal.ff.uff.typer.AtomType` for this
    atom when the force field is on screen and ``None`` when it is
    not; ``thermal`` says whether the picture is being drawn from the
    displacement parameters.  Neither is looked up here: this module
    knows no more about the window than the window knows about
    crystallography.

    Empty for an index the cell does not have, so a caller hovering
    over a structure that has changed under it says nothing rather
    than something wrong.
    """
    index = int(index)
    if index < 0 or index >= cell.n_atoms:
        return ""
    site = structure.sites[int(cell.site_idx[index])]
    lines = [_headline(site)]
    if atom_type is not None:
        lines.append(_typing(atom_type))
    if thermal:
        line = _thermal(site)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _headline(site) -> str:
    """The label, and what the label is made of.

    The element's full name and not its symbol: the symbol is already
    in the label of every structure that came from a CIF, and saying
    "O1  O" twice is one of the four things people learn to ignore.
    """
    element = el.element(site.element)
    name = site.label or site.element
    headline = f"{name}  {element.name.lower()}"
    if site.occupancy < 1.0:
        # A partially occupied site is the one fact about an atom that
        # changes what every number below it means, so it goes on the
        # first line rather than waiting for a panel.
        headline += f"  (occupancy {site.occupancy:g})"
    return headline


def _typing(atom_type) -> str:
    reason = atom_type.reason
    if len(reason) > REASON_LIMIT:
        reason = reason[:REASON_LIMIT].rsplit(" ", 1)[0] + "..."
    sure = "" if atom_type.is_sure else "  (uncertain)"
    return (f"UFF {atom_type.name}{sure}"
            + (f" -- {reason}" if reason else ""))


def _thermal(site) -> str:
    """``U_eq``, and whether anybody refined it anisotropically.

    Which of the two it is matters more than the number: an ORTEP
    drawn from a u_iso is a sphere by assumption rather than by
    measurement, and a picture of ellipsoids gives no sign of which
    atoms were only ever spheres.
    """
    u_eq = site.u_equivalent
    if u_eq is None:
        return "no displacement parameters"
    shape = ("anisotropic" if site.u_aniso is not None
             else "isotropic")
    return f"U_eq {u_eq:.4f} A^2  ({shape})"
