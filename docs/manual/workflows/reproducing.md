(workflows-reproducing)=
# Reproducing a result

A result is reproducible when someone else -- or you, a year on --
can run the same structure through the same version with the same
options and get the same number.  After this page you know which four
things to record, where each already is when a run was filed in a
workspace, and how this manual's own version relates to the program
you have.

```{index} single: reproducibility
```
```{index} single: version; recording
```

## What to record

1. **The version.**  `xtal --version` prints it, and it is the first
   line of every `run.log`:

   ```console
   $ xtal --version
   Crystal Builder 0.3.1.dev49+g0db248ed6.d20260926
   ```

   Record it as printed.  For a copy installed from a source checkout
   in editable mode, be aware that the installed package keeps the
   version it was installed at, so `git describe --tags` in the
   checkout is the second number to write down (the manual's own
   build reads its version from `git describe` for exactly this
   reason).

2. **The structure file**, as it went in.  A run filed in a workspace
   has it already: the entry's copy (`ws/MOF-5/MOF-5.cif`) is the
   file the run read, and the log's `source` line says where it came
   from.  If the file was prepared first, keep the `xtal prepare`
   command (or the *Prepare for simulation* steps) with it, because
   the prepared file and not the deposited one is the input.

3. **The engine and its options, as the log prints them.**  The
   block after `engine` in the header is every option the engine was
   given, defaults included, in the spelling `-p` takes -- which is
   also the spelling `xtal engines` prints:

   ```text
   engine         uff  (UFF)
     charges      site
     coulomb      off
     parameter_set uff4mof
     skin         2
     vdw_cutoff   12
   ```

   For an engine run, keep the *Atom types* table beneath it too: a
   UFF energy rests on the typing, and a type overridden in the panel
   ({doc}`UFF and UFF4MOF </energy/uff>`) is a difference the option
   block does not show.

4. **The module action and its parameters**, for `xtal run`: the
   `module` line and the parameter block under it list every
   parameter alphabetically, whether or not it was changed, so the
   header *is* the command line.  This header, for instance, re-runs
   as `xtal run scan.run resources/samples/prepared/MOF-5.cif -p
   axis1=volume -p axis1_start=4250 -p axis1_stop=4350 -p
   axis1_steps=3 -p direction=forward`:

   ```text
   module         scan.run
     axis1        volume
     axis1_start  4250
     axis1_steps  3
     axis1_stop   4350
     axis2        
   [...]
     direction    forward
     engine       uff
     max_steps    500
     method       smart
   [...]
     seed         previous
     tolerance    0.05
   ```

The command line and the window record the same header, because the
module that runs writes it and neither front end does
({doc}`reports <reports>`).  A run made by clicking is therefore as
reproducible from a terminal as one made by typing, and the reverse.

## Re-running

1. Run the same subcommand on the entry's copy of the structure, with
   the options from the header as `-p name=value`.  Filing it with
   `--workspace` into the same workspace puts the new run beside the
   old one under the same entry, with the next number.
2. Compare the two `run.log` files.  The header blocks should differ
   only in `run`, `started` and `finished`; the *Result* blocks are
   the comparison.

Two things in a scan's header matter more than they look:

:::{note}
`seed` and `direction` are part of the result.  A scan point starts
from its relaxed neighbour, so the grid is a walk and not a batch,
and the two directions are drawn apart rather than averaged because
the same target cell relaxed from a neighbour and from the input can
land in different places ({doc}`scans </structure/scans>`).  A scan
re-run with a different `seed` or `direction` is a different
measurement, not a repeat.
:::

:::{note}
An unconverged point is marked, not numbered.  A re-run that converges
where the original did not has not reproduced it; it has finished it.
Compare the `converged` column of `scan.csv` before comparing the
energies.
:::

## This manual and your version

This manual describes Crystal Builder {{ release }}.  Its
{ref}`reference appendix <reference-appendix>` -- every command, module
setting and engine option -- is not written by hand: it is generated
from the application's own registries by the manual's build script,
from the version the manual was built from.  If the number above is
not the one `xtal --version` prints, a setting the appendix lists may
be missing from your copy, or named differently, and `xtal modules`
and `xtal engines` are the authority for what your copy takes.
