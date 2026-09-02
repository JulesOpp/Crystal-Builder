"""What a tooltip says about one atom.

The decision under test is not the formatting but the *content*: a
tooltip that always says the same four things is one people learn to
ignore, so it says what the current view is about and nothing else.
"""

from xtal.core import describe, p1
from xtal.ff.uff import typer


def test_an_atom_says_its_label_and_what_it_is(rutile):
    """The two facts worth having without opening a panel."""
    cell = p1.expand(rutile)
    text = describe.atom(rutile, cell, 0)
    assert "Ti" in text
    assert "titanium" in text


def test_the_element_is_named_rather_than_repeated(rutile):
    """"O1  O" says one thing twice.  The label already carries the
    symbol on anything that came out of a CIF."""
    cell = p1.expand(rutile)
    lines = describe.atom(rutile, cell, 2).splitlines()
    assert lines[0].count("O") == 1


def test_the_force_field_is_quiet_unless_it_is_on_screen(rutile):
    """The UFF type is part of what the view is about only while
    somebody is looking at the force field."""
    cell = p1.expand(rutile)
    assert "UFF" not in describe.atom(rutile, cell, 0)

    types = typer.assign(rutile).types
    with_ff = describe.atom(rutile, cell, 0, atom_type=types[0])
    assert "UFF" in with_ff
    assert types[0].name in with_ff


def test_a_type_the_typer_is_unsure_of_says_so(rutile):
    """A wrong type gives a plausible number rather than an obvious
    error, so the doubt has to travel with the type."""
    cell = p1.expand(rutile)
    unsure = typer.AtomType("C_3", typer.UNCERTAIN, "nothing fitted")
    assert "uncertain" in describe.atom(rutile, cell, 0,
                                        atom_type=unsure)


def test_a_long_reason_is_cut_rather_than_run_on(rutile):
    """The argument for a coordination the typer had to talk itself
    into belongs in the panel, not under the cursor."""
    cell = p1.expand(rutile)
    wordy = typer.AtomType("C_3", typer.CERTAIN, "because " * 40)
    line = [ln for ln in
            describe.atom(rutile, cell, 0, atom_type=wordy).splitlines()
            if "UFF" in ln][0]
    assert len(line) < describe.REASON_LIMIT + 40
    assert line.endswith("...")


def test_displacement_parameters_only_when_they_are_drawn(rutile):
    """U_eq is what an ORTEP picture is *of*, and is noise beside a
    ball and stick."""
    cell = p1.expand(rutile)
    assert "U_eq" not in describe.atom(rutile, cell, 0)

    rutile.sites[0].u_iso = 0.0125
    text = describe.atom(rutile, cell, 0, thermal=True)
    assert "U_eq" in text and "0.0125" in text


def test_an_ellipsoid_says_whether_anybody_measured_it(rutile):
    """An ORTEP drawn from a u_iso is a sphere by assumption rather
    than by measurement, and the picture gives no sign of which."""
    cell = p1.expand(rutile)
    rutile.sites[0].u_iso = 0.01
    assert "isotropic" in describe.atom(rutile, cell, 0, thermal=True)

    rutile.sites[0].u_aniso = (0.01, 0.02, 0.03, 0.0, 0.0, 0.0)
    assert "anisotropic" in describe.atom(rutile, cell, 0,
                                          thermal=True)


def test_an_atom_with_no_thermal_data_says_that_too(rutile):
    """Silence would read as "spherical", which is a different claim
    from "nobody refined it"."""
    cell = p1.expand(rutile)
    assert "no displacement" in describe.atom(rutile, cell, 0,
                                              thermal=True)


def test_a_partly_occupied_site_says_so_first(rutile):
    """It changes what every number under it means."""
    cell = p1.expand(rutile)
    rutile.sites[0].occupancy = 0.5
    assert "occupancy 0.5" in describe.atom(rutile, cell, 0)


def test_an_atom_the_cell_does_not_have_says_nothing(rutile):
    """A tooltip over a structure that changed under it must not say
    something about somebody else's atom."""
    cell = p1.expand(rutile)
    assert describe.atom(rutile, cell, cell.n_atoms) == ""
    assert describe.atom(rutile, cell, -1) == ""
