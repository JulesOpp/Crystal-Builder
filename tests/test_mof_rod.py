"""Rods: 1-periodic building blocks cut from a crystal, with their
points of extension and the shape those points make stated."""

import importlib.util
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from xtal.core import p1
from xtal.io import read_cif
from xtal.mof import rod
from xtal.mof.rod import Rod, RodError

ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / "resources" / "samples" / "prepared"


def shipped(name) -> Rod:
    return Rod.read(rod.shipped()[name])


def degrees(r: Rod) -> dict[int, int]:
    """How many shape edges meet each point of extension."""
    count = Counter()
    for a, b, _shift in r.edges:
        count[a] += 1
        count[b] += 1
    return {x: count[x] for x in r.connections}


def hydroxyl_angles(r: Rod) -> list[float]:
    """For each metal, the angle at it between its two mu-OH oxygens."""
    angles = []
    for m in r.metals:
        oh = []
        for j, shift in r.neighbours(m):
            if r.symbols[j] == "O" and any(
                    r.symbols[h] == "H" for h, _ in r.neighbours(j)):
                oh.append(r.positions[j] + [0, 0, shift * r.repeat]
                          - r.positions[m])
        if len(oh) == 2:
            cos = oh[0] @ oh[1] / np.linalg.norm(oh[0]) \
                / np.linalg.norm(oh[1])
            angles.append(float(np.degrees(np.arccos(cos))))
    return angles


def test_mof_74s_rod_has_three_metals_a_repeat_on_a_three_fold_screw():
    """MOF-74's rod is a 3_1 helix of zinc; a cut that lost a metal or
    the screw would build a different framework."""
    r = shipped("MOF-74_Zn")
    assert [r.symbols[m] for m in r.metals] == ["Zn"] * 3
    assert r.screw()[0] == 3
    assert r.repeat == pytest.approx(6.796, abs=0.01)
    assert r.hand in ("right", "left")


def test_mil_53s_hydroxyls_are_trans_on_every_metal_and_mof_303s_alternate():
    """The mu-OH is the rod's own chemistry and the block carries it:
    trans on every Cr of MIL-53, while MOF-303 alternates an Al with
    them cis and one, on an inversion centre, with them trans -- which
    is what makes one chain straight and the other a crankshaft."""
    assert hydroxyl_angles(shipped("MIL-53_Cr")) == \
        pytest.approx([180.0, 180.0], abs=2.0)
    found = sorted(round(a) for a in hydroxyl_angles(shipped("MOF-303_Al")))
    assert found == pytest.approx([92, 92, 180, 180], abs=2)


def test_a_mirrored_rod_is_the_other_hand_and_the_same_rod_otherwise():
    r = shipped("MOF-74_Zn")
    other = r.mirror()
    assert {r.hand, other.hand} == {"right", "left"}
    assert other.symbols == r.symbols
    assert other.bonds == r.bonds and other.edges == r.edges
    assert other.mirror().positions == pytest.approx(r.positions)


def test_a_rod_with_an_improper_operation_of_its_own_has_no_hand():
    """MOF-303 has inversion centres on its axis and MIL-53 is straight:
    neither has a mirror image that differs from it, so a hand for each
    rod would be a question about nothing."""
    assert shipped("MOF-303_Al").hand is None
    assert shipped("MIL-53_Cr").hand is None
    assert shipped("Ni2Cl2BTDD_Ni").is_chiral()


def test_a_rod_written_and_read_back_is_the_same_rod(tmp_path):
    r = shipped("Ni2Cl2BTDD_Ni")
    back = Rod.read(r.write(tmp_path / "again.xyz"))
    assert back.symbols == r.symbols
    assert back.positions == pytest.approx(r.positions, abs=1e-4)
    assert back.repeat == pytest.approx(r.repeat, abs=1e-4)
    assert back.bonds == r.bonds and back.edges == r.edges
    assert back.name == r.name


def test_a_rod_states_how_many_points_meet_one_end_of_a_linker(tmp_path):
    """dobdc chelates MOF-74's rod -- its carboxylate and phenolate cut
    at neighbouring ring carbons -- so two points meet one end; every
    other shipped rod meets a linker end at one.  Cut from the crystal,
    written and read back."""
    faces = {name: Rod.read(path).face
             for name, path in rod.shipped().items()}
    assert {n for n, f in faces.items() if f == 2} == {
        "MOF-74_Co", "MOF-74_Mg", "MOF-74_Ni", "MOF-74_Zn"}
    assert set(faces.values()) == {1, 2}
    back = Rod.read(shipped("MOF-74_Zn").write(tmp_path / "again.xyz"))
    assert back.face == 2


def test_each_shipped_rod_states_the_shape_its_net_needs():
    """The shape is chosen once, when the rod is cut, and the file is
    the record of it: every PoE meets one linker, so the shape's
    degrees are the net's coordination less one -- sra 4, msf 7 and 5,
    etb 3, xhh 5, snp 6."""
    assert set(degrees(shipped("MIL-53_Cr")).values()) == {3}
    mof74 = shipped("MOF-74_Zn")
    by_kind = {"".join(sorted(mof74.symbols[m]
                              for m, _ in mof74.members(x))): d
               for x, d in degrees(mof74).items()}
    assert by_kind == {"C": 6, "O": 4}
    assert set(degrees(shipped("Ni2Cl2BTDD_Ni")).values()) == {2}
    assert set(degrees(shipped("MOF-303_Al")).values()) == {4}
    assert set(degrees(shipped("MBDP_Co")).values()) == {5}


def test_co_bdps_rod_is_a_four_fold_helix_of_pyrazolate_bridged_metals():
    """Each Co bridged to the next by two pyrazolates, which stay whole
    on the rod as BTDD's triazolate does: four metals and eight points
    a 14.35 A repeat, each point hanging off a ring's C4 alone."""
    r = shipped("MBDP_Co")
    assert [r.symbols[m] for m in r.metals] == ["Co"] * 4
    assert r.repeat == pytest.approx(14.3502)
    assert len(r.connections) == 8 and r.face == 1
    assert r.screw() == (4, pytest.approx(90.0, abs=1.0))
    for x in r.connections:
        [(c, _)] = r.members(x)
        assert r.symbols[c] == "C"
    assert Counter(r.symbols)["N"] == 16


def test_a_shipped_chiral_rod_says_how_its_crystal_handed_it(tmp_path):
    """A rod cannot tell from itself whether its neighbours were its
    hand or its mirror, so the file says: MOF-74's and Ni2Cl2BTDD's
    alternate, Co(BDP)'s are one hand in P4_122.  An achiral rod has
    nothing to say; a swapped metal says what its parent did."""
    hands = {name: Rod.read(path).hands
             for name, path in rod.shipped().items()}
    assert {n for n, h in hands.items() if h == "same"} == {
        "MBDP_Co", "MBDP_Zn"}
    assert hands["MOF-74_Mg"] == hands["Ni2Cl2BTDD_Co"] == "alternating"
    assert hands["MIL-53_Cr"] == hands["MOF-303_Al"] == ""
    back = Rod.read(shipped("MBDP_Zn").write(tmp_path / "again.xyz"))
    assert back.hands == "same"


def test_btdds_triazolate_stays_whole_on_the_rod():
    """As MFU-4l's nodes keep it, so the BTDD linker shipped for MFU-4l
    meets this rod through one point bonded to two carbons."""
    r = shipped("Ni2Cl2BTDD_Ni")
    assert len(r.connections) == 3
    for x in r.connections:
        assert [r.symbols[m] for m, _ in r.members(x)] == ["C", "C"]
    assert Counter(r.symbols)["N"] == 9


def test_a_swapped_metal_says_its_geometry_was_not_relaxed():
    r = shipped("MOF-74_Mg")
    assert [r.symbols[m] for m in r.metals] == ["Mg"] * 3
    assert any("not relaxed" in note for note in r.notes)
    assert r.positions == pytest.approx(shipped("MOF-74_Zn").positions)


def test_a_metal_in_a_three_periodic_oxide_is_not_a_rod(rutile):
    """Rutile's chains share oxygens with their neighbours, so what
    surrounds a Ti repeats in three directions and is refused."""
    with pytest.raises(RodError, match="not a rod"):
        rod.from_structure(rutile, 0)


def test_a_rod_starts_at_a_metal(rutile):
    cell = p1.expand(rutile)
    oxygen = cell.elements.index("O")
    with pytest.raises(RodError, match="not a metal"):
        rod.from_structure(rutile, oxygen)


def test_the_shipped_rods_from_cod_samples_are_what_the_script_writes():
    """The files are written by ``scripts/rod_blocks.py`` and never by
    hand.  MOF-303's crystal is not shipped, so only the samples' --
    and of those, the ones cut with no preparation first."""
    spec = importlib.util.spec_from_file_location(
        "rod_blocks", ROOT / "scripts" / "rod_blocks.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    for name, path, prepared, shape, rules, _swaps, linker, hands in \
            script.RODS:
        if path is None or name.startswith("Ni2Cl2BTDD"):
            continue
        made = script.cut(path, prepared, shape, rules, name, hands)
        assert made.text() == rod.shipped()[name].read_text()
        text = script.linker_text(script.crystal(path, prepared), rules)
        assert text == rod.shipped_linkers()[linker].read_text()


def test_a_cut_rod_lies_in_one_repeat_along_its_axis():
    """Every heavy atom's group starts within the repeat, so a rod laid
    end to end tiles its axis rather than piling copies on one part."""
    mil53 = read_cif(PREPARED / "MIL-53.cif")
    r = rod.from_structure(mil53, p1.expand(mil53).elements.index("Cr"))
    metals = r.positions[r.metals]
    assert np.all(metals[:, 2] > -0.5)
    assert np.all(metals[:, 2] < r.repeat + 0.5)
    assert np.linalg.norm(metals[:, :2], axis=1) == pytest.approx(
        0.0, abs=0.05)
