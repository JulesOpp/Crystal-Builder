"""The amorphous polymer builder as a module: xtal.modules.polymer."""

from __future__ import annotations

import pytest

from xtal.build import MISSING, installed
from xtal.core import bonding
from xtal.modules import MODULES, Job
from xtal.modules import polymer as polymer_module

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)

#: Three short chains: a build in about half a second.
SMALL = {"chains": 3, "length": 6}


def _run(**changes):
    _module, action = MODULES.find("polymer.build")
    params = dict(SMALL)
    params.update(changes)
    return action.run(Job(params=action.coerce(params)))


def test_the_polymer_builder_is_a_builder():
    """Listed with the builders and asking for no open structure: what
    it returns opens in a tab of its own."""
    module, action = MODULES.find("polymer.build")
    assert module.group == "build"
    assert action.needs_structure is False
    assert action.kind == "build"


def test_without_rdkit_the_entry_names_the_extra(monkeypatch):
    monkeypatch.setattr(polymer_module, "installed", lambda: False)
    availability = polymer_module.available()
    assert not availability.ok
    assert "build" in availability.reason


@needs_rdkit
def test_xtal_run_polymer_build_files_one_entry_with_stated_bonds(
        tmp_path, capsys):
    """``xtal run polymer.build`` files the model as one entry with one
    CIF, exactly as the window does, and the CIF carries the chains'
    bonds: reopened, nothing is perceived, so two hydrogens on
    neighbouring chains squeezed to 2.1 A stay unbonded."""
    from xtal.cli import main
    from xtal.io.cif_reader import read_cif

    workspace = tmp_path / "ws"
    assert main(["run", "polymer.build", "-p", "chains=3", "-p",
                 "length=6", "--workspace", str(workspace)]) == 0
    out = capsys.readouterr().out
    assert "What was built" in out
    cifs = [p for p in workspace.rglob("*.cif")
            if ".autosave" not in p.parts]
    assert len(cifs) == 1
    again = read_cif(cifs[0])
    assert again.perceived is not None
    assert len(bonding.graph(again).bonds) == 3 * (6 * 6 - 1 + 2)
    assert {s.element for s in again.sites} == {"C", "H"}


@needs_rdkit
def test_the_report_says_the_model_is_packed_not_equilibrated():
    """The report's note is the one thing a person must not miss, and
    its tables name the density reached beside the one asked."""
    result = _run()

    assert result.ok, result.message
    assert "packed, not equilibrated" in result.report.note
    titles = [t.title for t in result.report.tables]
    assert titles == ["What was built", "Chains"]
    density = next(r for r in result.report.tables[0].rows
                   if r.name == "Density")
    assert "asked 0.85" in density.note
    assert result.report.histograms[0].title == "End-to-end distance"


@needs_rdkit
def test_a_monomer_is_named_by_library_name_block_file_or_smiles(
        tmp_path):
    """Three ways in one box: the box's text is never sent to RDKit
    when it names a library entry or a file."""
    path = tmp_path / "ethylene.xyz"
    path.write_text(
        "8\n    6    7\n"
        "C    -0.7700 0.0000 0.0000\n"
        "C     0.7700 0.0000 0.0000\n"
        "H    -1.1300 1.0300 0.0000\n"
        "H    -1.1300 -0.5100 0.8900\n"
        "H     1.1300 1.0300 0.0000\n"
        "H     1.1300 -0.5100 0.8900\n"
        "X    -1.3000 -0.4400 -0.5000\n"
        "X     1.3000 -0.4400 -0.5000\n"
        "0 1 S\n0 2 S\n0 3 S\n1 4 S\n1 5 S\n0 6 S\n1 7 S\n",
        encoding="utf-8")

    by_name = polymer_module.monomer_of("Polyethylene")
    by_smiles = polymer_module.monomer_of("[*:1]CC[*:2]")
    by_file = polymer_module.monomer_of(str(path))

    assert by_name.name == "Polyethylene"
    assert by_file.name == "ethylene"
    assert by_name.formula == by_smiles.formula == by_file.formula


@needs_rdkit
def test_a_string_that_is_not_a_monomer_is_a_failed_run_naming_it():
    result = _run(monomer="CCO")
    assert not result.ok
    assert "connection point" in result.message


@needs_rdkit
def test_a_copolymer_without_a_second_monomer_is_a_failed_run():
    result = _run(composition="alternating")
    assert not result.ok
    assert "two monomers" in result.message


@needs_rdkit
def test_an_alternating_copolymer_has_both_monomers_in_turn():
    """PE and PVC alternating: half the units carry a chlorine."""
    result = _run(monomer_b="PVC", composition="alternating", length=6)

    assert result.ok, result.message
    chlorines = sum(s.element == "Cl" for s in result.structure.sites)
    assert chlorines == 3 * 3


@needs_rdkit
def test_an_oversized_recipe_is_refused_before_anything_grows():
    result = _run(chains=100, length=1000, max_atoms=1000)
    assert not result.ok
    assert "over the 1000" in result.message
