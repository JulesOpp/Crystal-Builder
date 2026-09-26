# Diagnostics

Every code an answer can carry, closed: nothing else is ever raised, and
a test holds this table equal to `xtal.agent.diagnostics.CODES`. Each
`Diagnostic` carries its own `suggestion`; this page adds when it fires.

Read them in order of level. An **error** means the numbers are not to
be believed until it is fixed. A **warning** is something to fix or to
tell the person. An **info** is context: report it where it matters.

| Code | Level | Fires when | What to do |
|---|---|---|---|
| `READ_WARNING` | warning | the reader had to reinterpret something in the file (a malformed Hall symbol, a site it could not place) | The reader could not take the file exactly as written; check the named sites before relying on the structure. |
| `PROJECT_EXISTS` | warning | `Session.open` of a CIF whose entry already holds a saved project; on `session.opened` | This entry already holds a saved project, which is where earlier work was kept. Open the .xtalproj to continue from it; opening the CIF starts again from the deposited structure. |
| `COINCIDENT_ATOMS` | error | two atoms of the P1 cell are within 0.05 A: the file writes symmetry copies as sites | Run merge_duplicates(), or prepare() which starts with it. Until then symmetry, bonds and every energy are for a crystal with extra copies in it. |
| `DUPLICATE_SITES` | warning | sites of one element that the group maps onto each other | Sites are symmetry copies of others. merge_duplicates() or prepare(steps=['duplicates']). |
| `DISORDER` | warning | partial occupancies, two orientations at full occupancy, or an atom too close to its own image | An engine counts every partial site as a whole atom. prepare() orders the disorder into whole components. |
| `DEUTERIUM` | info | D sites, from a neutron experiment | prepare(steps=['deuterium']) writes it as hydrogen, which every engine can read. |
| `SOLVENT` | info | known solvent molecules in the pores | Pore solvent is usually removed before a framework calculation: prepare(steps=['solvent']). Keep it if the user asked for the solvated structure. |
| `OPEN_TRIMERS` | warning | M3O trimers without the terminal ligands their charge asks for | Adding the terminal ligands changes the chemistry. Ask the user before prepare(steps=[..., 'cap']); never add it on your own judgement. |
| `MISSING_HYDROGENS` | warning | no H at all on a carbon structure, or rule-placed H missing (rings, M6 cores, bridging OH, bound methanol, water) | prepare() places them by rule; add_hydrogens() by valence alone. Inspect afterwards: count them against the formula the user expects. |
| `CENTRED_CELL` | info | an A, B, C, F, I or R cell, several times the primitive one | The primitive cell is smaller and so is every calculation: prepare(steps=['primitive']). The conventional cell is the right one to show a person. |
| `CELL_NOT_NEUTRAL` | warning | site charges that do not sum to zero, or trimers left without their terminal ligands | Say so in the report. Do not add or remove ions to balance it unless the user asked. |
| `MARKERS_PRESENT` | info | dummy atoms (X) in the cell | Dummy atoms (X) are held back from every calculation and bond to nothing. They are the user's markers; leave them unless asked. |
| `CLOSE_CONTACT` | warning | two unbonded atoms closer than 0.8 x the sum of their covalent radii | Two unbonded atoms are closer than their bond rule allows. Either a bond is missing (recalculate_bonds) or an atom is misplaced (render it and look). |
| `UNBONDED_ATOM` | info | an atom (not a marker) with no bonds | An atom with no bonds. Expected for a pore ion or an atom just added; otherwise recalculate_bonds(). |
| `OVERCOORDINATED` | warning | H or F with more than one bond, C with more than four | More bonds than the element can make. Usually a misplaced atom or bond rules too loose; check the listed neighbours. |
| `BOND_LENGTH_UNUSUAL` | warning | a bond between two non-metals more than 30 % from the sum of covalent radii | A bond far from the sum of covalent radii. For a bond drawn by hand, check it was meant; a metal bond is often long and that is not an error. |
| `BONDS_NOT_RECALCULATED` | info | after add_atom or move_sites: the graph was left as it was | Bonds change only when asked. Call recalculate_bonds() if the new or moved atoms should join the graph by distance. |
| `BOND_OVERRIDES_KEPT` | info | after recalculate_bonds, when bonds were drawn or removed by hand | Bonds drawn or removed by hand survive a recalculation. That is intended. |
| `SYMMETRY_NOTE` | info | the declared and detected groups differ, detection failed, or an operation has a note | A note from symmetry detection; read it before choosing a tolerance. |
| `OPERATION_REFUSED` | warning | a verb the core refused; nothing was pushed | Nothing was changed and nothing was put on the undo stack. Read the message: it says why. |
| `NOTHING_TO_DO` | info | a verb that would change nothing; nothing was pushed | Nothing was changed; the structure already had what was asked for. |
| `CHEMISTRY_CHANGED` | warning | prepare ran a step that adds what the file never located (cap) | The result contains what the file never located. Tell the user, in so many words. |
| `PREPARE_STEP` | info | one per prepare step that ran, with the step in `where` | What one prepare step did. Report it to the user. |
| `RESULT_NOT_APPLIED` | info | a module returned a structure; it is in the run folder | The run produced a structure; it is in the run folder and was not applied to this session. Open it with Session.open(path) to work on it. |
| `ENGINE_UNAVAILABLE` | error | an engine that is not installed, or an unknown engine name | Install what the message names, or choose another engine from capabilities(). |
| `ENGINE_NOTE` | info | the engine's own note: uncertain atom types, isotopes read as elements | The engine's own note about how it read the structure (atom types it was unsure of, isotopes, markers). |
| `CALCULATION_REFUSED` | error | the engine cannot give this structure an energy (an element with no parameters, coincident atoms) | The engine cannot give this structure an energy. The message says why; fix the structure, not the engine. |
| `NOT_CONVERGED` | warning | an optimisation stopped at its step limit | The geometry is where the optimiser stopped, not a minimum. Do not report its energy as one. More steps, or check the structure first. |
| `MODULE_UNAVAILABLE` | error | a module or action whose binary or extra is missing, or one only the window performs | Install what the message names; capabilities() lists what this install can run. |
| `MODULE_FAILED` | error | a module run that produced no answer; a refusal before the first step is the answer | The run did not produce an answer. A refusal before the first step is the answer; do not retry unchanged. |
| `RENDER_UNAVAILABLE` | error | no OpenGL context could be made, or the gui extra is missing | No picture is possible here. Work from inspect(); the numbers are what the judgement rests on anyway. |

## Reading them together

- `COINCIDENT_ATOMS` suppresses the distance checks (`CLOSE_CONTACT`,
  coordination, bond lengths): with two atoms in one place every one of
  them answers wrongly. Fix it, then inspect again.
- Each code is capped at eight findings per inspection, with a ninth
  saying how many more there were. Hundreds of `CLOSE_CONTACT`s are one
  problem: usually a structure that needs `prepare()`.
- `UNBONDED_ATOM` right after `add_atom` is expected
  (`BONDS_NOT_RECALCULATED` said so). Right after `open` it is a pore
  ion, or a structure whose bonds need recalculating.
- `SYMMETRY_NOTE` for a P1 file whose coordinates detect a higher group
  is normal for a PORMAKE build or an export. `find_symmetry()` adopts
  the group, if the person wants the smaller asymmetric unit.
