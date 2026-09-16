"""A quantity over a grid of two axes: the energy landscape block.

Most of what is pinned here is about the hole.  A point that did not
finish has to stay unmistakably absent all the way out to the text, the
CSV and the colour scale, because plotted as a zero it is the deepest
point of every landscape it appears in.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.modules.report import Report, Surface


@pytest.fixture
def landscape():
    return Surface(
        title="Energy landscape",
        x=np.array([4.7, 4.9, 5.1]),
        y=np.array([5.2, 5.4]),
        z=np.array([[8.7, 5.7, 8.7], [0.5, 0.0, np.nan]]),
        x_label="a (A)", y_label="c (A)", z_label="E (kcal/mol)",
        converged=np.array([[1, 1, 1], [1, 1, 0]], dtype=bool),
        paths=(("p0.cif", "p1.cif", "p2.cif"),
               ("p3.cif", "p4.cif", "")),
        note="Held: a and c, with the cell fixed at each point.")


def test_a_surface_knows_its_shape(landscape):
    assert landscape.shape == (2, 3)
    assert landscape.n_points == 6
    assert landscape.n_finished == 5


def test_an_unfinished_point_is_not_a_number(landscape):
    """The whole reason the block carries NaN rather than a sentinel:
    anything that is a number is a number somebody will plot."""
    assert np.isnan(landscape.z[1, 2])
    assert landscape.n_finished < landscape.n_points


def test_the_text_shows_a_hole_as_a_hole(landscape):
    """A log is the one place a stopped scan is read without a
    picture, so it has to distinguish "did not converge" from "never
    ran"."""
    text = landscape.as_text()
    assert "--" in text
    assert "did not finish" in text


def test_the_text_marks_a_point_that_did_not_converge(landscape):
    assert "did not reach the tolerance" in landscape.as_text()


def test_a_surface_with_everything_converged_says_nothing_about_it():
    """The footnote is for when it is needed; on a clean scan it is
    noise."""
    clean = Surface(x=np.array([1.0, 2.0]), y=np.array([1.0]),
                    z=np.array([[1.0, 2.0]]),
                    converged=np.ones((1, 2), dtype=bool))
    assert "tolerance" not in clean.as_text()


def test_an_empty_surface_says_so_rather_than_raising():
    assert "nothing to plot" in Surface(title="Empty").as_text()


def test_the_text_says_which_axis_is_which(landscape):
    said = landscape.as_text()
    assert "c (A) down" in said
    assert "a (A) across" in said


def test_the_note_says_what_was_held(landscape):
    """A profile that does not say what was fixed while it was taken
    cannot be read, so the note travels with the numbers."""
    assert "Held" in landscape.as_text()


def test_a_surface_exports_one_row_per_cell(landscape):
    """Not the grid as a matrix: a matrix loses which axis is which
    the moment it is pasted anywhere, and a cell's file has nowhere to
    go in it."""
    lines = [line for line in landscape.as_csv().splitlines() if line]
    assert len(lines) == 1 + 6
    assert lines[0].startswith("a (A),c (A),E (kcal/mol)")
    assert lines[0].endswith("converged,file")
    assert lines[1].endswith("p0.cif")


def test_the_export_carries_the_file_behind_each_cell(landscape):
    """What makes a landscape worth keeping: every point is a
    structure somebody can open again."""
    assert "p4.cif" in landscape.as_csv()


def test_a_cell_with_no_file_exports_an_empty_one(landscape):
    assert landscape.path_at(1, 2) == ""


def test_asking_for_a_cell_that_is_not_there_is_not_an_error(
        landscape):
    """A landscape is drawn from one array and clicked through
    another, and a scan that was stopped has fewer of the second."""
    assert landscape.path_at(9, 9) == ""
    assert landscape.path_at(-1, 0) == ""


def test_two_directions_are_two_sheets_of_one_surface(landscape):
    """Kept apart rather than averaged: where they differ is the
    hysteresis."""
    reverse = landscape.z + 0.4
    both = Surface(x=landscape.x, y=landscape.y, z=landscape.z,
                   z_label="forward",
                   sheets=(("reverse", reverse),))
    assert [label for label, _z in both.all_sheets()] == [
        "forward", "reverse"]
    assert both.as_csv().splitlines()[0].count("forward") == 1
    assert "reverse" in both.as_csv().splitlines()[0]


def test_a_report_finds_its_surfaces(landscape):
    """One line in Report, the same as every other block type."""
    report = Report(title="Scan", blocks=(landscape,))
    assert report.surfaces == [landscape]
    assert "Energy landscape" in report.as_text()
