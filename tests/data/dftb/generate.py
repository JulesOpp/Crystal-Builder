"""Remake the DFTB+ fixtures in this folder from the real binary.

    python tests/data/dftb/generate.py /tmp/dftb-fixtures

Needs ``dftb+`` and ``modes`` on PATH and a Slater-Koster set that
covers Si, C and O (``resources/PTBP`` does).  Every input is written
by :mod:`xtal.ff.dftb.hsd`, so a fixture is also proof that DFTB+
accepted what the writer wrote.  Captured with DFTB+ 24.1.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from xtal import Lattice, Structure
from xtal.ff.dftb import hsd
from xtal.ff.dftb.calculator import DFTBOptions
from xtal.io.gen import gen_string

HERE = Path(__file__).resolve().parent
OPTIONS = DFTBOptions(method="scc", temperature=0.0)
CO2 = ("3 C\nC O\n1 1 0.0 0.0 0.0\n2 2 0.0 0.0 1.17\n"
       "3 2 0.0 0.0 -1.17\n")
MODES_INPUT = """Geometry = GenFormat {
  <<< "geo.gen"
}
Hessian = {
  <<< "hessian.out"
}
Atoms = 1:-1
DisplayModes = {
  PlotModes = 1:-1
  Animate = No
}
"""

#: What was run -> the name it is kept under here.
KEPT = {
    "scc/detailed.out": "si_scc_detailed.out",
    "scc/dos_Si.out": "si_dos_Si.out",
    "bands/band.out": "si_klines_band.out",
    "bands/dftb_in.hsd": "si_klines_dftb_in.hsd",
    "relax/stdout.txt": "si_relax_stdout.txt",
    "relax/geo_end.gen": "si_relax_geo_end.gen",
    "md/md.out": "si_md.out",
    "md/geo_end.xyz": "si_md_geo_end.xyz",
    "hessian/hessian.out": "co2_hessian.out",
    "hessian/vibrations.tag": "co2_vibrations.tag",
    "hessian/modes_stdout.txt": "co2_modes_stdout.txt",
    "charges/detailed.out": "quartz_mulliken_detailed.out",
}


def silicon():
    a = 5.431
    matrix = np.array([[0, a / 2, a / 2], [a / 2, 0, a / 2],
                       [a / 2, a / 2, 0]])
    return Structure.from_arrays(Lattice(matrix), ["Si", "Si"],
                                 [[0, 0, 0], [0.25, 0.25, 0.25]],
                                 space_group="P1")


def quartz():
    return Structure.from_arrays(
        Lattice.from_parameters(4.9134, 4.9134, 5.4052, 90, 90, 120),
        ["Si", "O"], [[0.4697, 0, 2 / 3], [0.4135, 0.2669, 0.7857]],
        space_group="P3221")


def run(work, name, geometry, symbols, *, program="dftb+", copy=(),
        **writer):
    folder = work / name
    folder.mkdir(parents=True)
    (folder / "geo.gen").write_text(geometry)
    for source in copy:
        shutil.copy(work / source, folder)
    (folder / "dftb_in.hsd").write_text(
        hsd.hsd_string(sorted(set(symbols)), OPTIONS, **writer))
    done = subprocess.run([program], cwd=folder, capture_output=True,
                          text=True)
    (folder / "stdout.txt").write_text(done.stdout)
    if done.returncode:
        raise SystemExit(f"{name} failed:\n{done.stdout[-2000:]}")
    return folder


def main(work: Path) -> None:
    shutil.rmtree(work, ignore_errors=True)
    si = silicon()
    strained = si.copy()
    strained.lattice = Lattice(si.lattice.matrix * 1.03)
    run(work, "scc", gen_string(si), ["Si"], k_points=(2, 2, 2),
        analysis=hsd.Analysis(mulliken=True, regions=("Si",)))
    run(work, "bands", gen_string(si), ["Si"],
        k_points=hsd.KLines(((1, (0.5, 0.5, 0.5)), (4, (0, 0, 0)),
                             (5, (0.5, 0, 0.5))), ("L", "G", "X")),
        read_charges=True, max_scc=1, copy=("scc/charges.bin",),
        analysis=hsd.Analysis(forces=False))
    run(work, "relax", gen_string(strained), ["Si"], k_points=(2, 2, 2),
        driver=hsd.Relax(lattice=True, max_steps=150))
    run(work, "md", gen_string(si), ["Si"], k_points=(2, 2, 2),
        driver=hsd.Dynamics(steps=10, write_every=5,
                            thermostat="none"))
    hessian = run(work, "hessian", CO2, ["C", "O"], periodic=False,
                  driver=hsd.SecondDerivatives(),
                  analysis=hsd.Analysis(forces=False))
    (hessian / "modes_in.hsd").write_text(MODES_INPUT)
    done = subprocess.run(["modes"], cwd=hessian, capture_output=True,
                          text=True, check=True)
    (hessian / "modes_stdout.txt").write_text(done.stdout)
    run(work, "charges", gen_string(quartz()), ["Si", "O"],
        k_points=(1, 1, 1), analysis=hsd.Analysis(mulliken=True))
    for source, kept in KEPT.items():
        shutil.copy(work / source, HERE / kept)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
