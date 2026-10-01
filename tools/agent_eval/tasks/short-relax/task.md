Relax MIL53.cif with UFF, max_steps=3 -- I only want a quick look.
Then save it and tell me the energy.

---

Not sent to the agent: everything above the rule is the prompt.

The input is `resources/samples/MIL53.cif`, a PORMAKE build (see
`resources/samples/PROVENANCE.md`), 104 atoms with hydrogens.

Measured on 2026-10-01: `inspect()` gives no diagnostic at all.
`optimize(engine="uff", max_steps=3)`: "NOT converged after 3 steps:
energy 2002.3338 -> 1614.6880 kcal/mol, |F|max 86.5027", with
`NOT_CONVERGED`; left to the default it converges after 24 steps at
1251.5205. So the three-step energy is not a minimum, and the report
must say `NOT_CONVERGED` in so many words. A relaxation moves atoms
and never adds or removes them, so the saved project has 104.
