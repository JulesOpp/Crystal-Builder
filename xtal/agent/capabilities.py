"""
xtal.agent.capabilities
=======================
What *this* install can do, asked rather than remembered.

An agent that quotes an engine from memory will name one whose extra
is not installed, or a parameter that was renamed last month.  So the
skill says: call :func:`capabilities` before the first calculation and
:func:`help_for` before the first call of anything unfamiliar.  Both
read the registries the window and the CLI read, so there is no third
list to drift.
"""

from __future__ import annotations

import inspect as pyinspect
from importlib.util import find_spec

from xtal.agent.diagnostics import to_json

#: The public verbs of a session, in the order the skill teaches them.
VERBS = (
    "open", "new", "build", "inspect", "render",
    "add_atom", "delete_sites", "set_element", "move_sites",
    "set_cell", "supercell", "reduce_to_p1", "find_symmetry",
    "standardize", "set_space_group", "merge_duplicates",
    "recalculate_bonds", "add_bond", "remove_bond", "set_bond_type",
    "add_hydrogens", "prepare", "interpenetrate",
    "energy", "optimize", "run",
    "undo", "redo", "save", "export",
)


def _param(p) -> dict:
    row = {"name": p.name, "kind": p.kind,
           "default": _plain(p.default_value()), "title": p.title}
    if p.choices:
        row["choices"] = [_plain(v) for v, _label in
                          p.values_and_labels()]
    if p.help:
        row["help"] = p.help
    return row


def _plain(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return str(value)


class Capabilities(dict):
    """A dict (so ``json.dumps`` takes it) that prints readably."""

    def to_json(self) -> str:
        return to_json(dict(self))

    def __str__(self) -> str:
        lines = ["engines:"]
        for e in self["engines"]:
            mark = "" if e["available"] else f"  [no: {e['reason']}]"
            lines.append(f"  {e['name']:<10s} {e['label']}{mark}")
        lines.append("modules:")
        for m in self["modules"]:
            for a in m["actions"]:
                mark = "" if a["available"] else \
                    f"  [no: {a['reason']}]"
                lines.append(f"  {a['action']:<24s} {a['label']}{mark}")
        lines.append("render: " + ("yes" if self["render"]["available"]
                                   else f"no -- {self['render']['reason']}"))
        lines.append("verbs: " + ", ".join(self["verbs"]))
        return "\n".join(lines)


def capabilities() -> Capabilities:
    """Every engine and module action, and whether it can run here."""
    from xtal import __version__, plugins
    from xtal.ff import ENGINES
    from xtal.modules import MODULES

    plugins.load()
    engines = []
    for engine in ENGINES:
        available = engine.availability()
        engines.append({
            "name": engine.name, "label": engine.label,
            "available": bool(available), "reason": available.reason,
            "options": [_param(p) for p in engine.options]})
    modules = []
    for module in MODULES:
        module_ok = module.availability()
        actions = []
        for action in module.actions:
            available = module_ok and action.availability()
            if action.run is None:
                available_ok, reason = False, "performed by the window"
            else:
                available_ok = bool(available)
                reason = "" if available_ok else (
                    getattr(available, "reason", "")
                    or module_ok.reason)
            actions.append({
                "action": f"{module.name}.{action.name}",
                "label": action.label,
                "needs_structure": action.needs_structure,
                "available": available_ok, "reason": reason,
                "params": [_param(p) for p in action.params]})
        modules.append({"name": module.name, "label": module.label,
                        "actions": actions})
    return Capabilities(
        version=__version__, verbs=list(VERBS), engines=engines,
        modules=modules, render=render_availability())


def render_availability() -> dict:
    """Whether :func:`xtal.agent.render.render` can draw here.

    ``find_spec`` and never an import: VTK is the ``gui`` extra, and
    asking must not load it.  Whether an OpenGL context can actually
    be made is only known by trying, which ``render`` does.
    """
    if find_spec("vtkmodules") is None:
        from xtal.install import command
        return {"available": False,
                "reason": f"rendering needs the gui extra: "
                          f"{command('gui')}"}
    return {"available": True, "reason": ""}


def help_for(name: str) -> str:
    """What a verb takes, or what a module action or engine takes.

    ``help_for("add_atom")``, ``help_for("zeopp.pores")``,
    ``help_for("uff")``.
    """
    from xtal.agent.session import Session

    if name in VERBS:
        target = getattr(Session, name)
        signature = pyinspect.signature(target)
        doc = pyinspect.getdoc(target) or ""
        return f"Session.{name}{signature}\n\n{doc}"
    found = capabilities()
    for engine in found["engines"]:
        if engine["name"] == name:
            return _describe(f"engine {name}: {engine['label']}",
                             engine["options"], engine)
    for module in found["modules"]:
        for action in module["actions"]:
            if action["action"] == name:
                return _describe(f"{name}: {action['label']}",
                                 action["params"], action)
    raise KeyError(f"nothing called {name!r}: a verb "
                   f"({', '.join(VERBS)}), an engine or a module action "
                   f"(capabilities() lists them)")


def _describe(head, params, row) -> str:
    lines = [head]
    if not row["available"]:
        lines.append(f"unavailable here: {row['reason']}")
    for p in params:
        choices = (f" one of {p['choices']}" if "choices" in p else "")
        lines.append(f"  {p['name']}={p['default']!r}  ({p['kind']}"
                     f"{choices}) {p['title']}")
        if "help" in p:
            lines.append(f"      {p['help']}")
    if not params:
        lines.append("  (no parameters)")
    return "\n".join(lines)
