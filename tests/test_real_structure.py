"""End to end on a real deposited structure.

MFU-4l (CCDC 776578) is a metal-organic framework: cubic Fm-3m, a 31 A
cell, 10 sites expanding to 648 atoms, an infinite framework, and a
Hall symbol its depositing software wrote incorrectly.  Synthetic
fixtures do not exercise any of that.
"""

import pathlib

import pytest

from xtal.core import bonding, p1, properties, symmetry
from xtal.core import selection as sel
from xtal.io import cif_string, read_cif, read_cif_string

SAMPLE = (pathlib.Path(__file__).resolve().parent.parent
          / "resources" / "samples" / "MFU4l.cif")

pytestmark = pytest.mark.skipif(not SAMPLE.exists(),
                                reason="sample structure not present")


@pytest.fixture(scope="module")
def mfu4l():
    return read_cif(SAMPLE)


def test_it_reads_as_the_published_structure(mfu4l):
    info = properties.info(mfu4l)
    assert info.space_group == "Fm-3m"
    assert info.space_group_number == 225
    assert mfu4l.lattice.lengths[0] == pytest.approx(31.0569, abs=1e-3)
    assert mfu4l.n_sites == 10
    assert info.n_atoms == 648
    assert info.formula == "C36H12Cl4N18O6Zn5"
    assert info.z == 8
    # an ultra-porous framework: barely denser than water vapour
    assert info.density == pytest.approx(0.559, abs=0.01)


def test_a_malformed_hall_symbol_is_repaired_not_swallowed(mfu4l):
    """The file says ``-F 4;2;3``.  The semicolons are wrong, the
    symbol is otherwise fine, and the reader has to say so."""
    warnings = mfu4l.meta.get("warnings", [])
    assert any("Hall symbol" in w for w in warnings)
    assert any("malformed" in w for w in warnings)
    assert mfu4l.space_group.hall == "-F 4 2 3"
    assert mfu4l.space_group.order == 192


def test_the_kuratowski_node_comes_out_right(mfu4l):
    """MFU-4l's node is one octahedral Zn surrounded by four
    tetrahedral Zn-Cl units.  Bond perception has to reproduce that
    from distances alone."""
    cell = p1.expand(mfu4l)
    graph = bonding.graph(mfu4l)
    coordination = graph.coordination()

    zinc = sorted(sel.by_element(cell, "Zn"))
    counts = sorted(int(coordination[k]) for k in zinc)
    assert counts.count(6) == 8              # central, octahedral
    assert counts.count(4) == 32             # peripheral, tetrahedral
    assert len(zinc) == 40

    fragments = graph.fragments()
    assert len(fragments) == 1
    assert fragments[0].periodic                     # it is a framework
    assert len(fragments[0]) == cell.n_atoms


def test_deposited_coordinates_need_a_realistic_tolerance(mfu4l):
    """The published coordinates are rounded to five decimals, which
    in a 31 A cell puts the Cl site 0.0006 A off its mirror plane.  At
    spglib's default tolerance the crystal therefore looks
    orthorhombic; it takes about 0.005 A to see the cubic group.  This
    is why the tolerance is a control in the UI and not a constant."""
    flat = symmetry.reduce_to_p1(mfu4l)
    assert flat.n_sites == 648

    assert symmetry.detect(flat, symprec=1e-5).number == 47   # Pmmm
    assert symmetry.detect(flat, symprec=0.01).number == 225  # Fm-3m


def test_symmetry_round_trip_on_648_atoms(mfu4l):
    """648 atoms back down to the 10 published sites, with the right
    Wyckoff letters.

    The file's origin is not spglib's standard one, so asymmetrising
    without standardising must refuse rather than return a structure
    in the wrong setting."""
    flat = symmetry.reduce_to_p1(mfu4l)

    refused, report = symmetry.asymmetrize(flat, symprec=0.01)
    assert not report.ok
    assert "standard setting" in report.message
    assert refused is flat

    back, report = symmetry.asymmetrize(flat, symprec=0.01,
                                        standardize_cell=True)
    assert report.ok, report.message
    assert back.space_group.number == 225
    assert back.n_sites == 10
    assert p1.expand(back).n_atoms == 648
    assert [site.wyckoff for site in back.sites] == [
        "32f", "32f", "8c", "96k", "96k", "48g", "96k", "96k", "48h",
        "96k"]
    assert properties.density(back) == pytest.approx(
        properties.density(mfu4l))


def test_cif_round_trip(mfu4l, tmp_path):
    text = cif_string(mfu4l)
    back = read_cif_string(text)
    assert back.space_group == mfu4l.space_group
    assert back.n_sites == mfu4l.n_sites
    assert properties.density(back) == pytest.approx(
        properties.density(mfu4l))
    # the repaired Hall symbol is what we write, so the copy is clean
    assert not back.meta.get("warnings")


def test_selection_and_editing_scale(mfu4l):
    """A 648-atom cell is where a per-atom Python loop would show; the
    selection helpers stay array-based."""
    document = pytest.importorskip("xtalapp.document")
    doc = document.Document(mfu4l.copy())
    doc.select_element("Cl")
    assert len(doc.selection.atoms) == 32
    assert doc.selection_is_orbit_complete()

    doc.select([min(sel.by_element(doc.cell, "Zn"))])
    doc.expand_selection("shell", 1)
    assert len(doc.selection.atoms) == 5     # Zn + 3 N + 1 Cl
    assert not doc.selection_is_orbit_complete()

    assert "deleted 1 site(s) (32 atoms)" in (
        doc.select_element("Cl") or doc.delete_selection())
    assert doc.cell.n_atoms == 616


def test_the_scene_builder_handles_it(mfu4l):
    from xtalapp.viewport.builder import build_scene
    from xtalapp.viewport.view_settings import ViewSettings

    scene = build_scene(mfu4l, ViewSettings())
    assert scene.n_atoms > 648               # plus boundary copies
    assert scene.n_bond_halves > 1000
    assert scene.n_cell_lines == 12


def test_it_relaxes_in_p1_instead_of_grinding(mfu4l):
    """The regression this pins is what a user hit: MFU-4l reduced to
    P1, L-BFGS, defaults.  The energy stuck at the fourth step and the
    reported force wandered between 1 and 600 kcal/mol/A for two
    hundred iterations without the geometry moving a thousandth of an
    Angstrom.

    The cause was the octahedral zinc of the Kuratowski node.  UFF
    types it ``Zn3+2``, which reads as sp3, so every Zn-N bond
    collected torsions -- and their i-j-k is N-Zn-N at exactly 180
    degrees, where the torsion gradient divides by a sine.  At the
    starting geometry that sine was zero and the term was skipped; one
    step later it was 1e-4, and the term switched on with a gradient
    four orders of magnitude larger than anything real.
    """
    from xtal.ff import ENGINES, optimize

    flat = symmetry.reduce_to_p1(mfu4l)
    calculator = ENGINES.build("uff", flat)
    result = optimize.run(calculator, flat, method="lbfgs",
                          max_steps=200)

    assert result.converged, result.summary()
    assert result.steps < 60
    assert result.energy_change < 0          # it went downhill
    # and it got there by moving atoms, not by giving up
    moved = ((result.frac - flat.frac) @ flat.lattice.matrix)
    assert 0.01 < abs(moved).max() < 2.0
