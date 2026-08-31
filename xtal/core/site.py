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
    #: The six anisotropic displacement parameters of the CIF
    #: ``_atom_site_aniso_*`` loop, in Voigt order
    #: ``(U11, U22, U33, U12, U13, U23)`` and in Angstrom^2.  ``None``
    #: means the refinement gave none, which is not the same as zero
    #: and must not be drawn as if it were -- see
    #: :meth:`u_cartesian`.
    u_aniso: tuple | None = None
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
        if self.u_aniso is not None:
            values = tuple(float(v) for v in self.u_aniso)
            if len(values) != 6:
                raise ValueError(
                    "u_aniso needs six values (U11, U22, U33, U12, "
                    f"U13, U23), got {len(values)}")
            self.u_aniso = values

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

    def u_cartesian(self, lattice) -> np.ndarray | None:
        """The 3x3 displacement tensor in cartesian axes, or None.

        The CIF's U^ij are *not* a cartesian tensor: they are defined
        against the reciprocal basis, and drawing them directly gives
        an ellipsoid that is right only in an orthorhombic cell and
        visibly sheared in anything else.  The conversion is

            U_cart = N U N^T,   N = A diag(a*, b*, c*)

        with ``A`` the matrix whose columns are the cartesian
        components of the lattice vectors -- which is
        ``lattice.matrix`` transposed, since this code stores the
        vectors as rows.  In an orthogonal cell N is the identity and
        the two agree, which is why the mistake survives casual
        testing.
        """
        if self.u_aniso is None:
            return None
        u11, u22, u33, u12, u13, u23 = self.u_aniso
        u = np.array([[u11, u12, u13],
                      [u12, u22, u23],
                      [u13, u23, u33]], dtype=float)
        stars = np.diag(lattice.reciprocal().parameters[:3])
        n = np.asarray(lattice.matrix, dtype=float).T @ stars
        return n @ u @ n.T

    @property
    def u_equivalent(self) -> float | None:
        """``U_eq``: a third of the trace, which is the isotropic
        number a refinement would have reported instead.

        Taken from ``u_aniso`` when there is one and from ``u_iso``
        otherwise, so anything that wants one number per atom has one.
        """
        if self.u_aniso is not None:
            return float(sum(self.u_aniso[:3]) / 3.0)
        return self.u_iso

    # -- copying / serialisation ---------------------------------------

    def copy(self) -> Site:
        return Site(
            element=self.element,
            frac=self.frac.copy(),
            occupancy=self.occupancy,
            label=self.label,
            u_iso=self.u_iso,
            u_aniso=self.u_aniso,
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
        if self.u_aniso is not None:
            d["u_aniso"] = list(self.u_aniso)
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
            u_aniso=(tuple(d["u_aniso"]) if d.get("u_aniso") is not None
                     else None),
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
            and self.u_aniso == other.u_aniso
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
