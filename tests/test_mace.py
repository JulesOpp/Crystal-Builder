"""The MACE engine: the arithmetic around the model, and the model.

**Nearly everything here runs without mace installed**, and that is
the point rather than a convenience.  What can be got wrong in this
engine is this application's half -- the eV to kcal/mol conversion, the
P1 atom ordering the optimiser maps forces back through, whether the
cell handed in is the cell evaluated -- and none of that is MACE's.  So
the model loader is replaced with a cheap ASE calculator and the
arithmetic is checked against it.

One test needs the real thing, and it is the one that has to: whether
the stress the engine claims agrees with a numeric one.  See
``xtal/ff/xtb/calculator.py`` for what claiming a wrong stress costs.

**The two that import mace do it in a fresh interpreter.**  mace brings
torch's model code, e3nn, pandas, h5py and pyarrow: 227 shared
libraries on top of the seven hundred the rest of the suite has already
loaded.  That load, half way through a long run, is where full runs on
macOS 13.2 were aborting inside the dynamic loader -- and nothing these
tests assert needs mace in the same process as the rest of the suite.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tests.conftest_ff import water
from xtal import install
from xtal.ff import ENGINES
from xtal.ff.api import CalculatorError
from xtal.ff.mace import calculator as mace
from xtal.params import Availability

ase = pytest.importorskip("ase")

needs_mace = pytest.mark.skipif(
    importlib.util.find_spec("mace") is None,
    reason="mace is not installed -- pip install 'crystal-builder[mace]'")


def in_a_fresh_interpreter(program: str):
    """Run *program* in a new Python and return the JSON it prints last.

    See the module docstring for why: mace is imported there and never
    here.
    """
    done = subprocess.run(
        [sys.executable, "-c", program],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture
def stand_in(monkeypatch):
    """A Lennard-Jones ASE calculator where the model would be.

    Cheap, analytic, and it has an energy, forces and a stress -- which
    is every part of the interface this engine reads.
    """
    from ase.calculators.lj import LennardJones

    made = []

    def load(options):
        made.append(options)
        return LennardJones(rc=6.0)

    monkeypatch.setattr(mace, "_load_model", load)
    monkeypatch.setattr(mace, "_device", lambda wanted: "cpu")
    mace.forget_models()
    return made


# ------------------------------------------------------ the arithmetic

def test_the_energy_and_forces_come_back_in_kcal(stand_in):
    """Everything above this interface is kcal/mol and kcal/mol/A; ASE
    is eV.  One factor, and it has to be applied to both."""
    from ase.calculators.lj import LennardJones

    structure = water()
    engine = mace.MACECalculator(structure)
    cell = engine.cell
    result = engine.compute(cell.cart, structure.lattice.matrix)

    atoms = ase.Atoms(symbols=list(cell.elements),
                      positions=np.asarray(cell.cart),
                      cell=np.asarray(structure.lattice.matrix),
                      pbc=True)
    atoms.calc = LennardJones(rc=6.0)
    assert result.energy == pytest.approx(
        atoms.get_potential_energy() * mace.KCAL_PER_EV)
    assert result.forces == pytest.approx(
        np.asarray(atoms.get_forces()) * mace.KCAL_PER_EV)
    assert mace.KCAL_PER_EV == pytest.approx(23.0605, abs=1e-3)


def test_the_forces_are_in_p1_atom_order(stand_in):
    """The optimiser maps a force back onto the site it came from by
    index, so an atom container that reordered anything would put a
    force on the wrong atom."""
    structure = water()
    engine = mace.MACECalculator(structure)
    assert engine.symbols == tuple(engine.cell.elements)
    assert engine.symbols[0] == "O"
    result = engine.compute(engine.cell.cart, structure.lattice.matrix)
    assert len(result.forces) == engine.n_atoms == 3


def test_the_cell_it_is_given_is_the_cell_it_evaluates(stand_in):
    """A variable-cell relaxation hands in a strained lattice, and the
    positions with it.  Letting ASE carry the atoms along with the cell
    would apply the strain twice."""
    structure = water()
    engine = mace.MACECalculator(structure)
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    engine.compute(engine.cell.cart, matrix)
    first = np.array(engine._atoms.get_positions())
    engine.compute(engine.cell.cart, matrix * 1.2)
    assert np.allclose(engine._atoms.get_positions(), first)
    assert np.allclose(engine._atoms.cell, matrix * 1.2)


def test_positions_that_are_not_the_cell_are_refused(stand_in):
    engine = mace.MACECalculator(water())
    with pytest.raises(CalculatorError):
        engine.compute(np.zeros((2, 3)),
                       engine.structure.lattice.matrix)


def test_a_structure_with_no_atoms_is_a_sentence(stand_in):
    from xtal import Lattice, Structure

    with pytest.raises(CalculatorError):
        mace.MACECalculator(Structure(Lattice.cubic(10.0)))


def test_the_model_is_loaded_once_for_all_the_evaluations(stand_in):
    """A load is seconds and an optimisation is hundreds of
    evaluations."""
    engine = mace.MACECalculator(water())
    for _ in range(3):
        engine.compute(engine.cell.cart,
                       engine.structure.lattice.matrix)
    assert len(stand_in) == 1
    assert engine.calls == 3


# ------------------------------------------------------- availability

def test_a_missing_package_names_the_extra_to_install(monkeypatch):
    monkeypatch.setattr(mace, "installed", lambda: False)
    answer = mace.available()
    assert not answer.ok
    assert install.command("mace") in answer.reason


def test_a_foundation_model_says_it_will_be_downloaded(monkeypatch):
    """It is a download this application did not start, so it is said
    before anything runs rather than discovered as a pause."""
    monkeypatch.setattr(mace, "installed", lambda: True)
    answer = mace.available(model="medium")
    assert answer.ok
    assert "download" in answer.reason.lower()


def test_a_model_file_that_is_not_there_is_refused(monkeypatch,
                                                  tmp_path):
    monkeypatch.setattr(mace, "installed", lambda: True)
    missing = mace.available(model="custom",
                             model_path=str(tmp_path / "nope.model"))
    assert not missing.ok and "no model file" in missing.reason

    unnamed = mace.available(model="custom", model_path="")
    assert not unnamed.ok and "name the model file" in unnamed.reason

    real = tmp_path / "mine.model"
    real.write_bytes(b"weights")
    assert mace.available(model="custom",
                          model_path=str(real)).ok


def test_the_engine_is_in_the_registry_with_what_it_provides():
    engine = ENGINES.get("mace")
    assert "forces" in engine.provides and "stress" in engine.provides
    assert "periodic" in engine.provides
    assert [p.name for p in engine.options] == [
        "model", "model_path", "device", "double_precision"]
    assert isinstance(engine.availability(), Availability)


def test_the_registry_builds_it_with_markers_held_back(stand_in):
    """A centroid is a marker and not chemistry, so the engine is
    built over a cell with none -- which the registry does for every
    engine and is why this one does not do it itself."""
    from xtal.commands.atoms import new_site

    structure = water()
    structure.add_site(new_site("X", [0.4, 0.4, 0.4]))
    calculator = ENGINES.build("mace", structure)
    assert calculator.n_atoms == 4          # the marker is presented
    result = calculator.compute(
        np.asarray(__import__("xtal.core.p1", fromlist=["p1"])
                   .expand(structure).cart),
        structure.lattice.matrix)
    assert result.forces.shape == (4, 3)
    assert np.allclose(result.forces[3], 0.0)   # no force on a marker


# ------------------------------------------------------- the real model

@pytest.mark.slow
@needs_mace
def test_maces_analytic_hessian_agrees_with_finite_differences():
    """Our row loop over MACE's force graph, against central
    differences of the forces it reports: the conversion, the row
    order and which atoms' rows were asked for.  Water with its
    oxygen held, so a sliced block is what is compared."""
    answer = in_a_fresh_interpreter(
        "import json\n"
        "import numpy as np\n"
        "from tests.conftest_ff import water\n"
        "from xtal.core import p1\n"
        "from xtal.ff.mace import calculator as mace\n"
        "structure = water()\n"
        "engine = mace.MACECalculator(structure, mace.MACEOptions(\n"
        "    model='small', device='cpu', double_precision=True))\n"
        "cart = np.asarray(p1.expand(structure).cart, dtype=float)\n"
        "matrix = np.asarray(structure.lattice.matrix, dtype=float)\n"
        "rows = []\n"
        "block = engine.hessian(cart, matrix, atoms=[1, 2],\n"
        "    progress=lambda done, total: rows.append(done))\n"
        "coords = [3, 4, 5, 6, 7, 8]\n"
        "numeric = np.zeros((6, 6))\n"
        "for column, coord in enumerate(coords):\n"
        "    moved = cart.copy()\n"
        "    moved.flat[coord] += 1e-3\n"
        "    plus = engine.compute(moved, matrix).forces.ravel()\n"
        "    moved.flat[coord] -= 2e-3\n"
        "    minus = engine.compute(moved, matrix).forces.ravel()\n"
        "    numeric[:, column] = -(plus - minus)[coords] / 2e-3\n"
        "print(json.dumps({'analytic': block.tolist(),\n"
        "                  'numeric': numeric.tolist(),\n"
        "                  'rows': rows}))\n")
    analytic = np.asarray(answer["analytic"])
    assert analytic.shape == (6, 6)
    assert answer["rows"] == [1, 2, 3, 4, 5, 6]
    assert analytic == pytest.approx(np.asarray(answer["numeric"]),
                                     abs=0.2)
    assert np.abs(analytic).max() > 100.0      # kcal/mol/A^2, not eV


@pytest.mark.slow
@needs_mace
@pytest.mark.slow
def test_the_stress_it_claims_agrees_with_a_numeric_one():
    """The one test that needs mace, and the one that has to have it: a
    stress that is quietly wrong relaxes a cell to the wrong volume and
    reports converging while it does it."""
    # The smallest model, explicitly, and on the CPU.  What this test
    # is about is our own factor of 23.06 and the strain ASE is handed
    # -- neither improves with a better model, and the default is a
    # 76 MB download where this is 31.
    answer = in_a_fresh_interpreter(
        "import json\n"
        "import numpy as np\n"
        "from tests.conftest_ff import water\n"
        "from xtal.core import p1\n"
        "from xtal.ff.mace import calculator as mace\n"
        "structure = water()\n"
        "engine = mace.MACECalculator(structure, mace.MACEOptions(\n"
        "    model='small', device='cpu', double_precision=True))\n"
        "cell = p1.expand(structure)\n"
        "matrix = np.asarray(structure.lattice.matrix, dtype=float)\n"
        "claimed = engine.compute(cell.cart, matrix).stress\n"
        "numeric = engine.numeric_stress(cell.cart, matrix, strain=1e-4)\n"
        "print(json.dumps({'claimed': np.asarray(claimed).tolist(),\n"
        "                  'numeric': np.asarray(numeric).tolist()}))\n")
    assert np.asarray(answer["claimed"]) == pytest.approx(
        np.asarray(answer["numeric"]), abs=2e-3)


def test_a_model_with_no_stress_still_gives_an_energy_and_forces(
        monkeypatch):
    """A model that reports no stress must cost the stress and nothing
    else.

    ``compute`` used to fetch energy, forces and stress inside one
    ``except``, so a model with no stress -- which a fitted file of
    somebody's own is allowed to be -- failed every evaluation with
    "MACE could not compute this structure".  The energy and forces it
    would have given perfectly well went with it, and a fixed-cell
    optimisation that never wanted a stress could not run at all.
    """
    from ase.calculators.lj import LennardJones

    class NoStress(LennardJones):
        implemented_properties = ["energy", "forces"]

    monkeypatch.setattr(mace, "_load_model",
                        lambda options: NoStress(rc=6.0))
    monkeypatch.setattr(mace, "_device", lambda wanted: "cpu")
    mace.forget_models()
    from xtal.core import p1

    structure = water()
    engine = mace.MACECalculator(structure)
    cell = p1.expand(structure)
    result = engine.compute(cell.cart, structure.lattice.matrix)

    assert not engine.provides_stress
    assert result.stress is None
    assert np.isfinite(result.energy)
    assert result.forces.shape == (cell.n_atoms, 3)
    # Said rather than discovered: relaxing the cell still works, by
    # twelve evaluations a step instead of one.
    assert any("no stress" in w for w in engine.warnings)
    assert np.isfinite(engine.numeric_stress(
        cell.cart, structure.lattice.matrix)).all()


def test_the_default_model_is_the_one_mace_itself_defaults_to():
    """MACE-MPA-0, not MACE-MP-0a medium.

    mace-torch changed its own default at 0.3.10 and asking for
    ``medium`` now gets the older generation -- mace prints a line
    saying so.  A chooser whose first entry was ``medium`` handed
    everybody the previous default while looking like the current one,
    which is the kind of wrong nobody reads an error message about.
    """
    assert mace.DEFAULT_MODEL == "medium-mpa-0"
    assert mace.MACEOptions().model == mace.DEFAULT_MODEL
    param = next(p for p in mace.OPTIONS if p.name == "model")
    assert param.default == mace.DEFAULT_MODEL
    assert mace.MODEL_CHOICES[0][0] == mace.DEFAULT_MODEL


def test_a_licence_restricted_model_says_so_before_it_is_chosen(
        monkeypatch):
    """MACE prints "you accept the terms of the license" as it
    downloads; this application is the thing doing the downloading, so
    the licence is in the label the user picks from and in what
    ``available`` records.

    Installed is patched in because "not installed" is answered first,
    and the build venv has no mace extra: without it this checks the
    install message on a release machine and the licence nowhere."""
    monkeypatch.setattr(mace, "installed", lambda: True)
    offered = [name for name, _label in mace.MODEL_CHOICES]
    restricted = [n for n in offered if n in mace.ASL_MODELS]
    assert restricted, "the point of the test is that some are"
    for name, label in mace.MODEL_CHOICES:
        assert ("ASL" in label) == (name in mace.ASL_MODELS)
    assert "Academic Software License" in mace.available(
        model=restricted[0]).reason


@needs_mace
@pytest.mark.slow
def test_every_model_offered_is_a_name_mace_knows():
    """A name mace_mp cannot resolve fails at *download*, minutes into
    a run and after the model list looked fine.  Checked against
    mace's own table rather than against a copy of it."""
    mace_mp_urls = in_a_fresh_interpreter(
        "import json\n"
        "from mace.calculators.foundations_models import mace_mp_urls\n"
        "print(json.dumps(sorted(mace_mp_urls)))\n")

    # MACE-MP-MOF0 and uMOF-MH are not in mace's table: each is fetched
    # from its own pinned URL (``_FETCHED``) and never handed to mace_mp
    # by name.
    for name, _label in mace.MODEL_CHOICES:
        if name in ("custom", mace.MOF0, mace.UMOF):
            continue
        assert name in mace_mp_urls, name


# ------------------------------------------------------ MACE-MP-MOF0
#
# Elena et al., npj Comput. Mater. 11, 125 (2025): MACE-MP-0b
# fine-tuned on 127 MOFs at PBE-D3(BJ), for phonons.  One file holding
# two heads, 26 elements, CC BY 4.0 with a citation required.

def test_mof0_is_offered_and_says_what_it_is_before_it_is_chosen(
        monkeypatch):
    monkeypatch.setattr(mace, "installed", lambda: True)
    label = dict(mace.MODEL_CHOICES)[mace.MOF0]
    assert "D3" in label and "CC BY" in label
    said = mace.available(model=mace.MOF0).reason
    assert "31 MB" in said and "cite" in said


def test_mof0_is_loaded_through_its_mof_head(monkeypatch, tmp_path):
    """The file holds the MACE-MP-0b head it was fine-tuned from and
    the MOF head, and MACE refuses to guess -- so a file of one's own
    pointed at it cannot load at all.  The MOF head is pbe_d3."""
    import types

    made = []

    class Model:
        def __init__(self, **kwargs):
            made.append(kwargs)

    calculators = types.ModuleType("mace.calculators")
    calculators.MACECalculator = Model
    monkeypatch.setitem(sys.modules, "mace", types.ModuleType("mace"))
    monkeypatch.setitem(sys.modules, "mace.calculators", calculators)
    monkeypatch.setattr(mace, "_device", lambda wanted: "cpu")
    monkeypatch.setattr(mace, "_fetch_mof0",
                        lambda: tmp_path / "mofs_v2.model")

    mace._build_model(mace.MACEOptions(model=mace.MOF0))

    assert made == [{"model_paths": str(tmp_path / "mofs_v2.model"),
                     "device": "cpu", "default_dtype": "float64",
                     "head": "pbe_d3"}]


def test_mof0_is_fetched_once_and_only_as_the_file_it_was(monkeypatch,
                                                          tmp_path):
    """Pinned to a commit and a SHA-256.  A model file is a pickle, so
    loading one runs it: what is loaded has to be exactly the file the
    paper published, and a download that is anything else is deleted
    rather than kept for next time."""
    import hashlib
    import io

    good = b"the model"
    monkeypatch.setattr(mace, "MOF0_SHA256",
                        hashlib.sha256(good).hexdigest())
    monkeypatch.setattr(mace, "_cache_dir", lambda: tmp_path)
    served = []

    def urlopen(url, timeout=None):
        served.append(url)
        return io.BytesIO(served_bytes[0])

    monkeypatch.setattr(mace.urllib.request, "urlopen", urlopen)

    served_bytes = [b"something else"]
    with pytest.raises(CalculatorError, match="not the file"):
        mace._fetch_mof0()
    assert not (tmp_path / "mofs_v2.model").exists()

    served_bytes[0] = good
    path = mace._fetch_mof0()
    assert path.read_bytes() == good
    assert mace._fetch_mof0() == path                # cached
    assert len(served) == 2
    assert "3b6d2fd559272106d0fff0fce0d0ba32bcb16541" in served[0]


def test_mof0_is_cited_when_it_is_the_model(stand_in):
    from xtal.ff import ENGINES

    engine = ENGINES.get("mace")
    chosen = [r.url for r in engine.sources(model=mace.MOF0)]
    usual = [r.url for r in engine.sources()]
    assert any("10.1038/s41524-025-01611-8" in u for u in chosen)
    assert not any("s41524-025-01611-8" in u for u in usual)


# ------------------------------------------------------------ uMOF-MH
#
# Jaffrelot Inizan, Kamath, Elena and Persson, arXiv:2608.28100:
# MACE-MH-1's r2SCAN-D4 head fine-tuned on 19 950 MOFs, gas loading and
# MD among them.  Served only inside a zip beside uMOF-POLAR.

def _a_umof_archive(model: bytes) -> bytes:
    """A zip laid out as the figshare one is, macOS junk included."""
    import io
    import zipfile

    held = io.BytesIO()
    with zipfile.ZipFile(held, "w") as zipped:
        zipped.writestr("umof_models/", b"")
        zipped.writestr("umof_models/uMOF-POLAR.model", b"the other")
        zipped.writestr("__MACOSX/umof_models/._uMOF-MH.model", b"junk")
        zipped.writestr(mace.UMOF_MEMBER, model)
    return held.getvalue()


def test_umof_is_offered_and_says_what_it_is_before_it_is_chosen(
        monkeypatch):
    """The licence and the size are said before the download, because
    MACE's own notice comes as it downloads; and that dispersion is in
    it, because D3 on top would count it twice."""
    monkeypatch.setattr(mace, "installed", lambda: True)
    label = dict(mace.MODEL_CHOICES)[mace.UMOF]
    assert "r2SCAN-D4" in label and "ASL" in label and "cite" in label
    said = mace.available(model=mace.UMOF).reason
    assert "106 MB" in said and "Academic Software License" in said
    assert "2608.28100" in said and "dispersion" in said
    assert mace.DEFAULT_MODEL != mace.UMOF


def test_umof_is_loaded_through_its_r2scan_d4_head(monkeypatch,
                                                   tmp_path):
    """The file holds MH-1's own head beside the MOF one, and MACE
    refuses to guess.  The wrong head would answer under uMOF's name
    with the numbers of the model it was fine-tuned from."""
    import types

    made = []

    class Model:
        def __init__(self, **kwargs):
            made.append(kwargs)

    calculators = types.ModuleType("mace.calculators")
    calculators.MACECalculator = Model
    monkeypatch.setitem(sys.modules, "mace", types.ModuleType("mace"))
    monkeypatch.setitem(sys.modules, "mace.calculators", calculators)
    monkeypatch.setattr(mace, "_device", lambda wanted: "cpu")
    monkeypatch.setattr(mace, "_fetch_umof",
                        lambda: tmp_path / "uMOF-MH.model")

    mace._build_model(mace.MACEOptions(model=mace.UMOF))

    assert made == [{"model_paths": str(tmp_path / "uMOF-MH.model"),
                     "device": "cpu", "default_dtype": "float64",
                     "head": "r2scan+d4"}]


def test_umof_is_unzipped_only_from_the_published_archive(monkeypatch,
                                                          tmp_path):
    """Two checks, for two different things.  The archive's says what
    is unzipped is the authors' zip; the member's, run on every load,
    says the cached file is still theirs.  Nothing but the model is
    left behind -- not 47 MB of uMOF-POLAR, not a partial file."""
    import hashlib
    import io

    good = b"the model"
    archive = _a_umof_archive(good)
    monkeypatch.setattr(mace, "UMOF_SHA256",
                        hashlib.sha256(good).hexdigest())
    monkeypatch.setattr(mace, "UMOF_ZIP_SHA256",
                        hashlib.sha256(archive).hexdigest())
    monkeypatch.setattr(mace, "_cache_dir", lambda: tmp_path)
    served = []

    def urlopen(url, timeout=None):
        served.append(url)
        return io.BytesIO(served_bytes[0])

    monkeypatch.setattr(mace.urllib.request, "urlopen", urlopen)

    served_bytes = [_a_umof_archive(b"another model")]
    with pytest.raises(CalculatorError, match="archive is not the file"):
        mace._fetch_umof()
    assert list(tmp_path.iterdir()) == []

    served_bytes[0] = archive
    path = mace._fetch_umof()
    assert path.read_bytes() == good
    assert [p.name for p in tmp_path.iterdir()] == ["uMOF-MH.model"]
    assert mace._fetch_umof() == path                # cached
    assert len(served) == 2
    assert served[0].endswith("/files/67738656")

    path.write_bytes(b"tampered")
    with pytest.raises(CalculatorError, match="not the file"):
        mace._fetch_umof()
    assert not path.exists()


def test_umof_is_cited_when_it_is_the_model(stand_in):
    from xtal.ff import ENGINES

    engine = ENGINES.get("mace")
    chosen = [r.url for r in engine.sources(model=mace.UMOF)]
    usual = [r.url for r in engine.sources()]
    assert any("2608.28100" in u for u in chosen)
    assert not any("2608.28100" in u for u in usual)


@pytest.mark.slow
@needs_mace
def test_umof_answers_for_a_crystal_when_it_is_already_downloaded():
    """The real file through the real head: an energy, forces on every
    atom and a stress.  Skipped rather than downloaded where it is not
    cached -- 106 MB is not a test's to fetch."""
    answer = in_a_fresh_interpreter(
        "import json\n"
        "from tests.conftest_ff import water\n"
        "from xtal.core import p1\n"
        "from xtal.ff.mace import calculator as mace\n"
        "if not (mace._cache_dir() / mace.UMOF_FILE).is_file():\n"
        "    print(json.dumps(None)); raise SystemExit\n"
        "structure = water()\n"
        "engine = mace.MACECalculator(structure, mace.MACEOptions(\n"
        "    model=mace.UMOF, device='cpu'))\n"
        "import numpy as np\n"
        "cart = np.asarray(p1.expand(structure).cart, dtype=float)\n"
        "matrix = np.asarray(structure.lattice.matrix, dtype=float)\n"
        "got = engine.compute(cart, matrix)\n"
        "print(json.dumps({'energy': float(got.energy),\n"
        "    'forces': np.asarray(got.forces).shape,\n"
        "    'stress': None if got.stress is None\n"
        "              else np.asarray(got.stress).shape}))\n")
    if answer is None:
        pytest.skip("uMOF-MH is not in the MACE cache")
    assert np.isfinite(answer["energy"])
    assert answer["forces"] == [3, 3]
    assert answer["stress"] == [3, 3]


def test_an_element_the_model_was_not_fitted_on_is_refused_by_name(
        monkeypatch):
    """MACE-MP-MOF0 knows 26 elements -- no Cr, Mn, Co or Ni -- and
    MACE's own answer for another is "np.int64(63) is not in list".
    The same holds for any fitted model file."""
    from ase.calculators.lj import LennardJones

    class Fitted(LennardJones):
        z_table = type("Z", (), {"zs": [1, 6, 8, 30]})()

    monkeypatch.setattr(mace, "_load_model", lambda options: Fitted())
    monkeypatch.setattr(mace, "_device", lambda wanted: "cpu")
    structure = water()
    structure.sites[0].element = "Eu"
    structure.touch()

    with pytest.raises(CalculatorError, match="Eu"):
        mace.MACECalculator(structure)
