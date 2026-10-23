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

import difflib
import functools
import math
import typing
from dataclasses import dataclass, field, fields, replace

from xtal.core import elements as el
from xtal.core import scalars
from xtalapp.viewport import colormaps, styles

# Styles are looked up in xtalapp.viewport.styles; the name is stored
# here so settings stay a plain, serialisable record.
#: Occupancy pies, so that a disordered site says it is one the moment
#: a deposited structure opens -- and a fully occupied one looks
#: exactly as plain ball and stick does.
DEFAULT_STYLE = "ball_stick_occupancy"

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

#: Which pore sphere a porosity run's network is drawn with:
#: ``(value, label, tooltip)``.  D_f is not among them and cannot be --
#: see :class:`xtal.analysis.porosity.PoreNetwork`.
PORE_SPHERES = (
    ("largest", "By size",
     "One sphere, at the middle of a cavity: the largest, D_i, unless "
     "a smaller one is chosen below"),
    ("along_free", "Along the free path (D_if)",
     "One sphere, at the node that is the widest point of the channel "
     "the free sphere squeezes through: D_if"),
    ("all", "Every node",
     "A sphere at every accessible Voronoi node.  Hundreds of them in "
     "a cell"),
)

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

#: A ring's face by its size, after the picture a ZTC group sent of
#: their models: the hexagons a sheet is mostly made of in a warm
#: yellow that recedes, and the defects -- the five- and seven-rings
#: that bend it -- in colours that stand out from it and from each
#: other.  Anything above ten shares the last.  Overridden per size in
#: :attr:`ViewSettings.ring_colors`.
RING_COLORS = {
    3: (150, 150, 150),
    4: (214, 48, 49),
    5: (232, 84, 140),
    6: (247, 196, 37),
    7: (38, 198, 218),
    8: (108, 76, 214),
    9: (120, 190, 60),
    10: (150, 110, 60),
}

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

#: What "follow the system" means: the two of the above that belong
#: with a light and a dark window.  A white rectangle in the middle of
#: a dark application was what every screenshot of this program showed.
THEME_BACKGROUNDS = {False: BACKGROUNDS["white"], True: BACKGROUNDS["slate"]}

#: The name *View > Background* uses for the entry that is not a
#: colour.  Not a key of BACKGROUNDS: there is no such fixed colour.
FOLLOW_THE_SYSTEM = "system"


def theme_background() -> tuple[int, int, int]:
    """The background that goes with the theme in force."""
    from xtalapp.widgets.tone import is_dark
    return THEME_BACKGROUNDS[is_dark()]


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
    # How large the a, b, c triad in the corner is, against its
    # default.  A figure exported for a slide wants it larger than a
    # window on a laptop does.
    axes_scale: float = 1.0
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
    #: The Skeletal style: write every carbon as "C", or leave it
    #: implicit where lines meet, as a chemist draws one.
    sketch_explicit_carbon: bool = False
    #: The Skeletal style: labels in their element's colour rather
    #: than in ink.  Off, because the drawing it imitates is black.
    sketch_color_labels: bool = False
    #: The Skeletal style: a bond tilted out of the screen as a solid
    #: or hashed wedge.  Off draws every single bond as a plain line,
    #: for a picture that wants the connectivity and not the depth.
    sketch_wedges: bool = True
    #: The Skeletal style: each label on a box of the background, which
    #: interrupts whatever runs behind it, as ChemDraw sets one.  Off
    #: writes the letters alone.
    sketch_label_box: bool = True
    #: Whether that box hides a pore sphere behind the label too.  Off,
    #: because a translucent sphere punched full of white rectangles
    #: is a picture of the labels and not of the pore: the box then
    #: interrupts bonds and still lets the sphere through.
    sketch_box_over_pores: bool = False

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
    #: Which sphere: one of :data:`PORE_SPHERES`.  One sphere by
    #: default: a framework's accessible network is hundreds of nodes
    #: in a cell and thousands across a display range, and a
    #: translucent ball at each is a fog over the crystal it is about.
    pore_spheres: str = "largest"
    #: Under ``largest``, which kind of cavity, widest first: 0 is
    #: D_i.  See :meth:`xtal.analysis.porosity.PoreNetwork.cavities`
    #: -- HKUST-1's D_i is at the corner and face centres, and the cage
    #: at the body centre is the second kind.  Clamped where it is
    #: drawn, so a network with fewer kinds draws its last.
    pore_cavity: int = 0
    #: Which copy of that sphere, most central first; -1 is every copy.
    pore_copy: int = 0
    #: Whether that sphere is drawn.  Independent of ``show_pores``,
    #: which is the channel skeleton and the surface: either can be
    #: wanted without the other -- where the cavity is, or the path
    #: through it with nothing hiding the framework.
    show_pore_spheres: bool = True
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
    #: Whether the background follows the system's light or dark
    #: theme.  A colour chosen by hand turns it off -- an explicit
    #: choice is not a thing to overwrite when the sun goes down.
    background_follows_theme: bool = False
    projection: str = "perspective"         # perspective | orthographic
    show_legend: bool = False

    # Coordination polyhedra.  An empty set of centres means "whatever
    # has enough neighbours", which is the useful default: naming the
    # centres by hand is for when that guesses wrong, not before.
    polyhedron_opacity: float = 0.75
    polyhedron_min_vertices: int = 3
    polyhedron_centres: tuple = ()
    #: Element pairs ("O-Ti") whose bonds make no polyhedron -- Bond
    #: Rules' Polyhedra column.  Here and never in the bond rules,
    #: whose signature keys the stored graph: a tick there would have
    #: perceived the bonds again.
    polyhedron_pairs_off: tuple = ()

    # Rings filled in by size: a face per primitive ring, see
    # :mod:`xtal.core.rings`.  Off, because it is a search of the
    # whole graph and a picture of something particular -- the
    # pentagons and heptagons of a curved carbon -- rather than of the
    # crystal.  Up to eight-membered by default: the faces a carbon
    # sheet is made of, at a tenth of a second on three thousand atoms.
    show_rings: bool = False
    ring_max_size: int = 8
    #: Fainter than a polyhedron: rings tile a sheet edge to edge, and
    #: the atoms and bonds they are made of must still read through.
    ring_opacity: float = 0.45
    ring_colors: dict = field(default_factory=dict)

    # Colour by a number per atom or per bond (:mod:`xtal.core.
    # scalars`) in place of the element, with a colour bar for a
    # legend.  Empty is off.  It is read when the picture is built and
    # writes nothing back, so the colours chosen by hand per element
    # are what come back when it is turned off.  ``color_range`` is
    # None for the values' own least and greatest.
    color_by: str = ""
    color_map: str = "viridis"
    color_range: tuple | None = None

    element_colors: dict = field(default_factory=dict)
    element_radii: dict = field(default_factory=dict)

    # -- element appearance -------------------------------------------

    def color_for(self, element: str) -> tuple[int, int, int]:
        """User override if there is one, else the element's palette
        colour."""
        if element in self.element_colors:
            return tuple(self.element_colors[element])
        return el.color(element)

    def ring_color(self, size: int) -> tuple[int, int, int]:
        """The fill of an ``size``-membered ring: the user's, else
        :data:`RING_COLORS`."""
        if size in self.ring_colors:
            return tuple(self.ring_colors[size])
        return RING_COLORS[min(max(size, 3), max(RING_COLORS))]

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
                       ring_colors=dict(self.ring_colors),
                       polyhedron_centres=tuple(
                           self.polyhedron_centres),
                       polyhedron_pairs_off=tuple(
                           self.polyhedron_pairs_off))

    def to_dict(self) -> dict:
        return {
            "style": self.style,
            "atom_scale": self.atom_scale,
            "bond_radius": self.bond_radius,
            "show_atoms": self.show_atoms,
            "show_bonds": self.show_bonds,
            "show_cell": self.show_cell,
            "show_axes": self.show_axes,
            "axes_scale": self.axes_scale,
            "show_bond_orders": self.show_bond_orders,
            "show_topology": self.show_topology,
            "topology_color": list(self.topology_color),
            "show_planes": self.show_planes,
            "plane_color": list(self.plane_color),
            "show_pores": self.show_pores,
            "pore_spheres": self.pore_spheres,
            "pore_cavity": self.pore_cavity,
            "pore_copy": self.pore_copy,
            "show_pore_spheres": self.show_pore_spheres,
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
            "sketch_explicit_carbon": self.sketch_explicit_carbon,
            "sketch_color_labels": self.sketch_color_labels,
            "sketch_wedges": self.sketch_wedges,
            "sketch_label_box": self.sketch_label_box,
            "sketch_box_over_pores": self.sketch_box_over_pores,
            "range_a": list(self.range_a),
            "range_b": list(self.range_b),
            "range_c": list(self.range_c),
            "boundary": self.boundary,
            "background": list(self.background),
            "background_follows_theme": self.background_follows_theme,
            "projection": self.projection,
            "show_legend": self.show_legend,
            "polyhedron_opacity": self.polyhedron_opacity,
            "polyhedron_min_vertices": self.polyhedron_min_vertices,
            "polyhedron_centres": list(self.polyhedron_centres),
            "polyhedron_pairs_off": list(self.polyhedron_pairs_off),
            "show_rings": self.show_rings,
            "ring_max_size": self.ring_max_size,
            "ring_opacity": self.ring_opacity,
            # JSON keys are strings, so the sizes are written as such
            # and read back as numbers.
            "ring_colors": {str(k): list(v)
                            for k, v in self.ring_colors.items()},
            "color_by": self.color_by,
            "color_map": self.color_map,
            "color_range": (None if self.color_range is None
                            else list(self.color_range)),
            "element_colors": {k: list(v)
                               for k, v in self.element_colors.items()},
            "element_radii": dict(self.element_radii),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ViewSettings:
        s = cls()
        for key in ("style", "atom_scale", "bond_radius", "show_atoms",
                    "show_bonds", "show_cell", "show_axes",
                    "axes_scale", "show_bond_orders", "show_topology",
                    "show_planes", "show_pores", "pore_spheres",
                    "pore_cavity", "pore_copy",
                    "show_pore_spheres",
                    "pore_opacity", "show_scale_bar", "depth_cue",
                    "depth_cue_strength", "depth_cue_start",
                    "depth_cue_end", "ellipsoid_probability",
                    "ellipsoid_octants",
                    "label_mode", "sketch_explicit_carbon",
                    "sketch_color_labels", "sketch_wedges",
                    "sketch_label_box", "sketch_box_over_pores",
                    "boundary", "projection",
                    "show_legend", "polyhedron_opacity",
                    "polyhedron_min_vertices",
                    "show_rings", "ring_max_size", "ring_opacity",
                    "color_by", "color_map",
                    "background_follows_theme"):
            if key in d:
                setattr(s, key, d[key])
        if s.boundary not in BOUNDARIES:
            s.boundary = cls.boundary
        # A project written by a later version may name a style this
        # one does not have.  Opening it as the default draws the
        # crystal; keeping the name made every redraw raise.
        if s.style not in styles.STYLES:
            s.style = DEFAULT_STYLE
        # A session saved before the choice had three values held a
        # yes-or-no for every node.
        if d.get("pore_all_nodes") and "pore_spheres" not in d:
            s.pore_spheres = "all"
        if s.pore_spheres not in {v for v, _l, _t in PORE_SPHERES}:
            s.pore_spheres = cls.pore_spheres
        if "polyhedron_centres" in d:
            s.polyhedron_centres = tuple(d["polyhedron_centres"])
        if "polyhedron_pairs_off" in d:
            s.polyhedron_pairs_off = tuple(d["polyhedron_pairs_off"])
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
        s.ring_colors = {int(k): tuple(v) for k, v in
                         d.get("ring_colors", {}).items()}
        if s.color_by and s.color_by not in scalars.QUANTITIES:
            s.color_by = ""
        if d.get("color_range") is not None:
            s.color_range = tuple(float(v) for v in d["color_range"])
        return s


# -- what a client may ask for ------------------------------------------
#
# An assistant's request arrives as JSON, so every value is checked
# against the record's own type here before anything is set.  Unlike
# from_dict, which falls back to a default so that an old project
# still opens, a request that names something this version does not
# have is refused: the client asked for that picture and would
# otherwise be told it got it.

#: The values of ``label_mode``, in the order the Style panel offers
#: them.
LABEL_MODES = ("none", "element", "label", "index")
PROJECTIONS = ("perspective", "orthographic")

#: The string fields that take one of a fixed set of values.  Built
#: from the lists the panel and the scene use, never copied, so a
#: style added there is one a client may ask for.
VIEW_CHOICES: dict[str, tuple[str, ...]] = {
    "style": tuple(styles.names()),
    # "" is Element: the colours per element, not a quantity.
    "color_by": ("",) + tuple(scalars.QUANTITIES),
    "color_map": tuple(colormaps.COLOR_MAPS),
    "label_mode": LABEL_MODES,
    "boundary": BOUNDARIES,
    "projection": PROJECTIONS,
    "pore_spheres": tuple(v for v, _label, _tip in PORE_SPHERES),
}

#: The ring sizes a colour may be given for and the search may be
#: asked to go up to: the smallest ring there is, to the largest the
#: Style panel offers -- above ten the search is seconds.
RING_SIZES = range(3, 13)

# What the Style panel's controls offer, which the panel is built from
# and a client is held to: a value outside them is one the panel
# cannot show, and some the scene cannot draw.
ATOM_SCALE_MAX = 3.0
AXES_SCALE_RANGE = (0.5, 3.0)
BOND_RADIUS_RANGE = (0.01, 1.0)
#: Below 5% a face is invisible and still hides what is behind it.
OPACITY_RANGE = (0.05, 1.0)
ELEMENT_RADIUS_RANGE = (0.05, 5.0)
#: A dummy atom is a marker and not an atom, and a marker the size of
#: a pore is one of the things it is for -- so it has no ceiling worth
#: the name.  Qt needs a number.
DUMMY_RADIUS_MAX = 1e4


class _Refused(ValueError):
    """One value that cannot be set, carrying the reason why."""


def _bool(value) -> bool:
    # 0 and 1 are refused, so that a 2 is not quietly taken as true.
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true",
                                                            "false"):
        return value.strip().lower() == "true"
    raise _Refused(f"{value!r} is not true or false")


def _float(value) -> float:
    # A bool is an int to Python and never a number to a client.
    if isinstance(value, (int, float, str)) and \
            not isinstance(value, bool):
        try:
            number = float(value)
        except ValueError:
            pass
        else:
            # NaN or infinity would reach the scene and draw nothing.
            if math.isfinite(number):
                return number
    raise _Refused(f"{value!r} is not a number")


def _int(value) -> int:
    number = _float(value)
    if not number.is_integer():
        raise _Refused(f"{value!r} is not a whole number")
    return int(number)


def _number(lo=None, hi=None, *, integer=False, above=False,
            below=False):
    """(words, check) for a number from ``lo`` to ``hi``, either
    left out for no limit; ``above`` and ``below`` leave out the end
    itself."""
    if lo is not None and hi is not None:
        where = (f"between {lo:g} and {hi:g}, exclusive"
                 if above and below else
                 f"more than {lo:g}, at most {hi:g}" if above else
                 f"from {lo:g} to {hi:g}")
    elif lo is not None:
        where = f"more than {lo:g}" if above else f"at least {lo:g}"
    else:
        where = f"less than {hi:g}" if below else f"at most {hi:g}"
    read = _int if integer else _float

    def check(value):
        number = read(value)
        if lo is not None and (number <= lo if above else number < lo) \
                or hi is not None and (number >= hi if below
                                       else number > hi):
            raise _Refused(f"{value!r} is not {where}")
        return number
    return f"{'integer' if integer else 'number'} {where}", check


_FRACTION = _number(0.0, 1.0)
_OPACITY = _number(*OPACITY_RANGE)


def _rgb(value) -> tuple[int, int, int]:
    rgb = None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            rgb = tuple(_int(c) for c in value)
        except _Refused:
            pass
    if rgb is None or not all(0 <= c <= 255 for c in rgb):
        raise _Refused(f"{value!r} is not a colour: three integers "
                       "from 0 to 255")
    return rgb


def _background(value) -> tuple[int, int, int]:
    if isinstance(value, str):
        if value in BACKGROUNDS:
            return BACKGROUNDS[value]
        raise _Refused(f"{value!r} is not one of "
                       f"{', '.join(map(repr, BACKGROUNDS))}")
    return _rgb(value)


def _span(value, *, wide=False) -> tuple[float, float]:
    span = None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            span = tuple(_float(v) for v in value)
        except _Refused:
            pass
    if span is None or span[0] > span[1] or wide and span[0] == span[1]:
        raise _Refused(f"{value!r} is not two numbers, low first"
                       + (", and not equal" if wide else ""))
    return span


def _optional_span(value) -> tuple[float, float] | None:
    # A colour range of one value colours everything the middle of
    # the map, which says nothing.
    return None if value is None else _span(value, wide=True)


def _symbol(value) -> str:
    # The strict reading: "Kryptonite" is not krypton here.
    symbol = el.canonical_symbol(value) if isinstance(value, str) \
        else None
    if symbol is None:
        raise _Refused(f"{value!r} is not an element symbol")
    return symbol


def _symbols(value) -> tuple:
    # A bare string is refused rather than read letter by letter.
    if not isinstance(value, (list, tuple)):
        raise _Refused(f"{value!r} is not a list of element symbols")
    return tuple(_symbol(v) for v in value)


def _pair(value) -> str:
    if isinstance(value, str) and "-" in value:
        value = value.split("-", 1)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise _Refused(f"{value!r} is not a pair of elements, "
                       "\"O-Ti\" or [\"O\", \"Ti\"]")
    # Spelt as the builder spells a pair, so one pair is one entry.
    return "-".join(sorted(_symbol(v) for v in value))


def _pairs(value) -> tuple:
    if not isinstance(value, (list, tuple)):
        raise _Refused(f"{value!r} is not a list of element pairs")
    return tuple(_pair(v) for v in value)


def _ring_size(value) -> int:
    size = _int(value)
    if size not in RING_SIZES:
        raise _Refused(f"{value!r} is not a ring size from "
                       f"{RING_SIZES[0]} to {RING_SIZES[-1]}")
    return size


def _radius(symbol: str, value) -> float:
    lo, hi = ELEMENT_RADIUS_RANGE
    if el.is_dummy(symbol):
        hi = DUMMY_RADIUS_MAX
    return _number(lo, hi)[1](value)


def _keyed(key, coerce):
    """A dict whose keys and values are each checked -- JSON's keys
    are strings, so a ring size arrives as "6".  ``coerce`` is given
    the checked key as well as the value."""
    def coerce_dict(value) -> dict:
        if not isinstance(value, dict):
            raise _Refused(f"{value!r} is not an object")
        cleaned = {}
        for k, v in value.items():
            checked = key(k)
            # "o" and "O", or "6" and 6: which one won would be the
            # order the client happened to write them in.
            if checked in cleaned:
                raise _Refused(f"{k!r} names {checked!r} a second time")
            cleaned[checked] = coerce(checked, v)
        return cleaned
    return coerce_dict


def _choice(name: str):
    choices = VIEW_CHOICES[name]

    def coerce_choice(value) -> str:
        if isinstance(value, str) and value in choices:
            return value
        raise _Refused(f"{value!r} is not one of "
                       f"{', '.join(map(repr, choices))}")
    return coerce_choice


#: How each type of field is checked, as (what it is in words, the
#: function that checks it).
_BY_TYPE = {
    bool: ("true or false", _bool),
    float: ("number", _float),
    int: ("integer", _int),
    tuple[int, int, int]: ("colour: three integers from 0 to 255",
                           _rgb),
    tuple[float, float]: ("range in fractional coordinates: two "
                          "numbers, low first", _span),
}

#: The fields whose declared type says too little -- a bare ``tuple``
#: or ``dict`` -- or that take something besides it.
_BY_FIELD = {
    "background": (
        "colour: three integers from 0 to 255, or one of "
        + ", ".join(BACKGROUNDS), _background),
    "color_range": (
        "null for the values' own least and greatest, or two numbers, "
        "low below high", _optional_span),
    "polyhedron_centres": (
        "list of element symbols; empty is every metal", _symbols),
    "polyhedron_pairs_off": (
        "list of element pairs that make no polyhedron, \"O-Ti\" or "
        "[\"O\", \"Ti\"]", _pairs),
    "element_colors": ("object: element symbol to colour",
                       _keyed(_symbol, lambda _k, v: _rgb(v))),
    "element_radii": (
        "object: element symbol to radius in Angstrom, from "
        f"{ELEMENT_RADIUS_RANGE[0]:g} to {ELEMENT_RADIUS_RANGE[1]:g} "
        f"(up to {DUMMY_RADIUS_MAX:g} for a dummy atom)",
        _keyed(_symbol, _radius)),
    "ring_colors": (f"object: ring size from {RING_SIZES[0]} to "
                    f"{RING_SIZES[-1]} to colour",
                    _keyed(_ring_size, lambda _k, v: _rgb(v))),
    "atom_scale": _number(0.0, ATOM_SCALE_MAX, above=True),
    "bond_radius": _number(*BOND_RADIUS_RANGE),
    "axes_scale": _number(*AXES_SCALE_RANGE),
    # 1 is a sphere at infinity: transforms.probability_scale raises,
    # and so would every redraw.  90 meant as 90% is the likely slip.
    "ellipsoid_probability": (
        "a probability between 0 and 1, exclusive",
        _number(0.0, 1.0, above=True, below=True)[1]),
    "depth_cue_strength": _FRACTION,
    "depth_cue_start": _FRACTION,
    "depth_cue_end": _FRACTION,
    "polyhedron_opacity": _OPACITY,
    "pore_opacity": _OPACITY,
    "ring_opacity": _OPACITY,
    "ring_max_size": _number(RING_SIZES[0], RING_SIZES[-1],
                             integer=True),
    # A polyhedron has at least a face: three vertices.
    "polyhedron_min_vertices": _number(3, integer=True),
    "pore_cavity": _number(0, integer=True),
    # -1 is every copy.
    "pore_copy": _number(-1, integer=True),
}


@functools.cache
def _kinds() -> dict[str, tuple[str, typing.Callable]]:
    """Every field's (words, check).  Worked out on first use, so a
    field of a type nobody has taught this fails the schema's test
    rather than the import of the module that draws everything."""
    hints = typing.get_type_hints(ViewSettings)
    kinds = {}
    for f in fields(ViewSettings):
        if f.name in _BY_FIELD:
            kinds[f.name] = _BY_FIELD[f.name]
        elif f.name in VIEW_CHOICES:
            kinds[f.name] = ("one of the choices", _choice(f.name))
        else:
            kinds[f.name] = _BY_TYPE[hints[f.name]]
    return kinds


def coerce_view(changes) -> dict | str:
    """``changes`` as values ViewSettings holds, or the one sentence
    saying why not.

    All or nothing: the first key or value that cannot be set refuses
    the whole request, because half a change applied is a picture
    nobody asked for.
    """
    if not isinstance(changes, dict):
        return ("view settings are an object of setting names to "
                f"values, not {type(changes).__name__}")
    kinds = _kinds()
    cleaned = {}
    for name, value in changes.items():
        if name not in kinds:
            names = sorted(kinds)
            close = difflib.get_close_matches(str(name), names)
            hint = f"; did you mean {', '.join(close)}?" if close else "."
            return (f"there is no view setting {name!r}{hint} "
                    f"The settings are {', '.join(names)}")
        try:
            cleaned[name] = kinds[name][1](value)
        except _Refused as refused:
            return f"view setting {name}: {refused}"
    # A colour chosen by hand is never overwritten, by a theme change
    # or anything else: View > Background's colours stop following the
    # theme, and so does one an assistant was asked for.
    if "background" in cleaned:
        cleaned.setdefault("background_follows_theme", False)
    return cleaned


def view_schema() -> dict[str, dict]:
    """Each field's type in words, its choices if it has a list of
    them, and its default as ``to_dict`` writes it."""
    defaults = ViewSettings().to_dict()
    return {name: {"type": words,
                   "choices": (list(VIEW_CHOICES[name])
                               if name in VIEW_CHOICES else None),
                   "default": defaults[name]}
            for name, (words, _check) in _kinds().items()}
