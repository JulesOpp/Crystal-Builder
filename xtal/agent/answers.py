"""
xtal.agent.answers
==================
What a verb hands back: typed, printable, and JSON with one call.

Plain dataclasses rather than a validation library, because the core
has four dependencies and an agent needs ``to_json()`` far more than
it needs a schema.  ``str()`` of any answer is what a person would
want to read in a terminal, and ends with the diagnostics, because
those outrank every number above them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from xtal.agent.diagnostics import ERROR, Diagnostic, to_json

#: Site rows ``str()`` prints before saying how many it left out.  A
#: structure reduced to P1 has hundreds, and the rows that matter are
#: named by the diagnostics below them anyway.
MAX_ROWS = 40


def _worst(diagnostics) -> str:
    levels = {d.level for d in diagnostics}
    for level in (ERROR, "warning", "info"):
        if level in levels:
            return level
    return ""


@dataclass
class VerbResult:
    """One verb: whether it changed anything, and what to know about it.

    ``ok`` is False when nothing was changed because the verb was
    refused -- never because of a warning.  A warning rides on a change
    that was made and is still on the undo stack; an agent that reads
    ``ok`` alone and stops there has missed half of it, which is why
    ``str()`` puts the diagnostics last and in full.
    """

    verb: str
    ok: bool
    message: str
    undo_label: str = ""
    atoms_before: int = 0
    atoms_after: int = 0
    data: dict = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def worst(self) -> str:
        return _worst(self.diagnostics)

    def to_dict(self) -> dict:
        return {
            "verb": self.verb, "ok": self.ok, "message": self.message,
            "undo_label": self.undo_label,
            "atoms_before": self.atoms_before,
            "atoms_after": self.atoms_after,
            "data": self.data,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }

    def to_json(self) -> str:
        return to_json(self.to_dict())

    def __str__(self) -> str:
        head = "ok" if self.ok else "REFUSED"
        lines = [f"{self.verb}: {head} -- {self.message}"]
        if self.atoms_before != self.atoms_after:
            lines.append(f"  atoms {self.atoms_before} -> "
                         f"{self.atoms_after}")
        for key, value in self.data.items():
            if not isinstance(value, (list, dict)):
                lines.append(f"  {key}: {value}")
        lines.extend(f"  {d}" for d in self.diagnostics)
        return "\n".join(lines)


@dataclass
class Inspection:
    """Everything worth knowing about a structure before believing it.

    Numbers first -- composition, cell, symmetry, coordination -- and
    the diagnostics after, each with its remedy.  The per-site rows
    are the asymmetric unit, which is what the edit verbs take; the
    atoms of the P1 cell each name the site they come from.
    """

    formula: str
    z: int
    n_sites: int
    n_atoms: int
    cell: dict
    volume: float
    density: float
    space_group: str
    space_group_number: int
    detected_space_group: str
    symprec: float
    net_charge: float | None
    n_bonds: int
    fragments: list[dict]
    sites: list[dict]
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def worst(self) -> str:
        return _worst(self.diagnostics)

    def to_dict(self) -> dict:
        return {
            "formula": self.formula, "z": self.z,
            "n_sites": self.n_sites, "n_atoms": self.n_atoms,
            "cell": self.cell, "volume": self.volume,
            "density": self.density,
            "space_group": self.space_group,
            "space_group_number": self.space_group_number,
            "detected_space_group": self.detected_space_group,
            "symprec": self.symprec,
            "net_charge": self.net_charge, "n_bonds": self.n_bonds,
            "fragments": self.fragments, "sites": self.sites,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }

    def to_json(self) -> str:
        return to_json(self.to_dict())

    def __str__(self) -> str:
        c = self.cell
        detected = ("" if self.detected_space_group == self.space_group
                    else f"  (detected at {self.symprec:g} A: "
                         f"{self.detected_space_group})")
        lines = [
            f"formula      {self.formula}  (Z = {self.z})",
            f"space group  {self.space_group} "
            f"(#{self.space_group_number}){detected}",
            f"cell         a={c['a']:.4f} b={c['b']:.4f} c={c['c']:.4f}"
            f"  alpha={c['alpha']:.3f} beta={c['beta']:.3f} "
            f"gamma={c['gamma']:.3f}",
            f"volume       {self.volume:.2f} A^3, density "
            f"{self.density:.4f} g/cm^3",
            f"sites/atoms  {self.n_sites} / {self.n_atoms}, "
            f"{self.n_bonds} bonds",
        ]
        if self.net_charge is not None:
            lines.append(f"net charge   {self.net_charge:+.3f}")
        kinds = {}
        for f in self.fragments:
            key = (f["kind"], f["formula"])
            kinds[key] = kinds.get(key, 0) + 1
        for (kind, formula), n in sorted(kinds.items()):
            lines.append(f"fragment     {n} x {kind} {formula}")
        lines.append("")
        lines.append("site   label    el   mult  occ    CN  neighbours")
        for s in self.sites[:MAX_ROWS]:
            around = ", ".join(f"{e} {d:.2f}"
                               for e, d in s["neighbours"][:8])
            more = " ..." if len(s["neighbours"]) > 8 else ""
            lines.append(
                f"{s['index']:<6d} {s['label']:<8s} {s['element']:<4s} "
                f"{s['multiplicity']:<5d} {s['occupancy']:<6.3g} "
                f"{s['coordination']:<3d} {around}{more}")
        if len(self.sites) > MAX_ROWS:
            lines.append(f"... {len(self.sites) - MAX_ROWS} more sites "
                         f"(to_dict() has every one)")
        if self.diagnostics:
            lines.append("")
            lines.extend(str(d) for d in self.diagnostics)
        return "\n".join(lines)
