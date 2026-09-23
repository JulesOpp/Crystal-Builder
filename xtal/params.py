"""
xtal.params
===========
A value a thing needs before it can run, described rather than drawn.

This started inside the module registry, where it was
``Module ▸ Action ▸ Param`` and nothing else needed it.  DFTB+ is what
moved it out: it is an *engine*, not a module -- it goes behind
:class:`xtal.ff.api.Calculator` so that the optimiser, the worker
thread and the Force Field panel drive it exactly as they drive UFF --
and it still has a parameter set, a Hamiltonian, a k-point mesh and a
filling temperature that have to be asked for.  Those are the same
kind of thing a module's parameters are, they want the same generated
form, and duplicating the declaration for engines would have meant two
of everything: two kinds of ``Param``, two form builders, two coercion
rules.

So the declaration lives here, in neither package, and
:mod:`xtal.modules.registry` and :mod:`xtal.ff.registry` both use it.
:class:`Availability` moved for the same reason: "installed, or here
is why not" is the answer an external tool gives whether it is reached
as a module or as an engine.

Nothing here imports Qt.  A :class:`Param` describes a value, not a
widget -- so the same declaration renders into a Qt form, prints as
``--help``, and is checked by a headless test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The kinds a :class:`Param` can be.  Every one of them has an
#: obvious widget, an obvious command-line spelling and an obvious
#: default -- which is the test a sixth kind has to pass.
KINDS = ("bool", "int", "float", "choice", "text", "path")


class ParamError(ValueError):
    """A parameter was declared or given something it cannot be.

    :data:`xtal.modules.registry.ModuleError` is this class under
    another name, so code that has always caught one goes on catching
    both.
    """


@dataclass(frozen=True)
class Param:
    """One value a module or an engine needs before it can run.

    The form is generated from a list of these rather than hand-built,
    so a thing that grows an option grows a line and not a dialog.
    """

    name: str                       # "steps"
    label: str = ""                 # "Number of steps"
    kind: str = "float"
    default: Any = None
    #: For ``choice``: either plain values, or ``(value, label)``
    #: pairs when what the user reads is not what the caller wants.
    choices: tuple = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    decimals: int = 3
    suffix: str = ""
    help: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ParamError(
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
            raise ParamError(
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
    caller that received one would have to guess what to do with it.
    """
    given = dict(values or {})
    return {p.name: p.coerce(given.get(p.name)) for p in params}


# ======================================================================
#  WHETHER IT CAN RUN AT ALL
# ======================================================================

@dataclass(frozen=True)
class Availability:
    """Whether something can run, and why not when it cannot.

    An external tool that is missing is the most common state it will
    be in, so the answer carries a sentence a user can act on rather
    than a bare false.
    """

    ok: bool = True
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


# ======================================================================
#  A REGISTRY
# ======================================================================

class Registry:
    """Name -> thing, for anything that has a ``name``.

    Engines, modules and formats are each a registry of this shape,
    and each was written out on its own: three copies of thirty lines
    that had drifted apart -- only modules could be unregistered,
    formats had no ``names`` or ``len``, and an unknown format did not
    say what there was instead.  ``unregister``'s reason applies to all
    three: a registry that can only grow leaks between test cases, and
    a plugin that fails half way through registering has to be able to
    take back what it added.

    A subclass names what it holds (:attr:`noun`), the error an
    unknown name raises (:attr:`error`), and whether it is iterated in
    ``(order, label)`` order -- the chooser's -- or in the order things
    were registered (:attr:`sorted`), which for formats is the order a
    file dialog lists them in.
    """

    noun = "entry"
    error: type[Exception] = ValueError
    sorted = False

    def __init__(self):
        self._items: dict[str, Any] = {}

    def register(self, item):
        self._items[item.name] = item
        return item

    def unregister(self, name: str) -> None:
        self._items.pop(name, None)

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        items = list(self._items.values())
        if self.sorted:
            items.sort(key=lambda item: (item.order, item.label))
        return iter(items)

    def get(self, name: str):
        try:
            return self._items[name]
        except KeyError:
            raise self.error(
                f"unknown {self.noun}: {name!r}; have "
                f"{', '.join(sorted(self._items)) or 'none'}"
            ) from None

    def names(self) -> list[str]:
        """Every name, in iteration order."""
        return [item.name for item in self]
