"""
xtalapp.updates
===============
Help ▸ Check for Updates: is the running build the latest release?

Nothing contacts GitHub unless the person asks, the line
:mod:`xtalapp.feedback` draws too.  The fetch is the window's; this
module only judges a reply, so all of it is tested headless.

**A developer build is not offered a downgrade.**  setuptools_scm
numbers a checkout after ``v1.0.0`` as ``1.0.1.dev95+g...``: a
pre-release of 1.0.1, so newer than 1.0.0 and older than 1.0.1.
Reading only the numbers would call it 1.0.1 and say it is current
when 1.0.1 ships; reading only "dev" would offer it 1.0.0.  The
numbers are compared as integers, so 1.10 is after 1.9.

``packaging.version`` would do this but is not a dependency, and the
tags are plain ``vX.Y.Z``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

APP = "Crystal Builder"
REPOSITORY = "JulesOpp/Crystal-Builder"
RELEASES_API = (f"https://api.github.com/repos/{REPOSITORY}"
                "/releases/latest")
#: Where to send somebody when the reply named no page of its own.
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"

CURRENT = "current"
NEWER_AVAILABLE = "newer available"
AHEAD = "ahead"
UNKNOWN = "unknown"

_VERSION = re.compile(
    r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:\.?dev(\d+))?", re.IGNORECASE)


def release_tuple(text: str) -> tuple[int, int, int, int, int] | None:
    """A sortable key for a version: ``(x, y, z, final, dev)``.

    ``final`` is 0 for a ``.devN`` and 1 for the release itself, so
    every dev build of a number sorts before it.  A local part
    (``+g...``) is ignored.  ``None`` when there is no version here.
    """
    match = _VERSION.match(text.strip())
    if match is None:
        return None
    major, minor, patch, dev = match.groups()
    final = 0 if dev is not None else 1
    return (int(major), int(minor), int(patch or 0), final,
            int(dev or 0))


@dataclass(frozen=True)
class Verdict:
    state: str
    current: str
    latest: str = ""
    url: str = RELEASES_PAGE
    #: Why the state is UNKNOWN.
    reason: str = ""

    def message(self) -> str:
        if self.state == NEWER_AVAILABLE:
            return (f"{APP} {self.latest} is available; this is "
                    f"{self.current}.")
        if self.state == CURRENT:
            return f"{APP} {self.current} is the latest release."
        if self.state == AHEAD:
            return (f"This build, {self.current}, is newer than the "
                    f"latest release, {self.latest}.")
        return f"Could not tell which release is the latest: " \
            f"{self.reason}."


def judge(current: str, reply: bytes | str | dict) -> Verdict:
    """What the running ``current`` is, given GitHub's latest release.

    ``reply`` is the body of ``RELEASES_API``, raw or parsed.  Never
    raises: a reply that is not a release -- an empty body, GitHub's
    rate-limit complaint -- is UNKNOWN with the reason.
    """
    def unknown(reason: str) -> Verdict:
        return Verdict(UNKNOWN, current, reason=reason)

    if not isinstance(reply, dict):
        try:
            reply = json.loads(reply)
        except (ValueError, TypeError):
            return unknown("GitHub's reply was not readable")
        if not isinstance(reply, dict):
            return unknown("GitHub's reply was not a release")
    if "tag_name" not in reply:
        complaint = reply.get("message")
        return unknown(f"GitHub said {complaint!r}"
                       if isinstance(complaint, str)
                       else "GitHub's reply named no release")
    # releases/latest never returns these; a reply that does is not
    # one to send anybody to.
    if reply.get("draft") or reply.get("prerelease"):
        return unknown("the latest release is not a final one")
    tag = str(reply["tag_name"])
    latest = release_tuple(tag)
    if latest is None:
        return unknown(f"the latest release's tag {tag!r} is not a "
                       "version")
    mine = release_tuple(current)
    if mine is None:
        return unknown(f"this build's version {current!r} is not "
                       "readable")
    url = reply.get("html_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        url = RELEASES_PAGE
    name = tag[1:] if tag[:1] in "vV" else tag
    if mine < latest:
        state = NEWER_AVAILABLE
    elif mine == latest:
        state = CURRENT
    else:
        state = AHEAD
    return Verdict(state, current, latest=name, url=url)
