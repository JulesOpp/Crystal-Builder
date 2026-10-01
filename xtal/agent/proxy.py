"""
xtal.agent.proxy
================
``xtal mcp`` as the window's stdio door.

A client that starts a command and speaks stdio (Claude Desktop,
Cursor, Codex) cannot reach the window's HTTP server itself, so when a
window is serving, ``xtal mcp`` forwards: it asks the window for its
tools once, and passes every call through to it, answer and pictures
unchanged.  The tools are the window's own, so the assistant acts on
the tab the person is looking at.

Imports ``mcp`` only when called, like the rest of the agent's MCP
side.
"""

from __future__ import annotations

import contextlib
import sys

from xtal.agent.tools import SERVER_NAME

#: The SDK's own: a call may be a long relaxation, so the read waits.
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 60 * 60.0


@contextlib.asynccontextmanager
async def connect(url: str, token: str):
    """The SDK's streamable HTTP client to ``url``, with the token.

    ``trust_env`` off: an ``HTTP_PROXY`` in the environment would
    otherwise be handed a connection to this machine.
    """
    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    try:
        from mcp.client.streamable_http import streamable_http_client
    except ImportError:                           # pragma: no cover
        # An older mcp has only the older name, which takes the
        # headers itself rather than a client.
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(
                url, headers=headers, timeout=CONNECT_TIMEOUT,
                sse_read_timeout=READ_TIMEOUT) as streams:
            yield streams
        return
    client = httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
        trust_env=False)
    async with client, streamable_http_client(
            url, http_client=client) as streams:
        yield streams


def run(url: str, token: str) -> int:
    """Serve the window's tools on stdio until the client hangs up."""
    import anyio

    try:
        anyio.run(_serve, url, token)
    except Exception as exc:              # noqa: BLE001 -- said, not raised
        print(f"xtal mcp: the window stopped answering: {exc}",
              file=sys.stderr)
        return 1
    return 0


async def _serve(url: str, token: str) -> None:
    from mcp import ClientSession
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    async with connect(url, token) as streams, \
            ClientSession(streams[0], streams[1]) as window:
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
            result = await window.call_tool(name, arguments or {})
            if result.isError:
                raise RuntimeError(" ".join(
                    getattr(block, "text", "") for block in result.content))
            return list(result.content)

        async with stdio_server() as (read, write):
            await server.run(read, write,
                             server.create_initialization_options())
