# Prepare a structure from a database or a paper for a calculation
Prepare $path for a calculation.

1. Call `guide` with the topic `prepare` and read it.
2. `open` $path, then `inspect`. Note the atom count, the formula and
   every diagnostic.
3. Run `prepare` with its default steps. Never add `cap` without
   asking me first.
4. Report every step `prepare` names, then `inspect` again and compare
   the atom count, formula and coordination with step 2.
5. If `OPEN_TRIMERS` is left, tell me and ask whether to add the
   terminal ligands (`cap`); do not add them yourself. If
   `CELL_NOT_NEUTRAL` is left, say so; do not add or remove anything
   to balance it.
6. `save`, and give me the path and every diagnostic by its code.
