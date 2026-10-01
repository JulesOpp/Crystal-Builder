"""
xtalapp.agent_server
====================
The window's MCP server: the agent's tools over streamable HTTP, on
loopback, acting on the open tabs (:mod:`xtalapp.agent_host`).

**Where it runs.**  ``uvicorn`` on a plain daemon thread, not a
``QThread``: the server is asyncio and needs no Qt event loop, and a
daemon thread lets the application quit even while a tool call -- a
long relaxation -- is still computing.  Every verb crosses to the GUI
thread through the host's :class:`~xtalapp.agent_host.Bridge`; this
object lives on the GUI thread, and its signals are emitted there.

**Stopping cannot deadlock.**  A tool call may be blocked waiting on
the GUI thread at the moment the GUI thread stops the server.  So
:meth:`AgentServer.stop` never waits plainly: it tells the bridge to
refuse new calls, asks uvicorn to exit, and waits for the thread
against a deadline *while turning the event loop*, so the call already
waiting is answered.  Past the deadline the thread is abandoned -- it
is a daemon -- and the window goes on.

**Who may connect.**  Bound to ``127.0.0.1`` only, and every request
must carry ``Authorization: Bearer <token>``, a token made per launch:
any page in a browser can reach loopback, and the token is what stops
it driving the window.  The SDK's own DNS-rebinding check (allowed
hosts on loopback) is on as well.  The token goes into the discovery
file, readable by its owner only, and into no log.
"""

from __future__ import annotations

import asyncio
import errno
import hmac
import logging
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QObject,
    Qt,
    Signal,
    Slot,
)

from xtal.agent import discovery

HOST = discovery.HOST
DEFAULT_PORT = 7781
#: Seconds :meth:`AgentServer.stop` waits for the server's thread,
#: turning the event loop meanwhile.  A quit is not held longer.
STOP_DEADLINE = 3.0
#: Seconds uvicorn gives an open stream to finish before cancelling
#: it -- a connected client holds one open for as long as it is.
GRACE = 1


class _NotAnError(logging.Filter):
    """uvicorn logs a stream it cancelled at shutdown as an "Exception
    in ASGI application", traceback and all.  A connected client holds
    one open for as long as it is connected, so without this every
    quit with an assistant attached wrote one into the log."""

    def filter(self, record) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not isinstance(exc, asyncio.CancelledError)


_QUIET = _NotAnError()


class ServerRefused(RuntimeError):
    """The server was not started, for the reason given."""


def discovery_folder() -> Path:
    """The window's application-data folder, unless ``XTAL_APP_DATA``
    names another -- the one ``xtal mcp`` looks in."""
    from xtalapp import applog
    return discovery.folder(applog.app_data())


def discovery_path() -> Path:
    return discovery_folder() / discovery.FILE


def write_discovery(port: int, token: str) -> Path:
    from xtal import __version__
    return discovery.write(discovery_folder(), port=port, token=token,
                           pid=os.getpid(), version=__version__)


def remove_discovery(token: str | None = None) -> None:
    discovery.remove(discovery_folder(), token=token)


class AgentServer(QObject):
    """The tools of :func:`xtal.agent.tools.build_server` over this
    window's tabs, served on ``127.0.0.1``.

    One per window, kept between starts: the token is the same until
    the application quits, so a client configured once keeps working
    when the preference is turned off and on again.
    """

    started = Signal(int)
    stopped = Signal()
    failed = Signal(str)
    clientConnected = Signal()
    verbLanded = Signal(str)

    # Emitted on the server's thread; relayed on the GUI thread.
    _clientSeen = Signal()
    _threadEnded = Signal(object, str)

    def __init__(self, window, port: int = DEFAULT_PORT,
                 token: str | None = None):
        super().__init__(window)
        self.window = window
        self.preferred_port = int(port)
        self.port = int(port)
        self.token = token or secrets.token_hex(16)
        #: Why the last start failed, or ``""``.
        self.error = ""
        self._server = None
        self._thread = None
        self._stopping = False
        self._sessions: set[bytes] = set()
        self._clientSeen.connect(self._client_seen,
                                 Qt.ConnectionType.QueuedConnection)
        self._threadEnded.connect(self._thread_ended,
                                  Qt.ConnectionType.QueuedConnection)

    @property
    def url(self) -> str:
        return discovery.url(self.port)

    @property
    def running(self) -> bool:
        return self._server is not None

    # -- starting --------------------------------------------------------

    def start(self) -> tuple[str, int]:
        """Listen, write the discovery file, and say so.

        The preferred port first and any free one when it is taken.
        Refused -- ``failed`` emitted and the reason raised -- when
        another window is already what ``xtal mcp`` finds, when
        nothing can be bound, or while a stop is still under way.
        """
        if self._stopping:
            # Reached from the stop's own event loop: starting here
            # would be undone by the rest of the stop.
            return self._refused(ServerRefused("stopping"))
        if self.running:
            return HOST, self.port
        try:
            self._refuse_over_another()
            app = self._app()
            sock = _bind(self.preferred_port)
        except ImportError as exc:
            from xtal.install import command
            return self._refused(ServerRefused(
                f"the mcp extra is not installed: {command('mcp')}"),
                exc)
        except OSError as exc:
            return self._refused(ServerRefused(
                f"could not listen on {HOST}: {exc.strerror or exc}"), exc)
        except ServerRefused as exc:
            return self._refused(exc)
        import uvicorn

        logging.getLogger("uvicorn.error").addFilter(_QUIET)
        config = uvicorn.Config(
            app, log_config=None, log_level="warning", access_log=False,
            lifespan="on", loop="asyncio", http="h11", ws="none",
            timeout_graceful_shutdown=GRACE)
        server = uvicorn.Server(config)
        self.port = sock.getsockname()[1]
        self.error = ""
        self._sessions = set()
        self._server = server
        bridge = self.window.agent_host.bridge
        # A call left running by the last server is stale from here.
        bridge.generation += 1
        bridge.closing = False
        self._thread = threading.Thread(
            target=self._serve, args=(server, sock), daemon=True,
            name="crystal-builder-mcp")
        self._thread.start()
        write_discovery(self.port, self.token)
        self.started.emit(self.port)
        return HOST, self.port

    def _refused(self, refusal: ServerRefused, cause=None):
        self.error = str(refusal)
        self.failed.emit(self.error)
        raise refusal from cause

    def _refuse_over_another(self) -> None:
        entry = discovery.read(discovery_folder())
        if entry is not None and discovery.alive(entry):
            raise ServerRefused(f"another window is already listening "
                                f"on port {entry['port']}")

    def _app(self):
        """The SDK's streamable HTTP app over this window, behind the
        token.  Built per start: the SDK's session manager runs once
        per instance."""
        from xtal.agent.tools import build_server

        mcp = build_server(self.window.agent_host)
        return _Bearer(mcp.streamable_http_app(), self.token,
                       self._seen)

    def _serve(self, server, sock) -> None:
        """The server's thread."""
        reason = ""
        try:
            server.run(sockets=[sock])
        except BaseException as exc:     # noqa: BLE001 -- reported
            reason = f"the server stopped: {exc}"
        finally:
            sock.close()
        self._threadEnded.emit(server, reason or "the server stopped")

    def _seen(self, session: bytes) -> None:
        """On the server's thread: a request from a session."""
        if session not in self._sessions:
            self._sessions.add(session)
            self._clientSeen.emit()

    @Slot()
    def _client_seen(self) -> None:
        if self.running:
            self.clientConnected.emit()

    @Slot(object, str)
    def _thread_ended(self, server, reason: str) -> None:
        """The thread ended without being asked to: say so, and leave
        no file pointing at it."""
        if server is not self._server:
            return
        self._server = self._thread = None
        remove_discovery(self.token)
        self.error = reason
        self.failed.emit(reason)

    # -- stopping --------------------------------------------------------

    def stop(self) -> None:
        """Stop serving, remove the file, and say so.

        Never a plain ``join``: see the module docstring.
        """
        server, thread = self._server, self._thread
        if server is None or self._stopping:
            return
        self._stopping = True
        try:
            self._server = self._thread = None
            self.window.agent_host.bridge.closing = True
            server.should_exit = True
            deadline = time.monotonic() + STOP_DEADLINE
            while thread.is_alive() and time.monotonic() < deadline:
                thread.join(0.05)
                # The bridge's crossing, not the person's clicks: a
                # click here could reach this method again.
                QCoreApplication.processEvents(
                    QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            remove_discovery(self.token)
        finally:
            self._stopping = False
        self.stopped.emit()


class _Bearer:
    """ASGI middleware: 401 for a request without the token, and the
    sessions it sees reported, so the window can say a client came."""

    def __init__(self, app, token: str, seen):
        self.app = app
        self.expected = f"Bearer {token}".encode("ascii")
        self.seen = seen

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            # Nothing else is served (no websockets), and nothing
            # else gets past without the token.
            return
        headers = dict(scope["headers"])
        given = headers.get(b"authorization", b"")
        if not hmac.compare_digest(given, self.expected):
            from starlette.responses import PlainTextResponse

            refusal = PlainTextResponse(
                "a bearer token is required", status_code=401,
                headers={"WWW-Authenticate": "Bearer"})
            await refusal(scope, receive, send)
            return
        session = headers.get(b"mcp-session-id")
        if session:
            self.seen(session)
        await self.app(scope, receive, send)


def _bind(port: int) -> socket.socket:
    """A listening socket on ``port``, or on any free one when that
    is taken."""
    try:
        return _listen(port)
    except OSError:
        if port == 0:
            raise
        return _listen(0)


def _listen(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":                         # pragma: no cover
            # Windows' SO_REUSEADDR would let us take a port somebody
            # is listening on.
            sock.setsockopt(socket.SOL_SOCKET,
                            socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            if sys.platform == "darwin" and port and _answered(port):
                # macOS's SO_REUSEADDR also lets 127.0.0.1 be bound
                # under somebody's wildcard listener on the port, and
                # theirs must be the fallback, not a shared port.
                raise OSError(errno.EADDRINUSE,
                              os.strerror(errno.EADDRINUSE))
            # Off and on again on the same port: stopping closes a
            # connected client's connections from this end, and
            # without it their TIME_WAIT moved the server elsewhere
            # for half a minute -- away from the line it was given.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
        sock.listen()
    except OSError:
        sock.close()
        raise
    return sock


def _answered(port: int) -> bool:
    """Something accepts a connection on loopback at ``port``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) == 0
