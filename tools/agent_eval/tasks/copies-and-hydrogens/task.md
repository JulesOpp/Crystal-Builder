Ni2Cl2BTDD.cif is a structure I downloaded from the CSD. I want to
run a force-field calculation on it. Check it, get it ready for the
calculation, save it, and tell me what you found and what you changed.

---

Not sent to the agent: everything above the rule is the prompt.

The input is `resources/samples/Ni2Cl2BTDD.cif` (CCDC POSWUS, a
ConQuest export; see `resources/samples/PROVENANCE.md`), the file
`tests/test_agent_inspect.py` and `tests/test_merge_duplicates.py`
use. Its export writes symmetry copies as sites and the X-ray model
has no hydrogen at all.

Measured with `inspect()` on 2026-10-01:

- as given: `COINCIDENT_ATOMS` (2088 pairs) and `SYMMETRY_NOTE`; the
  coincidence hides every other finding.
- after `merge_duplicates()` alone: `MISSING_HYDROGENS`, `DISORDER`,
  `SOLVENT`, `CENTRED_CELL` and more -- so `MISSING_HYDROGENS: absent`
  is not satisfied by merging alone.
- after the default `prepare()` and `save()`: `SYMMETRY_NOTE` only
  (1152 -> 102 atoms), each step a `PREPARE_STEP` line in its answer.

The `PREPARE_STEP` lines are held by `log_must_contain: prepare`
rather than by `codes`, because the skill asks for each step's
sentence in the report, not for the code.
