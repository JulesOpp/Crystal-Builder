# Porosity and powder patterns

## Porosity

The **Porosity** module (registry key `zeopp`) has two kinds of entry:

- **Zeo++'s own**: `zeopp.diameters`, `zeopp.surface-area`,
  `zeopp.volume`, `zeopp.psd`. These need the `network` binary on PATH
  or in `XTAL_ZEOPP`.
- **The grid twins, "(faster)"**: `zeopp.volume-grid`,
  `zeopp.surface-area-grid`. No binary; a second or two on MFU-4l. They
  read their numbers off the same distance grid the drawn surface comes
  from.

```python
answer = s.run("zeopp.volume-grid", gas="n2")
print(answer.data["report_text"])
rows = answer.data["tables"][0]["rows"]        # label, value, unit, note
```

Rules:

1. **Quote every number with its probe and its radii.** A pore volume
   without "to N2 (1.86 Å), Zeo++'s radii" means nothing. The report
   says both; carry them into your answer.
2. **POAV from the grid reads up to 0.03 of the cell above Zeo++'s
   `-volpo`.** That is Zeo++ falling short of the union of probe
   spheres, not an error here. Do not "correct" one number to match the
   other; say which one you quote.
3. **Channels and pockets.** Accessible volume is the channels'. A
   pocket is space the probe cannot reach from outside.
4. **A borderline window** (within half a grid step of the probe) is
   flagged, never guessed. Rerun with a finer `spacing` or report it as
   unresolved.
5. **D_i and D_f.** Zeo++ gives the largest included sphere (D_i) at a
   Voronoi node, and the largest free sphere (D_f) as the width of a
   bottleneck along an edge. No output carries edge radii, so D_f is a
   number, not a place.
6. **Porosity is a property of the prepared framework.** Solvent still
   in the pores is volume the probe cannot have: `prepare()` first,
   unless the person wants the solvated number.

## Powder patterns

`s.run("pxrd.simulate", source="cu-ka1", two_theta_max=50)` computes
the pattern; `help_for("pxrd.simulate")` lists the profile parameters.

- **Say which radiation.** 2θ moves with the wavelength, so a
  comparison with a measurement must use the same source.
- **`b_overall` at 0 makes the high-angle peaks too strong** against a
  published pattern; 1 to 3 Å² is typical for a comparison.
- **`show_absences=True`** marks where the space group forbids a
  reflection. An unexpected peak over a forbidden position suggests the
  wrong group; one that is not suggests an impurity. A structure in P1
  has no absences.
- A simulated pattern is not a refinement. Fitting it to data is a job
  for a Rietveld package (rietx, GSAS-II), with the CIF from
  `s.export("model.cif")`.
