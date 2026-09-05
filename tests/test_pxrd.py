"""A calculated powder pattern, the .xy files either side of it, and
the module that puts the two together.

The one thing worth guarding above everything else is that the
*symmetry reaches the calculation*.  A structure factor summed over
the asymmetric unit instead of the cell is a pattern that is wrong in
a way nothing else here would notice: the peaks are in the right
places, the strong ones are still strong, and the forbidden ones are
simply present.  Halite's 100 is the test, because F centring forbids
it and an unexpanded calculation puts a peak there a third the height
of 200.

The rest is arithmetic that can be checked against a published
pattern -- NaCl's three strongest lines at 27.4, 31.7 and 45.5 degrees
for Cu Ka1 -- and the refusals, which are failed runs rather than
crashes.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.analysis import pxrd
from xtal.core.lattice import Lattice
from xtal.core.structure import Structure
from xtal.io.xy import read_xy, write_xy, xy_string
from xtal.modules import MODULES, Job
from xtal.modules import pxrd as pxrd_module
from xtal.modules import record as module_record
from xtal.modules.job import Cancellation, Cancelled
from xtal.modules.report import Curve, Table
from xtal.workspace import Workspace


@pytest.fixture
def entry(tmp_path, halite):
    from xtal.io import write_cif
    source = tmp_path / "halite.cif"
    write_cif(halite, source)
    return Workspace.create(tmp_path / "ws").add_structure(source)


# ------------------------------------------------ the gemmi bridge

def test_the_symmetry_reaches_the_calculation(halite):
    """The whole cell, not the asymmetric unit.

    Setting ``spacegroup_hm`` alone leaves ``cell.images`` empty, and
    then every structure factor is summed over two atoms instead of
    eight.  Four sodiums and four chlorines is what says the bridge
    expanded.
    """
    small = pxrd.to_small_structure(halite)

    assert len(small.sites) == 2
    assert len(small.get_all_unit_cell_sites()) == 8


def test_the_structure_is_simulated_as_it_is(halite):
    """A crystal the user dropped to P1 is calculated in P1.

    Nothing detects, standardises or otherwise improves the symmetry
    on the way in.  The *pattern* is the same either way -- the same
    atoms in the same cell scatter the same -- and the reflection
    list is not: what was one line in Fm-3m is the three or six
    independent reflections P1 says it is, and that is what the user
    asked to be shown.
    """
    from xtal.core.symmetry import reduce_to_p1

    expanded = reduce_to_p1(halite)
    symmetric = pxrd.simulate(halite, two_theta_min=20.0,
                              two_theta_max=50.0)
    plain = pxrd.simulate(expanded, two_theta_min=20.0,
                          two_theta_max=50.0)

    assert expanded.space_group.number == 1
    assert len(plain.reflections) > len(symmetric.reflections)
    assert np.allclose(plain.pattern.y, symmetric.pattern.y,
                       atol=1e-6)
    # 200, 020 and 002 are three independent reflections in P1 and
    # are NOT folded into one another.
    at_200 = [r.label for r in plain.reflections
              if abs(r.two_theta - symmetric.reflections[1].two_theta)
              < 1e-6]
    assert sorted(at_200) == ["(0 0 2)", "(0 2 0)", "(2 0 0)"]


def test_p1_forbids_nothing_so_it_has_no_absences(halite):
    """The honest answer rather than an empty result to explain away:
    P1 has no operations to make a systematic absence with."""
    from xtal.core.symmetry import reduce_to_p1

    small = pxrd.to_small_structure(reduce_to_p1(halite))

    assert pxrd.absences(small, two_theta_max=40.0).size == 0


def test_a_forbidden_reflection_is_absent(halite):
    """F centring forbids 100, and an unexpanded calculation does
    not: it comes back as a peak a third the height of 200, which is
    a pattern nobody would query and everybody would misindex."""
    small = pxrd.to_small_structure(halite)
    found = pxrd.reflections(small, two_theta_max=40.0)
    angles = [round(r.two_theta, 2) for r in found]

    assert round(float(pxrd.two_theta_from_d(5.6402, 1.5406)), 2) \
        not in angles


def test_every_setting_survives_the_round_trip_through_gemmi():
    """``determine_and_set_spacegroup("symops")`` *rewrites*
    ``spacegroup_hm``, and :func:`~xtal.analysis.pxrd.reflections`
    reads the group back out of it to place the systematic absences.

    So the round trip has to land on the same operations it started
    from, in every setting -- an origin choice or a rhombohedral axis
    resolved to its partner would give a pattern with the wrong
    reflections missing, which is the kind of wrong that looks
    plausible.  All 230 groups and every alternate setting they have.
    """
    import gemmi

    from xtal.core.spacegroup import SpaceGroup

    for number in range(1, 231):
        for setting in ("", "1", "2", "H", "R"):
            try:
                group = SpaceGroup.from_number(number, setting)
            except ValueError:
                continue                # that group has no such axis
            small = gemmi.SmallStructure()
            small.cell = gemmi.UnitCell(9.0, 9.0, 9.0, 90, 90, 90)
            small.spacegroup_hm = group.hm
            wanted = {op.triplet() for op
                      in gemmi.symops_from_hall(group.hall)}
            small.symops = sorted(wanted)
            small.determine_and_set_spacegroup("symops")

            resolved = gemmi.find_spacegroup_by_name(
                small.spacegroup_hm)
            assert resolved is not None, group.hm
            assert {op.triplet() for op
                    in resolved.operations()} == wanted, group.hm


def test_a_dummy_atom_is_held_back_at_the_door(halite):
    """``X`` has no scattering factor and is a marker rather than
    chemistry -- so it is left out, not refused, which is what every
    other door in this application does with one."""
    from xtal.core.site import Site

    marked = halite.copy()
    marked.sites.append(Site("X", [0.25, 0.25, 0.25]))
    small = pxrd.to_small_structure(marked)

    assert [s.type_symbol for s in small.sites] == ["Na", "Cl"]


def test_a_structure_with_no_atoms_says_what_is_missing():
    empty = Structure.empty(Lattice.cubic(5.0))
    with pytest.raises(pxrd.PxrdError, match="no atoms"):
        pxrd.to_small_structure(empty)


# ------------------------------------------------------- the physics

def test_the_three_strongest_lines_of_rock_salt_are_where_they_should_be(
        halite):
    """111, 200 and 220 at 27.4, 31.7 and 45.5 degrees for Cu Ka1,
    which is the pattern in every powder diffraction file."""
    simulation = pxrd.simulate(halite, two_theta_min=20.0,
                               two_theta_max=50.0)
    angles = sorted(round(r.two_theta, 1)
                    for r, percent in simulation.scaled_reflections()
                    if percent > 5.0)

    assert angles == [27.4, 31.7, 45.4]
    assert simulation.strongest.two_theta == pytest.approx(31.7, abs=0.1)


def test_multiplicity_counts_the_equivalents_and_the_friedel_pair(
        halite):
    """A powder superimposes every equivalent onto one peak, so 200 is
    six reflections and 111 is eight."""
    simulation = pxrd.simulate(halite, two_theta_min=20.0,
                               two_theta_max=50.0)
    by_angle = {round(r.two_theta): r.multiplicity
                for r in simulation.reflections}

    assert by_angle[27] == 8
    assert by_angle[32] == 6


def test_thermal_motion_attenuates_the_high_angle_peaks(halite):
    """Without a Debye-Waller factor the high-angle peaks come out
    systematically too strong against a published pattern, so an
    overall B has to reach them and not the low-angle ones."""
    cold = pxrd.simulate(halite, two_theta_min=20.0,
                         two_theta_max=90.0, b_overall=0.0)
    warm = pxrd.simulate(halite, two_theta_min=20.0,
                         two_theta_max=90.0, b_overall=3.0)

    def top(simulation, angle):
        return next(percent for r, percent
                    in simulation.scaled_reflections()
                    if round(r.two_theta) == angle)

    assert top(warm, 75) < top(cold, 75)


def test_a_pattern_is_scaled_to_a_hundred(halite):
    simulation = pxrd.simulate(halite, two_theta_min=20.0,
                               two_theta_max=50.0)

    assert simulation.pattern.y.max() == pytest.approx(100.0)
    assert simulation.pattern.wavelength == pytest.approx(1.5406)


def test_each_profile_shape_keeps_its_area():
    """A unit-area peak, whichever shape it is: the three have to be
    interchangeable without the relative heights of the pattern
    changing along with them.

    Integrated over a hundred FWHM either side, because a Lorentzian
    genuinely does not converge faster than that -- 2/pi atan(200) is
    99.7 per cent of it -- which is also why
    :data:`~xtal.analysis.pxrd.PROFILE_CUTOFF_FWHM` is twelve rather
    than three.
    """
    x = np.linspace(0.0, 40.0, 20001)
    for shape in pxrd.PROFILE_SHAPES:
        y = pxrd.profile(x, 20.0, 0.2, shape, 0.5)
        assert np.trapezoid(y, x) == pytest.approx(1.0, abs=0.01)


def test_a_shape_nothing_answers_to_says_what_there_is():
    with pytest.raises(pxrd.PxrdError, match="pseudo-voigt"):
        pxrd.profile(np.zeros(3), 1.0, 1.0, "voigt")


def test_a_negative_caglioti_parabola_gives_no_width_rather_than_a_nan(
):
    """Published U/V/W triples do dip negative at low angle, and a
    reflection with no width is dropped rather than drawn imaginary."""
    assert pxrd.caglioti_fwhm(2.0, 0.0, -1.0, 0.0) == 0.0


def test_an_empty_range_is_refused_by_name(halite):
    with pytest.raises(pxrd.PxrdError, match="2-theta range is empty"):
        pxrd.build_pattern([], 40.0, 10.0)


def test_a_range_with_no_reflections_in_it_says_what_would_help(
        halite):
    with pytest.raises(pxrd.PxrdError, match="wider range"):
        pxrd.simulate(halite, two_theta_min=0.6, two_theta_max=1.0)


def test_the_reflection_loop_can_be_stopped(halite):
    cancel = Cancellation()
    cancel.cancel()
    small = pxrd.to_small_structure(halite)

    with pytest.raises(Cancelled):
        pxrd.reflections(small, two_theta_max=90.0, cancel=cancel)


def test_a_source_is_named_rather_than_remembered():
    assert pxrd.wavelength_of("cu-ka1") == pytest.approx(1.5406)
    assert pxrd.wavelength_of("custom", 0.9) == pytest.approx(0.9)
    assert "1.5406" in pxrd.wavelength_label("cu-ka1")
    with pytest.raises(pxrd.PxrdError, match="not a known source"):
        pxrd.wavelength_of("chromium")


# ------------------------------------------------------------- .xy

def test_an_xy_file_round_trips(tmp_path):
    path = write_xy([10.0, 10.02], [3.0, 4.5], tmp_path / "p.xy",
                    header="a header line")
    x, y = read_xy(path)

    assert path.read_text().startswith("# a header line")
    assert list(x) == [10.0, 10.02]
    assert list(y) == [3.0, 4.5]


def test_a_measured_file_with_a_header_and_a_third_column_still_reads(
        tmp_path):
    """Files in the wild carry all three, and refusing them would
    mean the user editing a file before the application would look
    at it."""
    path = tmp_path / "measured.xy"
    path.write_text("! from the diffractometer\n"
                    "2theta  I  sigma\n"
                    "\n"
                    "5.00, 120, 11\n"
                    "5.02  131  11\n")
    x, y = read_xy(path)

    assert list(x) == [5.0, 5.02]
    assert list(y) == [120.0, 131.0]


def test_a_file_with_no_numbers_in_it_says_what_one_looks_like(
        tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("# nothing but a comment\n")
    with pytest.raises(ValueError, match="2-theta and intensity"):
        read_xy(path)


def test_the_pattern_is_not_a_structure_format(tmp_path):
    """``.xy`` is deliberately outside :data:`xtal.io.FORMATS`.  Open
    builds its filter from that registry and hands whatever comes back
    to a Document, so an entry there would put a file in the dialog
    that nothing downstream could accept."""
    from xtal.io import FORMATS

    assert "xy" not in FORMATS
    with pytest.raises(ValueError, match="no format is registered"):
        FORMATS.by_extension(tmp_path / "p.xy")


def test_writing_two_columns_of_different_lengths_is_refused():
    with pytest.raises(ValueError, match="2 angles and 3"):
        xy_string([1.0, 2.0], [1.0, 2.0, 3.0])


# ---------------------------------------------------- the module

def test_the_entry_is_registered_and_needs_no_binary():
    module, action = MODULES.find("pxrd.simulate")

    assert module is pxrd_module.PXRD
    assert module.check is None            # nothing to grey out
    assert action.needs_structure is True
    assert bool(module.availability())


def test_a_run_produces_a_curve_and_a_reflection_table(halite):
    result = pxrd_module.simulate_pattern(Job(
        structure=halite,
        params=pxrd_module.PXRD.action("simulate").coerce(
            {"two_theta_min": 20.0, "two_theta_max": 50.0})))

    assert result.ok
    curve, table = result.report.blocks
    assert isinstance(curve, Curve) and isinstance(table, Table)
    assert curve.x_label.startswith("2-theta")
    assert [label for label, _p in curve.tick_sets] == ["allowed"]
    assert curve.n_ticks == len(table.rows)
    assert any("(1 1 1)" in row.texts[1] for row in table.rows)


def test_the_table_has_the_columns_a_reference_pattern_has(halite):
    """No., hkl, d, 2-theta and I -- five different quantities across
    one row, which a Quantity/Value/Unit table cannot say."""
    result = pxrd_module.simulate_pattern(Job(
        structure=halite, params={"two_theta_max": 50.0}))
    table = result.report.blocks[1]

    assert table.columns == ("No.", "hkl", "d (\u00c5)",
                             "2\u03b8 (\u00b0)", "I (%)")
    assert table.named_columns
    assert [row.texts[0] for row in table.rows] == \
        [str(n + 1) for n in range(len(table.rows))]
    first = table.rows[0]
    assert first.texts[1] == "(1 1 1)"
    assert float(first.texts[3]) == pytest.approx(27.37, abs=0.01)


def test_every_reflection_is_listed(halite):
    """There was a threshold and it is gone: a weak reflection is
    exactly what somebody scanning the list is looking for."""
    result = pxrd_module.simulate_pattern(Job(
        structure=halite, params={"two_theta_max": 90.0}))
    curve, table = result.report.blocks

    assert len(table.rows) == curve.n_ticks
    assert "show_absences" in \
        {p.name for p in pxrd_module.PARAMS}
    assert "min_intensity" not in \
        {p.name for p in pxrd_module.PARAMS}


def test_the_caveat_travels_with_the_numbers(halite):
    """A calculated intensity assumes the structure is complete, and
    the row is where somebody reads the number -- so it is the row's
    note and not a footnote."""
    result = pxrd_module.simulate_pattern(Job(
        structure=halite, params={"two_theta_max": 50.0}))
    table = result.report.blocks[1]

    assert "preferred orientation" in result.report.note
    assert "disordered solvent" in table.rows[0].note


def test_the_forbidden_reflections_are_a_second_comb_when_asked_for(
        halite):
    """An unexpected peak is either an impurity or the wrong space
    group, and which one depends on whether it sits over a position
    this group forbids -- so the two combs are two colours and not
    one list."""
    plain = pxrd_module.simulate_pattern(Job(
        structure=halite, params={"two_theta_max": 50.0}))
    marked = pxrd_module.simulate_pattern(Job(
        structure=halite, params={"two_theta_max": 50.0,
                                  "show_absences": True}))

    assert [label for label, _p in plain.report.blocks[0].tick_sets] \
        == ["allowed"]
    labels = [label for label, _p in marked.report.blocks[0].tick_sets]
    assert labels == ["allowed", "forbidden"]
    assert marked.report.blocks[0].tick_sets[1][1].size > 0


def test_a_run_leaves_the_pattern_and_the_indexed_list_behind(
        entry, halite):
    """Two files, because neither is derivable from the other by
    somebody reading the folder later: the .xy is what gets plotted
    and the list is what says which plane a peak belongs to."""
    module, action = MODULES.find("pxrd.simulate")
    params = action.coerce({"two_theta_min": 20.0,
                            "two_theta_max": 50.0})
    folder = module_record.open_run(entry, module, action, params,
                                    halite)
    result = pxrd_module.simulate_pattern(
        Job(structure=halite, params=params, folder=folder))
    module_record.close_run(folder, result)

    x, y = read_xy(folder.path / "pattern.xy")
    listing = (folder.path / "reflections.txt").read_text()

    assert result.ok
    assert y.max() == pytest.approx(100.0)
    assert x[0] == pytest.approx(20.0)
    assert "2-theta" in listing
    assert "    1   1   1" in listing


def test_a_run_with_no_workspace_still_answers(halite):
    """The answer is a picture and a table on screen, and where a file
    gets saved is the user's to choose -- the same argument Zeo++
    makes about a run with nowhere to write."""
    result = pxrd_module.simulate_pattern(
        Job(structure=halite, params={"two_theta_max": 50.0}))

    assert result.ok
    assert result.artifacts == ()
    assert result.report


def test_a_range_nothing_falls_in_is_a_failed_run_not_a_crash(halite):
    result = pxrd_module.simulate_pattern(Job(
        structure=halite,
        params={"two_theta_min": 0.6, "two_theta_max": 1.0}))

    assert not result.ok
    assert "wider range" in result.message


def test_the_reflection_table_exports_as_csv(halite):
    """The grid and nothing else: a file whose first line is a
    sentence is one every reader has to be told to skip."""
    result = pxrd_module.simulate_pattern(Job(
        structure=halite,
        params={"two_theta_min": 20.0, "two_theta_max": 50.0}))
    lines = result.report.blocks[1].as_csv().splitlines()

    assert lines[0] == "No.,hkl,d (\u00c5),2\u03b8 (\u00b0),I (%)"
    assert lines[1].startswith("1,(1 1 1),")
    assert len(lines) == len(result.report.blocks[1].rows) + 1
    assert "Calculated intensities" not in lines[0]


def test_a_quantity_table_exports_without_inventing_headings(halite):
    """The default three are a convention rather than headings a
    reader needs, so they are not written."""
    from xtal.modules.report import Row, Table

    csv_text = Table(rows=(Row.number("Largest free sphere", 9.18,
                                      "A"),)).as_csv()

    assert csv_text == "Largest free sphere,9.180,A\n"


def test_the_curve_prints_as_characters_for_a_log(halite):
    """The same report prints from the CLI, renders into a dock and is
    asserted headless -- which is what the block being data rather
    than a widget buys."""
    result = pxrd_module.simulate_pattern(Job(
        structure=halite, params={"two_theta_max": 50.0}))
    text = result.report.as_text()

    assert "2-theta (degrees)" in text
    assert "#" in text
