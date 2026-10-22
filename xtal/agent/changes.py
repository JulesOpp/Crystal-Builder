"""
xtal.agent.changes
==================
Which steps of a document's history an assistant made, in bursts.

Every command an agent verb pushes carries an :class:`Origin`; a
person's carries none.  A *burst* is one run of an assistant's edits
on one document -- what it did for one request -- and is what the
window's *Agent changes* strip lists and reverts.  Nothing is stored
beside the history: bursts are read off the stack itself, so they
cannot disagree with what Undo will actually do.

A burst is opened lazily by the session that pushes, never by a timer:
see :meth:`xtal.agent.Session._tag` for the four things that end one.

No Qt, no ``mcp``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

#: Seconds without an assistant's call after which its next edit is a
#: new request: a person reading the answer and asking for something
#: else takes longer than one call follows another.
BURST_GAP = 60.0

#: The longest label made from verbs, so the strip stays one line.
LABEL_LENGTH = 60

TRIMMED = "the history has let this go"
REVERTED = "it is already reverted"
REPLACED = "an edit since has replaced it"
NOT_REVERTED = "it is not reverted"
UNKNOWN = "no such change"


def clock() -> float:
    """Seconds, replaced by the tests so nobody sleeps."""
    return time.time()


@dataclass(frozen=True)
class Origin:
    """An assistant's step: its burst, its place in it (``1`` first),
    the verb that pushed it, the burst's name if a ``checkpoint``
    gave one, and when."""

    burst: int
    step: int
    verb: str
    label: str
    at: float


def origin_of(command) -> Origin | None:
    return getattr(command, "origin", None)


def next_burst(stack) -> int:
    """One more than any burst the history holds: numbered from the
    stack, not a session, because the window remakes a tab's session
    and two bursts must never share a number."""
    numbers = [o.burst for c in (*stack.done(), *stack.undone())
               if (o := origin_of(c)) is not None]
    return max(numbers, default=0) + 1


def label_for(verbs, given: str = "") -> str:
    """The checkpoint's name, else the verbs in order, each once."""
    if given:
        return given
    text = ", ".join(dict.fromkeys(verbs))
    if len(text) <= LABEL_LENGTH:
        return text
    return text[:LABEL_LENGTH - 3] + "..."


@dataclass(frozen=True)
class Burst:
    """One run of an assistant's edits, as the history holds it now.

    ``steps`` counts its commands still in the history (done or
    undone); ``applied`` is ``"all"``, ``"part"`` or ``"none"`` of
    them; ``person_after`` and ``bursts_after`` are the applied steps
    after it that a revert would take too; ``reason`` says why it
    cannot be reverted, or is ``""``.
    """

    number: int
    label: str
    started: float
    verbs: tuple[str, ...]
    steps: int
    applied: str
    person_after: int
    bursts_after: int
    reason: str

    @property
    def revertible(self) -> bool:
        return not self.reason


def _timeline(stack) -> tuple[tuple, int]:
    """Every step in the order it was first made, and how many of the
    first are applied: the done ones, then the undone from the
    earliest."""
    done = stack.done()
    return done + tuple(reversed(stack.undone())), len(done)


def bursts(stack) -> list[Burst]:
    """The history's bursts, newest first."""
    timeline, applied_count = _timeline(stack)
    members: dict[int, list[int]] = {}
    for index, command in enumerate(timeline):
        origin = origin_of(command)
        if origin is not None:
            members.setdefault(origin.burst, []).append(index)
    found = []
    for number, indices in members.items():
        origins = [origin_of(timeline[i]) for i in indices]
        applied = [i < applied_count for i in indices]
        last_applied = max((i for i in indices if i < applied_count),
                           default=None)
        after = (timeline[last_applied + 1:applied_count]
                 if last_applied is not None else ())
        person_after = sum(1 for c in after if origin_of(c) is None)
        bursts_after = len({origin_of(c).burst for c in after
                            if origin_of(c) is not None
                            and origin_of(c).burst != number})
        if min(o.step for o in origins) > 1:
            reason = TRIMMED
        elif not any(applied):
            reason = REVERTED
        else:
            reason = ""
        found.append(Burst(
            number=number,
            label=label_for([o.verb for o in origins],
                            next((o.label for o in origins if o.label),
                                 "")),
            started=min(o.at for o in origins),
            verbs=tuple(o.verb for o in origins),
            steps=len(indices),
            applied=("all" if all(applied) else
                     "none" if not any(applied) else "part"),
            person_after=person_after, bursts_after=bursts_after,
            reason=reason))
    return sorted(found, key=lambda b: b.number, reverse=True)


def _find(stack, number) -> Burst | None:
    return next((b for b in bursts(stack) if b.number == number), None)


def revert_plan(stack, number: int) -> int | str:
    """How many undos take the history back to just before burst
    ``number``, or why it cannot be reverted."""
    burst = _find(stack, number)
    if burst is None:
        return UNKNOWN
    if burst.reason:
        return burst.reason
    done = stack.done()
    first = next(i for i, c in enumerate(done)
                 if (o := origin_of(c)) is not None and o.burst == number)
    return len(done) - first


def restore_plan(stack, number: int) -> int | str:
    """How many redos bring a reverted burst back with everything
    undone with it -- every step Redo holds, since Redo re-applies in
    order -- or why it cannot be."""
    undone = stack.undone()
    if any((o := origin_of(c)) is not None and o.burst == number
           for c in undone):
        return len(undone)
    burst = _find(stack, number)
    if burst is None:
        return REPLACED
    return NOT_REVERTED
