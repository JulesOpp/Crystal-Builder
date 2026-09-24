"""
xtal.mof.build
==============
PORMAKE invoked, the framework read back, and the net drawn on it.

Four steps, and the interesting ones are the last two.

**Resolve.**  A request is three strings -- a topology name, which
block goes in which node slot, which goes on which edge -- because
that is what survives a command line, a saved parameter set and a
dialog equally well.  :class:`BuildRequest` turns them into the
``{type: block}`` dictionaries ``Builder.build_by_type`` wants, and
refuses a block whose connection points do not match the slot's
coordination number *before* PORMAKE is asked to place it: PORMAKE's
own refusal is an assertion deep inside a locator, and "N59 has 6
connection points and node 2 wants 4" is the sentence a user can act
on.

**Build.**  One call.  This is the only place ``pormake`` is imported,
and it happens on the worker thread because the import costs ten
seconds.

**Hand over as CIF.**  ``Framework.write_cif`` into the run folder and
:func:`xtal.io.FORMATS.read` back.  Not the ASE or pymatgen objects
PORMAKE works in: the run folder wants the file on disk anyway, gemmi
already reads it, and a translation layer between three different atom
containers is a bug farm with no upside.

**Draw the net on it, and then check it.**  PORMAKE builds a framework
by putting a block on every slot of a net, so it knows exactly which
atoms are one node -- and a net is exactly what this application draws
on a framework by hand.  So :func:`draw_net` puts the edges in as
:data:`~xtal.core.structure.TOPOLOGY` bonds and the framework arrives
with its net already drawn: the Net panel names it as soon as the tab
opens, and nobody has to click two atoms of a 3856-atom framework to
find out what they built.

That also makes the build checkable, which nothing else in this
application does.  :func:`check_net` reads the net back off the
structure with :func:`xtal.analysis.net_of` -- the same function the
panel uses, over bonds stored in the structure rather than over
anything PORMAKE said -- and names it against the RCSR.  A build that
was asked for **tbo** and produces something that is not tbo says so
in its own report.  Every piece of that was written and tested for the
topology work; what is new here is using the canonical key for
something other than answering a question.
"""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from xtal.core.structure import TOPOLOGY, Bond
from xtal.mof.catalog import Catalog, CatalogError, Slot

#: How far :func:`closest_contact` looks.  Nothing unbonded within
#: 3 A is an open framework, not a verdict, and looking further costs
#: pairs without changing the answer: the shortest unbonded contact in
#: every sample that has one is under 2.2 A.
CONTACT_CUTOFF = 3.0

#: PORMAKE's own name for the atoms that mark where a block connects.
#: They are removed from the framework, which is what makes the atom
#: ordering below need stating rather than assuming.
CONNECTION = "X"


class MofError(ValueError):
    """A build that cannot be set up, said in a sentence."""


# ======================================================================
#  WHAT WAS ASKED FOR
# ======================================================================

@dataclass
class BuildRequest:
    """A topology, a block per node slot, and a block per edge slot.

    Held as plain data on purpose.  The same object is what a dialog
    fills in, what ``xtal run`` parses out of ``-p`` flags and what a
    test writes by hand, and none of those three should have to know
    about a PORMAKE object.
    """

    topology: str
    #: ``{node type: block name}``.  Node type 0 is the first ``NODE``
    #: line of the ``.cgd``; see :mod:`xtal.mof.catalog`.
    nodes: dict[int, str] = field(default_factory=dict)
    #: ``{(node type, node type): block name}``.  Empty means no
    #: linkers at all, which PORMAKE builds as nodes bonded directly.
    edges: dict[tuple[int, int], str] = field(default_factory=dict)
    #: How many times the net is repeated along its own axes before
    #: anything is placed on it.  ``(1, 1, 1)`` is the net itself and
    #: is the only value that takes the build down the path it always
    #: took -- see :meth:`xtal.mof.catalog.Topology.expanded`.
    repeat: tuple[int, int, int] = (1, 1, 1)
    #: Which way round the node blocks go: see :mod:`xtal.mof.orient`.
    #: ``"consistent"`` by default, because it is what builds MOF-5
    #: with its clusters alternating; ``"as-found"`` is what the
    #: locator chose, byte for byte what PORMAKE makes.  Spelled out
    #: here rather than imported, because :mod:`xtal.mof.orient`
    #: imports this module.
    orientation: str = "consistent"
    #: How far apart the sheets of a layer net are stacked, in
    #: Angstrom, or ``None`` for :data:`xtal.mof.layers.
    #: DEFAULT_SPACING`.  ``None`` is not the same as 3.4 written
    #: down: a 3-periodic net has no spacing to set, and one that was
    #: *asked for* there is refused rather than ignored.
    spacing: float | None = None
    #: Where each sheet sits over the one below, in fractions of the
    #: net's own *a* and *b*, or ``None`` for eclipsed.  Refused on a
    #: 3-periodic net for the same reason.
    offset: tuple[float, float] | None = None
    #: How many copies of the framework, threaded through one another.
    #: 1 is the framework alone.  Placed after the build by
    #: :func:`xtal.analysis.interpenetrate.best` -- the placement with
    #: the most room -- and refused, by name, when none has any.
    interpenetration: int = 1

    @classmethod
    def parse(cls, topology: str, nodes: str, edges: str,
              repeat: str = "", orientation: str = "",
              spacing: str = "", offset: str = "",
              interpenetration="") -> BuildRequest:
        """The strings a parameter form and a command line both hand
        over.

        ``nodes`` is ``"N59"`` when there is one node type and
        ``"0=N59,1=N131"`` when there is more than one; ``edges`` is
        ``"E32"``, ``"0-0=E32,0-1=E14"``, or empty for none.  The bare
        form exists because the overwhelming majority of nets people
        build on have one kind of node and one kind of edge, and
        making those spell a slot they cannot get wrong is ceremony.

        ``repeat`` is ``"2x2x2"``, ``"2"`` for the same in all three,
        or empty for the net as it stands.  ``spacing`` is a length in
        Angstrom and ``offset`` two fractions, ``"1/3, 2/3"``; both
        empty is a layer stacked eclipsed at the default spacing, and
        a 3-periodic net built as it always was.  ``interpenetration``
        is a count of copies, empty or 1 for the framework alone.
        """
        topology = str(topology or "").strip()
        if not topology:
            raise MofError("a build needs a topology to build on")
        return cls(topology,
                   _assignments(nodes, _node_key, "node"),
                   _assignments(edges, _edge_key, "edge"),
                   _repeat(repeat),
                   str(orientation or "").strip() or "consistent",
                   _spacing(spacing), _offset(offset),
                   _interpenetration(interpenetration))

    def spelled(self) -> tuple[str, str, str]:
        """Back to the three strings, for a log and for a saved set.

        The unkeyed form comes back unkeyed: what a user wrote is what
        their log says they ran, and rewriting ``N59`` as ``0=N59``
        would make the record of a run stop matching the run.
        """
        return (self.topology, _spell(self.nodes, _node_token),
                _spell(self.edges, _edge_token))

    def title(self) -> str:
        """What to call the framework: ``pcu-N59-E32``.

        A repeat is spelled into it -- ``pcu-2x2x2-N59-E32`` -- and
        only when there is one, so that the name of every framework
        built before repeats existed is the name it had.  The
        orientation rule is *not*: it changes which way round the
        blocks are and never what the framework is made of, and two
        files whose names differ only in it would be two names for
        one material.
        """
        parts = [self.topology]
        if self.repeat != (1, 1, 1):
            parts.append("x".join(str(n) for n in self.repeat))
        if self.interpenetration > 1:
            parts.append(f"{self.interpenetration}fold")
        parts += [self.nodes[k] for k in _ordered(self.nodes)]
        parts += [self.edges[k] for k in _ordered(self.edges)]
        return "-".join(p for p in parts if p)

    def block_for(self, slot: Slot) -> str:
        """The block this request puts in that slot, or ``""``.

        A single unkeyed assignment fills every slot of its kind,
        which is what makes ``nodes="N59"`` mean what it obviously
        means on a net with one node type -- and what makes it mean
        "the same block everywhere" on one with two.
        """
        table = self.edges if slot.is_edge else self.nodes
        if slot.key in table:
            return table[slot.key]
        if len(table) == 1 and _ANY in table:
            return table[_ANY]
        return ""


#: The key an unkeyed assignment is stored under -- ``"N59"`` rather
#: than ``"0=N59"``.  Not a valid slot key, so it can never collide
#: with one.
_ANY = "*"


def _assignments(text, key_of, what: str) -> dict:
    out: dict = {}
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, value = part.partition("=")
        if not sep:
            out[_ANY] = name.strip()
            continue
        try:
            out[key_of(name.strip())] = value.strip()
        except ValueError:
            raise MofError(
                f"{part!r} does not name an {what} slot -- write "
                f"{'0-1=E32' if what == 'edge' else '0=N59'}, or just "
                f"the block's name to use it everywhere") from None
    if _ANY in out and len(out) > 1:
        raise MofError(
            f"the {what} blocks are written both with and without a "
            f"slot; pick one spelling")
    return out


def _ordered(table: dict) -> list:
    """The keys of an assignment table, in a stable order.

    ``sorted`` cannot do it: the unkeyed marker is a string and every
    other key is an int or a pair of them.
    """
    return sorted(table, key=lambda k: (k == _ANY, str(k)))


def _spell(table: dict, token) -> str:
    if len(table) == 1 and _ANY in table:
        return table[_ANY]
    return ",".join(f"{token(k)}={table[k]}" for k in _ordered(table))


def _node_token(key) -> str:
    return str(key)


def _edge_token(key) -> str:
    return f"{key[0]}-{key[1]}"


def _repeat(text) -> tuple[int, int, int]:
    """``"2x2x2"``, ``"2"``, ``"2,2,1"`` or nothing, as three counts.

    Separators are not a matter of taste here: ``x`` is how a person
    writes a supercell and how :meth:`BuildRequest.title` spells one
    back, and a comma is how every other list in this module is
    written.  Both are taken, so neither is a mistake.
    """
    text = str(text or "").strip().lower()
    if not text:
        return (1, 1, 1)
    parts = [part for part in text.replace(",", "x").replace(
        " ", "x").split("x") if part]
    try:
        counts = [int(part) for part in parts]
    except ValueError:
        raise MofError(
            f"{text!r} does not say how many times to repeat the "
            f"net -- write 2x2x2, or just 2") from None
    if len(counts) == 1:
        counts = counts * 3
    if len(counts) != 3 or min(counts) < 1:
        raise MofError(
            f"{text!r} does not say how many times to repeat the net "
            f"-- write 2x2x2, or just 2")
    return (counts[0], counts[1], counts[2])


def _spacing(text) -> float | None:
    """A length in Angstrom, or nothing.

    Positive, and nothing more is checked: a spacing smaller than the
    layer is thick builds sheets that collide, and the build says so
    in its closest contact rather than guessing here how thick the
    layer will turn out to be.
    """
    text = str(text if text is not None else "").strip()
    if text.lower().endswith("a"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        raise MofError(
            f"{text!r} is not an interlayer spacing -- write it in "
            f"Angstrom, 3.4") from None
    if not np.isfinite(value) or value <= 0:
        raise MofError(
            f"an interlayer spacing of {text} A would put the layers "
            f"on top of each other")
    return value


def _offset(text) -> tuple[float, float] | None:
    """Two fractions of *a* and *b* -- ``"1/3, 2/3"``, ``"0.5 0"`` --
    or nothing.

    Fractions are taken as written because the stackings people name
    are thirds and halves, and ``0.3333`` is a slip of 0.0003 of a
    cell that ``1/3`` is not.
    """
    from fractions import Fraction

    text = str(text if text is not None else "").strip()
    if not text:
        return None
    parts = [p for p in text.replace(",", " ").split() if p]
    try:
        values = [float(Fraction(p)) for p in parts]
    except (ValueError, ZeroDivisionError):
        values = []
    if len(values) != 2:
        raise MofError(
            f"{text!r} is not a stacking offset -- write two "
            f"fractions of a and b, 0,0 for eclipsed or 1/3,2/3")
    return (values[0], values[1])


def _interpenetration(text) -> int:
    """A count of copies: empty and 1 are the framework alone."""
    from xtal.analysis.interpenetrate import MAX_FOLD

    text = str(text if text is not None else "").strip().lower()
    for suffix in ("-fold", "fold"):
        if text.endswith(suffix):
            text = text[:-len(suffix)].strip()
    if not text:
        return 1
    try:
        value = int(float(text))
    except ValueError:
        value = 0
    if value < 1 or value > MAX_FOLD or value != float(text):
        raise MofError(
            f"{text!r} is not a number of interpenetrating copies -- "
            f"1 for the framework alone, up to {MAX_FOLD}")
    return value


def _node_key(text: str) -> int:
    return int(text)


def _edge_key(text: str) -> tuple[int, int]:
    a, sep, b = text.replace(",", "-").partition("-")
    if not sep:
        raise ValueError(text)
    pair = (int(a), int(b))
    return (min(pair), max(pair))


# ======================================================================
#  BUILDING
# ======================================================================

@dataclass
class BuildOutcome:
    """A framework, and everything worth saying about how it got here.

    ``rmsd`` and ``objective`` are PORMAKE's: the objective is what its
    cell relaxation converged to and the RMSD is how far the placed
    blocks are from the local geometry the net asked for.  They are the
    honest measure of whether the geometry is any good, and they are
    kept apart from ``identified``, which is about the *net* and does
    not move when the geometry does.
    """

    structure: object
    cif: Path
    request: BuildRequest
    n_atoms: int = 0
    max_rmsd: float = 0.0
    mean_rmsd: float = 0.0
    objective: float = 0.0
    #: How many node-to-linker and node-to-node joins arrived bonded.
    #: See :func:`bond_joints`: a joint can be longer than any distance
    #: criterion, so it is stored rather than left to perception.
    joints: int = 0
    #: The longest bond a joint made, in Angstrom.  0.0 when nothing
    #: measured it -- a build of single-point blocks does not, because
    #: there is one bond per joint and PORMAKE already made it.  What
    #: it says is whether the two ends of a joint actually met, which
    #: the blocks' RMSD does not: each block can sit perfectly on its
    #: own slot and still present the wrong face to its neighbour.
    longest_joint: float = 0.0
    #: What the RCSR calls the net that was drawn on the framework.
    identified: object = None
    #: The topology's own name, as PORMAKE's database spells it.
    asked: str = ""
    #: The shortest distance between two atoms that are not bonded --
    #: see :func:`closest_contact`.  ``inf`` when it was not measured,
    #: which is why it is not 0.0: 0.000 A is a real answer and CFA1
    #: gives it.
    closest: float = float("inf")
    #: ``(cost, edges)``: how far the two nodes at the ends of each edge
    #: still disagree about their faces once the orientation rule has
    #: done what it can -- :func:`xtal.mof.attach.pair_cost` summed, 0
    #: for agreement and 2 an edge for a quarter turn.  ``None`` when
    #: no rule ran or no node had a face to score.  What says a cell
    #: had no room: ``pcu`` x 1x1x1 on N16 is 6.0 over 3, because its
    #: one slot cannot alternate, and the same net x 2x2x2 is 0.
    twist: tuple | None = None

    @property
    def net_name(self) -> str:
        return self.identified.name if self.identified else ""

    @property
    def net_agrees(self) -> bool:
        """Whether what came out is the net that was asked for --
        and in as many copies as were asked for."""
        return (bool(self.net_name) and self.net_name == self.asked
                and self.copies == self.request.interpenetration)

    @property
    def copies(self) -> int:
        """How many interpenetrating copies the drawn net reads as."""
        return max(int(getattr(self.identified, "copies", 1) or 1), 1)

    def verdict(self) -> str:
        """One line: what was measured, and nothing that was not.

        The net half is a measurement and not a repetition of the
        request: it is read back off the bonds in the structure by
        :func:`check_net`.  What it must never become is a claim about
        the *shape* of the cell.  A topology is a combinatorial object
        and its metric is free -- DMOF-1 is tetragonal **pcu** and
        MIL-53 monoclinic -- so "the cell relaxed to triclinic where
        pcu is cubic" would be a false alarm on real materials.  What
        says whether a build is any good is the fit and the contacts,
        and those are numbers, so they are given as numbers.
        """
        if not self.identified:
            head = "the net could not be read back off the framework"
        elif self.net_agrees and self.copies > 1:
            head = (f"the framework is {self.identified.headline()}, "
                    f"as asked")
        elif self.net_agrees:
            head = f"the framework is {self.asked}, as asked"
        elif self.net_name == self.asked:
            asked = self.request.interpenetration
            head = (f"asked for {asked} "
                    f"cop{'y' if asked == 1 else 'ies'} of {self.asked} "
                    f"and built {self.identified.headline()}")
        elif not self.net_name:
            head = (f"asked for {self.asked}; what was built is "
                    f"{self.identified.headline()}")
        else:
            head = (f"asked for {self.asked} and built {self.net_name} "
                    f"-- these are different nets")
        return head + self._measured()

    def _measured(self) -> str:
        """The numbers, when there are any, as a trailing clause."""
        said = [f"blocks fit to {self.max_rmsd:.3f} A"]
        if np.isfinite(self.closest):
            said.append(f"closest contact {self.closest:.2f} A")
        if self.joints:
            said.append(f"{self.joints} joint(s) bonded")
        if self.longest_joint:
            said.append(f"longest joint {self.longest_joint:.2f} A")
        return " -- " + ", ".join(said)


def build(request: BuildRequest, directory, catalog: Catalog | None
          = None, log=None, trace=None) -> BuildOutcome:
    """Build one framework, and hand back the structure and the check.

    ``directory`` is where the CIF is written, which is the run folder
    when there is one and a temporary directory when there is not --
    the caller decides, because a build with no workspace should still
    answer rather than refuse.

    ``log`` is what this application says about the build and ``trace``
    is what PORMAKE says about it, defaulting to the same place.  They
    are separate because a shell wants the first on a status bar and
    the second only in the run log: five lines a person is waiting to
    read, against forty a builder emits on the way past.
    """
    catalog = catalog or Catalog.default()
    directory = Path(directory)
    topology, node_bbs, edge_bbs = _resolve(request, catalog)
    _say(log, f"topology {topology.name}: {topology.summary()}")

    cif = directory / f"{_safe(request.title())}.cif"
    with _Logging(trace if trace is not None else log) as listening:
        framework = _build(topology, node_bbs, edge_bbs, log,
                           request.repeat, request.orientation)
        if topology.is_layer:
            _stack(framework, request, log)
        # After the build and before anything reads the geometry.  A
        # two-connected block's angle about its own axis is the one
        # freedom the fit leaves *undetermined* rather than decides,
        # so settling it is not a rule the user picks between -- it
        # runs whatever `orientation` says, and is empty for every
        # block whose connection points stand for one atom.
        from xtal.mof import orient

        orient.align_edges(
            framework, log,
            faces=request.orientation == orient.CONSISTENT)
        framework.write_cif(str(cif))
        if not cif.is_file():
            raise MofError(
                f"PORMAKE built the framework and then could not "
                f"write it out: {listening.failure or cif.name}")
    _say(log, f"wrote {cif.name}")

    from xtal.io import FORMATS

    structure = FORMATS.read(cif)
    structure.meta["title"] = request.title()
    structure.meta["mof"] = " ".join(request.spelled()).strip()
    outcome = BuildOutcome(
        structure=structure, cif=cif, request=request,
        n_atoms=structure.n_sites, asked=topology.name,
        max_rmsd=float(framework.info.get("max_rmsd", 0.0) or 0.0),
        mean_rmsd=float(framework.info.get("mean_rmsd", 0.0) or 0.0),
        objective=float(framework.info.get("relax_obj", 0.0) or 0.0))
    outcome.twist = framework.info.get("joint_twist")
    outcome.joints, outcome.longest_joint = bond_joints(
        structure, framework)
    outcome.closest = closest_contact(structure)
    _say(log, f"bonded {outcome.joints} joint(s) between blocks")
    drawn = draw_net(structure, framework)
    # Said before rather than after, because it is not free: naming a
    # net walks ten shells of an infinite graph and looks for the
    # smallest ring at every angle of every vertex, which is
    # milliseconds on pcu and half a minute on the worst net in the
    # database.  A status bar that has gone quiet for thirty seconds
    # should say what it is doing.
    _say(log, f"drew {drawn} net edge(s); identifying what came out")
    if request.interpenetration > 1:
        structure = _interpenetrate(outcome, request.interpenetration,
                                    log)
    outcome.identified = check_net(structure)
    _say(log, outcome.verdict())
    return outcome


def _interpenetrate(outcome: BuildOutcome, n: int, log):
    """Thread ``n`` copies of the built framework through each other.

    After the joints are bonded and the net is drawn, because the
    copies carry what the framework has and nothing is perceived
    afterwards: a copy with its joints unbonded would stay unbonded.
    The placement is the one with the most room; the Interpenetrate
    dialog is where somebody picks another.
    """
    from xtal.analysis import interpenetrate

    try:
        placement = interpenetrate.best(outcome.structure, n)
        array, placement = interpenetrate.build(outcome.structure,
                                                placement)
    except interpenetrate.InterpenetrationError as exc:
        raise MofError(
            f"the framework was built and cannot be interpenetrated "
            f"{n}-fold: {exc}") from None
    array.meta.update(outcome.structure.meta)
    _say(log, f"interpenetrated {n}-fold by {placement.name} "
              f"({placement.relation}); closest contact between "
              f"copies {placement.contact_text()}")
    outcome.structure = array
    outcome.n_atoms = array.n_sites
    outcome.joints *= n
    outcome.closest = closest_contact(array)
    return array


def _stack(framework, request: BuildRequest, log) -> None:
    """Stack a layer net's sheets the way the request says.

    Before anything else reads the geometry, for the reason
    :func:`xtal.mof.layers.restack` gives: the framework, the net and
    the placed blocks all move together, and every step after this
    one reads one of the three.
    """
    from xtal.mof import layers

    spacing = (request.spacing if request.spacing is not None
               else layers.DEFAULT_SPACING)
    offset = request.offset or (0.0, 0.0)
    thickness = layers.restack(framework, spacing, offset,
                               request.repeat)
    # The thickness is said every time rather than past a threshold:
    # 3.0 A of paddlewheel at a 3.4 A spacing is two sheets 0.4 A
    # apart, and no cutoff for "too close" would be anybody's but
    # ours.  The closest contact in the verdict is the measurement.
    _say(log, f"stacked the layers {spacing:.3f} A apart"
              + (f", each offset {offset[0]:g}, {offset[1]:g} over "
                 f"the last" if any(offset) else ", eclipsed")
              + f"; one layer is {thickness:.2f} A thick")


def _build(topology, node_bbs, edge_bbs, log, repeat=(1, 1, 1),
           orientation="consistent"):
    """The build, in one pass or in two, with PORMAKE imported at the
    point of use.

    **Pass 1 is today's call and returns there**, and that is what
    makes "nothing regresses" structural rather than argued: a build
    reaches the second pass only when the user asked for a rule other
    than ``as-found`` *and* some connection point has a frame to
    agree about -- several atoms, or the plane of one
    (:func:`_presents_face`).

    Pass 2 is the same builder, the same blocks and the same net with
    the node permutations pinned -- ``make_bbs_by_type`` and
    ``Builder.build(permutations=...)``, both public API, no vendored
    file edited.  What pass 1 is for, then, is two things it is the
    only source of: the net after relaxation, which is the geometry
    the chosen orientations will actually sit on, and whatever block
    it quietly mirrored at ``builder.py:313``, which pass 2 would
    otherwise place the wrong way round with nothing saying so.  And
    it is the yardstick: a pass 2 whose blocks fit their slots worse
    than pass 1's by more than :data:`xtal.mof.orient.FIT_SLACK` is
    thrown away, and pass 1 comes back.
    """
    _say(log, "loading PORMAKE")
    pormake = import_pormake()
    # By path rather than through ``pormake.Database``, which is a
    # name-to-file lookup over one topology folder and one block
    # folder.  Our catalogue already did that lookup, over as many
    # folders as the user has -- so a block they wrote themselves is
    # built with here for free rather than needing a second database.
    # ``expanded`` is the net's half of that, and the only place a
    # vendored ``Topology`` is made.
    topo = topology.expanded(*repeat)
    nodes = {int(k): pormake.BuildingBlock(str(v.path))
             for k, v in node_bbs.items()}
    edges = {tuple(int(i) for i in k): pormake.BuildingBlock(
        str(v.path)) for k, v in edge_bbs.items()}
    _say(log, f"placing {len(nodes)} node type(s) and "
              f"{len(edges)} linker type(s) on {topo.n_slots} slots")
    builder = pormake.Builder()
    framework = builder.build_by_type(
        topology=topo, node_bbs=nodes,
        edge_bbs=edges or None)

    from xtal.mof import orient

    if orientation == orient.AS_FOUND:
        return framework
    # The nodes, and not every block: the choice is of which way round
    # each *node* goes, and a linker with a face between nodes with
    # none -- cds on N307 and E3 -- has nothing here to choose.  The
    # linker still turns about its own axis, later, in `build`.  And
    # the blocks as made, not as placed: a node placed with no linker
    # beside it comes back without its X atoms while still naming
    # them, so N59 on bare pcu has points 20-25 in a block of 20.
    blocks = builder.make_bbs_by_type(topo, nodes, edges or None)
    if not any(_presents_face(blocks[int(slot)])
               for slot in topo.node_indices):
        _say(log, "no connection point of a node here stands for more "
                  "than one atom or presents a face, so there is no "
                  "orientation to choose; keeping the fit")
        return framework

    swapped, unchecked = orient.substitute_mirrored(blocks, framework)
    if swapped:
        _say(log, f"the fit mirrored the block on {len(swapped)} "
                  f"slot(s); carrying that into the second pass")
    if unchecked:
        _say(log, f"{len(unchecked)} slot(s) came back without the "
                  f"atoms that mark where they connect, so whether "
                  f"the fit mirrored them could not be read")
    found = framework.info["permutations"]
    scored: dict = {}
    chosen = orient.choose_permutations(
        framework.info["topology"], blocks, orientation,
        baseline={slot: found[slot] for slot in range(len(found))},
        log=log, trace=scored)
    kept = (scored["found"], scored["edges"])
    framework.info["joint_twist"] = kept
    if all(tuple(chosen[slot]) == tuple(found[slot])
           for slot in chosen):
        # Nothing was strictly better than what the fit already
        # chose, so the second pass is the first one again -- and
        # running it would be a second relaxation of the same cell
        # for the same answer.
        _say(log, "the fit had already put the nodes the best way "
                  "round; keeping it")
        return framework
    turned = builder.build(topo, blocks, permutations=chosen)
    # Pass 2 relaxes the cell again around the new orientations, and
    # nothing in the choice looked at how well the blocks would sit
    # afterwards.  A turn that agrees better across the joints and
    # fits the slots worse is not the better framework.
    before = float(framework.info.get("max_rmsd", 0.0) or 0.0)
    after = float(turned.info.get("max_rmsd", 0.0) or 0.0)
    if after > before + orient.FIT_SLACK:
        _say(log, f"the turned nodes fit their slots worse ({after:.3f} "
                  f"A against {before:.3f}); keeping the fit")
        return framework
    # And a turn that is a tie cannot move the cell.  One that does is
    # the relaxation finding another framework -- or collapsing, which
    # is what a perfect fit in a cell with no room looks like.
    if not orient.same_cell(framework.atoms.cell, turned.atoms.cell):
        was = ", ".join(f"{v:.2f}" for v in framework.atoms.cell.lengths())
        now = ", ".join(f"{v:.2f}" for v in turned.atoms.cell.lengths())
        _say(log, f"the turned nodes relaxed to another cell ({now} A "
                  f"against {was}); keeping the fit")
        return framework
    turned.info["joint_twist"] = (scored["cost"], scored["edges"])
    return turned


# ======================================================================
#  IMPORTING IT
# ======================================================================
#
# **PORMAKE is vendored**, at :mod:`xtal.mof.pormake`, trimmed of
# ``jax``, ``pymatgen`` and ``networkx``.  See
# ``xtal/mof/pormake/PROVENANCE.md`` for what changed and why.
#
# Both of the reasons this function used to be complicated are gone
# with them.  The import cost ten seconds warm and half a minute cold,
# and that was ``jax`` and ``pymatgen`` starting up, not PORMAKE; what
# is left is twelve modules over ``ase``, measured at 0.33 s cold in a
# fresh interpreter.  And it
# opened ``runtime.log`` in the current directory, in mode ``"w"``, at
# import -- somebody's home folder -- which took a swapped-out
# ``logging.FileHandler`` to contain and is now simply not done: see
# the note in ``pormake/log.py``.
#
# What remains is worth keeping.  The lock, because ``_rewire`` must
# happen exactly once and an import races on nothing else; and the
# rewiring itself, because PORMAKE's logger is how the builder reports
# what it did -- and, in one case, the *only* place it reports that a
# CIF was written and then deleted.

_LOCK = threading.Lock()

#: The build currently listening to PORMAKE's logger, or ``None``.
#: One build at a time, which is what the shell already enforces.
_listening = None


class _Forwarder(logging.Handler):
    """PORMAKE's console output, into the run log instead of stdout.

    Its logger prints ``>>> placing edges`` and forty more lines like
    it.  On a command line those are noise interleaved with the
    report; in the window they would go nowhere at all.  In the run
    log they are the trace of what the builder did, next to
    everything else that happened in the same run.

    **The errors are kept as well as forwarded**, and that is not
    tidiness.  ``Framework.write_cif`` catches whatever the write
    raises, deletes the half-written file and reports it *only*
    through this logger -- so a build whose CIF never appeared would
    otherwise fail several lines later on a missing file, with the
    reason nowhere.
    """

    def emit(self, record) -> None:
        listening = _listening
        if listening is None:
            return
        try:
            listening.take(record.levelno, self.format(record))
        except Exception:                       # noqa: BLE001, S110
            pass


def import_pormake():
    """The vendored ``pormake``, with its logger pointed at the run."""
    with _LOCK:
        name = "xtal.mof.pormake"
        if name in sys.modules:
            return sys.modules[name]
        import xtal.mof.pormake as pormake
        _rewire()
        return pormake


def _rewire() -> None:
    """Take PORMAKE's own handlers off its logger and put ours on.

    Closing them is what lets the temporary directory above go away:
    a file handler holds its file open, and on Windows an open file
    cannot be removed at all.
    """
    from xtal.mof.pormake.log import logger

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    forwarder = _Forwarder(logging.INFO)
    forwarder.setFormatter(logging.Formatter("pormake: %(message)s"))
    logger.addHandler(forwarder)


class _Logging:
    """PORMAKE's log lines going to this run's log, and no further."""

    def __init__(self, log):
        self.log = log
        self.errors: list[str] = []

    def take(self, level: int, text: str) -> None:
        if level >= logging.ERROR:
            self.errors.append(text)
        _say(self.log, text)

    @property
    def failure(self) -> str:
        return self.errors[0] if self.errors else ""

    def __enter__(self):
        global _listening
        _listening = self
        return self

    def __exit__(self, *_exc):
        global _listening
        _listening = None
        return False


def _resolve(request: BuildRequest, catalog: Catalog):
    """The topology and the blocks, checked against the slots.

    The check is the point: a block goes in a slot only when it has
    exactly as many connection points as the slot demands, and saying
    so here gives a sentence naming both instead of an assertion
    inside PORMAKE's locator.
    """
    topology = catalog.topology(request.topology)
    try:
        slots = topology.slots()
    except (CatalogError, ValueError) as exc:
        raise MofError(
            f"{topology.name}: the slots of this net cannot be worked "
            f"out from its file ({exc})") from None
    nodes, edges = {}, {}
    for slot in slots:
        name = request.block_for(slot)
        if not name:
            if slot.is_edge:
                continue            # no linker is a legitimate answer
            raise MofError(
                f"{topology.name} has a {slot.coordination}-connected "
                f"node slot ({slot.label}) with nothing in it")
        block = catalog.building_block(name)
        if block.n_connections != slot.coordination:
            raise MofError(
                f"{block.name} has {block.n_connections} connection "
                f"point(s) and {slot.label.lower()} needs "
                f"{slot.coordination}")
        (edges if slot.is_edge else nodes)[slot.key] = block
    if not topology.is_layer:
        asked = [what for what, value in
                 (("an interlayer spacing", request.spacing),
                  ("a stacking offset", request.offset))
                 if value is not None]
        if asked:
            raise MofError(
                f"{topology.name} is periodic in three directions, so "
                f"it has no layers to stack and {' or '.join(asked)} "
                f"means nothing on it; that is for a layer net, such "
                f"as hcb, hxl, sql or kgm")
    return topology, nodes, edges


# ======================================================================
#  THE NET, DRAWN ON WHAT CAME BACK
# ======================================================================

def draw_net(structure, framework) -> int:
    """Put the net's edges on the framework as topology bonds.

    A vertex has to be an *atom*, because that is what a bond joins,
    so each node slot is represented by the atom of its own block
    nearest that block's centroid -- which PORMAKE defines as the mean
    of the connection points and is the point it aligned with the
    slot.  For a metal node that is the metal.

    The image comes from the net and not from the geometry, and it has
    to: two nodes joined through a linker are twenty Angstrom apart,
    and there is no distance at which "the same cell or the next one"
    could be guessed from their coordinates.

    Returns how many edges were drawn.
    """
    topology = framework.info["topology"]
    blocks = framework.info["located_bbs"]
    representative = _representatives(topology, blocks)
    # The net's image joins two *slots*; the bond joins two atoms, and
    # an atom need not be in the cell its slot is in -- a metal a
    # hair past a face is written wrapped to the far side.  So each
    # end carries the whole-cell offset from its atom to its slot.
    # With one vertex, as pcu has, both ends carry the same offset and
    # it cancels, which is how this went unseen until a net was
    # repeated: pcu x 2 drew thirteen of its 24 edges a cell long.
    slots = topology.atoms.get_scaled_positions()
    sites = np.asarray(structure.frac, dtype=float)
    offset = {slot: np.rint(slots[slot] - sites[atom]).astype(int)
              for slot, atom in representative.items()}
    drawn = 0
    for i, j, image in _edges_of(topology):
        if i not in representative or j not in representative:
            continue                            # pragma: no cover
        image = tuple(int(v) for v in
                      np.asarray(image) + offset[j] - offset[i])
        if structure.add_bond(Bond(i=representative[i],
                                   j=representative[j],
                                   image=image, kind=TOPOLOGY)):
            drawn += 1
    return drawn


def bond_joints(structure, framework) -> tuple[int, float]:
    """Bond the joints PORMAKE made between one block and the next.

    A framework is blocks placed on a net and then *joined*: the
    connection points are fused and the bond that replaces them is the
    node-to-linker or node-to-node join.  Every bond inside a block
    arrives at a chemical length and perception finds it; a joint does
    not have to.  A carboxylate onto a metal, a nitrogen onto a zinc,
    a block whose connection points were written a little long -- the
    join can be well past any distance criterion, and the framework
    then opens with the linker floating unbonded beside the node it was
    built onto, which is the one bond in the structure that nobody
    would think to draw by hand.

    So the joints are stored as the user's own bonds, from what the
    builder did rather than from a distance: PORMAKE knows exactly
    which pairs it fused, and a bond that is *explicit* survives
    Recalculate Bonds and never has to answer for its length.

    **A joint is a bond the joining step made, not a bond between two
    blocks**, and the difference is a whole class of framework.  A net
    with one node slot and no linker -- pcu on N59 -- joins every node
    to *its own periodic image*, so both ends of the join are the same
    block and an inter-block test finds nothing to bond.  What
    separates a join from chemistry is that the blocks' own bond lists
    do not contain it, which is true in both cases and is what this
    subtracts.

    **A connection point may stand for several atoms**, and then one
    joint is several bonds.  The framework's own bond list cannot say
    so -- ``builder.py:644-658`` keeps one partner per point -- so
    those are enumerated instead, by :func:`_joint_bonds`, and
    appended to what the diff above found.

    Returns ``(how many were added, the longest joint bond)``.  The
    length is a measurement of the fit that nothing else reports: the
    blocks' RMSD says how well each one sits on its slot and says
    nothing about whether the two ends of a joint met.
    """
    blocks = framework.info["located_bbs"]
    inside = _intra_block_bonds(blocks)
    known = _block_of_atoms(blocks)
    labels = {site.label: index
              for index, site in enumerate(structure.sites)}
    frac = np.asarray(structure.frac, dtype=float)
    symbols = framework.atoms.symbols
    fresh, seen = [], {b.key(structure.space_group)
                       for b in structure.bonds}
    made, owned = ((), set())
    if any(_is_polydentate(block) for block in blocks):
        made, owned = _joint_bonds(framework, blocks)

    def take(i: int, j: int) -> None:
        """One bond between two framework atoms, if it is new."""
        # By label rather than by position.  The CIF is written in the
        # framework's own atom order and read back in it, and the
        # labels say so -- but the mapping is what this depends on, and
        # a reader that ever reorders should fail to find an atom
        # rather than bond the wrong one.
        ends = (labels.get(f"{symbols[i]}{i}"),
                labels.get(f"{symbols[j]}{j}"))
        if None in ends:                            # pragma: no cover
            return
        a, b = ends
        image = tuple(int(v) for v in np.round(frac[a] - frac[b]))
        bond = Bond(a, b, image)
        key = bond.key(structure.space_group)
        if key in seen:
            return
        seen.add(key)
        fresh.append(bond)

    for i, j in framework.bonds:
        i, j = int(i), int(j)
        if i not in known or j not in known:        # pragma: no cover
            continue
        pair = (min(i, j), max(i, j))
        if pair in inside:
            continue
        if pair in owned:
            # A joint the enumeration accounts for is the
            # enumeration's, whole.  PORMAKE bonds one pair of its
            # members and which pair is an accident, so taking this
            # one as well is how a bidentate joint gets three bonds.
            continue
        take(i, j)

    longest = 0.0
    for i, j, reach in made:
        take(i, j)
        longest = max(longest, reach)
    if fresh:
        # One change and not one per bond: every add drops the P1
        # expansion, and a framework re-expanded once per joint is the
        # stall that `set_bonds` exists to avoid.
        structure.set_bonds(list(structure.bonds) + fresh)
    return len(fresh), longest


def _is_polydentate(block) -> bool:
    """Whether any connection point of this placed block stands for
    more than one atom."""
    if block is None or block.bonds is None:
        return False
    from xtal.mof.attach import members_of

    members = members_of(block.connection_point_indices, block.bonds)
    return any(len(found) > 1 for found in members.values())


def _presents_face(block) -> bool:
    """Whether a placed block has a frame to agree about at any of its
    connection points -- several atoms, or the plane of one
    (:func:`xtal.mof.attach.presents_face`).  What decides whether a
    build has an orientation to choose; what decides whether it has
    joints to bond is :func:`_is_polydentate`, and a face is never
    that."""
    if block is None or block.bonds is None:
        return False
    from xtal.mof.attach import presents_face

    return presents_face(block.connection_point_indices, block.bonds,
                         block.atoms.get_positions())


def _intra_block_bonds(blocks) -> set[tuple[int, int]]:
    """Every bond a placed block brought with it, in framework indices.

    A block's own bond list is in its own atom numbering and includes
    its connection points; the framework's is the blocks concatenated
    with those points taken out.  So each block's bonds are carried
    over by the same walk :func:`_block_of_atoms` makes -- position
    among the kept atoms, plus where the block starts -- and the bonds
    that touched an ``X`` are dropped, because the atom on that end is
    not in the framework to name.

    What is left over when these are subtracted from the framework's
    bonds is exactly what the joining step added.  See
    :func:`bond_joints`.
    """
    starts, kept = _framework_indices(blocks)
    out: set[tuple[int, int]] = set()
    for slot, block in enumerate(blocks):
        if block is None:
            continue
        for u, v in np.asarray(block.bonds, dtype=int).reshape(-1, 2):
            a = kept.get(starts[slot] + int(u))
            b = kept.get(starts[slot] + int(v))
            if a is not None and b is not None:
                out.add((min(a, b), max(a, b)))
    return out


def _framework_indices(blocks):
    """``(starts, kept)`` -- the one walk over the placed blocks.

    ``starts[slot]`` is where that block's atoms begin in the
    concatenated numbering PORMAKE's *own* bond list is written in --
    connection points included, empty slots counted as nothing --
    and ``kept`` maps each of those indices that survives to the
    framework index it becomes, the connection points having been
    taken out.  It is PORMAKE's ``index_offsets`` and ``new_indices``,
    recomputed rather than read, because neither is put in ``info``.

    One walk and not three.  :func:`_intra_block_bonds`,
    :func:`_block_of_atoms` and :func:`_joints_of` each need a slice
    of it, and three private copies of the same arithmetic is exactly
    the drift the comment on :func:`_representatives` warns about --
    with the difference that a drift here bonds the wrong pair of
    atoms rather than failing to find one.
    """
    starts: list[int] = []
    kept: dict[int, int] = {}
    start = count = 0
    for block in blocks:
        starts.append(start)
        if block is None:
            continue
        for local, symbol in enumerate(
                block.atoms.get_chemical_symbols()):
            if symbol != CONNECTION:
                kept[start + local] = count
                count += 1
        start += block.n_atoms
    return starts, kept


def _block_of_atoms(blocks) -> dict[int, int]:
    """Framework atom index -> the slot whose block it came from.

    The framework's atoms are the located blocks concatenated in slot
    order with the connection points removed, so this is arithmetic
    rather than a search -- the same ordering :func:`_representatives`
    relies on, shared so that the two cannot drift apart.
    """
    starts, kept = _framework_indices(blocks)
    out: dict[int, int] = {}
    for slot, block in enumerate(blocks):
        if block is None:
            continue
        for local in range(block.n_atoms):
            index = kept.get(starts[slot] + local)
            if index is not None:
                out[index] = slot
    return out


def edge_ends(topology) -> dict:
    """Edge slot -> the two node slots it joins, and which of each
    node's edges this is.

    ``{edge slot: ((node slot, ordinal), (node slot, ordinal))}``, out
    of the topology alone -- no blocks, no permutations, nothing
    placed.  The ordinal is a position in the node's own neighbour
    list, and a slot's permutation is exactly what turns one into a
    connection point; keeping the two apart is what lets
    :mod:`xtal.mof.orient` try two dozen permutations per slot against
    one net without re-deriving which edge is which every time.

    ``builder.py``'s ``find_matched_atom_indices`` (``:441-469``)
    restated: an edge records each neighbour as a displacement, so the
    edge that leaves a node towards this one is the one whose
    displacement cancels the edge's own, to that function's own
    0.01 A.
    """
    out: dict[int, tuple[tuple[int, int], tuple[int, int]]] = {}
    for slot in topology.edge_indices:
        slot = int(slot)
        neighbours = topology.neighbor_list[slot]
        if len(neighbours) != 2:                    # pragma: no cover
            continue
        ends = []
        for end in neighbours:
            ordinal = _ordinal_of(topology, int(end.index), end)
            if ordinal is None:                     # pragma: no cover
                break
            ends.append((int(end.index), ordinal))
        if len(ends) == 2:
            out[slot] = (ends[0], ends[1])
    return out


def _ordinal_of(topology, node, end):
    """Which of ``node``'s own edges leaves it towards this edge."""
    reach = np.asarray(end.distance_vector, dtype=float)
    for ordinal, neighbour in enumerate(topology.neighbor_list[node]):
        total = np.asarray(neighbour.distance_vector,
                           dtype=float) + reach
        if float(np.linalg.norm(total)) < 0.01:
            return ordinal
    return None                                     # pragma: no cover


def edge_axis(topology, edge) -> np.ndarray:
    """The direction of one edge, from its first end to its second.

    Not normalised here, and not needed to be: what reads it is
    :func:`xtal.mof.attach.lateral`, which takes the unit vector for
    itself.
    """
    first, second = topology.neighbor_list[int(edge)]
    return (np.asarray(second.distance_vector, dtype=float)
            - np.asarray(first.distance_vector, dtype=float))


def point_at(block, permutation, ordinal) -> int:
    """Which connection point of a placed block one of its edges took.

    The slot's permutation is the whole of the mapping: PORMAKE's
    locator hands back the order its connection points were matched
    to the slot's neighbours in, and ``ordinal`` is a position in that
    neighbour list.
    """
    points = np.asarray(block.connection_point_indices)
    return int(points[np.asarray(permutation)[int(ordinal)]])


def fused_points(topology, blocks, permutations):
    """Every pair of connection points the builder fused, as
    ``((slot, point), (slot, point))`` in each block's own numbering.

    These are **enumerated and not read back**, and that is the whole
    reason this function exists.  ``builder.py:644-658`` collapses
    each connection point to a single partner --
    ``X_neighbor_list[i] = j``, a scalar into a list-valued map, so
    whichever partner was seen last wins -- and then makes one bond
    per fused pair.  A bidentate end therefore arrives with one bond
    where it needs two, and the framework's bond list is missing them
    rather than holding them wrongly, so no amount of reading it
    recovers them.  The vendored file is not edited
    (``xtal/mof/pormake/PROVENANCE.md``); what it *did* write is
    still taken, and this adds the rest.

    An edge slot with a block yields two fused pairs, one per end; an
    empty edge slot yields one, node point to node point, which is
    the linkerless net :func:`bond_joints` is already careful about.
    """
    out = []
    for edge, ends in edge_ends(topology).items():
        ends = tuple(
            (node, point_at(blocks[node], permutations[node], ordinal))
            for node, ordinal in ends)
        block = blocks[edge]
        if block is None:
            out.append(ends)
            continue
        points = np.asarray(block.connection_point_indices)[
            permutations[edge]]
        # Strict: an edge slot is two-connected and `_resolve`
        # refuses a block that does not match its slot before the
        # build starts, so a mismatch here is a broken guarantee
        # rather than a shape to tolerate -- and tolerating it would
        # silently bond one end of a joint and not the other.
        out.extend(((edge, int(point)), end)
                   for point, end in zip(points, ends, strict=True))
    return out


def _joints_of(topology, blocks, permutations):
    """:func:`fused_points`, in the concatenated numbering of
    :func:`_framework_indices` -- which is the numbering PORMAKE
    writes its own bond list in."""
    starts, _kept = _framework_indices(blocks)
    return [(starts[a[0]] + a[1], starts[b[0]] + b[1])
            for a, b in fused_points(topology, blocks, permutations)]


def _joint_bonds(framework, blocks):
    """``(chosen, owned)`` for every joint this can account for.

    ``chosen`` is ``(atom, atom, distance)``, one per pair of members
    the assignment made; ``owned`` is every member-to-member pair of
    every enumerated joint, whether it was chosen or not.

    The second is what stops a bidentate joint arriving with three
    bonds.  PORMAKE makes one bond per joint and *which* one is an
    accident of iteration order -- on MFU-4l over ``pcu``, three of
    its six are the pairing this rejects -- so a joint the
    enumeration knows about is the enumeration's whole answer, and
    :func:`bond_joints` drops what the builder made of it rather than
    adding to it.  For a monodentate joint the two agree atom for
    atom, so nothing is dropped and nothing changes.

    **Every member arrives bonded**, whatever the denticities are.
    The pairing is a rectangular assignment on distance, which covers
    the smaller end; a member of the larger end that the assignment
    left over then takes its nearest partner on the other side.  A
    bidentate end meeting a monodentate one is a real joint and
    leaving half of it floating would be the same defect this exists
    to repair, one size down.

    The geometry is the **placed blocks'**, not the framework's: a
    framework wraps its atoms into the cell (``framework.py:76``) and
    a wrapped block is in pieces.  The blocks are whole, but two of
    them need not be in the same cell -- half of MFU-4l's joints on
    ``pcu`` are a full 16.136 A apart as placed -- so the vector
    between two *different* blocks is taken at its minimum image
    under the framework's own cell.  Without that the pairing is
    decided on distances of 14.7 A that differ in the second decimal
    place, and the number reported alongside is not a bond length.
    """
    from scipy.optimize import linear_sum_assignment

    topology = framework.info["topology"]
    permutations = framework.info["permutations"]
    starts, kept = _framework_indices(blocks)
    owner, place = _placed_atoms(blocks, starts, kept)
    cell = np.asarray(framework.atoms.cell, dtype=float)
    inverse = np.linalg.inv(cell)

    chosen, owned = [], set()
    for left, right in _joints_of(topology, blocks, permutations):
        here, there = (_members_at(blocks, starts, kept, owner, point)
                       for point in (left, right))
        if not here or not there:
            continue
        owned.update((min(a, b), max(a, b))
                     for a in here for b in there)
        offset = (place[here][:, None, :]
                  - place[there][None, :, :])
        frac = offset @ inverse
        cost = np.linalg.norm(
            (frac - np.round(frac)) @ cell, axis=-1)
        rows, cols = linear_sum_assignment(cost)
        pairs = set(zip(rows.tolist(), cols.tolist(), strict=True))
        # The assignment covers the smaller end; whatever the larger
        # end has left over takes its nearest partner, so that every
        # member of a joint arrives bonded whatever the denticities.
        for row in set(range(len(here))) - {r for r, _c in pairs}:
            pairs.add((row, int(np.argmin(cost[row]))))
        for col in set(range(len(there))) - {c for _r, c in pairs}:
            pairs.add((int(np.argmin(cost[:, col])), col))
        chosen.extend((here[row], there[col], float(cost[row, col]))
                      for row, col in sorted(pairs))
    return chosen, owned


def _placed_atoms(blocks, starts, kept):
    """``(owner, place)`` -- which slot each concatenated index is in,
    and where each framework atom was *placed*, before wrapping.

    ``place`` is indexed by framework atom, so a list of members is a
    fancy index into it and the distances between two ends of a joint
    are one array operation.

    ``owner`` runs to each block's *declared* extent rather than to
    the atoms it still has, and the difference is one upstream
    accident.  The framework's atoms are built as
    ``sum(bb_atoms_list[1:], bb_atoms_list[0])`` and its connection
    points then deleted; where exactly one slot is filled -- a net
    with no linker -- that sum **is** its one argument, so the delete
    lands on the located block as well and it comes back short of
    every ``X`` it had.  ``bonds`` and ``connection_point_indices``
    still name them, which is what makes the joint recoverable at all,
    so the extent is taken from those rather than from ``n_atoms``.
    With two or more filled slots the sum copies and the two agree.
    """
    owner: dict[int, int] = {}
    place = np.zeros((len(kept), 3), dtype=float)
    for slot, block in enumerate(blocks):
        if block is None:
            continue
        positions = np.asarray(block.atoms.get_positions(),
                               dtype=float)
        points = np.asarray(block.connection_point_indices, dtype=int)
        extent = max(int(block.n_atoms),
                     int(points.max()) + 1 if points.size else 0)
        for local in range(extent):
            owner[starts[slot] + local] = slot
            index = kept.get(starts[slot] + local)
            if index is not None and local < len(positions):
                place[index] = positions[local]
    return owner, place


def _members_at(blocks, starts, kept, owner, point) -> list[int]:
    """The framework indices of the atoms one fused point stands for.

    Empty when the block never wrote its bonds, which is the one case
    where nothing here can say what the point stood for -- the joint
    is then left to whatever PORMAKE made of it.

    The whole block's connection points are handed to
    :func:`~xtal.mof.attach.members_of` and not just this one, so that
    a bond onto another point is recognised as such instead of being
    counted as an atom this one stands for.
    """
    from xtal.mof.attach import members_of

    slot = owner[point]
    block = blocks[slot]
    local = point - starts[slot]
    members = members_of(block.connection_point_indices,
                         block.bonds).get(local, ())
    found = [kept.get(starts[slot] + int(m)) for m in members]
    return [index for index in found if index is not None]


def _representatives(topology, blocks) -> dict[int, int]:
    """Node slot -> the index, in the framework, of its vertex atom.

    The framework's atoms are the located blocks concatenated in slot
    order with the connection points removed, which is what makes the
    index arithmetic rather than a search.  Stated here because it is
    PORMAKE's internal ordering and nothing enforces it from outside;
    the net check downstream is what would notice if it changed.

    **Which atom stands for the slot is decided by the slot, not by
    the block.**  The topology's own atoms are in the framework's
    frame -- the builder relaxes the cell and puts both in it -- so
    the vertex is the block's atom nearest the point the block was
    placed on.  For a metal node that is the metal.  The block's own
    ``centroid`` would say the same thing and is not usable: it is the
    mean of the connection points, and a framework built with no
    linker has had them consumed by the bonds between the nodes.
    """
    out: dict[int, int] = {}
    slots = np.asarray(topology.atoms.get_positions(), dtype=float)
    nodes = {int(s) for s in topology.node_indices}
    owner = _block_of_atoms(blocks)
    starts: dict[int, int] = {}
    for atom in sorted(owner):
        starts.setdefault(owner[atom], atom)
    for slot, block in enumerate(blocks):
        if block is None or slot not in nodes:
            continue
        kept = [i for i, symbol in
                enumerate(block.atoms.get_chemical_symbols())
                if symbol != CONNECTION]
        if not kept:                                # pragma: no cover
            continue
        positions = block.atoms.get_positions()[kept]
        nearest = int(np.argmin(
            ((positions - slots[slot]) ** 2).sum(axis=1)))
        out[slot] = starts[slot] + nearest
    return out


def _edges_of(topology) -> list[tuple[int, int, tuple[int, int, int]]]:
    """Every edge of the net, as ``(node slot, node slot, image)``.

    An edge slot sits between exactly two node slots and PORMAKE
    records each neighbour as a minimum-image displacement rather than
    as a cell offset, so the offset is recovered by taking the
    displaced point back to the vertex it is a copy of.  The edge's
    image is the difference of the two, which is what makes it
    independent of where the edge centre itself was put.
    """
    frac = topology.atoms.get_scaled_positions()
    inverse = np.linalg.inv(np.asarray(topology.atoms.cell))
    out = []
    for slot in topology.edge_indices:
        ends = []
        for neighbour in topology.neighbor_list[int(slot)]:
            index = int(neighbour.index)
            displaced = frac[int(slot)] + (
                np.asarray(neighbour.distance_vector) @ inverse)
            ends.append((index,
                         np.round(displaced - frac[index])))
        if len(ends) != 2:                      # pragma: no cover
            continue
        (i, shift_i), (j, shift_j) = ends
        out.append((i, j, tuple(int(v) for v in shift_j - shift_i)))
    return out


def closest_contact(structure) -> float:
    """The shortest distance between two atoms that are not bonded.

    The shortest distance of *any* kind says nothing about a build:
    it is the C-H bond every time, 0.930 A in `MFU4l.cif`'s own
    refinement and 0.930 A in a framework built out of it.  What a
    build whose blocks do not fit shows is atoms that are close and
    **not** joined.  Measured over `resources/samples`: every
    framework there sits between 1.996 A (Ni3(HITP)2) and 2.170 A
    (UiO-66), while `acs` built on `N457` -- blocks that genuinely do
    not fit that net -- sits at 1.662 A.

    No threshold is applied and none is wanted.  The bands are close
    enough that a constant would be a guess, and the number next to
    the fit is what a person needs to judge a build by; ``CFA1.cif``
    and ``Ni2Cl2BTDD.cif`` both answer 0.000 A, which is a fact about
    those files rather than a failure of this one.

    Dummy atoms are held back at the door here as everywhere: a
    connection point sits 0.75 A from the atom it hangs off and would
    otherwise be the answer to this question in every structure.

    ``inf`` when no unbonded pair is within :data:`CONTACT_CUTOFF` at
    all, which is an open framework rather than a good or a bad one.
    """
    from xtal.core import bonding, elements, p1
    from xtal.core.neighbors import neighbor_pairs

    cell = p1.expand(structure)
    pairs = neighbor_pairs(cell.frac, structure.lattice, CONTACT_CUTOFF,
                           min_distance=0.0)
    if not len(pairs):
        return float("inf")
    dummy = np.array([elements.is_dummy(str(e))
                      for e in cell.elements])
    keep = ~(dummy[pairs.i] | dummy[pairs.j])
    bonded = {_contact_key(b.i, b.j, b.image)
              for b in bonding.graph(structure).bonds}
    keep &= np.array([_contact_key(int(i), int(j), im) not in bonded
                      for i, j, im in zip(pairs.i, pairs.j, pairs.image,
                                          strict=True)])
    near = pairs.distance[keep]
    return float(near.min()) if len(near) else float("inf")


def _contact_key(i: int, j: int, image) -> tuple:
    """One name for a pair, whichever end it is described from."""
    image = np.asarray(image, dtype=int)
    if i <= j:
        return (int(i), int(j), tuple(int(v) for v in image))
    return (int(j), int(i), tuple(int(-v) for v in image))


def check_net(structure):
    """What the net drawn on this framework actually is.

    Read back off the structure with the same two functions the Net
    panel uses, so this is a statement about the bonds that are stored
    in the file and not about anything PORMAKE said while writing it.
    """
    from xtal.analysis import net_of, rcsr

    return rcsr.describe(net_of(structure))


# ======================================================================
#  SMALL THINGS
# ======================================================================

def _say(log, text: str) -> None:
    if log is not None:
        log(text)


def _safe(text: str) -> str:
    from xtal.workspace import safe_name

    return safe_name(text, "framework")
