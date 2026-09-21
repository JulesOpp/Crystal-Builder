"""
xtal.modules.net
================
A named RCSR net, drawn, as a registry entry.

The same shape as :mod:`xtal.modules.build` and for the same reason:
it makes a structure out of nothing, so ``needs_structure`` is False
and what it returns opens in a tab of its own.  The geometry is
:mod:`xtal.build.topology`; this file is the entry in the menu and
the sentence that comes back.

**There is nothing optional about it**, which makes it the only
builder here with no ``check``.  PORMAKE needed ``ase``, the molecule
builder needs RDKit, and this needs numpy and a gzipped file that
ships inside the package -- so there is no state in which the entry
is present and greyed out, and inventing one would be a check that
can only ever answer yes.

**No run folder.**  Nothing is left behind: a net somebody asked to
look at is a document, and where it gets saved is theirs to choose.
The same argument :mod:`xtal.modules.build` makes.
"""

from __future__ import annotations

from xtal.build import topology
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param

__all__ = ["PARAMS", "NET", "draw_net", "register"]

PARAMS = (
    Param("net", "Net", kind="text", default="pcu",
          help="The RCSR's own name for it -- pcu, dia, srs, acs, "
               "sod, rht, hcb.  2926 of them can be drawn, the 200 "
               "layers among them; the four with no cell cannot."),
    Param("scale", "Cell scale", kind="float", default=topology.SCALE,
          minimum=1.0, maximum=40.0,
          help="The .cgd cells are normalised so an edge is about one "
               "unit long.  Eight puts the atoms along an edge about "
               "1 A apart, which is what makes the edges read as "
               "rods."),
    Param("beads", "Atoms per edge", kind="int",
          default=topology.BEADS, minimum=2, maximum=24,
          help="Counting the two nodes.  More is a smoother rod and a "
               "bigger structure; the atom next to a node is what a "
               "coordination polyhedron is drawn over, so there has "
               "to be at least one between them."),
)


def draw_net(job) -> JobResult:
    """Draw one net, into a document of its own.

    A name that is not a net, a net with no cell and the one net whose
    edges do not land on it are all *failed runs* rather than crashes
    -- the same answer :mod:`xtal.modules.build` gives a string that
    is not a molecule.
    """
    name = str(job.param("net", "")).strip()
    try:
        structure = topology.by_name(
            name,
            scale=float(job.param("scale", topology.SCALE)),
            beads=int(job.param("beads", topology.BEADS)))
    except topology.NetDrawingError as exc:
        return JobResult.failure(str(exc))
    vertices = sum(1 for site in structure.sites
                   if site.element == topology.NODE_ELEMENT)
    job.say(f"drew {name} from the RCSR")
    return JobResult(
        message=f"{name}: {vertices} vertex site(s), "
                f"{len(structure.sites)} in the asymmetric unit, "
                f"{structure.space_group.hm}",
        structure=structure)


NET = Module(
    name="net",
    label="Net builder",
    description="Draw a named RCSR net -- a vertex is a hydrogen and "
                "an edge is a string of heliums, which is notation "
                "and not chemistry.  It opens in a tab of its own, "
                "with coordination polyhedra ready to draw over the "
                "vertices.",
    order=60,
    provides=frozenset({"structure"}),
    actions=(
        Action(name="draw", label="Draw a net...",
               tip="Draw a named RCSR net; it opens in a new tab",
               kind="build",
               needs_structure=False,
               writes_run_folder=False,
               dialog="net-draw",
               params=PARAMS,
               run=draw_net),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(NET)
