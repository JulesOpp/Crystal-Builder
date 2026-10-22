"""Which steps of a history an assistant made, and the bursts they
form.

The window's *Agent changes* strip, its Revert and the assistant's
being told are all read off these, so an origin missed on one verb, or
a burst that runs on across the person's own edit, shows the person a
change that is not the assistant's -- and reverts their work as if it
were.  Headless: a :class:`~xtal.agent.Session` over a real structure.
"""

import json

import pytest

from xtal.agent import Session, changes
from xtal.agent.changes import origin_of
from xtal.commands.atoms import AddSites, new_site


class _Clock:
    """``changes.clock`` the test moves by hand."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = _Clock()
    monkeypatch.setattr(changes, "clock", fake)
    return fake


@pytest.fixture
def session(rutile, tmp_path):
    from xtal.io import write_cif

    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    return Session.open(cif, workspace=tmp_path / "ws")


def _person_adds(session, frac=(0.31, 0.12, 0.47)):
    """A person's edit: a command pushed with no agent verb -- the
    command the window's Add atom pushes (``Document.add_atom``)."""
    session.stack.push(
        AddSites([new_site("O", list(frac))], perceive=False), session)


def _burst_numbers(session):
    return [origin_of(c).burst if origin_of(c) else None
            for c in session.stack.done()]


def test_every_step_an_agent_verb_pushes_says_it_was_the_agents(
        session, clock):
    """An untagged agent step is one the strip never lists and Revert
    never takes back."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    origins = [origin_of(c) for c in session.stack.done()]
    assert [o.verb for o in origins] == ["add_atom", "add_atom"]
    assert [o.burst for o in origins] == [1, 1]
    assert [o.step for o in origins] == [1, 2]


def test_a_persons_step_has_no_origin_and_ends_the_burst(session, clock):
    """The person's edit between two of the assistant's must split them,
    or a revert of the assistant's burst undoes the person's edit while
    calling it the assistant's."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    _person_adds(session)
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert _burst_numbers(session) == [1, None, 2]


def test_a_pause_longer_than_the_gap_starts_a_new_burst(session, clock):
    """Bursts are requests; a pause past the gap is the person reading
    an answer and asking for something else, and folding the two into
    one would revert both as one."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    clock.now += changes.BURST_GAP - 1
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    clock.now += changes.BURST_GAP + 1
    session.add_atom("O", frac=[0.3, 0.4, 0.5])
    assert _burst_numbers(session) == [1, 1, 2]


def test_a_persons_undo_ends_the_burst(session, clock):
    """Undo then a new agent edit: the step under the new one is no
    longer the assistant's last, so the burst it was in is over."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    session.stack.undo(session)
    session.add_atom("O", frac=[0.3, 0.4, 0.5])
    assert _burst_numbers(session) == [1, 2]


def test_checkpoint_names_the_next_burst_and_ends_this_one(session,
                                                            clock):
    """A checkpoint that pushed a step, or named the burst before it,
    would list the person's request against the wrong changes."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    answer = session.checkpoint("Prepared rutile")
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert answer.ok and session.stack.depth == 2
    second = origin_of(session.stack.done()[-1])
    assert (second.burst, second.label) == (2, "Prepared rutile")
    assert origin_of(session.stack.done()[0]).label == ""


def test_closing_the_burst_by_hand_starts_a_new_one(session, clock):
    """What a host's open and switch call: the next edit is a new
    request."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.close_burst()
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert _burst_numbers(session) == [1, 2]


def test_an_agent_step_never_merges_with_a_persons(session, clock):
    """A step that merged into the person's would be one undo step with
    two authors, and the strip could neither list nor revert it
    honestly."""
    _person_adds(session)
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    _person_adds(session, frac=(0.4, 0.4, 0.4))
    assert len(session.stack.done()) == 3


def test_burst_numbers_continue_from_the_history_not_from_the_session(
        session, clock):
    """A window drops and remakes a tab's session; numbering from the
    session would give two bursts one number."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    fresh = Session(session.structure, session.path, session.entry)
    fresh.stack = session.stack
    fresh.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert _burst_numbers(session) == [1, 2]


def test_a_label_from_verbs_is_short_and_says_each_once():
    """The strip is one line a burst; a label that repeated verbs or
    ran on would push the Revert off it."""
    label = changes.label_for(["prepare", "recalculate_bonds", "prepare",
                               "optimize"])
    assert label == "prepare, recalculate_bonds, optimize"
    long = changes.label_for(["set_bond_type_" + str(k)
                              for k in range(20)])
    assert len(long) <= changes.LABEL_LENGTH and long.endswith("...")
    assert changes.label_for(["optimize"], "Relaxed it") == "Relaxed it"


def test_the_log_names_the_burst_a_step_was_in(session, clock):
    """``agent-session.jsonl`` is how a person opening the entry later
    learns what the assistant did; the burst groups it as the strip
    did."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.checkpoint("Next")
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    rows = [json.loads(line) for line in
            session.log_path.read_text(encoding="utf-8").splitlines()]
    pushed = [r for r in rows if r["verb"] == "add_atom"]
    assert [r["burst"] for r in pushed] == [1, 2]
    assert "burst" not in next(r for r in rows
                               if r["verb"] == "checkpoint")
