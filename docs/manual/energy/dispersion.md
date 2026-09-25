# Dispersion corrections

Dispersion -- the London attraction between atoms that are not bonded
-- is what holds the sheets of a layered material together and what
sets how wide a pore relaxes to.  Some of the energy models in this
chapter carry it, some can be given it, and some run without it.
After this section you know what D3(BJ) is, which engine does what,
and how much the correction moves a relaxed framework's volume.

```{index} single: dispersion
```
```{index} single: D3(BJ)
```
```{index} single: Becke--Johnson damping
```

## What D3(BJ) is

DFT-D3 {cite}`grimme2010d3` is an atom-pairwise dispersion energy
added to an electronic-structure energy that lacks one.  Its
ingredients, in the authors' words: "atom-pairwise specific dispersion
coefficients and cutoff radii that are both computed from first
principles", eighth-order terms beside the sixth, and "fractional
coordination numbers" that interpolate the coefficients between the
chemical environments an atom can be in, so that a carbon in a ring
and a carbon in a methyl are not the same carbon.  "The method only
requires adjustment of two global parameters for each density
functional, is asymptotically exact for a gas of weakly interacting
neutral atoms, and easily allows the computation of atomic forces."

The damping function decides what happens at short range, where the
electronic-structure method already describes the interaction.
Becke--Johnson damping {cite}`grimme2011bj` -- "rational damping to
finite values for small interatomic distances" -- takes the pair term
to a constant rather than to zero as two atoms approach, "has the
advantage of avoiding repulsive interatomic forces at shorter
distances", and needs one fit parameter more than zero damping: three
per functional instead of two.  Written out, with the parameters
named as the application writes them into a DFTB+ input,

$$
E_\mathrm{disp}^{\mathrm{D3(BJ)}} = -\frac{1}{2}\sum_{A \ne B}\;\sum_{n = 6, 8}
  s_n\,\frac{C_n^{AB}}{r_{AB}^{\,n} + \left(a_1 R_0^{AB} + a_2\right)^{n}},
\qquad R_0^{AB} = \sqrt{C_8^{AB} / C_6^{AB}},
$$ (d3bj)

% Checked 2026-09-25 against the rational-damping form in the ORCA 6.1
% manual, eqs. 3.11-3.13 (a sum over A<B there, which is half the sum
% over A != B here).  Julius to confirm against Grimme 2011.

where $C_6^{AB}$ and $C_8^{AB}$ are the pair coefficients, $s_6$ and
$s_8$ scale the two orders, and $a_1$, $a_2$ are the damping
parameters.  The three fitted numbers ($s_8$, $a_1$, $a_2$) belong to
the method the correction is added to: a D3(BJ) fitted for PBE is not
the D3(BJ) fitted for DFTB3.

## Which engine has what

| Engine | Dispersion |
|---|---|
| UFF, UFF4MOF | Its own Lennard-Jones 12-6 term {cite}`rappe1992uff` (eq. {eq}`uff-vdw`), part of the parametrisation; not D3 |
| GFN1-xTB | D3, built into the method {cite}`grimme2017gfn1` |
| GFN2-xTB | D4, incorporated self-consistently {cite}`bannwarth2019gfn2` |
| GFN-FF | Part of the force field's own construction {cite}`spicher2020gfnff`; nothing is added by the application |
| DFTB+ | None of its own; **D3(BJ)** or a Lennard-Jones term with UFF's radii, as a setting |
| MACE-MP-0, -MPA-0, -0b3, -OMAT-0, -MATPES, -MH-1 | None |
| MACE-MP-MOF0 | **Inside the model**: its reference data were PBE-D3(BJ) {cite}`elena2025macemof0` |
| ORB-v3 | None |
| MatterSim | None |

For DFTB+ the application writes the `DftD3` block with
Becke--Johnson damping and $s_6 = 1.0$, $s_8 = 0.5883$, $a_1 =
0.5719$, $a_2 = 3.6017$, whichever Hamiltonian is chosen; the engine's
help says why it is offered at all: DFTB has no dispersion of its own,
and a framework's pore size is a dispersion-bound number, so for a
porous solid this is not an optional refinement.

:::{warning}
MACE-MP-MOF0 already has D3 inside and must never be given it twice.
The engines offer no way to add a correction today, so this cannot
happen in the application; it can in a script that wraps the
engine's calculator.
:::

## The measured effect

**ORB-v3, MatterSim and the MACE-MP models run the bare model.**  The
benchmark their descriptions cite, MOFSimBench
{cite}`krass2025mofsimbench`, ran every model with D3(BJ), computed at
inference time with the torch-dftd package at `dispersion_xc=pbe`,
`dispersion_cutoff=40 Bohr`, `damping=bj` -- so a volume from these
engines is the model's, not the benchmark's.  How much that matters
was measured with the application's own optimiser, cell free, against
the COD cells, with ORB-v3:

| Framework | Relaxed volume, no D3 | Relaxed volume, with D3(BJ) |
|---|---|---|
| MOF-74(Zn) | +0.66 % | −2.02 % |
| MOF-5 | +2.80 % | +2.17 % |

D3 moves a relaxed framework's volume by one to three per cent, and
not always towards experiment.

The prepared sample structures under *Open Sample ▸ Prepared for
simulation* record the same combination in use: six of them (MIL-100,
MIL-101, MIL-88B, MIL-53, Al-soc-MOF-1, pbz-MOF-1) were relaxed,
positions only at the experimental cell, with ORB-v3 and D3(BJ)
through torch-dftd at MOFSimBench's settings, by a script beside the
application rather than by the engine as shipped, after UFF had made
MIL-88B's linker geometry worse rather than better
(`resources/samples/PROVENANCE.md`).

## An open decision

Whether D3 should be offered as an option of the machine-learned
engines, and whether it should be on by default, is a decision for
the author and is recorded as such in `docs/TODO.md`: torch-dftd is
what the benchmark used and pulls in pymatgen, tad-dftd3 is
torch-only, and MACE-MP-MOF0 must be excluded from either.  This
manual describes the current state -- no correction on those engines
-- and will change when the decision does.

## Practical notes

- Relaxing a cell with an engine that has no dispersion gives the
  volume of that engine, which the table above puts a few per cent
  from the corrected one.  Compare against another engine, or hold
  the cell at the experimental value and relax the positions.
- For DFTB+ on a porous solid, choose a dispersion setting; *None* is
  there for comparison.
- D3's parameters belong to the method they were fitted with.  Do not
  read the DFTB+ values across to another engine.

## Settings

Dispersion is a setting of the {ref}`DFTB+ engine <engine-dftb>` only.
The MACE-MP-MOF0 choice is described under {ref}`MACE <engine-mace>`.
