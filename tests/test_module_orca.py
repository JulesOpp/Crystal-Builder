"""Modules > ORCA > Input file: the files it writes, and what it
refuses to write."""

from __future__ import annotations

from xtal.cli import main
from xtal.core.lattice import Lattice
from xtal.core.structure import Structure
from xtal.io import write_cif
from xtal.modules import MODULES, Job


class _Folder:
    def __init__(self, path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)

    def log(self):
        return None


def _run(structure, folder, **params):
    _module, action = MODULES.find("orca.input")
    values = action.coerce({**action.defaults(), **params})
    return action.run(Job(structure=structure, params=values,
                          folder=folder))


def test_the_run_writes_the_input_and_the_xyz_side_by_side(
        tmp_path, dry_ice):
    run = tmp_path / "run"
    result = _run(dry_ice, _Folder(run), name="dry ice", freq=True)
    assert result.ok, result.message
    inp = (run / "dry_ice.inp").read_text()
    assert "! BP86 def2-SVP Freq" in inp
    assert inp.rstrip().endswith("*xyzfile 0 1 dry_ice.xyz")
    xyz = (run / "dry_ice.xyz").read_text().splitlines()
    assert xyz[0] == "12"
    assert "88 electrons, singlet" in result.message


def test_a_refused_spin_writes_nothing(tmp_path, dry_ice):
    """A folder holding an input ORCA will reject is one somebody
    submits to a queue."""
    run = tmp_path / "run"
    result = _run(dry_ice, _Folder(run), multiplicity=2)
    assert not result.ok
    assert "even" not in result.message and "odd" in result.message
    assert list(run.iterdir()) == []


def test_no_workspace_is_said_rather_than_raised(dry_ice):
    result = _run(dry_ice, None)
    assert not result.ok
    assert "--workspace" in result.message


def test_a_selection_behind_a_marker_is_the_atoms_it_named(tmp_path):
    """The markers are left out by the cluster, not by removing their
    sites -- which would renumber the cell, and "1 2 3" would then be
    the oxygens and nothing."""
    marked = Structure.from_arrays(
        Lattice.cubic(10.0), ["X", "C", "O", "O"],
        [[0.5, 0.6, 0.5], [0.5, 0.5, 0.5], [0.616, 0.5, 0.5],
         [0.384, 0.5, 0.5]])
    run = tmp_path / "run"
    result = _run(marked, _Folder(run), atoms="1 2 3", name="co2")
    assert result.ok, result.message
    atoms = [line.split()[0] for line in
             (run / "co2.xyz").read_text().splitlines()[2:]]
    assert sorted(atoms) == ["C", "O", "O"]


def test_cautions_are_said_and_the_file_still_written(tmp_path, quartz):
    run = tmp_path / "run"
    result = _run(quartz, _Folder(run), name="quartz")
    assert result.ok
    assert "1 caution" in result.message
    assert "periodic" in result.detail
    assert (run / "quartz.inp").exists()


def test_xtal_run_orca_input_takes_the_same_parameters(
        tmp_path, dry_ice, capsys):
    path = tmp_path / "dry_ice.cif"
    write_cif(dry_ice, path)
    root = tmp_path / "ws"
    assert main(["run", "orca.input", str(path), "--workspace",
                 str(root), "-p", "functional=B3LYP",
                 "-p", "basis=def2-TZVP", "-p", "run=opt",
                 "-p", "freq=true", "-p", "tddft_nroots=10",
                 "-p", "scf_max_iter=300", "-q"]) == 0
    written = list(root.rglob("*.inp"))
    assert len(written) == 1
    text = written[0].read_text()
    assert "! B3LYP def2-TZVP Opt Freq" in text
    assert "%tddft\n  nroots 10" in text
    assert "%scf\n  MaxIter 300\nend" in text
    xyz = written[0].with_suffix(".xyz")
    assert xyz.exists()
    assert f"*xyzfile 0 1 {xyz.name}" in text
