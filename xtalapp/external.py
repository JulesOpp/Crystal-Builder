"""
xtalapp.external
================
Where other people's programs are, and how we say where we looked.

Three of the five things this application shells out to are found
through the environment: ``XTAL_ZEOPP``, ``XTAL_DFTB``,
``DFTB_PREFIX``.  That is exactly right in a terminal and useless in a
double-clicked application, which has no shell to export anything in
and no way of being told.  So the paths become preferences, and this
module is the seam between a preference and a package that must never
read one.

**The direction of the dependency is the whole point.**
:class:`xtal.modules.process.Program` has carried a ``setting`` field
since the module machinery was built and nothing ever filled it in.
It is filled in now -- ``tools/zeopp``, ``tools/dftb`` -- and
:func:`apply_hints` copies what those preferences say into
:func:`xtal.modules.process.set_hint`, which every later ``locate()``
reads first.  ``xtal`` still imports no Qt and knows nothing about
QSettings; it is handed an answer, the way a shell hands it one in an
environment variable.

**A preference beats the environment variable.**  Recorded in
``Program.hint``: a variable is what a *shell* set and a preference is
what a *person* set on purpose, and the shipped build has no shell.

**The status line is the feature.**  A path field that goes red says
nothing a user can act on.  What is wanted is *what was tried* --
"Found at /usr/local/bin/network, on PATH", or "Not found.  Looked at
XTAL_ZEOPP, which is not set, and on PATH" -- which is the difference
between a five-minute fix and concluding the feature is broken.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from xtal.ff.dftb import calculator as dftb
from xtal.ff.dftb import hsd
from xtal.modules import process, zeopp

#: The programs whose location is a preference.  Two, because those
#: are the two binaries this application runs; the list is read from
#: the modules themselves so that ``setting`` is written once.
PROGRAMS = (zeopp.PROGRAM, dftb.PROGRAM)

#: Where the Slater-Koster parameter directory is remembered.  Not a
#: :class:`~xtal.modules.process.Program` -- it is a folder of ``.skf``
#: files rather than a binary -- so it has a key of its own and is
#: read by :func:`xtal.ff.dftb.hsd.slater_koster_directory` through
#: the run form's field, whose default it becomes.
SLATER_KOSTER = "tools/dftb_parameters"


def apply_hints(settings) -> None:
    """Tell :mod:`xtal` where the preferences say the programs are.

    Cheap, and called every time the Modules menu is about to open as
    well as when a preference changes -- which is what makes a module
    that was greyed out light up the moment its path is filled in,
    with no restart.
    """
    for program in PROGRAMS:
        process.set_hint(program.setting,
                         settings.path_setting(program.setting))


@dataclass(frozen=True)
class Tool:
    """One row of Preferences > External tools."""

    key: str                    # the preference that stores the path
    label: str
    #: ``file`` opens a file chooser and ``folder`` a directory one.
    kind: str
    #: What it is for, under the field.
    hint: str


TOOLS = (
    Tool("tools/zeopp", "Zeo++ (network)", "file",
         "Pore diameters, surface area and the pore size "
         "distribution.  A single binary called network."),
    Tool("tools/dftb", "DFTB+ (dftb+)", "file",
         "The tight-binding engine, for energies and geometries a "
         "force field cannot reach."),
    Tool(SLATER_KOSTER, "Slater-Koster parameters", "folder",
         "The folder of .skf files DFTB+ needs -- a separate download "
         "from dftb.org.  This is the starting value of the run "
         "form's own field."),
    Tool("mof/topology_dir", "PORMAKE topologies", "folder",
         "Your own .cgd nets, read alongside the 2399 PORMAKE "
         "ships."),
    Tool("mof/bb_dir", "PORMAKE building blocks", "folder",
         "Your own .xyz blocks, read alongside PORMAKE's 867.  It is "
         "where Save as a building block writes."),
)


def program_for(key: str):
    """The :class:`Program` a preference names, or ``None``."""
    for program in PROGRAMS:
        if program.setting == key:
            return program
    return None


def status(settings, tool: Tool) -> tuple[bool, str]:
    """Whether it is there, and the sentence saying how we know.

    The stored path is passed in rather than read back out of
    :func:`~xtal.modules.process.hint_for`, so that the line under a
    field describes what is *in* that field.  A page that answered
    from the pushed hint would be a keystroke behind, and would say
    nothing at all in a dialog opened without a window behind it.
    """
    program = program_for(tool.key)
    if program is not None:
        return _program_status(program, tool,
                               settings.path_setting(tool.key))
    if tool.key == SLATER_KOSTER:
        return _parameters_status(settings.path_setting(tool.key))
    return _blocks_status(tool, settings.path_setting(tool.key))


# -- one program -------------------------------------------------------

#: The bundled copies, by preference.  Only Zeo++ ships one, and it is
#: the last thing tried rather than the first, so that a user who has
#: installed their own gets theirs.
#: Looked up through the module rather than bound here, so that a
#: test -- or a build where the copy is not there -- gets the answer
#: the module gives at the time it is asked.
_BUNDLED = {"tools/zeopp": lambda: zeopp.bundled()}


def _program_status(program, tool, hint="") -> tuple[bool, str]:
    tried = []
    for source, candidate, found in program.search(hint):
        if found is not None:
            return True, f"Found at {found} -- {_source(source)}."
        tried.append(_missing(source, candidate))
    bundled = _BUNDLED.get(tool.key)
    here = bundled() if bundled is not None else None
    if here is not None:
        return True, (f"Found at {here} -- the copy that ships with "
                      f"this source checkout.")
    sentence = "Not found.  Looked " + _join(tried) + "."
    if program.url:
        sentence += f"  It is at {program.url}"
    return False, sentence


def _source(source: str) -> str:
    if source == "preference":
        return "the path set here"
    if source == "PATH":
        return "on PATH"
    return f"named by {source}"


def _missing(source: str, candidate: str) -> str:
    if source == "preference":
        return f"at {candidate}, which is set here"
    if source == "PATH":
        return "on PATH"
    return (f"at {source}, which is not set" if not candidate
            else f"at {source} ({candidate})")


def _join(parts) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


# -- the two kinds of folder -------------------------------------------

def _parameters_status(given: str) -> tuple[bool, str]:
    """Where DFTB+'s parameters are, in the order they are looked for.

    The same order :func:`xtal.ff.dftb.hsd.slater_koster_directory`
    reads -- what is set here, then ``DFTB_PREFIX``, then a set
    bundled in a source checkout -- said out loud, because "DFTB+ is
    installed but has no parameters" is the state it is usually in and
    the least self-explanatory.
    """
    if given:
        path = Path(given).expanduser()
        if path.is_dir():
            return True, f"Found at {path} -- the folder set here."
        return False, f"{path} is not a folder."
    from_env = os.environ.get(hsd.ENV_VAR, "")
    if from_env and Path(from_env).expanduser().is_dir():
        return True, (f"Found at {from_env}, named by "
                      f"{hsd.ENV_VAR}.")
    bundled = hsd.bundled()
    if bundled is not None:
        return True, (f"Found at {bundled} -- the set that ships with "
                      f"this source checkout.")
    return False, (f"Not set, and {hsd.ENV_VAR} names nothing.  The "
                   f"sets are separate downloads from dftb.org -- 3ob "
                   f"for organics, matsci for inorganic solids.")


#: What a user's own folder holds, per row.
_PATTERNS = {"mof/topology_dir": "*.cgd", "mof/bb_dir": "*.xyz"}


def _blocks_status(tool, given: str) -> tuple[bool, str]:
    """A folder read alongside PORMAKE's own database.

    Empty is not a failure here and does not say it is: PORMAKE ships
    2399 nets and 867 blocks, and this row is only for the ones a user
    drew themselves.
    """
    pattern = _PATTERNS[tool.key]
    if not given:
        return True, (f"Not set.  PORMAKE's own database is read "
                      f"either way; this is for your own {pattern} "
                      f"files.")
    path = Path(given).expanduser()
    if not path.is_dir():
        return False, f"{path} is not a folder."
    count = len(list(path.glob(pattern)))
    return True, (f"{count} {pattern} file(s) in {path}." if count else
                  f"{path} has no {pattern} files in it.")
