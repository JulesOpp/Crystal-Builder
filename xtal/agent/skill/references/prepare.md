# Preparing a deposited structure

A CIF from the CSD, the COD or a paper's supplement describes an
*experiment*: partial occupancies, symmetry copies written as sites,
solvent in the pores, deuterium from neutrons, hydrogens the X-rays
never located. Every engine will take such a file and return a number
for a crystal nobody has. `prepare()` turns it into one model, one undo
step, and says what it chose at every step.

```python
answer = s.prepare()                         # all but "cap"
for d in answer.diagnostics:
    print(d.where, d.level, d.message)       # one PREPARE_STEP per step
```

## The steps, in the order they run

| Step | What it does | Why it is where it is |
|---|---|---|
| `duplicates` | merges sites that are symmetry copies of others | first, because a ConQuest export writes copies as sites (Ni2Cl2BTDD: 40 sites, 13 independent), which stack 1152 atoms on 378 places and make every later count wrong |
| `deuterium` | writes D as H | so every engine can read it |
| `primitive` | the declared centring's primitive cell, in P1 | a quarter of an F cell is a quarter of every later calculation |
| `disorder` | orders partial sites into whole components | keeps each place's most probable occupant and the composition the occupancies add up to; a hydrogen goes with the atom it rides on |
| `solvent` | removes known solvent molecules from the pores | after ordering, because a disordered solvent is not yet a molecule |
| `cap` | gives M3O trimers the terminal ligands their charge asks for | **changes the chemistry**; never a default (below) |
| `hydrogens` | places missing hydrogens | by rule first (rings, M6O8 cores, bridging OH, bound methanol, water on a metal), valence after |

`inspect()` names which steps a structure needs before you run any:
`DUPLICATE_SITES`, `COINCIDENT_ATOMS`, `DEUTERIUM`, `CENTRED_CELL`,
`DISORDER`, `SOLVENT`, `OPEN_TRIMERS`, `MISSING_HYDROGENS`.

## Rules

1. **`cap` is the person's decision, not yours.** It adds atoms the file
   never located, chosen by charge balance. Leave it out and the answer
   says, in warning tone, that the trimers were left open and the cell
   is not neutral (`CELL_NOT_NEUTRAL`). Name it and the answer says it
   changed the chemistry (`CHEMISTRY_CHANGED`). Either way, tell the
   person, and ask before naming it.
2. **Chemistry is decided by connectivity and charge**, never by a
   refinement's bond lengths. A bare oxygen on one metal that no
   cluster rule covers is a **water**, not a hydroxide: hydroxide takes
   a proton away, which is a claim about charge only the M6 and trimer
   rules know enough to make.
3. **Bonds drawn by hand refuse the operation** (`OPERATION_REFUSED`):
   ordering cannot carry them through. Prepare the file as deposited,
   then draw.
4. **Keep the solvent when the person asked for the solvated
   structure.** `prepare(steps=[...])` without `solvent`.
5. **After preparing, inspect.** The cell is P1 and its bonds were
   perceived afresh. Check the formula against the paper's, per metal:
   the `disorder` step's sentence says how the ordered cell differs from
   the CIF's declared formula, and that difference is worth reporting.

## What to report

Every `PREPARE_STEP` sentence, by step. For Ni2Cl2BTDD, for example: 27
sites were symmetry copies; the R cell was made primitive (378 → 126
atoms); O4, one atom disordered over two positions across a mirror, was
ordered; 42 waters were removed from the pores; 24 hydrogens were
placed (12 on arene rings, 12 as water on the metals). Then the atom
count, the formula, and any warning.
