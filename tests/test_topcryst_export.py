"""The CIF written for an upload to TopCryst."""

from xtal.core.site import Site
from xtal.core.structure import TOPOLOGY, Bond
from xtal.io import read_cif
from xtal.io.export import write_for_topcryst


def test_the_topcryst_export_holds_no_markers_or_net_edges(rutile,
                                                           tmp_path):
    """TopCryst reads what it is given as chemistry: a marker would
    reach it as an unknown element sitting in the cell, and a net
    edge as a bond four times too long."""
    rutile.sites.append(Site("X", [0.25, 0.25, 0.25], label="X1"))
    rutile.bonds += [Bond(0, 1, (0, 0, 0), kind="explicit"),
                     Bond(0, 2, (0, 0, 0), kind=TOPOLOGY)]

    written = write_for_topcryst(rutile, tmp_path, "rutile")

    assert written == tmp_path / "topcryst" / "rutile.cif"
    back = read_cif(written)
    assert sorted(s.element for s in back.sites) == ["O", "Ti"]
    assert back.space_group.number == 136
    text = written.read_text()
    assert "X1" not in text
    assert TOPOLOGY not in text
    assert len(rutile.sites) == 3       # the document is untouched
