(architecture-plugins)=
# Extending it: plug-ins, external programs and extras

Crystal Builder grows at three seams: a Python package installed
beside it can register modules, engines and formats through an entry
point; an external program is found through one lookup that
Preferences, an environment variable and `PATH` all feed; and an
optional Python package is detected without being imported.  After
this page you can write a module that appears in *Modules* and in
`xtal modules` without a line of the application changing, and you
know where a contributor's guides live in the repository.

```{index} single: plug-in
```
```{index} single: entry point; crystal_builder.plugins
```
```{index} single: external programs; how they are found
```
```{index} single: extras; detected without importing
```

## Registration from outside the tree

`xtal/plugins.py` is *registration from outside the tree*.  In-tree
entries register themselves when their package is imported; a
package installed beside the application declares, in its own
`pyproject.toml`, an entry point in the one group the application
looks in, `crystal_builder.plugins`:

```toml
[project.entry-points."crystal_builder.plugins"]
zeopp = "zeopp_plugin:register"
```

Its `register()` "is called once, at start-up, and may register into
any of the four registries" -- file formats, draw styles, engines and
modules.  Two rules govern the loading, "both learned from
applications that got this wrong":

- **A plug-in that raises must not take the application with it.**  A
  broken or half-installed plug-in is a warning in the log and an entry
  in the load report's `failures`, "not a window that will not open".
- **Loading happens once and is idempotent.**  It is called from the
  window's start-up (`xtalapp/main.py`, after the optional-packages
  folder below has gone on the import path) and from the command line
  (`xtal modules` and `xtal run`), and a second call is free.

A plug-in's module gets everything an in-tree one gets: the menu entry
and the Modules panel leaf, the generated form, the worker thread, the
run folder, the live log and Stop -- and the greying-out, because the
Preferences paths are pushed into the core's lookup before the menu
opens, "which keeps that true for a plugin's module, which this file
has never heard of" (`xtalapp/menus.py`).

### A worked example

The module below was written for this page and registered through the
real entry-point mechanism without installing anything: a scratch
folder held the module and a `xtal_hello_plugin-0.1.dist-info`
directory containing a two-line `METADATA` and this
`entry_points.txt`, and the folder was put on `PYTHONPATH`, which is
enough for `importlib.metadata` to find the entry point.  A real
plug-in would carry the same declaration in its `pyproject.toml` and
be installed with `pip`.

```ini
[crystal_builder.plugins]
hello = xtal_hello_plugin:register
```

```python
"""A module from outside the tree: counts the atoms in the cell."""

from xtal.modules import MODULES, Action, JobResult, Module, Param

PARAMS = (
    Param("element", "Element", kind="text", default="",
          help="Count only this element; blank counts every atom."),
)


def count_atoms(job) -> JobResult:
    wanted = str(job.param("element", "")).strip()
    sites = job.structure.sites
    n = sum(1 for s in sites if not wanted or s.element == wanted)
    job.say(f"counted {n} site(s)")
    return JobResult(message=f"{n} site(s) in the asymmetric unit"
                             + (f" are {wanted}" if wanted else ""))


HELLO = Module(
    name="hello",
    label="Hello",
    description="An example module registered by a plugin.",
    order=200,
    actions=(
        Action(name="count", label="Count atoms",
               tip="Count the sites of the current structure",
               writes_run_folder=False,
               params=PARAMS, run=count_atoms),
    ),
)


def register():
    MODULES.register(HELLO)
```

With the folder on the path, the module is listed after the in-tree
ones, its parameter spelt the way every other one is:

```console
$ xtal modules
[...]
hello
  hello.count            Count atoms
      -p element=''   text, element
```

and it runs through the same door as every other module, against a
sample:

```console
$ xtal run hello.count resources/samples/prepared/MIL-53.cif -p element=Cr
counted 2 site(s)
2 site(s) in the asymmetric unit are Cr
```

The first line is `job.say`, which goes to the log and the status bar;
the second is the `JobResult`'s message.  Without the folder on the
path the entry is absent, and `xtal.plugins.load().summary()` reports
`loaded hello` with it and `no plugins installed` without.  The window
picks it up the same way: launched with the folder on the path, the
run-app driver's `--list-actions` shows it registered as
`module.hello.count`, greyed out until a structure is open because
the action left `needs_structure` at its default.

The in-tree way to see the same machinery without writing anything is
the stub module: setting `XTAL_STUB_MODULE=1` registers a module that
counts, sleeps, writes a line per tick and can be told to fail, in the
worker thread and in a subprocess, which is how the run folder, the
live log and Stop are tested on a machine with no external program
installed (`xtal/modules/stub.py`).

:::{note}
Plug-ins installed with `pip` do not load in a packaged build.  A
frozen application has no `pip` and nowhere to install one to, so the
shipped build runs its in-tree modules only; *Preferences ▸ Engines*
offers a folder that is added to the import path at start-up, which
works for a pure-Python package.  Run from a source install if you
need more than that (the release notes, and `docs/PACKAGING.md`).
:::

## External programs

Zeo++, DFTB+ and its `waveplot` and `modes`, tblite, xtb and Blender
are all run through one class, `Program` in `xtal/modules/process.py`:
*an external binary the application knows how to look for*.  A
`Program` has the executable's `name`, a `label`, the `env_var` that
may name it, a `url` to get it from, the Preferences `setting` that
may hold a path, and `known` locations an ordinary install puts it in
("Blender on macOS is an application bundle whose binary is on
nobody's PATH").  `locate` tries them in that order -- the Preferences
path first, then the environment variable, then `PATH`, then the known
places -- and the docstring records the decision: the preference comes
ahead of the variable because "a variable is what a shell sets and a
preference is what a person set on purpose, and a packaged application
has no shell to set the first one in".

The core reads no preferences, so the path from Preferences reaches it
through a small dictionary the shell fills: "the GUI resolves its own
preference and puts the answer here, exactly as a shell puts one in an
environment variable.  Nothing in this package writes to it."
`xtalapp/external.py` does the filling every time the *Modules* menu
is about to open and whenever a preference changes.

Two consequences follow for a module that shells out.  A missing
binary is found "before launching, not inside a subprocess failure":
`Program.resolve` raises `MissingProgram`, which knows the name, where
it looked and where to get it, before the run folder is created; and
the same lookup answers the module's `check`, so the entry is greyed
out with that sentence before anybody clicks.  The run itself goes
through `ExternalProcess`, which writes and flushes every line of
output as it arrives so the Log panel can tail it, terminates the
whole process group on Stop and kills what survives a five-second
grace, and turns a non-zero exit into a sentence that quotes the last
twenty lines the program printed.  The programs, their variables and
the Preferences page are listed under {ref}`external-programs`.

## Optional Python packages

The MOF builder needs `ase`, the molecule builder RDKit, the sketcher
rdeditor, the PXRD window matplotlib, and each machine-learned engine
its own extra.  The rule for detecting them is the same everywhere in
the tree, and the repository states it as an invariant: **the check is
`find_spec` and never an import**.  The reason is in the checks
themselves -- the question is asked every time a menu is refreshed,
and `find_spec` "reads the location off the path and stops", where an
import of a machine-learning stack would load hundreds of libraries
into the window for the sake of greying out a menu entry.

When the package is missing, the entry greys out naming the extra, and
`xtal/install.py` spells the install command for *this* interpreter
and *this* checkout (the `xtal engines` line on the
{doc}`registries page <registries>` is one).  `xtalapp/extras.py`
decides what that message says in a packaged build, where "there is
no environment to install into": the small extras are bundled, and
the rows for the PyTorch engines say they are not included in this
build rather than offering an install nobody can do.  The same module
puts a user-writable folder first on `sys.path` at start-up, which is
the only answer a frozen build has to "install a plugin" at all.

## Where the contributor's guides are

The repository documents its own extension points, for people working
on the code, under `.claude/skills/`.  They are documents to read, not
commands to run:

`.claude/skills/add-module/SKILL.md`
: Adding a calculation: which registry it belongs in (an energy-and-
  forces model is an engine; something that runs and leaves artefacts
  is a module), the registry entry, the `Param` declarations, the
  availability check, an external binary and its Preferences row, an
  optional extra, what a `JobResult` may carry, a dialog in place of
  the generated form, packaging and tests.  It names the smallest
  complete module to copy, `xtal/modules/net.py`.

`.claude/skills/add-action/SKILL.md`
: Adding a command to a menu, the toolbar or a context menu: the chain
  from `build_actions` through a thin window method to a Document
  verb and an undoable command, the enabling rules and the tests that
  assert menu order, with *Merge atoms* as the worked example.

`.claude/skills/code-map/`, `.claude/skills/run-app/`
: A script that outlines a file's classes and methods with their
  first docstring sentence, so a large file need not be read whole;
  and a driver that launches the real window, opens a file, triggers
  an action by its registry key and screenshots the view, a panel or
  a dialog, which is how the figures in this manual were made.

`CLAUDE.md`, `docs/PLAN.md`, `docs/TODO.md`
: The conventions and invariants; the phase plan the layering comes
  from; what has been raised while using the application and is not
  yet scheduled.
