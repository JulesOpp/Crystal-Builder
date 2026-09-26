(workflows-cli)=
# The `xtal` command

`xtal` is the application without its window: one command with a
subcommand for each thing the core can do to a file.  After this page
you can inspect, convert and prepare a structure, run an engine or a
module against it from a terminal or a batch script, read the exit
status, and know which spelling of an option the command actually
honours.

```{index} single: command line; xtal
```

## Where it is

`xtal` is installed as a console script with the package
(`[project.scripts]` in `pyproject.toml`), so in a source install it
is `.venv/bin/xtal` under the checkout, or plain `xtal` once the
environment is activated.  Every example below is written the second
way and run from the repository root, so that the sample paths
`resources/samples/...` resolve.

% TODO(Sam): does the packaged .dmg / .exe expose `xtal` at all?
% docs/PACKAGING.md does not say either way, so this page does not.

## The shape of a command

Every subcommand takes a structure file (or two, for a conversion),
its own options, and `-h` for its own help:

```console
$ xtal --help
usage: xtal [-h] [--version]
            {info,symmetry,convert,prepare,bonds,types,energy,optimize,formats,modules,engines,run}
            ...

Build, inspect and convert crystal structures.

positional arguments:
  {info,symmetry,convert,prepare,bonds,types,energy,optimize,formats,modules,engines,run}
    info                cell, formula, density
    symmetry            detect the space group
    convert             convert and transform
    prepare             merge copied sites, order disorder, drop solvent, add
                        hydrogens: a deposited CIF made ready for a
                        calculation
    bonds               bonds, coordination, fragments
    types               UFF atom types and why each was chosen
    energy              single-point energy
    optimize            relax the geometry
    formats             list supported file formats
    modules             list the modules and what they take
    engines             list the energy engines and what they take
    run                 run one module action

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
$ xtal --version
Crystal Builder 0.3.1.dev49+g0db248ed6.d20260926
```

A file is read by its extension through the same format registry the
window uses (`xtal formats` lists them, below), and a warning the
reader raises about the file is printed to standard error before the
command goes on.  Structured output goes to standard output; warnings,
notes and errors go to standard error, so a pipeline can keep them
apart.

## Inspecting a structure

```{index} single: command line; info
```
```{index} single: command line; symmetry
```
```{index} single: command line; bonds
```
```{index} single: command line; types
```

### `xtal info`

The cell, the formula, the mass and the density, and the file's title
if it has one.

```console
$ xtal info --help
usage: xtal info [-h] file

positional arguments:
  file

options:
  -h, --help  show this help message and exit
```

```console
$ xtal info resources/samples/prepared/MIL-53.cif
formula        C8H5CrO5  (Z = 2)
space group    P1 (#1, triclinic)
cell           a=11.1912  b=11.1912  c=11.1912
               alpha=82.934  beta=108.070  gamma=144.374
volume         754.772 A^3
sites / atoms  38 / 38
mass           466.237 amu
density        1.0257 g/cm^3
title          MIL-53_prepared
```

### `xtal symmetry`

Detects the space group of the atoms as they stand, whatever group
the file declares -- {ref}`Find Symmetry <cmd-find_symmetry>` from
the command line -- and can list the Wyckoff letters or the subgroups
that need no new cell.  `-o` writes the structure symmetrised:
reduced to the asymmetric unit of the group it found, in the standard
cell.  What the tolerances mean, and what descending to a subgroup
splits, is in {doc}`symmetry </essentials/symmetry>`.

```console
$ xtal symmetry --help
usage: xtal symmetry [-h] [--symprec SYMPREC]
                     [--angle-tolerance ANGLE_TOLERANCE] [--wyckoff]
                     [--subgroups] [-o OUTPUT]
                     file

positional arguments:
  file

options:
  -h, --help            show this help message and exit
  --symprec SYMPREC     distance tolerance in Angstrom (default: 1e-05)
  --angle-tolerance ANGLE_TOLERANCE
                        angle tolerance in degrees, negative to derive it from
                        symprec
  --wyckoff             list Wyckoff letters and site symmetries
  --subgroups           list the subgroups of the current group that need no
                        new cell -- translationengleiche and klassengleiche --
                        and what descending to each would split
  -o OUTPUT, --output OUTPUT
                        write the symmetrised structure here
```

The prepared MOF-5 sample is written in P1; its atoms are still cubic:

```console
$ xtal symmetry resources/samples/prepared/MOF-5.cif --wyckoff
space group    Fm-3m (#225)
Hall           -F 4 2 3
point group    m-3m
operations     48
orbits         7
standard cell  no
current group  P1 (#1)
hand           chiral, its own enantiomorph

atom  wyckoff  site symmetry
Zn    f        .3m
Zn    f        .3m
[...]
O     c        -43m
O     c        -43m
O     k        ..m
[...]
C     g        2.mm
[...]
H     k        ..m
```

### `xtal bonds`

The structure's bonding graph in the P1 cell: each atom's
coordination number and neighbours with distances, then the
fragments the graph falls into.  What counts as a bond is the
subject of {doc}`bonding </essentials/structure>`.

```console
$ xtal bonds --help
usage: xtal bonds [-h] file

positional arguments:
  file

options:
  -h, --help  show this help message and exit
```

```console
$ xtal bonds resources/samples/prepared/MIL-53.cif
46 bonds in the cell

atom      coordination  neighbours
O0        3            Cr26 1.951 A, Cr27 1.951 A, H36 0.968 A
O1        3            Cr26 1.951 A, Cr27 1.951 A, H37 0.968 A
O2        2            C22 1.277 A, Cr26 1.991 A
[...]
Cr26      6            O0 1.951 A, O1 1.951 A, O2 1.991 A, O4 1.991 A, O6 1.992 A, O8 1.991 A
Cr27      6            O0 1.951 A, O1 1.951 A, O3 1.991 A, O5 1.992 A, O7 1.991 A, O9 1.991 A
H28       1            C15 1.090 A
[...]

1 fragment(s)
    38 atoms  framework
```

### `xtal types`

Every atom's UFF type, how sure the typer is, and why -- the table
the Force Field panel shows, and the first thing to read when a UFF
energy looks wrong ({doc}`UFF and UFF4MOF </energy/uff>`).

```console
$ xtal types --help
usage: xtal types [-h] file

positional arguments:
  file

options:
  -h, --help  show this help message and exit
```

```console
$ xtal types resources/samples/prepared/MIL-53.cif
atom       type    confidence  why
O0         O_3     likely      3 neighbours; bridging or over-bonded
O1         O_3     likely      3 neighbours; bridging or over-bonded
O2         O_3     certain     two neighbours at 133
[...]
C10        C_R     certain     in a flat aromatic ring
[...]
C22        C_2     certain     planar, angles sum to 360
[...]
Cr26       Cr6f3   likely      6 neighbours, in a framework node
Cr27       Cr6f3   likely      6 neighbours, in a framework node
H28        H_      certain     
[...]

38 atoms typed: C_2x4, C_Rx12, Cr6f3x2, H_x10, O_3x10
```

## Converting and preparing

```{index} single: command line; convert
```
```{index} single: command line; prepare
```
```{index} single: command line; formats
```

### `xtal convert`

Reads one file and writes another, in whichever formats the two
extensions name, with optional transformations applied in between.

```console
$ xtal convert --help
usage: xtal convert [-h] [--supercell NA NB NC] [--p1] [--niggli] [--wrap]
                    input output

positional arguments:
  input
  output

options:
  -h, --help            show this help message and exit
  --supercell NA NB NC
  --p1                  expand to P1 before writing
  --niggli              Niggli-reduce the cell
  --wrap                fold every atom into the cell
```

```console
$ xtal convert resources/samples/prepared/MIL-53.cif MIL-53.poscar --niggli
wrote MIL-53.poscar: C8H5CrO5, 38 sites, 38 atoms, P1
```

### `xtal prepare`

A deposited CIF made ready for a calculation: the steps, in the order
they run, are those of {doc}`Prepare for simulation
</structure/prepare>`, and the command prints what each step found.

```console
$ xtal prepare --help
usage: xtal prepare [-h] [--steps STEPS] input output

positional arguments:
  input
  output

options:
  -h, --help     show this help message and exit
  --steps STEPS  comma-separated, from duplicates,deuterium,primitive,disorder
                 ,solvent,cap,hydrogens, run in that order (default: all but
                 cap, which changes the chemistry and is only run when named)
```

```console
$ xtal prepare resources/samples/cod/MOF-5.cif MOF-5-prepared.cif
- the cell is F-centred, 4 times the primitive one (424 atoms against 106)

duplicates no site written twice
deuterium  no deuterium
primitive  primitive cell of the F-centred lattice: 106 atoms, from 424
disorder   nothing is disordered
solvent    no solvent molecules
hydrogens  no hydrogens to add

wrote MOF-5-prepared.cif: C24H12O13Zn4, 106 atoms, P1
```

### `xtal formats`

What can be read and written, by name and extension.  The name is
what `by_extension` resolves a path to, and the extensions are how
`convert`, `-o` and the window decide what to write.

```console
$ xtal formats
name   read  write  extensions
cif    yes   yes    .cif .mcif
xtalproj yes   yes    .xtalproj
poscar yes   yes    .poscar .vasp
pmg-json yes   yes    .json
cssr   yes   yes    .cssr
gen    yes   yes    .gen
xyz    yes   yes    .xyz .extxyz
```

## Energies and relaxations

```{index} single: command line; energy
```
```{index} single: command line; optimize
```
```{index} single: command line; --workspace
```

`xtal energy` and `xtal optimize` are the Force Field panel's
*Single point energy* and *Optimise geometry* ({ref}`mod-forcefield`),
run against a file.  Both take the same engine options; `optimize`
adds the optimiser's.  Which engine to choose, and what each one's
options mean, is the {doc}`energy chapter's </energy/index>`; the
optimisers, the cell and the pressure term are in {doc}`optimisation
</structure/optimisation>` and {doc}`the cell </structure/cell>`.

### `xtal energy`

```console
$ xtal energy --help
usage: xtal energy [-h] [--engine {uff,xtb,mace,orb,mattersim,dftb}]
                   [--coulomb] [--charges {site,qeq,eqeq,zero}]
                   [-p NAME=VALUE] [--workspace DIR]
                   file

positional arguments:
  file

options:
  -h, --help            show this help message and exit
  --engine {uff,xtb,mace,orb,mattersim,dftb}
                        which force field (default: uff)
  --coulomb             include electrostatics (off by default, as in UFF
                        itself)
  --charges {site,qeq,eqeq,zero}
                        where charges come from when electrostatics are on
  -p NAME=VALUE, --param NAME=VALUE
                        an option of an engine that declares them -- DFTB+'s
                        method, parameter directory, dispersion, k-point
                        spacing. `xtal engines` lists them.
  --workspace DIR       write the run into a workspace: a run folder with the
                        log, the trajectory and the final structure, in the
                        layout the application reads
```

With `--workspace`, the run is filed exactly as the window files one
(the next page): the structure gets an entry, the run a numbered
folder, and the command prints where.

```console
$ xtal energy resources/samples/prepared/MOF-5.cif --workspace ws
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

torsion            646.7626
angle              330.0816
bond               259.6529
van der Waals      118.6581
inversion            0.0000
total             1355.1552

max force      110.00889 kcal/mol/A
rms force      80.79335 kcal/mol/A
wrote ws/MOF-5/uff-single-point-001
```

### `xtal optimize`

```console
$ xtal optimize --help
usage: xtal optimize [-h] [--engine {uff,xtb,mace,orb,mattersim,dftb}]
                     [--coulomb] [--charges {site,qeq,eqeq,zero}]
                     [-p NAME=VALUE] [--workspace DIR] [-o OUTPUT]
                     [--method {lbfgs,fire,smart,steepest_descent,conjugate_gradient,quasi_newton,abnr}]
                     [--max-steps MAX_STEPS] [--tolerance TOLERANCE]
                     [--relax-cell] [--stress-tolerance STRESS_TOLERANCE]
                     [--pressure PRESSURE] [-q]
                     file

positional arguments:
  file

options:
  -h, --help            show this help message and exit
  --engine {uff,xtb,mace,orb,mattersim,dftb}
                        which force field (default: uff)
  --coulomb             include electrostatics (off by default, as in UFF
                        itself)
  --charges {site,qeq,eqeq,zero}
                        where charges come from when electrostatics are on
  -p NAME=VALUE, --param NAME=VALUE
                        an option of an engine that declares them -- DFTB+'s
                        method, parameter directory, dispersion, k-point
                        spacing. `xtal engines` lists them.
  --workspace DIR       write the run into a workspace: a run folder with the
                        log, the trajectory and the final structure, in the
                        layout the application reads
  -o OUTPUT, --output OUTPUT
                        write the relaxed structure here
  --method {lbfgs,fire,smart,steepest_descent,conjugate_gradient,quasi_newton,abnr}
  --max-steps MAX_STEPS
  --tolerance TOLERANCE
                        stop when the largest force per atom is below this, in
                        kcal/mol/A (default: 0.05)
  --relax-cell          relax the lattice as well, under a symmetry-adapted
                        strain
  --stress-tolerance STRESS_TOLERANCE
                        with --relax-cell, also stop only when the residual
                        stress is below this, in GPa (default: 0.05)
  --pressure PRESSURE   external pressure in GPa, as a P V term; needs
                        --relax-cell to have any effect
  -q, --quiet           do not print a line per step
```

Without `-q` a line is printed per step; with it, only the summary.
`-o` writes the relaxed structure wherever you say, with or without a
workspace, which is what a pipeline wants:

```console
$ xtal optimize resources/samples/prepared/MIL-53.cif --workspace ws -q -o MIL-53_relaxed.cif
38 atoms, 46 bonds, 92 angles, 80 torsions, 48 inversions

step          energy            max force

converged after 266 steps: -224.8117 kcal/mol to 360.3832, |F|max 0.0417 kcal/mol/A
wrote ws/MIL-53/uff-optimise-001
wrote MIL-53_relaxed.cif
```

A relaxation that hits `--max-steps` first says so on standard error
and exits with status 2, so a script can tell a minimum from a stop:

```console
$ xtal optimize resources/samples/prepared/MIL-53.cif --max-steps 5 -q
note: the geometry is where the optimiser stopped, not a minimum
38 atoms, 46 bonds, 92 angles, 80 torsions, 48 inversions

step          energy            max force

stopped without converging after 5 steps: -160.4975 kcal/mol to 424.6974, |F|max 55.4274 kcal/mol/A
$ echo $?
2
```

### Engine options: `-p`, and the two flags UFF keeps

```{index} single: command line; -p NAME=VALUE
```
```{index} single: command line; --coulomb
```

An engine's options are set with `-p NAME=VALUE`, repeated as often
as needed, using the names `xtal engines` prints (below).  An engine
that declares its options -- and every engine, UFF included, now does
-- is given *those and nothing else*, which is why the two older
flags are ignored when `-p` is available:

:::{warning}
`--coulomb` and `--charges` on `xtal energy` and `xtal optimize` are
**silently ignored** for the UFF engine, because UFF declares its
options and the command then reads only `-p`.  The spelling that
works is `-p coulomb=true -p charges=eqeq` (or `qeq`, `site`,
`zero`).  {doc}`Charges </energy/charges>` documents the option
itself; the two outputs below are the same structure both ways.
:::

```console
$ xtal energy resources/samples/prepared/MOF-5.cif --coulomb --charges eqeq
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

torsion            646.7626
angle              330.0816
bond               259.6529
van der Waals      118.6581
inversion            0.0000
total             1355.1552
[...]
$ xtal energy resources/samples/prepared/MOF-5.cif -p coulomb=true -p charges=eqeq
warning: EQeq charges (Wilmer, Kim and Snurr 2012) from NIST ionisation energies; an estimate to look over, not a published result; metals expanded about Zn +2
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

electrostatic    -3109.1033
torsion            646.7626
angle              330.0816
bond               259.6529
van der Waals      118.6581
inversion            0.0000
total            -1753.9481
[...]
```

An engine that is not installed refuses before anything is read
further, with the message the Force Field panel would show greyed
out:

```console
$ xtal energy resources/samples/prepared/MIL-53.cif --engine xtb
error: tblite is not installed, or not on PATH (XTAL_TBLITE is not set).  It is at https://github.com/tblite/tblite  (conda install tblite -c conda-forge)
```

## Running a module

```{index} single: command line; run
```
```{index} single: command line; modules
```
```{index} single: command line; engines
```
```{index} single: module; from the command line
```

Everything in the *Modules* panel that is a calculation rather than a
dialog -- the relaxed scan, the porosity entries, the PXRD pattern,
the MOF, molecule and net builders, DFTB+'s native runs, the Blender
export -- is `xtal run MODULE.ACTION`.  Two listings say what there
is and what each takes.

### `xtal modules` and `xtal engines`

`xtal modules` prints every module, each of its actions, and each
action's parameters with their type, default and label.  Three
markers matter:

- **`(in the window)`** after an action: it is a dialog or a panel
  and has nothing to run from a script.  The Force Field module's
  three entries are all of this kind -- their command-line
  equivalents are `xtal energy` and `xtal optimize` above.
- **`[unavailable: ...]`** after a module or an action: the binary or
  the Python extra it needs is missing, and the reason is the same
  sentence the window greys the entry out with.
- No `-p` lines under an action: it takes no parameters.

```console
$ xtal modules
forcefield
  forcefield.setup            Setup and atom types...  (in the window)
  forcefield.single-point     Single point energy  (in the window)
  forcefield.optimise         Optimise geometry  (in the window)
dftb   [unavailable: DFTB+ is not installed, or not on PATH (XTAL_DFTB is not set).  It is at https://dftbplus.org  (conda install 'dftbplus=*=nompi_*' -c conda-forge)]
  dftb.setup            Setup and parameters...  (in the window)
[...]
  dftb.dos              Density of states...
      -p spacing=0.1   float, k-point spacing
      -p sigma=0.1   float, broadening
      -p shells=False   bool, resolve s, p and d
[...]
zeopp
  zeopp.diameters        Pore diameters and channels...   [unavailable: Zeo++ is not installed, or not on PATH (XTAL_ZEOPP is not set).  It is at https://www.zeoplusplus.org/]
      -p gas='n2'   choice, probe
      -p probe_radius=1.86   float, probe radius
[...]
  zeopp.volume-grid      Accessible volume (faster)...
      -p gas='n2'   choice, probe
      -p probe_radius=1.86   float, probe radius
      -p occupiable=True   bool, probe-occupiable volume
      -p draw=True   bool, draw the accessible surface
      -p spacing=0.4   float, grid spacing
      -p radii='builtin'   choice, atom radii
      -p radii_file=''   path, radii file
[...]
mof
  mof.build            Build a framework...
      -p topology='pcu'   text, topology
      -p nodes=''   text, node building blocks
      -p edges=''   text, linkers
      -p repeat='1x1x1'   text, repeat the net
[...]
scan
  scan.run              Relaxed scan...
      -p engine='uff'   choice, engine
      -p axis1='volume'   text, first axis
      -p axis1_start=0.0   float, from
      -p axis1_stop=0.0   float, to
      -p axis1_steps=9   int, points
[...]
```

`xtal engines` does the same for the energy engines, in the order the
Force Field panel offers them; these are the names `-p` takes on
`energy`, `optimize` and `scan.run`:

```console
$ xtal engines
uff      UFF
      -p parameter_set='uff4mof'   choice, parameters
      -p coulomb=False   bool, include electrostatics
      -p charges='site'   choice, charges from
      -p vdw_cutoff=12.0   float, van der waals cutoff
      -p skin=2.0   float, neighbour list skin
xtb      xTB (GFN)   [unavailable: tblite is not installed, or not on PATH (XTAL_TBLITE is not set).  It is at https://github.com/tblite/tblite  (conda install tblite -c conda-forge)]
      -p method='gfn2'   choice, method
      -p charge=0.0   float, total charge
[...]
dftb     DFTB+   [unavailable: DFTB+ is not installed, or not on PATH (XTAL_DFTB is not set).  It is at https://dftbplus.org  (conda install 'dftbplus=*=nompi_*' -c conda-forge)]
      -p method='dftb3'   choice, hamiltonian
      -p parameter_directory=''   path, parameter directory
      -p dispersion='none'   choice, dispersion
[...]
```

The same lists, with each setting's range and help text, are the
generated {doc}`module </reference/modules>` and {doc}`engine
</reference/engines>` reference.

### `xtal run`

```console
$ xtal run --help
usage: xtal run [-h] [-p NAME=VALUE] [--workspace DIR] [-o OUTPUT] [-q]
                MODULE.ACTION [file]

positional arguments:
  MODULE.ACTION         which entry to run; `xtal modules` lists them
  file                  the structure to run against; omitted for a module
                        that builds one instead of reading it

options:
  -h, --help            show this help message and exit
  -p NAME=VALUE, --param NAME=VALUE
                        a parameter for the module; repeatable
  --workspace DIR       write the run into a workspace, in the layout the
                        application reads
  -o OUTPUT, --output OUTPUT
                        write the structure it produced here, if it produced
                        one
  -q, --quiet           do not echo the run's progress
```

1. Name the action as `module.action`, exactly as `xtal modules`
   prints it.
2. Give the structure file, unless the module builds one
   (`mof.build`, `build.molecule`, `net.draw`), in which case there
   is no file to give.
3. Set each parameter with `-p name=value`.  Values are typed as
   text and converted by the parameter itself -- `-p draw=False`, `-p
   axis1_steps=3`, `-p "axis1=distance 0, 26"` (quoted, because of the
   space) -- and a name the action does not have is refused rather
   than dropped (see the errors below).  Anything left unset keeps
   the default the listing shows.
4. Add `--workspace DIR` to file the run, `-o FILE` to write the
   structure it produced somewhere of your own, `-q` to keep the
   progress lines off the terminal.

The run's progress is echoed as it goes; then its summary; then, for
a module whose answer is a table, the table itself; and last the run
folder, if there was one:

```console
$ xtal run pxrd.simulate resources/samples/prepared/MIL-53.cif -p two_theta_max=20 --workspace ws
20 reflections, Cu Ka1 (1.5406 A)
20 reflections between 5 and 20.01 deg, strongest (0 0 1) at 8.540 deg

PXRD, Cu Ka1 (1.5406 A)

Calculated pattern, Cu Ka1 (1.5406 A)
    5.00  
    5.75  
    6.50  
    7.25  
    8.00  ############################################
    8.75  #
[...]
          2-theta (degrees)

Reflections (20)
No.  hkl       d (Å)    2θ (°)  I (%)
  1  (0 0 1)   10.3460   8.540  100.00
  2  (1 -1 0)  10.3460   8.540   99.99
  3  (-1 1 1)   8.3860  10.541    5.02
[...]
run folder: ws/MIL-53/pxrd-pxrd-003
```

Worked examples of the other actions are on their own pages, each
with the command and what it printed: {doc}`scan.run
</structure/scans>`, the {doc}`Zeo++ entries </porosity/zeopp>` and
the {doc}`grid entries </porosity/grid>`, {doc}`pxrd.simulate
</porosity/pxrd>`, {doc}`mof.build </frameworks/mof-builder>`,
{doc}`build.molecule </frameworks/molecule-builder>`, {doc}`net.draw
</frameworks/nets>` and the {doc}`native DFTB+ runs </energy/dftb>`.

## Exit status and error messages

```{index} single: command line; exit status
```
```{index} single: command line; error messages
```

Every command returns one of five statuses, so a shell script or a
scheduler can act on the outcome without parsing the text:

```{tabularcolumns} |\Y{0.12}|\Y{0.88}|
```

| Status | Meaning |
|---|---|
| `0` | Done, and -- for `optimize` and `run` -- the result is a good one: the relaxation converged, the module reported success. |
| `1` | Refused or failed before or during the run: a file that does not exist, a parameter or option that is wrong, an engine or binary that is not installed, a module entry that only the window can perform.  The reason is on standard error as `error: ...`. |
| `2` | The command ran to the end but the result is not what was asked: `optimize` stopped at `--max-steps` without converging, or the module reported a failure. |
| `130` | Interrupted with Ctrl+C.  `interrupted` is printed on standard error. |
| `143` | Ended by SIGTERM -- what a batch scheduler sends at a job's time limit.  `terminated` is printed on standard error. |

Under `xtal run`, an interrupt or a SIGTERM is the command line's
Stop button: the run folder is closed with the log saying how it
ended, so that what did finish is on disk rather than lost in a
traceback.

The messages, as the command prints them:

```console
$ xtal info nothere.cif
error: no such file: nothere.cif
$ xtal run scan.run resources/samples/prepared/MIL-53.cif -p step=5
error: no parameter called 'step'; this one takes engine, axis1, axis1_start, axis1_stop, axis1_steps, axis2, axis2_start, axis2_stop, axis2_steps, seed, direction, method, max_steps, tolerance, pre_engine, pre_max_steps, pre_tolerance
$ xtal run pxrd.simulate resources/samples/prepared/MIL-53.cif -p step
error: --param wants name=value, not 'step'
$ xtal run pxrd.simulate
error: pxrd.simulate needs a structure to run against: give it a file
$ xtal run forcefield.setup resources/samples/prepared/MIL-53.cif
error: forcefield.setup is performed by the application window and has nothing to run from a script
$ xtal run zeopp.diameters resources/samples/prepared/MIL-53.cif
error: Zeo++ is not installed, or not on PATH (XTAL_ZEOPP is not set).  It is at https://www.zeoplusplus.org/
```

Each of these exits with status 1.  A refusal that comes from deeper
inside a module can still surface as a Python traceback ending in the
sentence the dialog would have shown -- the scan's *b is not free in
SpaceGroup(...)* on the {doc}`scans page </structure/scans>` is one --
which is reported as a bug.
