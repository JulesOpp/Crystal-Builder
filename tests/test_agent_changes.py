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


def test_the_assistants_own_undo_does_not_end_its_burst(session, clock):
    """An assistant taking back its own misstep is still working on the
    same request; a new burst there would split one request in two on
    the strip and drop the name the checkpoint gave it."""
    session.checkpoint("Tidy rutile")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    session.undo()
    session.add_atom("O", frac=[0.3, 0.4, 0.5])
    assert _burst_numbers(session) == [1, 1]
    assert [origin_of(c).label for c in session.stack.done()] == [
        "Tidy rutile", "Tidy rutile"]


def test_the_assistants_undo_to_an_empty_history_keeps_its_burst(
        session, clock):
    """With nothing left applied there is no step to be "ours"; the
    empty history the assistant's own undo left must still count as
    its, or every retry after a first misstep is a new request."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.undo()
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert _burst_numbers(session) == [1]


def test_the_assistants_redo_does_not_end_its_burst(session, clock):
    """Redo puts back the assistant's own step; what it pushes next
    belongs with it."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    session.undo()
    session.redo()
    session.add_atom("O", frac=[0.3, 0.4, 0.5])
    assert _burst_numbers(session) == [1, 1, 1]


class _Boom(AddSites):
    """A command whose ``do`` fails, as a broken one would."""

    def do(self, host):
        raise RuntimeError("boom")


def test_a_push_that_raises_leaves_no_burst_on_the_next_row(session,
                                                            clock):
    """The failed command never reached the history; a burst on the
    next logged row would name a change that does not exist."""
    with pytest.raises(RuntimeError, match="boom"):
        session._push("add_atom", _Boom([new_site("O", [0.1] * 3)]),
                      "never", {})
    session.checkpoint("After")
    assert "burst" not in session.log[-1]
    assert session.stack.depth == 0
    # Neither a failure straight after the checkpoint nor one mid-burst
    # may spend the name, move the step count or end the burst.
    with pytest.raises(RuntimeError, match="boom"):
        session._push("add_atom", _Boom([new_site("O", [0.1] * 3)]),
                      "never", {})
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    with pytest.raises(RuntimeError, match="boom"):
        session._push("add_atom", _Boom([new_site("O", [0.2] * 3)]),
                      "never", {})
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert [(o.burst, o.step, o.label)
            for o in map(origin_of, session.stack.done())] == [
        (1, 1, "After"), (1, 2, "After")]


def test_a_step_the_assistant_undid_gives_its_number_back(session,
                                                          clock):
    """Revert reads a burst whose first step is not 1 as one the
    history let go; a step number the assistant's own undo threw away
    and never reused would make a whole burst unrevertible."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.undo()
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert [origin_of(c).step for c in session.stack.done()] == [1]
    assert changes.bursts(session.stack)[0].revertible


def test_the_assistants_redo_keeps_the_step_numbers_running(session,
                                                            clock):
    """Redo gives back the step it took; numbering the next one as if
    the redo had not happened would leave a gap or repeat a number."""
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    session.undo()
    session.redo()
    session.add_atom("O", frac=[0.3, 0.4, 0.5])
    assert [origin_of(c).step for c in session.stack.done()] == [1, 2, 3]


def _two_bursts_and_a_persons_edit(session, clock):
    session.checkpoint("First")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    session.checkpoint("Second")
    session.add_atom("O", frac=[0.3, 0.4, 0.5])
    _person_adds(session)


def test_bursts_are_listed_newest_first_with_what_came_after(session,
                                                              clock):
    """The strip's line and its 'also undoes N of yours' come from
    here; a wrong count reverts more than the person was told."""
    _two_bursts_and_a_persons_edit(session, clock)
    second, first = changes.bursts(session.stack)
    assert (second.number, second.label, second.steps) == (2, "Second", 1)
    assert (second.person_after, second.bursts_after) == (1, 0)
    assert (first.number, first.label, first.steps) == (1, "First", 2)
    assert (first.person_after, first.bursts_after) == (1, 1)
    assert first.verbs == ("add_atom", "add_atom")
    assert first.applied == "all" and first.revertible


def test_revert_undoes_back_to_just_before_the_burst(session, clock):
    """Linear history: reverting the first burst takes the second and
    the person's edit with it, and the plan says how many steps."""
    _two_bursts_and_a_persons_edit(session, clock)
    assert changes.revert_plan(session.stack, 2) == 2
    assert changes.revert_plan(session.stack, 1) == 4
    assert changes.revert_plan(session.stack, 9) == changes.UNKNOWN


def test_restore_brings_back_a_burst_and_what_redo_passes_not_later(
        session, clock):
    """Redo goes in order, so a burst comes back with whatever was
    undone before it in time -- and with nothing made after it; a plan
    that redid all of Redo would put back the person's edit and later
    bursts nobody asked for."""
    _two_bursts_and_a_persons_edit(session, clock)
    for _ in range(changes.revert_plan(session.stack, 1)):
        session.stack.undo(session)
    first = next(b for b in changes.bursts(session.stack)
                 if b.number == 1)
    assert first.applied == "none" and first.reason == changes.REVERTED
    assert changes.revert_plan(session.stack, 1) == changes.REVERTED
    assert changes.restore_plan(session.stack, 1) == 2
    assert changes.restore_plan(session.stack, 2) == 3


def test_reverting_newest_first_restores_the_older_burst_alone(session,
                                                               clock):
    """Two reverts, newest first, leave Redo as one revert of the older
    burst would; restoring the older must not bring the newer back."""
    _two_bursts_and_a_persons_edit(session, clock)
    for number in (2, 1):
        for _ in range(changes.revert_plan(session.stack, number)):
            session.stack.undo(session)
    assert changes.restore_plan(session.stack, 1) == 2


def test_restore_counts_a_persons_step_undone_from_under_the_burst(
        session, clock):
    """A person's step undone by hand after the revert sits ahead of
    the burst in Redo; a plan that left its redo out would stop one
    step short of the burst's last."""
    _person_adds(session)
    session.checkpoint("First")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    for _ in range(changes.revert_plan(session.stack, 1)):
        session.stack.undo(session)
    session.stack.undo(session)          # the person's step, by hand
    assert changes.restore_plan(session.stack, 1) == 3


def test_restore_is_refused_for_a_burst_that_was_never_reverted(
        session, clock):
    """Restore on a burst with nothing undone would redo nothing, or
    redo someone else's steps, and say it had restored it."""
    _two_bursts_and_a_persons_edit(session, clock)
    assert changes.restore_plan(session.stack, 2) == changes.NOT_REVERTED


def test_an_edit_after_a_revert_replaces_what_restore_would_bring_back(
        session, clock):
    """Redo is gone once something new is pushed; offering Restore then
    would redo nothing and say it had."""
    _two_bursts_and_a_persons_edit(session, clock)
    for _ in range(changes.revert_plan(session.stack, 2)):
        session.stack.undo(session)
    _person_adds(session, frac=(0.6, 0.6, 0.6))
    assert changes.restore_plan(session.stack, 2) == changes.UNKNOWN
    assert [b.number for b in changes.bursts(session.stack)] == [1]


def test_a_burst_partly_undone_by_hand_is_still_revertible(session,
                                                           clock):
    """Undo by hand that stops inside a burst leaves part of it
    applied; refusing then would leave the person no way to take the
    rest back as one."""
    _two_bursts_and_a_persons_edit(session, clock)
    session.stack.undo(session)          # the person's edit
    session.stack.undo(session)          # the second burst's step
    session.stack.undo(session)          # half the first burst
    first = next(b for b in changes.bursts(session.stack)
                 if b.number == 1)
    assert first.applied == "part"
    assert changes.revert_plan(session.stack, 1) == 1


def test_a_burst_whose_start_the_history_let_go_cannot_be_reverted(
        session, clock):
    """Undo can no longer reach its first step, so a revert would stop
    half way through it and call that reverted."""
    session.stack.limit = 3
    session.checkpoint("Long")
    for k in range(5):
        session.add_atom("O", frac=[0.1 + 0.1 * k, 0.2, 0.3])
    (only,) = changes.bursts(session.stack)
    assert only.reason == changes.TRIMMED and not only.revertible
    assert changes.revert_plan(session.stack, only.number) == \
        changes.TRIMMED
