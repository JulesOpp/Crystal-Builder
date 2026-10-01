"""Answers a model can hold: what an assistant reads first is sized for
its context, and nothing a person needs is lost to get there.

MOF-5 is 424 sites in P1.  Every site row and every parameter's help
in one answer was 172 kB and 127 kB, and an assistant that reads them
has spent its context before it has done anything.
"""

import json

from xtal import cli, plugins
from xtal.agent.capabilities import capabilities, help_for
from xtal.agent.inspect import inspect
from xtal.io import FORMATS

MOF5 = "resources/samples/MOF-5.cif"


def test_mof5_inspection_json_is_under_five_kilobytes():
    found = inspect(FORMATS.read(MOF5))
    assert found.n_sites == 424
    assert len(found.to_json()) < 5000


def test_capabilities_json_is_under_six_kilobytes():
    """Measured on a checkout where most extras are missing, which is
    the large case: every unavailable row carries a reason."""
    assert len(capabilities().to_json()) < 6000


def test_a_compact_reason_carries_no_command_and_verbose_does(
        monkeypatch):
    """The install command is the same for every action of a missing
    extra and, on a source checkout, a long path: nine pxrd actions
    repeated it into most of the compact answer.  ``verbose`` and
    ``help_for`` still say how to get it, and so does rendering's."""
    import importlib

    from xtal.ff import ENGINES
    from xtal.params import Availability

    module = importlib.import_module("xtal.agent.capabilities")
    pip = "uv pip install crystal-builder[{}]"
    reasons = {
        "mace": Availability(False, "MACE is not installed",
                             pip.format("mace")),
        "xtb": Availability(False, "Refinement needs RietX",
                            pip.format("refine"), ": "),
    }
    engine_type = type(ENGINES.get("mace"))
    real = engine_type.availability

    def availability(self, **options):
        if self.name in reasons:
            return reasons[self.name]
        return real(self, **options)

    monkeypatch.setattr(engine_type, "availability", availability)
    monkeypatch.setattr(module, "find_spec", lambda name: None)
    compact = capabilities()
    verbose = capabilities(verbose=True)
    engines = {e["name"]: e for e in compact["engines"]}
    full = {e["name"]: e for e in verbose["engines"]}
    for name, available in reasons.items():
        assert not engines[name]["available"]
        assert engines[name]["reason"] == available.what
        assert full[name]["reason"] == available.reason
        assert available.command not in compact.to_json()
    assert compact["render"] == {
        "available": False, "reason": "rendering needs the gui extra"}
    assert verbose["render"]["reason"].startswith(
        "rendering needs the gui extra: ")
    assert verbose["render"]["reason"] != compact["render"]["reason"]


def test_verbose_capabilities_still_carry_every_parameter(capsys):
    """The compact answer says what can run; ``--verbose`` is still
    where every option and parameter is, or an assistant has nowhere
    to read a default from."""
    from xtal.ff import ENGINES
    from xtal.modules import MODULES

    cli.main(["capabilities", "--json", "--verbose"])
    document = json.loads(capsys.readouterr().out)
    engines = {e["name"]: [p["name"] for p in e["options"]]
               for e in document["engines"]}
    assert engines == {e.name: [p.name for p in e.options]
                       for e in ENGINES}
    plugins.load()
    actions = {a["action"]: [p["name"] for p in a["params"]]
               for m in document["modules"] for a in m["actions"]}
    assert actions == {f"{m.name}.{a.name}": [p.name for p in a.params]
                       for m in MODULES for a in m.actions
                       if a.run is not None}


def test_actions_the_window_performs_are_not_listed():
    """``forcefield.optimise`` is ``optimize``: listing it unavailable
    sends an assistant looking for a way to run it that it already
    has."""
    from xtal.modules import MODULES

    plugins.load()
    window = {f"{m.name}.{a.name}" for m in MODULES for a in m.actions
              if a.run is None}
    assert "forcefield.optimise" in window
    compact = {a["name"] for a in capabilities()["actions"]}
    verbose = {a["action"] for m in capabilities(verbose=True)["modules"]
               for a in m["actions"]}
    assert compact and verbose
    assert not window & (compact | verbose)


def test_help_for_still_describes_an_action_the_window_performs():
    """Left out of the listings, but an assistant that meets the name
    (in a log, in the window's menus) must still be told what it is
    and which verb does it, not that it does not exist."""
    from xtal.modules import MODULES

    plugins.load()
    _module, action = MODULES.find("forcefield.optimise")
    described = help_for("forcefield.optimise")
    assert "performed by the window" in described
    assert "optimize" in described
    assert "(no parameters)" in described
    assert "energy" in help_for("forcefield.single-point")
