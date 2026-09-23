"""
xtal.modules.build
==================
A molecule from a SMILES string, as a registry entry.

The same shape as :mod:`xtal.modules.mof` and for the same reason:
RDKit is an optional extra, the tree is rebuilt every time a document
changes, and a check that costs an import is one nothing can afford to
run that often.  So :func:`available` is
:func:`xtal.build.installed`, which is ``find_spec`` and never an
import, and the entry greys out naming the extra when it is absent.

**Only the new-document half is a module.**  A build that makes a
molecule out of nothing is exactly what ``needs_structure = False``
describes -- it is handed no document, and what it returns opens in a
tab of its own.  Dropping the same molecule into the cell that is
already open is the *other* thing, and it cannot be an action here at
all: this registry has two behaviours for a returned structure and
both are wrong for a paste.  With ``needs_structure = True`` the
result replaces the open document as one undoable geometry change,
which throws the framework away and keeps the ligand; with it False
the result opens in a new tab, which is where the molecule already
was.  A paste is neither -- it is an edit *to* the open structure, of
the kind :class:`~xtal.commands.clipboard.PasteFragment` has always
been -- so it is a shell action, ``Structure > Insert molecule...``,
and it borrows :data:`INSERT` below only to satisfy the dialog
contract.

**No run folder.**  There is nothing to leave behind under a run
heading: a build reports nothing a log would hold that the molecule
itself does not say.  What it does get is an *entry* -- the shell
files what a build returns in the workspace and opens it from there
(``Workspace.adopt_build``), so the molecule is a file the moment
it appears rather than after a trip through Save As, and the run
folder this action still does not write is beside the point.
"""

from __future__ import annotations

from xtal.build import MISSING, from_smiles, installed
from xtal.modules.job import JobResult
from xtal.modules.registry import (
    MODULES,
    Action,
    Availability,
    Module,
    Param,
)

__all__ = ["MISSING", "PARAMS", "BUILD", "INSERT", "available",
           "build_molecule", "molecule_for", "register"]


def available() -> Availability:
    """The registry's answer, consulted every time the tree is built.

    ``find_spec`` and nothing more -- see :func:`xtal.build.installed`
    for why importing RDKit to find out whether RDKit is installed is
    not an option here.
    """
    if not installed():
        return Availability(False, MISSING)
    return Availability(True, "RDKit")


# ======================================================================
#  PARAMETERS
# ======================================================================

PARAMS = (
    Param("smiles", "SMILES", kind="text",
          help="The molecule, as SMILES -- c1ccccc1C(=O)[O-] is "
               "benzoate.  A '*' marks a connection point, and "
               "[*:1] and [*:2] say which is which."),
    Param("name", "Name", kind="text",
          help="What to call it, in the tab and in the block file.  "
               "The SMILES string itself when this is left empty."),
    Param("optimise", "Relax it", kind="bool", default=True,
          help="Relax the embedded geometry with MMFF, or UFF where "
               "MMFF has no parameters for it.  The force field in "
               "this application takes it further."),
    Param("seed", "Conformer seed", kind="int", default=0xf00d,
          minimum=0, maximum=2 ** 31 - 1,
          help="Which conformer comes out.  Fixed rather than random "
               "so that the same string twice is the same molecule; "
               "change it to be offered another one."),
)


def molecule_for(values: dict, connection_points: bool):
    """The molecule a set of parameter values describes.

    Shared by the module action and by the shell's insert, so that
    "what these values mean" is written once and the two paths cannot
    drift into building different molecules from the same box.
    """
    return from_smiles(
        str(values.get("smiles", "") or ""),
        name=str(values.get("name", "") or ""),
        seed=int(values.get("seed", 0xf00d) or 0),
        optimise=bool(values.get("optimise", True)),
        connection_points=connection_points)


# ======================================================================
#  RUNNING IT
# ======================================================================

def build_molecule(job) -> JobResult:
    """Build one molecule, into a document of its own.

    Connection points are allowed here and refused by the insert:
    a molecule with ``X`` on it is a building block on its way to
    :mod:`xtal.mof.block`, and a tab of its own is where it gets
    looked at and marked before it is written.
    """
    from xtal.build import BuildError
    try:
        molecule = molecule_for(job.params, connection_points=True)
    except BuildError as exc:
        # A string that is not a molecule is a failed run and not a
        # crash, the same way a block that does not fit its slot is.
        return JobResult.failure(str(exc))
    job.say(f"built {molecule.formula} from {molecule.smiles}")
    structure = molecule.to_structure()
    connections = (f"; {molecule.n_connections} connection point(s)"
                   if molecule.n_connections else "")
    return JobResult(
        message=f"{molecule.formula}, {molecule.n_atoms} atom(s)"
                f"{connections}",
        structure=structure)


# ======================================================================
#  THE MODULE
# ======================================================================

BUILD = Module(
    name="build",
    label="Molecule builder",
    description="Build a molecule from a SMILES string, with RDKit.  "
                "It opens in a tab of its own, in a box with enough "
                "vacuum around it to relax in.",
    order=50,
    check=available,
    provides=frozenset({"structure"}),
    actions=(
        Action(name="molecule", label="Molecule from SMILES...",
               tip="Build a molecule; it opens in a new tab",
               kind="build",
               needs_structure=False,
               writes_run_folder=False,
               dialog="build-molecule",
               params=PARAMS,
               run=build_molecule),
    ),
)

#: The declaration ``Structure > Insert molecule...`` asks with, and
#: the reason there are two dialog names for one dialog class.  It is
#: deliberately *not* an action of :data:`BUILD` -- see the module
#: docstring -- and it is registered nowhere, so nothing runs it; the
#: shell reads its ``params`` to coerce the values and its ``dialog``
#: to find the class, which is the whole of what a dialog needs.  Its
#: name is what tells that dialog connection points are not on offer
#: here.
INSERT = Action(
    name="insert", label="Insert molecule...",
    tip="Build a molecule and paste it into the open structure",
    params=PARAMS,
    dialog="build-insert",
    shell="insert_molecule")


def register(registry=MODULES) -> Module:
    return registry.register(BUILD)
