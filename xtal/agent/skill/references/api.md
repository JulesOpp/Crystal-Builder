# The session API

Every verb below is a method of `xtal.agent.Session`. The heading gives
the exact parameter names; a test checks each one against the installed
code, so if `help_for("verb")` and this page ever disagree, the page is
out of date. Trust `help_for`.

Conventions:

- **Sites** are indices into the asymmetric unit (`inspect().sites`,
  field `index`). An edit of a site edits every atom of its orbit.
- **Atoms** are indices into the P1 cell (`session.cell`); each site row
  of `inspect()` carries `first_atom`.
- Coordinates are fractional (`frac`) unless a parameter says `cart`,
  which is Cartesian in Å.
- Every verb that changes the structure is **one** undo step, and
  returns a `VerbResult`. `ok=False` means nothing was changed.
- Bonds are perceived afresh only by `recalculate_bonds()` and by the
  verbs that rebuild the cell into a different set of atoms
  (`supercell`, `find_symmetry`, `standardize`, `set_space_group`,
  `prepare`). Every other verb leaves the bond graph as it was.

## Getting a session

### `open(path, workspace)`

A classmethod. Opens a structure file (CIF, POSCAR, XYZ, PDB …) or a
`.xtalproj` project. With `workspace`, the file is **copied into** the
workspace and the session follows the copy; the original is recorded in
`structure.meta["source"]`. A file already inside a workspace is used
where it is. A project keeps its view and selection through a save.
`session.opened` is the open's own `VerbResult`: opening a CIF whose
entry already holds a saved project carries `PROJECT_EXISTS`, because
the project is where earlier work was kept. To continue across
processes, open the `.xtalproj` that `save()` returned.

### `new(a, b, c, alpha, beta, gamma, space_group, name, workspace)`

A classmethod. An empty cell to build into; `space_group` is any
Hermann–Mauguin symbol or number. With `workspace`, it gets an entry
named `name` of its own.

### `build(action, workspace, **params)`

A classmethod. Runs a builder module (`mof.build`, `net.draw`,
`build.molecule`) and opens what it built, filed in `workspace` as the
window files it: one entry, one CIF, the run underneath.
`session.built` is the builder's `VerbResult`, with its report tables
in `data["tables"]`. Raises `BuildFailed` (whose `.result` is the
`VerbResult`) when nothing was built. See `mof.md`.

## Reading

### `inspect(symprec)`

The `Inspection` (see below). `symprec` defaults to 0.01 Å, the
tolerance at which a file written to four decimals shows the group it
means.

### `render(path, view, size, style, highlight, show_cell)`

A PNG, drawn as the viewport draws it, in a subprocess. `view` is
`"diagonal"`, `"a"`, `"b"`, `"c"` or a lattice direction `[u, v, w]`;
`style` is a viewport style (`ball_stick`, `stick`, `spacefill`,
`wireframe`, `polyhedra`, `net` …); `highlight` is a list of P1 atoms to
draw selected. Orthographic, so a straight channel looks straight. Comes
back `ok=False` with `RENDER_UNAVAILABLE` where there is no OpenGL.

## Atoms

### `add_atom(element, frac, cart, bonded_to, occupancy, label)`

One atom at `frac` or `cart` (give exactly one). Bonded to nothing,
unless `bonded_to` names a P1 atom: then to that atom, explicitly, in
the same undo step. `data["site"]` is the new site's index. To place a
bonded atom at a sensible distance, the sum of covalent radii is
`xtal.core.bonding.bond_distance(a, b)`.

### `delete_sites(sites)`

Removes whole sites, every atom of each orbit.

### `set_element(sites, element)`

Retypes sites. Bonds are not re-perceived.

### `move_sites(sites, frac_delta, cart_delta, to)`

Moves sites by a fractional or Cartesian delta, or `to` explicit
fractional coordinates (one row per site). Bonds stay as they were
drawn.

## Cell and symmetry

### `set_cell(a, b, c, alpha, beta, gamma, keep)`

`keep="fractional"` (the atoms scale with the cell) or `"cartesian"`
(they stay put in space).

### `supercell(na, nb, nc)`

### `reduce_to_p1()`

Every orbit expanded into independent sites; the group dropped. Needed
before an edit that breaks the symmetry, such as moving one atom of an
orbit, or a scan the group would tie.

### `find_symmetry(symprec)`

Detects the group and keeps it; the cell becomes its asymmetric unit.

### `standardize(symprec, to_primitive)`

Rebuilds the cell in the conventional (or primitive) setting of its
detected group, idealising positions onto their special positions.

### `set_space_group(group, mode)`

`mode="reinterpret"` treats the sites as an asymmetric unit and lets the
group generate the rest. `"impose"` treats them as a whole cell and
looks for an asymmetric unit in it; atoms the group cannot explain are
reported, not dropped.

### `merge_duplicates(tol)`

Merges sites of one element that are the same atom. The remedy for
`COINCIDENT_ATOMS` and `DUPLICATE_SITES`.

## Bonds

### `recalculate_bonds()`

The only verb that bonds by distance. Bonds drawn or removed by hand
survive it. `data` has `added`, `removed` and `bonds`.

### `add_bond(atom_a, atom_b)`

Draws a bond between two P1 atoms, at their nearest images. Survives
every recalculation.

### `remove_bond(atom_a, atom_b)`

Suppresses the bond, and with it the whole orbit of that bond the group
generates. Survives every recalculation.

### `set_bond_type(atom_a, atom_b, order)`

`order` is 1, 1.5 (aromatic), 2, 3, or `"Single"`, `"Double"`,
`"Triple"`, `"Aromatic"`, `"Automatic"`. A stated order wins over
anything perception infers.

### `add_hydrogens(xray)`

Completes main-group valences, as one undo step, bonded. The one edit
that bonds what it adds. Refused with `NOTHING_TO_DO` when nothing is
missing. For a deposited structure, prefer `prepare()`, which places
cluster and water hydrogens by rule where valence alone would guess.

## Whole-structure operations

### `prepare(steps)`

See `prepare.md`. `steps` from `duplicates`, `deuterium`, `primitive`,
`disorder`, `solvent`, `cap`, `hydrogens`; the default is all but `cap`.
Each step's sentence comes back as a `PREPARE_STEP` diagnostic, with the
step in `where`. Refused (`OPERATION_REFUSED`) when the structure has
bonds drawn by hand, which ordering cannot carry through.

### `interpenetrate(n)`

`n` copies of the framework, where the detector finds the most room.
Refused by name when no placement fits.

## Calculations

### `energy(engine, **options)`

A single point. Changes nothing and is not on the stack. `data` has
`energy` (kcal/mol), `max_force`, `rms_force` (kcal/mol/Å) and `terms`.
`**options` are the engine's own (`help_for("uff")`).

### `optimize(engine, relax_cell, max_steps, tolerance, method, **options)`

Relaxes positions (and the cell, with `relax_cell=True`, under the
space group's allowed strains) as one undo step. `method` is one of
`lbfgs`, `fire`, `smart`, `steepest_descent`, `conjugate_gradient`,
`quasi_newton`, `abnr`. `tolerance` is the largest force to stop at, in
kcal/mol/Å. `data` has `converged`, `steps`, `initial_energy`,
`energy`, `max_force`, `max_displacement`, and `run`, the folder in the
workspace. An unconverged run is applied and says `NOT_CONVERGED`.

### `run(action, **params)`

Runs a module action against the structure (`zeopp.volume-grid`,
`pxrd.simulate`, `scan.run` …) and returns its report: `data["tables"]`
is the tables as rows, `data["report_text"]` the text the CLI prints,
`data["run"]` the folder. Parameters are the form's
(`help_for("zeopp.volume-grid")`). A module that returns a structure
does not change the session (`RESULT_NOT_APPLIED` says where it is).

## History and files

### `undo()`

### `redo()`

### `save(path)`

Writes the session as a project (`.xtalproj`): the structure, its bonds
and perceived graph, and the person's view. With no `path`, a structure
opened as `X.cif` is saved as `X.xtalproj` beside it; the CIF is left as
it is. Returns the path.

### `export(path)`

A copy for another program, in the format the suffix names: no markers,
no net edges, no suppressions.

## The answers

**`VerbResult`**: `verb`, `ok`, `message`, `undo_label`, `atoms_before`,
`atoms_after`, `data` (dict), `diagnostics` (list), `worst` (the most
severe level present), `to_dict()`, `to_json()`.

**`Inspection`**: `formula`, `z`, `n_sites`, `n_atoms`, `cell` (a, b, c,
alpha, beta, gamma), `volume` (Å³), `density` (g/cm³), `space_group`
and `space_group_number` (declared), `detected_space_group`, `symprec`,
`net_charge` (None unless sites carry charges), `n_bonds`, `fragments`
(kind, n_atoms, formula), `sites` (index, label, element, frac,
occupancy, multiplicity, first_atom, coordination, neighbours as
`[element, distance]`), `diagnostics`, `worst`, `to_dict()`,
`to_json()`. `str()` prints the first 40 sites; `to_dict()` has all.

**`Diagnostic`**: `code`, `level` (`info`, `warning`, `error`),
`message`, `where`, `suggestion`. Codes are closed: `diagnostics.md`.

## Also importable

- `capabilities()`: engines, modules and rendering, each with
  `available` and `reason`, and every parameter.
- `help_for(name)`: a verb's signature and docstring, or an engine's or
  a module action's parameters.
- `session.cell`: the P1 cell (`elements`, `frac`, `cart`, `site_idx`).
- `session.structure`: read it freely; never write to it.
- `session.history()`: the undo stack's labels.
- `session.log`, and the entry's `agent-session.jsonl`: every verb, one
  JSON object per line.
