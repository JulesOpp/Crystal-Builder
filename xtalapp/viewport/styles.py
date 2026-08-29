"""
xtalapp.viewport.styles
=======================
Draw styles, as a registry.

A style is a small record, not a class hierarchy: it says where an
atom's radius comes from, how big it is, and whether bonds are drawn as
tubes, as lines, or not at all.  The scene builder reads those fields;
it never asks "which style is this?".  Adding polyhedra later is one
more entry plus the geometry that fills the polyhedron arrays.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DrawStyle:
    """One way of drawing a structure."""

    name: str
    label: str                      # shown in the menu
    radius_source: str              # covalent | vdw | bond
    radius_factor: float
    draw_bonds: bool = True
    bond_render: str = "tube"       # tube | line
    description: str = ""

    def atom_radius(self, element: str, settings) -> float:
        base = settings.base_radius(element, self.radius_source)
        return base * self.radius_factor * settings.atom_scale


STYLES: dict[str, DrawStyle] = {}


def register(style: DrawStyle) -> DrawStyle:
    STYLES[style.name] = style
    return style


def get(name: str) -> DrawStyle:
    try:
        return STYLES[name]
    except KeyError:
        raise ValueError(f"unknown draw style: {name!r}") from None


def names() -> list[str]:
    return list(STYLES)


register(DrawStyle(
    name="ball_stick", label="Ball and stick",
    radius_source="covalent", radius_factor=0.5,
    description="Atoms at half their covalent radius, tubes for bonds",
))
register(DrawStyle(
    name="stick", label="Stick",
    radius_source="bond", radius_factor=1.0,
    description="Bond-width tubes with matching spheres at the joints",
))
register(DrawStyle(
    name="wireframe", label="Wireframe",
    radius_source="bond", radius_factor=0.0, bond_render="line",
    description="Bonds as lines, no atom geometry",
))
register(DrawStyle(
    name="spacefill", label="Space filling",
    radius_source="vdw", radius_factor=1.0, draw_bonds=False,
    description="Atoms at their van der Waals radius",
))
