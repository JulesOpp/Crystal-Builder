"""
xtalapp.dialogs
===============
The dialogs, and the one name that has to be resolved rather than
imported.

Everything in here is imported by path -- ``from
xtalapp.dialogs.supercell import SupercellDialog`` -- and this file
holds nothing, which is how a package this size stays cheap to
import.

The exception is :attr:`xtal.modules.registry.Action.dialog`.  A
module declares its parameters as data and imports no Qt, so an action
that needs a dialog of its own can only *name* one; this is where the
name becomes a class.  The import is inside the function for the
reason above: resolving one name must not drag in all the others.
"""

from __future__ import annotations

#: Action name -> where the dialog lives.  The shape is the point: a
#: module that grows a dialog adds a line here and changes nothing
#: else.
#:
#: Two names answer to one class on purpose.  The molecule builder has
#: two entries -- one opens a tab of its own, one pastes into the
#: structure already open -- and they differ only in whether
#: connection points are on offer and in what the footer says will
#: happen.  One dialog reading the action's *name* is the whole of
#: that difference; two classes would be two of everything to keep in
#: step.  See :mod:`xtalapp.dialogs.build_molecule`.
_BY_NAME = {
    "mof-build": ("xtalapp.dialogs.mof_build", "MofBuildDialog"),
    "build-molecule": ("xtalapp.dialogs.build_molecule",
                       "BuildMoleculeDialog"),
    "build-insert": ("xtalapp.dialogs.build_molecule",
                     "BuildMoleculeDialog"),
    "net-draw": ("xtalapp.dialogs.net_draw", "NetDrawDialog"),
    "stl-export": ("xtalapp.dialogs.stl_export", "StlExportDialog"),
    "band-structure": ("xtalapp.dialogs.dftb_run",
                       "BandStructureDialog"),
    "dftb-run": ("xtalapp.dialogs.dftb_run", "DftbRunDialog"),
    "scan": ("xtalapp.dialogs.scan", "ScanDialog"),
}


def dialog_modules() -> list[str]:
    """Every module :func:`module_dialog` might import.

    For ``packaging/bundle.py``, and it is not a convenience.  A
    module reached only through :func:`importlib.import_module` is
    invisible to PyInstaller's analysis, so it is simply absent from a
    frozen build and the action raises ``ModuleNotFoundError`` the
    moment somebody clicks it -- which is what happened to all three
    of the names above in the first bundle that carried them.  Nothing
    in the suite can see that, because a source checkout imports fine.

    Derived from the mapping rather than repeated beside it, so a
    module that grows a dialog still changes one line.
    """
    return sorted({module for module, _class in _BY_NAME.values()})


def dialog_actions() -> list[str]:
    """Every action name :func:`module_dialog` answers to.

    For ``crystal-builder --selftest``, which resolves all of them
    inside the built bundle for the reason in :func:`dialog_modules`.
    """
    return sorted(_BY_NAME)


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


__all__ = ["dialog_actions", "dialog_modules", "module_dialog"]
