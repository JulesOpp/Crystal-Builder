"""Rod MOFs built: rods on a pattern, a linker on every joint, the
bonds stated, and the net of the points of extension read back."""

from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pytest

from xtal.core import bonding, p1
from xtal.core.bonding import BondRules
from xtal.io import read_cif
from xtal.mof import rod, rodbuild
from xtal.mof.rodbuild import RodBuildError, RodRequest

ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / "resources" / "samples" / "prepared"


def built(name, pattern, **kw):
    return rodbuild.build(RodRequest(name, pattern, **kw))


@pytest.fixture(scope="module")
def mil_53():
    return built("MIL-53_Cr", "sql")


@pytest.fixture(scope="module")
def mof_74():
    return built("MOF-74_Zn", "hcb")


def per_metal(structure, metal):
    count = sum(1 for e in p1.expand(structure).elements if e == metal)
    return structure.lattice.volume / count, \
        structure.n_sites / count


def test_mil_53_on_sql_with_bdc_reads_back_as_sra(mil_53):
    """Trans mu-OH chains as flat zigzag ladders, joined by BDC on a
    rhombus: sra (Schoedel et al. 2016) -- read off the bonds drawn on
    the framework, not assumed from the request."""
    assert mil_53.net_name == "sra"
    assert mil_53.placement.worst < 0.05
    assert "sra" in mil_53.verdict()


@pytest.mark.slow
def test_mof_74_on_hcb_with_dobdc_reads_back_as_msf(mof_74):
    """The rod's stated shape plus dobdc's four ring junctions are msf;
    the alternating helices are the crystal's own (R-3)."""
    assert mof_74.net_name == "msf"
    assert mof_74.placement.net.hands == "alternating"
    assert {hand for _node, hand, _t, _z in mof_74.rods} == \
        {"right", "left"}


@pytest.mark.slow
def test_mof_74_is_built_within_3_percent_of_its_crystals_cell(mof_74):
    """Placed by arithmetic from the blocks alone, the framework has the
    crystal's rods 8.64 A apart, its volume per zinc and its formula."""
    crystal = read_cif(PREPARED / "MOF-74.cif")
    volume, atoms = per_metal(crystal, "Zn")
    built_volume, built_atoms = per_metal(mof_74.structure, "Zn")
    assert built_volume == pytest.approx(volume, rel=0.03)
    assert built_atoms == atoms
    assert mof_74.placement.spacing == pytest.approx(8.64, rel=0.03)
    assert mof_74.structure.lattice.parameters[2] == \
        pytest.approx(6.796, abs=1e-3)


@pytest.mark.slow
def test_mof_303_on_sql_with_pzdc_reads_back_as_xhh():
    """pzdc is bent -- its carboxylates leave 13.6 degrees off the line
    between them -- and a placement that asked every joint to be
    straight could not close MOF-303 at all (0.96 A off).  With the
    bend it closes at the crystal's angle with every other rod turned
    over (P2_1/c), and the net is xhh.  The angle is found, not given:
    the crystal's is 85.3 degrees."""
    made = built("MOF-303_Al", "sql")
    assert made.placement.angle_from == "from the rod's faces"
    assert min(made.placement.gamma, 180 - made.placement.gamma) == \
        pytest.approx(85.3, abs=1.0)
    assert made.placement.worst < 0.1
    assert made.placement.turned_over
    assert made.placement.spacing == pytest.approx(10.15, rel=0.02)
    assert made.net_name == "xhh"


@pytest.mark.slow
def test_a_three_fold_helix_rod_reads_eta_with_one_hand_and_etb_with_both():
    """The review's own example of hands making the net: Ni2Cl2BTDD's
    3_1 helices joined in threes are etb when neighbours alternate,
    as in the crystal, and eta when every rod is one hand."""
    both = built("Ni2Cl2BTDD_Ni", "hcb")
    one = built("Ni2Cl2BTDD_Ni", "hcb", hands="same")
    assert both.placement.net.hands == "alternating"
    assert both.net_name == "etb"
    assert one.net_name == "eta"
    assert {hand for _n, hand, _t, _z in one.rods} == {"right"}
    # Cut where the rod was cut, BTDD's carbons meet the triazolate's
    # at the crystal's 1.4 A; measured from its own side they were 1.65.
    assert both.longest_joint < 1.45


def test_a_rod_builds_with_its_bonds_stated_and_nothing_perceived(
        mil_53, tmp_path):
    """The rods', the linkers' and the joints' bonds are the stored
    graph; a clean build states exactly what perception would find, and
    a save keeps the graph and the net, so reopening perceives
    nothing."""
    s = mil_53.structure
    stated = {b.key() for b in bonding.perceive(s)}
    fresh = {b.key() for b in bonding.perceive(
        s, BondRules.from_dict(s.bond_rules))}
    assert stated == fresh
    cell = p1.expand(s)
    graph = bonding.graph(s)
    for metal in (i for i, e in enumerate(cell.elements) if e == "Cr"):
        assert len(graph.bonds_of(metal)) == 6
    assert mil_53.joints == 4 and mil_53.longest_joint < 1.5
    from xtal.io.cif_writer import write_cif

    path = write_cif(s, tmp_path / "mil.cif", perception=True)
    again = read_cif(path)
    assert {b.key() for b in bonding.perceive(again)} == stated
    from xtal.mof.build import check_net

    assert check_net(again).name == "sra"


def test_a_rod_mof_repeats_along_its_rods_with_the_same_net():
    one = built("MIL-53_Cr", "sql", angle=76.0)
    two = built("MIL-53_Cr", "sql", angle=76.0, repeat=(1, 1, 2))
    assert two.n_atoms == 2 * one.n_atoms
    assert two.structure.lattice.parameters[2] == \
        pytest.approx(2 * one.structure.lattice.parameters[2])
    assert two.joints == 2 * one.joints
    assert two.net_name == "sra"


def test_a_shipped_linker_is_the_one_its_crystal_gives():
    """BDC is cut out of MIL-53 where the rod was and kept whole, its
    carboxylates with it; made a linker, its X sits where the rod's
    does, so the joint is the crystal's C-C."""
    from xtal.mof import donors
    from xtal.mof.trimer import Block

    crystal = read_cif(PREPARED / "MIL-53.cif")
    whole = rod.linker_from_structure(crystal, whole=True)
    assert whole.text() == rod.shipped_linkers()["BDC"].read_text()
    assert sorted(whole.symbols) == sorted(["C"] * 8 + ["H"] * 4
                                           + ["O"] * 4)
    bare = rod.linker_from_structure(crystal)
    made = donors.as_linker(Block.parse(whole.text()))
    assert made.kinds == ("carboxylate", "carboxylate")

    def xs(block):
        at = np.asarray(block.positions)[block.connections]
        return at - at.mean(axis=0)

    gaps = np.linalg.norm(xs(made)[:, None] - xs(bare)[None], axis=2)
    assert gaps.min(axis=1).max() < 2e-3


def test_a_rod_without_a_linker_of_its_own_must_be_told_one(tmp_path):
    made = rod.Rod.read(rod.shipped()["MIL-53_Cr"])
    path = made.write(tmp_path / "mine.xyz")
    with pytest.raises(RodBuildError, match="name one"):
        _ = RodRequest(str(path), "sql").linker_name
    assert RodRequest(str(path), "sql", "BDC").title() == "mine-sql-BDC"
    with pytest.raises(RodBuildError, match="no linker called"):
        rodbuild.build(RodRequest("MIL-53_Cr", "sql", "nothing"))


def test_what_cannot_be_built_is_refused_by_name():
    with pytest.raises(RodBuildError, match="odd rings"):
        rodbuild.build(RodRequest("Ni2Cl2BTDD_Ni", "hxl",
                                  hands="alternating"))
    with pytest.raises(RodBuildError, match="must divide"):
        rodbuild.build(RodRequest("MIL-53_Cr", "hcb"))
    with pytest.raises(RodBuildError, match="one of"):
        RodRequest.parse("MIL-53_Cr", "dia")
    with pytest.raises(RodBuildError, match="number of degrees"):
        RodRequest.parse("MIL-53_Cr", "sql", angle="wide")


def test_the_rod_entry_builds_from_its_parameters(tmp_path):
    from xtal.modules.job import Job
    from xtal.modules.registry import MODULES

    _module, action = MODULES.find("mof.rod")
    result = action.run(Job(params={"rod": "MIL-53_Cr", "pattern": "sql",
                                    "angle": "76"}))
    assert result.ok, result.message
    assert "sra" in result.message
    titles = [block.title for block in result.report.blocks]
    assert titles == ["What was built", "Each rod", "How well it closed",
                      "The net that came out"]
    failed = action.run(Job(params={"rod": "MIL-53_Cr",
                                    "pattern": "hcb"}))
    assert not failed.ok and "must divide" in failed.message
    assert np.isfinite(float(result.report.blocks[2].rows[0].value))


def test_a_rod_saved_from_ni2cl2btdd_rebuilds_its_own_framework(tmp_path):
    """The deposited file, ConQuest's symmetry copies and all, cut from
    a prepared copy: the rod and its linker go into the workspace's
    blocks, and a build naming only the rod finds both, closes, and
    reads back as the crystal's own etb with the rods 12.84 A apart.
    A rod cut from the raw sites, or a linker taken from anywhere
    else, would not meet the crystal's lengths."""
    raw = read_cif(ROOT / "resources" / "samples" / "Ni2Cl2BTDD.cif")
    before = raw.n_sites
    saved = rod.save_block(raw, tmp_path, name="mine")
    assert raw.n_sites == before                    # not touched
    assert saved.path == tmp_path / "rods" / "mine.xyz"
    assert saved.linker_path == tmp_path / "rods" / "linkers" / "mine.xyz"
    assert any("symmetry copies" in s for s in saved.prepared)
    assert rod.Rod.read(saved.path).linker == "mine"
    assert "mine" in rod.saved(tmp_path)

    outcome = rodbuild.build(RodRequest("mine", "hcb"),
                             folders=(tmp_path,))
    assert outcome.net_name == "etb"
    assert outcome.placement.worst < 0.05
    assert outcome.placement.spacing == pytest.approx(12.84, abs=0.05)
    assert not outcome.overlaps
    assert outcome.request.title() == "mine-hcb-mine"
    # The run names the build before it builds: the rod's own linker
    # has to be known by then, or the entry refused a saved rod.
    request = RodRequest("mine", "hcb").resolved((tmp_path,))
    assert request.title() == "mine-hcb-mine"


def test_a_saved_rod_is_cut_where_the_seed_is_and_named_apart(tmp_path):
    """The seed is carried through the prepared copy by where it is,
    and a shipped rod's name is refused: a build naming it would take
    the shipped one."""
    structure = read_cif(PREPARED / "MIL-53.cif")
    with pytest.raises(rod.RodError, match="shipped rod's name"):
        rod.save_block(structure, tmp_path, name="MIL-53_Cr")
    cell = p1.expand(structure)
    last = max(i for i, s in enumerate(cell.elements) if s == "Cr")
    saved = rod.save_block(structure, tmp_path, last, name="cr")
    assert saved.rod.repeat == pytest.approx(
        rod.Rod.read(rod.shipped()["MIL-53_Cr"]).repeat, abs=1e-3)
    with pytest.raises(rod.RodError, match="not a metal"):
        rod.save_block(structure, tmp_path,
                       cell.elements.index("O"), name="o")


def test_a_linker_with_one_point_an_end_on_mof_74_is_refused_by_name():
    """BDC on MOF-74 used to be placed, a carboxylate meeting one X of
    each chelate, and fail at the joints 2 A off naming neither."""
    with pytest.raises(RodBuildError,
                       match="MOF-74_Zn meets each end of a linker at "
                             "2 points.*BDC has 1 at each end"):
        built("MOF-74_Zn", "hcb", linker="BDC")
    with pytest.raises(RodBuildError, match="dobdc has 2 at each end"):
        built("MIL-53_Cr", "sql", linker="dobdc")


#: A biphenyl with an X on C3 and C4 of each ring, as RDKit embeds it
#: (32 degrees between the rings): dobpdc and pc-dobpdc both, until
#: something says which X is the carboxylate.
BIPHENYL_CORE = ROOT / "tests" / "data" / "rod_biphenyl_core.xyz"


def carboxylates_by_place(structure):
    """``(para, meta)``: how many carboxylate carbons hang off a ring
    carbon para to the biaryl bond, and how many off one meta."""
    el = list(p1.expand(structure).elements)
    near = defaultdict(set)
    for bond in bonding.perceive(structure):
        i, j = bond.key()[:2]
        near[i].add(j)
        near[j].add(i)

    def carbon(a):
        return el[a] == "C"

    aryl = {a for a in range(len(el)) if carbon(a)
            and all(el[n] != "O" for n in near[a])
            and sum(carbon(n) for n in near[a]) == 3}
    biaryl = {a for a in aryl if near[a] & aryl}

    def steps(a):
        seen, queue = {a: 0}, deque([a])
        while queue:
            x = queue.popleft()
            if x in biaryl:
                return seen[x]
            for n in near[x]:
                if carbon(n) and n not in seen:
                    seen[n] = seen[x] + 1
                    queue.append(n)
        return None

    found = [0, 0]
    for c in range(len(el)):
        if carbon(c) and sum(el[n] == "O" for n in near[c]) == 2:
            ring = next(n for n in near[c] if carbon(n))
            found[steps(ring) == 2] += 1
    return tuple(found)


@pytest.mark.slow
def test_every_joint_pairs_a_linkers_points_the_same_way():
    """A biphenyl core's C4 X is the carboxylate at every joint or at
    none: one isomer a framework.  Paired joint by joint, half the
    ends came out dobpdc and half pc-dobpdc, 1.27 A apart where they
    met."""
    outcome = built("MOF-74_Mg", "hcb", linker=str(BIPHENYL_CORE))
    assert carboxylates_by_place(outcome.structure) in ((6, 0), (0, 6))
    assert outcome.closest > 1.7
    assert outcome.net_name == "msg"


def test_mof_74_with_dobdc_builds_as_it_did(mof_74):
    """dobdc's carboxylate and phenolate X were already paired the
    same way at every joint; one choice for the whole build keeps it,
    joints at the crystal's 1.46-1.48 A (the shipped dobdc is written
    whole, and its X come back from its donors to 1e-3 A)."""
    assert 1.45 < mof_74.longest_joint < 1.49
    assert mof_74.closest == pytest.approx(2.054, abs=0.002)


@pytest.fixture(scope="module", params=[("dobpdc", (0, 6)),
                                        ("pc_dobpdc", (6, 0))],
                ids=["dobpdc", "pc-dobpdc"])
def drawn_whole(request):
    """MOF-74's rod with each isomer as RDKit drew it, whole, and where
    its carboxylates should come out."""
    name, place = request.param
    outcome = built("MOF-74_Mg", "hcb",
                    linker=str(ROOT / "tests" / "data"
                               / f"rod_{name}_whole.xyz"))
    return outcome, place


@pytest.mark.slow
def test_dobpdc_and_pc_dobpdc_drawn_whole_build_as_two_isomers(
        drawn_whole):
    """Drawn with their carboxylates and phenols, each X goes on the
    rod point of its own donor: dobpdc's carboxylates meta to the
    biaryl bond at every joint, pc-dobpdc's para."""
    outcome, place = drawn_whole
    assert carboxylates_by_place(outcome.structure) == place


@pytest.mark.slow
def test_a_drawn_biphenyl_is_turned_to_join_the_rods_at_bond_lengths(
        drawn_whole):
    """RDKit drew dobpdc's rings 32 degrees apart and pc-dobpdc's donors
    on one side: built so, the joints were 2.28 A and pc-dobpdc read a
    net that is not in the RCSR.  Turned about the biaryl bond, both
    are msg with joints of the crystal's lengths and nothing
    overlapping."""
    outcome, _place = drawn_whole
    assert outcome.net_name == "msg"
    assert outcome.longest_joint < 1.55
    assert outcome.closest > 1.7 and not outcome.overlaps


@pytest.mark.slow
def test_a_linker_between_alternating_rods_is_placed_centrosymmetric(
        drawn_whole):
    """MOF-74's neighbouring rods are each other's mirror images, so a
    linker between them sits on an inversion centre: its ends a half
    turn apart, to within a turning step and the build's refinement."""
    import math

    outcome, _place = drawn_whole
    assert outcome.placement.posed is not None
    assert math.degrees(outcome.placement.linker.twist) > 170


def test_a_linker_with_donors_the_rod_lacks_is_refused_by_name():
    """Hydroquinone's phenolates on MIL-53's carboxylate points, said
    before anything is fitted rather than as a joint with no pairing."""
    linker = str(ROOT / "tests" / "data" / "rod_hydroquinone_whole.xyz")
    with pytest.raises(RodBuildError,
                       match="rod_hydroquinone_whole brings a "
                             "phenolate to each end, where MIL-53_Cr "
                             "has a carboxylate"):
        built("MIL-53_Cr", "sql", linker=linker)


@pytest.mark.slow
def test_rods_of_one_hand_leave_a_linkers_twist_free():
    """Zn2(dobpdc) (P3_121) has every rod one hand, a two-fold across
    each linker, and the linker's ends 128 degrees apart.  The twist
    was held at 0 for one hand, which built dobpdc on MOF-74's rod with
    a 19.99 A cell; spread over the twists and the best kept, it
    closes within 1 % of the crystal's 21.657 A, in the crystal's
    group."""
    from xtal.core import symmetry

    outcome = built("MOF-74_Mg", "hcb", hands="same",
                    linker=str(ROOT / "tests" / "data"
                               / "rod_dobpdc_whole.xyz"))
    assert outcome.net_name == "msi"
    assert outcome.placement.cell[0] == pytest.approx(21.657, rel=0.01)
    assert outcome.longest_joint < 1.55 and not outcome.overlaps
    found = symmetry.detect(outcome.structure, symprec=0.5)
    assert found.international == "P3_121"


def carboxylate_tilts(structure):
    """Each carboxylate's angle out of the plane of the ring it is on,
    in degrees."""
    cell = p1.expand(structure)
    rows = np.asarray(cell.lattice.matrix)
    xyz = cell.frac @ rows
    near = defaultdict(list)
    for b in bonding.graph(structure).bonds:
        image = np.asarray(b.image, float)
        near[b.i].append((b.j, image))
        near[b.j].append((b.i, -image))

    def at(i, image):
        return xyz[i] + image @ rows

    def normal(a, b, c):
        n = np.cross(b - a, c - a)
        return n / np.linalg.norm(n)

    tilts = []
    for i, symbol in enumerate(cell.elements):
        oxygens = [(j, s) for j, s in near[i] if cell.elements[j] == "O"]
        if symbol != "C" or len(oxygens) != 2:
            continue
        (r, rs), = [(j, s) for j, s in near[i] if cell.elements[j] == "C"]
        ring = [(k, s + rs) for k, s in near[r]
                if cell.elements[k] == "C" and k != i][:2]
        here = at(i, np.zeros(3))
        a = normal(here, *(at(j, s) for j, s in oxygens))
        b = normal(at(r, rs), *(at(k, s) for k, s in ring))
        tilts.append(np.degrees(np.arccos(min(1.0, abs(a @ b)))))
    return tilts


def test_a_two_point_linker_is_turned_so_each_end_lies_in_its_rods_group():
    """BPDC as drawn has its rings 35 degrees apart, and one turn of the
    whole linker cannot put both into MIL-53's coplanar carboxylates:
    each was left 27 degrees off its ring.  Turned about the biaryl
    bond, each lies in its ring as BDC's do."""
    outcome = built("MIL-53_Cr", "sql",
                    linker=str(ROOT / "tests" / "data"
                               / "rod_bpdc_whole.xyz"))
    assert outcome.net_name == "sra"
    assert max(carboxylate_tilts(outcome.structure)) < 5
