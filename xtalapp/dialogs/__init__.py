"""
xtalapp.dialogs
===============
The dialogs, and the one name that has to be resolved rather than
imported.

Everything in here is imported by path -- ``from
xtalapp.dialogs.supercell import SupercellDialog`` -- and this file
holds nothing, which is how a package of fourteen dialogs stays cheap
to import.

The exception is :attr:`xtal.modules.registry.Action.dialog`.  A
module declares its parameters as data and imports no Qt, so an action
that needs a dialog of its own can only *name* one; this is where the
name becomes a class.  The import is inside the function for the
reason above: resolving one name must not drag in the other thirteen.
"""

from __future__ import annotations

#: Action name -> where the dialog lives.  One entry, and the shape
#: is the point: a module that grows a dialog adds a line here and
#: changes nothing else.
_BY_NAME = {
    "mof-build": ("xtalapp.dialogs.mof_build", "MofBuildDialog"),
}


def module_dialog(name: str):
    """The dialog class an action asked for, or ``None``.

    ``None`` for the empty name, which is every action that is happy
    with the generated form, and also for a name nothing answers to --
    a module from a plugin naming a dialog this application does not
    have should fall back on the form and run, not refuse to open.
    """
    found = _BY_NAME.get(str(name or ""))
    if found is None:
        return None
    module_name, class_name = found
    import importlib

    return getattr(importlib.import_module(module_name), class_name)


__all__ = ["module_dialog"]
