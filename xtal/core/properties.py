"""
xtal.core.properties
====================
The numbers that belong in the status bar and the structure-info
panel: cell contents, formula, Z, mass, density, charge balance.

Everything here counts the FULL cell, so it goes through the P1
expansion and respects site multiplicity and partial occupancy.  The
asymmetric unit's own composition (``Structure.composition``) is a
different, smaller question.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import gcd

import numpy as np

from xtal.core import elements as el
from xtal.core import p1

# amu / Angstrom^3 -> g / cm^3
AMU_PER_A3_TO_G_PER_CM3 = 1.66053906660


def cell_contents(structure) -> dict[str, float]:
    """Occupancy-weighted element counts for the whole unit cell."""
    cell = p1.expand(structure)
    counts: Counter[str] = Counter()
    for element, occ in zip(cell.elements, cell.occupancy, strict=True):
        counts[element] += float(occ)
    return dict(counts)


def cell_mass(structure) -> float:
    """Mass of the unit cell contents, in amu."""
    return sum(n * el.mass(sym)
               for sym, n in cell_contents(structure).items())


def density(structure) -> float:
    """Crystallographic density in g/cm^3."""
    volume = structure.lattice.volume
    if volume <= 0:
        return 0.0
    return cell_mass(structure) / volume * AMU_PER_A3_TO_G_PER_CM3


def formula(structure, reduce: bool = True) -> tuple[str, int]:
    """(formula string, Z).

    With ``reduce=True`` the cell contents are divided by the largest
    integer that leaves whole numbers -- so a cell holding Ti2O4 comes
    back as ("TiO2", 2).  Fractional occupancies defeat reduction, and
    then Z is 1 and the formula carries the decimals.
    """
    counts = cell_contents(structure)
    if not counts:
        return "", 0
    values = list(counts.values())
    integral = all(abs(v - round(v)) < 1e-6 for v in values)
    z = 1
    if reduce and integral:
        ints = [int(round(v)) for v in values]
        z = ints[0]
        for v in ints[1:]:
            z = gcd(z, v)
        z = max(z, 1)
        counts = {k: int(round(v)) // z for k, v in counts.items()}
    elif integral:
        counts = {k: int(round(v)) for k, v in counts.items()}
    return _format_formula(counts), z


def _format_formula(counts) -> str:
    """Order the elements the way the relevant community writes them.

    A compound containing both carbon and hydrogen is organic (or
    organometallic) and gets Hill order -- C, H, then the rest
    alphabetically -- which is what the CSD and every chemist expects:
    C6H6, C10H10Fe.  Everything else is inorganic and gets
    electronegativity order, electropositive element first: SiO2, TiO2,
    CaCO3, NaCl.  Alphabetical order would write those backwards.
    """
    if "C" in counts and "H" in counts:
        keys = (["C", "H"]
                + sorted(k for k in counts if k not in ("C", "H")))
    else:
        keys = sorted(counts,
                      key=lambda k: (el.electronegativity(k) or 0.0, k))
    parts = []
    for k in keys:
        n = counts[k]
        if abs(n - 1) < 1e-9:
            parts.append(k)
        elif abs(n - round(n)) < 1e-6:
            parts.append(f"{k}{int(round(n))}")
        else:
            parts.append(f"{k}{n:g}")
    return "".join(parts)


def charge_balance(structure) -> float | None:
    """Net charge of the cell, or None if no site carries a charge."""
    cell = p1.expand(structure)
    charges = [structure.sites[int(i)].charge for i in cell.site_idx]
    if all(c is None for c in charges):
        return None
    total = sum((c or 0.0) * float(occ)
                for c, occ in zip(charges, cell.occupancy, strict=True))
    return float(total)


@dataclass(frozen=True)
class StructureInfo:
    """One shot of everything the info panel shows."""

    formula: str
    z: int
    n_sites: int
    n_atoms: int
    volume: float
    mass: float
    density: float
    space_group: str
    space_group_number: int
    crystal_system: str
    parameters: tuple
    net_charge: float | None

    def text(self) -> str:
        a, b, c, al, be, ga = self.parameters
        charge = ("" if self.net_charge is None
                  else f"\nnet charge     {self.net_charge:+.3f}")
        return (
            f"formula        {self.formula}  (Z = {self.z})\n"
            f"space group    {self.space_group} "
            f"(#{self.space_group_number}, {self.crystal_system})\n"
            f"cell           a={a:.4f}  b={b:.4f}  c={c:.4f}\n"
            f"               alpha={al:.3f}  beta={be:.3f}  "
            f"gamma={ga:.3f}\n"
            f"volume         {self.volume:.3f} A^3\n"
            f"sites / atoms  {self.n_sites} / {self.n_atoms}\n"
            f"mass           {self.mass:.3f} amu\n"
            f"density        {self.density:.4f} g/cm^3" + charge
        )


def info(structure) -> StructureInfo:
    """Collect everything at once (one P1 expansion, not five)."""
    cell = p1.expand(structure)
    form, z = formula(structure)
    return StructureInfo(
        formula=form,
        z=z,
        n_sites=structure.n_sites,
        n_atoms=cell.n_atoms,
        volume=structure.lattice.volume,
        mass=cell_mass(structure),
        density=density(structure),
        space_group=structure.space_group.short_name,
        space_group_number=structure.space_group.number,
        crystal_system=structure.space_group.crystal_system,
        parameters=tuple(np.round(structure.lattice.parameters, 6)),
        net_charge=charge_balance(structure),
    )
