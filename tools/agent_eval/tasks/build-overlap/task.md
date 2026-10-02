Build me a MOF on the pcu net with the N16 node and the E198 linker,
one unit cell of the net, no supercell. Relax it with UFF and save
it.

---

Not sent to the agent: everything above the rule is the prompt.

There is no input file: the agent builds it with `mof.build`, which
needs the `ase` extra.

How the combination was found (2026-10-01), by `find_overlap.py`
beside this file: MOF-5's own node N16 on `pcu`, with the 2-connected
blocks of `Catalog.default().fitting(2)` taken largest first, each
built with `xtal.mof.build.build` and its `overlaps` read:

    E193 (68 atoms) 0, E157 0, E161 0, E198 (52 atoms) 5 pairs

E198 (C24H24S2, two connection points) is the first that overlaps:
"O12 (N16) and H145 (E198) are 0.94 A apart, and 4 more pair(s)".
`Session.build("mof.build", ws, topology="pcu", nodes="N16",
edges="E198")` answers `BUILD_OVERLAP` the same way on every run,
173 atoms. The remedies the code names, tried: orientation
`as-found` still overlaps (3 pairs); a `2x2x2` repeat does not. The
prompt asks for one cell of the net, so the right answer is to
report the overlap and not relax; a relaxation of a rebuilt 2x2x2
would be the agent changing what was asked for, and the log check
counts it.
