# Building a framework on a net

`Session.build("mof.build", workspace, ...)` runs the vendored PORMAKE
builder: pick a **net** (an RCSR topology), put a **node** block in each
node slot and a **linker** on each kind of edge, and it places,
orients, bonds and files the result. It needs the `ase` extra
(`capabilities()` says whether it is installed).

```python
s = Session.build("mof.build", "~/Crystal Builder",
                  topology="pcu", nodes="N16", edges="E14",
                  repeat="2x2x2")
print(s.built)          # the build's own tables -- read them
print(s.inspect())
```

`help_for("mof.build")` lists every parameter. The ones that matter:

| Parameter | Meaning |
|---|---|
| `topology` | the RCSR name: `pcu`, `dia`, `tbo`, `soc`, `hcb` … 2599 nets ship |
| `nodes` | `N16` for a net with one kind of node, `0=N19,1=N59` for several |
| `edges` | `E14`, or `0-0=E32,0-1=E14`; empty joins nodes directly |
| `repeat` | tile the net first: `2x2x2`, or `2` |
| `orientation` | `consistent` (default) or `as-found` (PORMAKE's own) |
| `spacing`, `offset` | layer nets only: sheet spacing in Å (default 3.4) and stacking offset |
| `interpenetration` | copies threaded through each other, where the most room is |

## Choosing blocks

A block fits a slot only when it has as many connection points as the
slot has neighbours. The catalogue answers that without guessing:

```python
from xtal.mof.catalog import Catalog, matches_composition
catalog = Catalog.default()
net = catalog.topology("pcu")
print(net.summary(), [slot.label for slot in net.slots()])
print(catalog.building_block("N16").summary())   # 6-connected, C6O13Zn4
six = catalog.fitting(6)                          # every 6-connected block
zinc = [b.name for b in six if matches_composition(b, "4Zn")]
```

Known combinations: MOF-5 is `pcu` + `N16` (the Zn4O(CO2)6 cluster) +
`E14` (the benzene of BDC), 2x2x2 for the conventional cell. HKUST-1 is
`tbo`. A layer net (`hcb`, `sql`, `kgm`, `hxl`) builds sheets that are
stacked afterwards, never by the builder.

## Judging a build

The build's report (`s.built`, and `data["tables"]`) is the first thing
to read:

1. **Largest RMSD** near 0 Å: the blocks fit their slots. Several
   tenths of an Å means a strained framework.
2. **Closest contact** above ~1.5 Å: no atoms on top of one another.
3. **The net that came out** equals the one asked for. If `Built` is
   not `Asked for`, the framework is not the one requested.
4. **Joints bonded**: the count in the headline. MOF-5 on `pcu` 2x2x2
   has 48.
5. **Joint twist left**: how far the faces across each linker are from
   agreeing, which the orientation rule could not fix. Non-zero is
   reported, not an error: `pcu` 1x1x1 on N16 is 6.0 over 3, because a
   single slot cannot alternate.

Then `inspect()`: formula (MOF-5 is `C24H12O13Zn4` per formula unit),
detected group (a PORMAKE build is written in P1; MOF-5's coordinates
detect Fm-3m), coordination of the metal.

## Rules

- **A connection point is an `X` 0.75 Å from the centroid of the atoms
  it hangs off**, not a bond length. A block of your own written with a
  1.4 Å X builds every linker bond twice too long, and nothing reports
  it.
- **Which way round a symmetric node goes is a tie**, broken by default
  so the faces across every edge agree (`orientation="consistent"`).
  That is what makes MOF-5's clusters alternate. `as-found` is PORMAKE
  byte for byte; use it only to compare with PORMAKE.
- **A build is filed as one entry with one CIF.** `s.path` is that CIF;
  `s.save()` writes the project beside it.
- **Relax a build before quoting its geometry.** PORMAKE places rigid
  blocks; bond lengths at the joints are the blocks', not the
  material's. See `calculations.md`.
