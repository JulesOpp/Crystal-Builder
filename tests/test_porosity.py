"""Reading what Zeo++ writes.

Captured from a real run of ``network`` 0.3 on MFU-4l, because the
whole risk in these parsers is that the files are undocumented,
header-less and inconsistent with each other -- one is a bare line of
numbers, one is ``Key: value`` with a value that is sometimes missing
entirely, and one has a header and four columns.  Nothing here needs
Zeo++ installed, which is the point: the parsers are the half of the
module that can be tested anywhere.
"""

import numpy as np
import pytest

from xtal.analysis import porosity

RES = "   MFU4l.res    18.72736 9.18223  18.72243\n"

SA = (
    "@ MFU4l.sa Unitcell_volume: 29955.3   Density: 0.559382   "
    "ASA_A^2: 5358.14 ASA_m^2/cm^3: 1788.71 ASA_m^2/g: 3197.65 "
    "NASA_A^2: 0 NASA_m^2/cm^3: 0 NASA_m^2/g: 0\n"
    "Number_of_channels: 1 Channel_surface_area_A^2: 5358.14  \n"
    "Number_of_pockets: 0 Pocket_surface_area_A^2: \n")

VOL = (
    "@ MFU4l.vol Unitcell_volume: 29955.3   Density: 0.559382   "
    "AV_A^3: 13827.4 AV_Volume_fraction: 0.4616 AV_cm^3/g: 0.825196 "
    "NAV_A^3: 0 NAV_Volume_fraction: 0 NAV_cm^3/g: 0\n"
    "Number_of_channels: 1 Channel_volume_A^3: 13827.4  \n"
    "Number_of_pockets: 0 Pocket_volume_A^3: \n")


def psd_text(counts=((11.5, 40), (18.7, 900))) -> str:
    """A histogram of a thousand bins with a few of them filled --
    which is the shape Zeo++ actually writes."""
    lines = ["Pore size distribution histogram",
             "Bin size (A): 0.1",
             "Number of bins: 1000",
             "From: 0", "To: 100",
             "Total samples: 5000",
             "Accessible samples: 2910",
             "Fraction of sample points in node spheres: 0.582",
             "Fraction of sample points outside node spheres: 0",
             "", "Bin Count Cumulative_dist Derivative_dist"]
    filled = {round(d, 1): n for d, n in counts}
    total = sum(filled.values()) or 1
    seen = 0
    for index in range(1000):
        diameter = round(index * 0.1, 1)
        count = filled.get(diameter, 0)
        seen += count
        remaining = (total - seen) / total
        lines.append(f"{diameter} {count} {remaining:.6f} 0")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------- the diameters

def test_the_three_diameters_are_in_order():
    found = porosity.parse_res(RES)
    assert found.included == pytest.approx(18.72736)
    assert found.free == pytest.approx(9.18223)
    assert found.included_along_free == pytest.approx(18.72243)


def test_the_free_sphere_is_the_smallest_of_the_three():
    """Not an assertion about this file -- an assertion that the three
    numbers have not been read in the wrong order, which is the one
    way this parser can be wrong and still look right."""
    found = porosity.parse_res(RES)
    assert found.free < found.included_along_free <= found.included


def test_the_numbers_are_taken_from_the_right(tmp_path):
    """The name Zeo++ writes is whatever it was told, and may be a
    path -- so counting from the left would break on a run in a
    subdirectory."""
    found = porosity.parse_res("  runs/001/out.res 5.0 3.0 4.5\n")
    assert (found.included, found.free) == (5.0, 3.0)


def test_every_diameter_carries_what_it_means():
    for label, _value, symbol, meaning in \
            porosity.parse_res(RES).rows():
        assert label and symbol and meaning


def test_an_empty_res_file_says_to_read_the_log():
    with pytest.raises(porosity.ZeoOutputError, match="log"):
        porosity.parse_res("")


# --------------------------------------------------------- area and volume

def test_the_surface_area_is_read():
    found = porosity.SurfaceArea.parse(SA, probe=1.86)
    assert found.accessible_per_gram == pytest.approx(3197.65)
    assert found.accessible_per_volume == pytest.approx(1788.71)
    assert found.channels == 1
    assert found.pockets == 0
    assert found.probe == 1.86


def test_a_key_with_no_value_does_not_swallow_the_next_one():
    """Zeo++ writes ``Pocket_surface_area_A^2:`` and then nothing at
    all when there are no pockets.  A parser that took the next token
    as its value would read the following line's key as a number."""
    found = porosity.parse_summary(SA)
    assert found["Pocket_surface_area_A^2"] == 0.0
    assert found["Number_of_pockets"] == 0.0


def test_the_volume_is_read():
    found = porosity.Volume.parse(VOL, probe=1.86)
    assert found.accessible_per_gram == pytest.approx(0.825196)
    assert found.accessible_fraction == pytest.approx(0.4616)
    assert found.channels == 1


def test_an_empty_summary_says_to_read_the_log():
    with pytest.raises(porosity.ZeoOutputError, match="log"):
        porosity.parse_summary("")


# ------------------------------------------------- the size distribution

def test_the_histogram_is_read():
    found = porosity.parse_psd(psd_text(), probe=1.2)
    assert found.n_bins == 1000
    assert found.bin_size == pytest.approx(0.1)
    assert found.total_samples == 5000
    assert found.accessible_samples == 2910
    assert found.accessible_fraction == pytest.approx(0.582)


def test_the_peak_is_the_middle_of_its_bin_not_its_edge():
    """A bin holds everything from its edge to one width later, so
    quoting the edge reports every pore half a bin narrower than it
    is."""
    found = porosity.parse_psd(psd_text([(18.7, 900)]))
    assert found.mode() == pytest.approx(18.75)


def test_the_mean_is_weighted_by_count():
    found = porosity.parse_psd(psd_text([(10.0, 1), (20.0, 3)]))
    assert found.mean() == pytest.approx(0.25 * 10.05 + 0.75 * 20.05)


def test_the_window_is_the_part_worth_drawing():
    """A thousand bins of 0.1 A is a hundred Angstrom of axis for a
    material whose pores span four."""
    found = porosity.parse_psd(psd_text([(11.5, 40), (18.7, 900)]))
    window = found.window()

    assert window.n_bins < found.n_bins
    assert window.diameters[0] < 11.5 < window.diameters[-1]
    assert window.diameters[0] < 18.7 < window.diameters[-1]
    # and the peak is unchanged by cutting the empty bins off
    assert window.mode() == pytest.approx(found.mode())


def test_an_empty_histogram_has_a_window_and_does_not_raise():
    found = porosity.parse_psd(psd_text([]))
    assert found.window().n_bins == found.n_bins
    assert found.mode() == 0.0
    assert found.mean() == 0.0


def test_an_empty_psd_file_says_to_read_the_log():
    with pytest.raises(porosity.ZeoOutputError, match="log"):
        porosity.parse_psd("Pore size distribution histogram\n")


# ----------------------------------------------------------- the probes

def test_a_named_probe_has_a_radius():
    assert porosity.probe_radius("n2") == pytest.approx(1.86)
    assert "Nitrogen" in porosity.probe_label("n2")


def test_a_custom_probe_uses_the_number_given():
    assert porosity.probe_radius("custom", 1.4) == pytest.approx(1.4)
    assert "1.40" in porosity.probe_label("custom", 1.4)


# ------------------------------------------------------ what it refuses

def test_a_disordered_structure_is_refused(rutile):
    """Zeo++ has no way to express half an atom, and handed one it
    returns a confident number for a crystal that does not exist."""
    rutile.sites[1].occupancy = 0.5
    message = porosity.refuse(rutile)
    assert "partially occupied" in message
    assert "resolve the disorder" in message


def test_an_ordered_structure_is_not_refused(quartz):
    assert porosity.refuse(quartz) == ""


def test_an_empty_structure_is_refused():
    from xtal import Structure
    assert porosity.refuse(Structure.empty())
    assert porosity.refuse(None)


def test_the_diameters_summarise_in_one_line():
    assert "D_f" in porosity.parse_res(RES).summary()


def test_the_histogram_columns_are_arrays():
    found = porosity.parse_psd(psd_text())
    for column in (found.diameters, found.counts, found.cumulative,
                   found.derivative):
        assert isinstance(column, np.ndarray)
        assert len(column) == found.n_bins
