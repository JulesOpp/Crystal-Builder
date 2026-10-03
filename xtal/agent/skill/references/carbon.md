# Building a disordered carbon

`Session.build("carbon.build", workspace, ...)` makes a zeolite-templated
carbon or a schwarzite: one connected sheet of carbon that follows a
**net**, cut into ribbons, with Stone-Wales defects and terminated edges,
at the carbon **density** asked for. Nothing optional is needed.

```python
s = Session.build("carbon.build", "~/Crystal Builder",
                  net="dia", repeat="2x2x2", density=0.42,
                  fluorine=0.29, hydrogen=0.07, seed=0)
print(s.built)          # cell, density, H/C F/C O/C, rings -- read them
print(s.inspect())
```

`help_for("carbon.build")` lists every parameter. The ones that matter:

| Parameter | Meaning |
|---|---|
| `net` | a 3-periodic RCSR net: `dia` (FAU's supercages, the ZTC default), `srs` (a gyroid schwarzite) |
| `repeat` | cells of the net the disorder is drawn over: `2x2x2`, or `2` |
| `density` | g/cm³ of framework carbon; the cell is **solved** for it, not chosen |
| `coverage` | share of the closed sheet kept: 1 is a closed schwarzite, lower is narrower ribbons and more edge carbon |
| `radius_ratio` | strut radius over edge length; the innermost sheet must stay 2.5 Å from its edge |
| `layers`, `interlayer` | stacked sheets, never bonded, 3.35 Å apart by default |
| `stone_wales` | 5-7-7-5 pairs per 100 rings, on top of what the net's shape fixes |
| `hydrogen`, `fluorine`, `oxygen` | per carbon of the result; `ether`, `hydroxyl`, `carbonyl` split the oxygen |
| `relax` | `uff` (default, positions only at the solved cell) or `none` |
| `seed` | the same seed and recipe build the same carbon |

## What to check

- **One piece, percolating in 3 directions** per layer is the point of
  the builder; the report says both. A refusal saying the ribbons do not
  run through the cell means they are too narrow: lower `coverage` is
  *more* edge, so raise it, or raise `density`.
- **The rings are partly fixed.** Gauss–Bonnet makes the closed sheet's
  sum of (6 − ring size) six times its Euler characteristic: dia's cell
  needs 96 more heptagon-equivalents than pentagons whatever the seed.
  Ask for Stone-Wales pairs, not for a ratio of five-, six- and
  seven-membered rings.
- **A ratio there is too little edge for is said, not faked**: the
  report's notes name what was short. Edge carbons with no room for a
  termination stay bare, as a real ZTC's do.
- **Bonds are stated, never perceived.** Do not recalculate bonds on a
  built carbon: a curved sheet's carbons are closer across a pore than a
  bond in places.
