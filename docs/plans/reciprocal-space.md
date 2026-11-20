# Reciprocal space: the zone, its high-symmetry paths, and their coordinates

## Context

A user wrote (2026-11):

> "...reciprocal lattice and Brillouin zone calculations, the ability to
> select high-symmetry paths, and the option to display the coordinates
> of high-symmetry points along the selected path ... similar to
> XCrySDen, but with a completely redesigned, more modern, and
> user-friendly interface."

Most of the core already exists, but it is hidden inside one dialog.
`xtal/analysis/kpath.py` builds the first zone (a Voronoi cell, tested
on fcc, cubic and quartz), reads ASE's path for the cell, parses
`"GXWKGL,UX"`, and samples DFTB+ `Klines`. `xtalapp/widgets/brillouin.py`
is a QPainter zone you can drag to rotate. Both are reached only through
DFTB+ ▸ Band structure (`dftb_run.BandStructureDialog`) and the band
results block (`report.Zone`). What is missing:

1. a reciprocal-space tool of its own;
2. a path that comes from the crystal's symmetry rather than the cell's
   shape;
3. the coordinates shown and written out for the codes people use.

Decisions taken with the user (2026-11-16):

- **Its own window.** Cell ▸ Reciprocal space…, a non-modal window like
  the refinement workbench, not a dock.
- **HPKOT through seekpath is the default.** ASE's Setyawan–Curtarolo
  is kept as a choice in a box.
- **Export to all of these:** QE `crystal_b`, VASP line mode, DFTB+
  `Klines`, phonopy `BAND`, CASTEP `BS_KPOINT_PATH`, CP2K `KPOINT_SET`,
  and CSV or the clipboard.

## What is actually there — measured

Measured on 2026-11-16 with
`scratchpad/measure_kpath.py`, using seekpath 2.2.1, spglib 2.7.0 and
the ASE in /opt/anaconda3.

| Structure | Declared | ASE (lattice only) | seekpath @1e-5 | seekpath @0.05 Å | ASE path | seekpath ms | zone ms |
|---|---|---|---|---|---|---|---|
| halite, conventional | Fm-3m | **CUB** | cF2 | cF2 | ΓXMΓRX,MR | 19 | 4 |
| MOF-5 | Fm-3m* | **CUB** | cF2 | cF2 | ΓXMΓRX,MR | 25 | 2 |
| HKUST-1 | Fm-3m | **CUB** | cF2 | cF2 | ΓXMΓRX,MR | 27 | 4 |
| MFU-4l | Fm-3m | **CUB** | **oP1** | cF2 (from 0.01) | ΓXMΓRX,MR | 31 | 3 |
| NiHITP | P6/mmm | HEX | hP2 | hP2 | ΓMKΓALHA,LM,KH | 4 | 6 |
| ZIF-8 (P1 file) | P1 | TRI | aP2 | mC3 | — | 3 | 3 |
| CFA-1 | — | HEX | **refused**: "too close distance between atoms" | | | — | — |

\* as read by `read_cif` from the shipped sample.

seekpath's points carried back into the user's conventional halite cell
come out right: X (½,0,½)prim becomes (0,1,0) in the cell's reciprocal
fractions, and K becomes (¾,¾,0). Importing seekpath costs 0.36 s, and
it is pure Python on top of spglib (already a core dependency), under
the MIT licence.

Decisions that follow:

1. **ASE alone is wrong for a centred cell given in its conventional
   setting.** ASE reads only the metric, so every F-centred sample above
   gets the simple-cubic path. That path is the zone of the conventional
   *cell*, folded, and not the crystal's zone. The default has to read
   the space group from the atoms, which is what HPKOT does.
2. **symprec is `p1.SPECIAL_POSITION_TOL` (0.05 Å), not seekpath's
   1e-5.** At 1e-5, MFU-4l is found as oP1, because its four-decimal
   coordinates are off by more than that. The app already says a site
   is where its coordinates say "to the precision they were written
   at" (see the special-position invariant). Reusing that tolerance
   keeps one answer to "what is this crystal's symmetry". When the
   group found differs from the declared one, the window says so.
3. **The spglib cell is the app's own** (`symmetry._spglib_cell`): it
   handles occupancy, and markers are held back first
   (`markers.hold_back`). An `X` is not chemistry and would break the
   symmetry.
4. **A refusal falls back, and says so.** CFA-1 is refused by spglib.
   The window then shows the lattice-only path (ASE's, or the zone with
   Γ alone when the `ase` extra is missing), and says that the atoms
   could not be read for symmetry, with *Prepare for simulation* as the
   remedy.
5. **Cost is not an issue.** Everything is in milliseconds on 648
   atoms, so there is no `limits` entry, no worker, and a recompute on
   every structure change.

## The invariant this adds

**A k-point's coordinates are written together with the cell they
belong to.** A point is held in two bases: the standard primitive cell
(HPKOT's) and the cell the tab holds. In the conventional halite cell,
fcc X is (0,1,0), which is a reciprocal lattice vector of that cell and
so equivalent to Γ. A band calculation run there is correct for that
cell but folded. So:

- every table and export names its basis: *this cell (8 atoms,
  conventional F)* or *standard primitive cell (2 atoms)*;
- exporting in the primitive basis also writes that primitive cell
  (CIF, POSCAR or a QE `CELL_PARAMETERS`/`ATOMIC_POSITIONS` block),
  so the coordinates never travel without their cell;
- when the cell in front is not primitive, the window says the bands
  in its basis are folded, in warning tone (`tone`).

This goes into CLAUDE.md next to the other invariants.

## Other invariants kept

- **xtal imports no Qt.** All the crystallography goes in
  `xtal/analysis/kpath.py` and a new `kpath_formats.py`. The window only
  presents it.
- **Nothing here changes the structure.** The window holds no undo
  step. The one action that leads to a new structure, *Open the
  primitive cell*, files a new entry through
  `Workspace.adopt_build`-style filing and opens a new tab. The tab in
  front is left as it is, so its bonds, hidden atoms and groups are
  never at stake.
- **Dummy atoms are held back at the door** (decision 3).
- **Bonds are untouched.** The primitive cell that gets written is
  built by `symmetry.standardize(to_primitive=True)`, which states its
  `atom_map` and does not perceive bonds.
- **A panel never holds its column open.** This is a window, not a
  dock, so the rule does not apply, but the tables still sit in
  `docks.scrolling`.
- **The agent edits through the same commands.** The new verb only
  reads, so it joins `agent_host.READ_ONLY` and is answered even during
  a calculation.

---

## Phase 1: the path comes from the crystal (`xtal/analysis/kpath.py`)

- Add seekpath to the core dependencies in `pyproject.toml`
  (`seekpath>=2.1`), with a comment giving its licence and the
  spglib-only reason. It is imported lazily inside `kpath`. Check that
  PyInstaller picks it up and add a `kpath` line on rutile to
  `--selftest`.
- Add `CONVENTIONS`, a small registry: `hpkot` (seekpath) and
  `setyawan-curtarolo` (ASE, available only when `kpath.installed()`).
  Each entry has a label, an availability and a citation string.
- Add `KPath`, frozen, extending `BandPath` (which keeps its `points`
  and `runs`):
  - `primitive` (a Lattice) and `to_cell` (an exact rational 3×3
    matrix, taken from seekpath's `primitive_transformation_matrix`
    and the conventional transform rather than from Cartesian
    rotation);
  - `bravais` (for example `cF2`), `group_found`, `group_declared`;
  - `notes` (folded cell, group mismatch, fallback used);
  - `in_basis("cell" | "primitive")`, which returns the points in that
    basis.
- `special_path(structure, convention="hpkot", time_reversal=True,
  symprec=p1.SPECIAL_POSITION_TOL) -> KPath`. It holds markers back,
  uses `symmetry._spglib_cell`, falls back as in decision 4, and leaves
  `band_path(lattice)` untouched for its current callers.
- `ReciprocalLattice.of(lattice, two_pi)`: the vectors, lengths,
  angles and volume, plus the zone's volume.
- `vertex_table(kpath, basis, density)`: for each vertex of the path,
  its label, fractional k, Cartesian k (1/Å, 2π included), cumulative
  distance and the number of samples to the next vertex. It reuses
  `positions()`.
- Tests (`tests/test_kpath.py`, all headless):
  - `test_a_conventional_fcc_cell_gets_the_fcc_path_not_the_cubic_one`:
    halite gives cF2 with an L. Breaks if ASE's metric-only path comes
    back as the default.
  - `test_fcc_x_in_the_conventional_basis_is_a_reciprocal_lattice_vector`:
    (0,1,0), and the folded note is set.
  - `test_every_point_maps_back_to_the_same_cartesian_k`: on rutile,
    quartz, halite and dry ice, a point in the cell basis and in the
    primitive basis is the same vector up to the standardising
    rotation.
  - `test_mfu4l_is_found_fm3m_at_the_written_precision` (slow). Breaks
    if symprec goes back to 1e-5.
  - `test_a_marker_does_not_lower_the_symmetry`: an `X` at a general
    position in halite still gives cF2.
  - `test_a_structure_spglib_refuses_falls_back_and_says_so`: CFA-1.
  - `test_a_found_group_unlike_the_declared_one_is_a_note`.
  - `test_without_time_reversal_a_polar_crystal_gets_the_longer_path`:
    quartz.
  - `test_the_reciprocal_lattice_times_the_real_one_is_two_pi`.
- Size: M.

## Phase 2: the formats (`xtal/analysis/kpath_formats.py`)

- A registry of `PathFormat(key, label, extension, write(table, cell)
  -> str)`, one entry for each of `qe`, `vasp`, `dftb`, `phonopy`,
  `castep`, `cp2k` and `csv`. Each header comment names the basis and
  the cell. A jump (`U|K`) is written the way each code reads one:
  - QE: a zero weight on the last point of a run;
  - VASP: pairs, so a jump comes out naturally;
  - phonopy: a comma in `BAND`;
  - CASTEP: `BREAK`;
  - CP2K: one `KPOINT_SET` per run;
  - DFTB+: the existing `KLines` (one point that starts the run).
- `write_with_cell(path_format, kpath, basis, out_dir)`. In the
  primitive basis it also writes the primitive cell, through
  `export.for_export` so that markers and net edges are cleaned out.
- Tests (`tests/test_kpath_formats.py`): golden text for halite's
  primitive path in every format
  (`test_each_format_writes_halites_path_as_its_code_reads_it`);
  `test_a_jump_is_a_break_in_every_format`;
  `test_a_primitive_basis_export_writes_its_cell_beside_it`;
  `test_the_header_names_the_basis`. One round trip where a reader
  exists: phonopy parses its own `BAND` string, and ASE reads the VASP
  `KPOINTS`.
- Size: M.

## Phase 3: the zone view grows up (`xtalapp/widgets/brillouin.py`)

Still QPainter: tests stay GL-free, and the zone is a few dozen
polygons.
- Faces drawn back to front with low alpha, and hidden edges dashed.
- The arrows b1, b2 and b3 are labelled and can be turned off. The
  zone of the cell as it is (folded) can be drawn as a second wireframe
  inside the crystal's zone. The wireframe is what makes folding
  visible.
- Points are markers with labels. Hovering one shows its coordinates
  in both bases. **A click appends it to the path** (XCrySDen's
  gesture), shift-click starts a new run, and Backspace removes the
  last point. Emits `pathEdited(runs)`.
- View along b1, b2, b3 or Γ→a selected point, and save as PNG or SVG
  (extending `save_zone`).
- Tests (`tests/test_brillouin_view.py`, gui):
  `test_clicking_a_point_appends_it_to_the_path`,
  `test_shift_click_starts_a_new_run`,
  `test_hover_names_the_point_and_both_coordinates`,
  `test_the_folded_zone_is_drawn_only_for_a_non_primitive_cell`. The
  existing DFTB+ dialog tests stay green.
- Size: M.

## Phase 4: the window (`xtalapp/reciprocal/window.py`), Cell ▸ Reciprocal space…

Wired by `add-action`: `reciprocal_space` under Cell, after the
reductions. It is opened through `windows.present` and follows the
document it was opened over.
- Left: the zone view. Right, top to bottom:
  - **Lattice**: real and reciprocal vectors, a 2π toggle (off is the
    crystallographic convention, as in `Lattice.reciprocal`), and the
    volume of the BZ.
  - **Symmetry**: the group found or the declared one, the Bravais type
    (`cF2`), the convention box, the time-reversal tick, and the notes
    line in warning tone.
  - **Path**: the text field (`GXWKGL,UX`, using the existing parser),
    *Recommended*, and *Add point…* for a custom named point given in
    either basis.
  - **Points** table: label, fractional, Cartesian, distance, samples.
    A basis box (*this cell* / *standard primitive*) and a density
    spinbox. Selecting a row highlights the point.
  - Buttons: **Export…** (format box, with the cell written beside it
    when needed), **Copy** (CSV), and **Open primitive cell** (a new
    entry and tab; this tab is left alone).
- It recomputes on `structureChanged` for its document (a few ms) and
  closes with the document's tab.
- Tests (`tests/test_reciprocal_window.py`, gui, stub viewport as in
  `test_open_once.py`):
  - `test_reciprocal_space_opens_over_the_tab_in_front`;
  - `test_editing_the_cell_redraws_the_zone_without_an_undo_step`;
  - `test_the_basis_box_changes_every_coordinate_and_the_note`;
  - `test_a_custom_point_can_be_put_on_the_path`;
  - `test_export_in_the_primitive_basis_writes_the_cell_too` (patch the
    file dialog);
  - `test_open_primitive_cell_leaves_this_tab_unchanged`;
  - `test_the_window_closes_with_its_document`.
- Size: L.

## Phase 5: one path everywhere (DFTB+, results, CLI, agent)

- `dftb_run.BandStructureDialog` gains the convention box and uses
  `special_path`. **DFTB+ runs on the cell as it is**, so its points
  stay in the cell basis. For a non-primitive cell the dialog shows the
  folded note and a *Reduce to primitive cell* button that runs the
  existing `primitive` action. `report.Zone` records the convention.
  (This changes the default path for centred conventional cells, see
  Open questions.)
- CLI: `xtal kpath FILE [--convention] [--basis cell|primitive]
  [--format qe|…] [--density] [--out DIR]`, which prints the vertex
  table by default.
- Agent: a read-only verb `band_path` on `Session`, an MCP tool in
  `tools.py`, an entry in `READ_ONLY`, and changes to the skill,
  `mcp.md` and `diagnostics.md` in the same commit. New diagnostic
  codes: `SYMMETRY_UNREADABLE` (the fallback) and `FOLDED_CELL`.
  `test_agent_skill.py` will hold them.
- Tests: `test_the_band_dialog_offers_both_conventions`,
  `test_xtal_kpath_writes_quantum_espresso_crystal_b`,
  `test_band_path_is_answered_while_a_calculation_runs`.
- Size: M.

## Phase 6 (optional, ask first): a layer's path stays in its plane

For NiHITP, graphene and slabs: when the structure is a layer (vacuum
along c, or built as one), the window offers the 2D path (Γ–M–K–Γ for
a hexagonal sheet) and draws the 2D zone. seekpath has no 2D
convention, so this would be our own small table for the five 2D
Bravais lattices. Size: M.

---

## Verification (end to end)

```bash
python .claude/skills/run-app/drive.py --scratch $SCRATCH \
  --open resources/samples/MOF-5.cif --action reciprocal_space \
  --grab ReciprocalSpaceWindow --viewport-shot zone.png
```

The screenshot must show:

- the truncated octahedron (fcc) and not a cube;
- the folded cubic wireframe inside it;
- Γ, X, L, W, K and U labelled;
- the Points table with a basis box and the folded-cell note.

Then switch to the primitive basis, *Export…* to QE, and check that
`K_POINTS crystal_b` and the primitive cell were both written. Repeat
on NiHITP (hexagonal prism) and CFA-1 (the fallback note).

Per phase:

```bash
python -m pytest -q -n0 tests/test_kpath.py tests/test_kpath_formats.py
```

and the GUI files for that phase. The full suite runs once at the end
with `-n 3`.

## Docs

- CLAUDE.md:
  - the new invariant ("A k-point's coordinates are written together
    with the cell they belong to", and symprec = the special-position
    tolerance);
  - `xtal/analysis/kpath*.py` and `xtalapp/reciprocal/` in Layout;
  - seekpath as a core dependency.
- docs/MENUS.md: Cell ▸ Reciprocal space….
- docs/TODO.md: schedule Phases 1–5 (plus 6 if approved) under
  *Scheduled*, and delete each section as it ships.
- The manual: a short "Reciprocal space" chapter with one scripted
  screenshot (`manual-writing`).
- The agent skill: `band_path` and the two codes.
- Release notes: credit the user's suggestion.

## Suggested order

1. Phase 1 (the folded-cubic problem is what is wrong; everything
   else is missing).
2. Phase 2.
3. Phase 3.
4. Phase 4.
5. Phase 5.
6. Phase 6 if wanted.

One commit per phase, on `features/reciprocal-space` from main.

## Open questions

1. **The DFTB+ band dialog's default on a centred conventional cell.**
   Today it gets ASE's simple-cubic path: honest for that cell, but not
   the textbook picture. After Phase 5 it would get HPKOT's fcc points
   in the cell basis (folded), with a *Reduce to primitive* button. The
   alternative is to keep ASE there until the user reduces the cell.
2. **Phase 6 (2D paths):** wanted now, or later?
