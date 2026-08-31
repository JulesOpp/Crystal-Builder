"""
xtal.modules.registry
=====================
What can be run, as data rather than as menu items.

The menu bar had ``Calculate``, holding a single point, an
optimisation and a panel toggle -- three entries that were all UFF, in
a menu whose name promised everything that computes.  Every engine
after it (DFTB+, Zeo++, PXRD) would have gone into the same flat list,
and each would have arrived as a new menu item, a new dialog and a new
worker written by hand.

So a module is a registry entry::

    MODULES.register(Module(
        name="zeopp", label="Zeo++",
        actions=(Action(name="pore-diameter", label="Pore diameter...",
                        params=(Param("radii", "Radii file",
                                      kind="path"),),
                        run=zeo.pore_diameter),),
        check=lambda: NETWORK.availability()))

and the menu, the dock, the parameter form, the worker thread, the run
folder and the cancel button are all built from that.  Adding an engine
touches no existing file, which is the whole point of Phase D.

Four decisions hold this up.

**A module declares, it does not draw.**  Nothing here imports Qt, and
:class:`Param` describes a value rather than a widget -- so the same
declaration renders into a Qt form, prints as ``--help``, and is
checked by a headless test.  What a ``float`` looks like on screen is
the shell's business.

**The declaration is deliberately small.**  Three modules is not
enough to know what the fourth needs: there is no layout, no
conditional enabling, no validation language and no result schema
beyond "a message, and optionally a structure".  Each of those is
cheap to add against a real module that wants it and expensive to
remove once something depends on the shape.

**An action is what appears in the tree**, not a module.  ``Forcefield``
is one module with three entries because those three entries are what
a user picks between; a module with one action shows one leaf.

**A module runs something and leaves artefacts behind.**  That is the
line between this registry and the ``Symmetry``, ``Cell`` and
``Structure`` menus, which edit the structure in place and stay where
they are.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

#: The kinds a :class:`Param` can be.  Every one of them has an
#: obvious widget, an obvious command-line spelling and an obvious
#: default -- which is the test a fifth kind has to pass.
KINDS = ("bool", "int", "float", "choice", "text", "path")


class ModuleError(ValueError):
    """A module was asked for something it cannot do."""


# ======================================================================
#  PARAMETERS
# ======================================================================

@dataclass(frozen=True)
class Param:
    """One value a module needs before it can run.

    The form is generated from a list of these rather than hand-built,
    so a module that grows an option grows a line and not a dialog.
    """

    name: str                       # "steps"
    label: str = ""                 # "Number of steps"
    kind: str = "float"
    default: Any = None
    #: For ``choice``: either plain values, or ``(value, label)``
    #: pairs when what the user reads is not what the module wants.
    choices: tuple = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    decimals: int = 3
    suffix: str = ""
    help: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ModuleError(
                f"{self.name}: unknown parameter kind {self.kind!r}; "
                f"have {', '.join(KINDS)}")

    @property
    def title(self) -> str:
        return self.label or self.name.replace("_", " ").capitalize()

    def values_and_labels(self) -> list[tuple[Any, str]]:
        """``choices`` as ``(value, label)``, however it was written."""
        out = []
        for choice in self.choices:
            if isinstance(choice, tuple | list) and len(choice) == 2:
                out.append((choice[0], str(choice[1])))
            else:
                out.append((choice, str(choice)))
        return out

    def default_value(self) -> Any:
        """What this parameter is when nobody has said otherwise."""
        if self.default is not None:
            return self.default
        if self.kind == "bool":
            return False
        if self.kind == "int":
            return int(self.minimum or 0)
        if self.kind == "float":
            return float(self.minimum or 0.0)
        if self.kind == "choice":
            pairs = self.values_and_labels()
            return pairs[0][0] if pairs else None
        return ""

    def coerce(self, value) -> Any:
        """Turn whatever arrived into what this parameter is.

        A dialog hands back the right type already; a command line and
        a saved session hand back strings.  Clamping rather than
        refusing is deliberate for the numeric kinds: a spinbox cannot
        produce an out-of-range value, so one that arrives came from a
        script, and stopping a run over it helps nobody.
        """
        if value is None:
            return self.default_value()
        if self.kind == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes",
                                                 "on")
            return bool(value)
        if self.kind in ("int", "float"):
            number = int(float(value)) if self.kind == "int" \
                else float(value)
            if self.minimum is not None:
                number = max(number, type(number)(self.minimum))
            if self.maximum is not None:
                number = min(number, type(number)(self.maximum))
            return number
        if self.kind == "choice":
            allowed = [v for v, _ in self.values_and_labels()]
            if value in allowed:
                return value
            for candidate in allowed:
                if str(candidate) == str(value):
                    return candidate
            raise ModuleError(
                f"{self.name}: {value!r} is not one of "
                f"{', '.join(str(a) for a in allowed)}")
        return str(value)


def defaults(params) -> dict:
    """Every parameter at its default, as a plain dict."""
    return {p.name: p.default_value() for p in params}


def coerce(params, values: dict | None) -> dict:
    """Fill in what was not given and type what was.

    Unknown keys are dropped rather than passed through: they are
    almost always a stale saved value or a typo in a script, and a
    module that received one would have to guess what to do with it.
    """
    given = dict(values or {})
    return {p.name: p.coerce(given.get(p.name)) for p in params}


# ======================================================================
#  MODULES AND THEIR ACTIONS
# ======================================================================

@dataclass(frozen=True)
class Availability:
    """Whether a module can run at all, and why not when it cannot.

    An external tool that is missing is the most common state it will
    be in, so the answer carries a sentence a user can act on rather
    than a bare false.
    """

    ok: bool = True
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class Action:
    """One entry under a module: the thing a user actually picks.

    ``run`` is a callable taking a :class:`~xtal.modules.job.Job` and
    returning a :class:`~xtal.modules.job.JobResult`.  It runs on a
    worker thread, knows nothing about the window, and is the same
    callable the CLI invokes -- which is what keeps a module testable
    without a display.

    ``shell`` is the exception, and it exists for exactly one reason:
    the Force Field panel predates this registry and does things a
    generic runner cannot (a live plot, a preview that moves the
    atoms, one undoable command at the end).  An action with a
    ``shell`` name is performed by the window's action of that name,
    so those three entries moved into the Modules menu unchanged
    rather than being rewritten to fit.  A new module has no business
    using it.
    """

    name: str                       # "single-point", unique per module
    label: str                      # "Single point energy"
    tip: str = ""
    shortcut: Any = None            # a key, or a list of equivalents
    params: tuple[Param, ...] = ()
    run: Callable | None = None     # (Job) -> JobResult
    shell: str = ""                 # the window performs it instead
    #: Whether the run folder is opened before ``run`` is called.  A
    #: module that only reads (a validity check, a table) has nothing
    #: to leave behind and should not litter the workspace with empty
    #: folders.
    writes_run_folder: bool = True
    #: The middle word of the run folder's name, when it is not the
    #: action's own.
    kind: str = ""
    #: Whether it needs a structure open.  Everything does today; a
    #: module that fetches or builds one would not.
    needs_structure: bool = True

    def __post_init__(self):
        if self.run is None and not self.shell:
            raise ModuleError(
                f"{self.name}: an action needs either a run callable "
                f"or the name of a shell action to defer to")

    @property
    def run_kind(self) -> str:
        return self.kind or self.name

    def defaults(self) -> dict:
        return defaults(self.params)

    def coerce(self, values: dict | None) -> dict:
        return coerce(self.params, values)


@dataclass(frozen=True)
class Module:
    """One thing that can be run, and everything about it."""

    name: str                       # "forcefield"
    label: str                      # "Forcefield"
    description: str = ""
    actions: tuple[Action, ...] = ()
    #: What to check before offering it -- typically that a binary is
    #: installed.  Called every time the tree is rebuilt, so it has to
    #: be cheap; ``shutil.which`` is the intended cost.
    check: Callable[[], Availability] | None = None
    #: Where it sits in the tree.  Forcefield is 10 because it is the
    #: one that was there before there was a tree.
    order: int = 100
    provides: frozenset = field(default_factory=frozenset)

    def availability(self) -> Availability:
        if self.check is None:
            return Availability(True)
        try:
            return self.check()
        except Exception as exc:                    # noqa: BLE001
            # A broken check must not take the menu with it: the
            # module is simply unavailable, and says why.
            return Availability(False, str(exc))

    def action(self, name: str) -> Action:
        for action in self.actions:
            if action.name == name:
                return action
        raise ModuleError(
            f"{self.name} has no action {name!r}; have "
            f"{', '.join(a.name for a in self.actions) or 'none'}")

    def __contains__(self, name: str) -> bool:
        return any(a.name == name for a in self.actions)

    def __iter__(self):
        return iter(self.actions)


class ModuleRegistry:
    """Name -> :class:`Module`, in the order the tree shows them."""

    def __init__(self):
        self._modules: dict[str, Module] = {}

    def register(self, module: Module) -> Module:
        self._modules[module.name] = module
        return module

    def unregister(self, name: str) -> None:
        """Take one out again.

        Here for tests and for a plugin that fails to load half way:
        a registry that can only grow leaks between test cases.
        """
        self._modules.pop(name, None)

    def __contains__(self, name: str) -> bool:
        return name in self._modules

    def __len__(self) -> int:
        return len(self._modules)

    def __iter__(self):
        return iter(sorted(self._modules.values(),
                           key=lambda m: (m.order, m.label)))

    def get(self, name: str) -> Module:
        try:
            return self._modules[name]
        except KeyError:
            raise ModuleError(
                f"unknown module: {name!r}; have "
                f"{', '.join(sorted(self._modules)) or 'none'}"
            ) from None

    def names(self) -> list[str]:
        return [m.name for m in self]

    def find(self, path: str) -> tuple[Module, Action]:
        """``"forcefield.optimise"`` -> the module and the action.

        One string names an action everywhere: in the CLI, in a saved
        session, in a keyboard shortcut and in a test.
        """
        module_name, _, action_name = str(path).partition(".")
        module = self.get(module_name)
        if not action_name:
            raise ModuleError(
                f"{path!r} names a module but not one of its actions "
                f"({', '.join(a.name for a in module.actions)})")
        return module, module.action(action_name)

    def paths(self) -> list[str]:
        """Every ``module.action`` there is, for a help message."""
        return [f"{m.name}.{a.name}" for m in self for a in m.actions]


MODULES = ModuleRegistry()
