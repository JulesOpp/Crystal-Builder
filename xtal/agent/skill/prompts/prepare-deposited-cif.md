# Prepare a structure from a database or a paper for a calculation
Prepare $path for a calculation.

1. Call `guide` with the topic `prepare` and read it.
2. `open` $path, then `inspect`. Note the atom count, the formula and
   every diagnostic.
3. Run `prepare` with its default steps. Never add `cap` without
   asking me first.
4. Report every step `prepare` names, then `inspect` again and compare
   the atom count, formula and coordination with step 2.
5. If `OPEN_TRIMERS` or `CELL_NOT_NEUTRAL` is left, tell me and ask
   whether to add the terminal ligands; do not add them yourself.
6. `save`, and give me the path and every diagnostic by its code.
