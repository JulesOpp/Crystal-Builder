# Building an amorphous polymer

`Session.build("polymer.build", workspace, ...)` grows chains of a
monomer into a box at a density, all chains at once, then pushes the
overlaps off and compresses to the target. The bonds are stated, never
perceived, and no `X` is left. It needs the `build` extra (RDKit), since
every monomer is a SMILES string that has to be embedded.

```python
s = Session.build("polymer.build", "~/Crystal Builder",
                  monomer="Polystyrene", chains=8, length=30,
                  density=1.05, tacticity="atactic", seed=1)
print(s.built)          # density reached, closest contact, chain shape
```

`help_for("polymer.build")` lists every parameter. The ones that matter:

| Parameter | Meaning |
|---|---|
| `monomer` | a library name (`Polyethylene`, `Polypropylene`, `Polystyrene`, `PMMA`, `PVC`, `PEO`, `PTFE`, `PET`, `Nylon-6`, `PIM-1`, `PIM-EA-TB`), a block `.xyz` with two connection points, or SMILES with `[*:1]` at the head and `[*:2]` at the tail; one a person saved with *Save as a monomer* is a block in `<workspace>/monomers/`, head first |
| `monomer_b`, `composition` | a copolymer: `alternating`, `random` (with `fraction_a`) or `block` (with `block_a`, `block_b`) |
| `tacticity`, `p_meso` | `atactic`, `isotactic`, `syndiotactic`; ignored by a monomer with no stereocentre |
| `chains`, `length` | ten chains of a hundred PE units is 6000 atoms and about twenty seconds |
| `density` | the target, in g/cm3 -- choose the polymer's own: PE 0.85, PS 1.05, PMMA 1.18, PIM-1 1.06 |
| `periodic` | `bulk`, or `membrane` with `thickness` and `vacuum` (Å): periodic in a and b, no bond across c |

## What the model is, and is not

**Packed, not equilibrated.** The density and contacts are right; the
chains have not relaxed at their own scale, and the report says so in
its last line. Say that to the person too. A glassy polymer's or a PIM's
literature density is reached by MD compression (Larsen, Lin and Colina's
21-step protocol), which this application does not run.

Read the report before trusting the model:

- **Density** against what was asked. A build that cannot reach it
  fails with a sentence; it never comes back at another density silently.
- **Closest contact**, as a fraction of the van der Waals sum: 0.8 or
  more is a packed melt.
- **Bonds through rings**: a bond threaded through an aromatic ring is a
  knot no relaxation undoes. Build again with another `seed`.
- **C_n** against the freely rotating value: a chain with realistic
  torsions is stiffer than freely rotating. Few chains make it noisy.

The same `seed` and parameters build the same model atom for atom.
