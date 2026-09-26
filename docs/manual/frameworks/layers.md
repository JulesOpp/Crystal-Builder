# Layer nets

A layered framework is a sheet repeated along the one direction its
net says nothing about.  After this section you can build on any of
the RCSR's 2-periodic nets, set the spacing and the offset between the
sheets, understand why the stacking is set after the build rather
than by it, and read what the log says about the layer it stacked.

```{index} single: layer net
```
```{index} single: interlayer spacing
```
```{index} single: stacking offset
```

## The layers are the RCSR's

PORMAKE's own database holds 3-periodic nets only.  The application's
layer nets are the RCSR's {cite}`okeeffe2008rcsr`: every 2-periodic
net in the RCSR's file that PORMAKE can build on -- 196 of the 200;
the four it cannot (**fzh**, **mtb-a**, **mtc-a**, **sde**) are left
out by name.  Each is written flat in the layer group of its plane
group, in a cell 10 units tall, and held as text; PORMAKE is handed a
file only when one is built on.  **hcb** -- the honeycomb, the net of
Ni{sub}`3`(HITP){sub}`2` -- is, value for value, the hand-written file
it replaced.

In the topology picker the **2D** box shows them and says how many
there are; **3D** is PORMAKE's nets.  A layer answers a search by its
**plane group number**, 1 to 17 (**hcb** is 17, p6mm), and not by the
space group it is built in, because 17 is what the RCSR prints beside
it.  Choosing one adds a line to the description -- *a layer: its
sheets are stacked at the spacing below* -- and enables the two rows
under *How it is built* that only a layer has
({numref}`fig-frameworks-mof-builder-layer`).

:::{figure} /figures/frameworks/mof-builder-layer.png
:name: fig-frameworks-mof-builder-layer
:width: 100%

The MOF builder with the **2D** nets listed and **hcb** chosen for
Ni{sub}`3`(HITP){sub}`2`: the triphenylene on the 3-connected node,
the NiN{sub}`4` on the edge.
:::

A layer is known by its **graph**, not by the folder it came from: the
net's own lattice has rank two and no cycle of it closes along *c*.
So a 2-periodic net you write into your own topology folder is stacked
like one of the RCSR's -- provided it lies in the *ab* plane; a layer
in the *ac* plane is refused rather than stacked along a direction it
is periodic in.  PORMAKE's nets arrive already recorded as 3-periodic,
because asking the graph of all 2400 would cost ten seconds every time
the picker opened, and the RCSR's layers are recorded the other way;
both facts are re-derived by the application's tests.

## Stacked after the build, never by it

:::{note}
**A layer net is stacked after it is built, never by the builder.**
PORMAKE scales the net's cell by one factor chosen for the in-plane
edges, and *c* is scaled with everything else: **hcb** written with
*c* = 10 comes out of a Ni{sub}`3`(HITP){sub}`2` build with
*c* = 107 Å.  The sheet itself comes out flat, so nothing is lost by
throwing that *c* away.  The application rewrites it, moving the
framework, the net drawn on it and the placed blocks together, and puts
the sheets' **mean planes** one spacing apart.
:::

What changes is only the stacking.  Each sheet is moved as a whole to
where the new cell puts it and keeps its own out-of-plane shape, so a
block that is not flat -- a paddlewheel's axial ligands, a hydrogen out
of the ring -- is carried rather than squashed.  In the plane nothing
moves at all: every edge of a layer net lies in its plane, so every
joint the builder made still means what it meant.  Each sheet is
lifted so that its *middle* sits one spacing above the last one's,
because PORMAKE does not put every sheet exactly on its plane (on
**hcb** repeated twice along *c*, one sheet came out 0.021 Å above its
plane and the other on it, and carrying that across made "3.3 Å apart"
read 3.28).

The two settings:

Layer spacing (Å)
: The distance between the sheets' mean planes.  Left empty it is
  **3.4 Å** -- graphite's 3.35 rounded, where π-stacked sheets sit:
  Ni{sub}`3`(HITP){sub}`2` at 3.24, Cu-HHTP at 3.3 -- because a
  layered framework that is a hundred Ångström of vacuum until
  somebody types a number is a default nobody would choose.

Stacking offset
: Where each sheet sits over the one below, as two fractions of the
  **net's own** *a* and *b* -- `1/3, 2/3`, or `0.5, 0`.  The net's
  own cell, before any repeat, so that `1/3, 2/3` means the same slip
  on a 1×1×1 and a 2×2×1.  Left empty the sheets are **eclipsed**, one
  directly over the next, which is how Ni{sub}`3`(HITP){sub}`2`
  stacks.

Repeating the net along *c* (`1x1x2`) puts that many sheets in a cell,
each one step -- the spacing along the normal plus the offset -- above
the last.  The log always says what it did and how thick the sheet is:

```text
stacked the layers 3.240 A apart, eclipsed; one layer is 0.00 A thick
```

The thickness is said every time rather than past a threshold: a
3.0 Å paddlewheel at a 3.4 Å spacing is two sheets 0.4 Å apart, and no
cutoff for "too close" would be anybody's but the application's.  The
*Closest contact* in the verdict is the measurement.

:::{note}
**A spacing or offset given for a 3-periodic net is refused, never
ignored.**  Typing `3.4` into the spacing with **pcu** selected and
pressing Build gives a failed run, not a build with a number quietly
dropped:

```text
pcu is periodic in three directions, so it has no layers to stack and an interlayer spacing means nothing on it; that is for a layer net, such as hcb, hxl, sql or kgm
```

The dialog helps with this: a spacing typed while **hcb** was selected
does not follow you to **pcu**, because the two rows are handed over
only for a layer net.
:::

## Worked example: Ni3(HITP)2 on hcb

```{index} single: Ni3(HITP)2; building
```

Ni{sub}`3`(HITP){sub}`2` is a sheet on the honeycomb: a triphenylene
at each 3-connected vertex and, on each edge, a nickel meeting the two
triphenylenes through two nitrogens each -- so every connection point
of both blocks stands for two atoms.  Its two blocks ship with the application as
**NiHITP_triphenylene** (*3-connected · C18H6*) and **NiHITP_NiN4**
(*2-connected, metal · H4N4Ni*).  Built at the crystal's own spacing:

```console
$ xtal run mof.build -p topology=hcb -p nodes=NiHITP_triphenylene -p edges=NiHITP_NiN4 -p spacing=3.24 --workspace ws
PORMAKE: building hcb-NiHITP_triphenylene-NiHITP_NiN4
topology hcb: 3-c  ·  p6mm (17)  ·  [1 1 1]
loading PORMAKE
placing 1 node type(s) and 1 linker type(s) on 5 slots
orientation consistent: joints disagree by 0.000000 over 3 edge(s), against 0.000000 as found
the fit had already put the nodes the best way round; keeping it
stacked the layers 3.240 A apart, eclipsed; one layer is 0.00 A thick
wrote hcb-NiHITP_triphenylene-NiHITP_NiN4.cif
bonded 12 joint(s) between blocks
drew 3 net edge(s); identifying what came out
the framework is hcb, as asked -- blocks fit to 0.000 A, closest contact 2.00 A, 12 joint(s) bonded, longest joint 1.61 A
[...]
75 atoms; the framework is hcb, as asked -- blocks fit to 0.000 A, closest contact 2.00 A, 12 joint(s) bonded, longest joint 1.61 A

hcb-NiHITP_triphenylene-NiHITP_NiN4

What was built
Topology          hcb
Node blocks       NiHITP_triphenylene
Linkers           NiHITP_NiN4
Net repeated      1x1x1
Interpenetration  none
Node orientation  consistent
Atoms                                    75
Joints bonded                            12
Cell              22.731 x 22.731 x 3.240 A

How well the blocks fit the net
Largest RMSD      0.0000  A
Mean RMSD         0.0000  A
Cell relaxation   0.0000
Closest contact    1.996  A
Longest joint      1.606  A
Joint twist left   0.000
[...]
The net that came out
Asked for              hcb
Built                  hcb
coordination sequence  3, 6, 9, 12, 15, 18, 21, 24, 27, 30
point symbol           6^3
[...]
```

Six joints of two bonds each make the 12; *c* is the 3.24 Å asked
for; and the sheet is flat to the hundredth.  Seen down *c*
({numref}`fig-frameworks-layer-built`) the honeycomb is the net drawn
over the atoms.

:::{figure} /figures/frameworks/layer-built.png
:name: fig-frameworks-layer-built
:width: 90%

Ni{sub}`3`(HITP){sub}`2` built on **hcb** and stacked at 3.24 Å,
seen down *c*, with the net the builder drew.
:::

Two numbers in the output are worth reading against the crystal.  The
*Longest joint* of 1.606 Å is the N--C bond across each cut, against
1.294 Å in the crystal, and it is why *a* is 22.731 Å against the
crystal's 21.552 (+5.5 %): the joint between two chelating ends comes
out about 0.3 Å long, for the reason given under *Limitations* in
{doc}`mof-builder`.  The Ni--N bonds inside the block are the crystal's
to the thousandth.  The build places blocks and stops; a relaxation in
the Force Field panel is where the joint is pulled back.

## Settings

*Interlayer spacing* and *Stacking offset* are two parameters of
{ref}`Build a framework… <mod-mof-build>`, `-p spacing=3.24` and
`-p offset="1/3, 2/3"` on the command line; *Repeat the net* is the
third that matters here.

## Limitations

- Only a layer lying in the *ab* plane is stacked; one in another plane
  is refused.
- A spacing smaller than a sheet is thick is not refused -- the log
  gives the thickness and the verdict the closest contact, and the
  judgement is yours.
- The joint between two chelating ends is about 0.3 Å long
  (`docs/TODO.md`), which on a layer built entirely from such joints
  is a few percent on *a* and *b*.
