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
from xtal.params import Availability

#: The public verbs of a session, in the order the skill teaches them.
VERBS = (
    "open", "new", "build", "inspect", "render", "select",
    "add_atom", "delete_sites", "set_element", "move_sites",
    "set_cell", "supercell", "slab", "reduce_to_p1", "find_symmetry",
    "standardize", "set_space_group", "merge_duplicates",
    "recalculate_bonds", "add_bond", "remove_bond", "set_bond_type",
    "add_hydrogens", "substitute", "fill_pores", "place_molecule",
    "prepare", "interpenetrate",
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
        return to_json(dict(self), compact=True)

    def __str__(self) -> str:
        lines = ["engines:"]
        for e in self["engines"]:
            mark = "" if e["available"] else f"  [no: {e['reason']}]"
            lines.append(f"  {e['name']:<10s} {e['label']}{mark}")
        lines.append("modules:")
        if "modules" in self:
            actions = [{**a, "name": a["action"]}
                       for m in self["modules"] for a in m["actions"]]
        else:
            actions = self["actions"]
        for a in actions:
            mark = "" if a["available"] else f"  [no: {a['reason']}]"
            lines.append(f"  {a['name']:<24s} {a['label']}{mark}")
        lines.append("render: " + ("yes" if self["render"]["available"]
                                   else f"no -- {self['render']['reason']}"))
        lines.append("verbs: " + ", ".join(self["verbs"]))
        return "\n".join(lines)


def capabilities(verbose: bool = False) -> Capabilities:
    """Every engine and module action, and whether it can run here.

    Each is a ``name``, ``label``, ``available`` and its ``reason``
    without the install command, with the module actions as one list,
    ``actions``: the command is the same for every action of a missing
    extra, and nine pxrd actions repeated it into most of the answer.
    ``verbose`` is the whole reason and every option and parameter with
    its help as well, under ``modules`` -- 127 kB, which
    :func:`help_for` gives one name at a time.  An action only the
    window performs is in neither: it is a verb here.
    """
    from xtal import __version__, plugins
    from xtal.ff import ENGINES
    from xtal.modules import MODULES

    plugins.load()
    engines = []
    for engine in ENGINES:
        row = {"name": engine.name, "label": engine.label,
               **_state(engine.availability(), verbose)}
        if verbose:
            row["options"] = [_param(p) for p in engine.options]
        engines.append(row)
    modules, compact = [], []
    for module in MODULES:
        module_ok = module.availability()
        actions = []
        for action in module.actions:
            if action.run is None:
                continue
            available = module_ok and action.availability()
            why = (Availability(True) if available else available
                   if getattr(available, "reason", "") else module_ok)
            name = f"{module.name}.{action.name}"
            compact.append({"name": name, "label": action.label,
                            "available": bool(available),
                            "reason": why.what})
            actions.append({
                "action": name, "label": action.label,
                "needs_structure": action.needs_structure,
                "available": bool(available), "reason": why.reason,
                "params": [_param(p) for p in action.params]})
        modules.append({"name": module.name, "label": module.label,
                        "actions": actions})
    render = _state(render_availability(), verbose)
    if not verbose:
        return Capabilities(
            version=__version__, verbs=list(VERBS), engines=engines,
            actions=compact, render=render)
    return Capabilities(
        version=__version__, verbs=list(VERBS), engines=engines,
        modules=modules, render=render)


def _state(available: Availability, verbose: bool) -> dict:
    return {"available": bool(available),
            "reason": available.reason if verbose else available.what}


def render_availability() -> Availability:
    """Whether :func:`xtal.agent.render.render` can draw here.

    ``find_spec`` and never an import: VTK is the ``gui`` extra, and
    asking must not load it.  Whether an OpenGL context can actually
    be made is only known by trying, which ``render`` does.
    """
    if find_spec("vtkmodules") is None:
        from xtal.install import command
        return Availability(False, "rendering needs the gui extra",
                            command("gui"), ": ")
    return Availability(True)


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
    found = capabilities(verbose=True)
    for engine in found["engines"]:
        if engine["name"] == name:
            return _describe(f"engine {name}: {engine['label']}",
                             engine["options"], engine)
    for module in found["modules"]:
        for action in module["actions"]:
            if action["action"] == name:
                return _describe(f"{name}: {action['label']}",
                                 action["params"], action)
    window = _window_action(name)
    if window is not None:
        return window
    raise KeyError(f"nothing called {name!r}: a verb "
                   f"({', '.join(VERBS)}), an engine or a module action "
                   f"(capabilities() lists them)")


#: The verb that does what a window-only action does, by action name.
_WINDOW_VERBS = {"optimise": "optimize", "single-point": "energy"}


def _window_action(name: str) -> str | None:
    """:func:`help_for` of an action only the window performs.

    The listings leave these out because a verb covers them, but the
    name is in the window's menus and in run logs, and an assistant
    that asks about it is better told which verb than that nothing
    is called that.
    """
    from xtal.modules import MODULES

    for module in MODULES:
        for action in module.actions:
            if (f"{module.name}.{action.name}" != name
                    or action.run is not None):
                continue
            reason = "performed by the window"
            verb = _WINDOW_VERBS.get(action.name)
            if verb:
                reason += f"; use the `{verb}` verb"
            return _describe(f"{name}: {action.label}",
                             [_param(p) for p in action.params],
                             {"available": False, "reason": reason})
    return None


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
