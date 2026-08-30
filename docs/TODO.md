# TODO

Work that is wanted but not yet scheduled into a phase.
[docs/PLAN.md](PLAN.md) holds the roadmap; this file holds everything
that came up while using the application and does not belong to a phase
yet.  An entry gets deleted when it ships, not ticked.

---

## Appearance

### ORTEP draw style

A draw style that shows atoms as **thermal ellipsoids** rather than
spheres — the picture every crystallographer expects from a refined
structure, and the one that makes a bad refinement obvious at a glance.

* A new entry in `xtalapp/viewport/styles.py`, plus the geometry that
  fills it.  The registry is designed for exactly this, so no existing
  style changes.
* Needs anisotropic displacement parameters on the site, which
  `Site.u_iso` does not carry: `Site` needs a `u_aniso` (the U11, U22,
  U33, U12, U13, U23 of the CIF `_atom_site_aniso_*` loop), the CIF
  reader needs to read that loop, and the writer needs to write it
  back.  `Structure` already round-trips through gemmi, so the data is
  there to be picked up.
* Rendering is a sphere glyph with a per-atom 3×3 transform: VTK's
  tensor glyph mapper takes the U matrix directly, so the scene
  model gains an `(M, 3, 3)` array next to `radii` and the actor
  count does not change.
* The probability level (50%, 90%) is a view setting, not structure
  data, and belongs in `ViewSettings`.
* Sites with only `u_iso` fall back to a sphere of the equivalent
  radius; sites with neither fall back to the current ball-and-stick
  radius.  Both cases have to be visible in the picture rather than
  silently drawn as if they were measured.

## Editing

### Arrow buttons on translate and rotate

The Move dock takes a number and applies it once.  Nudging — hold
the arrow, watch the fragment slide — is how the tool is actually
used, and it is missing.

* A pair of arrows per axis in the translate group, and a pair for the
  rotation angle: one step per click, auto-repeating while held.
* The command stack already merges repeated moves into one undo step
  (`Command.merge_with`), so a burst of nudges must arrive as one
  Ctrl+Z, not forty.  `MoveSites` merges today; check that it still
  does under auto-repeat and that the merge window ends when the button
  is released.
* The step size is the spinbox value, so the existing controls keep
  their meaning and the arrows are pure acceleration.
* Same treatment for rotation about the chosen axis.

### Make planar

A button that takes the selected atoms and **flattens them onto their
best-fit plane** — the fastest way to fix an aromatic ring that came
out of a builder or an optimiser slightly puckered.

* Best-fit plane by SVD of the mean-centred cartesian coordinates: the
  plane normal is the singular vector with the smallest singular value.
* Each selected atom moves along that normal onto the plane, which is
  the smallest displacement that makes them coplanar.
* Belongs in `xtal/core/transforms.py` as a free function, with a
  `PlanarizeSites` command over it in `xtal/commands/atoms.py` — the
  same shape as `TransformSites`, so it is undoable and scriptable.
* The button belongs in the Move dock next to mirror, and must report
  the largest displacement it made: "planarised 6 atoms, moved by up to
  0.08 Å" is the difference between a fix and a silent corruption.
* Symmetry: like every other move, this acts on whole orbits. Fewer
  than three atoms have no plane, and the button says so rather than
  doing nothing.
