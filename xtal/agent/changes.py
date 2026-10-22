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
