"""An ORCA input and its coordinates, written from a structure."""

from __future__ import annotations

import numpy as np

from xtal.core import bonding
from xtal.core.lattice import Lattice
from xtal.core.structure import Structure
from xtal.orca import input as orca
from xtal.orca.input import OrcaInput


def _lines(text):
    return [line for line in text.splitlines() if line.strip()]


def test_the_defaults_write_bp86_def2_svp_and_nothing_else(dry_ice):
    """The header asked for, and no block nobody asked for."""
    text = orca.render(OrcaInput(), "dry_ice.xyz")
    assert _lines(text) == ["! BP86 def2-SVP",
                            "*xyzfile 0 1 dry_ice.xyz"]


def test_an_odd_electron_count_refuses_a_singlet():
    assert "need an even multiplicity" in orca.check_spin(23, 1)


def test_a_radical_doublet_is_accepted():
    assert orca.check_spin(23, 2) == ""


def test_a_closed_shell_triplet_is_accepted():
    """O2 is a triplet: an even count with an odd multiplicity."""
    assert orca.check_spin(16, 3) == ""


def test_a_multiplicity_above_the_electron_count_is_refused():
    """H atom: one electron can be a doublet and nothing higher."""
    assert "at most 2" in orca.check_spin(1, 4)


def test_charge_changes_which_multiplicities_are_allowed(dry_ice):
    """Four CO2 are 88 electrons: a singlet neutral, a doublet as a
    cation -- the refusal follows the charge, not the atoms alone."""
    found = orca.cluster(dry_ice)
    assert orca.electrons(found.elements, 0) == 88
    neutral = OrcaInput(charge=0, multiplicity=1)
    cation = OrcaInput(charge=1, multiplicity=1)
    assert orca.problems(neutral, found)[0] == []
    refused, _ = orca.problems(cation, found)
    assert any("87 electrons" in r for r in refused)
    assert orca.problems(OrcaInput(charge=1, multiplicity=2),
                         found)[0] == []


def test_a_charge_beyond_the_electrons_is_refused():
    assert "can be at most" in orca.check_spin(-1, 1)


def test_a_molecule_across_a_cell_face_is_written_whole(dry_ice):
    """Pa-3 puts each oxygen at +-0.118 of its carbon, so half of them
    wrap to the far side of the cell.  Written as wrapped, the "C-O
    bond" of those is over seven angstroms."""
    found = orca.cluster(dry_ice)
    carbons = found.cart[[i for i, e in enumerate(found.elements)
                          if e == "C"]]
    oxygens = found.cart[[i for i, e in enumerate(found.elements)
                          if e == "O"]]
    nearest = np.linalg.norm(oxygens[:, None] - carbons[None],
                             axis=2).min(axis=1)
    assert len(nearest) == 8
    assert np.allclose(nearest, 1.149, atol=0.01)


def test_a_framework_is_written_with_a_caution(quartz):
    found = orca.cluster(quartz)
    assert found.periodic_pieces == 1
    _, cautions = orca.problems(OrcaInput(), found)
    assert any("periodic" in c for c in cautions)


def test_selected_atoms_only_writes_those_atoms(dry_ice):
    """One CO2 picked out of four, and whole."""
    graph = bonding.graph(dry_ice)
    carbon = 0
    molecule = [carbon] + graph.neighbors(carbon)
    found = orca.cluster(dry_ice, atoms=molecule)
    assert sorted(found.elements) == ["C", "O", "O"]
    c, o1, o2 = (found.cart[found.elements.index("C")],
                 *found.cart[[i for i, e in enumerate(found.elements)
                              if e == "O"]])
    assert np.allclose([np.linalg.norm(o1 - c), np.linalg.norm(o2 - c)],
                       1.149, atol=0.01)
    assert orca.electrons(found.elements, 0) == 22


def test_a_dummy_atom_never_counts_as_an_electron():
    """A centroid marker is chemistry to nobody: it is left out of
    the file and the count, and said."""
    marked = Structure.from_arrays(
        Lattice.cubic(10.0), ["C", "O", "O", "X"],
        [[0.5, 0.5, 0.5], [0.616, 0.5, 0.5], [0.384, 0.5, 0.5],
         [0.5, 0.6, 0.5]])
    found = orca.cluster(marked)
    assert found.elements == ["C", "O", "O"]
    assert found.markers == 1
    assert orca.problems(OrcaInput(), found)[0] == []


def test_zinc_with_a_small_pople_basis_is_a_caution_naming_zinc():
    """3-21GSP stops at argon; said before ORCA aborts on it."""
    sphalerite = Structure.from_arrays(
        Lattice.cubic(5.41), ["Zn", "S"],
        [[0, 0, 0], [0.25, 0.25, 0.25]], space_group="F-43m")
    found = orca.cluster(sphalerite)
    _, cautions = orca.problems(OrcaInput(basis="3-21GSP"), found)
    assert any("no functions for Zn" in c for c in cautions)
    _, cautions = orca.problems(OrcaInput(basis="def2-SVP"), found)
    assert not any("no functions" in c for c in cautions)


def test_an_unknown_functional_or_basis_is_refused(dry_ice):
    found = orca.cluster(dry_ice)
    refused, _ = orca.problems(
        OrcaInput(functional="NOTAFUNCTIONAL", basis="nope"), found)
    assert len(refused) == 2


def test_the_xyz_name_has_no_spaces():
    """*xyzfile takes the name unquoted."""
    assert orca.safe_name("MOF 5 (relaxed)") == "MOF_5_relaxed"
    assert orca.safe_name("   ") == "structure"


def test_xyzfile_has_no_closing_asterisk():
    """With *xyzfile a closing "*" is an ORCA input error."""
    text = orca.render(OrcaInput(charge=-1, multiplicity=2), "a.xyz")
    assert text.rstrip().splitlines()[-1] == "*xyzfile -1 2 a.xyz"
    assert text.count("*") == 1


def test_geom_block_only_appears_for_an_optimisation():
    single = orca.render(OrcaInput(max_iter=200), "a.xyz")
    assert "%geom" not in single
    opt = orca.render(OrcaInput(run="opt", max_iter=200), "a.xyz")
    assert "%geom\n  MaxIter 200\nend" in opt
    assert "! BP86 def2-SVP Opt" in opt


def test_scf_block_holds_maxiter_and_guess_only_when_set():
    """An empty %scf ... end is harmless but noise in every file."""
    assert "%scf" not in orca.render(OrcaInput(), "a.xyz")
    only_iter = orca.render(OrcaInput(scf_max_iter=300), "a.xyz")
    assert "%scf\n  MaxIter 300\nend" in only_iter
    both = orca.render(OrcaInput(scf_max_iter=300, scf_guess="PModel"),
                       "a.xyz")
    assert "%scf\n  MaxIter 300\n  Guess PModel\nend" in both


def test_scf_and_geom_maxiter_are_separate():
    text = orca.render(OrcaInput(run="opt", max_iter=50,
                                 scf_max_iter=500), "a.xyz")
    assert "%scf\n  MaxIter 500\nend" in text
    assert "%geom\n  MaxIter 50\nend" in text


def test_tddft_block_carries_nroots_and_triplets():
    text = orca.render(OrcaInput(tddft_nroots=10, tddft_triplets=True),
                       "a.xyz")
    assert "%tddft\n  nroots 10\n  triplets true\nend" in text
    off = orca.render(OrcaInput(tddft_nroots=0, tddft_triplets=True),
                      "a.xyz")
    assert "%tddft" not in off


def test_optts_with_cartesian_writes_both_keywords():
    text = orca.render(OrcaInput(run="optts", cartesian=True), "a.xyz")
    assert text.splitlines()[0] == "! BP86 def2-SVP OptTS COpt"


def test_cartesian_is_nothing_without_an_optimisation():
    text = orca.render(OrcaInput(cartesian=True), "a.xyz")
    assert "COpt" not in text


def test_a_composite_writes_no_basis():
    """r2SCAN-3c is fitted with its own basis; one beside it would
    replace that."""
    text = orca.render(OrcaInput(functional="R2SCAN-3C"), "a.xyz")
    assert text.splitlines()[0] == "! R2SCAN-3C"


def test_ri_writes_the_matching_auxiliary_basis():
    rij = orca.render(OrcaInput(functional="B3LYP", ri="RIJCOSX"),
                      "a.xyz")
    assert rij.splitlines()[0] == "! B3LYP def2-SVP RIJCOSX def2/J"
    jk = orca.render(OrcaInput(ri="RIJK"), "a.xyz")
    assert "RIJK def2/JK" in jk
    pople = orca.render(OrcaInput(basis="6-31G*", ri="RI"), "a.xyz")
    assert "RI AutoAux" in pople
    assert "def2/J" not in orca.render(OrcaInput(ri="NORI"), "a.xyz")


def test_a_double_hybrid_gets_its_correlation_auxiliary():
    text = orca.render(OrcaInput(functional="B2PLYP",
                                 basis="def2-TZVP"), "a.xyz")
    assert "def2-TZVP/C" in text.splitlines()[0]


def test_dispersion_twice_is_a_caution(dry_ice):
    found = orca.cluster(dry_ice)
    _, cautions = orca.problems(
        OrcaInput(functional="WB97X-D3BJ", dispersion="D3BJ"), found)
    assert any("counts it twice" in c for c in cautions)


def test_a_solvent_is_written_in_the_simple_line():
    text = orca.render(OrcaInput(solvation="CPCM", solvent="water"),
                       "a.xyz")
    assert text.splitlines()[0] == "! BP86 def2-SVP CPCM(water)"
    assert "%cpcm" not in text


def test_a_solvent_with_a_space_goes_in_the_cpcm_block():
    """CPCM(butanoic acid) is two words to ORCA's parser."""
    text = orca.render(OrcaInput(solvation="SMD",
                                 solvent="butanoic acid"), "a.xyz")
    assert text.splitlines()[0] == "! BP86 def2-SVP CPCM"
    assert '%cpcm\n  smd true\n  SMDsolvent "butanoic acid"\nend' \
        in text


def test_a_solvent_smd_does_not_know_is_refused(dry_ice):
    found = orca.cluster(dry_ice)
    refused, _ = orca.problems(OrcaInput(solvation="SMD",
                                         solvent="ammonia"), found)
    assert refused == ["SMD has no parameters for ammonia"]


def test_resources_are_written_only_when_set():
    assert "%pal" not in orca.render(OrcaInput(nprocs=1), "a.xyz")
    text = orca.render(OrcaInput(nprocs=8, maxcore_mb=4000), "a.xyz")
    assert "%pal\n  nprocs 8\nend" in text
    assert "%maxcore 4000" in text


def test_extra_keywords_and_blocks_are_written_as_given():
    block = "%output\n  Print[P_Hirshfeld] 1\nend"
    text = orca.render(OrcaInput(extra_keywords="NMR  KDIIS",
                                 extra_blocks=block), "a.xyz")
    assert text.splitlines()[0] == "! BP86 def2-SVP NMR KDIIS"
    assert block in text


def test_the_xyz_is_plain_four_columns(dry_ice):
    """No Lattice= -- a cluster has no cell, and ORCA reads the comment
    line as a comment, whatever is on it."""
    text = orca.xyz_text(orca.cluster(dry_ice), "dry ice")
    lines = text.splitlines()
    assert lines[0] == "12" and lines[1] == "dry ice"
    assert all(len(line.split()) == 4 for line in lines[2:])
    assert "Lattice" not in text


def test_deuterium_is_written_as_hydrogen():
    heavy = Structure.from_arrays(Lattice.cubic(10.0), ["O", "D", "D"],
                                  [[0.5, 0.5, 0.5], [0.596, 0.5, 0.5],
                                   [0.476, 0.593, 0.5]])
    assert orca.cluster(heavy).elements == ["O", "H", "H"]
