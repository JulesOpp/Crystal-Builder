(architecture-registries)=
# Registries: commands, modules and engines

Almost everything the window offers that is not crystallography
itself is an entry in a registry: every menu command, every module
under *Modules*, every engine in the Force Field chooser, every file
format.  After this page you know what each registry holds, how one
declaration becomes a menu entry, a form, a `--help` line and a page
of this manual, and why an entry that cannot run is greyed out with
a reason rather than failing when clicked.

```{index} single: registry; commands
```
```{index} single: registry; modules
```
```{index} single: registry; engines
```
```{index} single: Param
```
```{index} single: Availability
```

## One shape, several registries

`xtal/params.py` holds the `Registry` class the core's registries
share: *name -> thing, for anything that has a `name`*.  It has
`register`, `unregister`, `get`, `names`, `in`, `len` and iteration,
and a subclass names what it holds, which error an unknown name
raises, and whether it iterates in `(order, label)` order -- the
chooser's -- or in registration order, which for file formats is the
order a file dialog lists them in.  The docstring records why there
is one class: engines, modules and formats "were each written out on
their own: three copies of thirty lines that had drifted apart", and
`unregister` exists because "a registry that can only grow leaks
between test cases, and a plugin that fails half way through
registering has to be able to take back what it added".

| Registry | Where | Holds | Listed by |
|---|---|---|---|
| `FORMATS` | `xtal/io/registry.py` | File formats, read and written by extension | `xtal formats`; {doc}`/utilities/formats` |
| `MODULES` | `xtal/modules/registry.py` | Modules: things that run and leave a {term}`run folder` | `xtal modules`; the *Modules* menu and {ref}`panel <panel-modules_dock>` |
| `ENGINES` | `xtal/ff/registry.py` | Energy engines: energy, forces and, where they can, stress | `xtal engines`; the Force Field {ref}`panel <panel-ff_dock>`'s chooser |
| the action registry | `xtalapp/actions.py`, filled in `xtalapp/menus.py` | Every command in the window | the menus, the toolbar, the context menus, *Help* |

Plug-ins register into the first three (and into the shell's draw
styles) through the mechanism on the {doc}`next page <plugins>`.

## Commands: the action registry

A command is defined **once**.  `xtalapp/menus.py` opens with the
principle: "the action registry is filled once, and the menu bar, the
toolbar, the Modules menu and the context menus are all built by
reading names back out of it.  That is why a context-menu entry and a
menu-bar entry are the same object, enabled and disabled by the same
rule and showing the same tick."

`build_actions(window)` is the one place a command is declared.  Each
line is a call to `ActionRegistry.add`:

```python
add("new", "&New", window.new_document, "Ctrl+N")
add("save", "&Save File", window.save_document, "Ctrl+S",
    tip="Save the session -- the structure, the bonds you drew, "
        "the view, the selection and the measurements -- over "
        "the file this is, without asking where")
```

The pieces are: the **key** (`save`), which is permanent -- tests, the
log, the generated reference's anchors and the run-app driver all
spell a command by it; the **label** as the menu shows it, with its
mnemonic; the **slot**, always a method of the window; an optional
**shortcut**, one key or a list of equivalents (the `Delete` key on a
laptop sends Backspace, so an action bound to one spelling alone "has
no key at all on the machine most people are sitting at"); and the
**tip**, which is at once the tooltip, the status-bar line and the
text under the command in *Help* and in {ref}`the reference
<reference-appendix>`.  `checkable`, `group` and the macOS menu `role`
complete it.

`build_menus`, `build_toolbar` and `context_menu` then place keys, not
actions: a menu is a list of keys with `None` for a separator.  Module
entries join the same registry under the name
`module.<module>.<action>` (`menus.module_action`), "so that a
keyboard shortcut, a test and the CLI all spell it the same way".
Enabling is decided centrally too -- `shell_state.py` holds "every
enabling decision" -- which is how a command is greyed out in the
menu bar, the toolbar and the right-click menu at the same moment.

## Modules

`xtal/modules/registry.py` declares *what can be run, as data rather
than as menu items*.  A `Module` has a `name`, a `label`, a
`description`, a tuple of `actions`, an optional `check`, an `order`
in the tree and a `provides` set; an `Action` is "the thing a user
actually picks": `name`, `label`, `tip`, `shortcut`, its `params`, and
`run`, "a callable taking a `Job` and returning a `JobResult`.  It
runs on a worker thread, knows nothing about the window, and is the
same callable the CLI invokes -- which is what keeps a module
testable without a display."

Four decisions from the module's docstring shape everything built on
it:

- **A module declares, it does not draw.**  Nothing in the registry
  imports Qt; what a `float` looks like on screen is the shell's
  business.
- **The declaration is deliberately small.**  No layout, no
  conditional enabling, no validation language, no result schema
  beyond "a message, and optionally a structure".
- **An action is what appears in the tree, not a module.**
  *Forcefield* is one module with three entries because those three
  are what you pick between.
- **A module runs something and leaves artefacts behind.**  That is
  the line between *Modules* and the *Structure*, *Symmetry* and
  *Cell* menus, which edit the structure in place.

From one `MODULES.register(Module(...))` the application builds the
menu entry, the leaf in the Modules panel, the parameter form, the
worker thread, the run folder, the live log and the Stop button.  The
further fields on `Action` are the exceptions that real modules
needed: `shell` hands the whole action to a window method (the three
Force Field entries predate the registry and keep their live plot);
`dialog` names a dialog that replaces only the *collection of the
parameters* and hands back the same values a generated form would
(the MOF builder, whose parameters depend on the topology chosen);
`writes_run_folder=False` for an action with nothing to leave behind;
`needs_structure=False` for a builder that makes one; `keeps_markers`
for the one action that reads the bonding with the dummy atoms still
in it.  `MODULES.find("forcefield.optimise")` resolves the
`module.action` spelling that `xtal run` and the reference anchors
use.

## Engines

`xtal/ff/registry.py` is "name -> calculator, the same shape as the
file-format and draw-style registries".  An `Engine` has a `name`, a
`label`, a `description`, `build` (a callable
`(structure, **options) -> Calculator`), a `provides` set drawn from
`forces`, `stress`, `charges`, `periodic` and `types` "for the UI to
grey out honestly", its `options` as `Param` declarations, a `check`,
an `order` in the chooser and its `references`, shown under the
chooser as links.  `ENGINES.build(name, structure, **options)` is what
the optimiser, the relaxed scan, the Force Field panel and
`xtal energy` all call, and none of them knows which engine it was
given ({doc}`/energy/index`).

An engine's `check` is handed the options, "because for an external
engine half the answer is in them: DFTB+ without a Slater-Koster
directory cannot run, and *which* directory is a field in the form.
A check that ignored them would tell a user their engine was
unavailable while they were looking at the box that makes it
available."  UFF declares no options and keeps its two hand-built
controls; an engine that declares options gets a generated form,
"which is what let DFTB+, with its Hamiltonian, its parameter set, its
k-point mesh and its filling temperature, arrive without the panel
learning any of those words" ({ref}`engine-dftb`).

## `Param`: a value described, not drawn

Both registries declare what they need as `Param` objects from
`xtal/params.py`: *one value a module or an engine needs before it
can run*, with a `name`, a `label`, a `kind` from `bool`, `int`,
`float`, `choice`, `text` and `path`, a `default`, `choices`,
`minimum`, `maximum`, `step`, `decimals`, `suffix` and `help`.  The
docstring gives the test a seventh kind would have to pass: "every one
of them has an obvious widget, an obvious command-line spelling and an
obvious default".  `defaults(params)` and `coerce(params, values)`
fill in what was not given and type what was, the same way for a
dialog and for `-p name=value` on the command line.

One declaration therefore renders four ways: the generated form in
the window (`xtalapp/dialogs/module_form.py`), the `-p` lines of
`xtal modules` and `xtal engines` ({ref}`workflows-cli`), the setting's
row in the {ref}`reference <reference-appendix>` and the *Help*
window, and a headless test.  The `help` string is the tooltip and the
reference's text at once, which is why a wrong sentence in the manual
is fixed in the source and regenerated rather than edited.

## `Availability`: greyed out, with a reason

`Availability` is "whether something can run, and why not when it
cannot": an `ok` flag and a `reason`, true or false in a boolean
context.  "An external tool that is missing is the most common state
it will be in, so the answer carries a sentence a user can act on
rather than a bare false."  A module's `check` is called every time
the tree is rebuilt, so it has to be cheap -- `shutil.which` for a
binary, `find_spec` for a Python package, never an import.  An
`Action` may carry a `check` of its own, for an entry that needs an
extra the rest of its module does not, and `Module.blocked()` answers
with the module's reason or else the first entry's.

In the window the reason becomes the tooltip on the greyed entry
(`menus.refresh_module_availability`), and the paths from Preferences
are pushed into the core's lookup first, "which is what makes a module
whose binary was named there stop being greyed out without a restart".
On the command line the same object prints beside the entry.  On the
machine this manual was written on, with no Zeo++ installed:

```console
$ xtal modules
[...]
zeopp
  zeopp.diameters        Pore diameters and channels...   [unavailable: Zeo++ is not installed, or not on PATH (XTAL_ZEOPP is not set).  It is at https://www.zeoplusplus.org/]
      -p gas='n2'   choice, probe
      -p probe_radius=1.86   float, probe radius
[...]
```

and, for an engine whose extra is missing, the exact command to type
for this interpreter and this checkout:

```console
$ xtal engines
uff      UFF
      -p parameter_set='uff4mof'   choice, parameters
[...]
mace     MACE (machine-learned)   [unavailable: MACE is not installed -- "/Users/sam/Projects/Jules/Crystal-Builder/.venv/bin/python" -m pip install -e "/Users/sam/Projects/Jules/Crystal-Builder[mace]"]
[...]
```

## Why the reference cannot drift

Appendix A of this manual -- the commands, the modules and their
settings, the engines and their options, the panels -- is not written
by hand.  `.claude/skills/manual-writing/reference.py` builds a real
main window with a stub in place of the 3D view, in scratch
preferences and a scratch workspace, and never shows it; it walks the
menu bar to list every action with its path, shortcut and tip, reads
`MODULES` and `ENGINES` for every entry and every `Param`, reads each
dock's docstring, and writes `docs/manual/reference/*.md` and an
`inventory.json`.  Every entry gets a label built from its registry
key -- `(cmd-recompute_bonds)=`, `(mod-zeopp-diameters)=`,
`(engine-uff)=`, `(panel-ff_dock)=` -- "never from the wording, so a
rewording does not break a link".  The script reads "the same live
objects the Help window reads", so the appendix and *Help* cannot
disagree, and the pages are committed and rebuilt by continuous
integration with every warning an error, so a renamed key breaks a
cross-reference in the prose and fails the build ({doc}`testing`).
