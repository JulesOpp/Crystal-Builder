# Single-metal nodes and PORMAKE2's block library in the MOF builder

## Context

Asked (2026-11-20): "Plan single metal nodes and expanded library (check
the repo's license)", following a read of Lee, Kim, Lee & Kim,
*Chem. Mater.* 2026, doi 10.1021/acs.chemmater.6c02674 (PORMAKE2,
`JulesWork/references/pormake2.pdf`).

Why it matters: every node we can build with today is a cluster or an
organic node. None of our 867 PORMAKE blocks or our 12 own blocks is a
lone metal, so ZIF-type, CALF-20-type and other single-metal frameworks
cannot be built. `candidates.py` already refuses azolate and pyridyl
linkers by name for that reason.

What already exists and makes this smaller than it sounds:

- **A metal end that sits at a dative distance.** `attach.DATIVE_MN` and
  `attach.dative_point` already put a metal's connection point at
  `d(M-N) - 0.75` so a pyridyl's 0.75 Å end adds up to a real M-N bond.
- **The coordination shapes.** `xtal/build/coordination.SHAPES` holds
  every shape (trigonal planar through cubic), `default_shape` picks
  square planar for Cu/Ni/Pd/Pt, and `bond_length` gives an M-donor
  distance.
- **Bonding a chelate to a metal.** `build._joint_bonds` bonds every
  member of a joint, so a chelating carboxylate's two oxygens on one
  metal arrive as two M-O bonds with no new code.
- **Joints without a linker.** An edge slot left empty is already
  allowed (`build._resolve`). That is how an organic node such as a
  carboxylate-ended BTC meets a metal directly.

**Answers given by the user:**

1. Clone the PORMAKE2 repo to measure it. Done: scratchpad clone of
   `Timeout-99/PORMAKE2` at commit 6e1ca05f (v2.2.0, 2026-10-22).
2. Metal geometry is **shape held, pick the shape**. The user first chose
   PORMAKE2's "net decides" mode, then changed to this after the ZIF-8
   measurement below.
3. The library is **vendored, converted** to our conventions and shipped
   like PORMAKE's.

## Licence

PORMAKE2 is **MIT**: "MIT License / Copyright (c) 2026 PORMAKE2
contributors". The GitHub API reports spdx `MIT` and the README says
"License: MIT." That is the same licence as the PORMAKE we already
vendor. Shipping the converted blocks needs the copyright and permission
notice beside them. Phase 0 copies `LICENSE` into the library folder and
records provenance as `xtal/mof/pormake/PROVENANCE.md` does.

## What is actually there, measured

### The repository

| Folder | Files | What it is |
|---|---|---|
| `bbs/v1/Node_cluster`, `Edge_cluster` | 648 + 219 | PORMAKE's own 867, which we already vendor |
| `bbs/v2/Node_metal` | 88 | 22 metals x CN 3/4/5/6. One metal and X at **0.900 Å**, idealised shapes, no metadata |
| `bbs/v2/Edge_metal` | 227 | donor-ended linkers, every one with metadata |
| `bbs/v2/Node_nonmetal` | 777 | donor-ended organic nodes, 3-16 points, no metadata |
| `topologies/` | 2406 | **identical** to our vendored nets apart from list files, so there are no new nets |
| `data/` | 2 | `allowed_oxidation_states.json` (MOSAEC, 1 % threshold), `metal_donor_coordination_limits.csv` (used only for their random generation) |

The `v2` blocks total 4.3 MB.

### Connection points, by the atoms each hangs off ("members")

| Library | Members per point | Member atoms | X to members' centroid |
|---|---|---|---|
| PM2 linkers | 1: 145, 2: 309 | N 145, OO 309 (each carboxylate is one chelating point) | 0.52-0.97 Å, median 0.63 |
| PM2 non-metal nodes | 1: 3140, 2: 514 | O 1750 (a carboxylate's two oxygens as two separate points), N 1390, OO 514 | 0.55-1.29 Å, median 0.90 |
| PORMAKE v1 nodes / edges | 1, except 2 points | C 3462 / 410, plus a few N, B, P, S | median 0.750 |

Roles in the linker metadata: carboxylate 309, azolate 70, pyridine_N 60,
pyrimidine_N 10, chain_N 5. Metadata keys: `x_roles`,
`x_oxidation_states`, `x_donor_counts`, `charge`. They sit as
`# key = a,b` lines after the bond block.

### ZIF-8 built through our own path

Zn on `sod` with PM2's imidazolate E27. Script:
`scratchpad/scripts/zif8.py`. Experiment: a = 16.99 Å, Zn-N about
1.99 Å, N-Zn-N about 109°.

| Build | a, Å | Zn-N, Å | N-Zn-N |
|---|---|---|---|
| PM2's 0.9 + 0.9 Å, shape held | 15.64 | 1.67-1.71 | 94-131° |
| **Ours**: Zn point at 2.0 - 0.75 Å, linker 0.75 Å, shape held | **16.77** | 1.86-1.91 | 92-127° |
| Ours, net decides (PM2's mode, through a `Locator` override) | 16.77 | 1.87 | 80-134° |
| Either of ours after UFF4MOF with the cell relaxed | 16.87 | 1.90-1.96 | 103-116° |

All four builds have 204 atoms and 48 joints, with no overlaps and a
maximum RMSD of 0.170.

### Decisions that follow

1. **We generate our own metal nodes and do not ship PM2's 88.** Theirs
   are four fixed shapes at 0.9 Å. Ours come from
   `coordination.SHAPES`, so square planar and square pyramidal are
   offered too, and the point sits at a donor's distance:
   - PM2's 0.9 + 0.9 Å makes ZIF-8's cell 8 % short (15.64 Å).
   - Our reach gets within 1.3 % (16.77 Å) before any relax.
2. **No "net decides" mode.** On `sod` it is worse than holding the
   tetrahedron (80-134° against 92-127°), and both relax to the same
   structure. The net's own vertex has 90° and 120° angles, while
   ZIF-8's zinc is tetrahedral because the imidazolate bends. So the
   vendored `Locator` is left alone.
3. **A metal point's distance depends on what meets it.** It is
   `donor_reach(metal, kind) - CONNECTION_DISTANCE`, worked out when a
   build is resolved from the blocks on the slot's edges:
   - an anionic N or O donor uses `coordination.bond_length`;
   - a pyridyl uses `DATIVE_MN`, falling back to `bond_length + 0.1`;
   - a chelating OO uses `sqrt(d^2 - (bite/2)^2)`, with the bite
     measured off the block.

   So a metal node is a **template**, written into the run folder at
   build time, not a file in the catalogue.
4. **Every converted point is pulled to 0.75 Å** by `block.pull_in`,
   which already exists, keeping its direction. Our invariant stays as
   it is, and the metal side absorbs the difference.
5. **Metadata goes in a sidecar** (`index.json`), not in the `.xyz`.
   The vendored PORMAKE reader would crash on the `# x_roles = ...`
   lines (`pormake/utils.py:533`, `int('#')`). Our own reader skips
   them, but PORMAKE reads the same file.
6. **The names are prefixed** `P2E<n>` and `P2N<n>`. PM2's `E40` and
   `N1` would otherwise replace PORMAKE's blocks of the same name,
   because a later folder wins in `Catalog._read`. The paper's metal
   names `M1`-`M88` resolve as aliases to ours, so "kag + M42 + E40"
   can be typed as `kag`, `M42`, `P2E40`.
7. **Ends must match.** A joint pairs a carbon end with a carbon end
   (PORMAKE's convention) or a donor end with a metal end, and nothing
   else. A donor-ended linker on N16 would put a second carboxylate on
   a cluster that already has one. That is refused by name, never built.

## Phase 0: the converted library (`scripts/pormake2_blocks.py`, `xtal/mof/library/pormake2/`)

- **The script** takes a path to a PORMAKE2 checkout and writes
  `xtal/mof/library/pormake2/`:
  - the 227 linkers and 777 non-metal nodes, points pulled to
    `CONNECTION_DISTANCE`, renamed `P2E*` / `P2N*`;
  - `index.json` with each block's source file, roles, oxidation states,
    donor counts, charge, and a point kind for every point;
  - `aliases.json` mapping `M1`-`M88` to our metal-node names;
  - `LICENSE`, a copy of PM2's;
  - `PROVENANCE.md`: commit, date, what was changed, what was refused.
- **Point kinds.** For a linker, from `x_roles`. For a non-metal node,
  from its members: O is a bridging carboxylate oxygen, OO a chelating
  carboxylate, N an azolate or pyridyl, told apart by
  `donors.py`'s ring reading.
- **Every block goes through `block.problems`** (inward points, span,
  X-X bonds). A refused block is left out and counted in
  `PROVENANCE.md`, not shipped broken. The `E231` file, whose second
  line is a name and not indices, has its X atoms found by `_connections`.
- **`Catalog.default`** reads the new folder after PORMAKE's and before
  ours. `BuildingBlock` gains `ends` (`"carbon"`, `"donor"`, `"metal"`)
  and `metadata`, both read from the sidecar. A block with no sidecar
  entry is `"carbon"`, so every existing block reads as it did.
- **Packaging.** Add `"library/pormake2/*.xyz"` and `*.json` /
  `LICENSE` to `pyproject.toml` package-data and to
  `packaging/bundle.py`'s `xtal/mof/library` entry.
- **Measure** the catalogue's first read with roughly 1000 more files,
  and the `linkers.profile` pass over them. If either passes half a
  second on the 8 GB M2, profile lazily per block.
- **Invariants:**
  - The connection distance is kept: every point ends at 0.75 Å, which
    a test holds.
  - The vendored PORMAKE is untouched.
- **Tests** (`tests/test_mof_pormake2_library.py`):
  - `test_every_converted_point_sits_at_the_connection_distance`: a
    0.63 Å carboxylate end left as written makes every M-O joint short.
  - `test_no_converted_block_shadows_a_pormake_block`: an `E40`
    collision silently replaces PORMAKE's E40 in every saved build
    request.
  - `test_pormake_reads_every_converted_block`: a metadata line in an
    `.xyz` crashes the vendored reader.
  - `test_a_linker_keeps_its_roles_and_charge`
  - `test_a_block_from_before_reads_as_carbon_ended`
  - `test_the_mit_notice_ships_beside_the_blocks`
  - `test_the_script_reproduces_the_shipped_library`: skipped without a
    checkout, as `test_orca_catalogue` is.
- **Size:** M.

## Phase 1: single-metal nodes (`xtal/mof/metal_nodes.py`)

- **`MetalNode(element, shape)`** with names like `Zn_T4`, `Cu_SP4`,
  `Co_OC6`, `Zn_TP3`, `Fe_TBP5`, `Cu_SPY5`; one code per
  `coordination.SHAPES` key.
  - Offered for PM2's 22 metals at CN 3-6.
  - CN 7-8 (pentagonal bipyramid, square antiprism, cube) only for metals
    whose donor limit in PM2's csv is 8 or more: Zr, U, Na and the
    lanthanides.
- **`donor_reach(metal, kind, block)`** implements decision 3.
  `attach.dative_point` is then this function with the pyridyl kind;
  its callers in `decorate.py` and `partition.py` keep the same numbers,
  which a test holds.
- **`materialise(node, partners, folder)`** writes the template's
  `.xyz` with the reach its partners need.
  - If one metal's points meet different kinds (CALF-20: triazolate N
    and oxalate O), they get the mean reach.
  - The verdict then names the largest joint error, which a relax
    removes.
- **Catalogue.** `Catalog.building_block("Zn_T4")` and `fitting(n)`
  include the templates as virtual `BuildingBlock`s with `ends="metal"`.
  `M42`-style aliases resolve through `aliases.json`.
- **`build._resolve`**:
  - materialises each metal node into the run folder;
  - checks every joint's ends (decision 7) and raises `MofError` naming
    both blocks and the rule, for example "P2E27's ends are azolate
    donors and N16's points are carbon: a donor-ended linker meets a
    single metal, not a cluster";
  - also checks node-to-node joints when an edge slot is empty.
- **`candidates.linker_block`** stops refusing azolate and pyridyl
  linkers where the forecast's node is a single metal, using
  `P2E*` blocks matched by SMILES where one exists. Otherwise the refusal
  stands as it is.
- **Invariants:**
  - *A built framework's bonds are its blocks' own and its joints', never
    perceived.* The metal-donor bonds come from `bond_joints`; a test
    holds ZIF-8's 48 Zn-N joints to 192 Zn-N bonds in the P1 cell and
    none perceived.
  - *A connection point is 0.75 Å from its members.* Unchanged for every
    block. The metal side is the documented exception that `DATIVE_MN`
    already is, now general (a CLAUDE.md edit).
  - *Which way round a symmetric node goes.* A lone metal presents no
    face (`attach.face_of`: "a metal is no face"), so pass 2 is never
    reached and nothing in `orient` changes.
- **Tests** (`tests/test_mof_metal_nodes.py`, the builds marked `slow`
  if over a second):
  - `test_zif8_on_sod_comes_within_two_percent_of_its_cell`: 16.77
    against 16.99. PM2's 0.9 Å reach gives 15.64.
  - `test_every_zinc_imidazolate_joint_is_one_zn_n_bond_near_two_angstrom`:
    the range is 1.86-1.91 today.
  - `test_a_chelating_carboxylate_bonds_both_oxygens_to_its_metal`
  - `test_a_donor_linker_on_a_cluster_node_is_refused_by_name`
  - `test_a_carbon_linker_on_a_metal_node_is_refused_by_name`
  - `test_m42_names_the_metal_node_the_paper_built_with`
  - `test_dative_point_still_puts_a_pyridyl_where_it_did`
  - `test_every_shape_code_round_trips_to_its_template`
  - `test_existing_builds_are_written_byte_for_byte_as_before`: MOF-5 on
    `pcu`.
- **Size:** L.

## Phase 2: charge check (`xtal/mof/charge.py`)

- **The framework's formal charge.** Each metal can take any oxidation
  state in PM2's `allowed_oxidation_states.json` (vendored with the
  library). Each block contributes its stated charge.
  - If no assignment of states makes the cell neutral, the build warns
    and is never refused. This follows *a drawing no shape fits is
    still built, and says so*.
  - A block with no stated charge (every non-metal node, every PORMAKE
    block) means nothing is said, rather than a guess.
- **Where the warning shows:** the verdict, a report row, the new tab's
  notice, and a new diagnostic code `BUILD_CHARGE`. It goes into
  `diagnostics.CODES` and the skill's `diagnostics.md` in the same
  commit, which the skill test requires.
- **Tests:**
  - `test_zinc_with_two_imidazolates_is_neutral_and_says_nothing`
  - `test_an_impossible_metal_and_linker_pair_warns_with_the_states_it_tried`
  - `test_a_block_with_no_charge_leaves_the_check_silent`
- **Size:** S-M.

## Phase 3: the window and the agent

- **The MOF builder's block picker:**
  - a *Single metal* group listing the templates for the slot's count,
    one row per metal and shape;
  - an *Ends* column (carbon / donor / metal) and a filter on it;
  - search matching the `M42` aliases and PM2's roles ("azolate").
  - The picker already filters by count. It now also greys a block
    whose ends cannot meet the neighbouring slot's choice, and says why
    in the tooltip.
- **The agent.** `Session.build_mof` takes the new names unchanged.
  The skill's MOF page gains the metal-node names, the ends rule and
  `BUILD_CHARGE`. `tests/test_agent_skill.py` holds every name.
- **Tests** in `tests/test_mof_ui.py`:
  - `test_a_four_connected_slot_offers_zinc_tetrahedral_and_copper_square_planar`
  - `test_a_donor_linker_is_greyed_beside_a_cluster_node`
- **Size:** M.

## Verification (end to end)

- `python .claude/skills/run-app/drive.py --scratch DIR` with the MOF
  builder on `sod`, `Zn_T4` and `P2E27`, then
  `--viewport-shot zif8.png`. The shot must show sodalite cages with
  zinc tetrahedra and no stray bonds.
- Force Field panel, UFF4MOF with the cell relaxed. a should come out
  near 16.87 and Zn-N near 1.90-1.96.
- Repeat on a square-planar case (`Cu_SP4` on `nbo` with a pyridyl
  linker) and a mixed-donor case (CALF-20-like: Zn, triazolate and
  oxalate).
- Per phase: `python -m pytest -q -n0 tests/test_mof_pormake2_library.py
  tests/test_mof_metal_nodes.py tests/test_mof_builder.py
  tests/test_mof_orientation.py tests/test_mof_vendored.py`.
- The full suite once at the end with `-n 3`.

## Docs

- **CLAUDE.md:**
  - the layout row for `xtal/mof/` gains `metal_nodes.py` and the
    `pormake2` library;
  - the connection-point invariant gains "a metal's point sits at its
    donor's distance less 0.75 Å, decided by what meets it";
  - a new invariant: "a joint pairs carbon with carbon or donor with
    metal".
- **docs/TODO.md:** schedule these phases. Leave PORMAKE2's
  symmetry-coupled, energy-ranked linker rotation as an unscheduled
  entry. It matters most for exactly these compact frameworks: ZIF-8's
  imidazolate turn is the gate.
- **Manual:** the MOF builder chapter gains single-metal nodes and the
  ZIF-8 walk-through. The bibliography gains the PORMAKE2 paper.
- **The skill** (`xtal/agent/skill/`), in Phases 2 and 3 as above.

## Suggested order

0, then 1, 2, 3, one commit per phase. Phase 0 changes no build, because
every existing block still reads as carbon-ended. Phase 1 is the feature.
Phases 2 and 3 can swap.

Not in this plan, and worth raising separately: symmetry-coupled linker
rotation ranked by energy with the Force Field panel's engine. Today a
ZIF-8 imidazolate is drawn as written or turned for room, not chosen by
energy.
