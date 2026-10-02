Scan the Na-Cl distance in NaCl.cif from 2.7 to 2.9 A in three steps
with UFF, and give me the energy at each point.

---

Not sent to the agent: everything above the rule is the prompt.

The input is `resources/samples/simple/NaCl.cif` (COD 1000041, Fm-3m,
8 atoms in the conventional cell). Every Na-Cl distance is fixed by
the group, so `scan.run` refuses before its first point.

Measured on 2026-10-01: `inspect()` gives `CENTRED_CELL` only.
`run("scan.run", axis1="distance 0, 4", axis1_start=2.7,
axis1_stop=2.9, axis1_steps=3)` -- and `"distance 0, 1"` -- answer
`ok=False` with `MODULE_FAILED` ("the space group ties it") and
`SCAN_SIZE`. Scanning the cell parameter `a` instead runs (6 of 6
points), which is a different scan from the one asked for.

The prompt does not ask for the symmetry to be broken, so the log
must not hold `reduce_to_p1`.
