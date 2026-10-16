# Written 2026-09-19 against Crystal-Builder e35ebe1 (base 3cd15e2, v0.2.1).
"""How long Stop stays dead, per candidate polling point.

`optimize.steps` takes ``cancel=`` and never polls it, so the only
granularity today is the consumer breaking the generator: one whole
optimiser step.  A relaxed scan does not even do that -- it polls once
per grid point.  This measures the three units: one scan point, one
optimiser step, one energy evaluation.
"""
import time

from xtal.core import p1
from xtal.ff import optimize
from xtal.ff.registry import ENGINES
from xtal.io import FORMATS

for name in ("MFU4l", "MIL53"):
    s = FORMATS.read(f"resources/samples/{name}.cif")
    calc = ENGINES.get("uff").build(s)
    cell = p1.expand(s)

    t = time.perf_counter()
    calc.compute(cell.cart, s.lattice.matrix)
    one_eval = time.perf_counter() - t

    for relax_cell in (False, True):
        problem_calls = []
        real = calc.compute

        def counted(positions, matrix, _real=real):
            problem_calls.append(time.perf_counter())
            return _real(positions, matrix)

        calc.compute = counted
        marks = []
        t0 = time.perf_counter()
        n = 0
        for step in optimize.steps(calc, s, "lbfgs",
                                   relax_cell=relax_cell,
                                   max_steps=10):
            marks.append(time.perf_counter())
            n += 1
        total = time.perf_counter() - t0
        calc.compute = real
        gaps = [b - a for a, b in zip(marks, marks[1:])]
        per_step = total / max(n, 1)
        per_eval = total / max(len(problem_calls), 1)
        print(f"{name:8s} relax_cell={str(relax_cell):5s} "
              f"{n:3d} steps  {len(problem_calls):4d} evaluations  "
              f"{len(problem_calls) / max(n, 1):5.1f} eval/step  "
              f"step {per_step * 1000:8.1f} ms  "
              f"eval {per_eval * 1000:7.1f} ms  "
              f"slowest step {max(gaps or [0]) * 1000:8.1f} ms")
    print(f"{name:8s} one bare compute() = {one_eval * 1000:.1f} ms, "
          f"{len(s.sites)} sites / {cell.n_atoms} atoms")

print("\nscan: max_steps default and what one point costs")
from xtal.modules import scan as scan_mod                     # noqa: E402
for p in scan_mod.MODULE.actions[0].params:
    if "step" in p.name:
        print(f"  {p.name} default={p.default}")
