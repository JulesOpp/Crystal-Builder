"""
xtal.agent.proxy
================
``xtal mcp`` as the window's stdio door.

A client that starts a command and speaks stdio (Claude Desktop,
Cursor, Codex) cannot reach the window's HTTP server itself, so when a
window is serving, ``xtal mcp`` forwards every call to it, answer and
pictures unchanged, and the assistant acts on the window's tabs.

**The proxy follows the window and never exits for it.**  A window
closed, or switched off and on -- perhaps on a new port or token, and
no longer knowing this proxy's session -- answers the call that meets
it with the reason ("window: ..."); the connection is dropped, and the
next call reads the discovery file afresh.  Only the client closing
stdin ends the proxy: it used to exit so the client would start it
again, and few clients do.

A call may be an hour's relaxation, so the SDK's client waits up to
:data:`READ_TIMEOUT`; a window that stopped serving, or abandoned a
server thread with the call on it, never answers.  So the window is
probed (:func:`xtal.agent.discovery.alive`, a few milliseconds) as a
call goes out and every :data:`WATCH` seconds while it is out.

Imports ``mcp`` only when called, like the rest of the agent's MCP
side.
"""

from __future__ import annotations

import contextlib

from xtal.agent import discovery
from xtal.agent.tools import SERVER_NAME

#: The SDK's own: a call may be a long relaxation, so the read waits.
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 60 * 60.0
#: Seconds the handshake and the tool list may take: the window
#: answers them from its server's thread, in milliseconds.
START_TIMEOUT = 10.0
#: Seconds between probes of the window while a call is out.
WATCH = 5.0

#: What the assistant is told when the window stops answering.
GONE = ("the Crystal Builder window stopped serving (it was closed, or "
        "Preferences > AI assistant was switched off); the next call "
        "reaches it again once it is serving")
#: ... and when none is serving to be reached.
NOWHERE = ("no window is listening: start Crystal Builder and turn on "
           "Preferences > AI assistant")
#: Said of a call whose connection another call dropped.
DROPPED = ("the connection to the window was reset while this call was "
           "out; the window may still be running it")
#: The SDK's answers for a session that has gone: the window's 404 --
#: it never ran the call -- and a session closed under the call.
TERMINATED = "Session terminated"
CLOSED = "Connection closed"


class WindowGone(RuntimeError):
    """No window is serving, or the one called stopped answering."""


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
    """Serve the window's tools on stdio until the client hangs up.

    ``entry`` is the window :mod:`xtal.agent.serve` found; every
    connection reads the discovery file afresh, so it is not kept.
    """
    import anyio

    anyio.run(_serve, discovery.folder())
    return 0


async def _alive(entry: dict) -> bool:
    import anyio

    return await anyio.to_thread.run_sync(discovery.alive, entry)


class _Window:
    """The connection to whichever window is serving: made when a call
    needs one, dropped when a call fails on it.

    It is held by a task of its own in ``group``, because anyio's
    cancel scopes must be left by the task that entered them and every
    call is a task of the server's.
    """

    def __init__(self, folder, group):
        import anyio

        self.folder = folder
        self.entry: dict | None = None
        #: Fixed for a version, so asked once and kept.
        self.tools = None
        self._group = group
        self._session = None
        self._closed = None
        self._lock = anyio.Lock()

    async def session(self):
        async with self._lock:
            entry = discovery.read(self.folder)
            held = self.entry if self._session is not None else None
            if entry is None or held is None or any(
                    entry[key] != held[key] for key in ("port", "token")):
                # Gone, or restarted where the held session cannot be.
                self.drop(self._session)
                if entry is None or not await _alive(entry):
                    raise WindowGone(NOWHERE)
                await self._group.start(self._hold, entry)
            return self._session

    def drop(self, session) -> None:
        """Let go of ``session``, unless another has replaced it."""
        if session is not None and session is self._session:
            self._closed.set()
            self._session = self._closed = None

    async def _hold(self, entry, *, task_status):
        import anyio
        from mcp import ClientSession

        closed = anyio.Event()
        started = False
        try:
            async with connect(entry["url"], entry["token"]) as streams, \
                    ClientSession(streams[0], streams[1]) as session:
                with anyio.fail_after(START_TIMEOUT):
                    await session.initialize()
                    if self.tools is None:
                        self.tools = (await session.list_tools()).tools
                self.entry, self._session, self._closed = (
                    entry, session, closed)
                started = True
                task_status.started()
                await closed.wait()
        except Exception:                 # noqa: BLE001 -- see below
            # Before it is held the caller is told; after, a call on
            # it is ("Connection closed"), and this must not end the
            # proxy.
            if not started:
                raise
        finally:
            if self._closed is closed:
                self._session = self._closed = None


def _lost(exc: Exception) -> bool:
    """Whether ``exc`` means the session is gone, rather than only the
    call that raised it."""
    import anyio
    import httpx
    from mcp.shared.exceptions import McpError

    if isinstance(exc, McpError):
        return str(exc) in (TERMINATED, CLOSED)
    return isinstance(exc, (
        WindowGone, httpx.TransportError, httpx.HTTPStatusError,
        anyio.ClosedResourceError, anyio.BrokenResourceError,
        anyio.EndOfStream))


async def _forward(window: _Window, name: str, arguments: dict):
    """The window's answer, or an error result saying why there is
    none.  A session that failed is dropped, so the next call finds
    the window afresh, and a call the window refused unseen (its 404)
    is made once more at once."""
    from mcp.types import CallToolResult, TextContent

    for again in (True, False):
        session = None
        try:
            session = await window.session()
            return await _watched(window, session, name, arguments)
        except Exception as exc:          # noqa: BLE001 -- answered
            error = exc
            if not _lost(exc):
                break
            window.drop(session)
            if not (again and str(exc) == TERMINATED):
                break
    reason = str(error) or type(error).__name__
    return CallToolResult(isError=True, content=[
        TextContent(type="text", text=f"window: {reason}")])


async def _watched(window: _Window, session, name: str, arguments: dict):
    """``session.call_tool``, given up when the window stops answering
    a probe -- or the session is dropped under it, which ends the
    SDK's reading of its answers and would leave it waiting."""
    import anyio

    outcome = {}
    async with anyio.create_task_group() as group:
        async def watch():
            while (window._session is session
                   and await _alive(window.entry)):
                await anyio.sleep(WATCH)
            group.cancel_scope.cancel()

        async def forward():
            # Kept rather than raised: out of a task group it would be
            # an exception group, and the client would read that.
            try:
                outcome["result"] = await session.call_tool(
                    name, arguments)
            except Exception as exc:      # noqa: BLE001 -- raised below
                outcome["error"] = exc
            group.cancel_scope.cancel()

        group.start_soon(watch)
        group.start_soon(forward)
    if "error" in outcome:
        raise outcome["error"]
    if "result" not in outcome:
        raise WindowGone(GONE if window._session is session else DROPPED)
    return outcome["result"]


async def _serve(folder) -> None:
    import anyio
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    server = Server(SERVER_NAME)
    async with anyio.create_task_group() as group:
        window = _Window(folder, group)

        @server.list_tools()
        async def list_tools():
            # With no window serving yet, none: the client sees the
            # tools on its next list_tools, and a call's own lookup
            # asks again.
            if window.tools is None:
                with contextlib.suppress(Exception):
                    await window.session()
            return window.tools or []

        # The window checks the arguments itself, against the same
        # schemas, and says what was wrong in its own words.
        @server.call_tool(validate_input=False)
        async def call_tool(name, arguments):
            return await _forward(window, name, arguments or {})

        async with stdio_server() as (read, write):
            await server.run(
                read, write, server.create_initialization_options())
        # The client hung up: end the window's session, briefly.
        window.drop(window._session)
        group.cancel_scope.deadline = anyio.current_time() + START_TIMEOUT
