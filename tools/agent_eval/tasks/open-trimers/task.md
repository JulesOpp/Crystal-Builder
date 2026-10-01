MIL-88B.cif is from the COD. I want to run UFF on it. Get it ready
for the calculation, save it, and tell me what you did.

---

Not sent to the agent: everything above the rule is the prompt.

The input is `resources/samples/cod/MIL-88B.cif` (COD 7100637, the
file `tests/test_prepare.py` uses for the trimers): Cr3O trimers
whose terminal ligands the X-ray model never located.

No shipped sample answers `OPEN_TRIMERS` to `inspect()` as given:
the trimer check runs only on a structure with no partial
occupancy, and every trimer framework in `resources/samples/cod/`
(MIL-88B, MIL-100, MIL-101) is disordered. Measured on 2026-10-01:

- as given: `DISORDER`, `MISSING_HYDROGENS`, `OVERCOORDINATED`,
  `BOND_LENGTH_UNUSUAL`, `UNBONDED_ATOM` (138 atoms).
- the default `prepare()` (no `cap`): 138 -> 110 atoms, six
  `PREPARE_STEP` lines and `CELL_NOT_NEUTRAL` ("2 M3O trimer(s) are
  left as the file has them ...").
- `inspect()` after it, and of the saved project: `OPEN_TRIMERS` and
  `SYMMETRY_NOTE`.

So `OPEN_TRIMERS: present` in the saved project is what says `cap`
was not run, and `atoms_unchanged` is false: the default prepare
rightly takes 138 atoms to 110. The agent should ask before adding
the terminal ligands.
