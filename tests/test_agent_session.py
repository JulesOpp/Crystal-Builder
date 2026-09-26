"""The agent session: verbs over the command stack, and what they say.

An agent edits through the same commands a person's clicks push, so
every product rule the commands carry -- bonds only on request,
markers held back, the chemistry step never by default -- has to hold
here too.  These tests are the ones that notice when a verb reaches
around a command instead of pushing one.
"""

import json

import numpy as np
import pytest

from xtal.agent import diagnostics
from xtal.agent.capabilities import VERBS, capabilities, help_for
from xtal.agent.session import Session
from xtal.core import bonding
from xtal.io import write_cif
from xtal.io.project import read_project


def test_adding_an_atom_does_not_perceive_bonds(quartz):
    """If this breaks, an agent's atom arrives bonded to whatever it
    happens to land near -- the rule Recalculate Bonds exists for."""
    session = Session(quartz)
    before = len(bonding.graph(session.structure).bonds)
    # Near an oxygen, where perception would certainly bond a silicon.
    oxygen = session.cell.frac[session.cell.indices_of_site(1)[0]]
    answer = session.add_atom("Si", frac=oxygen + [0.25, 0, 0])
    assert answer.ok
    graph = bonding.graph(session.structure)
    new_atoms = session.cell.indices_of_site(2)
    assert all(graph.coordination()[a] == 0 for a in new_atoms)
    assert len(graph.bonds) == before
    assert any(d.code == "BONDS_NOT_RECALCULATED"
               for d in answer.diagnostics)


def test_an_atom_added_bonded_to_an_anchor_has_that_bond_only(quartz):
    session = Session(quartz)
    silicon = int(session.cell.indices_of_site(0)[0])
    frac = session.cell.frac[silicon] + [0.0, 0.0, 0.3]
    answer = session.add_atom("H", frac=frac, bonded_to=silicon)
    assert answer.ok
    graph = bonding.graph(session.structure)
    hydrogen = [a for a in session.cell.indices_of_site(2)
                if silicon in graph.neighbors(a)]
    assert hydrogen, "the hydrogen should be bonded to its anchor"
    assert all(graph.coordination()[a] == 1 for a in hydrogen)


def test_every_verb_is_one_undo_step(rutile):
    """An agent that undoes once must get back exactly the structure
    before its last verb -- not part of it, and not two verbs."""
    session = Session(rutile)
    steps = [
        lambda: session.add_atom("O", frac=[0.5, 0.5, 0.5]),
        lambda: session.set_element([0], "Zr"),
        lambda: session.move_sites([1], frac_delta=[0.01, 0.01, 0]),
        lambda: session.set_cell(4.7, 4.7, 3.0, 90, 90, 90),
        lambda: session.supercell(1, 1, 2),
        lambda: session.recalculate_bonds(),
        lambda: session.reduce_to_p1(),
        lambda: session.delete_sites([0]),
    ]
    for step in steps:
        before = session.structure.copy()
        depth = session.stack.depth
        answer = step()
        assert answer.ok, answer
        assert session.stack.depth == depth + 1, answer.verb
        session.undo()
        assert session.stack.depth == depth
        assert _same(session.structure, before), answer.verb
        session.redo()


def _same(a, b) -> bool:
    return (a.n_sites == b.n_sites
            and [s.element for s in a.sites] == [s.element for s in b.sites]
            and np.allclose([s.frac for s in a.sites],
                            [s.frac for s in b.sites])
            and np.allclose(a.lattice.matrix, b.lattice.matrix)
            and a.space_group.number == b.space_group.number)


def test_a_refused_operation_pushes_nothing(rutile):
    """A refusal that left a no-op on the stack would make undo appear
    to do nothing -- the thing Document.operate refuses to do too."""
    session = Session(rutile)
    answer = session.prepare(steps=["deuterium"])
    assert not answer.ok
    assert session.stack.depth == 0
    assert answer.diagnostics[0].code in ("NOTHING_TO_DO",
                                          "OPERATION_REFUSED")


def test_a_marker_is_held_back_from_an_optimisation_and_said_so(
        dry_ice):
    """If the marker reached the engine UFF would refuse the crystal;
    if it moved, the force field would have changed the user's atoms."""
    session = Session(dry_ice)
    session.add_atom("X", frac=[0.5, 0.5, 0.5])
    marker = session.structure.sites[-1].frac.copy()
    answer = session.optimize(max_steps=3)
    assert answer.ok, answer
    assert np.allclose(session.structure.sites[-1].frac, marker)
    assert any(d.code == "MARKERS_PRESENT"
               for d in session.inspect().diagnostics)


def test_an_optimisation_changes_neither_atoms_nor_bonds(dry_ice):
    session = Session(dry_ice)
    session.recalculate_bonds()
    bonds = len(bonding.graph(session.structure).bonds)
    atoms = session.n_atoms
    session.optimize(max_steps=5)
    assert session.n_atoms == atoms
    assert len(bonding.graph(session.structure).bonds) == bonds


def test_an_unconverged_optimisation_says_so(dry_ice):
    answer = Session(dry_ice).optimize(max_steps=1, tolerance=1e-9)
    assert not answer.data["converged"]
    assert any(d.code == "NOT_CONVERGED" for d in answer.diagnostics)


def test_prepare_never_caps_unless_asked_and_warns_either_way(
        tmp_path):
    """The trimer step changes the chemistry: left out of the default,
    and a warning whichever way it went (prepare.CHEMISTRY)."""
    from xtal.core import prepare as core

    session = Session.open("resources/samples/MIL53.cif")
    answer = session.prepare()
    assert "cap" not in answer.data.get("steps", core.DEFAULT_STEPS)
    assert "cap" not in core.DEFAULT_STEPS
    steps = [d.where for d in answer.diagnostics
             if d.code == "PREPARE_STEP"]
    assert "cap" not in steps
    assert all(d.level != "error" for d in answer.diagnostics)


def test_a_chemistry_caution_is_a_warning_not_a_step(monkeypatch,
                                                     rutile):
    """A caution from prepare.run must reach the agent as a warning it
    has to pass on, not an info line among the steps."""
    from xtal.commands import prepare as prepare_commands
    from xtal.core import prepare as core

    changed = rutile.copy()
    changed.sites[0].element = "Zr"

    def run(structure, steps):
        return core.Outcome(changed, ["did it"],
                            ["Complete M3O trimers changes the "
                             "chemistry of the material -- ..."])

    monkeypatch.setattr(prepare_commands.core, "run", run)
    answer = Session(rutile).prepare(steps=["cap"])
    assert answer.ok
    warned = [d for d in answer.diagnostics
              if d.code == "CHEMISTRY_CHANGED"]
    assert warned and warned[0].level == "warning"


def test_a_refused_scan_is_a_diagnostic_not_an_exception(halite):
    """Every Na-Cl distance in Fm-3m is fixed by the group; the scan
    refuses before its first point, and the agent reads a code."""
    session = Session(halite)
    session.recalculate_bonds()
    answer = session.run("scan.run", axis1="distance 0, 1",
                         axis1_start=2.7, axis1_stop=2.9,
                         axis1_steps=2)
    assert not answer.ok
    assert answer.diagnostics[0].code == "MODULE_FAILED"
    assert "space group ties it" in answer.message
    assert session.stack.depth == 1       # only the recalculation


def test_an_unknown_engine_is_refused_by_code(rutile):
    answer = Session(rutile).energy(engine="no-such-engine")
    assert not answer.ok
    assert answer.diagnostics[0].code == "ENGINE_UNAVAILABLE"


def test_a_saved_session_opens_as_the_same_structure_in_the_project_reader(
        tmp_path, quartz):
    cif = tmp_path / "quartz.cif"
    write_cif(quartz, cif)
    session = Session.open(cif, workspace=tmp_path / "ws")
    session.add_atom("H", frac=[0.1, 0.2, 0.3])
    saved = session.save()
    assert saved.suffix == ".xtalproj"
    assert saved.parent == session.entry.path
    structure, _view, _session = read_project(saved)
    assert structure.n_sites == 3
    assert not session.modified


def test_opening_copies_the_file_into_the_workspace_and_follows_it(
        tmp_path, rutile):
    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    session = Session.open(cif, workspace=tmp_path / "ws")
    assert session.path.parent == session.entry.path
    assert session.path != cif
    assert session.structure.meta["source"] == str(cif)


def test_the_log_records_every_verb_as_one_json_line(tmp_path, rutile):
    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    session = Session.open(cif, workspace=tmp_path / "ws")
    session.recalculate_bonds()
    session.set_element([0], "Sn")
    session.undo()
    rows = [json.loads(line) for line in
            session.log_path.read_text().splitlines()]
    assert [r["verb"] for r in rows] == ["open", "recalculate_bonds",
                                         "set_element", "undo"]


def test_a_project_keeps_the_view_it_was_opened_with(tmp_path, rutile):
    """An agent that opens and saves somebody's project must not reset
    the way they were looking at it."""
    from xtal.io.project import write_project
    path = tmp_path / "ws" / "r" / "r.xtalproj"
    path.parent.mkdir(parents=True)
    write_project(rutile, path, view={"style": "spacefill"},
                  session={"selection": [0]})
    session = Session.open(path)
    session.save()
    _structure, view, saved = read_project(path)
    assert view == {"style": "spacefill"}
    assert saved["selection"] == [0]


def test_every_diagnostic_code_has_a_suggestion():
    for code, known in diagnostics.CODES.items():
        assert known.level in ("info", "warning", "error"), code
        assert known.suggestion.strip(), code


def test_an_unknown_diagnostic_code_cannot_be_raised():
    with pytest.raises(KeyError):
        diagnostics.Diagnostic("NOT_A_CODE", "anything")


def test_capabilities_names_the_extra_a_missing_engine_needs(
        monkeypatch):
    from xtal.ff import ENGINES
    from xtal.params import Availability

    engine = ENGINES.get("mace")
    monkeypatch.setattr(type(engine), "availability",
                        lambda self, **_: Availability(
                            False, "pip install crystal-builder[mace]"),
                        raising=False)
    found = {e["name"]: e for e in capabilities()["engines"]}
    assert not found["mace"]["available"]
    assert "mace" in found["mace"]["reason"]


def test_every_verb_capabilities_names_is_a_method_with_help():
    for verb in VERBS:
        assert hasattr(Session, verb), verb
        assert help_for(verb).startswith(f"Session.{verb}(")


def test_the_log_summary_counts_steps_and_warnings_not_opens_and_saves(
        tmp_path, dry_ice):
    from xtal.agent.session import summarise_log

    cif = tmp_path / "dry_ice.cif"
    write_cif(dry_ice, cif)
    session = Session.open(cif, workspace=tmp_path / "ws")
    session.recalculate_bonds()
    session.optimize(max_steps=1, tolerance=1e-9)    # NOT_CONVERGED
    session.save()
    steps, warnings = summarise_log(session.log_path)
    assert steps == 2
    assert warnings >= 1
    assert summarise_log(tmp_path / "nothing.jsonl") is None


def test_reopening_the_cif_after_a_save_points_at_the_project(
        tmp_path, rutile):
    """An agent that runs one script per step and reopens the CIF each
    time redoes everything before it -- seen end to end: six opens and
    six prepares for one prepared structure."""
    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    first = Session.open(cif, workspace=tmp_path / "ws")
    first.set_element([0], "Sn")
    project = first.save()

    again = Session.open(first.entry.path / "rutile.cif")
    codes = [d.code for d in again.opened.diagnostics]
    assert codes == ["PROJECT_EXISTS"]
    assert again.opened.diagnostics[0].where == str(project)

    resumed = Session.open(project)
    assert resumed.opened.diagnostics == []
    assert resumed.structure.sites[0].element == "Sn"
