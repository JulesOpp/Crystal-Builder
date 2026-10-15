Give me the UFF single-point energy of MIL53.cif with its a axis at
98 %, 100 % and 102 % of its length. Carry the atoms with the cell
(keep their fractional coordinates), keep b, c and the angles as they
are, and relax nothing.

---

Not sent to the agent: everything above the rule is the prompt.

The input is `resources/samples/MIL53.cif`, a PORMAKE build (see
`resources/samples/PROVENANCE.md`), 104 atoms with hydrogens.

A composition task. Raw access loops over three cells in one script.
Over MCP it is `set_cell`, `energy` and `undo` three times, and the
turns column shows the cost.

Measured on 2026-10-15 with `set_cell(a*f, b, c, alpha, beta, gamma)`
(keep="fractional", the default) and `energy("uff")`, undone between
points: 1977.5796 at 0.98 (a = 13.8641), 2002.3338 at 1.00 (the
three-step `short-relax` start), 2053.4819 at 1.02 (a = 14.4300)
kcal/mol. The tolerance of 0.5 kcal/mol allows rounding to one place;
the points are 25 to 50 apart. No `optimize` may be run.
