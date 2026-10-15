"""
xtal.agent.context
==================
What an MCP client is told, as against what it can call.

Claude Code reads the skill off disk; a chat client cannot, so before
this an assistant in Claude Desktop had the tool list and nothing of
the protocol: prepare first, read every diagnostic, never report an
unconverged energy as a minimum.  This is the one reader of that text
for both servers -- :func:`xtal.agent.tools.build_server` and the
``xtal mcp`` proxy -- so the window, the headless server and the proxy
say the same thing.

- :func:`instructions` is ``skill/mcp.md``, which every client puts in
  front of the model; it is held to :data:`INSTRUCTIONS_LIMIT`.
- :func:`guide` is a reference page of the skill, the same pages
  Claude Code reads, fetched by the model when it needs one, or with
  no topic the instructions again.  Which pages there are, and when
  to read each, is ``mcp.md``'s own list, so the instructions and the
  tool cannot disagree.
- :func:`prompts` are ``skill/prompts/*.md``: a workflow a person
  picks, its first line the description and the rest a
  :class:`string.Template`.

Imports no ``mcp``: the SDK's types are made where it is imported.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass

from xtal.agent import skill

#: The most ``mcp.md`` may be: every client pays it in every
#: conversation, before the person has said anything.
INSTRUCTIONS_LIMIT = 6 * 1024

GUIDE_URI = "crystal-builder://guide/{}"
DOCUMENT_URI = "crystal-builder://document/current"
DOCUMENT_DESCRIPTION = ("inspect of the current document: the one "
                        "every verb acts on")

#: The heading of ``mcp.md``'s guide list, and one line of it:
#: "- `topic`: when to read it".
_GUIDES = "## Guides"
_TOPIC = re.compile(r"^- `([\w-]+)`: (.+)$", re.MULTILINE)


def instructions() -> str:
    """What the server tells every client when it connects."""
    return (skill.source() / "mcp.md").read_text(encoding="utf-8")


def topics() -> dict[str, str]:
    """Each guide and when to read it, as ``mcp.md``'s last section
    lists them; a bullet elsewhere in it is not a guide."""
    listed = instructions().partition(_GUIDES)[2]
    return dict(_TOPIC.findall(listed))


def guide(topic: str | None = None) -> str:
    """A guide's text; with no topic, the instructions, which end with
    the guides and when to read each -- for a client that never shows
    the model the server's instructions."""
    if topic is None:
        return instructions()
    known = topics()
    if topic not in known:
        raise LookupError(f"no guide called {topic!r}; the guides are "
                          f"{', '.join(known)}")
    page = skill.source() / "references" / f"{topic}.md"
    return page.read_text(encoding="utf-8")


@dataclass(frozen=True)
class PromptText:
    """A workflow a person picks: its name, what it is for, the
    arguments it asks for, and the text they are filled into."""

    name: str
    description: str
    arguments: tuple[str, ...]
    template: str

    def render(self, **values) -> str:
        """The text with every argument filled; ``KeyError`` names
        one that is missing."""
        return string.Template(self.template).substitute(values)


def prompts() -> list[PromptText]:
    """Every ``skill/prompts/*.md``, by name."""
    found = []
    for path in sorted((skill.source() / "prompts").glob("*.md")):
        head, _, body = path.read_text(encoding="utf-8").partition("\n")
        body = body.strip()
        found.append(PromptText(
            path.stem, head.lstrip("#").strip(),
            tuple(string.Template(body).get_identifiers()), body))
    return found
