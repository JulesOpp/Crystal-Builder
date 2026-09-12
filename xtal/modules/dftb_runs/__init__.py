"""
xtal.modules.dftb_runs
======================
DFTB+'s own runs, as entries of the DFTB+ module.

The three entries the DFTB+ module had are the Force Field panel's --
a single point and an optimisation that *our* optimiser drives, one
DFTB+ evaluation a step.  These are the other kind: one invocation in
which DFTB+ does what it does natively -- a band structure, a density
of states, charges, its own driver, molecular dynamics, a Hessian --
and this package writes the input, runs it in the run folder, and
reads the answer.  Nothing DFTB+ can do itself is done again here.

**The Hamiltonian is the DFTB+ panel's.**  Parameter set, dispersion,
temperature and the rest are chosen once, in the panel, and every run
here reads them from there (``job.params["hamiltonian"]``, filled in by
the run dialogs) -- a band structure computed with a different
Hamiltonian from the relaxation beside it would be a figure of a
different crystal.  A run from the CLI gets the panel's defaults.
"""
