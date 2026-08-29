"""
xtal.core.site
==============
One site of the asymmetric unit.

A Site is deliberately mutable and deliberately dumb: it holds data,
validates it, and knows nothing about the structure it belongs to.
Every edit that reaches a Site in the running application arrives
through a Command, which is what makes the edit undoable.

``props`` is the per-site extension point.  Anything a later module
needs to hang off an atom -- ``uff_type``, a refinement flag, a
computed charge, a Zeo++ label -- goes in there rather than growing a
new field on this class.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.core import elements


@dataclass
class Site:
    """An atom (or partially-occupied atom) in the asymmetric unit."""

    element: str
    frac: np.ndarray                      # (3,) fractional coordinates
    occupancy: float = 1.0
    label: str = ""                       # CIF _atom_site_label
    u_iso: float | None = None            # Angstrom^2
    charge: float | None = None
    wyckoff: str | None = None            # filled by symmetry detection
    props: dict = field(default_factory=dict)

    def __post_init__(self):
        self.element = elements.parse_symbol(self.element)
        self.frac = np.asarray(self.frac, dtype=float).reshape(3).copy()
        if not np.all(np.isfinite(self.frac)):
            raise ValueError(
                f"non-finite coordinates for site {self.label or '?'}"
            )
        occ = float(self.occupancy)
        if not 0.0 < occ:
            raise ValueError(f"occupancy must be > 0, got {occ}")
        self.occupancy = occ

    # -- derived -------------------------------------------------------

    @property
    def z(self) -> int:
        return elements.atomic_number(self.element)

    @property
    def mass(self) -> float:
        return elements.mass(self.element)

    def cart(self, lattice) -> np.ndarray:
        """Cartesian position in the given lattice."""
        return lattice.to_cart(self.frac)

    def wrapped(self) -> np.ndarray:
        """This site's coordinates folded into [0, 1)."""
        return np.mod(self.frac, 1.0)

    @property
    def is_partial(self) -> bool:
        return self.occupancy < 1.0 - 1e-6

    # -- copying / serialisation ---------------------------------------

    def copy(self) -> Site:
        return Site(
            element=self.element,
            frac=self.frac.copy(),
            occupancy=self.occupancy,
            label=self.label,
            u_iso=self.u_iso,
            charge=self.charge,
            wyckoff=self.wyckoff,
            props=dict(self.props),
        )

    def to_dict(self) -> dict:
        d = {
            "element": self.element,
            "frac": self.frac.tolist(),
            "occupancy": self.occupancy,
            "label": self.label,
        }
        for key in ("u_iso", "charge", "wyckoff"):
            if getattr(self, key) is not None:
                d[key] = getattr(self, key)
        if self.props:
            d["props"] = dict(self.props)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Site:
        return cls(
            element=d["element"],
            frac=np.array(d["frac"], dtype=float),
            occupancy=d.get("occupancy", 1.0),
            label=d.get("label", ""),
            u_iso=d.get("u_iso"),
            charge=d.get("charge"),
            wyckoff=d.get("wyckoff"),
            props=dict(d.get("props", {})),
        )

    # -- comparison ----------------------------------------------------

    def almost_equal(self, other: Site, tol: float = 1e-8) -> bool:
        return (
            isinstance(other, Site)
            and self.element == other.element
            and np.allclose(self.frac, other.frac, atol=tol)
            and abs(self.occupancy - other.occupancy) <= tol
            and self.label == other.label
            and self.u_iso == other.u_iso
            and self.charge == other.charge
            and self.props == other.props
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, Site):
            return NotImplemented
        return self.almost_equal(other)

    def __repr__(self) -> str:
        x, y, z = self.frac
        occ = "" if self.occupancy == 1.0 else f", occ={self.occupancy:g}"
        lab = f" {self.label!r}" if self.label else ""
        return (f"Site({self.element}{lab}, "
                f"[{x:.5f}, {y:.5f}, {z:.5f}]{occ})")
