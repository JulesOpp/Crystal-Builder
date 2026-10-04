"""Computed charges written onto the sites, where a file can carry
them."""

import numpy as np
import pytest

from xtal.core import p1
from xtal.core.site import Site
from xtal.ff.charges import sites
from xtal.io.cif_reader import read_cif_string
from xtal.io.cif_writer import cif_string


def test_a_site_takes_the_mean_of_its_images_and_says_how_far_apart(
        rutile):
    """Rutile's oxygen site is four atoms of the cell.  Fails if a site
    takes one image's charge, which would hide a cell less symmetric
    than its group."""
    cell = p1.expand(rutile)
    oxygens = np.flatnonzero(cell.site_idx == 1)
    values = np.where(cell.site_idx == 0, 1.0, -0.5)
    values[oxygens[0]] = -0.6
    charges, spread = sites.per_site(rutile, values)
    assert charges[0] == pytest.approx(1.0)
    assert charges[1] == pytest.approx(-0.5 - 0.1 / len(oxygens))
    assert spread == pytest.approx(0.1)


def test_eqeq_on_the_sites_holds_a_marker_back_and_leaves_it_none(
        rutile):
    """A centroid is not chemistry: EQeq is handed the cell without
    it, and its site gets no charge rather than a refusal."""
    marked = rutile.copy()
    marked.sites.append(Site("X", np.array([0.5, 0.5, 0.5])))
    values, note = sites.eqeq_values(marked)
    charges, spread = sites.per_site(marked, values)
    assert charges[-1] is None
    assert charges[0] > 0 > charges[1]
    assert spread < sites.SPREAD
    assert "EQeq" in note
    # And they leave in the CIF and come back.
    marked.sites.pop()
    for site, q in zip(marked.sites, charges, strict=False):
        site.charge = q
    back = read_cif_string(cif_string(marked))
    assert [s.charge for s in back.sites] == pytest.approx(charges[:2],
                                                           abs=1e-5)


def test_the_window_writes_eqeq_charges_as_one_undo_step(rutile):
    """Nothing in the window called SetCharges, so EQeq's charges
    could not reach a file without a script."""
    pytest.importorskip("PySide6")
    from xtalapp.document import Document

    document = Document(rutile.copy())
    said = document.assign_eqeq_charges()
    assert "EQeq charges on 2 site(s)" in said
    assert document.structure.sites[0].charge > 0
    document.undo()
    assert document.structure.sites[0].charge == rutile.sites[0].charge
    assert document.keep_shown_charges() == "no charges are shown to keep"
