# Energies, relaxations and scans

## Engines

`capabilities()` lists every engine and whether it runs here; each
missing one names what to install. `help_for("uff")` lists an engine's
options, which `energy()` and `optimize()` take as keywords.

| Engine | What it is | When |
|---|---|---|
| `uff` | UFF, with UFF4MOF's metal-node rows (`parameter_set="uff4mof"`, the default) | always available; seconds on a thousand atoms. A first relaxation, a sanity check, a scan's pre-relaxation |
| `xtb` | GFN-xTB via tblite | electronic structure at semi-empirical cost |
| `dftb` | DFTB+ | needs the binary and Slater–Koster parameters (`DFTB_PREFIX`) |
| `mace`, `orb`, `mattersim` | machine-learned interatomic potentials, in process | framework geometry closer to DFT than UFF; each needs its own extra |

**UFF is not always the better geometry.** It made MIL-88B's linker
geometry *worse* than the deposited one; the project's prepared samples
were relaxed with ORB-v3 + D3(BJ) for that reason. If a UFF relaxation
moves a linker a long way, say so, and suggest an ML potential if one
is installed.

Units: energies in kcal/mol, forces in kcal/mol/Å, stress in GPa.

## Relaxing

```python
before = s.inspect()
answer = s.optimize(engine="uff", max_steps=500, tolerance=0.05)
print(answer)                        # converged? how far did atoms move?
after = s.inspect()
```

1. **Only on a prepared structure.** An engine refuses coincident atoms
   (`CALCULATION_REFUSED`). It does not refuse disorder or missing
   hydrogens; it computes an energy for them.
2. **The atoms and bonds are the same afterwards.** Compare
   `before.n_atoms`, `n_bonds` and the fragments with `after`. If
   coordination changed, a bond now spans an unphysical length: report
   it, and do not recalculate the bonds to make it go away.
3. **`NOT_CONVERGED`**: the geometry is where the optimiser stopped.
   The energy is not a minimum. More steps, or a structural problem.
4. **`max_displacement`** in `data`: the furthest any atom moved. More
   than about 1 Å from a deposited structure means the engine and the
   experiment disagree. That is worth a sentence to the person.
5. **`relax_cell=True`** relaxes the lattice under the space group's
   allowed strains. For a framework whose pores are empty, the cell
   under UFF can shrink noticeably; report the volume change
   (`answer.message` has it).
6. **`ENGINE_NOTE`** "atom(s) have a type the typer is not sure of":
   look at which (`xtal types FILE`) before trusting the numbers.

Markers (`X`) are held back from the engine and stay where they are;
nothing needs deleting first.

## Scans

`s.run("scan.run", axis1=..., axis1_start=..., axis1_stop=...,
axis1_steps=...)` relaxes the structure at every point of a grid along
one or two coordinates. `help_for("scan.run")` lists the parameters.

- **An axis is written `distance 32, 33`** (P1 atoms), `angle 1, 2, 3`,
  `torsion 1, 2, 3, 4`, `plane 0+1+2, 6+7+8` (`+` joins a centroid,
  which follows its atoms), or a cell parameter (`a`, `b`, `c`,
  `alpha`, `beta`, `gamma`, `volume`).
- **A scan holds a coordinate; it does not freeze atoms.** The profile
  is the material's, not a constraint's.
- **A coordinate the group ties is refused before the first point**
  (`MODULE_FAILED`, "the space group ties it"). `reduce_to_p1()` first
  only if the person wants the symmetry broken; the scan never drops it
  on its own.
- **An unconverged point is NaN**, never a number. Both directions are
  walked by default and reported apart; a difference between them is
  hysteresis or an unconverged neighbour, not noise to average.
- **It is slow.** Ni2Cl2BTDD under UFF is about 0.44 s a step, so a
  12×12 grid is hours. Every point is written the moment it finishes.
  Tell the person the size before starting a large grid.
- A scan returns no structure. The points are files in the run folder,
  and `report.json` opens the landscape in the window.
