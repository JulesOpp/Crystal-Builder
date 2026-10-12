"""The thermochemistry and IR results in the window."""

from __future__ import annotations

import numpy as np
import pytest

from xtal.modules.report import Modes, Report, Spectrum
from xtalapp.docks.results import ResultsDock, select_mode


@pytest.fixture
def dock(qtbot):
    widget = ResultsDock()
    qtbot.addWidget(widget)
    return widget


def _report():
    frequencies = np.array([0.0, 0.0, 0.0, 1600.0, 3650.0, 3750.0])
    modes = Modes(title="Vibrational modes", frequencies=frequencies,
                  displacements=np.zeros((6, 3, 3)),
                  elements=("O", "H", "H"), cart=np.zeros((3, 3)))
    spectrum = Spectrum(title="IR spectrum",
                        frequencies=frequencies[3:],
                        intensities=np.array([60.0, 5.0, 40.0]),
                        modes=(3, 4, 5))
    return Report(title="IR", blocks=(modes, spectrum))


def test_clicking_a_stick_selects_its_mode(dock):
    """A peak is chosen on the spectrum and watched from the mode
    table: the click has to land on the row of the stick nearest it,
    in the table's own numbering, rigid modes and all."""
    report = _report()
    dock.show_report(report)
    spectrum = report.spectra[0]
    assert select_mode(spectrum, dock, 3700.0) == 4
    view = next(w.view for w in dock._blocks if hasattr(w, "animate"))
    assert view.selectionModel().selectedRows()[0].row() == 4
    assert select_mode(spectrum, dock, 1500.0) == 3


def test_the_band_is_redrawn_at_the_width_asked(dock):
    report = _report()
    dock.show_report(report)
    widget = next(w for w in dock._blocks if hasattr(w, "fwhm"))
    narrow = widget.plot.curve.y.max()
    widget.fwhm.setValue(40.0)
    assert widget.plot.curve.y.max() < narrow
    # Drawn as IR is: wavenumber falling from left to right.
    assert widget.plot.curve.x[0] > widget.plot.curve.x[-1]

