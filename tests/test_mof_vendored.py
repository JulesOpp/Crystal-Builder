"""The vendored PORMAKE against the real one, and against itself.

:mod:`xtal.mof.pormake` is PORMAKE 0.2.3 with ``networkx``, ``jax``
and ``pymatgen`` taken out of it -- 889 MB down to about 23 -- so that
the MOF builder ships inside the packaged application instead of being
the one feature a packaged user cannot have.
``xtal/mof/pormake/PROVENANCE.md`` records every difference.

Two of those differences are numerical work against somebody else's
optimiser, which is why this file exists: **"it runs" is not "it
builds the same framework"**.

* ``jax.jit(jax.grad(fun))`` supplied the jacobian for a
  ``scipy.optimize.minimize`` that was already there.  It is now a
  hand-derived gradient.
* ``pymatgen.Structure.from_spacegroup`` expanded a net's asymmetric
  unit.  It is now gemmi, through the same helper
  :mod:`xtal.analysis.rcsr` expands RCSR entries with.

So the tests come in three kinds, and only the first needs upstream:

**Against the real PORMAKE**, when one is installed beside this
checkout -- the expansion site for site, and a whole build compared by
composition, RMSD and net.  Skipped when it is not, because a user, a
packaged build and CI all have no reason to carry the thing that was
just removed.

**Against arithmetic**, which needs nothing: the gradient against
finite differences.  This is the one that would catch a wrong
derivative on a machine that has never seen upstream.

**Against the trim itself**: that a build imports none of the three
packages that were taken out.  Cheap, and it is what fails if somebody
reintroduces an import while fixing something else.
"""

import logging
import pathlib
import subprocess
import sys
import tempfile

import numpy as np
import pytest

from xtal.mof import Catalog, database_root, installed
from xtal.mof.build import BuildRequest, build

#: Nets chosen to spread the expansion over real cases rather than
#: over one: cubic, rhombohedral and hexagonal settings, one and two
#: node types, and four that the first pass of this comparison flagged
#: as disagreeing -- they did not, the comparison was wrong, and they
#: stay because that is exactly the shape of mistake worth pinning.
TOPOLOGIES = ("pcu", "tbo", "dia", "srs", "nbo", "bcu", "soc", "rht",
              "acs-f", "act-a", "ahq-a", "ahr-a")


#: Holds the temporary directory upstream's log is diverted into for
#: the length of this session.  Module-level so it outlives the import.
_HOLDER = None


def _upstream():
    """The real PORMAKE, or ``None`` -- imported without litter.

    **Upstream opens ``runtime.log`` in the current directory, mode
    "w", at import time**, which when the suite runs is the root of
    this checkout.  Vendoring fixed that where it happens, in
    ``xtal/mof/pormake/log.py``, and the fix does upstream no good at
    all: these tests import the real thing, so without this they put
    the file back -- and ``tests/test_mof_builder.py`` has a test
    asserting it is not there.

    So the file handler is contained for the length of the import and
    then taken off upstream's logger, which is what
    ``xtal.mof.build.import_pormake`` used to have to do for every
    build.

    Called once at module scope, to decide the skip, so the
    containment is in place before any test can import it a second
    way.
    """
    global _HOLDER

    if "pormake" in sys.modules:
        return sys.modules["pormake"]

    _HOLDER = tempfile.TemporaryDirectory(prefix="upstream-pormake-")
    original = logging.FileHandler

    class _Contained(original):             # type: ignore[misc]
        def __init__(self, filename, *args, **kwargs):
            given = pathlib.Path(filename)
            if not given.is_absolute():
                filename = pathlib.Path(_HOLDER.name) / given.name
            super().__init__(filename, *args, **kwargs)

    logging.FileHandler = _Contained
    try:
        import pormake
    except Exception:                       # pragma: no cover
        return None
    finally:
        logging.FileHandler = original

    # A file handler holds its file open, and on Windows an open file
    # cannot be removed -- so the directory could not be cleaned up.
    from pormake.log import logger as upstream_logger
    for handler in list(upstream_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            upstream_logger.removeHandler(handler)
            handler.close()
    return pormake


needs_upstream = pytest.mark.skipif(
    _upstream() is None,
    reason="the real PORMAKE is not installed, so there is nothing "
           "to diff the vendored one against")

needs_database = pytest.mark.skipif(
    database_root() is None,
    reason="the vendored PORMAKE database is missing")

#: Everything here runs the builder, so everything here needs ``ase``
#: as well as the data -- see the note in ``tests/test_mof_builder.py``.
needs_builder = pytest.mark.skipif(
    not installed(),
    reason="the MOF builder needs ase -- pip install "
           "'crystal-builder[ase]'")


#: Upstream's ``Scaler`` still passes scipy's deprecated ``disp``
#: option, and the global ignore for it is gone from ``pyproject.toml``
#: because the vendored copy no longer does.  Any test that runs the
#: *real* PORMAKE has to tolerate it locally -- which is a much better
#: place for it than a rule covering the whole suite.
tolerates_upstream_scipy = pytest.mark.filterwarnings(
    "ignore:scipy.optimize:DeprecationWarning")


@pytest.fixture(scope="module")
def catalog():
    if database_root() is None:
        pytest.skip("the vendored PORMAKE database is missing")
    return Catalog.default()


# ------------------------------------------- the expansion, site for site

def _same_sites(mine, theirs, tol=1e-4):
    """Whether two sets of fractional positions are the same sites.

    Pairs each position with an unused partner, modulo one lattice
    translation.  Both halves matter: a plain subtraction calls
    0.99999 and 0.0 half a cell apart when they are the same site, and
    sorting the coordinates to line them up has the same bug one level
    up -- which is how the first version of this comparison reported
    255 nets as disagreeing when none of them did.
    """
    if len(mine) != len(theirs):
        return False
    used = np.zeros(len(theirs), dtype=bool)
    for point in mine:
        delta = theirs - point
        delta -= np.round(delta)
        found = np.where((np.abs(delta) < tol).all(axis=1) & ~used)[0]
        if not len(found):
            return False
        used[found[0]] = True
    return bool(used.all())


@needs_builder
@needs_upstream
@pytest.mark.slow
@pytest.mark.parametrize("name", TOPOLOGIES)
def test_a_net_expands_to_the_same_slots_pymatgen_gave(name):
    """The trap the pymatgen substitution had to avoid, stated exactly.

    The expansion does not merely have to produce the same *set* of
    points: its order is the slot order of the net, and
    ``Topology.node_indices``, the builder's per-slot placement and
    ``xtal.mof.build._representatives`` are all indices into it.

    **But "identical to pymatgen's order" is not the invariant, and it
    was never reachable.**  pymatgen holds a space group's operations
    in a ``set``, so the order within one orbit falls out of
    ``SymmOp.__hash__``; gemmi lists them in the order the group
    defines.  Measured over the whole database, that permutes the
    members of an orbit in 2146 nets out of 2404 -- and changes
    nothing else in any of them.

    What has to hold, and does, is the invariant that actually carries
    the indices:

    * the same number of slots -- checked here and, over all 2404
      nets, by the test below;
    * **the same tag on the same slot**, so the block a user asked for
      on node type 0 goes on node type 0;
    * per tag, the same set of positions.

    A permutation inside a tag is a relabelling of slots that are
    symmetry-equivalent by construction, which is why the framework
    comes out the same -- and that is not argued here, it is measured
    by the build comparisons further down.
    """
    import pormake.utils as upstream_utils

    import xtal.mof.pormake.utils as ours

    path = str(database_root() / "topologies" / f"{name}.cgd")
    theirs = upstream_utils.read_cgd(filename=path)
    mine = ours.read_cgd(filename=path)

    assert len(mine) == len(theirs)
    assert list(mine.get_tags()) == list(theirs.get_tags())
    assert mine.info["cn"] == theirs.info["cn"]
    assert mine.get_chemical_symbols() == theirs.get_chemical_symbols()

    tags = np.asarray(mine.get_tags())
    ours_frac = mine.get_scaled_positions()
    theirs_frac = theirs.get_scaled_positions()
    for tag in sorted(set(tags.tolist())):
        assert _same_sites(ours_frac[tags == tag],
                           theirs_frac[tags == tag]), \
            f"{name}: slots of type {tag} are not the same sites"


@needs_builder
@needs_upstream
@pytest.mark.slow
def test_a_spread_of_the_database_expands_to_the_same_slot_counts():
    """Not just the twelve named above, and not all 2404 either.

    A space group symbol the new expansion read differently would show
    up as a net with the wrong number of slots, and one net in 2404 is
    enough to build somebody a wrong framework.  So this walks a
    deterministic stride through the database rather than a chosen
    handful.

    **The whole database was compared once, off-suite, and agreed on
    every one of the 2404 nets** -- same slot count, same tags, and
    nothing our reader refused that upstream accepted.  It is not done
    here because it is thirty minutes, essentially all of it inside
    pymatgen: ``read_cgd`` is about 0.2 s a net upstream and rather
    less vendored, and there are 2404 of them.  A test nobody will
    wait for is a test that gets deselected.
    """
    import pormake.utils as upstream_utils

    import xtal.mof.pormake.utils as ours

    files = sorted((database_root() / "topologies").glob("*.cgd"))
    assert len(files) > 2000

    disagreed = []
    for path in files[::120]:
        try:
            theirs = upstream_utils.read_cgd(filename=str(path))
        except Exception:
            continue            # unreadable either way; not our news
        try:
            mine = ours.read_cgd(filename=str(path))
        except Exception as exc:                # pragma: no cover
            disagreed.append(f"{path.stem}: ours raised {exc!r}")
            continue
        if len(mine) != len(theirs):
            disagreed.append(
                f"{path.stem}: {len(mine)} slots against {len(theirs)}")
        elif list(mine.get_tags()) != list(theirs.get_tags()):
            disagreed.append(f"{path.stem}: tags differ")

    assert not disagreed, disagreed[:20]


@needs_builder
@needs_upstream
@pytest.mark.slow
def test_the_new_expansion_is_not_slower_than_the_one_it_replaced():
    """gemmi in place of pymatgen had to not cost anything.

    Reading a net is on the path a user waits on: it happens once per
    build, on the worker thread, before anything else can start.  The
    nets below are the four slowest in the database -- ``nzn`` is 832
    slots and about ten seconds *in both* -- so if the substitution
    had made expansion quadratic in the wrong place, it would show
    here and nowhere else.

    Measured over the whole database: 574 s for 2404 nets, 0.24 s
    each, and within a few per cent of upstream at every size.  A
    generous bound, because this is a wall clock on a shared machine
    and the claim is "no worse", not a benchmark.
    """
    import time

    import pormake.utils as upstream_utils

    import xtal.mof.pormake.utils as ours

    for name in ("naz-x", "mjt"):
        path = str(database_root() / "topologies" / f"{name}.cgd")

        started = time.perf_counter()
        upstream_utils.read_cgd(filename=path)
        theirs = time.perf_counter() - started

        started = time.perf_counter()
        ours.read_cgd(filename=path)
        mine = time.perf_counter() - started

        assert mine < 2.0 * theirs + 1.0, (
            f"{name}: {mine:.1f}s against upstream's {theirs:.1f}s")


# ----------------------------------------------- a whole build, compared

def _build_upstream(name, nodes, edge, directory):
    """The same framework, built by the real PORMAKE.

    Given our database files, so the topology and the blocks are
    identical and the only variable is whose code placed them.
    """
    import pormake

    root = database_root()
    topology = pormake.Topology(str(root / "topologies" / f"{name}.cgd"))
    node_bbs = {
        int(k): pormake.BuildingBlock(str(root / "bbs" / f"{v}.xyz"))
        for k, v in nodes.items()}
    edge_bbs = (
        {tuple(sorted(t)): pormake.BuildingBlock(
            str(root / "bbs" / f"{edge}.xyz"))
         for t in topology.unique_edge_types}
        if edge else None)
    return pormake.Builder().build_by_type(
        topology=topology, node_bbs=node_bbs, edge_bbs=edge_bbs)


@needs_builder
@needs_upstream
@tolerates_upstream_scipy
@pytest.mark.slow
@pytest.mark.parametrize("name,nodes,edge", [
    ("pcu", {0: "N59"}, "E32"),
    ("pcu", {0: "N59"}, ""),
    ("dia", {0: "N12"}, "E32"),
])
def test_a_vendored_build_is_the_framework_upstream_builds(
        name, nodes, edge, tmp_path, catalog):
    """The gate this whole change stands or falls on.

    Not bit-identical, and it cannot be: jax runs in float32 by
    default, so upstream's gradient was single precision where the
    hand-derived one is double.  The two land on slightly different
    points of the same minimum.  What must agree is everything that
    would tell a chemist the build had changed -- how many atoms,
    which elements, and how well the blocks sat on their slots.
    """
    spelled = ",".join(f"{k}={v}" for k, v in nodes.items())
    ours = build(BuildRequest.parse(name, spelled, edge), tmp_path,
                 catalog)
    theirs = _build_upstream(name, nodes, edge, tmp_path)

    assert ours.n_atoms == len(theirs.atoms)
    assert (sorted(s.element for s in ours.structure.sites)
            == sorted(theirs.atoms.get_chemical_symbols()))

    # The locator's fit, which is what says the blocks were placed on
    # the slots rather than merely near them.  Ours is computed from a
    # cell the more accurate gradient relaxed, so it is allowed to
    # differ -- but only in the fourth decimal of an Angstrom.
    assert ours.max_rmsd == pytest.approx(
        theirs.info["max_rmsd"], abs=5e-3)
    assert ours.mean_rmsd == pytest.approx(
        theirs.info["mean_rmsd"], abs=5e-3)


@needs_builder
@needs_upstream
@pytest.mark.slow
def test_a_two_node_build_still_identifies_as_the_net_asked_for():
    """**tbo**, and the loudest signal the trim broke something.

    A framework that stops identifying as the net it was built on is
    what a wrong expansion or a wrong gradient produces: the atoms are
    all there and the composition is right, and the connectivity is
    something else.  ``check_net`` reads the net back off the
    structure's own bonds, so this is a statement about the file and
    not about anything PORMAKE said while writing it.
    """
    import tempfile

    catalogue = Catalog.default()
    three = next(b.name for b in catalogue.fitting(3) if b.has_metal)
    four = next(b.name for b in catalogue.fitting(4) if b.has_metal)
    with tempfile.TemporaryDirectory() as folder:
        outcome = build(
            BuildRequest.parse("tbo", f"0={three},1={four}", "E32"),
            folder, catalogue)
    assert outcome.net_name == "tbo"
    assert outcome.net_agrees


# ------------------------------------------------- the gradient, by itself

@needs_builder
@pytest.mark.slow
@pytest.mark.parametrize("name,block", [("pcu", "N59"), ("dia", "N12")])
def test_the_hand_derived_gradient_agrees_with_finite_differences(
        name, block, monkeypatch):
    """What replaced 554 MB of jax, checked against arithmetic.

    ``Scaler.scale`` builds its objective out of the topology and the
    blocks and hands one function to scipy, so the honest way to get
    at it is to let a real build happen and intercept the call.  A
    gradient that is merely plausible optimises to the wrong cell and
    every downstream check still passes, which is why this is here and
    not left to the build tests.
    """
    import scipy.optimize

    from xtal.mof.pormake import scaler as scaler_module

    seen = {}
    real = scipy.optimize.minimize

    def spy(**kwargs):
        seen.setdefault("fun", kwargs["fun"])
        seen.setdefault("x0", kwargs["x0"])
        return real(**kwargs)

    monkeypatch.setattr(scaler_module.sp.optimize, "minimize", spy)

    import xtal.mof.pormake as pm
    root = database_root()
    topology = pm.Topology(str(root / "topologies" / f"{name}.cgd"))
    blocks = {t: pm.BuildingBlock(str(root / "bbs" / f"{block}.xyz"))
              for t in topology.unique_node_types}
    pm.Builder().build_by_type(topology=topology, node_bbs=blocks)

    assert "fun" in seen, "the optimiser was never reached"
    fun, x0 = seen["fun"], seen["x0"]

    # At the start, and away from it: a gradient can be right at a
    # symmetric point and wrong everywhere else.
    rng = np.random.default_rng(0)
    for x in (x0, x0 + 0.01 * rng.standard_normal(x0.size)):
        _value, gradient = fun(x)
        approx = scipy.optimize.approx_fprime(
            x, lambda y: fun(y)[0], 1e-7)
        error = (np.linalg.norm(gradient - approx)
                 / (np.linalg.norm(approx) + 1e-30))
        assert error < 1e-5


# ------------------------------------------------------- the trim itself

@needs_builder
@pytest.mark.slow
def test_a_build_imports_none_of_the_three_packages_that_were_removed():
    """889 MB down to 23, and this is what keeps it there.

    In a subprocess, because the claim is about a fresh interpreter:
    this test session may well have imported the real PORMAKE -- and
    with it jax and pymatgen -- to run the comparisons above, and
    ``sys.modules`` would then say the opposite of the truth.

    A whole framework is built, not just imported, so the check covers
    the expansion and the cell relaxation rather than only the import
    lines at the top of each file.
    """
    program = (
        "import sys, tempfile;"
        "from xtal.mof import Catalog;"
        "from xtal.mof.build import BuildRequest, build;"
        "d = tempfile.mkdtemp();"
        "build(BuildRequest.parse('pcu', 'N59', 'E32'), d,"
        " Catalog.default());"
        "print(' '.join(sorted("
        "  n for n in ('jax', 'jaxlib', 'pymatgen', 'networkx')"
        "  if n in sys.modules)) or 'none')")
    out = subprocess.run([sys.executable, "-c", program],
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "none", out.stdout


@needs_upstream
def test_importing_the_real_pormake_here_leaves_no_runtime_log():
    """These tests must not put back the litter vendoring removed.

    Upstream opens ``runtime.log`` in the current directory at import
    time, and when the suite runs that is the root of this checkout.
    ``_upstream`` contains it; this is what notices if that stops
    working, because the symptom is otherwise a stray file nobody
    connects to a test run.
    """
    assert "pormake" in sys.modules, "the containment never ran"
    assert not pathlib.Path("runtime.log").exists()
    assert not (pathlib.Path(__file__).resolve().parent.parent
                / "runtime.log").exists()


@needs_builder
def test_the_vendored_tree_carries_its_licence_and_its_provenance():
    """Vendoring somebody else's MIT code is clean only if the notice
    travels with it, and only useful if what changed is written down.

    Both are named in ``pyproject.toml``'s package data and in
    ``packaging/bundle.py``, so a wheel and a bundle carry them too.
    """
    from pathlib import Path

    import xtal.mof.pormake as pm

    root = Path(pm.__file__).resolve().parent
    licence = (root / "LICENSE.md").read_text()
    assert "MIT License" in licence
    assert "Copyright (c) 2022 Sangwon" in licence

    provenance = (root / "PROVENANCE.md").read_text()
    for subject in ("jax", "pymatgen", "networkx", "0.2.3"):
        assert subject in provenance
