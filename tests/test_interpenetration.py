"""
Interpenetration, generated: ``xtal/analysis/interpenetrate.py``, the
command over it, and the MOF builder's parameter.

Every array here is checked by the detector that was in the tree first
-- :meth:`xtal.analysis.topology.Net.multiplicity`, through
:func:`~xtal.analysis.interpenetrate.copies` and the RCSR report -- so
a generator that put its copies in the wrong place, or joined them, is
caught by code that knows nothing about how they were made.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.test_mof_builder import needs_database
from xtal.analysis import interpenetrate, net_of, rcsr
from xtal.analysis.interpenetrate import InterpenetrationError
from xtal.commands.interpenetrate import Interpenetrate
from xtal.core import bonding
from xtal.core.lattice import Lattice
from xtal.core.structure import TOPOLOGY, Bond, Structure
from xtal.io import FORMATS
from xtal.mof import Catalog, MofError, library_root
from xtal.mof.build import BuildRequest, build

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"

needs_library = pytest.mark.skipif(
    library_root() is None,
    reason="the polydentate blocks are missing from this installation")


def pcu(a: float = 4.0) -> Structure:
    """One carbon per cell, bonded to its six neighbours by hand.

    Every edge is 4 A: longer than any C-C criterion, so the bonds
    exist only because they were drawn -- which is what makes it a
    test of whether the copies *carry* bonds rather than perceive
    them.
    """
    s = Structure.from_arrays(Lattice.cubic(a), ["C"], [[0.0, 0.0, 0.0]])
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        s.add_bond(Bond(0, 0, image))
    return s


def pcu_net(a: float = 4.0) -> Structure:
    """The same, drawn as a net rather than as chemistry."""
    s = Structure.from_arrays(Lattice.cubic(a), ["C"], [[0.0, 0.0, 0.0]])
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        s.add_bond(Bond(0, 0, image, kind=TOPOLOGY))
    return s


# ---------------------------------------------------- the candidates

def test_a_pcu_framework_interpenetrates_two_fold_at_the_body_centre():
    """The P surface's two labyrinths: the second pcu sits at the
    middle of the first one's cube, 3.46 A from every vertex of a 4 A
    cell, and nowhere else is as far from everything.

    A face-centre offset, 2 A from two vertices, winning here would
    mean the ranking reads the contacts backwards."""
    best = interpenetrate.best(pcu(), 2)
    assert best.name == "translation by 1/2, 1/2, 1/2"
    assert best.relation == "Class Ia"
    assert best.contact == pytest.approx(4.0 * np.sqrt(3) / 2)


def test_the_candidates_come_best_first_and_once_each():
    """The seven half-vectors of a cube are three kinds -- a face, an
    edge, the body -- and the three face centres are one placement
    turned.  Offering all three is offering a choice nobody can make,
    and the symmetry that merges them is *detected*: this structure is
    labelled P1."""
    found = interpenetrate.candidates(pcu(), 2)
    ia = [c for c in found if c.relation == "Class Ia"]
    assert [c.name for c in ia] == ["translation by 1/2, 1/2, 1/2",
                                    "translation by 0, 1/2, 1/2",
                                    "translation by 0, 0, 1/2"]
    contacts = [c.contact for c in found if not c.collides]
    assert contacts == sorted(contacts, reverse=True)


def test_mof5_finds_its_second_copy_a_quarter_along_the_diagonal():
    """2-fold MOF-5 is the second copy a quarter of the cell along the
    body diagonal, and no half-vector of its F-centred cell reaches it
    -- every one is a centring or puts a node on a node.  It is found
    as the inversion through an eighth-cell point, which for a
    centrosymmetric framework is that translation."""
    mof5 = FORMATS.read(SAMPLES / "MOF-5.cif")
    best = interpenetrate.best(mof5, 2)
    assert best.name == "translation by 1/4, 1/4, 1/4"
    assert best.relation == "Class II"
    assert best.contact > 3.0


def test_a_dense_framework_offers_no_candidate_and_says_so(halite):
    """Rock salt has nowhere to put a second copy: every placement
    lands an ion within bonding distance of one of the first copy's.
    The refusal names the best of them and the two atoms, because "no
    candidates" alone would look like the enumeration was broken."""
    found = interpenetrate.candidates(halite, 2)
    assert found and all(c.collides for c in found)
    with pytest.raises(InterpenetrationError,
                       match=r"no 2-fold placement leaves room.*Na"):
        interpenetrate.best(halite, 2)


def test_a_molecular_crystal_has_nothing_to_interpenetrate(dry_ice):
    """Four CO2 per cell and no framework: the copies of a molecule
    are not interpenetration, and the sentence says what would make
    it one."""
    with pytest.raises(InterpenetrationError, match="only molecules"):
        interpenetrate.candidates(dry_ice, 2)


def test_a_fold_outside_the_range_is_refused():
    with pytest.raises(InterpenetrationError, match="not offered"):
        interpenetrate.candidates(pcu(), 1)
    with pytest.raises(InterpenetrationError, match="not offered"):
        interpenetrate.candidates(pcu(), interpenetrate.MAX_FOLD + 1)


def test_three_fold_offers_the_translations_of_order_three():
    """Index-3 superlattices: the copies at a third and two thirds of
    one direction, and the best of them along the body diagonal."""
    best = interpenetrate.best(pcu(), 3)
    assert best.fold == 3
    assert best.name == ("translations by 1/3, 1/3, 2/3; "
                         "2/3, 2/3, 1/3")


def test_an_offset_is_read_as_three_fractions():
    assert interpenetrate.parse_offset("1/2, 1/2, 1/2") == (0.5, 0.5,
                                                             0.5)
    assert interpenetrate.parse_offset("0.25 0 0") == (0.25, 0.0, 0.0)
    with pytest.raises(InterpenetrationError, match="not an offset"):
        interpenetrate.parse_offset("1/2, 1/2")


# ---------------------------------------------------- building one

def test_an_offset_that_collides_is_refused_by_name():
    """A face centre of a 3 A pcu is 1.5 A from two vertices -- close
    enough for Recalculate Bonds to join the copies, which would make
    them one framework.  Refused with the two atoms named, and never
    built crowded."""
    placement = interpenetrate.translation(2, (0.5, 0.0, 0.0))
    with pytest.raises(InterpenetrationError,
                       match=r"C1? of one copy 1\.50 A from C.* of "
                             r"another.*Recalculate Bonds"):
        interpenetrate.build(pcu(3.0), placement)


def test_the_generator_agrees_with_the_detector():
    """The array counts two copies by the chemistry *and* by the net,
    and the RCSR report -- the Net panel's own -- names it 2-fold pcu.
    The copies are separate components of the quotient graph here,
    because the cell is the one each copy had; the detector sums them,
    which is what makes one copy in a doubled cell count the same."""
    for make in (pcu, pcu_net):
        out, _ = interpenetrate.build(
            make(), interpenetrate.best(make(), 2))
        if make is pcu:
            assert interpenetrate.copies(out) == 2
        else:
            report = rcsr.describe(net_of(out))
            assert report.copies == 2
            assert report.headline() == "2-fold interpenetrated pcu"


def test_the_copies_keep_the_bonds_they_had():
    """Six 4 A bonds per carbon, which no distance criterion draws:
    they are in the array because each copy carried its own, on the
    right atoms, and none joins one copy to the other.  Perceiving
    afresh instead would leave both copies with none."""
    out, _ = interpenetrate.build(pcu(), interpenetrate.best(pcu(), 2))
    bonds = bonding.graph(out).bonds
    assert len(bonds) == 6
    assert {(b.i, b.j) for b in bonds} == {(0, 0), (1, 1)}
    assert sorted(tuple(abs(v) for v in b.image) for b in bonds) == (
        sorted([(1, 0, 0), (0, 1, 0), (0, 0, 1)] * 2))


def test_the_perceived_graph_travels_with_the_copies():
    """MOF-5's 512 perceived bonds become 1024, and are the ones a
    fresh perception of the array would find: nothing is re-perceived,
    and nothing that is carried is wrong."""
    mof5 = FORMATS.read(SAMPLES / "MOF-5.cif")
    before = len(bonding.graph(mof5).bonds)
    out, _ = interpenetrate.build(mof5, interpenetrate.best(mof5, 2))
    assert out.perceived is not None
    carried = {b.key() for b in bonding.graph(out).bonds}
    assert len(carried) == 2 * before
    out.clear_perceived()
    assert {b.key() for b in bonding.graph(out).bonds} == carried


def test_a_structure_with_symmetry_comes_out_in_p1():
    """The array's group is not one copy's group, so it is not
    guessed: P1, and Find Symmetry is where the array's own is
    looked for."""
    s = pcu()
    s.set_space_group("Pm-3m")
    out, _ = interpenetrate.build(s, interpenetrate.best(s, 2))
    assert out.is_p1 and out.n_sites == 2


# ---------------------------------------------------- the command

def test_interpenetrating_is_one_undo_step():
    """One Ctrl+Z takes the copies away again, bonds and all."""
    pytest.importorskip("PySide6")
    from xtalapp.document import Document

    document = Document(pcu())
    report = document.interpenetrate(interpenetrate.best(pcu(), 2))
    assert report.ok and document.structure.n_sites == 2
    assert document.undo_label.startswith("Interpenetrate")
    document.undo()
    assert document.structure.n_sites == 1
    assert len(bonding.graph(document.structure).bonds) == 3


def test_a_refused_placement_leaves_nothing_to_undo():
    pytest.importorskip("PySide6")
    from xtalapp.document import Document

    document = Document(pcu(3.0))
    report = document.interpenetrate(
        interpenetrate.translation(2, (0.5, 0.0, 0.0)))
    assert not report.ok and "of one copy" in report.message
    assert not document.can_undo
    assert document.structure.n_sites == 1


def test_a_pore_network_is_dropped_by_interpenetrating():
    """A pore network measured on one framework is a picture of
    channels the second copy now fills."""
    pytest.importorskip("PySide6")
    from xtalapp.document import Document

    document = Document(pcu())
    document.pores = object()
    document.interpenetrate(interpenetrate.best(pcu(), 2))
    assert document.pores is None


def test_the_command_says_what_it_did():
    command = Interpenetrate(interpenetrate.best(pcu(), 2))
    out, report = command.preview(pcu())
    assert out.n_sites == 2
    assert report.message.startswith(
        "2-fold interpenetrated by translation by 1/2, 1/2, 1/2")


# ---------------------------------------------------- the builder

def test_interpenetration_is_parsed_as_a_count_of_copies():
    assert BuildRequest.parse("pcu", "N59", "E32").interpenetration == 1
    request = BuildRequest.parse("pcu", "N59", "E32",
                                 interpenetration="2")
    assert request.interpenetration == 2
    assert request.title() == "pcu-2fold-N59-E32"
    assert BuildRequest.parse("pcu", "N59", "E32",
                              interpenetration="3-fold"
                              ).interpenetration == 3
    with pytest.raises(MofError, match="interpenetrating copies"):
        BuildRequest.parse("pcu", "N59", "E32", interpenetration="0")


@needs_database
@needs_library
def test_the_builder_interpenetrates_mfu4l_two_fold(tmp_path):
    """Two MFU-4l frameworks on one pcu cell, the second at the body
    centre with 4.8 A to spare, and the build's own check -- the net
    read back off the file -- says 2-fold pcu, as asked.  Every joint
    is bonded in both copies."""
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    single = build(BuildRequest.parse("pcu", "MFU4l_Kuratowski",
                                      "MFU4l_BTDD"),
                   tmp_path / "one", Catalog.default())
    double = build(BuildRequest.parse("pcu", "MFU4l_Kuratowski",
                                      "MFU4l_BTDD",
                                      interpenetration="2"),
                   tmp_path / "two", Catalog.default())
    assert double.n_atoms == 2 * single.n_atoms
    assert double.joints == 2 * single.joints
    assert double.identified.copies == 2
    assert double.net_agrees
    assert "2-fold interpenetrated pcu, as asked" in double.verdict()
    assert interpenetrate.copies(double.structure) == 2
