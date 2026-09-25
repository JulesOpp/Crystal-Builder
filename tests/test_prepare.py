"""From a deposited CIF to a cell a calculation can use.

Two kinds of test.  Small structures built by hand, where the right
answer is known before the code runs: two alternatives, a counter-ion
spread over six places, a trimer.  And the shipped COD frameworks,
checked against the one independent thing each carries -- the formula
its own refinement declares -- and for atoms no chemist would put
where they ended up.
"""

from pathlib import Path

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import bonding, p1, prepare
from xtal.core.neighbors import neighbor_pairs
from xtal.core.site import Site

COD = Path(__file__).resolve().parents[1] / "resources" / "samples" / "cod"


def _read(name):
    from xtal.io import FORMATS
    return FORMATS.read(COD / f"{name}.cif")


def _counts(structure) -> dict:
    counts: dict[str, int] = {}
    for e in p1.expand(structure).elements:
        counts[e] = counts.get(e, 0) + 1
    return counts


def _clashes(structure) -> int:
    cell = p1.expand(structure)
    pairs = neighbor_pairs(cell.frac, structure.lattice, 2.1,
                           min_distance=0.0)
    return sum(1 for i, j, d in zip(pairs.i, pairs.j, pairs.distance,
                                    strict=True)
               if i != j and prepare._clash(cell.elements[i],
                                            cell.elements[j], d))


def _box(*sites, a=12.0):
    structure = Structure(lattice=Lattice(np.eye(3) * a),
                          sites=[Site(e, np.array(f), occupancy=o,
                                      label=f"{e}{k}")
                                 for k, (e, f, o) in enumerate(sites)])
    structure.ensure_labels()
    return structure


# ======================================================================
#  ORDERING THE DISORDER
# ======================================================================

def test_of_two_alternatives_the_more_occupied_is_kept():
    """UiO-66's O2A at 0.73 and O2B at 0.27, 0.44 A apart: one place,
    two answers, and the refinement says which is likelier."""
    structure = _box(("O", (0.50, 0.50, 0.50), 0.73),
                     ("O", (0.535, 0.50, 0.50), 0.27))
    out, said = prepare.order_disorder(structure)

    assert [round(s.frac[0], 3) for s in out.sites] == [0.5]
    assert out.sites[0].occupancy == 1.0
    assert "kept 1" in said


def test_three_orientations_at_a_third_are_one_ring():
    """MIL-88B's pyridine: three orientations, each 1/3.  The place is
    full -- the thirds add to one -- so exactly one orientation stays,
    and whole: never half of one and half of another."""
    ring = []                  # three orientations 30 degrees apart,
    for orientation in range(3):         # each overlapping the next
        angle = np.radians(30 * orientation)
        for k in range(2):
            r = 0.10 + 0.12 * k
            ring.append(("C", (0.5 + r * np.cos(angle),
                               0.5 + r * np.sin(angle), 0.5), 1 / 3))
    out, _ = prepare.order_disorder(_box(*ring, a=10.0))

    assert len(out.sites) == 2
    kept = np.array([s.frac for s in out.sites])
    assert np.linalg.norm((kept[1] - kept[0]) * 10.0) == \
        pytest.approx(1.2, abs=0.01)             # the pair that was one
    assert _clashes(out) == 0


def test_a_counter_ion_spread_over_six_places_is_one_ion():
    """Al-soc-MOF-1's chloride sits at 1/6 on six positions that never
    clash.  Keeping every site above one half would drop all six and
    leave the framework charged; the cell keeps the one ion the
    occupancies add up to."""
    places = [(0.1, 0.1, 0.1), (0.9, 0.1, 0.1), (0.1, 0.9, 0.1),
              (0.1, 0.1, 0.9), (0.5, 0.5, 0.1), (0.5, 0.1, 0.5)]
    out, _ = prepare.order_disorder(
        _box(*[("Cl", p, 1 / 6) for p in places]))

    assert _counts(out) == {"Cl": 1}


def test_a_rarely_there_guest_is_left_out():
    out, _ = prepare.order_disorder(_box(("O", (0.5, 0.5, 0.5), 0.2)))
    assert out.sites == []


def test_atoms_of_one_component_share_an_occupancy():
    """Mn-BTT: an extra-framework Mn at 0.06 bonded to a DMF oxygen at
    0.42.  Averaged into one unit they came out as eighteen Mn where the
    refinement has one; a refinement ties a component's atoms to one
    occupancy, so these are two components."""
    structure = _box(("Mn", (0.5, 0.5, 0.5), 0.06),
                     ("O", (0.5 + 2.1 / 12, 0.5, 0.5), 0.42))
    out, _ = prepare.order_disorder(structure)
    assert _counts(out) == {}                      # 0.06 and 0.42, alone


def test_nothing_disordered_is_left_alone(quartz):
    out, said = prepare.order_disorder(quartz)
    assert out is quartz
    assert "nothing" in said


# ======================================================================
#  THE COD FRAMEWORKS
# ======================================================================

DISORDERED = ["Al-soc-MOF-1", "MIL-100", "MIL-101", "MIL-88B",
              "MOF-808", "Mn-BTT", "PCN-222", "UiO-66", "ZIF-8",
              "cubic-EuHOTP", "pbz-MOF-1"]


@pytest.mark.parametrize("name", DISORDERED)
def test_every_disordered_cod_framework_orders_without_a_clash(name):
    out, _ = prepare.order_disorder(_read(name))
    assert all(s.occupancy == 1.0 for s in out.sites)
    assert _clashes(out) == 0


@pytest.mark.parametrize("name", ["PCN-222", "ZIF-8", "MIL-88B"])
def test_the_ordered_cell_has_the_formula_the_refinement_declared(name):
    """The independent check.  These come out exactly: the ordering
    chose among alternatives without changing what the cell holds.
    (MIL-88B's CIF formula has no hydrogens, and neither does the
    ordered cell.)"""
    structure = _read(name)
    out, said = prepare.order_disorder(structure)
    assert "differs from the CIF" not in said


def test_uio66_comes_out_ideal_and_says_so():
    """UiO-66's refinement describes about 27 % missing linkers; the
    most likely occupant of every linker place is the linker, so the
    cell is defect-free -- the usual simulation model -- and the
    message says the formula differs rather than letting it pass."""
    out, said = prepare.order_disorder(_read("UiO-66"))
    assert "differs from the CIF" in said and "C 8.00 (CIF 5.82)" in said


# ======================================================================
#  THE PRIMITIVE CELL
# ======================================================================

@pytest.mark.parametrize("name, before, after", [
    ("MIL-101", 16000, 4000), ("MIL-100", 13552, 3388),
    ("UiO-66", 688, 172), ("MIL-53", 72, 36)])
def test_the_primitive_cell_is_the_declared_centrings(name, before,
                                                       after):
    """From the declared symbol, not by detecting symmetry again: a
    powder structure's coordinates do not let spglib see MIL-101's
    F-centring at its default tolerance."""
    structure = _read(name)
    out, _ = prepare.primitive(structure)
    assert p1.expand(structure).n_atoms == before
    assert len(out.sites) == after
    assert structure.lattice.volume / out.lattice.volume == \
        pytest.approx(before / after)


def test_the_primitive_cell_keeps_the_disorder_groups():
    """Standardising keeps element and occupancy and nothing else, and
    the ordering step reads the groups next."""
    out, _ = prepare.primitive(_read("UiO-66"))
    groups = {str(s.props.get("disorder_group", "")) for s in out.sites}
    assert {"1", "2"} <= groups


def test_a_primitive_cell_is_left_alone(quartz):
    out, said = prepare.primitive(quartz)
    assert out is quartz and "already primitive" in said


# ======================================================================
#  SYMMETRY COPIES WRITTEN AS SITES
# ======================================================================

def _ni2cl2btdd():
    from xtal.io import FORMATS
    return FORMATS.read(COD.parent / "Ni2Cl2BTDD.cif")


def test_symmetry_copies_written_as_sites_are_merged_before_reducing():
    """A CSD ConQuest export writes 27 symmetry copies of its 13
    independent sites under R-3m.  Expanded, 1152 atoms stack on 378
    places, and the primitive cell refused them: 378 / 3 is 126, not
    1152 / 3."""
    out, said = prepare.prepare(_ni2cl2btdd(),
                                steps=("duplicates", "primitive"))
    assert "27 site(s)" in said[0]
    assert len(out.sites) == 126
    assert "126 atoms, from 378" in said[1]


def test_the_primitive_cell_names_stacked_atoms_rather_than_the_group():
    """"Find symmetry first" sent the user after a group that was
    right; the atoms written twice were what was wrong."""
    with pytest.raises(ValueError, match="Merge duplicates"):
        prepare.primitive(_ni2cl2btdd())


def test_the_diagnosis_counts_each_atom_once():
    found = prepare.diagnose(_ni2cl2btdd())
    assert "duplicates" in found.keys()
    text = found.text()
    assert "27 of 40 sites" in text
    assert "378 atoms against 126" in text


def test_a_bare_oxygen_on_a_metal_is_a_water():
    """"Bis(mu-chloro)-diaqua-di-nickel(II)": Ni(II) x 2 against two
    chlorides and BTDD(2-) leaves the oxygen on each nickel neutral.
    The planner read the Ni-O bond as covalent and made each a
    hydroxide, the framework -2 per formula unit."""
    out, said = prepare.prepare(_ni2cl2btdd())
    cell = p1.expand(out)
    graph = bonding.graph(out)
    on_nickel = [o for o in range(cell.n_atoms)
                 if cell.elements[o] == "O"
                 and [cell.elements[k] for k in graph.neighbors(o)
                      if cell.elements[k] != "H"] == ["Ni"]]
    assert len(on_nickel) == 6
    assert all(sum(cell.elements[k] == "H" for k in graph.neighbors(o))
               == 2 for o in on_nickel)
    assert "12 as water on metals" in said[-1]


def test_an_atom_that_clashes_with_its_own_image_is_disorder():
    """"O3b disordered by symmetry over two configurations with
    occupancy 0.5", says the refinement; the export dropped the
    occupancy column, so O4 and its mirror image, 1.21 A apart, were
    both whole waters -- an O-O "molecule" the solvent step could not
    name and the planner gave hydrogens."""
    structure = prepare.merge_duplicates(_ni2cl2btdd())[0]
    assert "O4" in prepare.diagnose(structure).text()
    out, said = prepare.order_disorder(structure)
    assert "O4" in said
    cell = p1.expand(out)
    pairs = neighbor_pairs(cell.frac, out.lattice, 2.0)
    assert not any(cell.elements[i] == cell.elements[j] == "O"
                   for i, j in zip(pairs.i, pairs.j, strict=True))
    assert _counts(out)["O"] == _counts(structure)["O"] - 18


def test_the_pore_water_that_was_two_halves_is_solvent():
    out, said = prepare.prepare(_ni2cl2btdd())
    solvent = said[prepare.DEFAULT_STEPS.index("solvent")]
    assert "other molecule" not in solvent
    assert "more by valence" not in said[-1]
    assert not any(prepare.SOURCE_SITE in s.props for s in out.sites)


def test_an_atom_written_once_is_not_a_duplicate(quartz):
    out, said = prepare.merge_duplicates(quartz)
    assert out is quartz and said == "no site written twice"


# ======================================================================
#  CHEMISTRY THE FILE DID NOT HAVE
# ======================================================================

def test_completing_the_trimers_is_never_a_default():
    """Choosing F, OH or water for a site the refinement left bare is a
    change to the material, so it is asked for or not done."""
    assert "cap" in prepare.STEPS
    assert "cap" not in prepare.DEFAULT_STEPS


def test_a_trimer_left_as_found_gets_no_hydrogen_on_its_ligands():
    """Without the trimer step the planner read valences and made all
    three terminal oxygens hydroxide -- the trimer -2, a charge choice
    nobody made."""
    out, _said = prepare.prepare(_read("MIL-88B"))
    cell = p1.expand(out)
    graph = bonding.graph(out)
    ligands = [lig for _o, members in prepare._trimers(out)
               for _m, lig in members if lig is not None]
    assert ligands
    assert not any(cell.elements[k] == "H"
                   for lig in ligands for k in graph.neighbors(lig))


def test_a_trimer_left_charged_is_a_caution():
    outcome = prepare.run(_read("MIL-88B"), prepare.DEFAULT_STEPS)
    assert len(outcome.cautions) == 1
    assert "2 M3O trimer(s)" in outcome.cautions[0]
    assert "not neutral" in outcome.cautions[0]


def test_completing_the_trimers_is_a_caution_that_names_the_change():
    outcome = prepare.run(_read("MIL-88B"), prepare.STEPS)
    assert len(outcome.cautions) == 1
    assert "changes the chemistry" in outcome.cautions[0]
    assert "2 OH and 4 water" in outcome.cautions[0]


def test_a_framework_without_trimers_has_nothing_to_caution():
    assert prepare.run(_read("UiO-66"), prepare.STEPS).cautions == []


# ======================================================================
#  CHARGE: TRIMERS AND ZR6 CORES
# ======================================================================

def _terminal_roles(structure):
    """``(OH, water, F)`` on the trimers of ``structure``."""
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    counts = {"OH": 0, "water": 0, "F": 0}
    for _o, members in prepare._trimers(structure):
        for _m, ligand in members:
            if cell.elements[ligand] == "F":
                counts["F"] += 1
                continue
            h = sum(1 for k in graph.neighbors(ligand)
                    if cell.elements[k] == "H")
            counts["OH" if h == 1 else "water"] += 1
    return counts


def test_each_trimer_carries_one_anion_and_two_waters():
    """Cr3O(bdc)3 is +1.  A hydrogen planner reading valences made all
    three terminal oxygens hydroxide, and each trimer -2."""
    out, _ = prepare.prepare(_read("MIL-88B"), prepare.STEPS)
    assert _terminal_roles(out) == {"OH": 2, "water": 4, "F": 0}


def test_a_counter_ion_in_the_pores_is_the_trimers_anion():
    """Al-soc-MOF-1 is [Al3O(abtc)1.5(H2O)3]+ Cl-: the chloride is the
    anion, and the trimer keeps three waters."""
    out, said = prepare.prepare(_read("Al-soc-MOF-1"), prepare.STEPS)
    assert _counts(out)["Cl"] == len(prepare._trimers(out)) == 8
    assert _terminal_roles(out) == {"OH": 0, "water": 24, "F": 0}
    assert "halide ion" in said[prepare.STEPS.index("cap")]


def test_a_zr6_core_gets_its_four_hydroxides_outward():
    """Zr6O4(OH)4: four of the eight capping oxygens, on alternate
    faces, each with its hydrogen pointing away from the cluster --
    not into it, which a centre taken across a cell face once did."""
    out, _ = prepare.prepare(_read("UiO-66"))
    cell = p1.expand(out)
    graph = bonding.graph(out)
    hydroxides = [o for o in range(cell.n_atoms)
                  if cell.elements[o] == "O"
                  and sum(cell.elements[j] == "Zr"
                          for j in graph.neighbors(o)) == 3
                  and any(cell.elements[j] == "H"
                          for j in graph.neighbors(o))]
    assert len(hydroxides) == 4
    pairs = neighbor_pairs(cell.frac, out.lattice, 2.2)
    for i, j, d in zip(pairs.i, pairs.j, pairs.distance, strict=True):
        if {cell.elements[i], cell.elements[j]} == {"Zr", "H"}:
            pytest.fail(f"a hydrogen {d:.2f} A from a Zr")


def test_mof808_is_the_textbook_composition():
    """Zr6O4(OH)4(btc)2(HCOO)6, per cluster: 16 H and 32 O."""
    out, _ = prepare.prepare(_read("MOF-808"))
    counts = _counts(out)
    clusters = counts["Zr"] // 6
    assert counts["H"] == 16 * clusters
    assert counts["O"] == 32 * clusters


# ======================================================================
#  HYDROGENS A POWDER STRUCTURE CANNOT BE TRUSTED WITH
# ======================================================================

def test_ring_hydrogens_come_from_the_ring_and_not_the_bond_lengths():
    """MIL-101: 68 trimers, three bdc each, four ring hydrogens a
    linker -- 816, whatever the refinement did to the bond lengths."""
    out, said = prepare.prepare(_read("MIL-101"))
    assert "816 on arene rings" in said[-1]


def test_a_bent_carboxylate_gets_no_hydrogen():
    """MIL-100's powder model has a carboxylate carbon with angles
    summing to 337 degrees; typed by geometry it wanted a hydrogen."""
    out, said = prepare.prepare(_read("MIL-100"), prepare.STEPS)
    assert "were not added" in said[-1]
    counts = _counts(out)
    trimers = counts["Fe"] // 3
    assert counts["H"] == 6 * trimers + 1 * trimers + 4 * trimers


# ======================================================================
#  THE REST
# ======================================================================

def test_solvent_goes_and_a_counter_ion_stays():
    water = _box(("O", (0.5, 0.5, 0.5), 1.0))
    chloride = _box(("Cl", (0.5, 0.5, 0.5), 1.0))
    assert prepare.remove_solvent(water)[0].sites == []
    out, said = prepare.remove_solvent(chloride)
    assert out is chloride and said == "no solvent molecules"


def test_deuterium_is_written_as_hydrogen():
    out, _ = prepare.to_hydrogen(_read("MIL-53"))
    assert "D" not in _counts(out)


@pytest.mark.parametrize("name", sorted(p.stem for p in COD.glob("*.cif")))
def test_a_prepared_framework_has_nothing_left_to_prepare(name):
    """And nothing a calculation would choke on: no two atoms closer
    than two alternatives are, and no hydrogen bonded to nothing."""
    out, _ = prepare.prepare(_read(name), prepare.STEPS)
    assert not prepare.diagnose(out)
    assert _clashes(out) == 0
    graph = bonding.graph(out)
    cell = p1.expand(out)
    assert all(graph.neighbors(a) for a in range(cell.n_atoms)
               if cell.elements[a] == "H")


def _formula(structure) -> dict:
    counts = _counts(structure)
    return {e: n for e, n in sorted(counts.items())}


@pytest.mark.parametrize("name, per_cluster", [
    # Zr6O4(OH)4(OH)4(H2O)4(TBAPy)2: four OH and four waters on the
    # eight-connected node -- eight OH, which is what the planner
    # gave, left each node -4.
    ("NU-1000", {"C": 88, "H": 60, "O": 32, "Zr": 6}),
    # The same node on TCPP-FeCl.  The CIF rides a hydrogen on every
    # terminal oxygen; they are replaced, not added to.
    ("PCN-222", {"C": 96, "H": 64, "Cl": 2, "Fe": 2, "N": 8, "O": 32,
                 "Zr": 6}),
    ("UiO-66", {"C": 48, "H": 28, "O": 32, "Zr": 6}),
    ("MOF-808", {"C": 24, "H": 16, "O": 32, "Zr": 6}),
])
def test_an_m6_core_gets_the_terminal_ligands_its_charge_asks_for(
        name, per_cluster):
    out, _ = prepare.prepare(_read(name))
    counts = _counts(out)
    clusters = counts["Zr"] // 6
    assert {e: n // clusters for e, n in counts.items()} == per_cluster
    assert all(n % clusters == 0 for n in counts.values())


def test_no_riding_hydrogen_is_left_against_a_zirconium():
    out, said = prepare.prepare(_read("PCN-222"))
    assert "riding hydrogen(s) the CIF put" in said[-1]
    cell = p1.expand(out)
    pairs = neighbor_pairs(cell.frac, out.lattice, 2.2)
    for i, j in zip(pairs.i, pairs.j, strict=True):
        assert {cell.elements[i], cell.elements[j]} != {"Zr", "H"}


def test_mil53s_bridging_oxygen_is_a_hydroxide():
    """Cr(OH)(bdc): the neutron structure deuterated the linker and
    never located the mu2-OD."""
    out, said = prepare.prepare(_read("MIL-53"))
    assert _counts(out) == {"C": 16, "Cr": 2, "H": 10, "O": 10}
    assert "on mu2-OH bridging trivalent metals" in said[-1]


def test_a_vanadium_oxo_bridge_is_left_an_oxo():
    """MIL-47 is V(IV)O(bdc).  Vanadium is left out of the rule."""
    assert "V" not in prepare.BRIDGING_HYDROXIDE_METALS


def test_a_bound_methanol_is_a_whole_methanol():
    """Mn-BTT's methanol: an O and a barely located C.  Three hydrogens
    on the carbon whatever its C-O length says, one on the oxygen
    whatever the metal bond does to its count."""
    out, said = prepare.prepare(_read("Mn-BTT"))
    assert "completing bound methanol" in said[-1]
    cell = p1.expand(out)
    graph = bonding.graph(out)
    methyls = [c for c in range(cell.n_atoms)
               if cell.elements[c] == "C"
               and [cell.elements[k] for k in graph.neighbors(c)
                    if cell.elements[k] != "H"] == ["O"]]
    assert len(methyls) == 12
    for c in methyls:
        assert sum(cell.elements[k] == "H"
                   for k in graph.neighbors(c)) == 3
        oxygen = next(k for k in graph.neighbors(c)
                      if cell.elements[k] == "O")
        assert sum(cell.elements[k] == "H"
                   for k in graph.neighbors(oxygen)) == 1


def test_a_hydrogen_goes_with_the_carbon_it_rides_on():
    """pbz-MOF-1's acetate: carbon at 5/6, its methyl hydrogens at 5/12
    over two orientations.  Chosen apart, 48 of them outlived carbons
    that were not kept."""
    out, said = prepare.order_disorder(_read("pbz-MOF-1"))
    assert "left out with the atom they ride on" in said
    graph = bonding.graph(out)
    cell = p1.expand(out)
    assert all(graph.neighbors(a) for a in range(cell.n_atoms)
               if cell.elements[a] == "H")


def test_a_missing_acetate_leaves_a_hydroxide_and_a_water():
    """Acetate is -1: where one is missing, its two oxygens stay on the
    zirconiums as one OH and one water, three hydrogens -- turned so
    that no hydrogen of one points at the other, 2.2 A away."""
    out, said = prepare.prepare(_read("pbz-MOF-1"))
    assert "12 on M6 cores' terminal OH and water" in said[-1]
    assert _clashes(out) == 0


def test_no_oxygen_is_shared_by_two_nitrates():
    """cubic-EuHOTP's orientation-A distal oxygen sits on a two-fold
    axis between two nitrates; joined, every pair came out N-O-N."""
    out, _ = prepare.order_disorder(_read("cubic-EuHOTP"))
    cell = p1.expand(out)
    graph = bonding.graph(out)
    for a in range(cell.n_atoms):
        if cell.elements[a] == "O":
            assert sum(cell.elements[k] == "N"
                       for k in graph.neighbors(a)) <= 1
    for n in range(cell.n_atoms):
        if cell.elements[n] == "N":
            assert sum(cell.elements[k] == "O"
                       for k in graph.neighbors(n)) == 3


def test_every_europium_keeps_one_chelating_nitrate():
    """Of a pair across the axis, A on one leaves room only for B on
    the other; the shared oxygen, which follows its nitrate, must not
    take the place of the second."""
    out, _ = prepare.order_disorder(_read("cubic-EuHOTP"))
    cell = p1.expand(out)
    graph = bonding.graph(out)
    for eu in range(cell.n_atoms):
        if cell.elements[eu] == "Eu":
            chelating = {k for k in graph.neighbors(eu)
                         if cell.elements[k] == "N"}
            assert len(chelating) == 1


def test_an_unknown_step_is_named():
    with pytest.raises(ValueError, match="no preparation step"):
        prepare.prepare(_box(), steps=("tidy",))


def test_ring_hydrogens_on_a_structure_with_symmetry_are_not_multiplied():
    """The rules place a hydrogen on every ring carbon of the P1 cell.
    Appended to a structure that still had its group, each would be
    expanded by it -- 192 operations in MOF-5's Fm-3m."""
    mof5 = _read("MOF-5")
    stripped = mof5.copy()
    stripped.sites = [s for s in stripped.sites if s.element != "H"]
    stripped.touch()
    out, _ = prepare.prepare(stripped, steps=("hydrogens",))
    assert _counts(out)["H"] == _counts(mof5)["H"] == 96
    assert _clashes(out) == 0


def test_a_step_with_nothing_to_do_hands_back_its_argument(quartz):
    for step, operation in prepare.OPERATIONS.items():
        assert operation(quartz)[0] is quartz, step


# ======================================================================
#  THE COMMAND
# ======================================================================

def test_the_command_reports_every_step_it_ran():
    from xtal.commands.prepare import Prepare

    out, report = Prepare(prepare.STEPS).preview(_read("MIL-88B"))
    assert report.ok
    assert report.n_after == p1.expand(out).n_atoms == 120
    assert len(report.warnings) == len(prepare.STEPS)
    assert "2 OH and 4 water" in \
        report.warnings[prepare.STEPS.index("cap")]


def test_nothing_to_prepare_is_not_an_edit(quartz):
    """An ok report would push an entry Ctrl+Z then undoes nothing."""
    from xtal.commands.prepare import Prepare

    out, report = Prepare().preview(quartz)
    assert out is quartz and not report.ok
    assert report.message == "nothing to prepare"


def test_bonds_drawn_by_hand_are_refused_rather_than_lost(rutile):
    """Ordering renumbers and drops sites; a bond the user drew cannot
    be carried through it, and losing one quietly is the thing the
    bonding invariants exist to prevent."""
    from xtal.commands.prepare import Prepare
    from xtal.core.structure import Bond

    structure = rutile.copy()
    structure.add_bond(Bond(0, 1, kind="explicit"))
    out, report = Prepare().preview(structure)
    assert out is structure and not report.ok
    assert "Reset bonds to automatic" in report.message


def test_xtal_prepare_writes_the_prepared_cell(tmp_path, capsys):
    """By default the trimers stay as the file has them, and a warning
    says the cell is not neutral."""
    from xtal.cli import main
    from xtal.io import FORMATS

    out = tmp_path / "mil88b.cif"
    assert main(["prepare", str(COD / "MIL-88B.cif"), str(out)]) == 0
    printed = capsys.readouterr().out
    assert "partially occupied" in printed
    assert "C24H12Cr3O16" in printed
    assert "warning: 2 M3O trimer(s)" in printed
    assert p1.expand(FORMATS.read(out)).n_atoms == 110


def test_xtal_prepare_completes_the_trimers_only_when_named(tmp_path,
                                                           capsys):
    from xtal.cli import main

    out = tmp_path / "mil88b.cif"
    assert main(["prepare", str(COD / "MIL-88B.cif"), str(out),
                 "--steps", ",".join(prepare.STEPS)]) == 0
    printed = capsys.readouterr().out
    assert "C24H17Cr3O16" in printed
    assert "warning: Complete M3O trimers' terminal ligands changes " \
           "the chemistry" in printed


def test_xtal_prepare_names_an_unknown_step_before_reading(tmp_path,
                                                           capsys):
    from xtal.cli import main

    assert main(["prepare", "nowhere.cif", str(tmp_path / "x.cif"),
                 "--steps", "tidy"]) != 0
    assert "no preparation step called tidy" in capsys.readouterr().err


def test_two_orientations_written_at_full_occupancy_are_ordered():
    """Al-soc-MOF-1's CIF gives both tilts of the terphenyl's central
    ring occupancy 1, and its formula counts both: C75 per Al3, where
    [Al3O(TCPT)1.5(H2O)3]Cl is C69H45.  The ordered cell keeps one
    tilt per ring, keeps its chloride, and says it differs from the
    CIF rather than agreeing with its mistake."""
    structure = _read("Al-soc-MOF-1")
    assert "overlap as two orientations" in \
        prepare.diagnose(structure).text()
    out, said = prepare.prepare(structure, prepare.STEPS)
    assert "two overlapping orientations" in \
        said[prepare.STEPS.index("disorder")]
    counts = _counts(out)
    trimers = counts["Al"] // 3
    assert {e: n // trimers for e, n in counts.items()} == \
        {"Al": 3, "C": 69, "Cl": 1, "H": 45, "O": 16}
    graph = bonding.graph(out)
    cell = p1.expand(out)
    assert max(len([k for k in graph.neighbors(a)
                    if cell.elements[k] != "H"])
               for a in range(cell.n_atoms)
               if cell.elements[a] == "C") == 3


def test_a_ring_carbon_takes_no_hydrogen_whatever_its_angles():
    """The ipso carbon of an ordered ring sits at the average of the two
    tilts and looks pyramidal; typed by its angles it got an sp3
    hydrogen, 24 of them in Al-soc-MOF-1."""
    _out, said = prepare.prepare(_read("Al-soc-MOF-1"))
    assert "more by valence" not in said[-1]


@pytest.mark.parametrize("name", sorted(p.stem for p in COD.glob("*.cif")))
def test_every_prepared_atom_has_a_label_of_its_own(name):
    """A CIF names atoms by label in its bond loop.  The primitive cell
    once gave every image of a site that site's label, and a bond
    written between two atoms came back between two others."""
    out, _ = prepare.prepare(_read(name))
    labels = [s.label for s in out.sites]
    assert len(set(labels)) == len(labels)
