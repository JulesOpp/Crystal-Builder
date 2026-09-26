"""Inspection and the CLI's JSON: what an agent reads before it believes
a structure.

The codes are the contract.  An agent acts on ``COINCIDENT_ATOMS`` by
looking up its remedy; a finding that comes back under the wrong code,
or not at all, sends it down the wrong path with nothing to say so.
"""

import json

import numpy as np
import pytest

from xtal import cli
from xtal.agent.inspect import MAX_PER_CODE, inspect
from xtal.agent.session import Session
from xtal.io import FORMATS, write_cif


def _codes(found) -> list[str]:
    return [d.code for d in found.diagnostics]


def test_inspecting_halite_reports_octahedral_sodium(halite):
    found = inspect(halite)
    sodium = next(s for s in found.sites if s["element"] == "Na")
    assert sodium["coordination"] == 6
    assert {e for e, _d in sodium["neighbours"]} == {"Cl"}
    assert found.detected_space_group == "Fm-3m"
    assert found.n_atoms == 8


def test_a_site_written_just_off_its_special_position_is_not_duplicated(
        rutile):
    """0.01 A off the 2a position is still on it (SPECIAL_POSITION_TOL),
    so the orbit is two titanium, not four -- and nothing says the cell
    repeats itself, because it does not."""
    shifted = rutile.copy()
    shifted.sites[0].frac = np.array([0.002, 0.0, 0.0])
    found = inspect(shifted)
    titanium = next(s for s in found.sites if s["element"] == "Ti")
    assert titanium["multiplicity"] == 2
    assert "COINCIDENT_ATOMS" not in _codes(found)


def test_a_file_that_repeats_its_own_atoms_is_one_coincidence_finding():
    """Ni2Cl2BTDD's export writes symmetry copies as sites.  The remedy
    is Merge Duplicates, and the reader's warning is the same finding --
    so it is reported once, as the code that names the remedy."""
    found = inspect(FORMATS.read("resources/samples/Ni2Cl2BTDD.cif"))
    assert _codes(found).count("COINCIDENT_ATOMS") == 1
    assert found.worst == "error"
    assert not any(d.code == "READ_WARNING" and "on top of" in d.message
                   for d in found.diagnostics)


def test_an_atom_dropped_on_another_is_a_close_contact(quartz):
    session = Session(quartz)
    session.recalculate_bonds()
    oxygen = session.cell.cart[session.cell.indices_of_site(1)[0]]
    session.add_atom("O", cart=oxygen + [0.9, 0.0, 0.0])
    assert "CLOSE_CONTACT" in _codes(session.inspect())


def test_a_hydrogen_with_two_bonds_is_overcoordinated(dry_ice):
    session = Session(dry_ice)
    carbon = session.cell.cart[0]
    oxygen = session.cell.cart[session.cell.indices_of_site(1)[0]]
    middle = (carbon + oxygen) / 2
    session.add_atom("H", cart=middle + [0.0, 0.3, 0.0])
    session.recalculate_bonds()
    assert "OVERCOORDINATED" in _codes(session.inspect())


def test_a_new_atom_is_reported_unbonded_until_bonds_are_recalculated(
        rutile):
    session = Session(rutile)
    session.add_atom("Ar", frac=[0.5, 0.0, 0.5])
    assert "UNBONDED_ATOM" in _codes(session.inspect())


def test_a_marker_is_reported_as_one_and_never_as_unbonded(rutile):
    session = Session(rutile)
    session.add_atom("X", frac=[0.5, 0.5, 0.5])
    found = session.inspect()
    assert "MARKERS_PRESENT" in _codes(found)
    assert not any(d.code == "UNBONDED_ATOM" and "X" in d.message
                   for d in found.diagnostics)


def test_findings_of_one_kind_are_capped_with_a_count(rutile):
    session = Session(rutile)
    session.supercell(3, 3, 3)
    for k in range(MAX_PER_CODE + 4):
        session.add_atom("Ar", frac=[0.05 + 0.07 * k, 0.5, 0.5])
    unbonded = [d for d in session.inspect().diagnostics
                if d.code == "UNBONDED_ATOM"]
    assert len(unbonded) == MAX_PER_CODE + 1
    assert "more like the above" in unbonded[-1].message


def test_inspection_never_perceives_bonds_the_structure_lacks(quartz):
    """Reading must not change: an atom added unbonded stays unbonded
    after inspection, which would otherwise be a recalculation nobody
    asked for."""
    session = Session(quartz)
    session.add_atom("Si", frac=[0.1, 0.1, 0.1])
    session.inspect()
    assert "UNBONDED_ATOM" in _codes(session.inspect())


# ----------------------------------------------------------------------
#  --json
# ----------------------------------------------------------------------

@pytest.fixture
def quartz_file(tmp_path, quartz):
    path = tmp_path / "quartz.cif"
    write_cif(quartz, path)
    return str(path)


@pytest.mark.parametrize("command", [
    ["info"], ["inspect"], ["symmetry", "--wyckoff"], ["bonds"],
    ["types"], ["energy"], ["optimize", "--max-steps", "2"],
    ["run", "pxrd.simulate"],
])
def test_json_output_round_trips_for_every_cli_command_that_offers_it(
        command, quartz_file, capsys):
    """stdout is one JSON document and nothing else, or a pipeline
    parsing it fails on the first line of prose."""
    status = cli.main([*command, "--json", quartz_file]
                      if command[0] != "run"
                      else [*command, quartz_file, "--json"])
    assert status in (0, 2)             # 2: an optimisation unconverged
    document = json.loads(capsys.readouterr().out)
    assert isinstance(document, dict) and document


def test_json_inspection_names_every_site_and_diagnostic(quartz_file,
                                                         capsys):
    cli.main(["inspect", "--json", quartz_file])
    document = json.loads(capsys.readouterr().out)
    assert [s["element"] for s in document["sites"]] == ["Si", "O"]
    assert all({"code", "level", "message", "suggestion"} <= set(d)
               for d in document["diagnostics"])


def test_capabilities_json_lists_every_engine(capsys):
    from xtal.ff import ENGINES

    cli.main(["capabilities", "--json"])
    document = json.loads(capsys.readouterr().out)
    assert {e["name"] for e in document["engines"]} == \
        {e.name for e in ENGINES}
