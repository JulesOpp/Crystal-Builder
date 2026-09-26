# Measure

The *Measure* menu takes distances, angles and torsions between atoms,
fits planes through them, and measures the angles between planes.
After this page you can measure what is selected in one keystroke,
read the *Measure* panel, and know why a measurement follows the
crystal when the atoms move but never appears on the undo stack.

## Measuring what is selected

```{index} single: measurement; distance, angle, torsion
```

1. Select the atoms, in the order the measurement reads them.
2. Press {ref}`Measure selection <cmd-measure_selection>`
   ({kbd}`Ctrl+M`).  Two atoms are a distance, three an angle about
   the middle one, four a torsion; the status bar gives the number
   and it joins the *Measure* panel's table -- for two Zn of MOF-5,
   *Zn1 - Zn1   10.6895 A*; for three, *Zn1 - Zn1 - Zn1   90.00 deg*.
3. With bonds selected and no atom in hand, the same command measures
   every selected bond, one distance each and announced once:
   clicking a bond and pressing {kbd}`Ctrl+M` is the shortest way to
   ask how long it is, and a box drawn round a linker followed by
   {kbd}`Ctrl+M` measures the eleven bonds inside it.

The entry is enabled exactly when it would do something -- two to four
atoms, or bonds with no atom -- and the context menu names the
measurement the selection admits: *Measure distance* over two atoms,
*Measure angle* over three, *Measure dihedral* over four, *Measure
bond length* over a bond and *Measure 11 bond lengths* over eleven.
The *Measure* mouse mode takes the same measurements by clicking; see
{doc}`mouse modes <mouse-modes>`.

A distance is the minimum-image one, like every other measurement: a
bond you drew to a further image reports the near distance, and says
so by being a distance rather than claiming to be that bond.  Two
bonds between the same pair in different images give one row.

## Planes

```{index} single: plane; defining and measuring
```

Planes are made from the selection rather than from a run of clicks,
because three atoms determine one and a ring is six.

1. Select three or more atoms and press {ref}`Define plane from
   selection <cmd-define_plane>` ({kbd}`Ctrl+Shift+P`).  Exactly three
   atoms give the plane through them; more are fitted by least
   squares, and the status bar reports the fit -- *Plane 1: Zn1, Zn1,
   Zn1, Zn1, Zn1, Zn1   rms 3.563 A* for six atoms that are nowhere
   near coplanar, a number close to zero for a ring.  The plane joins
   a list of its own in the *Measure* panel, named *Plane 1*, *Plane
   2*, and is drawn as a translucent quad with its normal on it while
   *View ▸ Show ▸ Planes* is on; choose rows in the list to draw only
   those, and give a plane a colour from the same list.
2. With two or more planes defined, {ref}`Angle between planes
   <cmd-plane_angle>` measures the angle between them -- one row per
   pair, because there is no such thing as *the* angle between three
   planes.  With one plane it says *define at least two planes to
   measure between them*.
3. {ref}`Clear planes <cmd-clear_planes>` and {ref}`Clear
   measurements <cmd-clear_measurements>` empty the two lists; each
   is enabled only while its list has something in it.  A single row
   is removed from the panel.

:::{note}
**Measurements are notes about the crystal, not changes to it.**
Nothing here is an undo step and nothing marks the document modified,
but they do follow the crystal: move an atom and the numbers change,
because each one is taken again over its atoms; delete an atom and
the measurements and planes that named it go with it.  A plane is
re-fitted from its atoms after every move, which is the only way an
interplanar angle can be trusted after an optimisation.  Measurements
and planes are part of the session, so *Save File* keeps them in the
project and *Export…* does not.
:::

A {term}`dummy atom` measures like any other atom.  *Structure ▸ Add
centroid…* on a ring, then a distance from the centroid to a metal, is
how a metal--ring distance is taken.
