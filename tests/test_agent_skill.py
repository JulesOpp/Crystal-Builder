"""The shipped skill, held to the code it describes.

A skill that names a verb, a parameter or a diagnostic this version
does not have is worse than none: the agent believes it, calls it, and
reads the resulting error as the structure's fault.  So every name in
``SKILL.md`` and ``references/`` is checked here against the installed
package, as rietx checks its own.
"""

import inspect as pyinspect
import re
import tomllib
from pathlib import Path

import pytest

from xtal import cli, plugins
from xtal.agent import skill
from xtal.agent.capabilities import VERBS
from xtal.agent.diagnostics import CODES
from xtal.agent.session import Session

ROOT = skill.source()
PAGES = {str(name): (ROOT / name).read_text(encoding="utf-8")
         for name in skill.shipped_files()}
ALL_TEXT = "\n".join(PAGES.values())

REFERENCES = ("api.md", "diagnostics.md", "prepare.md", "mof.md",
              "calculations.md", "porosity.md", "workspace.md")


def _actions() -> dict:
    from xtal.modules import MODULES

    plugins.load()
    return {f"{m.name}.{a.name}": a for m in MODULES for a in m.actions}


def _parameters(function) -> tuple[set, bool]:
    """Named parameters, and whether it takes ``**kwargs``."""
    signature = pyinspect.signature(function)
    names = {p.name for p in signature.parameters.values()
             if p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
             and p.name not in ("self", "cls")}
    open_ended = any(p.kind is p.VAR_KEYWORD
                     for p in signature.parameters.values())
    return names, open_ended


def test_the_skill_ships_in_the_package_data():
    names = {str(n) for n in skill.shipped_files()}
    assert "SKILL.md" in names
    assert {f"references/{r}" for r in REFERENCES} <= names
    config = tomllib.loads(Path("pyproject.toml").read_text())
    tool = config["tool"]["setuptools"]
    assert "xtal.agent.skill" in tool["packages"]
    assert tool["package-data"]["xtal.agent.skill"] == [
        "SKILL.md", "references/*.md"]


def test_the_skill_has_the_frontmatter_an_assistant_reads():
    head = PAGES["SKILL.md"].split("---")[1]
    assert re.search(r"^name: crystal-builder$", head, re.MULTILINE)
    assert "description:" in head


def test_every_reference_the_skill_names_is_shipped():
    named = set(re.findall(r"references/([\w-]+\.md)", PAGES["SKILL.md"]))
    assert named == set(REFERENCES)


def test_every_verb_the_skill_names_exists_with_that_signature():
    """api.md has one heading per verb, with its parameter names; the
    two lists and every signature must agree."""
    headings = re.findall(r"^### `(\w+)\(([^)]*)\)`", PAGES[
        "references/api.md"], re.MULTILINE)
    assert [name for name, _ in headings] == list(VERBS)
    for name, written in headings:
        named = {w.strip().lstrip("*") for w in written.split(",")
                 if w.strip() and not w.strip().startswith("**")}
        actual, _ = _parameters(getattr(Session, name))
        assert named == actual, name


def test_every_call_the_skill_shows_uses_real_keywords():
    """``s.optimize(engine="uff", max_steps=500)`` in an example is a
    promise that those keywords exist."""
    calls = re.findall(r"\b(?:s|Session)\.(\w+)\(([^()]*)\)", ALL_TEXT)
    assert calls, "the skill should show calls"
    for name, arguments in calls:
        assert hasattr(Session, name), name
        method = getattr(Session, name)
        if not callable(method):
            continue
        actual, open_ended = _parameters(method)
        for keyword in re.findall(r"(\w+)=", arguments):
            assert keyword in actual or open_ended, f"{name}({keyword}=)"


def test_every_module_action_the_skill_names_exists():
    known = _actions()
    prefixes = {name.split(".")[0] for name in known}
    named = {m for m in re.findall(r"`([a-z]+\.[a-z-]+)`", ALL_TEXT)
             if m.split(".")[0] in prefixes and not m.endswith(".md")}
    named |= set(re.findall(r'(?:run|build)\("([a-z]+\.[a-z-]+)"',
                            ALL_TEXT))
    assert named, "the skill should name module actions"
    missing = sorted(named - set(known))
    assert not missing, missing


def test_every_module_parameter_the_skill_passes_exists():
    known = _actions()
    for action, arguments in re.findall(
            r'(?:run|build)\("([a-z]+\.[a-z-]+)",?([^)]*)\)', ALL_TEXT):
        params = {p.name for p in known[action].params}
        for keyword in re.findall(r"(\w+)=", arguments):
            assert keyword in params, f"{action}: {keyword}"


def test_every_diagnostic_code_is_documented_and_no_other_is():
    table = set(re.findall(r"^\| `([A-Z_]+)` \|",
                           PAGES["references/diagnostics.md"],
                           re.MULTILINE))
    assert table == set(CODES)
    for code, known in CODES.items():
        assert known.suggestion in PAGES["references/diagnostics.md"], \
            f"{code}'s suggestion is not the documented one"


def test_every_code_the_prose_mentions_is_a_real_code():
    mentioned = set(re.findall(r"`([A-Z][A-Z_]{4,})`", ALL_TEXT))
    not_codes = {"DFTB_PREFIX", "XTAL_ZEOPP"}
    assert mentioned - not_codes <= set(CODES), \
        sorted(mentioned - not_codes - set(CODES))


def test_every_xtal_command_the_skill_shows_exists():
    parser = cli.build_parser()
    commands = set(parser._subparsers._group_actions[0].choices)
    shown = set(re.findall(r"^xtal (\w+)", ALL_TEXT, re.MULTILINE))
    shown |= set(re.findall(r"`xtal (\w+)", ALL_TEXT))
    assert shown and shown <= commands, sorted(shown - commands)


def test_skill_install_writes_to_the_directory_it_was_given(tmp_path):
    target = skill.install(project=tmp_path)
    assert target == tmp_path / ".claude" / "skills" / "crystal-builder"
    assert (target / "SKILL.md").read_text() == PAGES["SKILL.md"]
    assert (target / "references" / "api.md").exists()


def test_installing_twice_is_harmless_and_an_edited_copy_is_kept(
        tmp_path):
    """A person's edits to their installed skill are not replaced in
    silence; --force is how they ask for that."""
    target = skill.install(project=tmp_path)
    skill.install(project=tmp_path)                 # identical: fine
    edited = target / "SKILL.md"
    edited.write_text("my own notes")
    with pytest.raises(FileExistsError):
        skill.install(project=tmp_path)
    assert edited.read_text() == "my own notes"
    skill.install(project=tmp_path, force=True)
    assert edited.read_text() == PAGES["SKILL.md"]


def test_skill_install_from_the_command_line(tmp_path, capsys):
    assert cli.main(["skill", "install", "--project",
                     str(tmp_path)]) == 0
    assert "crystal-builder" in capsys.readouterr().out
    assert cli.main(["skill", "path"]) == 0
    assert Path(capsys.readouterr().out.strip()) == ROOT
