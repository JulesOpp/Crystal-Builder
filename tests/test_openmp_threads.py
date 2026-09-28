"""How many threads an OpenMP program is started with.

Measured with DFTB+ 25.1 on an M2 (four performance cores, four
efficiency cores), one single point from fresh charges:

    atoms   1 thread   4 threads   8 threads (OpenMP's own default)
      106     3.9 s      3.2 s       4.7 s     MOF-5, primitive
      138     4.4 s      3.6 s       6.4 s     ZIF-8
      648    61.6 s     30.8 s      35.7 s     MFU-4l

OpenMP divides a loop evenly and waits for the slowest thread, and on
a chip with two kinds of core the slowest is an efficiency core: all
eight was slower than four at every size, and at 138 atoms slower than
one.  So a program whose speed is OpenMP's is started with one thread
per performance core -- unless the user said otherwise.
"""

import os

import pytest

from tests.conftest_program import write_program
from xtal.modules import process


def test_a_mac_with_two_kinds_of_core_is_asked_for_its_fast_ones():
    asked = []

    def sysctl(name):
        asked.append(name)
        return {"hw.nperflevels": "2",
                "hw.perflevel0.physicalcpu": "4"}[name]

    assert process.performance_cores(sysctl=sysctl,
                                     platform="darwin") == 4
    assert "hw.perflevel0.physicalcpu" in asked


def test_one_kind_of_core_is_left_to_openmp():
    """An Intel Mac, or anything else: nothing was measured there, and
    OpenMP's own default is the answer it would give anyway."""
    assert process.performance_cores(
        sysctl=lambda name: {"hw.nperflevels": "1"}[name],
        platform="darwin") is None
    assert process.performance_cores(sysctl=lambda name: "2",
                                     platform="linux") is None


def test_a_sysctl_that_fails_is_left_to_openmp():
    def broken(name):
        raise OSError("no sysctl")

    assert process.performance_cores(sysctl=broken,
                                     platform="darwin") is None


def test_the_environment_asks_for_the_performance_cores(monkeypatch):
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.setattr(process, "performance_cores", lambda: 4)
    env = process.openmp_environment()
    assert env["OMP_NUM_THREADS"] == "4"
    assert env["PATH"] == os.environ["PATH"]


def test_a_thread_count_the_user_set_is_theirs(monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    monkeypatch.setattr(process, "performance_cores", lambda: 4)
    assert process.openmp_environment() is None


def test_with_nothing_to_change_the_program_inherits(monkeypatch):
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.setattr(process, "performance_cores", lambda: None)
    assert process.openmp_environment() is None


@pytest.mark.skipif(os.name == "nt", reason="the stand-in is a script")
def test_dftb_is_started_with_the_performance_cores(
        tmp_path, monkeypatch):
    from xtal import Lattice, Structure
    from xtal.ff.dftb import calculator as dftb

    parameters = tmp_path / "skf"
    parameters.mkdir()
    for pair in ("Si-Si", "Si-H", "H-Si", "H-H"):
        (parameters / f"{pair}.skf").write_text("1.0 10\n")
    script = write_program(tmp_path, "dftb+", (
        "import os, pathlib\n"
        "pathlib.Path('threads.txt').write_text("
        "os.environ.get('OMP_NUM_THREADS', 'unset'))\n"
        "pathlib.Path('detailed.out').write_text("
        "' Total Mermin free energy:  -1.0 H\\n\\n Total Forces\\n"
        "    1  0.0 0.0 0.0\\n    2  0.0 0.0 0.0\\n')\n"))
    monkeypatch.setenv("XTAL_DFTB", str(script))
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.setattr(process, "performance_cores", lambda: 4)
    two = Structure.from_arrays(
        Lattice.cubic(10.0), ["Si", "H"],
        [[0.0, 0.0, 0.0], [0.0, 0.0, 0.15]], space_group="P1")
    engine = dftb.build(two, parameter_directory=str(parameters))

    engine.compute(engine.cell.cart, two.lattice.matrix)

    assert (engine.directory / "threads.txt").read_text() == "4"
