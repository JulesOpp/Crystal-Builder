"""
xtal.agent.tools
================
The session verbs as MCP tools, over whichever host holds the sessions.

One tool per verb in :data:`~xtal.agent.capabilities.VERBS`, named as
the verb and taking its keywords, so the skill an assistant reads
describes the tools without a second list to drift.  The tools reach
the structure only through a :class:`Host`: the headless one in
:mod:`xtal.agent.serve` holds sessions in a dict, and the window holds
one per tab.  Nothing here knows which, so a verb that answers one way
from ``xtal mcp`` answers the same way from the window.

A verb's ``**options`` (``energy``, ``optimize``, ``run``, ``select``,
``build``) arrive as one object of that name, because a JSON schema
has no open-ended keywords.

**Every tool runs on a worker thread, never on the server's event
loop.**  The SDK calls a plain function inline, so one relaxation
silenced the whole server for its length: the window's discovery
probe went unanswered and a second window started over it.  The host
says whether its sessions take one call at a time themselves
(``serialises``: the window's bridge does, and refuses with
``WINDOW_BUSY`` what must wait); for any other host the tools take a
lock, so the headless sessions are never touched by two threads.

The SDK is the ``mcp`` extra and is imported by :func:`build_server`
alone, so the core imports this module without it.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import inspect as pyinspect
import threading
import typing
from pathlib import Path
from typing import Any, Literal, Protocol

from xtal.agent.answers import SITES, VerbResult
from xtal.agent.capabilities import VERBS, capabilities, help_for
from xtal.agent.diagnostics import Diagnostic, to_json
from xtal.agent.session import Session

#: Verbs that make a session rather than act on one: the host does
#: them, so the session lands where the host keeps its documents.
HOST_VERBS = ("open", "new", "build")

#: What a tool says before there is anything to act on.
NO_SESSION = "open a structure first"

#: What a client lists the tools under, served headless, by the
#: window, or through ``xtal mcp``'s proxy.
SERVER_NAME = "crystal-builder"


class Host(Protocol):
    """Where the sessions the tools act on are kept.

    A host whose sessions take one call at a time themselves sets
    ``serialises = True``; the tools lock around any other.
    """

    def current(self) -> Session:
        """The session the verbs act on; ``LookupError`` if none."""

    def open(self, path, workspace=None) -> Session:
        """Open ``path``, or hand back the session already over it,
        and make it current."""

    def sessions(self) -> list[Session]:
        """Every session held, current or not."""

    def switch(self, path) -> Session:
        """Make the session over ``path`` current; ``LookupError`` if
        none is."""


def build_server(host: Host, name: str = SERVER_NAME):
    """A ``FastMCP`` server whose tools act on ``host``'s sessions."""
    from mcp.server.fastmcp import FastMCP

    # The SDK logs every request at INFO, which on stdio is a line in
    # the client's log per tool call.
    server = FastMCP(name, log_level="WARNING")
    one_at_a_time = (contextlib.nullcontext()
                     if getattr(host, "serialises", False)
                     else threading.Lock())
    add = functools.partial(_add, server, one_at_a_time)
    for verb in VERBS:
        if verb in HOST_VERBS:
            continue
        fn, description = _verb_tool(host, verb)
        add(fn, verb, description)
    for verb, make in (("open", _open_tool), ("new", _new_tool),
                       ("build", _build_tool)):
        fn, description = make(host)
        add(fn, verb, description)
    add(_documents_tool(host), "documents",
        "The documents open here: path, name, atoms, whether modified, "
        "and which one is current -- the one every verb acts on.")
    add(_switch_tool(host), "switch",
        "Make the open document at ``path`` the current one.")
    add(_capabilities_tool(), "capabilities",
        pyinspect.getdoc(capabilities))
    add(_help_tool(), "help_for", pyinspect.getdoc(help_for))
    return server


def _add(server, one_at_a_time, fn, name, description) -> None:
    # Unstructured: the answer is the JSON text, and a copy of it as
    # structured content would be the same answer twice in the
    # assistant's context.
    server.add_tool(_off_the_loop(fn, name, one_at_a_time), name=name,
                    description=description, structured_output=False)


def _off_the_loop(fn, name, one_at_a_time):
    """``fn`` as a coroutine that runs it on a worker thread, with the
    same signature for the schema.  A call the client gave up on is
    left to finish on its thread: a verb cannot be stopped half way,
    and the window's bridge refuses what it would apply too late."""
    import anyio

    signature = pyinspect.signature(fn, eval_str=True)

    def blocking(kwargs):
        with one_at_a_time:
            return fn(**kwargs)

    async def tool(**kwargs):
        return await anyio.to_thread.run_sync(
            functools.partial(blocking, kwargs), abandon_on_cancel=True)

    _dress(tool, name, signature)
    return tool


# ----------------------------------------------------------------------
#  VERBS ON THE CURRENT SESSION
# ----------------------------------------------------------------------

def _verb_tool(host: Host, verb: str):
    method = getattr(Session, verb)
    signature, spread = _signature(method)
    extra = ()
    if verb == "inspect":
        extra = (pyinspect.Parameter(
            "sites", pyinspect.Parameter.KEYWORD_ONLY,
            default="problems", annotation=Literal[SITES]),)
        signature = signature.replace(
            parameters=[*signature.parameters.values(), *extra])

    def tool(**kwargs):
        try:
            session = host.current()
        except LookupError as exc:
            return _text(_no_session(verb, exc))
        if verb == "inspect":
            sites = kwargs.pop("sites")
            found = session.inspect(**kwargs)
            if isinstance(found, VerbResult):
                # A window that is closing refuses even a look.
                return _text(found)
            return to_json(found.to_dict(sites), compact=True)
        _spread(verb, kwargs, spread)
        answer = getattr(session, verb)(**kwargs)
        if verb == "render":
            return _picture(answer)
        if isinstance(answer, Path):
            answer = _written(verb, answer, session)
        return _text(answer)

    _dress(tool, verb, signature)
    description = _description(method, spread)
    if extra:
        description += ("\n\n``sites``: which site rows to give -- "
                        "those a diagnostic names (problems), all, "
                        "or none.")
    return tool, description


def _picture(answer: VerbResult):
    from mcp.types import ImageContent, TextContent

    content = [TextContent(type="text", text=to_json(answer.to_dict(),
                                                     compact=True))]
    if answer.ok:
        png = Path(answer.data["path"]).read_bytes()
        content.append(ImageContent(
            type="image", data=base64.b64encode(png).decode("ascii"),
            mimeType="image/png"))
    return content


def _written(verb: str, path: Path, session: Session) -> VerbResult:
    """``save`` and ``export`` hand a script the path; an assistant
    reads an answer like every other verb's."""
    said = "saved" if verb == "save" else "exported"
    return session._named(VerbResult(verb, True, f"{said} {path.name}",
                                     atoms_before=session.n_atoms,
                                     atoms_after=session.n_atoms,
                                     data={"path": str(path)}))


# ----------------------------------------------------------------------
#  VERBS THE HOST DOES
# ----------------------------------------------------------------------

def _open_tool(host: Host):
    method = Session.open
    signature, _spread_name = _signature(method)

    def tool(path, workspace=None):
        held = host.sessions()
        session = host.open(path, workspace)
        if any(s is session for s in held):
            # What opening said the first time is the file as it was
            # read; the session has been edited since.
            n = session.n_atoms
            return _text(session._named(VerbResult(
                "open", True, f"{_name(session)} is already open",
                atoms_before=n, atoms_after=n,
                data={"modified": session.modified},
                diagnostics=_workspace_ignored(session, workspace))))
        return _text(session._named(session.opened or VerbResult(
            "open", True, f"opened {_name(session)}",
            atoms_after=session.n_atoms)))

    _dress(tool, "open", signature)
    return tool, _description(method, None)


def _new_tool(host: Host):
    """``Session.new``, filed in ``workspace`` and opened by the host.

    The host keeps documents by their file, so a cell with nowhere to
    be cannot be handed to it -- the window makes ``untitled`` in its
    workspace for the same reason.
    """
    method = Session.new
    signature, _spread_name = _signature(method)
    signature = signature.replace(parameters=[
        p.replace(default=p.empty, annotation=str)
        if p.name == "workspace" else p
        for p in signature.parameters.values()])

    def tool(**kwargs):
        made = Session.new(**kwargs)
        session = host.open(made.save())
        return _text(session._named(VerbResult(
            "new", True, f"new {kwargs['space_group']} cell, "
                         f"{_name(session)}",
            atoms_after=session.n_atoms,
            data={"path": str(session.path)})))

    _dress(tool, "new", signature)
    return tool, (_description(method, None)
                  + "\n\n``workspace`` is required here: the cell is "
                    "filed there and opened as a document.")


def _build_tool(host: Host):
    from xtal.agent.session import BuildFailed

    method = Session.build
    signature, spread = _signature(method)

    def tool(**kwargs):
        _spread("build", kwargs, spread)
        try:
            built = Session.build(**kwargs)
        except BuildFailed as exc:
            return _text(exc.result)
        session = host.open(built.path)
        return _text(session._named(built.built))

    _dress(tool, "build", signature)
    return tool, _description(method, spread)


def _workspace_ignored(session: Session, workspace) -> list:
    """``WORKSPACE_IGNORED`` when a re-open names a workspace the open
    document is not in: it stays where it is, and an assistant that
    named another would look for its runs there."""
    from xtal.workspace import Workspace

    if workspace is None or session.path is None:
        return []
    found = Workspace.find(session.path)
    if found is not None and found.root == Path(workspace).resolve():
        return []
    return [Diagnostic("WORKSPACE_IGNORED",
                       f"{session.path} is already open; {workspace} "
                       f"was not used")]


def _documents_tool(host: Host):
    def documents():
        return to_json({"documents": [_row(host, s)
                                      for s in host.sessions()]},
                       compact=True)
    return documents


def _switch_tool(host: Host):
    def switch(path: str):
        try:
            session = host.switch(path)
        except LookupError as exc:
            return _text(_refused(
                "switch", str(exc) or f"{path} is not open"))
        return to_json(_row(host, session), compact=True)
    return switch


def _row(host: Host, session: Session) -> dict:
    try:
        current = host.current() is session
    except LookupError:
        current = False
    return {"path": str(session.path) if session.path else "",
            "name": _name(session), "atoms": session.n_atoms,
            "modified": session.modified, "current": current}


def _name(session: Session) -> str:
    return session.path.name if session.path else "untitled"


# ----------------------------------------------------------------------
#  ASKING
# ----------------------------------------------------------------------

def _capabilities_tool():
    def capabilities_(verbose: bool = False):
        return capabilities(verbose=verbose).to_json()
    _dress(capabilities_, "capabilities",
           pyinspect.signature(capabilities_, eval_str=True))
    return capabilities_


def _help_tool():
    def help_for_(name: str):
        return help_for(name)
    _dress(help_for_, "help_for",
           pyinspect.signature(help_for_, eval_str=True))
    return help_for_


# ----------------------------------------------------------------------
#  PLUMBING
# ----------------------------------------------------------------------

def _signature(method):
    """The verb's own parameters, every one a keyword, typed for the
    schema: ``Any`` where the verb leaves a parameter untyped, which
    the SDK would otherwise describe as a string -- and ``frac`` is
    three numbers.  A ``**options`` becomes one object of that name.
    """
    hints = typing.get_type_hints(method)
    params, spread = [], None
    for p in pyinspect.signature(method).parameters.values():
        if p.name in ("self", "cls"):
            continue
        if p.kind is p.VAR_KEYWORD:
            spread = p.name
            p = p.replace(kind=p.KEYWORD_ONLY, default=None,
                          annotation=dict[str, Any] | None)
        else:
            p = p.replace(kind=p.KEYWORD_ONLY,
                          annotation=hints.get(p.name, Any))
        params.append(p)
    return pyinspect.Signature(params), spread


def _spread(verb: str, kwargs: dict, spread: str | None) -> None:
    """``**options`` back into the call -- refusing, as Python does, an
    option that names a parameter, rather than letting one win."""
    if spread is None:
        return
    extra = kwargs.pop(spread) or {}
    clash = sorted(set(extra) & set(kwargs))
    if clash:
        raise TypeError(f"{verb}() got multiple values for argument "
                        f"{clash[0]!r}: give it once, not also in "
                        f"{spread}")
    kwargs.update(extra)


def _dress(fn, name, signature) -> None:
    fn.__name__ = fn.__qualname__ = name
    fn.__signature__ = signature
    fn.__annotations__ = {p.name: p.annotation
                          for p in signature.parameters.values()}


def _description(method, spread) -> str:
    """The verb's docstring, or its signature where it has none."""
    own = pyinspect.signature(method, eval_str=True)
    own = own.replace(parameters=[p for p in own.parameters.values()
                                  if p.name not in ("self", "cls")],
                      return_annotation=own.empty)
    text = pyinspect.getdoc(method) or f"{method.__name__}{own}"
    if spread is not None:
        text += (f"\n\n``{spread}``: the keyword arguments the verb "
                 f"takes as ``**{spread}``, as one object.")
    return text


def _no_session(verb: str, exc: LookupError) -> VerbResult:
    return _refused(verb, str(exc.args[0]) if exc.args else NO_SESSION)


def _refused(verb: str, message: str) -> VerbResult:
    return VerbResult(verb, False, message, diagnostics=[
        Diagnostic("OPERATION_REFUSED", message)])


def _text(answer: VerbResult) -> str:
    return to_json(answer.to_dict(), compact=True)
