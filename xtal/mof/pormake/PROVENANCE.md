# PORMAKE, vendored

Upstream: **PORMAKE 0.2.3**, https://github.com/Sangwon91/PORMAKE
Licence: **MIT**, "Copyright (c) 2022 Sangwon" — `LICENSE.md`, unchanged.
Taken from the published wheel, verified against its `RECORD` hashes
before anything was edited.

This project is MIT too, so vendoring is clean provided the notice
travels and the modifications are written down. That is what this file
is: **every difference from upstream 0.2.3 is listed below**, so the
next person can diff rather than guess.

## Why it is here at all

The MOF builder was the single feature a packaged user could not have.
`pip install pormake` is 44 packages and ~889 MB — larger than the rest
of the application put together — so `packaging/bundle.py` excluded it
and *Preferences → Optional features* explained the absence.

The 889 MB turned out to be almost entirely two dependencies PORMAKE
barely uses: **one gradient** and **one function call**. Removing those
two brings the whole builder in on top of the numpy, scipy and spglib
that already ship, and measured on a real macOS bundle rather than
estimated it costs **5.2 MB of bytes**: 2.85 MB of nets and blocks,
1.41 MB of `ase` and the twelve vendored modules compiled into the
PyInstaller archive, and 0.95 MB of code-signature hashes, which grow
with the file count. So it is vendored and trimmed rather than
excluded, and there is nothing left for a user to configure.

`ase` is nearly all of that 1.41 MB, and it is that small because
it is traced and not collected whole: PyInstaller reaches 200 of its
1218 modules, which is every one the builder touches. See `COLLECT` in
`packaging/bundle.py`, and "On the size" in `docs/PACKAGING.md` for
the rest of the measurement.

(The database is 3271 small files, so `du` reports it as 13.5 MB where
the bytes are 2.85, and the installed bundle grows by 15.8 MB rather
than 5.2 for the same reason. The 13.5 is the honest number for an
*installed* bundle, which pays a 4 KB block per file; the 2.85 is what
a download carries.)

An external-tool route — point the application at a conda environment,
the way it finds DFTB+ — was designed and proven working first, then
rejected: it still asks somebody to configure something.

## What was removed, and what replaced it

### `networkx` — declared, never imported

Deleted from the dependency list. Nothing in the twelve modules imports
it; verified by grep across all of them. No code change.

### `jax` + `jaxlib`, 554 MB — one gradient, in `scaler.py`

`Scaler.scale` was already optimising with
`scipy.optimize.minimize(method="L-BFGS-B")`. jax appeared solely as
`jax.jit(jax.grad(fun))` supplying the `jac=` argument.

That derivative is now hand-written in `scaler.py`'s
`value_and_gradient`, which returns the objective and its gradient
together and is passed to scipy as `jac=True`. The comment above it
carries the derivation. The objective is unchanged.

Checked against `scipy.optimize.approx_fprime` on real topologies:
relative error 6e-8 (**pcu**) and 9e-7 (**dia**), which is finite
difference noise rather than disagreement.

**It is not bit-identical to upstream, and it is more accurate.**
jax runs with `jax_enable_x64` off by default, so upstream's objective
and gradient were computed in **float32**; these are float64. Builds
therefore land on slightly different points of the same minimum. This
is why the tests in `tests/test_mof_builder.py` compare a build against
upstream by composition, RMSD and *net identification* rather than by
exact coordinates.

Two knock-on tidies, since this file is ours now: the deprecated `disp`
option is gone from the `minimize` call, and with it the
`filterwarnings` entry in `pyproject.toml` that existed to ignore
scipy's warning about it.

### `pymatgen` (+ sympy, pandas, plotly, matplotlib), ~250 MB — one call, in `utils.py`

`read_cgd` expanded a net's asymmetric unit with
`mg.Structure.from_spacegroup(...)` over `mg.Lattice.from_parameters`.
Replaced by two functions at the top of `utils.py` —
`cell_from_parameters` and `expand_asymmetric_unit` — over **gemmi**,
which this project already depends on, through the same
`space_group_operations` helper `xtal/analysis/rcsr.py` expands RCSR
entries with.

**Both deliberately reproduce pymatgen's conventions**, because the
result is not just a set of points. The order the sites come out in is
the *slot order* of the topology: `Topology.node_indices`,
`Topology.edge_indices`, the builder's per-slot block placement and
`xtal.mof.build._representatives` are all indices into it.

- `cell_from_parameters` uses `Lattice.from_parameters`' convention
  (**b** placed by the reciprocal angle gamma\*, **c** along z), not
  ase's or gemmi's.
- `expand_asymmetric_unit` emits one orbit per input site in input
  order, deduplicating within an orbit modulo a lattice translation at
  the same `1e-5` tolerance `SpaceGroup.get_orbit` uses.

`tests/test_mof_builder.py` asserts the agreement rather than trusting
it.

### `ase` — kept

26 MB installed on disk, 20 MB of bytes, and genuinely pervasive:
`Atoms`, `neighborlist` and `io` throughout. Replacing it with
`xtal.core.structure.Structure` is a much larger refactor and must not
ride along with this one.

Only 200 of its 1218 modules reach a bundle, though, and none of its
106 data files: `ase.io` is imported here and never called, because
`framework.py` formats its own CIF. That is why it came off `COLLECT`
in `packaging/bundle.py`.

The free part was taken: `ase.visualize` was imported by four
`view()` methods and nothing else — `building_block.py`,
`local_structure.py`, `framework.py` and `topology.py`. They opened an
interactive ASE viewer, which this application has its own 3D view for.
All four are deleted, along with their imports.

## Other changes

- **`experimental/decomposer` is not vendored.** Nothing imports it.
- **2404 `.cgd` files are 2403 nets, and nothing is missing.**
  `pry.cgd` declares `NAME pyr` upstream, and `pyr.cgd` is there as
  well, so the catalogue — which keys on the declared name — has one
  entry fewer than the directory has files. `packaging/bundle.py`
  counts 3271 files and `--selftest` reports 2403 nets for that
  reason.
- **Twelve files in `database/topologies/` are not vendored**: nine
  `.pickle`, `RCSR_topology.zip`, `cgd_list.txt` and `rcsr_list.txt`,
  about 1 MB. The lists and the archive are unread. The pickles are
  `Database.get_topology`'s cache, and shipping them would be worse
  than pointless: nothing here goes through `Database` — the catalogue
  globs the `.cgd` files and `xtal.mof.build` constructs
  `Topology(path)` directly — and each pickle is an upstream
  `Topology` under the module path `pormake.topology`, built by the
  *pymatgen* expansion this vendoring replaced. It would either fail
  to unpickle or quietly restore a net expanded by the old code.
  `Database` itself is kept and falls back to reading the `.cgd`,
  which is the correct behaviour.
- **`atoms.get_cell_lengths_and_angles()` → `atoms.cell.cellpar()`**,
  three places (`framework.py` once, `topology.py` twice). ase
  deprecated the old spelling. This one bit harder than it looks:
  `write_cif` catches whatever the write raises, deletes the
  half-written file and logs it, so under the suite's
  `error::DeprecationWarning` every build test failed on a *missing
  CIF* rather than on the deprecation. The `filterwarnings` entry that
  suppressed it is gone too.
- **`read_cgd`'s overlap removal uses `xtal.core.neighbors`, not
  `ase.neighborlist.neighbor_list`.** A 0.1 cutoff over a net cell
  whose edges are about one unit long made ase bin the cell into a
  vast grid and resize arrays per bin: 3.9 s of the 4.0 s `naz-x`
  took to read, on the path every build waits on. Measured over 417
  nets (every sixth in the database, plus the ones the tests name):
  the same sites removed in every one of them, 50 of which have
  overlaps, and 103 s down to 0.8 s for the step.
- **Nothing else is reformatted.** The tree is excluded from `ruff` in
  `pyproject.toml` for exactly that reason: it fails this project's
  lint in twenty places, all of them upstream's own style, and
  rewrapping somebody else's code to our line length is how a vendored
  tree stops being diffable against the version it came from.

## Where it is checked

- `tests/test_mof_vendored.py` — the expansion against pymatgen's site
  for site, whole builds against a real upstream PORMAKE by
  composition, RMSD and net, the gradient against finite differences,
  and a subprocess assertion that a build imports none of the three
  removed packages. The upstream half skips when upstream is absent.
- `tests/test_mof_builder.py` — the builder's own behaviour, no longer
  skipped for a missing PORMAKE.
- `tests/test_packaging.py` — that `packaging/bundle.py` names every
  net, every block, the licence and this file.
- `crystal-builder --selftest` — builds **pcu** inside the *built
  bundle* and checks the net. The only layer that can say the database
  survived PyInstaller.

## Updating it

Diff the new upstream against 0.2.3, apply what is relevant, and
re-check the two substitutions above — `tests/test_mof_builder.py`
compares vendored builds against a real installed PORMAKE when one is
present and skips when it is not, which is the fastest way to find out
whether a change matters.
