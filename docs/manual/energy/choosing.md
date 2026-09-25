# Choosing a model

No one engine is right for every framework, and the application does
not choose for you.  What it does is say, for each engine, what it
needs before it can run, what it provides, what it costs, and what it
is known to be bad at.  This section collects those statements --
each is the engine's own description, its help text, or a number
measured and recorded in the repository -- so that you can choose
with them in front of you.

```{index} single: choosing an engine
```
```{index} single: engines; comparison
```

## What each engine needs and provides

```{tabularcolumns} |\Y{0.16}|\Y{0.34}|\Y{0.18}|\Y{0.32}|
```

| Engine | Needs | Provides | Runs |
|---|---|---|---|
| {doc}`UFF / UFF4MOF <uff>` | Nothing: native, in process, every element | forces, stress, charges, types | milliseconds |
| {doc}`xTB (GFN) <xtb>` | The tblite binary (GFN1, GFN2) or the xtb binary (GFN-FF) | forces | seconds, one subprocess per evaluation |
| {doc}`DFTB+ <dftb>` | The DFTB+ binary and a Slater-Koster set covering every element pair | forces | seconds to minutes, one subprocess per evaluation |
| {doc}`MACE <ml>` | The `mace` extra; weights downloaded on first use | forces, stress | in process; 3.32 s an evaluation on MOF-5 (424 atoms, float64, on the developer's CPU as the engine's notes record) |
| {doc}`ORB-v3 <ml>` | The `orb` extra; weights downloaded on first use | forces, stress | in process; 2.58 s (float64), 0.94 s (float32) |
| {doc}`MatterSim <ml>` | The `mattersim` extra; weights downloaded on first use | forces, stress | in process; 0.51 s (float64), 0.33 s (float32) |

*Stress* in the table means an analytic one.  An engine without it
still relaxes a cell, by twelve extra energy evaluations a step
({ref}`xTB <engine-xtb>` and {ref}`DFTB+ <engine-dftb>`; and UFF
itself when electrostatics are on).  UFF's own evaluation on the same
424-atom MOF-5 cell, measured for this draft, is about 5 ms once the
topology is built.

## What the sources say about each

The statements below are quoted or condensed from the engines' own
descriptions and help text and from the numbers recorded beside them.

**UFF and UFF4MOF.**  Covers the whole periodic table and needs
nothing installed.  Its answer is only as good as its atom types, and
the typing tells you where it is unsure.  UFF4MOF adds rows fitted to
metal nodes in frameworks and types everything else exactly as UFF
does.  On MOFSimBench {cite}`krass2025mofsimbench`, UFF4MOF reaches
62 % volume accuracy on frameworks where the best universal
machine-learned potentials reach 89 %.  On the shipped samples, UFF
made MIL-88B's linker geometry worse rather than better, which is why
the prepared copies of six frameworks were relaxed with ORB-v3 and D3
instead.

**xTB.**  No parameter set to download and no atom typing to get
right.  GFN2-xTB is the most accurate of the three; GFN1-xTB is older
and more robust for metals; GFN-FF is orders of magnitude faster,
which for a framework of a few thousand atoms is the difference
between a relaxation and an afternoon.  No stress of its own.

**DFTB+.**  DFT-like and fast enough to relax a framework UFF can
only approximate.  Needs a parameter set for every element pair, and
its dispersion is a setting you must choose: for a porous solid this
is not an optional refinement.  The only engine here with band
structures, densities of states, Mulliken charges, orbitals,
vibrational modes and molecular dynamics.  No stress of its own on the
engine; its native driver relaxes a cell with DFTB+'s.

**MACE.**  The MACE-MP foundation models answer for a framework
whose metal node UFF has no parameters for, at a cost between a force
field's and tight binding's.  MACE-MP-MOF0 is fine-tuned on
frameworks for phonons, carries D3 inside, and knows 26 elements --
no Cr, Mn, Co or Ni.  The only one of the three that runs on an
Apple GPU.

**ORB-v3.**  Among the most accurate on the framework benchmark, but
that ranking included D3, which the engine does not have: a relaxed
volume differs by a per cent or more from the benchmark's.

**MatterSim.**  The fastest of the three.  Its authors note
relatively low accuracy for organic polymeric systems, which is the
linker half of a framework, so a relaxation here wants checking
against another engine.  No dispersion.

## Reading the numbers you get

- **A large force on a deposited structure is not a fault.**  A
  refinement's bond lengths are not a force field's; on the COD
  MOF-5, UFF4MOF reports a largest force of 110 kcal/mol/Å before any
  relaxation.
- **An energy from one engine is not comparable with an energy from
  another**, and only differences between geometries under the same
  engine and settings mean anything.  A per-term breakdown (UFF's
  bond, angle, torsion, inversion, van der Waals, electrostatic) is
  printed with every single point and is the thing to read when a
  number looks wrong.
- **A relaxed cell volume carries the engine's dispersion, or lack of
  it**: see the measured one-to-three per cent in {doc}`dispersion`.
- **Every warning an engine leaves is part of its answer**: an
  uncertain atom type, a derived angular momentum, a DFTB3 element
  without a Hubbard derivative, an EQeq charge beyond what an atom can
  carry, a model that reports no stress.  The panel shows them above
  the result and the command line prints them to standard error.

## A way to decide

1. Start with **UFF4MOF**.  It is always there, it is fast, and
   `xtal types` (or the panel's atom-type table) tells you at once
   whether the framework's metal was recognised as a node and whether
   any atom is uncertain.
2. If the metal is typed by coordination alone or marked uncertain,
   or the relaxed geometry moves a linker in a way that looks wrong,
   ask a model that needs no typing: **GFN2-xTB** if tblite is
   installed, or a **universal potential** if its extra is.  Between
   the universal potentials, the engines' own notes make MatterSim the
   fastest, ORB-v3 the one the framework benchmark (with D3) ranks
   among the most accurate, and MACE-MP-MOF0 the one fitted to
   frameworks -- where its 26 elements cover the structure.
3. For a volume or a pore size, remember which engines carry
   dispersion ({doc}`dispersion`), and check a relaxed cell against
   another engine or against the experimental cell.
4. For anything electronic -- a band structure, a density of states,
   charges from a self-consistent calculation -- **DFTB+** is the only
   engine here that computes it.

What this section does not do is rank the engines' accuracy for a
class of framework.  The repository records no such benchmark of its
own, and the manual will not invent one; the author is the person to
ask.
