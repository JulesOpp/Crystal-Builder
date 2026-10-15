HKUST1.cif and MOF-5.cif: which has the shorter metal-metal distance,
and how long is it?

---

Not sent to the agent: everything above the rule is the prompt.

The inputs are `resources/samples/HKUST1.cif` (Cu paddlewheels) and
`resources/samples/MOF-5.cif` (Zn4O clusters).

A composition task. Raw access answers with numpy over the positions.
MCP has no distance query yet (sub-project B), so this measures that
gap.

Measured on 2026-10-15 with ase (`get_all_distances(mic=True)` over the
Cu or Zn atoms): HKUST-1 Cu-Cu 2.6302 A, MOF-5 Zn-Zn 3.1727 A. The
report must name HKUST and give 2.63 within 0.01 A.
