"""
xtal.mof
========
Build a framework from a net, a metal node and a linker.

`PORMAKE <https://github.com/Sangwon91/PORMAKE>`_ does the geometry:
it holds 2399 topologies and 867 building blocks, places a block on
every slot of a net, relaxes the cell and hands back a framework.  We
are not writing a builder.  What is here is the four things that stand
between that and this application, and each is in this package rather
than in :mod:`xtal.modules.mof` because none of them needs a run
folder, a worker thread or a menu:

**Reading the catalogue without importing PORMAKE.**
:mod:`~xtal.mof.catalog`.  PORMAKE is vendored at
:mod:`xtal.mof.pormake` and the ``jax`` and ``pymatgen`` that made
the import cost ten seconds warm and half a minute cold are gone with
it, but the import is still not a thing to do when a dialog opens --
and everything the dialog has to show is in the files themselves.
The topologies are ``.cgd``, which :mod:`xtal.io.cgd` has read since
the RCSR work, and a building block is an XYZ with its connection
points listed on the second line.
So the picker is instant and PORMAKE is imported once, on the worker
thread, by the run that needs it.

**Turning a net into slots to fill.**  A topology decides how many
distinct node slots there are and what coordination number each
demands, and only a block with that many connection points may go in
one.  That is what makes the parameters of this module neither flat
nor static, and it is computed from the ``.cgd`` by
:meth:`~xtal.mof.catalog.Topology.slots`.

**The handover, which is CIF.**  :mod:`~xtal.mof.build`.  Not the ASE
or pymatgen objects PORMAKE works in: the run folder wants the file on
disk anyway, gemmi already reads it, and a translation layer between
three different atom containers is a bug farm with no upside.

**Drawing the net on what came back.**  Also :mod:`~xtal.mof.build`,
and it is the part nothing else in the application does.  PORMAKE
knows exactly which atoms are one node, so the framework can arrive
with its net already drawn as :data:`~xtal.core.structure.TOPOLOGY`
bonds -- which means the Net panel names it the moment the tab opens,
and means the build can be *checked*: :func:`xtal.analysis.net_of` and
the RCSR catalogue answer "what did this actually come out as", and a
build that says **tbo** and produces something that is not tbo says so
in its own report.

**And four blocks of our own.**  :mod:`xtal.mof.library`, read by
:meth:`~xtal.mof.catalog.Catalog.default` beside PORMAKE's 867.  Not
a fifth kind of work so much as the first material the four above
were written for: every connection point of every one of them stands
for *two* atoms, which none of PORMAKE's do, and MFU-4l cannot be
built out of a catalogue where a chelate is one atom.
"""

from xtal.mof.block import (
    BOND_LETTERS,
    CONNECTION_DISTANCE,
    BlockError,
    block_string,
    problems,
    pull_in,
    write_building_block,
)
from xtal.mof.build import (
    BuildRequest,
    MofError,
    build,
    check_net,
    draw_net,
)
from xtal.mof.catalog import (
    BuildingBlock,
    Catalog,
    Slot,
    Topology,
    database_root,
    has_ase,
    installed,
    library_root,
)

__all__ = ["BOND_LETTERS", "BlockError", "BuildRequest",
           "BuildingBlock", "CONNECTION_DISTANCE", "Catalog",
           "MofError", "Slot", "Topology", "block_string", "build",
           "check_net", "database_root", "draw_net", "has_ase",
           "installed", "library_root",
           "problems", "pull_in", "write_building_block"]
