"""A slab along (hkl): the surface cell, the vacuum, and the bonds it
carries rather than perceives."""

import time

import numpy as np
import pytest

from xtal.core import bonding, p1
from xtal.core.slab import make_slab, surface_basis
from xtal.core.structure import Bond


def _normal(lattice):
    m = np.asarray(lattice.matrix, float)
    n = np.cross(m[0], m[1])
    return m, n / np.linalg.norm(n)


@pytest.mark.parametrize("hkl", [(1, 0, 0), (1, 1, 0), (1, 1, 1),
                                 (2, -1, 3), (0, 0, 2), (-1, 2, 0),
                                 (3, 3, 0)])
def test_the_surface_basis_spans_the_plane_and_has_determinant_one(hkl):
    """Unimodular, so a layer holds one cell's atoms exactly; and a
    common factor divided out, so (220) is the (110) plane."""
    basis = surface_basis(hkl)
    h = np.array(hkl) // np.gcd.reduce(np.abs(hkl))
    assert (h @ basis.T).tolist() == [0, 0, 1]
    assert round(np.linalg.det(basis)) == 1


def test_a_zero_plane_is_refused():
    with pytest.raises(ValueError, match="Miller"):
        surface_basis((0, 0, 0))


def test_a_rutile_110_slab_has_c_normal_to_the_plane_and_the_vacuum_asked_for(  # noqa: E501
        rutile):
    slab = make_slab(rutile, (1, 1, 0), layers=3, vacuum=15.0)
    m, normal = _normal(slab.structure.lattice)
    # c is along the normal and exactly slab + vacuum long.
    assert abs(m[2] @ normal) == pytest.approx(np.linalg.norm(m[2]))
    assert np.linalg.norm(m[2]) == pytest.approx(slab.thickness + 15.0)
    # d(110) of rutile, three times.
    assert slab.thickness == pytest.approx(3 * 4.594 / np.sqrt(2),
                                           rel=1e-4)
    # The in-plane cell is c by a*sqrt(2).
    lengths = sorted(np.linalg.norm(m[:2], axis=1))
    assert lengths == pytest.approx([2.959, 4.594 * np.sqrt(2)],
                                    rel=1e-4)
    heights = p1.expand(slab.structure).frac[:, 2] * np.linalg.norm(m[2])
    assert heights.max() < slab.thickness
    assert slab.structure.is_p1


def test_no_atom_sits_on_the_face_of_the_cell(halite):
    """The cut passes through a plane of atoms, and an atom on the
    cell's face is drawn at both faces: the bottom layer again at the
    top of the vacuum, floating."""
    slab = make_slab(halite, (1, 0, 0), layers=2, vacuum=15.0)
    height = np.linalg.norm(slab.structure.lattice.matrix[2])
    z = slab.structure.frac[:, 2] * height
    assert z.min() == pytest.approx(0.5)
    assert z.max() < 0.5 + slab.thickness
    # And the gap to the next slab up is the vacuum asked for.
    assert height - slab.thickness == pytest.approx(15.0)


@pytest.mark.parametrize("hkl, layers", [((1, 0, 0), 2), ((1, 1, 1), 3)])
def test_the_atom_count_is_layers_times_the_cell(halite, hkl, layers):
    slab = make_slab(halite, hkl, layers=layers, vacuum=10.0)
    assert slab.structure.n_sites == layers * p1.expand(halite).n_atoms


def test_every_atom_keeps_its_neighbours_inside_the_slab(quartz):
    """The cut changes which atoms there are, never where the inner
    ones sit: an atom in the middle layer has the same distances to
    its bonded neighbours as in the crystal."""
    slab = make_slab(quartz, (1, 0, 1), layers=3, vacuum=12.0)
    before = sorted(round(b.distance, 3)
                    for b in bonding.graph(quartz).bonds)
    out = slab.structure
    cell = p1.expand(out)
    matrix = np.asarray(out.lattice.matrix, float)
    after = {round(b.length(cell.frac, matrix), 3)
             for b in bonding.graph(out).bonds}
    assert after <= set(before)


def test_no_bond_crosses_the_vacuum(quartz):
    slab = make_slab(quartz, (0, 0, 1), layers=2, vacuum=12.0)
    out = slab.structure
    assert all(b.image[2] == 0 for b in bonding.graph(out).bonds)
    assert all(b.image[2] == 0 for b in out.bonds)
    assert slab.cut > 0


def test_the_carried_bonds_are_what_distance_would_find_on_a_clean_cut(
        rutile):
    """On a crystal nobody has edited the carried graph is exactly
    the perceived one -- the carrying is right, not merely cautious."""
    out = make_slab(rutile, (1, 1, 0), layers=3, vacuum=15.0).structure
    fresh = out.copy()
    fresh.clear_perceived()

    def keys(s):
        return sorted(b.key() for b in bonding.graph(s).bonds)

    assert keys(out) == keys(fresh)


def test_an_explicit_bond_inside_the_slab_is_carried(dry_ice):
    """A long bond drawn by hand, which distance would never find:
    it has to arrive in every copy of its molecule in the slab."""
    drawn = dry_ice.copy()
    drawn.add_bond(Bond(0, 0, (1, 0, 0), kind="explicit"))
    slab = make_slab(drawn, (0, 0, 1), layers=2, vacuum=10.0)
    explicit = [b for b in slab.structure.bonds if b.kind == "explicit"]
    assert explicit
    cell = p1.expand(slab.structure)
    matrix = np.asarray(slab.structure.lattice.matrix, float)
    lengths = {round(float(np.linalg.norm(
        (cell.frac[b.j] + b.image - cell.frac[b.i]) @ matrix)), 3)
        for b in explicit}
    assert lengths == {5.624}


def test_a_suppressed_bond_stays_suppressed_in_the_slab(rutile):
    """The suppression is a record, carried like any bond; left
    behind, the slab's first Recalculate would bring the bond back."""
    clean = make_slab(rutile, (0, 0, 1), layers=4, vacuum=10.0)
    rutile.add_bond(Bond(0, 1, kind="suppressed"))
    edited = make_slab(rutile, (0, 0, 1), layers=4, vacuum=10.0)
    assert any(b.kind == "suppressed" for b in edited.structure.bonds)
    assert (len(bonding.graph(edited.structure).bonds)
            < len(bonding.graph(clean.structure).bonds))
    again = edited.structure.copy()
    again.clear_perceived()
    assert (len(bonding.graph(again).bonds)
            == len(bonding.graph(edited.structure).bonds))


def test_making_a_slab_perceives_nothing(quartz, monkeypatch):
    """The slab arrives with its graph stored, so reading it asks
    distance nothing.  If this breaks, a slab silently re-bonds:
    every bond the user had taken away comes back, which is
    Recalculate Bonds' job."""
    slab = make_slab(quartz, (1, 1, 0), layers=2, vacuum=10.0)
    assert slab.structure.perceived is not None

    def refuse(*_args, **_kwargs):
        raise AssertionError("perceived")

    monkeypatch.setattr(bonding, "_search", refuse)
    assert len(bonding.graph(slab.structure).bonds) > 0


def test_the_shift_moves_the_cut_and_so_the_termination(rutile):
    one = make_slab(rutile, (1, 1, 0), layers=2, vacuum=10.0)
    other = make_slab(rutile, (1, 1, 0), layers=2, vacuum=10.0,
                      shift=0.5)
    assert one.structure.n_sites == other.structure.n_sites
    assert not np.allclose(np.sort(one.structure.frac[:, 2]),
                           np.sort(other.structure.frac[:, 2]))


def test_a_slab_is_one_undo_step(rutile):
    from xtal.commands.base import CommandStack
    from xtal.commands.cell import MakeSlab

    class Host:
        structure = rutile

    host = Host()
    stack = CommandStack()
    stack.push(MakeSlab((1, 1, 0), 3, 15.0), host)
    assert host.structure.n_sites == 18
    stack.undo(host)
    assert host.structure is rutile


def test_the_report_counts_the_cut_bonds(rutile):
    from xtal.commands.cell import MakeSlab

    _out, report = MakeSlab((1, 1, 0), 3, 15.0).preview(rutile)
    assert "(1 1 0) slab, 3 layers" in report.message
    assert "6 bonds cut at the surfaces" in report.message


def test_a_mfu4l_slab_is_quick():
    """Every bond visited once per layer, in Python: this holds it to
    a figure a preview can afford on every spinbox change."""
    from pathlib import Path

    from xtal.io import read_cif

    mfu4l = read_cif(Path(__file__).parent.parent / "resources"
                     / "samples" / "MFU4l.cif")
    started = time.perf_counter()
    slab = make_slab(mfu4l, (1, 1, 1), layers=2, vacuum=15.0)
    assert time.perf_counter() - started < 5.0
    assert slab.structure.n_sites == 2 * 648
