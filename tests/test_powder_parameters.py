"""The parameter set: the numbers a refinement starts from, which of
them it moves, and the text Copy and Paste carry them in."""

from __future__ import annotations

import numpy as np
import pytest

from xtal.core.lattice import Lattice
from xtal.core.structure import Site, Structure
from xtal.powder import parameters as p
from xtal.powder.data import PowderData, PowderError, Radiation

#: RietX's Cu preset, as ``bridge.preset_parameters`` reads it -- the
#: rows the set names, so these tests need no RietX.
PRESET = {
    "phases.0.scale": 1.0,
    "phases.0.lor_size": 0.0, "phases.0.gauss_size": 0.0,
    "phases.0.lor_strain": 0.0, "phases.0.gauss_strain": 0.0,
    "instrument.zero_shift": 0.0,
    "instrument.geometry.sample_displacement": 0.0,
    "instrument.profile.u": 0.0, "instrument.profile.v": 0.0,
    "instrument.profile.w": 0.001, "instrument.profile.x": 0.001,
    "instrument.profile.y": 0.0,
    **{f"instrument.background.c{n}": 0.0 for n in range(8)},
}


@pytest.fixture
def pattern():
    """A flat 100-count background under a few sharp lines."""
    two_theta = np.arange(10.0, 60.0, 0.02)
    counts = np.full_like(two_theta, 100.0)
    for centre in (20.0, 31.0, 44.0):
        counts += 5000.0 * np.exp(-((two_theta - centre) / 0.05) ** 2)
    return PowderData(two_theta, counts)


@pytest.fixture
def start(rutile, pattern):
    return p.defaults(PRESET, structure=rutile, data=pattern)


def test_the_text_form_reads_back_what_it_wrote(start):
    """Copy then Paste must carry every flag and every number -- a
    number to a hundredth of its esd, so a zero-cycle run on pasted
    numbers gives the R values the copied ones did."""
    start.set_value("zero_error", 0.00119874)
    start["zero_error"].esd = 0.0003
    start.set_refine("zero_error", True)
    start.set_refine("Ti1_occ", True)
    text = start.to_text()
    other = p.defaults(PRESET, structure=None)
    other = p.with_structure(other, _rutile_again())
    other.paste(text)
    for row in start:
        pasted = other[row.name]
        assert pasted.refine == row.refine, row.name
        if row.value is None:
            continue
        tolerance = row.esd / 100 if row.esd else 1e-9 * max(
            1.0, abs(row.value))
        assert pasted.value == pytest.approx(row.value, abs=tolerance)


def test_a_value_is_written_to_its_esds_precision():
    assert p.format_value(0.00119874, 0.0003) == "0.0011987 ± 0.00030"
    assert p.format_value(4.593976, 0.00012) == "4.5939760 ± 0.00012"
    assert p.format_value(98.873461, 0.21) == "98.8735 ± 0.21"
    assert p.format_value(0.0) == "0"
    assert p.format_value(0.001100492572) == "0.001100492572"


def test_the_rows_read_as_a_person_would_write_them(start):
    text = start.to_text()
    assert "\nscale 1 Refine\n" in text
    assert "\nzero_error 0 NoRefine\n" in text
    assert "\nTi1_xyz Refine\n" in text
    assert "\nO2_occ 1 NoRefine\n" in text
    assert "# Peak shape\n" in text


def test_an_unknown_name_is_refused_with_its_line(start):
    """A typo in a pasted line silently ignored is a parameter the
    person believes is refining and is not."""
    with pytest.raises(PowderError, match="line 2: .*'zero_eror'"):
        start.paste("scale 2 Refine\nzero_eror 0.1 Refine\n")


def test_a_line_without_a_flag_is_refused(start):
    with pytest.raises(PowderError, match="line 1: .*Refine or NoRefine"):
        start.paste("zero_error 0.1\n")


def test_a_paste_that_fails_changes_nothing(start):
    """Half a paste is a set nobody wrote: the first lines applied and
    the rest not."""
    before = start.to_text()
    with pytest.raises(PowderError):
        start.paste("scale 7 Refine\nW 0.5 Refine\nU banana Refine\n")
    assert start.to_text() == before


def test_a_few_lines_pasted_leave_the_rest_alone(start):
    start.set_value("W", 0.02)
    assert start.paste("U 0.003 ± 0.001 Refine\n") == 1
    assert start["U"].value == pytest.approx(0.003)
    assert start["U"].esd == pytest.approx(0.001)
    assert start["W"].value == pytest.approx(0.02)


def test_a_flag_takes_no_value(start):
    with pytest.raises(PowderError, match="Ti1_xyz is a flag"):
        start.paste("Ti1_xyz 0.3 Refine\n")


def test_pasting_a_higher_coefficient_grows_the_background(start):
    start.paste("bkg_c10 1.5 NoRefine\n")
    assert start.background_terms == 11
    assert start["bkg_c10"].value == pytest.approx(1.5)
    assert start["bkg_c9"].value == 0.0


def test_more_background_terms_keeps_the_coefficients_it_had(start):
    """Raising the order is how a person follows a background that
    bends; it must not throw away the level the last fit found."""
    start.set_value("bkg_c0", 123.0)
    start.set_value("bkg_c1", -4.0)
    start.set_background_terms(12)
    assert start["bkg_c0"].value == 123.0
    assert start["bkg_c1"].value == -4.0
    assert start.background_terms == 12
    start.set_background_terms(2)
    assert [r.name for r in start.in_group(p.BACKGROUND)] == \
        ["bkg_c0", "bkg_c1"]
    names = start.names()
    assert names.index("bkg_c1") < names.index("zero_error")


def test_the_background_starts_under_the_data(start):
    """At zero, the first fit spends its early cycles pulling the
    whole curve up to the counts; at the median, a crowded pattern
    starts above its own floor."""
    assert 90.0 <= start["bkg_c0"].value <= 100.0
    assert start["bkg_c1"].value == 0.0


def test_reset_puts_the_profile_back_and_leaves_the_structures_numbers(
        start):
    """Reset is for a background or a broadening that ran away; the
    atoms are the structure's, and Ctrl+Z is how they go back."""
    start.set_value("W", 12.0)
    start.set_value("cs_l", 900.0)
    start.set_background_terms(10)
    start.set_value("bkg_c9", 1e6)
    start.set_value("Ti1_biso", 3.3)
    start["U"].esd = 0.1
    start.reset(p.defaults(PRESET, data=None))
    assert start["W"].value == pytest.approx(0.001)
    assert start["cs_l"].value == 0.0
    assert start["bkg_c9"].value == 0.0
    assert start["U"].esd is None
    assert start["Ti1_biso"].value == 3.3
    assert start.background_terms == 10


def test_reset_keeps_what_is_refined(start):
    start.set_refine("zero_error", True)
    start.set_refine("W", False)
    start.reset(p.defaults(PRESET))
    assert start["zero_error"].refine
    assert not start["W"].refine


def test_a_held_row_is_shown_but_never_set(start):
    """RietX refuses a value for a locked or tied path; it has to be
    left out rather than sent."""
    path = start["sample_displacement"].path
    start.set_refine("sample_displacement", True)
    start.hold({path: "locked for a capillary"})
    assert path not in start.values_by_path()
    assert path not in start.freed_paths()
    assert "# sample_displacement 0 Refine  (held: locked for a " \
        "capillary)" in start.to_text()


def test_a_fit_writes_its_values_and_esds_back(start):
    """What was not refined loses its esd: an esd describes the model
    that gave it."""
    start["zero_error"].esd = 0.5
    start.take({"instrument.profile.w": 0.0023,
                "instrument.zero_shift": -0.01},
               {"instrument.profile.w": 0.0001})
    assert start["W"].value == pytest.approx(0.0023)
    assert start["W"].esd == pytest.approx(0.0001)
    assert start["zero_error"].value == pytest.approx(-0.01)
    assert start["zero_error"].esd is None


def test_a_fit_limited_to_some_groups_leaves_the_rest_alone(start):
    """A Pawley fit gives back its background and peak shape and never
    its scale -- the scaffold's scale is no start for a Rietveld run,
    and without the limit the next run begins a thousand times off."""
    start["scale"].esd = 0.001
    start.take({"phases.0.scale": 1234.0, "instrument.profile.w": 0.002},
               {"phases.0.scale": 5.0, "instrument.profile.w": 1e-4},
               groups=(p.BACKGROUND, p.PROFILE))
    assert start["scale"].value == 1.0 and start["scale"].esd == 0.001
    assert start["W"].value == pytest.approx(0.002)


def test_the_boxes_become_flags(start):
    """``xtal run`` without a parameter file still means what its boxes
    said: each box turns on its rows and nothing else, and the scale
    is always refined."""
    start.flag_boxes(("background", "profile", "positions"))
    flagged = {row.name for row in start if row.refine}
    assert {"scale", "bkg_c0", "bkg_c7", "U", "W", "Y", "Ti1_xyz",
            "O2_xyz"} <= flagged
    assert not flagged & {"zero_error", "sample_displacement", "cs_l",
                          "strain_g", "po_r", "Ti1_biso", "O2_occ"}


def test_every_row_answers_to_a_box(start):
    """A row no box names could never be freed from ``xtal run``, and
    the plan could not put it in a stage."""
    assert all(p.box_of(row.path) for row in start)


def test_a_group_turns_on_and_off_together(start):
    start.set_group_refine(p.SAMPLE, True)
    assert all(row.refine for row in start.in_group(p.SAMPLE))
    assert set(start.freed_paths()) >= {
        "phases.0.lor_size", "phases.0.gauss_strain"}


def test_a_synchrotron_does_not_refine_specimen_displacement():
    capillary = p.defaults(PRESET, synchrotron=True)
    assert not capillary["sample_displacement"].refine


def test_atom_rows_are_the_structures_values(rutile):
    rutile.sites[1].u_iso = 0.01
    rows = {row.name: row for row in p.atom_rows(rutile)}
    assert rows["O2_biso"].value == pytest.approx(0.01 * p.B_PER_U)
    assert rows["Ti1_biso"].value == p.DEFAULT_BISO
    assert rows["Ti1_xyz"].value is None
    assert rows["O2_occ"].path == "phases.0.atoms.1.occ"
    assert {row.owner for row in rows.values()} == {"structure"}


def test_a_dummy_atom_has_no_rows(rutile):
    """A marker is not a scatterer: RietX is never handed one, so there
    is nothing of it to refine."""
    rutile.add_site(Site("X", [0.5, 0.5, 0.5]))
    labels = [label for _index, label in p.site_labels(rutile)]
    assert len(labels) == 2
    assert not any(row.name.startswith("X") for row in
                   p.atom_rows(rutile))


def test_two_sites_with_one_label_are_two_rows():
    """RietX addresses atoms by index here, but the text form addresses
    them by name, and two O1 rows would be one."""
    structure = Structure.from_arrays(
        Lattice.from_parameters(5, 5, 5, 90, 90, 90), ["O", "O"],
        [[0, 0, 0], [0.5, 0.5, 0.5]], space_group="P1")
    for site in structure.sites:
        site.label = "O1"
    names = [row.name for row in p.atom_rows(structure)]
    assert len(set(names)) == len(names) == 6


def test_an_edited_structure_keeps_the_atoms_flags(start, rutile):
    start.set_refine("O2_biso", False)
    rutile.sites[0].occupancy = 0.9
    again = p.with_structure(start, rutile)
    assert not again["O2_biso"].refine
    assert again["Ti1_occ"].value == pytest.approx(0.9)



def test_an_edited_structure_keeps_what_the_last_fit_found(start, rutile):
    """The esd of a Biso the structure still has, and what RietX
    holds: a Rietveld run commits its structure, and the table rebuilt
    from it lost every atom's esd and showed a fixed Ti as free."""
    start["Ti1_xyz"].held = "fixed by symmetry"
    start["O2_biso"].esd = 0.03
    start["Ti1_biso"].esd = 0.05
    rutile.sites[0].u_iso = 0.02
    again = p.with_structure(start, rutile)
    assert again["Ti1_xyz"].held == "fixed by symmetry"
    assert again["O2_biso"].esd == 0.03
    assert again["Ti1_biso"].esd is None            # a new value


def test_a_table_row_names_the_site_it_edits(rutile):
    fields = p.site_fields(rutile)
    assert fields["Ti1_biso"] == (0, "biso")
    assert fields["O2_occ"] == (1, "occupancy")
    assert set(fields) == {row.name for row in p.atom_rows(rutile)
                           if row.value is not None}


def test_a_run_log_names_the_set_in_one_line(start):
    """A run's header lists what it was handed; the set's repr was a
    Python object address, and the whole of it is a page."""
    from xtal.workspace import readable_option

    text = readable_option(start)
    assert "\n" not in text
    assert text.startswith(f"{len(start)} parameters, "
                           f"{len(start.freed_paths())} refined")


# --------------------------------------------------- against RietX

def test_the_labels_are_the_ones_rietx_is_given(rutile):
    """The table's Ti1 has to be RietX's atom 0, or a flag frees the
    wrong atom."""
    pytest.importorskip("rietx")
    from xtal.powder import bridge

    phase, indices = bridge.phase_of(rutile)
    assert [atom.label for atom in phase.atoms] == \
        [label for _index, label in p.site_labels(rutile)]
    assert indices == [index for index, _label in p.site_labels(rutile)]


def test_the_preset_is_read_from_rietx():
    pytest.importorskip("rietx")
    from xtal.powder import bridge

    preset = bridge.preset_parameters(Radiation("cu"), 8)
    assert preset["instrument.profile.w"] == pytest.approx(0.001)
    assert preset["phases.0.scale"] == pytest.approx(1.0)
    start = p.defaults(preset)
    assert start.background_terms == 8
    assert set(start.values_by_path()) <= set(preset) | {
        "phases.0.preferred_orientation.r"}


def test_every_path_is_one_rietx_knows(rutile):
    """A path RietX does not have is a parameter the table shows and
    no fit ever moves."""
    pytest.importorskip("rietx")
    import rietx as rx

    from xtal.powder import bridge

    structure, _indices = bridge.to_rietx(rutile)
    refinement = rx.Refinement(
        structure, bridge._with_background(Radiation("cu"), 8),
        history=False)
    known = {row.path for row in refinement.parameters()}
    start = p.defaults(bridge.preset_parameters(Radiation("cu"), 8),
                       structure=rutile)
    for row in start:
        if row.group == p.TEXTURE:
            continue                # only there when an axis is given
        if row.path.endswith(".*"):
            assert any(k.startswith(row.path[:-1]) for k in known) or \
                row.name == "Ti1_xyz", row.path
        else:
            assert row.path in known, row.path


def _rutile_again():
    return Structure.from_arrays(
        Lattice.from_parameters(4.5940, 4.5940, 2.9590, 90, 90, 90),
        ["Ti", "O"], [[0.0, 0.0, 0.0], [0.30530, 0.30530, 0.0]],
        space_group="P4_2/mnm")
