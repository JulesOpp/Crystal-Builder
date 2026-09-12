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

#: What becomes of a bond whose far atom is outside the display
#: range, in the order the menu offers them.
#:
#: ``in_range`` drops it, which under-coordinates every atom on the
#: surface of the picture.  ``bonded`` draws the far atom as well,
#: which keeps a coordination polyhedron whole at the cell edge and
#: hangs a halo of extra spheres round a picture that was meant to be
#: of one cell.  ``half`` draws the near half of the bond and no
#: sphere at all on the end of it -- the notation every
#: crystallography program has used for a surface bond, and the only
#: one that says "there is more here" without drawing what is not.
#:
#: ``half`` is the default.  The other two are each wrong about
#: something and only one of them can be turned off at a time:
#: ``in_range`` draws every atom on the surface of the picture
#: under-coordinated, and ``bonded`` draws a box surrounded by atoms
#: that are not in it.  A half bond is what a crystallographer draws
#: and is the answer that misleads nobody, so it is what the
#: application opens with.
#:
#: A session written before ``half`` existed holds one of the first
#: two, so the reader needs no migration -- it keeps what it is told
#: and only falls back for a value from a *newer* version.
BOUNDARIES = ("in_range", "bonded", "half")

#: The net is drawn over the chemistry rather than in place of it, so
#: it opens in one flat colour that is nobody's element, and the user
#: can move it from there.
TOPOLOGY_COLOR = (124, 96, 200)

#: A plane is not chemistry either, and takes a flat colour for the
#: same reason.
PLANE_COLOR = (232, 168, 60)

#: The pore network is neither.  A cool blue, chosen to be nobody's
#: element and to read as *empty space* beside the warm oranges and
#: greys a framework is usually drawn in -- what is being shown is the
#: hole, not a new atom.
PORE_COLOR = (64, 156, 220)

#: The skeleton, a shade darker than the sphere so the two are
#: distinguishable where a channel runs into the cavity it feeds.
PORE_EDGE_COLOR = (40, 112, 168)

#: How far towards black a plane's normal is taken from the plane's
#: own colour.  Derived rather than settable: two controls for one
#: object is two chances to make it unreadable.
NORMAL_DARKEN = 0.62


def normal_of(color) -> tuple[int, int, int]:
    """A plane's normal, taken from the plane's own colour.

    A function and not just a property, because a plane may carry a
    colour of its own and its normal has to follow *that* one -- two
    planes in two colours with their normals both in a third is the
    picture this is drawn to avoid.
    """
    return tuple(int(round(c * NORMAL_DARKEN)) for c in color)

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
    # Draw a double bond as two tubes and a triple as three.  On by
    # default: a framework whose bonds are all single loses nothing by
    # it, and a structure that is not is unreadable without it.  An MOF
    # with three hundred aromatic carbons is the case for turning it
    # off.
    show_bond_orders: bool = True
    # The net a chemist drew over the framework.  On when there is one
    # to draw, because a topology bond is invisible to everything else
    # and hiding it as well would leave no sign it existed.
    show_topology: bool = True
    # What colour the net is drawn in.  A setting and not a constant
    # because the one flat colour that is nobody's element on a white
    # background is somebody's element on a black one, and a net drawn
    # over a purple framework is the picture this exists to avoid.
    topology_color: tuple[int, int, int] = TOPOLOGY_COLOR
    # Fade distant atoms towards the background, so a thick slab reads
    # as having depth instead of as a flat mat of spheres.  Off by
    # default: it is an effect you reach for when the picture is deep,
    # and a documentation image or a render test that quietly acquired
    # it would be showing something nobody asked for.
    depth_cue: bool = False
    #: How far into the background an atom behind the end of the fade
    #: goes: 0 is not at all, 1 is all the way.
    depth_cue_strength: float = 0.7
    #: Where the fade begins and where it is complete, as fractions of
    #: the depth of the *atoms* -- 0 is the nearest atom's front and 1
    #: the farthest one's back.  Two ends and not an exponent, which is
    #: what this was: "fade from 30% to 100%" is a sentence, and
    #: "gradient 2.3" was a number nobody could predict the picture of.
    depth_cue_start: float = 0.3
    depth_cue_end: float = 1.0

    # The probability an ORTEP ellipsoid encloses.  A view setting and
    # not structure data: the same refinement drawn at 50% and at 90%
    # is the same crystal, and every published picture states which it
    # is.
    ellipsoid_probability: float = 0.50
    #: ORTEP's octant shading: the three principal sections drawn as
    #: arcs, and one pair of opposite octants filled.  On, because it
    #: is what makes an ellipsoid read as an ellipsoid rather than as
    #: a squashed ball -- a sphere and a 3:1 ellipsoid seen down its
    #: long axis are the same silhouette, and only the arcs tell them
    #: apart.  Off is for a picture that wants the shape and not the
    #: refinement.
    ellipsoid_octants: bool = True
    label_mode: str = "none"                # none | element | label | index

    # A translucent quad at every plane the user has defined, with its
    # normal on it.  On, because a plane is defined by pressing a
    # button and then has nothing on screen to show for it -- the
    # entry in the list is the only sign it exists.
    show_planes: bool = True
    #: What colour a quad is when its plane does not name one -- a
    #: plane carries its own, because two planes want two colours.
    #: The normal is drawn in a darkened version of whichever applies
    #: rather than in a colour of its own: a normal is the plane's
    #: arrow and reading as a separate object is what it must not do.
    plane_color: tuple[int, int, int] = PLANE_COLOR
    # The pore network a porosity run came back with.  On, because the
    # run that produced it was asked for and the whole reason it draws
    # anything is that a table cannot say *where*.  Nothing is drawn
    # until a run has answered, so a structure nobody has measured is
    # unaffected by the default.
    show_pores: bool = True
    #: One sphere, at the widest node, or one at every node.  Off: a
    #: framework's accessible network is hundreds of nodes in a cell
    #: and thousands across a display range, and a translucent ball at
    #: each is a fog over the crystal it is about.
    pore_all_nodes: bool = False
    pore_color: tuple[int, int, int] = PORE_COLOR
    pore_edge_color: tuple[int, int, int] = PORE_EDGE_COLOR
    #: Fainter than a polyhedron and for the same reason a plane is:
    #: the framework has to stay readable *through* the cavity, which
    #: is the whole point of drawing the cavity there.
    pore_opacity: float = 0.35
    # A ruler in the corner, in Angstrom.  Off by default, like depth
    # cueing: it is what you reach for when the size is the question,
    # and a documentation image that quietly acquired one would be
    # showing something nobody asked for.
    show_scale_bar: bool = False

    # Display range in fractional coordinates, inclusive.
    range_a: tuple[float, float] = (0.0, 1.0)
    range_b: tuple[float, float] = (0.0, 1.0)
    range_c: tuple[float, float] = (0.0, 1.0)
    #: What happens to a bond whose far atom is outside the range.
    #: ``half`` by default: of the three it is the only one that is
    #: not wrong about something -- see :data:`BOUNDARIES`.
    boundary: str = "half"

    background: tuple[int, int, int] = BACKGROUNDS["white"]
    projection: str = "perspective"         # perspective | orthographic
    show_legend: bool = False

    # Coordination polyhedra.  An empty set of centres means "whatever
    # has enough neighbours", which is the useful default: naming the
    # centres by hand is for when that guesses wrong, not before.
    polyhedron_opacity: float = 0.75
    polyhedron_min_vertices: int = 4
    polyhedron_centres: tuple = ()

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

    @property
    def normal_color(self) -> tuple[int, int, int]:
        """The normal of a plane that has no colour of its own."""
        return normal_of(self.plane_color)

    # -- display range -------------------------------------------------

    @property
    def ranges(self) -> tuple[tuple[float, float], ...]:
        return (self.range_a, self.range_b, self.range_c)

    def set_cells(self, na: float, nb: float, nc: float) -> None:
        """Show na x nb x nc cells starting at the origin.

        Fractional counts are the point of taking floats: 1.5 x 1 x 1
        is half a cell more of a framework, which is how you see what a
        pore connects to without the eight-fold picture a whole extra
        cell in every direction gives.  Whole numbers are what the
        toolbar usually sends and mean exactly what they did.
        """
        for n in (na, nb, nc):
            if float(n) <= 0.0:
                raise ValueError("cell counts must be more than 0")
        self.range_a = (0.0, float(na))
        self.range_b = (0.0, float(nb))
        self.range_c = (0.0, float(nc))

    @property
    def cells(self) -> tuple[float, float, float]:
        """How many cells the range spans along each axis.

        Not rounded to whole cells: the number it hands back is what
        the toolbar's boxes show, and rounding 1.5 to 2 there would
        make the picture and the control disagree about what is drawn.
        """
        return tuple(max(hi - lo, 0.0) for lo, hi in self.ranges)

    # -- housekeeping --------------------------------------------------

    def copy(self) -> ViewSettings:
        return replace(self,
                       element_colors=dict(self.element_colors),
                       element_radii=dict(self.element_radii),
                       polyhedron_centres=tuple(
                           self.polyhedron_centres))

    def to_dict(self) -> dict:
        return {
            "style": self.style,
            "atom_scale": self.atom_scale,
            "bond_radius": self.bond_radius,
            "show_atoms": self.show_atoms,
            "show_bonds": self.show_bonds,
            "show_cell": self.show_cell,
            "show_axes": self.show_axes,
            "show_bond_orders": self.show_bond_orders,
            "show_topology": self.show_topology,
            "topology_color": list(self.topology_color),
            "show_planes": self.show_planes,
            "plane_color": list(self.plane_color),
            "show_pores": self.show_pores,
            "pore_all_nodes": self.pore_all_nodes,
            "pore_color": list(self.pore_color),
            "pore_edge_color": list(self.pore_edge_color),
            "pore_opacity": self.pore_opacity,
            "show_scale_bar": self.show_scale_bar,
            "depth_cue": self.depth_cue,
            "depth_cue_strength": self.depth_cue_strength,
            "depth_cue_start": self.depth_cue_start,
            "depth_cue_end": self.depth_cue_end,
            "ellipsoid_probability": self.ellipsoid_probability,
            "ellipsoid_octants": self.ellipsoid_octants,
            "label_mode": self.label_mode,
            "range_a": list(self.range_a),
            "range_b": list(self.range_b),
            "range_c": list(self.range_c),
            "boundary": self.boundary,
            "background": list(self.background),
            "projection": self.projection,
            "show_legend": self.show_legend,
            "polyhedron_opacity": self.polyhedron_opacity,
            "polyhedron_min_vertices": self.polyhedron_min_vertices,
            "polyhedron_centres": list(self.polyhedron_centres),
            "element_colors": {k: list(v)
                               for k, v in self.element_colors.items()},
            "element_radii": dict(self.element_radii),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ViewSettings:
        s = cls()
        for key in ("style", "atom_scale", "bond_radius", "show_atoms",
                    "show_bonds", "show_cell", "show_axes",
                    "show_bond_orders", "show_topology",
                    "show_planes", "show_pores", "pore_all_nodes",
                    "pore_opacity", "show_scale_bar", "depth_cue",
                    "depth_cue_strength", "depth_cue_start",
                    "depth_cue_end", "ellipsoid_probability",
                    "ellipsoid_octants",
                    "label_mode", "boundary", "projection",
                    "show_legend", "polyhedron_opacity",
                    "polyhedron_min_vertices"):
            if key in d:
                setattr(s, key, d[key])
        if s.boundary not in BOUNDARIES:
            s.boundary = cls.boundary
        if "polyhedron_centres" in d:
            s.polyhedron_centres = tuple(d["polyhedron_centres"])
        for key in ("range_a", "range_b", "range_c"):
            if key in d:
                setattr(s, key, tuple(d[key]))
        for key in ("background", "topology_color", "plane_color",
                    "pore_color", "pore_edge_color"):
            if key in d:
                setattr(s, key, tuple(d[key]))
        s.element_colors = {k: tuple(v) for k, v in
                            d.get("element_colors", {}).items()}
        s.element_radii = dict(d.get("element_radii", {}))
        return s
