(tutorial-pxrd)=
# Tutorial: a powder pattern, calculated and compared

A powder pattern is the first thing a laboratory measures of a new
framework and the cheapest thing to calculate from a model, so the
two are compared before anything else is believed.  In this tutorial
you calculate the pattern of HKUST-1 for the radiation a laboratory
diffractometer uses, read the reflection table and the two files the
run leaves, overlay a pattern on it, and then see what the
refinement workbench does with the measured one.

```{index} single: tutorial; powder pattern
```

:::{note}
**No measured pattern ships with the application.**  Where this page
needs one it uses a stand-in made from the calculated pattern -- its
2θ shifted by 0.08°, scaled to counts, a background and Poisson noise
added.  A stand-in is not a measurement, and the refinement numbers
below measure the software finding the model it was given, not
anything about a material.  With your own `.xy` (or a diffractometer's
own file) the steps are the same: put its path where this page puts
`standin.xy`.
:::

## Calculate the pattern

1. Open *File ▸ Open Sample ▸* {ref}`HKUST-1 <cmd-sample_hkust1>`.
2. Choose *Modules ▸ PXRD ▸* {ref}`Simulate a pattern…
   <mod-pxrd-simulate>`.  The entry needs no binary and is never
   greyed.
3. Choose the **radiation** the measurement used: *Cu Kα1* is
   1.5406 Å.  2θ runs from 5° to 50° by default, in steps of 0.01°.
   Tick **Mark systematic absences** if you want the second comb.
4. Run it.  The {ref}`Results panel <panel-results_dock>` shows the
   trace, a comb of every reflection, and the reflection table.

```console
$ xtal run pxrd.simulate resources/samples/HKUST1.cif --workspace ws
111 reflections, Cu Ka1 (1.5406 A)
111 reflections between 5 and 50 deg, strongest (2 2 2) at 11.627 deg

Reflections (111)
No.  hkl        d (Å)    2θ (°)  I (%)
  1  (1 1 1)    15.2091   5.806    0.39
  2  (2 0 0)    13.1715   6.705   69.20
  3  (2 2 0)     9.3137   9.488   31.39
  4  (3 1 1)     7.9427  11.131    1.00
  5  (2 2 2)     7.6046  11.627  100.00
  6  (4 0 0)     6.5857  13.434   22.94
[...]
```

The strongest line is (222) at 11.627°; (200), at 6.705°, is 69 % of
it, and (220) at 9.488° is 31 %.  A pattern with those three in that
order, at those angles, is HKUST-1 in this radiation; the weak (111)
at 5.806° and (311) at 11.131° are the lines to look for in a good
pattern.  Every reflection is in the table, whatever its intensity,
because a weak one at the wrong angle is how a second phase shows
itself.

The run leaves two files in its folder: `pattern.xy`, 4501 points
from 5.00° to 50.00°, which loads into whatever you plot with, and
`reflections.txt`, the indexed list with each reflection's
multiplicity.  Intensities are the structure's as written -- a
framework with partial occupancies or its solvent still in is
calculated as it is -- so {doc}`prepare </structure/prepare>` a
deposited structure first, if it is the prepared model's pattern you
want.

## Compare it with a pattern

Make the stand-in, or use your own:

```python
import numpy as np
d = np.loadtxt("ws/HKUST1/pxrd-pxrd-001/pattern.xy")
tt, I = d[::2, 0] + 0.08, d[::2, 1]          # 0.02 deg steps, shifted
counts = 8000 * I / 100 + 150 + 6 * np.exp(-(tt - 5) / 15)
y = np.random.default_rng(1).poisson(counts)
np.savetxt("standin.xy", np.c_[tt, y], fmt=["%.3f", "%d"])
```

In the results panel, **Plot and overlay data…** opens the pattern
window (it needs the `pxrd` extra, matplotlib; the button says so
when it is greyed).  Press **Overlay data…** and open `standin.xy`.
The measured trace is drawn on its own 2θ, never resampled onto the
calculated grid, and both traces are scaled to their own maximum,
because a calculated pattern is in electrons squared and a measured
one in counts -- so compare heights, positions and widths, not
counts ({doc}`/porosity/pxrd`).

**What to look for:**

- *Positions.*  Every calculated tick should have a peak under it, to
  within the zero error of the instrument.  Here the whole pattern is
  0.08° too high -- a specimen-height or zero shift -- and no line is
  out of order.
- *Relative heights.*  A strong line too weak, or the reverse, points
  at the model (occupancy, a guest in the pores, preferred
  orientation) rather than at the cell.
- *Lines the table does not have.*  Look them up against the
  systematic-absence comb before deciding they are a second phase.
- *Widths.*  A calculated pattern's widths are the *Caglioti* terms
  you gave it; a measured one's are the sample's and the instrument's.
  They are not expected to agree until refined.

## What the workbench does with it

The comparison above ends where refinement begins: subtracting the two
is not a plot but a fit.  *Modules ▸ PXRD ▸*
{ref}`Refine against a measured pattern…
<cmd-refine_workbench>` opens the workbench, whose steps run as modules
too.  On the stand-in, from the command line, at Cu Kα1:

```console
$ xtal run pxrd.peaks -p xy=standin.xy -p radiation=cu-ka1 -p start=5 -p finish=30 --workspace ws
33 lines, 24 usable for indexing, Cu Kα1 only (monochromated)
[...]
  1   6.7857  0.0004  13.01575  681.5    0.1015  yes
```

The first fitted line is at 6.7857°: the calculated (200) at 6.705°
plus the 0.08° that was added.  Indexing the lines finds the cell
without being told it:

```console
$ xtal run pxrd.index -p xy=standin.xy -p radiation=cu-ka1 -p start=5 -p finish=30 -p bravais=cF --workspace ws
[...]
12 cells; the first is cF 26.2498 26.2498 26.2498 Å, high confidence
```

26.250 Å against the model's 26.343 Å: 0.35 % short, because the
indexer only allows for a zero error and the pattern has one.
A Pawley fit takes the cell and the group and refines the shift too:

```console
$ xtal run pxrd.pawley -p xy=standin.xy -p radiation=cu-ka1 -p cell="26.34 26.34 26.34 90 90 90" -p space_group="F m -3 m" -p start=5 -p finish=30 -p zero=True --workspace ws
[...]
Rwp 5.75 %   Rp 4.00 %   Rexp 5.76 %   GoF 0.998.  a 26.341(5)   b 26.341(5)   c 26.341(5)   α 90   β 90   γ 90.  V 18277.18 Å³, F m -3 m
```

*a* = 26.341(5) Å, to two thousandths of the 26.343 the pattern was
made from, and a goodness of fit of 1.0 -- as it must be, since
the pattern *is* the model's plus noise.  On a real pattern those
numbers are where you start asking questions.  The Pawley and
indexing runs each took a few seconds here.  Both need the `refine`
extra (RietX).

From a Pawley fit the path is Rietveld: the atoms move, and the
refinement is one undo step on the document.  That, the parameter
table with its *Refine* column, refining with a force field's
energies, and what each statistic means are in
{doc}`/porosity/refinement`; the calculated pattern's own theory is
{doc}`/porosity/pxrd`.

## What to check

- The radiation is the measurement's, with Kα2 if the tube was not
  monochromated.  A wrong wavelength moves every line.
- A constant offset between calculated and measured is an instrument
  zero or specimen height; a growing one is a cell.
- Judge heights only after the model is complete: pores emptied in the
  calculation but full in the experiment change the low-angle lines
  first.

## Where this is explained

{doc}`/porosity/pxrd` for the calculation and the pattern window,
{doc}`/porosity/refinement` for peaks, indexing, Pawley and Rietveld.
