"""The equilibration seam: xtal.polymer.protocol."""

from __future__ import annotations

import pytest

from xtal.polymer.protocol import (
    NPT,
    NVT,
    TWENTY_ONE_STEP,
    Stage,
    twenty_one_step,
)


def test_the_twenty_one_step_is_twenty_one_stages_ending_at_the_target():
    """An equilibrator handed this runs exactly what was published: a
    stage lost or the last NPT at p_max is a glass at 50 kbar."""
    stages = TWENTY_ONE_STEP.stages

    assert len(stages) == 21
    assert stages[-1] == Stage(NPT, 300.0, 800.0, 1.0)
    assert TWENTY_ONE_STEP.duration == pytest.approx(1560.0)
    # Every third stage is the compression or decompression.
    assert [s.ensemble for s in stages[2::3]] == [NPT] * 7
    assert max(s.pressure for s in stages if s.pressure) == 5.0e4


def test_the_hot_stages_follow_t_max_and_the_pressures_p_max():
    """t_max and p_max are what a user changes, and the pattern must
    survive the change."""
    cooler = twenty_one_step(t_max=500.0, p_max=1.0e4)

    assert [s.temperature for s in cooler.stages[:2]] == [500.0, 300.0]
    assert cooler.stages[2].pressure == pytest.approx(0.02 * 1.0e4)
    assert cooler.stages[8].pressure == pytest.approx(1.0e4)


def test_a_stage_that_mixes_its_ensemble_and_pressure_is_refused():
    """An NVT stage given a pressure would be read by one equilibrator
    and ignored by another."""
    with pytest.raises(ValueError, match="NPT stage needs a pressure"):
        Stage(NVT, 300.0, 10.0, pressure=1.0)
    with pytest.raises(ValueError, match="NPT stage needs a pressure"):
        Stage(NPT, 300.0, 10.0)
    with pytest.raises(ValueError, match="no ensemble"):
        Stage("NVE", 300.0, 10.0)
