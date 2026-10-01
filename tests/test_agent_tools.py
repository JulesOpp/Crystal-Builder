"""The MCP tools: one per verb, over whatever host holds the sessions.

Every test here talks to the server through the SDK's own client over
its in-memory transport, so what is checked is what an assistant
sees -- the tool list, each tool's schema and the JSON it answers --
and not what a Python caller of the functions would.  The tool layer
is the one both hosts serve (headless here, the window later), so a
verb that answers differently here answers differently there.
"""

import base64
import json
from pathlib import Path

import pytest

from tests.conftest import needs_offscreen_gl
from xtal.agent.capabilities import VERBS
from xtal.agent.serve import HeadlessHost
from xtal.agent.tools import build_server

pytest.importorskip("mcp")


def _talk(conversation):
    """``conversation(client)`` against a fresh headless server."""
    import anyio
    from mcp.shared.memory import (
        create_connected_server_and_client_session,
    )

    server = build_server(HeadlessHost())

    async def main():
        async with create_connected_server_and_client_session(
                server) as client:
            return await conversation(client)

    return anyio.run(main)


def _answer(result) -> dict:
    assert not result.isError, result.content[0].text
    return json.loads(result.content[0].text)


def test_every_verb_is_a_tool_with_the_verbs_own_parameters():
    """A verb missing from the list is one an assistant cannot call,
    and a parameter missing from a schema is one it cannot pass --
    ``add_atom`` without ``bonded_to`` places atoms bonded to
    nothing."""
    async def conversation(client):
        return (await client.list_tools()).tools

    tools = {t.name: t for t in _talk(conversation)}
    host_tools = {"open", "new", "build"}
    expected = (set(VERBS) - host_tools) | {
        "documents", "switch", "capabilities", "help_for"}
    assert expected <= set(tools)
    assert host_tools <= set(tools)
    schema = tools["add_atom"].inputSchema
    assert {"element", "frac", "cart", "bonded_to"} <= set(
        schema["properties"])
    assert schema["required"] == ["element"]
    assert "Place one atom" in tools["add_atom"].description


def test_a_tool_before_any_open_is_refused_not_raised():
    """Before ``open`` there is nothing to act on.  An error there
    reads to an assistant as a broken server; a refusal with its code
    says what to do next."""
    async def conversation(client):
        return [await client.call_tool(name, {})
                for name in ("inspect", "undo", "reduce_to_p1")]

    for result in _talk(conversation):
        answer = _answer(result)
        assert answer["ok"] is False
        assert answer["message"] == "open a structure first"
        assert [d["code"] for d in answer["diagnostics"]] == [
            "OPERATION_REFUSED"]


def test_open_inspect_add_atom_and_undo_through_the_client(rutile_cif):
    """The round trip an assistant makes first: if any step of it
    answers differently through the server than through a session,
    the tools are not the verbs."""
    async def conversation(client):
        opened = await client.call_tool("open", {"path": rutile_cif})
        looked = await client.call_tool("inspect", {})
        added = await client.call_tool(
            "add_atom", {"element": "O", "frac": [0.5, 0.5, 0.25]})
        undone = await client.call_tool("undo", {})
        return opened, looked, added, undone

    opened, looked, added, undone = map(_answer, _talk(conversation))
    assert opened["ok"] and opened["atoms_after"] == 6
    assert looked["formula"] == "TiO2"
    assert added["ok"] and added["atoms_after"] > 6
    assert added["undo_label"] == "Add O"
    assert undone["ok"]
    assert undone["message"] == "undid Add O"
    assert undone["atoms_after"] == 6


def test_inspect_tool_defaults_to_problem_sites_only(rutile_cif):
    """The rows a diagnostic names are the ones worth an assistant's
    context; a reduced framework's hundreds of others are not, and
    the default is what gets called."""
    async def conversation(client):
        await client.call_tool("open", {"path": rutile_cif})
        # An O on the c axis between two Ti: too close to both.
        await client.call_tool(
            "add_atom", {"element": "O", "frac": [0.5, 0.5, 0.25]})
        return [await client.call_tool("inspect", args) for args in
                ({}, {"sites": "all"}, {"sites": "none"})]

    default, every, none = map(_answer, _talk(conversation))
    named = [s["index"] for s in default["sites"]]
    assert named == [0, 2]
    assert len(every["sites"]) == every["n_sites"] == 3
    assert none["sites"] == []


@pytest.mark.gui
@pytest.mark.slow
@needs_offscreen_gl
def test_render_tool_returns_the_picture_as_image_content(tmp_path,
                                                          rutile_cif):
    """An assistant cannot open a path on the machine the server runs
    on; the picture it is shown is the one in the answer."""
    pytest.importorskip("vtkmodules")
    out = tmp_path / "r.png"

    async def conversation(client):
        await client.call_tool("open", {"path": rutile_cif})
        return await client.call_tool(
            "render", {"path": str(out), "view": "c",
                       "size": [160, 120]})

    result = _talk(conversation)
    answer = _answer(result)
    assert answer["ok"], answer
    image = result.content[1]
    assert image.type == "image" and image.mimeType == "image/png"
    assert base64.b64decode(image.data) == out.read_bytes()


def test_two_opens_of_one_file_are_one_session(tmp_path, rutile_cif):
    """An assistant that opens a file it already has must get its
    edits back, not a fresh copy beside them -- whichever spelling of
    the path it used."""
    (tmp_path / "elsewhere").mkdir()
    spelled = str(tmp_path / "elsewhere" / ".." / Path(rutile_cif).name)

    async def conversation(client):
        await client.call_tool("open", {"path": rutile_cif})
        added = await client.call_tool(
            "add_atom", {"element": "O", "frac": [0.5, 0.5, 0.25]})
        again = await client.call_tool("open", {"path": spelled})
        listed = await client.call_tool("documents", {})
        undone = await client.call_tool("undo", {})
        return added, again, listed, undone

    added, again, listed, undone = map(_answer, _talk(conversation))
    assert again["ok"]
    assert "already open" in again["message"]
    assert again["atoms_after"] == added["atoms_after"]
    assert again["data"]["modified"] is True
    rows = listed["documents"]
    assert len(rows) == 1
    assert rows[0]["modified"] and rows[0]["current"]
    assert rows[0]["atoms"] == added["atoms_after"] > 6
    assert undone["message"] == "undid Add O"


def test_switch_makes_another_open_document_current(tmp_path, rutile_cif,
                                                    quartz_cif):
    """The verbs act on the current document, so an assistant holding
    two has to be able to say which; one it never opened is
    refused."""
    async def conversation(client):
        await client.call_tool("open", {"path": rutile_cif})
        await client.call_tool("open", {"path": quartz_cif})
        switched = await client.call_tool("switch", {"path": rutile_cif})
        looked = await client.call_tool("inspect", {"sites": "none"})
        stranger = await client.call_tool(
            "switch", {"path": str(tmp_path / "never.cif")})
        listed = await client.call_tool("documents", {})
        return switched, looked, stranger, listed

    switched, looked, stranger, listed = map(_answer, _talk(conversation))
    assert switched["name"] == "rutile.cif" and switched["current"]
    assert looked["formula"] == "TiO2"
    assert stranger["ok"] is False
    assert stranger["diagnostics"][0]["code"] == "OPERATION_REFUSED"
    current = [r["name"] for r in listed["documents"] if r["current"]]
    assert current == ["rutile.cif"]


def test_new_makes_a_cell_in_the_workspace_and_opens_it(tmp_path):
    """A cell the host cannot hold by its file is one the next verb
    cannot reach; the schema says the workspace is needed rather than
    a call finding out."""
    workspace = tmp_path / "ws"

    async def conversation(client):
        tools = {t.name: t for t in (await client.list_tools()).tools}
        made = await client.call_tool(
            "new", {"a": 4.2, "b": 4.2, "c": 4.2,
                    "space_group": "Pm-3m", "workspace": str(workspace)})
        added = await client.call_tool(
            "add_atom", {"element": "Na", "frac": [0, 0, 0]})
        listed = await client.call_tool("documents", {})
        return tools["new"], made, added, listed

    tool, made, added, listed = _talk(conversation)
    assert "workspace" in tool.inputSchema["required"]
    made, added, listed = map(_answer, (made, added, listed))
    assert made["ok"]
    assert Path(made["data"]["path"]).is_file()
    assert Path(made["data"]["path"]).is_relative_to(workspace)
    assert added["ok"] and added["atoms_after"] == 1
    (row,) = listed["documents"]
    assert row["current"] and row["path"] == made["data"]["path"]


def test_build_tool_keeps_the_builders_own_answer(tmp_path):
    """The build's report -- what was built, how well the blocks fit,
    where the run is -- is what an assistant judges the framework by;
    an answer that only says a file was opened throws it away."""
    from xtal.mof import database_root, installed

    if database_root() is None or not installed():
        pytest.skip("the MOF builder needs ase and the PORMAKE database")

    async def conversation(client):
        built = await client.call_tool(
            "build", {"action": "mof.build",
                      "workspace": str(tmp_path / "ws"),
                      "params": {"topology": "pcu", "nodes": "N16",
                                 "edges": "E14"}})
        listed = await client.call_tool("documents", {})
        return built, listed

    built, listed = map(_answer, _talk(conversation))
    assert built["verb"] == "mof.build" and built["ok"]
    assert "pcu" in built["message"]
    assert Path(built["data"]["run"]).is_dir()
    (row,) = listed["documents"]
    assert row["current"] and row["atoms"] == built["atoms_after"]


def test_an_option_naming_a_parameter_is_an_error_not_an_override(
        rutile_cif):
    """``energy(engine="uff", **{"engine": "xtb"})`` is a TypeError in
    Python; through the tool it must not quietly pick one of the
    two."""
    async def conversation(client):
        await client.call_tool("open", {"path": rutile_cif})
        return await client.call_tool(
            "energy", {"engine": "uff", "options": {"engine": "xtb"}})

    result = _talk(conversation)
    assert result.isError
    assert "engine" in result.content[0].text


def test_opening_the_path_documents_lists_after_a_save_is_the_same_session(
        tmp_path, rutile_cif):
    """``documents`` lists where the session is now -- the workspace's
    copy, then the project a save wrote.  Opening that path must find
    the session, not read the file into a second one beside it."""
    async def conversation(client):
        await client.call_tool("open", {"path": rutile_cif,
                                        "workspace": str(tmp_path / "ws")})
        await client.call_tool(
            "add_atom", {"element": "O", "frac": [0.5, 0.5, 0.25]})
        await client.call_tool("save", {})
        (row,) = _answer(await client.call_tool("documents", {}))[
            "documents"]
        again = await client.call_tool("open", {"path": row["path"]})
        listed = await client.call_tool("documents", {})
        return row, again, listed

    row, again, listed = _talk(conversation)
    assert row["path"].endswith(".xtalproj")
    again, listed = _answer(again), _answer(listed)
    assert "already open" in again["message"]
    assert again["atoms_after"] == row["atoms"]
    assert len(listed["documents"]) == 1


def test_reopening_in_another_workspace_says_that_workspace_was_not_used(
        tmp_path, rutile_cif):
    """The file stays in the workspace it was opened into; an assistant
    that named another would look for its runs there."""
    async def conversation(client):
        await client.call_tool("open", {"path": rutile_cif,
                                        "workspace": str(tmp_path / "ws")})
        same = await client.call_tool(
            "open", {"path": rutile_cif, "workspace": str(tmp_path / "ws")})
        other = await client.call_tool(
            "open", {"path": rutile_cif,
                     "workspace": str(tmp_path / "other")})
        return same, other

    same, other = map(_answer, _talk(conversation))
    assert same["diagnostics"] == []
    (ignored,) = other["diagnostics"]
    assert ignored["code"] == "WORKSPACE_IGNORED"
    assert "is already open" in ignored["message"]
    assert str(tmp_path / "other") in ignored["message"]
