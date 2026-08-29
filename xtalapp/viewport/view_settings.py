"""
xtalapp.viewport.view_settings
==============================
How a structure is drawn -- and nothing about what it *is*.

ViewSettings is deliberately separate from Structure: changing a colour
or the display range must never touch the crystal, never mark the
document modified in the structural sense, and never land on the undo
stack as a chemistry edit.  It is also Qt-free and VTK-free, so the
scene builder that consumes it stays unit-testable without a display.

The display range is in fractional units and inclusive at both ends,
which is what makes a picture look right: a range of (0, 1) draws the
atom at x = 0 *and* its copy at x = 1, the way VESTA does.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from xtal.core import elements as el

# Styles are looked up in xtalapp.viewport.styles; the name is stored
# here so settings stay a plain, serialisable record.
DEFAULT_STYLE = "ball_stick"

BACKGROUNDS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "slate": (32, 36, 46),
    "paper": (246, 245, 240),
}


@dataclass
class ViewSettings:
    """Everything the scene builder needs that is not the structure."""

    style: str = DEFAULT_STYLE
    atom_scale: float = 1.0
    bond_radius: float = 0.15               # Angstrom
    show_atoms: bool = True
    show_bonds: bool = True
    show_cell: bool = True
    show_axes: bool = True
    label_mode: str = "none"                # none | element | label | index

    # Display range in fractional coordinates, inclusive.
    range_a: tuple[float, float] = (0.0, 1.0)
    range_b: tuple[float, float] = (0.0, 1.0)
    range_c: tuple[float, float] = (0.0, 1.0)
    # in_range: draw only atoms inside the range
    # bonded:   also draw the atoms just outside that complete a bond
    boundary: str = "in_range"

    background: tuple[int, int, int] = BACKGROUNDS["white"]
    projection: str = "perspective"         # perspective | orthographic

    element_colors: dict = field(default_factory=dict)
    element_radii: dict = field(default_factory=dict)

    # -- element appearance -------------------------------------------

    def color_for(self, element: str) -> tuple[int, int, int]:
        """User override if there is one, else the element's palette
        colour."""
        if element in self.element_colors:
            return tuple(self.element_colors[element])
        return el.color(element)

    def base_radius(self, element: str, source: str) -> float:
        """Radius before the style's factor and the global scale."""
        if element in self.element_radii:
            return float(self.element_radii[element])
        if source == "vdw":
            return el.vdw_radius(element)
        if source == "covalent":
            return el.covalent_radius(element)
        return self.bond_radius

    # -- display range -------------------------------------------------

    @property
    def ranges(self) -> tuple[tuple[float, float], ...]:
        return (self.range_a, self.range_b, self.range_c)

    def set_cells(self, na: int, nb: int, nc: int) -> None:
        """Show na x nb x nc whole cells starting at the origin."""
        for n in (na, nb, nc):
            if int(n) < 1:
                raise ValueError("cell counts must be >= 1")
        self.range_a = (0.0, float(na))
        self.range_b = (0.0, float(nb))
        self.range_c = (0.0, float(nc))

    @property
    def cells(self) -> tuple[int, int, int]:
        """The whole-cell counts, when the range is a whole number of
        cells starting at the origin."""
        out = []
        for lo, hi in self.ranges:
            out.append(max(1, int(round(hi - lo))))
        return tuple(out)

    # -- housekeeping --------------------------------------------------

    def copy(self) -> ViewSettings:
        return replace(self,
                       element_colors=dict(self.element_colors),
                       element_radii=dict(self.element_radii))

    def to_dict(self) -> dict:
        return {
            "style": self.style,
            "atom_scale": self.atom_scale,
            "bond_radius": self.bond_radius,
            "show_atoms": self.show_atoms,
            "show_bonds": self.show_bonds,
            "show_cell": self.show_cell,
            "show_axes": self.show_axes,
            "label_mode": self.label_mode,
            "range_a": list(self.range_a),
            "range_b": list(self.range_b),
            "range_c": list(self.range_c),
            "boundary": self.boundary,
            "background": list(self.background),
            "projection": self.projection,
            "element_colors": {k: list(v)
                               for k, v in self.element_colors.items()},
            "element_radii": dict(self.element_radii),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ViewSettings:
        s = cls()
        for key in ("style", "atom_scale", "bond_radius", "show_atoms",
                    "show_bonds", "show_cell", "show_axes",
                    "label_mode", "boundary", "projection"):
            if key in d:
                setattr(s, key, d[key])
        for key in ("range_a", "range_b", "range_c"):
            if key in d:
                setattr(s, key, tuple(d[key]))
        if "background" in d:
            s.background = tuple(d["background"])
        s.element_colors = {k: tuple(v) for k, v in
                            d.get("element_colors", {}).items()}
        s.element_radii = dict(d.get("element_radii", {}))
        return s
