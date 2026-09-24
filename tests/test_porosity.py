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

from tests.conftest_zeo import (
    CHAN,
    RES,
    SA,
    VOL,
    VOLPO,
    VORO_EDGES,
    VORO_NODES,
    psd_text,
)
from xtal.analysis import porosity

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


# ----------------------------------------------------- the channel network

def _cell():
    """MFU-4l's cell, which is what the captured node files are in."""
    from xtal.core.lattice import Lattice
    return Lattice.cubic(31.0569)


def test_a_channel_carries_its_dimensionality():
    """The one number no other Zeo++ output has, and the reason
    ``-chan`` is run at all."""
    channels = porosity.parse_chan(CHAN)
    assert len(channels) == 1
    assert channels[0].dimensionality == 3
    assert channels[0].included == pytest.approx(18.7273)
    assert channels[0].free == pytest.approx(9.18228)


def test_the_channel_diameters_match_the_res_file():
    """Two flags of one run describing one crystal.  If these ever
    disagree the module has paired a picture with somebody else's
    numbers."""
    channel = porosity.parse_chan(CHAN)[0]
    res = porosity.parse_res(RES)
    assert channel.included == pytest.approx(res.included, abs=0.01)
    assert channel.free == pytest.approx(res.free, abs=0.01)


def test_dimensionality_is_said_once_when_they_agree():
    channels = porosity.parse_chan(CHAN)
    assert porosity.dimensionality(channels).startswith("3D")


def test_dimensionality_names_every_kind_when_they_differ():
    """Averaging two channels' dimensionality would invent a number
    that describes neither of them."""
    channels = (porosity.Channel(0, 1, 6.0, 5.0, 6.0),
                porosity.Channel(1, 3, 9.0, 8.0, 9.0))
    said = porosity.dimensionality(channels)
    assert "1D" in said and "3D" in said


def test_a_dense_solid_has_no_channels_and_that_is_an_answer():
    text = "out.chan   0 channels identified of dimensionality \n"
    channels = porosity.parse_chan(text)
    assert channels == ()
    assert "no channels" in porosity.dimensionality(channels)


def test_a_truncated_chan_file_says_the_run_failed():
    with pytest.raises(porosity.ZeoOutputError):
        porosity.parse_chan("")


def test_the_fifth_column_of_a_voronoi_file_is_a_radius():
    """``read_xyz`` would take it for an occupancy, which is why this
    file has a parser of its own."""
    _frac, radii = porosity.parse_voro_nodes(VORO_NODES, _cell())
    assert len(radii) == 6
    assert radii.max() == pytest.approx(9.371)


def test_the_widest_node_is_where_the_largest_sphere_sits():
    """Twice its radius is D_i, which is how the picture and the table
    are checked against each other."""
    frac, radii = porosity.parse_voro_nodes(VORO_NODES, _cell())
    net = porosity.PoreNetwork(nodes=frac, radii=radii)
    node, radius = net.largest()
    assert 2 * radius == pytest.approx(18.742, abs=0.01)
    assert _cell().to_cart(node) == pytest.approx([15.528, 0.0, 0.0])


def test_voronoi_nodes_are_stored_fractional():
    """The display range draws this in more than one cell, and a
    cartesian point cannot be repeated."""
    frac, _radii = porosity.parse_voro_nodes(VORO_NODES, _cell())
    assert frac.max() <= 1.0


def test_the_edges_come_back_as_endpoints_not_indices():
    """That file's POINTS block is every node followed by a second
    copy of the accessible ones, and its LINES index into the
    combination -- a different list from the node file's."""
    starts, ends = porosity.parse_voro_edges(VORO_EDGES, _cell())
    assert starts.shape == (3, 3) and ends.shape == (3, 3)
    assert _cell().to_cart(starts[0]) == pytest.approx(
        [7.782, 3.983, 3.983])


def test_an_index_past_the_end_is_a_truncated_file_not_a_segment():
    text = VORO_EDGES.replace("2 2 3", "2 2 99")
    starts, _ends = porosity.parse_voro_edges(text, _cell())
    assert len(starts) == 2


def test_a_pore_network_round_trips_through_a_dict():
    """It is written into the project's session, so it has to come
    back as what it went in as."""
    frac, radii = porosity.parse_voro_nodes(VORO_NODES, _cell())
    starts, ends = porosity.parse_voro_edges(VORO_EDGES, _cell())
    net = porosity.PoreNetwork(
        nodes=frac, radii=radii, edge_starts=starts, edge_ends=ends,
        probe=1.2, channels=porosity.parse_chan(CHAN))
    back = porosity.PoreNetwork.from_dict(net.to_dict())
    assert np.allclose(back.nodes, net.nodes)
    assert np.allclose(back.radii, net.radii)
    assert np.allclose(back.edge_ends, net.edge_ends)
    assert back.channels == net.channels
    assert back.probe == 1.2


def test_an_empty_pore_network_has_no_largest_sphere():
    assert porosity.PoreNetwork().largest() is None
    assert porosity.PoreNetwork().n_nodes == 0


# ------------------------------------------------------ the two volumes

def test_the_probe_occupiable_volume_spells_every_key_differently():
    """-volpo writes POAV_* where -vol writes AV_*.  A parser that
    reads only the first spelling answers a confident 0.000 cm^3/g for
    a framework that is three quarters empty."""
    found = porosity.Volume.parse(VOLPO, probe=1.86)
    assert found.accessible_per_gram == pytest.approx(1.32503)
    assert found.accessible_fraction == pytest.approx(0.7412)
    assert found.accessible_volume == pytest.approx(22202.9)
    assert found.occupiable


def test_the_occupiable_volume_is_the_larger_of_the_two():
    """Always, and it is why quoting one for the other matters."""
    centre = porosity.Volume.parse(VOL, probe=1.86)
    occupied = porosity.Volume.parse(VOLPO, probe=1.86)
    assert occupied.accessible_per_gram > centre.accessible_per_gram
    assert not centre.occupiable


def test_volpo_reports_no_counts_and_says_so():
    """Zero channels and "not reported" are different answers, and a
    row saying the first over a framework with one is worse than no
    row."""
    assert porosity.Volume.parse(VOL).counted
    assert not porosity.Volume.parse(VOLPO).counted


# ------------------------------------------------------------ the radii

def test_the_transcribed_radii_still_match_the_vendored_source():
    """``ZEO_RADII`` is typed out of Zeo++'s ``networkinfo.cc``,
    because the table is compiled into the binary and written nowhere
    it could be read back -- and the *picture* of a run has to be
    drawn with the radii its *numbers* were computed with.  So a Zeo++
    upgrade that changes a radius fails here rather than quietly
    moving a surface off the volume beside it.

    ``resources/zeo++-0.3`` is gitignored, so without the excerpt in
    ``tests/data`` this skipped in every clean checkout and in CI --
    the one place a transcription error would otherwise be caught.
    The unpacked source wins where it exists, because that is what
    notices an upgrade."""
    import re
    from pathlib import Path

    here = Path(__file__).resolve().parent
    source = here.parent.joinpath("resources", "zeo++-0.3",
                                  "networkinfo.cc")
    if not source.is_file():
        source = here / "data" / "zeo_radii.cc"
    text = source.read_text()
    block = text[text.index("void initializeRadTable()"):]
    theirs = {symbol: float(radius) for symbol, radius in re.findall(
        r'radTable\.insert\(pair <string,double> '
        r'\("([A-Za-z]+)",\s*([0-9.]+)\)\)',
        block[:block.index("}")])}

    assert theirs
    assert porosity.ZEO_RADII == theirs


def test_an_element_zeo_has_never_heard_of_gets_a_default():
    assert porosity.zeo_radius("Zn") == pytest.approx(1.39)
    assert porosity.zeo_radius("Uuo") == pytest.approx(1.7)
    # Whatever case the caller spells it in.
    assert porosity.zeo_radius("zn") == porosity.zeo_radius("Zn")
