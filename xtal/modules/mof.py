"""
xtal.modules.mof
================
PORMAKE, as a registry entry.

One action: pick a net, a node and a linker and get a framework.
Everything about the run folder, the log, the worker thread and the
Stop button is :mod:`xtal.modules.record` and the shell, written once
in Phase D; everything about topologies, building blocks and the net
that came out is :mod:`xtal.mof`.  What is here is only what is true
of PORMAKE in particular, and there are four things.

**It is not an optional extra any more, and that is the interesting
part.**  ``pip install pormake`` brings ``ase``, ``networkx``,
``pymatgen`` and ``jax[cpu]``: 44 packages and 889 MB against the four
this application installs.  So it was excluded from the bundle, and
the MOF builder was the one feature a packaged user could not have.

It is now **vendored and trimmed**, at :mod:`xtal.mof.pormake` --
``networkx`` was never imported, ``jax`` was one gradient and
``pymatgen`` was one call, and both are gone.  What is left is about
23 MB -- 3 MB of code and database, and ``ase``, which it is written
over -- it ships, and there is nothing for a user to configure.
``xtal/mof/pormake/PROVENANCE.md`` records all of it.

**Nothing here imports it even so.**  :meth:`Module.availability` is
called every time the module tree is rebuilt, and the import still
costs more than a menu should; it happens once, inside
:func:`xtal.mof.build.build`, on the worker thread.  What
:func:`available` checks is the database, which is the only half that
can now go missing.

**Its parameters are not flat, and that is what ``Action.dialog`` is
for.**  How many node slots a build has, and what coordination number
each demands, is decided by the topology -- so the generated form
cannot ask the question and a dialog is opened instead.  The ``run``
callable below still takes plain strings and is still what ``xtal
run`` invokes and what a test calls with no display; only the
*collection* of the parameters is substituted.

**It does not need a structure open, and what it makes is a new
document.**  ``needs_structure = False`` has existed since the
registry was written and this is the first module to use it.

Two of the parameters are directories rather than values, and they are
the whole of "a user's own building block is a folder, not a code
change": PORMAKE's database is a folder of ``.cgd`` nets and a folder
of ``.xyz`` blocks, a block is an XYZ whose connection points are
listed on its second line, and anything dropped in one of these two
folders appears in the picker beside the 867 that shipped.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from xtal.modules.job import JobResult
from xtal.modules.registry import (
    MODULES,
    Action,
    Availability,
    Module,
    Param,
)
from xtal.modules.report import Report, Row, Table
from xtal.mof import Catalog, MofError, database_root, has_ase
from xtal.mof.build import BuildRequest, build

#: What to say when the database is not there.  It ships inside the
#: package, so this is not a missing dependency a user can install --
#: it is a broken installation, and saying so is more use than naming
#: a ``pip`` command that would not help.
MISSING = ("The PORMAKE database of nets and building blocks is "
           "missing from this installation, so there is nothing to "
           "build with")

#: And what to say when ``ase`` is not there.  This one *is* something
#: the user can act on, which is why it is a separate sentence: the
#: vendored PORMAKE is written over ``ase.Atoms`` and
#: ``ase.neighborlist``, and replacing those with this project's own
#: :class:`~xtal.core.structure.Structure` is a much larger piece of
#: work than the trim that brought the builder in.
NEEDS_ASE = ("The MOF builder needs ase -- pip install "
             "'crystal-builder[ase]'")


def available() -> Availability:
    """The registry's answer, consulted every time the tree is built.

    ``find_spec`` and a directory test, and deliberately nothing more:
    this runs on every menu rebuild, and importing PORMAKE to find out
    whether the builder works would freeze the window for seconds to
    answer a question the file system already knows.

    The code is vendored, so it cannot be absent.  Two things beside
    it can be, and they are different answers rather than one wording
    with a hole in it: the nets and blocks, which
    ``packaging/bundle.py`` has to name and a wheel has to carry, and
    which a user cannot install; and ``ase``, which they can.
    """
    root = database_root()
    if root is None:
        return Availability(False, MISSING)
    if not has_ase():
        return Availability(False, NEEDS_ASE)
    return Availability(True, str(root))


# ======================================================================
#  PARAMETERS
# ======================================================================

PARAMS = (
    Param("topology", "Topology", kind="text", default="pcu",
          help="The net to build on, by its RCSR name -- pcu, tbo, "
               "soc.  2399 of them ship with PORMAKE."),
    Param("nodes", "Node building blocks", kind="text",
          help="Which block goes in which node slot: 'N59' when the "
               "net has one kind of node, or '0=N19,1=N59' when it "
               "has more.  A block fits a slot only when it has as "
               "many connection points as the slot is coordinated."),
    Param("edges", "Linkers", kind="text",
          help="Which linker goes on which kind of edge: 'E32', or "
               "'0-0=E32,0-1=E14'.  Left empty the nodes are joined "
               "directly, which is what PORMAKE builds for a net with "
               "no linker in it."),
    Param("topology_dir", "Extra topologies", kind="path",
          help="A folder of your own .cgd nets, read alongside the "
               "ones PORMAKE ships"),
    Param("bb_dir", "Extra building blocks", kind="path",
          help="A folder of your own .xyz building blocks, whose "
               "connection points are listed on the second line"),
)


def catalog_for(job) -> Catalog:
    """The database this run is building out of.

    The two folders are parameters rather than a constant so that the
    same run is reproducible from a command line, and so that a saved
    parameter set records which blocks it was built from.

    **The workspace's own blocks are read as well, and that is not a
    convenience.**  A block drawn on a slot row is written into
    ``<workspace>/blocks/`` -- see
    :meth:`xtalapp.dialogs.mof_build.MofBuildDialog._draw_into` -- and
    the dialog reads it there, offers it and selects it.  The run did
    not, so pressing Build on the block you had just drawn failed with
    "no building block called ...": the one folder the answer was
    certain to be in was the one nobody looked in.  It is found by
    walking up from the run folder rather than passed in, so ``xtal
    run`` inside a workspace builds with the same blocks the window
    does, and a run with no workspace still has none to find.
    """
    blocks = []
    if job.folder is not None:
        from xtal.workspace import Workspace

        workspace = Workspace.find(job.folder.path)
        if workspace is not None:
            blocks.append(workspace.blocks)
    return Catalog.default(str(job.param("topology_dir", "") or ""),
                           str(job.param("bb_dir", "") or ""),
                           also_blocks=tuple(blocks))


# ======================================================================
#  RUNNING IT
# ======================================================================

def _prepare(job):
    """Where the CIF goes, and what to clean up afterwards.

    The same rule as Zeo++: a run with no workspace still answers,
    into a temporary directory that goes away afterwards, because the
    answer is a framework in a tab and not only a file on disk.  The
    status line says the files were not kept.
    """
    if job.folder is not None:
        return Path(job.folder.path), None
    holder = tempfile.TemporaryDirectory(prefix="pormake-")
    job.note("no workspace open, so this build is happening in a "
             "temporary folder and its CIF will not be kept")
    return Path(holder.name), holder


def build_framework(job) -> JobResult:
    """Build one framework from a net, a node and a linker.

    Cancellation is checked either side of the build and not during
    it: PORMAKE places every block, relaxes the cell and returns in
    one call with nothing to poll, and a Stop that pretends to
    interrupt it would be a lie.  The builds that take long enough to
    want stopping are the ones with a thousand slots, and those are
    minutes rather than hours.
    """
    directory, holder = _prepare(job)
    try:
        request = BuildRequest.parse(job.param("topology", ""),
                                     job.param("nodes", ""),
                                     job.param("edges", ""))
        job.say(f"PORMAKE: building {request.title()}")
        job.check()
        # ``say`` for our own five lines, ``note`` for PORMAKE's
        # forty: the first are what somebody watching a slow build
        # wants on the status bar, the second are the trace that
        # belongs in the run folder and nowhere else.
        outcome = build(request, directory, catalog_for(job),
                        log=job.say, trace=job.note)
        if job.cancelled:
            return JobResult.stopped("stopped after the build "
                                     "finished")
        artifacts = ((outcome.cif,) if job.folder is not None
                     else ())
        report = _report(outcome)
        job.note("")
        job.note(report.as_text())
        return JobResult(
            message=f"{outcome.n_atoms} atoms; {outcome.verdict()}",
            structure=outcome.structure, report=report,
            artifacts=artifacts,
            detail="" if outcome.net_agrees else outcome.verdict())
    except MofError as exc:
        # A request that does not describe a buildable framework is a
        # failed run and not a crash: it is nearly always a block in
        # a slot it does not fit, and the sentence names both.
        return JobResult.failure(str(exc))
    finally:
        if holder is not None:
            holder.cleanup()


def _report(outcome) -> Report:
    """What was built, and whether it is what was asked for."""
    topology, nodes, edges = outcome.request.spelled()
    structure = outcome.structure
    a, b, c, alpha, beta, gamma = structure.lattice.parameters
    what = Table(
        title="What was built",
        rows=(
            Row("Topology", topology, "", outcome.asked),
            Row("Node blocks", nodes or "none"),
            Row("Linkers", edges or "none -- nodes joined directly"),
            Row("Atoms", str(outcome.n_atoms)),
            Row("Joints bonded", str(outcome.joints), "",
                "the node-to-linker and node-to-node joins, stored as "
                "bonds -- a join can be longer than any distance "
                "criterion would draw"),
            Row("Cell", f"{a:.3f} x {b:.3f} x {c:.3f} A",
                "", f"{alpha:.2f}, {beta:.2f}, {gamma:.2f} deg"),
        ))
    fit = Table(
        title="How well the blocks fit the net",
        rows=(
            Row.number("Largest RMSD", outcome.max_rmsd, "A",
                       "how far one block's connection points sit "
                       "from the directions the net asked for -- the "
                       "worst slot in the framework", "", decimals=4),
            Row.number("Mean RMSD", outcome.mean_rmsd, "A", "", "",
                       decimals=4),
            Row.number("Cell relaxation", outcome.objective, "", "",
                       "", decimals=4),
        ),
        note="PORMAKE's own numbers.  They say whether the geometry "
             "is strained; they say nothing about the net, which is "
             "the next table.")
    return Report(
        title=f"{outcome.request.title()}",
        blocks=(what, fit, _check(outcome)),
        note=outcome.verdict())


def _check(outcome) -> Table:
    """The net read back off the framework, named against the RCSR.

    This is the row the roadmap is really after: the build is asked
    for a net by name and the answer is computed from the bonds that
    ended up in the structure, by the same two functions the Net panel
    uses.  A build that says *tbo* and produces something that is not
    tbo says so here.
    """
    identified = outcome.identified
    rows = [Row("Asked for", outcome.asked, "",
                "the topology PORMAKE was given"),
            Row("Built", identified.headline() if identified
                else "could not be read", "",
                "the net drawn on the framework, identified against "
                "the RCSR")]
    if identified and identified.parts:
        for line in identified.parts[0].invariant_lines():
            label, _, value = line.partition("  ")
            rows.append(Row(label.strip(), value.strip()))
    return Table(
        title="The net that came out",
        rows=tuple(rows),
        note="The framework arrives with its net already drawn, so "
             "the Net panel names it without anything being clicked "
             "-- and so this check is over the bonds in the file "
             "rather than over anything PORMAKE said.")


# ======================================================================
#  THE MODULE
# ======================================================================

PORMAKE = Module(
    name="mof",
    label="MOF builder",
    description="Build a framework from a topology, a metal node and "
                "a linker, with PORMAKE.  The result opens in a new "
                "tab with its net already drawn.",
    order=40,
    check=available,
    provides=frozenset({"structure", "table"}),
    actions=(
        Action(name="build", label="Build a framework...",
               tip="Pick a net, a node and a linker; the framework "
                   "opens in a new tab",
               kind="build",
               needs_structure=False,
               dialog="mof-build",
               params=PARAMS,
               run=build_framework),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(PORMAKE)
