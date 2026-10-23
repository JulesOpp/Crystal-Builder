"""How a session's structure is drawn: ``view`` reads it, ``set_view``
changes it, and a headless render draws it.

A view change is view state, never chemistry: it is no undo step and
leaves the structure alone, it is all or nothing, and the project a
session saves carries it, as the window's does.  Everything here is
headless; the render is spied on, so no OpenGL is needed.
"""

import importlib
import subprocess
import sys

import pytest

from xtal.agent.session import Session
from xtal.io.project import read_project
from xtal.view import settings as view_settings

# The module and not the function the package exports under its name.
render_module = importlib.import_module("xtal.agent.render")


def _spy_on_render(monkeypatch):
    """The keywords each :meth:`Session.render` hands the renderer."""
    calls = []

    def render(structure, path, **kwargs):
        from xtal.agent.answers import VerbResult
        calls.append(kwargs)
        return VerbResult("render", True, f"wrote {path}")

    monkeypatch.setattr(render_module, "render", render)
    return calls


def test_view_gives_the_defaults_and_the_choices(rutile):
    """An assistant that cannot read the view sets it blind; one told
    no choices sends a style the panel does not have."""
    session = Session(rutile)
    answer = session.view()
    assert answer.ok, answer.message
    assert answer.data["view"] == view_settings.ViewSettings().to_dict()
    choices = answer.data["choices"]
    assert set(choices) == set(view_settings.VIEW_CHOICES)
    assert "polyhedra" in choices["style"]
    assert session.log[-1]["verb"] == "view"


def test_set_view_changes_the_view_and_says_what_it_was(rutile):
    """``was`` is what puts the view back in one call; without it an
    assistant asked to undo its restyling has nothing to send."""
    session = Session(rutile)
    default = session.view().data["view"]
    answer = session.set_view({"style": "polyhedra",
                               "show_rings": True})
    assert answer.ok, answer.message
    assert answer.data["changed"] == {"style": "polyhedra",
                                      "show_rings": True}
    assert answer.data["was"] == {"style": default["style"],
                                  "show_rings": default["show_rings"]}
    now = session.view().data["view"]
    assert now["style"] == "polyhedra" and now["show_rings"] is True
    assert session.set_view(answer.data["was"]).ok
    assert session.view().data["view"] == default


def test_a_view_change_is_no_undo_step_and_leaves_the_structure(rutile):
    """A style draws the structure and never changes it: a view change
    on the stack would be undone in place of the edit before it."""
    session = Session(rutile)
    before = (session.structure.n_sites, session.n_atoms)
    session.set_view({"style": "spacefill", "color_by": "coordination"})
    assert session.history() == []
    assert not session.modified
    assert (session.structure.n_sites, session.n_atoms) == before
    assert session.log[-1]["verb"] == "set_view"
    assert session.log[-1]["ok"] is True


def test_a_bad_setting_changes_nothing_and_is_refused_by_code(rutile):
    """All or nothing: the good half of a request applied without the
    bad half is a picture nobody asked for."""
    session = Session(rutile)
    before = session.view().data["view"]
    for request in ({"style": "polyhedra", "show_ringz": True},
                    {"style": "polyhedra", "ring_opacity": 7},
                    {"style": "watercolour"}):
        answer = session.set_view(request)
        assert not answer.ok
        assert [d.code for d in answer.diagnostics] == [
            "VIEW_SETTING_REFUSED"]
        assert answer.diagnostics[0].level == "error"
        assert session.view().data["view"] == before
    assert "did you mean show_rings" in session.set_view(
        {"show_ringz": True}).message


def test_an_empty_request_is_ok_and_changes_nothing(rutile):
    """An empty call is a no-op said as one; refused, an assistant
    that sends back an empty ``was`` would read an error for nothing
    done."""
    session = Session(rutile)
    answer = session.set_view({})
    assert answer.ok
    assert answer.message == "no view settings given"
    assert answer.data == {"changed": {}, "was": {}}


def test_a_view_change_is_not_counted_as_a_step(tmp_path):
    """The window says how many steps an assistant took on an entry;
    restyling counted there reads as edits the person must look for."""
    from xtal.agent.session import summarise_log

    log = tmp_path / "agent-session.jsonl"
    log.write_text('{"verb": "view", "ok": true}\n'
                   '{"verb": "set_view", "ok": true}\n',
                   encoding="utf-8")
    assert summarise_log(log) == (0, 0)


def test_a_callers_view_is_not_changed_by_set_view(rutile):
    """The view a session is opened with is the caller's own record;
    ``set_view`` writing into it changed a project read elsewhere."""
    given = {"style": "spacefill"}
    session = Session(rutile, view=given)
    assert session.set_view({"style": "polyhedra"}).ok
    assert given == {"style": "spacefill"}


def test_view_and_set_view_work_without_the_window(rutile, monkeypatch):
    """The record is the core's (``xtal.view``): a core-only install,
    with no ``xtalapp``, reads and changes the view.  It was refused
    there, naming the gui extra, while the record was the window's."""
    monkeypatch.setitem(sys.modules, "xtalapp", None)
    session = Session(rutile)
    for answer in (session.set_view({"style": "polyhedra"}),
                   session.view()):
        assert answer.ok, answer.message
    assert session.view().data["view"]["style"] == "polyhedra"


def test_a_saved_project_carries_the_view(tmp_path, rutile):
    """The window opens the project the assistant saved; a view left
    out of it is restyling the person never sees."""
    session = Session(rutile)
    session.set_view({"style": "polyhedra", "show_rings": True})
    path = session.save(tmp_path / "rutile.xtalproj")
    _structure, view, _session = read_project(path)
    loaded = view_settings.ViewSettings.from_dict(view)
    assert loaded.style == "polyhedra"
    assert loaded.show_rings is True


def test_render_is_handed_the_sessions_view(tmp_path, rutile,
                                            monkeypatch):
    """A headless picture drawn in another style than the one set is
    the assistant judging a picture the person will never see."""
    calls = _spy_on_render(monkeypatch)
    session = Session(rutile)
    session.render(tmp_path / "before.png")
    # None is the view's own: one default style, the record's.
    assert calls[-1]["style"] is None
    assert calls[-1]["show_cell"] is None
    session.set_view({"style": "polyhedra", "show_rings": True,
                      "show_cell": False})
    session.render(tmp_path / "after.png")
    assert calls[-1]["style"] is None
    assert calls[-1]["view_settings"]["style"] == "polyhedra"
    assert calls[-1]["view_settings"]["show_rings"] is True
    assert calls[-1]["view_settings"]["show_cell"] is False


def test_an_explicit_style_wins_for_that_render_only(tmp_path, rutile,
                                                     monkeypatch):
    """A style given to render is a look at one picture, not a change
    to how the tab is drawn."""
    calls = _spy_on_render(monkeypatch)
    session = Session(rutile)
    session.set_view({"style": "polyhedra", "show_cell": False})
    session.render(tmp_path / "x.png", style="spacefill",
                   show_cell=True)
    assert calls[-1]["style"] == "spacefill"
    assert calls[-1]["show_cell"] is True
    view = session.view().data["view"]
    assert (view["style"], view["show_cell"]) == ("polyhedra", False)
    session.render(tmp_path / "y.png")
    assert (calls[-1]["style"], calls[-1]["show_cell"]) == (None, None)


def test_the_render_project_carries_the_view(tmp_path, rutile,
                                             monkeypatch):
    """The view crosses to the subprocess in the scratch project, as
    the structure does; left out, the snapshot draws the defaults."""
    pytest.importorskip("vtkmodules")
    seen = []

    def runs(command, **kwargs):
        project = next(a for a in command if a.endswith(".xtalproj"))
        seen.append(read_project(project)[1])
        return subprocess.CompletedProcess(command, -11, "", "")

    monkeypatch.setattr(render_module.subprocess, "run", runs)
    render_module.render(rutile, tmp_path / "x.png",
                         view_settings={"show_rings": True,
                                        "range_c": [0.0, 2.0]})
    assert seen[0]["show_rings"] is True
    assert seen[0]["range_c"] == [0.0, 2.0]


def test_the_snapshot_draws_with_the_projects_view():
    """The snapshot built a fresh ViewSettings from the style alone,
    so rings, colour by and display ranges never reached a picture."""
    snapshot = pytest.importorskip("xtalapp.viewport.snapshot")
    view = {"style": "polyhedra", "show_cell": False,
            "show_rings": True}
    settings = snapshot.settings_for(view, {"style": None,
                                            "show_cell": None})
    assert settings.style == "polyhedra"
    assert settings.show_cell is False
    assert settings.show_rings is True
    # The record's own default, the one view() reports.
    assert snapshot.settings_for(None, {"style": None,
                                        "show_cell": None}).style \
        == view_settings.ViewSettings().style
    settings = snapshot.settings_for(
        {"style": "polyhedra", "show_rings": True,
         "color_by": "coordination", "range_c": [0.0, 2.0]},
        {"style": "spacefill", "show_cell": False})
    assert settings.style == "spacefill"
    assert settings.show_cell is False
    assert settings.show_rings is True
    assert settings.color_by == "coordination"
    assert settings.range_c == (0.0, 2.0)
    assert snapshot.settings_for(None, {"style": "ball_stick",
                                        "show_cell": True}).style \
        == "ball_stick"


def test_a_background_set_by_hand_says_it_no_longer_follows_the_theme(
        rutile):
    """``was`` must put the view back as it was: a background sent
    back without the theme flag would stay pinned after the undoing
    call."""
    session = Session(rutile, view={"background_follows_theme": True})
    answer = session.set_view({"background": [10, 20, 30]})
    assert answer.ok, answer.message
    assert answer.data["changed"]["background_follows_theme"] is False
    assert answer.data["was"]["background_follows_theme"] is True
    assert session.set_view(answer.data["was"]).ok
    assert session.view().data["view"]["background_follows_theme"] \
        is True
