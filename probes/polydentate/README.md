# Polydentate probes

Evidence for the MOF-builder work in
[docs/ROADMAP.md](../../docs/ROADMAP.md) § 2, written 2026-09-20
against `f0fafe7`.  **Not shipped code and not tests** — throwaway
scripts kept because their numbers decided the design, and because
`blocks/` took real work to cut.

Run from the repository root:

```bash
python probes/polydentate/mkblocks.py         # cut the four blocks
python probes/polydentate/p1_mfu4l.py         # the objective, MFU-4l
python probes/polydentate/p1b_costs.py        # which cost definition
python probes/polydentate/p1d_ni_angle.py     # the objective, Ni-HITP
python probes/polydentate/p2_lever.py         # P2, P3 and P5
python probes/polydentate/p4_reads.py         # the vendored reader
python probes/polydentate/p7_shipped.py       # all 867 shipped blocks
python probes/polydentate/p89_supercell_layer.py
python probes/polydentate/p9b_spacing.py
python probes/polydentate/p6_10.py
python probes/polydentate/phase6_settle.py
```

The last one is named for a **phase** and not for a Phase 1 probe:
`pN_` is the numbering of the ten questions this design was measured
against before any of it was built, and `phase6_settle.py` came
afterwards, with Phase 6.  It holds the numbers
[docs/ROADMAP.md](../../docs/ROADMAP.md) § 2 carries under *What
Phase 6 changed*, and the evidence behind *A repeated net cannot be
told to flip its neighbours* in [docs/TODO.md](../../docs/TODO.md)
§ Modules -- both measured on the blocks below.

`blocks/` holds the four blocks cut out of `MFU4l.cif` and
`NiHITP.cif`, and `nets/hcb.cgd` a honeycomb layer written in
PORMAKE's own dialect in a 3-D cell.

The four **shipped** with Phase 7 and live at
`xtal/mof/library/blocks/`, under the names the picker shows:
`MFU4l_Kuratowski`, `MFU4l_BTDD`, `NiHITP_triphenylene` and
`NiHITP_NiN4`.  These stay as they are, byte for byte, because
`mkblocks.py` is the record of how they were cut and the probes above
read them by the names they were cut under; change a block and change
it there, not here.  `nets/hcb.cgd` is still a draft and belongs to
Phase 8.
