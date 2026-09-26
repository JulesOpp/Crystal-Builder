"""What a structure looks like to RietX, and what comes back.

The bridge is the one module that imports RietX, so these are the
tests that fail when RietX moves something -- which is why its
version is pinned in ``pyproject.toml`` and not left open.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rietx")

from xtal.core.site import Site  # noqa: E402
from xtal.powder import bridge  # noqa: E402
from xtal.powder.data import PowderData, PowderError, Radiation  # noqa: E402


def _with_marker(structure):
    """The structure with a dummy atom between its two real sites."""
    out = structure.copy()
    sites = list(out.sites)
    out.remove_sites(list(range(len(sites))))
    out.add_sites([sites[0], Site("X", np.array([0.1, 0.2, 0.3])),
                   *sites[1:]])
    return out


@pytest.mark.parametrize("name", ["rutile", "quartz"])
def test_a_structure_crosses_to_rietx_and_back_site_for_site(
        name, request):
    """Rietveld writes a refined position back by index.  If the
    atoms reordered on the way across, every position would land on
    the wrong site and the structure would still look refined."""
    structure = _with_marker(request.getfixturevalue(name))
    phase, indices = bridge.phase_of(structure)
    assert indices == [0, 2]            # the marker is not a scatterer
    for atom, index in zip(phase.atoms, indices, strict=True):
        site = structure.sites[index]
        assert atom.species == site.element
        assert [atom.x.value, atom.y.value, atom.z.value] == \
            pytest.approx(list(site.frac))

    phase.atoms[1].x.value += 0.01
    phase.cell.a.value += 0.1
    back = bridge.apply_phase(structure, phase, indices)
    assert len(back.sites) == len(structure.sites)
    assert back.sites[2].frac[0] == pytest.approx(
        structure.sites[2].frac[0] + 0.01)
    assert list(back.sites[1].frac) == pytest.approx([0.1, 0.2, 0.3])
    assert back.sites[0].frac == pytest.approx(structure.sites[0].frac)
    assert back.lattice.parameters[0] == pytest.approx(
        structure.lattice.parameters[0] + 0.1)


def test_a_phase_of_another_size_is_refused_rather_than_written_partway(
        rutile):
    phase, indices = bridge.phase_of(rutile)
    with pytest.raises(PowderError, match="atoms"):
        bridge.apply_phase(rutile, phase, indices[:1])


def test_the_space_group_goes_across_with_its_setting(quartz, halite):
    assert bridge.space_group_symbol(quartz) == "P 32 2 1"
    assert bridge.space_group_symbol(halite) == "F m -3 m"


def test_a_laboratory_tube_is_a_doublet_and_a_synchrotron_one_line():
    cu = bridge.instrument(Radiation("cu"))
    assert [line.wavelength.value for line in cu.source.lines] == \
        pytest.approx([1.5405929, 1.5444274])
    assert len(bridge.instrument(Radiation("cu-ka1")).source.lines) == 1
    sync = bridge.instrument(Radiation("synchrotron", 0.4139))
    assert sync.source.lines[0].wavelength.value == pytest.approx(0.4139)


def test_rutiles_strongest_line_is_where_bragg_puts_110(rutile):
    """d(110) = a / sqrt(2) = 3.248 A, so 27.44 degrees at Cu Ka1."""
    tt = np.arange(20.0, 40.0, 0.01)
    y = bridge.predict(rutile, Radiation("cu-ka1"), tt)
    assert tt[np.argmax(y)] == pytest.approx(27.44, abs=0.03)


def _rutile_pattern(rutile):
    tt = np.arange(20.0, 60.0, 0.02)
    y = bridge.predict(rutile, Radiation("cu"), tt)
    return PowderData(tt, y / y.max() * 1000 + 50)


def test_no_run_writes_a_rietx_folder_in_the_working_directory(
        rutile, tmp_path, monkeypatch):
    """RietX records a fit into ./.rietx/runs unless told otherwise --
    for this application, the user's home or the inside of the app
    bundle.  Told a run folder, it records there and nowhere else."""
    import rietx as rx

    monkeypatch.delenv("RIETX_TELEMETRY", raising=False)
    monkeypatch.chdir(tmp_path)
    data = _rutile_pattern(rutile)
    for folder in (None, tmp_path / "run"):
        structure, _indices = bridge.to_rietx(rutile)
        refinement = rx.Refinement(
            structure, bridge.instrument(Radiation("cu")), history=False)
        bridge.fit(refinement, data, folder=folder,
                   plan="profile_only")
    assert not (tmp_path / ".rietx").exists()
    assert (tmp_path / "run" / "rietx").is_dir()
