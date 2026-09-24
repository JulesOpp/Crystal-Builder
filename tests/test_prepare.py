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


@pytest.mark.parametrize("name", ["Al-soc-MOF-1", "PCN-222", "ZIF-8",
                                  "MIL-88B"])
def test_the_ordered_cell_has_the_formula_the_refinement_declared(name):
    """The independent check.  These four come out exactly: the
    ordering chose among alternatives without changing what the cell
    holds -- Al-soc-MOF-1 keeping its chloride at 1/3 per Al among
    them.  (MIL-88B's CIF formula has no hydrogens, and neither does
    the ordered cell.)"""
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
    out, _ = prepare.prepare(_read("MIL-88B"))
    assert _terminal_roles(out) == {"OH": 2, "water": 4, "F": 0}


def test_a_counter_ion_in_the_pores_is_the_trimers_anion():
    """Al-soc-MOF-1 is [Al3O(abtc)1.5(H2O)3]+ Cl-: the chloride is the
    anion, and the trimer keeps three waters."""
    out, said = prepare.prepare(_read("Al-soc-MOF-1"))
    assert _counts(out)["Cl"] == len(prepare._trimers(out)) == 8
    assert _terminal_roles(out) == {"OH": 0, "water": 24, "F": 0}
    assert "halide ion" in said[4]


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
    out, said = prepare.prepare(_read("MIL-100"))
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


def test_a_prepared_framework_has_nothing_left_to_prepare():
    for name in ("MIL-88B", "MOF-808", "ZIF-8"):
        out, _ = prepare.prepare(_read(name))
        assert not prepare.diagnose(out), name


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
    assert "2 OH and 4 water" in report.warnings[4]


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
    from xtal.cli import main
    from xtal.io import FORMATS

    out = tmp_path / "mil88b.cif"
    assert main(["prepare", str(COD / "MIL-88B.cif"), str(out)]) == 0
    printed = capsys.readouterr().out
    assert "partially occupied" in printed
    assert "C24H17Cr3O16" in printed
    assert p1.expand(FORMATS.read(out)).n_atoms == 120


def test_xtal_prepare_names_an_unknown_step_before_reading(tmp_path,
                                                           capsys):
    from xtal.cli import main

    assert main(["prepare", "nowhere.cif", str(tmp_path / "x.cif"),
                 "--steps", "tidy"]) != 0
    assert "no preparation step called tidy" in capsys.readouterr().err
