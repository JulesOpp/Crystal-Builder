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
| `partition` | `acs` with a trimer node only: a pyridyl partitioner on every channel (`tpt`, `tpb`, `tripp`, `tppb`, or `auto`) |

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

## Partitioning the pores (pacs)

`partition` builds a MIL-88-type `acs` framework with a C3 pyridyl on
each channel axis, bonded to the trimers' open metal sites: the
pore-space-partitioned **pacs** frameworks. Give `topology="acs"`, one
open M3O trimer node and one linker; the build is then on `pacs`, which
reads back as the `nia-d` net.

Compatible nodes: N268 (Co), N536 (Cr), N481 (Fe), N270 (Ga), N92 (In),
N198 (Mn), N589 (Ni), N433 (Sc), N287 (Zn) -- M3O trimers whose metals
each have an open octahedral site. `partition.compatible_nodes(catalog)`
asks the catalogue, workspace blocks included. N9 and N354 carry
terminal waters and N422, N554, N590 have tetrahedral zinc: refused.

The partitioner sets the cell's *a* and the linker its *c*, so not
every pair closes. Ask first, without building:

```python
from xtal.mof import partition
node = partition.node_geometry(catalog.building_block("N589"))
span = partition.linker_span(catalog.building_block("E14"))
for fit in partition.rank(node, "E14", span):
    print(fit.sentence())          # predicted a, c; or why it cannot
need = partition.linker_requirement(node, partition.partitioner("tpt"),
                                    pocket=8.0)   # layers 8 A apart
print(need.sentence())
```

A refused pair is a failed build with the same sentence, never a
strained framework. The report's *Pore-space partition* table puts
the predicted cell beside the built one, and the metal-N lengths as
built. Relax before reading the cell as a material's.

## Supertetrahedra on a zeolite net (sod-st)

Any 4-connected net decorated with supertetrahedra is a topology by
name: `sod-st` is `sod` with an M3O trimer (6-c) at every edge and a
tritopic face (3-c) on each supertetrahedron; `mtn-st` is MIL-100's
net (`moo`). Node 0 is the trimer and the next the face. A window is
filled by naming it: `sod-st-f6` puts a filler (6-c pyridyl) in every
6-ring, `sod-st-f4-f6` in both kinds, which makes the trimer 9-c.
Name the plain 6-c trimer (`N536`); the build writes its twin with
the open sites the windows take. A net whose vertex is held flat
(`asv`, `ptt`, `ssf`) or whose window is too wide to read is refused
by name. Ask what a window wants before building:

```python
from xtal.mof import decorate, linkers
from xtal.mof.partition import node_geometry
sod = decorate.decoration("sod")
trimer, face = catalog.building_block("N536"), catalog.building_block("N19")
scale = decorate.trial_scale(sod, trimer, face)   # one PORMAKE pass
for kind in decorate.windows(sod):
    need = decorate.requirement(sod, kind, node_geometry(trimer), face,
                                at_scale=scale)
    print(kind.label(), need.sentence(), linkers.suggest(need, catalog))
```

A filler outside its window's range is a failed build with both
numbers, never a strained framework.

## Judging a build

The build's report (`s.built`, and `data["tables"]`) is the first thing
to read:

1. **Largest RMSD** near 0 Å: the blocks fit their slots. Several
   tenths of an Å means a strained framework.
2. **Closest contact** above ~1.5 Å: no atoms on top of one another.
   Below 1.0 Å the build also answers `BUILD_OVERLAP`, naming the two
   atoms and their blocks. Overlapping atoms are *not* bonded: a
   build's bonds are its blocks' own and its joints, never perceived
   by distance, so a clean build has exactly the graph perception
   would give and a bad one does not hide its overlaps as bonds.
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
