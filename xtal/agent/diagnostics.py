"""
xtal.agent.diagnostics
======================
The closed set of things an agent can be told about a structure or an
edit, each with what to do about it.

Closed on purpose.  An agent that reads a sentence has to guess what
kind of sentence it is; one that reads ``COINCIDENT_ATOMS`` can look
the code up in the skill's ``references/diagnostics.md`` and find the
remedy that was measured for it.  A test holds the two lists equal, so
a code cannot be raised here and be missing there.

Where the core already says something -- a prepare caution, a symmetry
warning, an engine's note about the structure -- the core's sentence
is carried as the message and only the *code* is ours.  Rewording it
would be a second place for the wording to drift.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

INFO, WARNING, ERROR = "info", "warning", "error"


@dataclass(frozen=True)
class Code:
    level: str
    suggestion: str


#: Every code, its level and the one thing to do about it.
CODES: dict[str, Code] = {
    # -- reading and the state of the file -----------------------------
    "READ_WARNING": Code(
        WARNING, "The reader could not take the file exactly as "
                 "written; check the named sites before relying on "
                 "the structure."),
    "COINCIDENT_ATOMS": Code(
        ERROR, "Run merge_duplicates(), or prepare() which starts with "
               "it. Until then symmetry, bonds and every energy are "
               "for a crystal with extra copies in it."),
    "DUPLICATE_SITES": Code(
        WARNING, "Sites are symmetry copies of others. "
                 "merge_duplicates() or prepare(steps=['duplicates'])."),
    "DISORDER": Code(
        WARNING, "An engine counts every partial site as a whole atom. "
                 "prepare() orders the disorder into whole components."),
    "DEUTERIUM": Code(
        INFO, "prepare(steps=['deuterium']) writes it as hydrogen, "
              "which every engine can read."),
    "SOLVENT": Code(
        INFO, "Pore solvent is usually removed before a framework "
              "calculation: prepare(steps=['solvent']). Keep it if the "
              "user asked for the solvated structure."),
    "OPEN_TRIMERS": Code(
        WARNING, "Adding the terminal ligands changes the chemistry. "
                 "Ask the user before prepare(steps=[..., 'cap']); "
                 "never add it on your own judgement."),
    "MISSING_HYDROGENS": Code(
        WARNING, "prepare() places them by rule; add_hydrogens() by "
                 "valence alone. Inspect afterwards: count them "
                 "against the formula the user expects."),
    "CENTRED_CELL": Code(
        INFO, "The primitive cell is smaller and so is every "
              "calculation: prepare(steps=['primitive']). The "
              "conventional cell is the right one to show a person."),
    "CELL_NOT_NEUTRAL": Code(
        WARNING, "Say so in the report. Do not add or remove ions to "
                 "balance it unless the user asked."),
    "MARKERS_PRESENT": Code(
        INFO, "Dummy atoms (X) are held back from every calculation "
              "and bond to nothing. They are the user's markers; "
              "leave them unless asked."),
    # -- bonding and geometry ------------------------------------------
    "CLOSE_CONTACT": Code(
        WARNING, "Two unbonded atoms are closer than their bond rule "
                 "allows. Either a bond is missing (recalculate_bonds) "
                 "or an atom is misplaced (render it and look)."),
    "UNBONDED_ATOM": Code(
        INFO, "An atom with no bonds. Expected for a pore ion or an "
              "atom just added; otherwise recalculate_bonds()."),
    "OVERCOORDINATED": Code(
        WARNING, "More bonds than the element can make. Usually a "
                 "misplaced atom or bond rules too loose; check the "
                 "listed neighbours."),
    "BOND_LENGTH_UNUSUAL": Code(
        WARNING, "A bond far from the sum of covalent radii. For a "
                 "bond drawn by hand, check it was meant; a metal bond "
                 "is often long and that is not an error."),
    "BONDS_NOT_RECALCULATED": Code(
        INFO, "Bonds change only when asked. Call recalculate_bonds() "
              "if the new or moved atoms should join the graph by "
              "distance."),
    "BOND_OVERRIDES_KEPT": Code(
        INFO, "Bonds drawn or removed by hand survive a "
              "recalculation. That is intended."),
    # -- symmetry ------------------------------------------------------
    "SYMMETRY_NOTE": Code(
        INFO, "A note from symmetry detection; read it before "
              "choosing a tolerance."),
    # -- edits ---------------------------------------------------------
    "OPERATION_REFUSED": Code(
        WARNING, "Nothing was changed and nothing was put on the undo "
                 "stack. Read the message: it says why."),
    "NOTHING_TO_DO": Code(
        INFO, "Nothing was changed; the structure already had what "
              "was asked for."),
    "CHEMISTRY_CHANGED": Code(
        WARNING, "The result contains what the file never located. "
                 "Tell the user, in so many words."),
    "PREPARE_STEP": Code(
        INFO, "What one prepare step did. Report it to the user."),
    "RESULT_NOT_APPLIED": Code(
        INFO, "The run produced a structure; it is in the run folder "
              "and was not applied to this session. Open it with "
              "Session.open(path) to work on it."),
    # -- calculations --------------------------------------------------
    "ENGINE_UNAVAILABLE": Code(
        ERROR, "Install what the message names, or choose another "
               "engine from capabilities()."),
    "ENGINE_NOTE": Code(
        INFO, "The engine's own note about how it read the structure "
              "(atom types it was unsure of, isotopes, markers)."),
    "CALCULATION_REFUSED": Code(
        ERROR, "The engine cannot give this structure an energy. "
               "The message says why; fix the structure, not the "
               "engine."),
    "NOT_CONVERGED": Code(
        WARNING, "The geometry is where the optimiser stopped, not a "
                 "minimum. Do not report its energy as one. More "
                 "steps, or check the structure first."),
    "MODULE_UNAVAILABLE": Code(
        ERROR, "Install what the message names; capabilities() lists "
               "what this install can run."),
    "MODULE_FAILED": Code(
        ERROR, "The run did not produce an answer. A refusal before "
               "the first step is the answer; do not retry unchanged."),
    "RENDER_UNAVAILABLE": Code(
        ERROR, "No picture is possible here. Work from inspect(); the "
               "numbers are what the judgement rests on anyway."),
}


@dataclass(frozen=True)
class Diagnostic:
    """One finding: a closed code, a sentence, where, and what to do."""

    code: str
    message: str
    where: str = ""
    level: str = ""
    suggestion: str = ""

    def __post_init__(self):
        known = CODES.get(self.code)
        if known is None:
            raise KeyError(f"no diagnostic code {self.code!r}")
        # Filled from the registry so a caller names the code and the
        # sentence and nothing else: the level and the remedy are the
        # code's, and a call site cannot make them disagree.
        if not self.level:
            object.__setattr__(self, "level", known.level)
        if not self.suggestion:
            object.__setattr__(self, "suggestion", known.suggestion)

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        where = f" [{self.where}]" if self.where else ""
        return (f"{self.level.upper():7s} {self.code}{where}: "
                f"{self.message} -> {self.suggestion}")


def to_json(value) -> str:
    return json.dumps(value, indent=2, default=_plain)


def _plain(value):
    """numpy scalars and arrays, and anything with ``to_dict``."""
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")
