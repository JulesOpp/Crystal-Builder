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

So the tests come in three kinds:

**Against the real PORMAKE's answers**, recorded once in
``tests/data/pormake_upstream.json`` by the script beside it -- the
expansion site for site, a spread of slot counts, and whole builds
compared by composition and RMSD.  Upstream is a pinned release and the
vendored tree is ours, so neither side moves by accident, and recording
means the comparison runs everywhere, CI included, instead of only
where upstream happens to be installed.  It also keeps upstream out of
this process: pymatgen, jax, h5py and pandas were several hundred
shared libraries loaded half way through a long run, and on macOS 13.2
that load is where every aborted run died.  One slow test re-derives a
sample of the recording, in a subprocess, when upstream is installed.

**Against arithmetic**, which needs nothing: the gradient against
finite differences.  This is the one that would catch a wrong
derivative on a machine that has never seen upstream.

**Against the trim itself**: that a build imports none of the three
packages that were taken out.  Cheap, and it is what fails if somebody
reintroduces an import while fixing something else.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
from collections import Counter

import numpy as np
import pytest

from xtal.mof import Catalog, database_root, installed
from xtal.mof.build import BuildRequest, build

HERE = pathlib.Path(__file__).resolve().parent
RECORDER = HERE / "data" / "record_pormake_upstream.py"
RECORDING = HERE / "data" / "pormake_upstream.json"

#: Nets chosen to spread the expansion over real cases rather than
#: over one: cubic, rhombohedral and hexagonal settings, one and two
#: node types, and four that the first pass of this comparison flagged
#: as disagreeing -- they did not, the comparison was wrong, and they
#: stay because that is exactly the shape of mistake worth pinning.
#: The recorder keeps its own copy of this list; the recording is keyed
#: by it, and a name missing from it fails loudly below.
TOPOLOGIES = ("pcu", "tbo", "dia", "srs", "nbo", "bcu", "soc", "rht",
              "acs-f", "act-a", "ahq-a", "ahr-a")

needs_database = pytest.mark.skipif(
    database_root() is None,
    reason="the vendored PORMAKE database is missing")

#: Everything here runs the builder, so everything here needs ``ase``
#: as well as the data -- see the note in ``tests/test_mof_builder.py``.
needs_builder = pytest.mark.skipif(
    not installed(),
    reason="the MOF builder needs ase -- pip install "
           "'crystal-builder[ase]'")

needs_upstream = pytest.mark.skipif(
    importlib.util.find_spec("pormake") is None,
    reason="the real PORMAKE is not installed, so the recording cannot "
           "be checked against it")


@pytest.fixture(scope="module")
def recorded():
    return json.loads(RECORDING.read_text())


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
@pytest.mark.parametrize("name", TOPOLOGIES)
def test_a_net_expands_to_the_same_slots_pymatgen_gave(name, recorded):
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

    * the same number of slots -- checked here and, over a stride of
      the database, by the test below;
    * **the same tag on the same slot**, so the block a user asked for
      on node type 0 goes on node type 0;
    * per tag, the same set of positions.

    A permutation inside a tag is a relabelling of slots that are
    symmetry-equivalent by construction, which is why the framework
    comes out the same -- and that is not argued here, it is measured
    by the build comparisons further down.
    """
    import xtal.mof.pormake.utils as ours

    theirs = recorded["expansions"][name]
    mine = ours.read_cgd(
        filename=str(database_root() / "topologies" / f"{name}.cgd"))

    assert len(mine) == len(theirs["tags"])
    assert [int(t) for t in mine.get_tags()] == theirs["tags"]
    assert [int(c) for c in mine.info["cn"]] == theirs["cn"]
    assert mine.get_chemical_symbols() == theirs["symbols"]

    tags = np.asarray(mine.get_tags())
    ours_frac = mine.get_scaled_positions()
    theirs_frac = np.asarray(theirs["frac"])
    for tag in sorted(set(tags.tolist())):
        assert _same_sites(ours_frac[tags == tag],
                           theirs_frac[tags == tag]), \
            f"{name}: slots of type {tag} are not the same sites"


@needs_builder
def test_a_spread_of_the_database_expands_to_the_same_slot_counts(
        recorded):
    """Not just the twelve named above, and not all 2404 either.

    A space group symbol the new expansion read differently would show
    up as a net with the wrong number of slots, and one net in 2404 is
    enough to build somebody a wrong framework.  So this walks a
    deterministic stride through the database rather than a chosen
    handful, against what upstream gave for the same files.

    **The whole database was compared once, off-suite, and agreed on
    every one of the 2404 nets** -- same slot count, same tags, and
    nothing our reader refused that upstream accepted.  It is not done
    here because it was thirty minutes, essentially all of it inside
    pymatgen.
    """
    import xtal.mof.pormake.utils as ours

    files = sorted((database_root() / "topologies").glob("*.cgd"))
    assert len(files) == recorded["of"]
    stride = files[::recorded["stride"]]
    assert [p.stem for p in stride] == list(recorded["slots"])

    disagreed = []
    for path in stride:
        theirs = recorded["slots"][path.stem]
        if theirs is None:
            continue            # unreadable upstream; not our news
        try:
            mine = ours.read_cgd(filename=str(path))
        except Exception as exc:                # pragma: no cover
            disagreed.append(f"{path.stem}: ours raised {exc!r}")
            continue
        if len(mine) != theirs["slots"]:
            disagreed.append(f"{path.stem}: {len(mine)} slots against "
                             f"{theirs['slots']}")
        elif [int(t) for t in mine.get_tags()] != theirs["tags"]:
            disagreed.append(f"{path.stem}: tags differ")

    assert not disagreed, disagreed[:20]


@needs_builder
@needs_upstream
@pytest.mark.slow
def test_the_recording_is_what_upstream_says(tmp_path):
    """The recorded answers came from the real PORMAKE, and still do.

    A sample -- three slot counts, two expansions, one build -- asked
    for again by the recorder's ``--check``.  **In a subprocess**, so
    that upstream never enters this process, and **in a temporary
    directory**, because upstream opens ``runtime.log`` in the current
    one at import and the suite's is the root of this checkout.  That
    stray file is checked for here too: it is otherwise a file nobody
    connects to a test run.
    """
    checkout = HERE.parent
    before = (checkout / "runtime.log").exists()
    done = subprocess.run([sys.executable, str(RECORDER), "--check"],
                          cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr[-2000:]
    assert "recording matches upstream" in done.stdout
    assert (checkout / "runtime.log").exists() == before


@needs_builder
def test_the_largest_nets_are_read_in_well_under_a_second():
    """Reading a net is on the path a user waits on.

    It happens once per build, on the worker thread, before anything
    else can start.  These are the slowest nets in the database: with
    pymatgen's expansion and ase's neighbour list, ``nzn`` (832 slots)
    took about ten seconds upstream and ``naz-x`` 4.4.  Both expansions
    are now gemmi and the overlap check is a KD-tree, and each reads in
    a few hundredths of a second -- so a bound of one second is generous
    on a loaded machine and still catches a return to a quadratic
    search.  It used to be measured against upstream, which was the
    only bound that meant anything while the two were equally slow.
    """
    import time

    import xtal.mof.pormake.utils as ours

    for name in ("nzn", "naz-x", "mjt"):
        path = str(database_root() / "topologies" / f"{name}.cgd")
        started = time.perf_counter()
        ours.read_cgd(filename=path)
        took = time.perf_counter() - started
        assert took < 1.0, f"{name}: {took:.2f} s"


# ----------------------------------------------- a whole build, compared

@needs_builder
@pytest.mark.slow
@pytest.mark.parametrize("name,nodes,edge", [
    ("pcu", {0: "N59"}, "E32"),
    ("pcu", {0: "N59"}, ""),
    ("dia", {0: "N12"}, "E32"),
])
def test_a_vendored_build_is_the_framework_upstream_builds(
        name, nodes, edge, tmp_path, catalog, recorded):
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
    theirs = recorded["builds"][f"{name}|{spelled}|{edge}"]

    assert ours.n_atoms == theirs["n_atoms"]
    assert (dict(sorted(Counter(
        s.element for s in ours.structure.sites).items()))
        == theirs["elements"])

    # The locator's fit, which is what says the blocks were placed on
    # the slots rather than merely near them.  Ours is computed from a
    # cell the more accurate gradient relaxed, so it is allowed to
    # differ -- but only in the fourth decimal of an Angstrom.
    assert ours.max_rmsd == pytest.approx(theirs["max_rmsd"], abs=5e-3)
    assert ours.mean_rmsd == pytest.approx(theirs["mean_rmsd"], abs=5e-3)


@needs_builder
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
