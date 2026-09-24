"""The ORB-v3 engine: the arithmetic around the model, and the model.

The same bargain as ``tests/test_mace.py``, whose module docstring
gives the reasons: almost everything runs against a stand-in ASE
calculator in place of the model, because the half that can be got
wrong is this application's, and the few tests that need orb-models
run it in a fresh interpreter so that torch never loads into the
suite's own process.

Those skip wherever orb-models is not installed, which is most places:
it is an extra, and on Python 3.13 its pinned dm-tree has to be built.
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
from xtal.ff.orb import calculator as orb
from xtal.params import Availability

ase = pytest.importorskip("ase")

needs_orb = pytest.mark.skipif(
    importlib.util.find_spec("orb_models") is None,
    reason="orb-models is not installed -- "
           "pip install 'crystal-builder[orb]'")


def in_a_fresh_interpreter(program: str):
    """Run *program* in a new Python and return the JSON it prints
    last.  See the module docstring."""
    done = subprocess.run(
        [sys.executable, "-c", program],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture
def stand_in(monkeypatch):
    """A Lennard-Jones ASE calculator where the model would be."""
    from ase.calculators.lj import LennardJones

    made = []

    def load(options):
        made.append(options)
        return LennardJones(rc=6.0)

    monkeypatch.setattr(orb, "_load_model", load)
    monkeypatch.setattr(orb, "_device", lambda wanted: "cpu")
    orb.forget_models()
    return made


# ------------------------------------------------------ the arithmetic

def test_the_energy_and_forces_come_back_in_kcal(stand_in):
    """The same one factor as MACE, applied to both, because it is the
    same base class; this is what fails if ORB ever grows a compute of
    its own."""
    from ase.calculators.lj import LennardJones

    structure = water()
    engine = orb.ORBCalculator(structure)
    cell = engine.cell
    result = engine.compute(cell.cart, structure.lattice.matrix)

    atoms = ase.Atoms(symbols=list(cell.elements),
                      positions=np.asarray(cell.cart),
                      cell=np.asarray(structure.lattice.matrix),
                      pbc=True)
    atoms.calc = LennardJones(rc=6.0)
    assert result.energy == pytest.approx(
        atoms.get_potential_energy() * orb.KCAL_PER_EV)
    assert result.forces == pytest.approx(
        np.asarray(atoms.get_forces()) * orb.KCAL_PER_EV)


def test_the_model_is_loaded_once_for_all_the_evaluations(stand_in):
    engine = orb.ORBCalculator(water())
    for _ in range(3):
        engine.compute(engine.cell.cart,
                       engine.structure.lattice.matrix)
    assert len(stand_in) == 1
    assert engine.calls == 3


def test_the_registry_builds_it_with_markers_held_back(stand_in):
    """A marker is presented with no force on it and never reaches the
    model -- the registry does that for every engine."""
    from xtal.commands.atoms import new_site
    from xtal.core import p1

    structure = water()
    structure.add_site(new_site("X", [0.4, 0.4, 0.4]))
    calculator = ENGINES.build("orb", structure)
    result = calculator.compute(np.asarray(p1.expand(structure).cart),
                                structure.lattice.matrix)
    assert result.forces.shape == (4, 3)
    assert np.allclose(result.forces[3], 0.0)


# ------------------------------------------------------- availability

def test_a_missing_package_names_the_extra_to_install(monkeypatch):
    monkeypatch.setattr(orb, "installed", lambda: False)
    answer = orb.available()
    assert not answer.ok
    assert install.command("orb") in answer.reason


def test_the_weights_are_said_to_be_a_download(monkeypatch):
    monkeypatch.setattr(orb, "installed", lambda: True)
    answer = orb.available()
    assert answer.ok
    assert "download" in answer.reason.lower()


def test_the_engine_is_in_the_registry_with_what_it_provides():
    engine = ENGINES.get("orb")
    assert {"forces", "stress", "periodic"} <= engine.provides
    assert [p.name for p in engine.options] == [
        "model", "device", "double_precision"]
    assert isinstance(engine.availability(), Availability)


def test_only_conservative_models_are_offered():
    """A direct model's forces are not the gradient of its energy, and
    a line search that compares energies along a force that is not
    their gradient does not converge."""
    names = [name for name, _label in orb.MODEL_CHOICES]
    assert orb.DEFAULT_MODEL == names[0]
    assert all("conservative" in name for name in names)


def test_an_apple_gpu_is_never_asked_for():
    """orb-models 0.7.0 calls ``.cuda()`` on anything that is not the
    CPU, so mps fails at load: 'auto' must not pick it the way
    MACE's does."""
    assert "mps" not in dict(orb.DEVICE_CHOICES)
    assert orb._torch_device("cpu") == "cpu"


def test_double_precision_is_the_default():
    """Measured on MOF-5: float32's error on a 1e-4 A step is a third
    of the energy change a line search is reading."""
    assert orb.ORBOptions().double_precision
    param = next(p for p in orb.OPTIONS if p.name == "double_precision")
    assert param.default is True


def test_a_model_it_does_not_know_is_refused_before_loading(
        monkeypatch):
    monkeypatch.setattr(orb, "installed", lambda: True)
    assert not orb.available(model="orb-v3-direct-inf-omat").ok


# ------------------------------------------------------- the real model

@needs_orb
@pytest.mark.slow
def test_the_real_model_s_stress_agrees_with_a_numeric_one():
    """A stress that is quietly wrong relaxes a cell to the wrong
    volume and reports converging while it does it.  In the same run:
    loading the model leaves torch's default dtype where it found it,
    since that is a global every other engine in the process reads --
    and the model still works in its own precision with the global at
    float32, which it did not.

    Sheared quartz, not a molecule in a box: one water in 30 A has a
    stress smaller than the tolerance, so a sign or a factor of two
    passed.  A dense, strained crystal has one to get wrong."""
    answer = in_a_fresh_interpreter(
        "import json\n"
        "import numpy as np\n"
        "import torch\n"
        "from xtal import Lattice, Structure\n"
        "from xtal.core import p1\n"
        "from xtal.ff.orb import calculator as orb\n"
        "quartz = Structure.from_arrays(\n"
        "    Lattice.from_parameters(4.9134, 4.9134, 5.4052, 90, 90, 120),\n"
        "    ['Si', 'O'], [[0.4697, 0.0, 2 / 3],\n"
        "                  [0.4135, 0.2669, 0.7857]], space_group='P3221')\n"
        "cell = p1.expand(quartz)\n"
        "shear = np.eye(3) + np.array([[0.02, 0.03, 0], [0, -0.01, 0],\n"
        "                              [0, 0, 0.015]])\n"
        "matrix = np.asarray(quartz.lattice.matrix) @ shear\n"
        "cart = cell.frac @ matrix\n"
        "before = str(torch.get_default_dtype())\n"
        "engine = orb.ORBCalculator(quartz, orb.ORBOptions(device='cpu'))\n"
        "after = str(torch.get_default_dtype())\n"
        "result = engine.compute(cart, matrix)\n"
        "numeric = engine.numeric_stress(cart, matrix, strain=1e-4)\n"
        "f = result.forces / np.linalg.norm(result.forces)\n"
        "h = 1e-4\n"
        "slope = -(engine.compute(cart + h * f, matrix).energy\n"
        "          - engine.compute(cart - h * f, matrix).energy) / (2 * h)\n"
        "print(json.dumps({'claimed': np.asarray(result.stress).tolist(),\n"
        "                  'numeric': np.asarray(numeric).tolist(),\n"
        "                  'slope': slope,\n"
        "                  'along': float(np.sum(result.forces * f)),\n"
        "                  'before': before, 'after': after}))\n")
    claimed = np.asarray(answer["claimed"])
    assert np.abs(claimed).max() > 0.05          # there is a stress
    assert claimed == pytest.approx(np.asarray(answer["numeric"]),
                                    abs=2e-3)
    assert answer["after"] == answer["before"]
    # Double precision, measured rather than assumed: float32 geometry
    # gets this wrong by 2e-3 of the force.
    assert answer["slope"] == pytest.approx(answer["along"], rel=1e-6)


@needs_orb
@pytest.mark.slow
def test_every_model_offered_is_a_name_orb_knows():
    """Checked against orb-models' own table, so a rename upstream
    fails here rather than at load, minutes into a run."""
    known = in_a_fresh_interpreter(
        "import json\n"
        "from orb_models.forcefield.pretrained import "
        "ORB_PRETRAINED_MODELS\n"
        "print(json.dumps(sorted(ORB_PRETRAINED_MODELS)))\n")

    for name, _label in orb.MODEL_CHOICES:
        assert name in known, name


def test_every_graph_is_built_in_the_models_own_precision():
    """orb-models builds each input graph -- positions, edge vectors --
    in torch's *global* default dtype unless told otherwise, and its
    ASE calculator never tells it.  The loader puts that global back
    to float32 after loading a float64 model, as it should, so the
    float64 model was handed float32 geometry: along the force on
    MOF-74 the energy's slope then disagreed with the force by 2e-3 at
    a 1e-4 A step, against 6e-9 in float64 -- the error double
    precision was chosen to remove.  And it depended on which engine
    had loaded first, because MACE leaves the global at float64.

    So the dtype is given to the adapter, from the model's weights."""
    called = []

    class Weights:
        dtype = "float64-of-the-model"

    class Adapter:
        def from_ase_atoms(self, **kwargs):
            called.append(kwargs)

    class Model:
        adapter = Adapter()

        class model:                                     # noqa: N801
            @staticmethod
            def parameters():
                return iter([Weights()])

    pinned = orb._pin_dtype(Model())
    pinned.adapter.from_ase_atoms(atoms="the atoms")

    assert called == [{"atoms": "the atoms",
                       "output_dtype": Weights.dtype,
                       "graph_construction_dtype": Weights.dtype}]


def test_a_load_that_fails_is_a_sentence_naming_the_model(monkeypatch):
    """The panel's message is all the user gets."""
    monkeypatch.setattr(orb, "_device", lambda wanted: "cpu")
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(CalculatorError, match="not installed"):
        orb._build_model(orb.ORBOptions())
