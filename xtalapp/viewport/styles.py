"""
xtalapp.viewport.styles
=======================
Draw styles, as a registry.

A style is a small record, not a class hierarchy: it says where an
atom's radius comes from, how big it is, and whether bonds are drawn as
tubes, as lines, or not at all.  The scene builder reads those fields;
it never asks "which style is this?".  Polyhedra were the test of that:
adding VESTA's signature style was one more entry here plus the
geometry that fills the polyhedron arrays -- no existing style, and no
branch in the builder keyed on a style name.

The two report styles at the foot of this file are where that rule
cost something.  There is no per-atom mesh -- every atom in the
picture is one instanced glyph -- so an outline around each of them is
a second glyph and not a property, and it is the renderer and the SVG
exporter that grew, not this file: what arrives here is still a
number.  The fields they added (``shading``, ``outline``, ``tint``,
``bond_factor``, ``bond_color``) are all readable by any style, which
is the test of whether they were fields or a special case.
"""

from __future__ import annotations

from dataclasses import dataclass

from xtal.core import elements as el

#: The colour an outline is drawn in.  Not black: a pure black rim
#: against a white page reads as heavier than the ink of a printed
#: figure, and against a black background it disappears entirely --
#: this is dark enough to be ink and light enough to be seen.
INK = (34, 34, 40)


@dataclass(frozen=True)
class DrawStyle:
    """One way of drawing a structure."""

    name: str
    label: str                      # shown in the menu
    radius_source: str              # covalent | vdw | bond
    radius_factor: float
    draw_bonds: bool = True
    bond_render: str = "tube"       # tube | line
    #: The bond radius, as a multiple of the one in the settings.  A
    #: style that draws thin bonds says so here rather than moving the
    #: user's slider under them.
    bond_factor: float = 1.0
    #: One colour for every bond, replacing the rule that each half
    #: takes its own atom's.  ``None`` leaves the two-tone bonds
    #: alone, which is what all but the report styles want.
    bond_color: tuple | None = None
    draw_polyhedra: bool = False
    #: Which atoms get a hull when the user has not named any:
    #: "any" (whatever has enough neighbours) or "metals".
    polyhedra_centres: str = "any"
    #: Draw the atoms as thermal ellipsoids rather than spheres.  The
    #: bonds, the cell and everything else are unchanged, which is why
    #: this is a field and not a separate render path.
    ellipsoids: bool = False
    #: Draw a site that more than one thing shares as a sphere cut
    #: into wedges, one per occupant -- VESTA's picture of disorder.
    #: A field for the same reason ``ellipsoids`` is one: the bonds,
    #: the cell and everything else are unchanged.
    occupancy_pies: bool = False
    #: How the atoms and the bonds are lit: ``"lit"`` is a shaded
    #: surface with a highlight on it, ``"matte"`` the same shading
    #: with the highlight taken off -- a report figure is printed and
    #: a specular highlight prints as a white hole -- and ``"flat"``
    #: no lighting at all, one colour per atom edge to edge.
    shading: str = "lit"
    #: Ink around every atom and every bond, as a fraction of its own
    #: radius.  0 draws none, which is every style that came before
    #: these two.
    outline: float = 0.0
    outline_color: tuple = INK
    #: How far towards white each element's colour is taken before it
    #: is drawn.  The report styles want pale atoms carrying a dark
    #: outline; everything else wants the palette as it is.
    tint: float = 0.0
    description: str = ""

    def atom_radius(self, element: str, settings) -> float:
        base = settings.base_radius(element, self.radius_source)
        return base * self.radius_factor * settings.atom_scale

    def atom_color(self, element: str, settings) -> tuple:
        """The colour this style draws ``element`` in.

        The palette is the user's and the tint is the style's, in that
        order: an element recoloured in the preferences stays
        recognisable in a report figure, it is simply drawn paler.
        Asking the style rather than the settings is what keeps the
        builder from having to know which style is being drawn.
        """
        color = settings.color_for(element)
        if not self.tint:
            return tuple(int(c) for c in color)
        return tuple(int(round(c + (255 - c) * self.tint))
                     for c in color)

    def centres(self, elements, settings) -> frozenset:
        """Which elements get a coordination polyhedron, decided once
        for the whole structure rather than atom by atom.

        Centres named in the settings are the user speaking, and they
        win.  With none named the style decides, and the two styles
        want different things: the polyhedral picture takes anything
        with enough neighbours, which is right for a dense oxide, and
        the mixed one takes only the metals -- because in an MOF the
        linker has four-coordinate carbons too, and drawing those as
        tetrahedra is the picture this style exists to avoid.

        **A structure with no metals in it is the case that rule gets
        wrong**, and it takes the whole structure to see it: asked one
        element at a time, "is this a metal?" answers no for every atom
        of a topology net or an organic crystal, and *Polyhedra and
        sticks* draws no polyhedra at all.  A style whose name promises
        them and delivers none is broken rather than restrained, so
        when the metals rule selects nothing the style falls back to
        what *Polyhedra* would have done.  It never fires on a
        structure that has a metal in it, which is every case the rule
        was written for.
        """
        if settings.polyhedron_centres:
            return frozenset(settings.polyhedron_centres)
        present = frozenset(elements)
        if self.polyhedra_centres == "metals":
            metals = frozenset(symbol for symbol in present
                               if el.element(symbol).is_metal)
            if metals:
                return metals
        return present


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
    name="ball_stick_occupancy", label="Ball and stick (occupancy)",
    radius_source="covalent", radius_factor=0.5,
    occupancy_pies=True,
    description="Ball and stick, with every shared or partly empty "
                "site cut into wedges -- one per occupant, and a grey "
                "one for the vacancy",
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
    name="net", label="Net only",
    radius_source="bond", radius_factor=0.0, draw_bonds=False,
    description="The topology and nothing else -- no atoms and no "
                "chemical bonds, for looking at the net a framework "
                "reduces to",
))
register(DrawStyle(
    name="spacefill", label="Space filling",
    radius_source="vdw", radius_factor=1.0, draw_bonds=False,
    description="Atoms at their van der Waals radius",
))
register(DrawStyle(
    name="ortep", label="Thermal ellipsoids (ORTEP)",
    radius_source="covalent", radius_factor=0.25,
    ellipsoids=True,
    description="Atoms as displacement ellipsoids at the probability "
                "level set in the style panel -- the picture that "
                "makes a bad refinement obvious",
))
register(DrawStyle(
    name="polyhedra_stick", label="Polyhedra and sticks",
    radius_source="covalent", radius_factor=0.25,
    draw_bonds=True, draw_polyhedra=True, polyhedra_centres="metals",
    description="Coordination polyhedra for the nodes and tubes for "
                "everything else -- an MOF's metals and its linkers "
                "in the same picture",
))
register(DrawStyle(
    name="polyhedra", label="Polyhedra",
    radius_source="covalent", radius_factor=0.25,
    draw_bonds=False, draw_polyhedra=True,
    description="Coordination polyhedra as translucent hulls, "
                "coloured by the atom at the centre",
))
register(DrawStyle(
    name="platon", label="Ellipsoid plot (PLATON)",
    radius_source="covalent", radius_factor=0.25,
    ellipsoids=True, shading="matte", outline=0.11, tint=0.70,
    bond_factor=0.55, bond_color=INK,
    description="The ellipsoid plot a structure report is checked in: "
                "pale outlined atoms, thin dark bonds and no "
                "highlight -- what PLATON and checkCIF draw",
))
register(DrawStyle(
    name="cartoon", label="Cartoon",
    radius_source="covalent", radius_factor=0.5,
    shading="flat", outline=0.13,
    description="Flat colour inside a dark outline, and no shading at "
                "all -- the one style that exports as plain circles "
                "and strokes an illustrator can recolour",
))
