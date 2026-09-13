"""DFTB+'s own relaxation and molecular dynamics, against a stand-in.

The stand-in relaxes by scaling the cell it is handed -- and breaks the
symmetry when told to -- so what is tested is the mapping back onto the
space group and what is reported about it.  Its standard output and the
MD files are DFTB+ 24.1's, from ``tests/data/dftb``.
"""

from pathlib import Path

import numpy as np
import pytest

from tests.conftest_program import write_program
from xtal import Lattice, Structure
from xtal.modules import MODULES, Job
from xtal.modules import process as process_module

DATA = Path(__file__).resolve().parent / "data" / "dftb"
A = 5.431

FAKE = r'''
import os, pathlib, shutil
text = pathlib.Path("dftb_in.hsd").read_text()
if "VelocityVerlet" in text:
    shutil.copy(DATA + "/si_md.out", "md.out")
    shutil.copy(DATA + "/si_md_geo_end.xyz", "geo_end.xyz")
    for line in pathlib.Path(DATA + "/si_md.out").read_text().splitlines():
        if line.startswith("MD Temperature"):
            print(line, flush=True)
else:
    rows = [r for r in pathlib.Path("geo.gen").read_text().splitlines()
            if r.strip()]
    count = int(rows[0].split()[0])
    atoms = rows[2:2 + count]
    if os.environ.get("FAKE_BREAK"):
        parts = atoms[0].split()
        parts[2] = str(float(parts[2]) + 0.05)
        atoms[0] = " ".join(parts)
    vectors = [" ".join(str(float(v) * 1.01) for v in r.split())
               for r in rows[3 + count:6 + count]]
    pathlib.Path("geo_end.gen").write_text("\n".join(
        rows[:2] + atoms + [rows[2 + count]] + vectors) + "\n")
    print(pathlib.Path(DATA + "/si_relax_stdout.txt").read_text())
    pathlib.Path("detailed.out").write_text("Geometry converged\n")
'''


@pytest.fixture
def parameters(tmp_path):
    directory = tmp_path / "skf"
    directory.mkdir()
    for a in ("Si", "O", "Na", "Cl"):
        for b in ("Si", "O", "Na", "Cl"):
            (directory / f"{a}-{b}.skf").write_text("1.0 10\n")
    return directory


@pytest.fixture
def fake_dftb(tmp_path, monkeypatch):
    process_module.clear_hints()
    body = f"DATA = {str(DATA)!r}\n" + FAKE
    monkeypatch.setenv("XTAL_DFTB",
                       str(write_program(tmp_path, "dftb+", body)))
    yield
    process_module.clear_hints()


class _Folder:
    def __init__(self, path):
        self.path = Path(path)

    def log(self):
        return None


def _run(name, structure, run, parameters, **params):
    _module, action = MODULES.find(f"dftb.{name}")
    values = action.coerce(params)
    values["hamiltonian"] = {"method": "scc",
                             "parameter_directory": str(parameters)}
    values["frozen"] = params.get("frozen", [])
    return action.run(Job(structure=structure, params=values,
                          folder=_Folder(run)))


def test_a_relaxed_cell_comes_back_in_its_space_group(
        fake_dftb, halite, parameters, tmp_path):
    """DFTB+ relaxes the P1 cell of halite; the answer is two sites in
    Fm-3m on the cell DFTB+ ended with."""
    run = tmp_path / "run"
    result = _run("relax", halite, run, parameters, lattice=True,
                  pressure=0.5)
    assert result.ok, result.detail
    written = (run / "dftb_in.hsd").read_text()
    assert "Driver = LBFGS {" in written
    assert "LatticeOpt = Yes" in written
    assert "Pressure [Pa] = 5e+08" in written

    adopted = result.structure
    assert adopted.space_group.short_name == "Fm-3m"
    assert adopted.n_sites == 2
    assert adopted.lattice.parameters[0] == pytest.approx(5.6402 * 1.01)
    assert "0.0000 A" in result.message
    steps = [b for b in result.report.curves if b.title == "Energy"]
    assert len(steps[0].x) == 63


def test_a_relaxation_that_leaves_the_group_is_not_adopted(
        fake_dftb, halite, parameters, tmp_path, monkeypatch):
    """One sodium moved off its special position: put back into Fm-3m
    its orbit splits, and adopting that would add atoms."""
    monkeypatch.setenv("FAKE_BREAK", "1")
    result = _run("relax", halite, tmp_path / "run", parameters)
    assert not result.ok
    assert result.structure is None
    assert "Fm-3m" in result.message
    assert "Reduce to P1" in result.detail
    assert (tmp_path / "run" / "geo_end.gen").is_file()


def test_the_distance_off_the_group_is_reported(fake_dftb, parameters,
                                                tmp_path, monkeypatch):
    """In P1 nothing can leave the group, and the deviation is what
    DFTB+ moved against itself: zero."""
    monkeypatch.setenv("FAKE_BREAK", "1")
    box = Structure.from_arrays(Lattice.cubic(6.0), ["Na", "Cl"],
                                [[0.1, 0.1, 0.1], [0.6, 0.5, 0.5]],
                                space_group="P1")
    result = _run("relax", box, tmp_path / "run", parameters)
    assert result.ok, result.detail
    rows = {row.label: row for row in result.report.tables[0].rows}
    assert float(rows["Largest move off the group"].value) == \
        pytest.approx(0.0, abs=1e-6)
    assert result.structure.sites[0].frac[0] == pytest.approx(0.15)


def test_frozen_sites_are_left_out_of_moved_atoms(
        fake_dftb, quartz, parameters, tmp_path):
    """Quartz's cell lists its three silicons first."""
    quartz.ensure_labels()
    label = quartz.sites[0].label
    run = tmp_path / "run"
    result = _run("relax", quartz, run, parameters, frozen=[label])
    assert result.ok, result.detail
    assert "MovedAtoms = 4:9" in (run / "dftb_in.hsd").read_text()

    free = _run("relax", quartz, tmp_path / "free", parameters,
                frozen=[label], freeze=False)
    assert "MovedAtoms = 1:-1" in \
        (tmp_path / "free" / "dftb_in.hsd").read_text()
    assert free.ok


def test_dynamics_returns_frames_for_the_transport_bar(
        fake_dftb, parameters, tmp_path):
    matrix = np.array([[0, A / 2, A / 2], [A / 2, 0, A / 2],
                       [A / 2, A / 2, 0]])
    silicon = Structure.from_arrays(Lattice(matrix), ["Si", "Si"],
                                    [[0, 0, 0], [0.25, 0.25, 0.25]],
                                    space_group="P1")
    run = tmp_path / "run"
    result = _run("md", silicon, run, parameters, steps=10,
                  write_every=5, thermostat="berendsen", coupling=0.1)
    assert result.ok, result.detail
    written = (run / "dftb_in.hsd").read_text()
    assert "Driver = VelocityVerlet {" in written
    assert "Thermostat = Berendsen {" in written

    trajectory = result.trajectory
    assert trajectory.n_frames == 3
    assert trajectory.elements == ("Si", "Si")
    assert trajectory[0].lattice is silicon.lattice
    assert [f.step for f in trajectory] == [0, 5, 10]
    titles = [c.title for c in result.report.curves]
    assert titles == ["Temperature", "Total energy"]
    assert result.structure is None             # nothing to adopt
