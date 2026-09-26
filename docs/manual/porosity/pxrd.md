# Powder X-ray Diffraction

*Modules ▸ PXRD ▸* {ref}`Simulate a pattern… <mod-pxrd-simulate>`
calculates a powder diffraction pattern from the structure on screen:
peak positions from the cell and the space group, intensities from
the atoms through structure factors.  After this section you know
what goes into each peak and its width, why the reflection list is
one entry per orbit and what the systematic-absence comb is for,
what the two files in the run folder hold, and how to lay a measured
pattern over the calculation.

```{index} single: powder diffraction
```
```{index} single: PXRD
```
```{index} single: structure factor
```
```{index} single: Lorentz-polarisation factor
```
```{index} single: systematic absences
```
```{index} single: pseudo-Voigt
```
```{index} single: Caglioti relation
```

## What the code calculates

Peak *positions* need only the cell and the {term}`space group`'s
{term}`systematic absences <systematic absence>`.  Peak *intensities*
need the atoms, and they are the reason to calculate a pattern rather
than a comb of tick marks: a
phase is identified by which peaks are strong, not only by where they
are.  The application's code records where its science came from: the
Lorentz-polarisation factor, the multiplicity count, the Debye-Waller
attenuation, the pseudo-Voigt profile and the Caglioti width relation
were ported from the author's *DataPlotter* application for measured
patterns, which had been checked against published ones; what
changed in the port is that the input is the open structure rather
than a CIF on disk.

### Positions

Each reflection $hkl$ has a $d$-spacing from the cell, and Bragg's
law puts it at

$$
\lambda = 2 d \sin\theta ,
$$ (pxrd-bragg)

so the angle moves with the **Radiation**: Cu Kα1 (1.5406 Å), the Cu Kα
average (1.5418 Å), Mo Kα1 (0.7093 Å), Co Kα1 (1.7890 Å), Ag Kα1
(0.5594 Å), or a **Wavelength** of your own.  A pattern compared with a
measurement has to be calculated for the same source.  A reflection
this wavelength cannot reach ($|\sin\theta| > 1$) is left out rather
than treated as an error.

### Intensities

Each reflection's intensity is

$$
I_{hkl} = m_{hkl} \, |F_{hkl}|^2 \, \mathrm{LP}(2\theta) \, T(\theta),
$$ (pxrd-intensity)

with:

- $|F_{hkl}|^2$ the structure factor, from gemmi's calculator
  {cite}`wojdyr2022gemmi` over the atoms of the structure;
- $m_{hkl}$ the multiplicity, the number of symmetry-equivalent
  reflections that share the $d$-spacing;
- the Lorentz-polarisation factor of an unmonochromated powder,

  $$
  \mathrm{LP} = \frac{1 + \cos^2 2\theta}{\sin^2\theta \cos\theta} ,
  $$ (pxrd-lp)

  which is what turns $|F|^2$ into an observable powder intensity --
  without it the low-angle peaks, the ones a MOF is identified by,
  come out far too weak.  It diverges as $2\theta \to 0$, which is why
  half a degree is the floor of the range;
- the thermal attenuation

  $$
  T = \exp\!\left( -\frac{2 B \sin^2\theta}{\lambda^2} \right)
  $$ (pxrd-dw)

  with one **Overall B** for every atom, because most structures
  carry no displacement parameters and one number is the honest
  amount of detail to offer.  Left at zero the high-angle peaks come
  out systematically too strong against a published pattern; the help
  text says 1 to 3 Å² is typical.

The pattern is scaled so its strongest point is 100, because the
absolute value is in electrons squared times a geometry factor and
means nothing next to a measured pattern's counts.

### Profiles

Each reflection is spread by a unit-area profile of width FWHM.
**Peak shape** offers a Gaussian, a Lorentzian, or the pseudo-Voigt,
the linear mixture of the two by a **Lorentzian fraction** $\eta$
{cite}`wertheim1974pseudovoigt`,

$$
P(x) = \eta \, L(x) + (1 - \eta) \, G(x),
$$ (pxrd-pv)

which approximates the true Voigt convolution of sample and
instrument broadening; the help text calls it the usual choice for
laboratory data, with 0 a pure Gaussian and 1 a pure Lorentzian.  The
width follows the Caglioti relation {cite}`caglioti1958width`,

$$
\mathrm{FWHM}^2 = U \tan^2\theta + V \tan\theta + W ,
$$ (pxrd-caglioti)

in degrees squared, with **Caglioti U**, **V** and **W** defaulting to
0.004, −0.002 and 0.010, a typical laboratory diffractometer.  Where a
published triple dips negative at low angle the width is zero and the
reflection is dropped rather than drawn imaginary.  Each profile is
summed onto the 2θ grid of **Step** (0.01° by default -- it has to be
several times finer than the peak width or the peaks come out as
spikes), and evaluated only within twelve widths of its centre, which
is what keeps a thousand reflections on a ten-thousand-point grid
from being a ten-million-point sum.

### The reflection list

The list is every **symmetry-inequivalent reflection in range, one
per orbit**, with the equivalents counted into the intensity through
$m_{hkl}$ -- which is the list a reference pattern prints.  gemmi
supplies the asymmetric reflections for the group; 98 of them cover
MFU-4l to 50° where the same crystal expanded to {term}`P1` has 3177,
and both are right, because each answers what *this* structure
allows.

Several reflections can land at the same 2θ -- 333 and 511 share a
$d$-spacing in any cubic cell -- and they are *not* folded into one
row.  The code records that folding was tried and taken back out: it
made the table shorter and stopped the list describing the structure
it was calculated from.  The pattern is the same either way.

:::{note}
**The structure is simulated as it is.**  Nothing detects,
standardises or otherwise improves the symmetry: a crystal you
expanded to P1 is calculated in P1, with the same pattern and a
reflection list three times as long.  A {term}`dummy atom` is held
back at the door -- `X` has no scattering factor -- as it is from
every other calculation.
:::

### Systematic absences

With **Mark systematic absences** on, a second comb is drawn under
the pattern, in its own colour, at every 2θ where this space group
forbids a reflection: every $hkl$ the *lattice* offers in range, minus
the ones the group allows.  An unexpected peak in a measurement is
either an impurity or the wrong space group, and which one depends on
whether it sits over a forbidden position.  A structure in P1 has no
forbidden positions, because P1 forbids nothing.

:::{warning}
**Calculated intensities assume the structure is complete.**  The
caveat is printed under the pattern and on every row of the table,
in the code's words: *A framework refined without its disordered
solvent, or with partial occupancies, gives peak positions that are
right and intensities that need not be -- and a real powder shows
preferred orientation on top of that.*  Positions can be exactly
right while intensities are not.
:::

## Running it

1. Open the structure and choose *Modules ▸ PXRD ▸ Simulate a
   pattern…*.  The entry needs no binary and no extra: it is never
   greyed.
2. Choose the radiation, the 2θ range (5° to 50° by default -- the
   help text says fifty degrees is where a laboratory MOF pattern
   stops being worth plotting), the profile and, if you want the
   second comb, **Mark systematic absences**.
3. The {ref}`Results panel <panel-results_dock>` shows the trace with
   a comb of every reflection under it -- including the ones too weak
   to see, which is what says a shoulder on a peak is two reflections
   -- and the reflection table: number, $hkl$, $d$ in Å, 2θ in
   degrees and $I$ as a percentage of the strongest, every row with
   its multiplicity and $|F|^2$ in its note.  There is no intensity
   threshold on the table, because a weak reflection is exactly what
   somebody deciding whether a shoulder is a second phase is looking
   for.
4. Two files are left in the run folder under the structure's entry
   in the {term}`workspace`: `pattern.xy`, the calculation as two
   columns of 2θ and intensity with a comment header naming the
   source, formula and space group, which is what loads into whatever
   you already plot with; and `reflections.txt`, the indexed list.
   Neither is derivable from the other by somebody reading the folder
   later.  With no workspace open nothing is written, and the answer
   is the picture and the table.

## The pattern window and a measured overlay

```{index} single: pattern window
```
```{index} single: overlay; measured pattern
```

The panel draws the pattern with nothing installed.  Under it, **Plot
and overlay data…** opens the pattern window
({numref}`fig-pattern-window-hkust1`), which needs the `pxrd` extra
(matplotlib {cite}`hunter2007matplotlib`; see
{doc}`/quickstart/installation`).  Without it the button is greyed
with the reason: *matplotlib is not installed, so a pattern can be
looked at in the panel but not zoomed, overlaid or exported as a figure*,
followed by the install command.  *Preferences* lists the extra as
*Pattern plot window*.

:::{figure} /figures/porosity/pattern-window-hkust1.png
:name: fig-pattern-window-hkust1
:width: 90%

The pattern window on HKUST-1's calculated pattern, Cu Kα1, 5° to
50°, with the allowed and forbidden combs.  The 2θ boxes in the
toolbar always show the axis's own limits, after a zoom too.
:::

The window is modeless, so it stays open while you work on the
structure it came from.  Its buttons:

- **Overlay data…** reads a measured pattern (`.xy`, `.xye` or
  `.dat`: whitespace- or comma-separated 2θ and intensity, a header,
  blank lines and a third column of errors all tolerated) and draws it
  on top.  **Every trace is scaled to its own maximum**, because a
  calculated pattern is in electrons squared and a measured one in
  counts, and on one absolute axis one of them is a flat line; the
  axis is labelled as a percentage for that reason, and the sentence
  under the plot says so once a file is overlaid.  **The measured file
  is not resampled onto the calculated grid**: it is drawn on its own
  2θ, because interpolating it invents intensity between the points
  that were counted.  What that costs is that the two cannot be
  subtracted here; subtracting them is refinement, not comparison.
- **Save figure…** writes the figure, raster or vector by the suffix.
  In a vector file the text stays text -- the axis labels arrive in a
  vector editor as editable labels rather than outlined shapes.
- **Save pattern…** writes the calculated trace as `.xy`.

## Worked example: HKUST-1

The shipped HKUST-1 (*File ▸ Open Sample ▸* {ref}`HKUST-1
<cmd-sample_hkust1>`; Fm-3m) from the command line, with the absences
asked for, in 0.3 s:

```console
$ xtal run pxrd.simulate resources/samples/HKUST1.cif -p show_absences=True --workspace ws
111 reflections, Cu Ka1 (1.5406 A)
111 reflections between 5 and 50 deg, strongest (2 2 2) at 11.627 deg

PXRD, Cu Ka1 (1.5406 A)

Calculated pattern, Cu Ka1 (1.5406 A)
    5.00  ##############################
    7.25  ##############
    9.50  ############################################
   11.75  ##########
[...]
          2-theta (degrees)

Reflections (111)
No.  hkl        d (Å)    2θ (°)  I (%)
  1  (1 1 1)    15.2091   5.806    0.39
  2  (2 0 0)    13.1715   6.705   69.20
  3  (2 2 0)     9.3137   9.488   31.39
  4  (3 1 1)     7.9427  11.131    1.00
  5  (2 2 2)     7.6046  11.627  100.00
  6  (4 0 0)     6.5857  13.434   22.94
  7  (3 3 1)     6.0435  14.646    3.57
  8  (4 2 0)     5.8905  15.028    4.90
  9  (4 2 2)     5.3772  16.472    4.82
 10  (3 3 3)     5.0697  17.479   10.48
 11  (5 1 1)     5.0697  17.479    0.51
 12  (4 4 0)     4.6568  19.042   16.87
[...]
111  (12 8 0)    1.8266  49.887    0.71

Symmetry-inequivalent reflections, one per orbit, with the equivalents counted into the intensity -- which is the list a reference pattern prints.  I is a percentage of the strongest reflection in range.

C3 Cu H O, F m -3 m.  Calculated intensities assume the structure is complete.  [...]
```

Rows 10 and 11 are the cubic coincidence above: 333 and 511 at the
same $d$, kept as two rows.  The text histogram is the command line's
rendering of the trace; the panel and the pattern window draw it
properly.  The run folder holds `pattern.xy` -- 4501 points from 5.00°
to 50.00° at 0.01° --

```text
# Calculated powder pattern, Cu Ka1 (1.5406 A)
# C3 Cu H O  F m -3 m
# 2-theta (degrees), intensity (% of the maximum)
5.00000  0.000601183
5.01000  0.000616319
[...]
```

and `reflections.txt`, the same list with the multiplicity in its
last column:

```text
# Calculated powder pattern, Cu Ka1 (1.5406 A)
# C3 Cu H O  F m -3 m
# 2-theta (degrees), intensity (% of the maximum)
#  No.    h   k   l          d      2-theta      I(%)   mult
     1      1   1   1    15.2091       5.8062      0.39      8
     2      2   0   0    13.1715       6.7054     69.20      6
     3      2   2   0     9.3137       9.4883     31.39     12
     4      3   1   1     7.9427      11.1308      1.00     24
     5      2   2   2     7.6046      11.6274    100.00      8
[...]
```

% TODO(Sam): the run folder this wrote was `ws/HKUST1/pxrd-pxrd-003`,
% because the folder is named <module>-<action kind>-NNN and the PXRD
% action's kind is "pxrd" rather than "simulate" (the Zeo++ entries'
% kinds match their names).  Reported; the page does not name the
% folder until that is settled.

## Practical notes

- Calculate for the source the measurement used; the 2θ scale is the
  wavelength's.
- Overlay before you judge a match by eye: both traces are scaled to
  their own maximum, so heights compare and counts do not.
- A weak reflection at an unexpected 2θ is in the table whatever its
  intensity; the systematic-absence comb says whether the position is
  one this group forbids.
- The intensities are those of the structure as written.  A
  framework carrying partial occupancies or missing its solvent is
  calculated as such; {doc}`Prepare for simulation
  </structure/prepare>` is where a deposited model is made whole
  first, if that is what you want the pattern of.

## Settings

{ref}`Simulate a pattern… <mod-pxrd-simulate>` in the generated
reference lists every setting with its range and default.  From the
command line it is `xtal run pxrd.simulate FILE`, with `-p` for any of
them (`xtal modules` prints the names).

## Limitations

- One overall $B$ for every atom; the per-atom displacement
  parameters of a refinement are not used.
- Profiles are pseudo-Voigt, Gaussian or Lorentzian with a Caglioti
  width; there is no axial-divergence or asymmetry correction, no
  background and no preferred-orientation model.
- The Lorentz-polarisation factor is the unmonochromated powder
  form of {eq}`pxrd-lp`.
- The reflection list and the pattern are those of the structure as
  written, with partial occupancies and missing solvent taken
  literally; see the caveat above.
- The pattern window compares; it does not subtract, fit or refine.
- The window and the vector export need the `pxrd` extra; the pattern,
  the table and the `.xy` file do not.
