"""
xtal.agent.proxy
================
``xtal mcp`` as the window's stdio door.

A client that starts a command and speaks stdio (Claude Desktop,
Cursor, Codex) cannot reach the window's HTTP server itself, so when a
window is serving, ``xtal mcp`` forwards: it asks the window for its
tools once, and passes every call through to it, answer and pictures
unchanged.  The tools are the window's own, so the assistant acts on
the window's tabs.

**A window that goes away is said, not waited for.**  The SDK's
client waits up to :data:`READ_TIMEOUT` for an answer, because a call
may be an hour's relaxation, and a window that has stopped serving
never sends one.  So the window is probed before every call is
forwarded (:func:`xtal.agent.discovery.alive`, a few milliseconds) and
every :data:`WATCH` seconds while one is out; once it does not answer,
the call is answered with the reason and the proxy exits 1, so the
client starts ``xtal mcp`` afresh -- which then finds whatever is
serving by then, or none.  The call itself has no short timeout.  A
window switched off and on again answers the probe -- same port, same
token -- but no longer knows this proxy's session ("Session
terminated"), which is the same ending.

Imports ``mcp`` only when called, like the rest of the agent's MCP
side.
"""

from __future__ import annotations

import contextlib
import json
import sys

from xtal.agent.tools import SERVER_NAME

#: The SDK's own: a call may be a long relaxation, so the read waits.
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 60 * 60.0
#: Seconds the handshake and the tool list may take: the window
#: answers them from its server's thread, in milliseconds.
START_TIMEOUT = 10.0
#: Seconds between probes of the window while a call is out.
WATCH = 5.0

#: What the assistant is told, and the client's log says, when the
#: window has gone.
GONE = ("the Crystal Builder window stopped serving (it was closed, or "
        "Preferences > AI assistant was switched off); nothing more can "
        "reach it through this connection, and xtal mcp is exiting so "
        "the client can start it again")


#: What it is told when the window answers, but not to this proxy's
#: session -- its server was switched off and on again since.
ENDED = ("the Crystal Builder window ended this connection's session "
         "(Session terminated: its server was switched off and on "
         "again); xtal mcp is exiting so the client can start it again "
         "and open a new one")
#: The SDK's error for a session the server no longer knows (404).
TERMINATED = "Session terminated"


class WindowGone(RuntimeError):
    """The window stopped answering, or no longer knows this proxy's
    session; the proxy is done."""


@contextlib.asynccontextmanager
async def connect(url: str, token: str):
    """The SDK's streamable HTTP client to ``url``, with the token.

    ``trust_env`` off: an ``HTTP_PROXY`` in the environment would
    otherwise be handed a connection to this machine.
    """
    import httpx
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {token}"}
    client = httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
        trust_env=False)
    async with client, streamable_http_client(
            url, http_client=client) as streams:
        yield streams


def run(entry: dict) -> int:
    """Serve the window's tools on stdio until the client hangs up --
    0 -- or the window goes away -- 1, said on stderr."""
    import anyio

    try:
        gone = anyio.run(_serve, entry)
    except Exception as exc:              # noqa: BLE001 -- said, not raised
        print(f"xtal mcp: the window stopped answering: {exc}",
              file=sys.stderr)
        return 1
    if gone:
        print(f"xtal mcp: {gone}", file=sys.stderr)
        return 1
    return 0


async def _alive(entry: dict) -> bool:
    import anyio

    from xtal.agent import discovery

    return await anyio.to_thread.run_sync(discovery.alive, entry)


async def _forward(entry: dict, call):
    """``await call()``, refused with :class:`WindowGone` when the
    window does not answer a probe first, or stops answering while
    the call is out."""
    import anyio

    if not await _alive(entry):
        raise WindowGone(GONE)
    outcome = {}
    async with anyio.create_task_group() as group:
        async def watch():
            while True:
                await anyio.sleep(WATCH)
                if not await _alive(entry):
                    group.cancel_scope.cancel()
                    return

        async def forward():
            # Kept rather than raised: out of a task group it would be
            # an exception group, and the client would read that.
            try:
                outcome["result"] = await call()
            except Exception as exc:  # noqa: BLE001 -- raised below
                outcome["error"] = exc
            group.cancel_scope.cancel()

        group.start_soon(watch)
        group.start_soon(forward)
    if "error" in outcome:
        raise outcome["error"]
    if "result" not in outcome:
        raise WindowGone(GONE)
    return outcome["result"]


class _Leaving:
    """The request whose answer is the proxy's last, and the moment
    that answer has reached stdout: exiting before it is written would
    leave the client with a dead process and no reason."""

    def __init__(self):
        import anyio

        self.request = None
        self.reason = ""
        self.written = anyio.Event()


class _Stdout:
    """Standard output as :func:`mcp.server.stdio.stdio_server` writes
    it, noticing the line that answers :attr:`_Leaving.request`."""

    def __init__(self, leaving: _Leaving):
        from io import TextIOWrapper

        import anyio

        self._out = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer,
                                                  encoding="utf-8"))
        self._leaving = leaving
        self._last = ""

    async def write(self, text: str) -> None:
        await self._out.write(text)
        self._last = text

    async def flush(self) -> None:
        await self._out.flush()
        request = self._leaving.request
        if request is not None and _answers(self._last, request):
            self._leaving.written.set()


class _Stdin:
    """Standard input, a line at a time, that a cancelled proxy can
    leave.  The SDK's own reads it on one of anyio's worker threads,
    which are not daemons: blocked in ``readline`` it held the exit
    until the client wrote again or hung up.  Here a daemon thread
    reads, and :meth:`close` releases whatever waits on it."""

    def __init__(self):
        import queue
        import threading
        from io import TextIOWrapper

        self._lines = queue.Queue()
        source = TextIOWrapper(sys.stdin.buffer, encoding="utf-8",
                               errors="replace")

        def read():
            for line in source:
                self._lines.put(line)
            self._lines.put(None)

        threading.Thread(target=read, daemon=True,
                         name="xtal-mcp-stdin").start()

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        import anyio

        line = await anyio.to_thread.run_sync(self._lines.get,
                                              abandon_on_cancel=True)
        if line is None:
            self._lines.put(None)          # for any other reader
            raise StopAsyncIteration
        return line

    def close(self) -> None:
        self._lines.put(None)


def _answers(line: str, request) -> bool:
    try:
        return json.loads(line).get("id") == request
    except (ValueError, AttributeError):
        return False


async def _serve(entry: dict) -> str:
    """Why the proxy is leaving, or ``""`` when the client hung up."""
    import anyio
    from mcp import ClientSession
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    from mcp.shared.exceptions import McpError

    leaving = _Leaving()
    async with connect(entry["url"], entry["token"]) as streams, \
            ClientSession(streams[0], streams[1]) as window:
        with anyio.fail_after(START_TIMEOUT):
            await window.initialize()
            tools = (await window.list_tools()).tools
        server = Server(SERVER_NAME)

        @server.list_tools()
        async def list_tools():
            return tools

        # The window checks the arguments itself, against the same
        # schemas, and says what was wrong in its own words.
        @server.call_tool(validate_input=False)
        async def call_tool(name, arguments):
            if leaving.request is not None:
                raise WindowGone(leaving.reason)
            try:
                try:
                    result = await _forward(
                        entry, lambda: window.call_tool(name,
                                                        arguments or {}))
                except McpError as exc:
                    if TERMINATED not in str(exc):
                        raise
                    # The probe passed -- the same port and token,
                    # a new server -- but every call on this session
                    # would be refused the same way.
                    raise WindowGone(ENDED) from exc
            except WindowGone as exc:
                leaving.reason = str(exc)
                leaving.request = server.request_context.request_id
                raise
            if result.isError:
                raise RuntimeError(" ".join(
                    getattr(block, "text", "") for block in result.content))
            return list(result.content)

        stdin = _Stdin()
        try:
            async with anyio.create_task_group() as group:
                async def leave_once_said():
                    await leaving.written.wait()
                    group.cancel_scope.cancel()

                group.start_soon(leave_once_said)
                async with stdio_server(stdin=stdin,
                                        stdout=_Stdout(leaving)) as (
                        read, write):
                    await server.run(
                        read, write, server.create_initialization_options())
                # The client hung up.
                group.cancel_scope.cancel()
        finally:
            stdin.close()
    return leaving.reason
