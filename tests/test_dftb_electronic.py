"""Mulliken charges and orbitals: the runs, and the overlays they leave.

The stand-ins write what DFTB+ 24.1 and waveplot wrote -- quartz's
charges, and a cube of silicon's fourth state over a toy basis -- from
``tests/data/dftb``.  What is tested is our side: the inputs, which
state is asked for, the overlay, and how long the overlay lives.
"""

from pathlib import Path

import numpy as np
import pytest

from tests.conftest_program import write_program
from xtal import Lattice, Structure
from xtal.analysis import overlays
from xtal.modules import MODULES, Job
from xtal.modules import process as process_module
from xtal.modules.dftb_runs import electronic

DATA = Path(__file__).resolve().parent / "data" / "dftb"
A = 5.431

FAKE_DFTB = r'''
import pathlib, shutil
text = pathlib.Path("dftb_in.hsd").read_text()
pathlib.Path("seen.hsd").write_text(text)
if "MullikenAnalysis" in text:
    shutil.copy(DATA + "/quartz_mulliken_detailed.out", "detailed.out")
else:
    pathlib.Path("detailed.out").write_text(
        "Nr. of electrons (up):      8.00000000\n")
    pathlib.Path("band.out").write_text(
        " KPT 1 SPIN 1 KWEIGHT 1.0\n" + "".join(
            f"  {n} {-10.0 + n:.3f} 2.0\n" for n in range(1, 9)))
    pathlib.Path("detailed.xml").write_text("<xml/>")
    pathlib.Path("eigenvec.bin").write_bytes(b"0")
'''

FAKE_WAVEPLOT = r'''
import pathlib, re, shutil
text = pathlib.Path("waveplot_in.hsd").read_text()
level = re.search(r"PlottedLevels = (\d+)", text)[1]
shutil.copy(DATA + "/si_toy_orbital.cube", f"wp-1-1-{level}-real.cube")
'''


@pytest.fixture
def parameters(tmp_path):
    directory = tmp_path / "skf"
    directory.mkdir()
    for a in ("Si", "O"):
        for b in ("Si", "O"):
            (directory / f"{a}-{b}.skf").write_text("1.0 10\n")
    return directory


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    process_module.clear_hints()
    prefix = f"DATA = {str(DATA)!r}\n"
    monkeypatch.setenv("XTAL_DFTB", str(write_program(
        tmp_path, "dftb+", prefix + FAKE_DFTB)))
    monkeypatch.setenv("XTAL_WAVEPLOT", str(write_program(
        tmp_path, "waveplot", prefix + FAKE_WAVEPLOT)))
    yield
    process_module.clear_hints()


@pytest.fixture
def silicon():
    matrix = np.array([[0, A / 2, A / 2], [A / 2, 0, A / 2],
                       [A / 2, A / 2, 0]])
    return Structure.from_arrays(Lattice(matrix), ["Si", "Si"],
                                 [[0, 0, 0], [0.25, 0.25, 0.25]],
                                 space_group="P1")


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
    return action.run(Job(structure=structure, params=values,
                          folder=_Folder(run)))


# ------------------------------------------------------------ charges

def test_charges_are_a_table_per_site_and_an_overlay_per_atom(
        fakes, quartz, parameters, tmp_path):
    run = tmp_path / "run"
    result = _run("charges", quartz, run, parameters)
    assert result.ok, result.detail
    assert "MullikenAnalysis = Yes" in (run / "seen.hsd").read_text()
    overlay = result.overlay
    assert isinstance(overlay, overlays.AtomCharges)
    assert overlay.n_atoms == 9
    rows = result.report.tables[0].rows
    assert [row.texts[2] for row in rows] == ["3", "6"]
    assert rows[0].texts[3] == "+0.9120"
    assert (run / "charges.dat").read_text().count("\n") == 10


def test_the_colour_map_diverges_from_white_at_zero():
    charges = overlays.AtomCharges(np.array([-0.5, 0.0, 0.25, 0.5]))
    colors = charges.colors()
    assert tuple(colors[1]) == (245, 245, 245)
    assert colors[0][2] > colors[0][0]          # blue
    assert colors[3][0] > colors[3][2]          # red
    assert tuple(colors[3]) == (200, 40, 40)
    back = overlays.AtomCharges.from_dict(charges.to_dict())
    assert np.allclose(back.values, charges.values)


# ------------------------------------------------------------ orbitals

def test_the_homo_is_worked_out_from_the_electron_count(
        fakes, silicon, parameters, tmp_path):
    (parameters / "wfc.toy.hsd").write_text("Si {}\n")
    run = tmp_path / "run"
    result = _run("orbital", silicon, run, parameters, isovalue=0.03)
    assert result.ok, result.detail
    seen = (run / "seen.hsd").read_text()
    assert "WriteEigenvectors = Yes" in seen
    assert "WriteDetailedXML = Yes" in seen
    waveplot = (run / "waveplot_in.hsd").read_text()
    assert "PlottedLevels = 4" in waveplot       # 8 electrons, 2 a state
    assert str(parameters / "wfc.toy.hsd") in waveplot

    surface = result.overlay
    assert isinstance(surface, overlays.OrbitalSurface)
    assert surface.n_faces > 0
    assert set(np.unique(surface.signs)) == {-1, 1}
    rows = {row.label: row for row in result.report.tables[0].rows}
    assert rows["Energy"].value == "-6.000"


@pytest.mark.parametrize("params, expected", [
    ({"state": "homo", "offset": 2}, 2),
    ({"state": "lumo"}, 5),
    ({"state": "lumo", "offset": 1}, 6),
    ({"state": "index", "index": 7}, 7)])
def test_the_state_asked_for(params, expected):
    job = Job(params=params)
    assert electronic.chosen_level(
        job, "Nr. of electrons (up):  8.0\n") == expected


def test_a_parameter_set_without_a_basis_is_refused_by_name(
        fakes, silicon, parameters, tmp_path):
    run = tmp_path / "run"
    result = _run("orbital", silicon, run, parameters)
    assert not result.ok
    assert "wfc" in result.message
    assert not run.exists()


def test_the_lobes_are_inside_the_cell_they_were_marched_over(silicon):
    from xtal.io.cube import read_cube
    cube = read_cube(DATA / "si_toy_orbital.cube")
    surface = overlays.orbital_surface(cube, silicon.lattice, 0.03)
    assert surface.points.min() > -0.1
    assert surface.points.max() < 1.1
    assert surface.faces.max() == len(surface.points) - 1


# ------------------------------------------------------------ overlays

@pytest.fixture
def document(qtbot, quartz):
    pytest.importorskip("pytestqt")
    from xtalapp.document import Document
    quartz.ensure_labels()
    return Document(quartz)


def test_charges_are_not_an_edit_and_go_when_the_atoms_move(document):
    document.set_overlay(overlays.AtomCharges(np.linspace(-1, 1, 9)))
    assert document.charges is not None
    assert not document.modified
    assert not document.can_undo
    document.select([0])
    document.move_selection([0.01, 0.0, 0.0])
    assert document.charges is None


def test_charges_survive_a_save_and_an_orbital_does_not(document,
                                                        tmp_path):
    from xtalapp.document import Document
    document.set_overlay(overlays.AtomCharges(np.linspace(-1, 1, 9)))
    document.set_overlay(overlays.OrbitalSurface(
        points=np.zeros((3, 3)), faces=np.array([[0, 1, 2]]),
        signs=np.array([1])))
    path = document.save(tmp_path / "quartz.xtalproj")
    again = Document.load(path)
    assert again.charges is not None
    assert np.allclose(again.charges.values, np.linspace(-1, 1, 9))
    assert again.orbital is None


def test_the_scene_colours_atoms_by_charge_and_draws_the_lobes(quartz):
    from xtalapp.viewport.builder import build_scene
    from xtalapp.viewport.view_settings import ViewSettings
    settings = ViewSettings()
    charges = overlays.AtomCharges(np.array([1.0] * 3 + [-1.0] * 6))
    plain = build_scene(quartz, settings)
    coloured = build_scene(quartz, settings, charges=charges)
    assert not np.array_equal(plain.colors, coloured.colors)
    assert {tuple(c) for c in coloured.colors} == {(200, 40, 40),
                                                   (40, 80, 200)}
    lobes = overlays.OrbitalSurface(
        points=np.array([[0.1, 0.1, 0.1], [0.2, 0.1, 0.1],
                         [0.1, 0.2, 0.1]]),
        faces=np.array([[0, 1, 2]]), signs=np.array([-1]))
    drawn = build_scene(quartz, settings, orbital=lobes)
    assert drawn.n_pore_surface_faces == plain.n_pore_surface_faces + 1
    assert tuple(drawn.pore_surface_colors[-1]) == overlays.NEGATIVE
