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
    assert "crystal-builder[orb]" in answer.reason


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
    since that is a global every other engine in the process reads."""
    answer = in_a_fresh_interpreter(
        "import json\n"
        "import numpy as np\n"
        "import torch\n"
        "from tests.conftest_ff import water\n"
        "from xtal.core import p1\n"
        "from xtal.ff.orb import calculator as orb\n"
        "before = str(torch.get_default_dtype())\n"
        "structure = water()\n"
        "engine = orb.ORBCalculator(structure, orb.ORBOptions(\n"
        "    device='cpu'))\n"
        "after = str(torch.get_default_dtype())\n"
        "cell = p1.expand(structure)\n"
        "matrix = np.asarray(structure.lattice.matrix, dtype=float)\n"
        "claimed = engine.compute(cell.cart, matrix).stress\n"
        "numeric = engine.numeric_stress(cell.cart, matrix, strain=1e-4)\n"
        "print(json.dumps({'claimed': np.asarray(claimed).tolist(),\n"
        "                  'numeric': np.asarray(numeric).tolist(),\n"
        "                  'before': before, 'after': after}))\n")
    assert np.asarray(answer["claimed"]) == pytest.approx(
        np.asarray(answer["numeric"]), abs=2e-3)
    assert answer["after"] == answer["before"]


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


def test_a_load_that_fails_is_a_sentence_naming_the_model(monkeypatch):
    """The panel's message is all the user gets."""
    monkeypatch.setattr(orb, "_device", lambda wanted: "cpu")
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(CalculatorError, match="not installed"):
        orb._build_model(orb.ORBOptions())
