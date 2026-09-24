"""The MatterSim engine: the arithmetic around the model, and the model.

The same bargain as ``tests/test_mace.py`` and ``tests/test_orb.py``:
almost everything runs against a stand-in ASE calculator, and the few
tests that need mattersim run it in a fresh interpreter so that torch
never loads into the suite's own process.  Those skip wherever
mattersim is not installed -- which includes the suite's usual
interpreter; the checkout's ``.venv`` has it.
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
from xtal.ff.mattersim import calculator as mattersim
from xtal.params import Availability

ase = pytest.importorskip("ase")

needs_mattersim = pytest.mark.skipif(
    importlib.util.find_spec("mattersim") is None,
    reason="mattersim is not installed")


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

    monkeypatch.setattr(mattersim, "_load_model", load)
    monkeypatch.setattr(mattersim, "_device", lambda wanted: "cpu")
    mattersim.forget_models()
    return made


# ------------------------------------------------------ the arithmetic

def test_the_energy_and_forces_come_back_in_kcal(stand_in):
    """What fails if MatterSim ever grows a compute of its own instead
    of the base class's."""
    from ase.calculators.lj import LennardJones

    structure = water()
    engine = mattersim.MatterSimCalculator(structure)
    cell = engine.cell
    result = engine.compute(cell.cart, structure.lattice.matrix)
    atoms = ase.Atoms(symbols=list(cell.elements),
                      positions=np.asarray(cell.cart),
                      cell=np.asarray(structure.lattice.matrix),
                      pbc=True)
    atoms.calc = LennardJones(rc=6.0)
    assert result.energy == pytest.approx(
        atoms.get_potential_energy() * mattersim.KCAL_PER_EV)
    assert result.forces == pytest.approx(
        np.asarray(atoms.get_forces()) * mattersim.KCAL_PER_EV)


def test_the_model_is_loaded_once_for_all_the_evaluations(stand_in):
    engine = mattersim.MatterSimCalculator(water())
    for _ in range(3):
        engine.compute(engine.cell.cart,
                       engine.structure.lattice.matrix)
    assert len(stand_in) == 1
    assert engine.calls == 3


def test_the_registry_builds_it_with_markers_held_back(stand_in):
    from xtal.commands.atoms import new_site
    from xtal.core import p1

    structure = water()
    structure.add_site(new_site("X", [0.4, 0.4, 0.4]))
    calculator = ENGINES.build("mattersim", structure)
    result = calculator.compute(np.asarray(p1.expand(structure).cart),
                                structure.lattice.matrix)
    assert result.forces.shape == (4, 3)
    assert np.allclose(result.forces[3], 0.0)


# ------------------------------------------------------- availability

def test_a_missing_package_names_the_extra_to_install(monkeypatch):
    monkeypatch.setattr(mattersim, "installed", lambda: False)
    answer = mattersim.available()
    assert not answer.ok
    assert install.command("mattersim") in answer.reason


def test_the_weights_are_said_to_be_a_download_of_their_size(
        monkeypatch):
    monkeypatch.setattr(mattersim, "installed", lambda: True)
    for model, _label in mattersim.MODEL_CHOICES:
        answer = mattersim.available(model=model)
        assert answer.ok
        assert "download" in answer.reason.lower()
        assert f"{mattersim.MODEL_SIZES[model]} MB" in answer.reason


def test_the_engine_is_in_the_registry_with_what_it_provides():
    engine = ENGINES.get("mattersim")
    assert {"forces", "stress", "periodic"} <= engine.provides
    assert [p.name for p in engine.options] == [
        "model", "device", "double_precision"]
    assert isinstance(engine.availability(), Availability)


def test_a_model_it_does_not_know_is_refused_before_loading(
        monkeypatch):
    monkeypatch.setattr(mattersim, "installed", lambda: True)
    assert not mattersim.available(model="MatterSim-v2").ok


def test_double_precision_is_the_default():
    """Measured on MOF-5: float32 gets the energy change of a 1e-4 A
    step wrong by 7 %."""
    assert mattersim.MatterSimOptions().double_precision
    param = next(p for p in mattersim.OPTIONS
                 if p.name == "double_precision")
    assert param.default is True


def test_an_apple_gpu_is_never_offered_or_chosen():
    """On macOS 13 MatterSim loads its weights onto mps without asking
    whether there is one, and the process dies of a segmentation
    fault; elsewhere mps cannot take float64."""
    assert "mps" not in dict(mattersim.DEVICE_CHOICES)
    assert mattersim._torch_device("cpu") == "cpu"


def test_an_apple_gpu_asked_for_by_name_is_a_sentence_not_a_crash(
        monkeypatch):
    """A saved setting or the CLI can still name it; the answer has to
    come from here, before mattersim is asked."""
    monkeypatch.setattr(mattersim, "_device", lambda wanted: wanted)
    with pytest.raises(CalculatorError, match="Apple GPU"):
        mattersim._build_model(mattersim.MatterSimOptions(device="mps"))


def test_a_load_that_fails_is_a_sentence_naming_the_package(
        monkeypatch):
    """The panel's message is all the user gets."""
    monkeypatch.setattr(mattersim, "_device", lambda wanted: "cpu")
    monkeypatch.setitem(sys.modules, "mattersim", None)
    monkeypatch.setitem(sys.modules, "mattersim.forcefield", None)
    with pytest.raises(CalculatorError, match="not installed"):
        mattersim._build_model(mattersim.MatterSimOptions())


# ------------------------------------------------------- the real model

@needs_mattersim
@pytest.mark.slow
def test_the_real_model_s_stress_agrees_with_a_numeric_one():
    """A stress that is quietly wrong relaxes a cell to the wrong
    volume.  MatterSim hands its stress through a ``stress_weight`` of
    its own, which is exactly where a unit could slip.  In the same
    run: torch's default dtype is where it was."""
    answer = in_a_fresh_interpreter(
        "import json\n"
        "import numpy as np\n"
        "import torch\n"
        "from tests.conftest_ff import water\n"
        "from xtal.core import p1\n"
        "from xtal.ff.mattersim import calculator as mattersim\n"
        "before = str(torch.get_default_dtype())\n"
        "structure = water()\n"
        "engine = mattersim.MatterSimCalculator(structure,\n"
        "    mattersim.MatterSimOptions(device='cpu'))\n"
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


@needs_mattersim
@pytest.mark.slow
def test_every_model_offered_is_a_name_mattersim_resolves():
    """mattersim knows its checkpoints by comparing strings in
    ``Potential.from_checkpoint``; a name it does not match is taken
    for a file path and fails at load.  Read from its source, so the
    5M model need not be downloaded to check it."""
    source = in_a_fresh_interpreter(
        "import inspect, json\n"
        "from mattersim.forcefield.potential import Potential\n"
        "print(json.dumps(inspect.getsource(\n"
        "    Potential.from_checkpoint)))\n")

    for name, _label in mattersim.MODEL_CHOICES:
        assert f'"{name.lower()}"' in source, name
