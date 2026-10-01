"""
xtal.agent.serve
================
``xtal mcp``: the agent's tools over stdio, for a client that starts
the command itself (Claude Code, Claude Desktop, Cursor ...).

When a window is serving the tools (Preferences > AI assistant), the
command is a proxy to it: the window's discovery file says where, and
its tabs are the documents (:mod:`xtal.agent.proxy`).  Otherwise the
sessions live in this process, one per file, as a script's would.
``--window`` insists on the window and fails when none answers, rather
than quietly handing the assistant a structure nobody can see;
``--headless`` never looks for one.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from xtal.agent.session import Session
from xtal.agent.tools import NO_SESSION, Host


class HeadlessHost(Host):
    """Sessions in a dict, found by the path they were opened from or
    the one they have now: opening a file already held hands back its
    session, edits and all, however the path was spelled."""

    def __init__(self):
        self._sessions: dict[Path, Session] = {}
        self._current: Path | None = None

    def current(self) -> Session:
        if self._current is None:
            raise LookupError(NO_SESSION)
        return self._sessions[self._current]

    def open(self, path, workspace=None) -> Session:
        held = self._held(path)
        if held is None:
            session = Session.open(path, workspace)
            held = Path(path).resolve()
            self._sessions[held] = session
        self._current = held
        return self._sessions[held]

    def sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def switch(self, path) -> Session:
        held = self._held(path)
        if held is None:
            raise LookupError(f"{path} is not open")
        self._current = held
        return self._sessions[held]

    def _held(self, path) -> Path | None:
        """The key of the session over ``path``: the path it was
        opened from, or the path it has now -- a workspace's copy, or
        the project a save wrote -- which is the one ``documents``
        lists, and so the one an assistant opens again."""
        wanted = Path(path).resolve()
        for key, session in self._sessions.items():
            if wanted == key or (session.path is not None
                                 and session.path.resolve() == wanted):
                return key
        return None


def mcp_arguments(parser: argparse.ArgumentParser) -> None:
    """``xtal mcp``'s flags, for this parser and the CLI's."""
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--headless", action="store_true",
                       help="serve sessions in this process, even "
                            "when a window is serving")
    where.add_argument("--window", action="store_true",
                       help="drive the running Crystal Builder window, "
                            "or fail (the default is the window when "
                            "one answers, else headless)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="xtal mcp",
        description="The agent verbs as MCP tools, over stdio.")
    mcp_arguments(parser)
    args = parser.parse_args(argv)
    if importlib.util.find_spec("mcp") is None:
        from xtal.install import command
        print(f"xtal mcp needs the mcp extra: {command('mcp')}",
              file=sys.stderr)
        return 2
    if not args.headless:
        from xtal.agent import discovery

        entry = discovery.read(discovery.folder())
        if entry is not None and discovery.alive(entry):
            from xtal.agent import proxy
            return proxy.run(entry["url"], entry["token"])
    if args.window:
        print("no window is listening: start Crystal Builder and turn "
              "on Preferences > AI assistant, or use --headless",
              file=sys.stderr)
        return 2
    from xtal.agent.tools import build_server
    build_server(HeadlessHost()).run(transport="stdio")
    return 0
