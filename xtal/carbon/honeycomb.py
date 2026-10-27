"""
xtal.carbon.honeycomb
=====================
What every builder of an sp2 sheet reads a recipe with: an element
spelled properly or refused by name, a bond typed into the form or
left to the elements, the X-H length a cap is put at, and the record
:func:`xtal.carbon.lattice.structure_of` turns into a structure.

Lifted out of :mod:`xtal.nanotube.build` so that the fullerene and
graphene builders read their forms the same way the nanotube's does.
Each refusal is raised as the caller's own error class, because each
module catches its own builder's error and reports it as a failed run.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.core import elements

__all__ = ["BOND_RANGE", "Atoms", "element_symbol", "given_bond",
           "hydrogen_length"]

#: The bond lengths a recipe may give, A: the form's old spinbox
#: range, kept now the box is text and nothing else holds it.
BOND_RANGE = (0.8, 3.0)


def element_symbol(text, error=ValueError) -> str:
    """``text`` as an element's symbol, or ``error`` naming it.  A
    dummy is no element here: nothing is built out of markers."""
    symbol = elements.canonical_symbol(str(text))
    if symbol is None or elements.is_dummy(symbol):
        raise error(f"{str(text).strip()!r} is not an element")
    return symbol


def given_bond(value, error=ValueError) -> float | None:
    """A bond given as a number or the form's text, in A; None when
    none was given."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            bond = float(text)
        except ValueError:
            raise error(f"the bond length must be a number, "
                        f"not {text!r}") from None
    else:
        bond, text = float(value), f"{float(value):g}"
    low, high = BOND_RANGE
    if not low <= bond <= high:
        raise error(f"the bond length must be {low} to {high} "
                    f"A, not {text}")
    return bond


def hydrogen_length(symbol: str) -> float:
    """UFF's natural X-H single bond for an sp2 ``symbol`` -- what
    Add Hydrogens would put the hydrogen at.  An element with no
    resonant or sp2 type takes its first UFF type, and one with no UFF
    type at all the sum of the two covalent radii."""
    from xtal.ff.uff import params, terms

    types = params.types_for(symbol)
    for name in (f"{symbol}_R", f"{symbol}_2"):
        if name in types:
            return terms.natural_bond_length(name, "H_", 1.0)
    if types:
        return terms.natural_bond_length(types[0], "H_", 1.0)
    return elements.covalent_radius(symbol) \
        + elements.covalent_radius("H")


@dataclass
class Atoms:
    """What :func:`xtal.carbon.lattice.structure_of` reads."""

    matrix: np.ndarray
    elements: list
    frac: np.ndarray
    bonds: np.ndarray
    images: np.ndarray
