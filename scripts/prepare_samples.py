"""Write the prepared half of Open Sample from the COD samples.

    python scripts/prepare_samples.py            # prepare, keep relaxed
    python scripts/prepare_samples.py --relax    # and relax RELAXED again
    python scripts/prepare_samples.py --check    # exit 1 if it would change

Each COD framework through :func:`xtal.core.prepare.prepare` -- every
step, in order -- and written to ``resources/samples/prepared`` under
the same name.  The COD files are never touched: they are the
depositors' crystals, disorder and all, and these are models made
from them, which is a different thing to ship and is said so in
``PROVENANCE.md``.

**Some are relaxed as well, and it takes a model this project does
not ship.**  A refinement's linker geometry is sometimes wrong in ways
no preparation can see -- MIL-100's powder model has ring C-C bonds of
1.45-1.58 A and a C-C to its carboxylate of 1.61 -- and those are
relaxed, positions only at the experimental cell, with ORB-v3
(``conservative-inf-omat``; float64, and float32-high above
:data:`FLOAT32_ABOVE` atoms) and D3(BJ) through torch-dftd at
MOFSimBench's settings (xc pbe, 40 Bohr, bj).  UFF was tried first and
made MIL-88B worse: ring angles 115-123 degrees from 119-120, O-C-O
115 from 118, the ring-to-carboxylate bond 1.56 A.  MACE-MP-MOF0 was
not usable: it knows no Cr, Mn or Eu.

``--relax`` needs ``orb-models`` and ``torch-dftd``, and runs for
hours on a laptop; without it the relaxed files already here are
kept, re-prepared and checked atom for atom against a fresh
preparation, so a change to the preparation that would alter one is
still caught.  ``--check`` compares element by element, and the
unrelaxed files coordinate by coordinate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCE = ROOT / "resources" / "samples" / "cod"
TARGET = ROOT / "resources" / "samples" / "prepared"

#: The frameworks whose refined linker geometry is relaxed, and why.
RELAXED = {
    "MIL-100": "powder model: ring C-C 1.45-1.58 A, C-O to 1.36, "
               "ring-carboxylate C-C to 1.61",
    "MIL-101": "powder model: ring C-C to 1.46 A, C-O 1.21-1.36, "
               "O-C-O 115-126 degrees",
    "MIL-88B": "O-C-O 118 degrees, C-O to 1.32 A",
    "MIL-53": "carboxylate C-O 1.17 A",
    "Al-soc-MOF-1": "the ordered ring's ipso carbon is left at the "
                    "average of two tilts, an 88 degree ring angle",
    "pbz-MOF-1": "acetate C-O to 1.47 A, O-C-O to 132 degrees",
}

#: Tried, and not relaxed, and why -- so that nobody tries again
#: without reading this.
NOT_RELAXED = {
    "Mn-BTT": "its extra-framework Mn slid 1.42 A, taking a methanol "
              "oxygen and four Mn-Cl and Mn-O bonds with it: the cell "
              "holds one of the one and a half the charge wants, and "
              "the framework's own geometry needed nothing",
}

#: How converged a relaxation is asked to be, eV/A.
FMAX = 0.03

#: Above this many atoms ORB runs in ``float32-high``.  In float64
#: MIL-100's 3264 atoms need 4.4 GB and two minutes a force call on a
#: laptop with 8 GB, which is a day for the pair; float32-high is 33 s.
#: Measured on MIL-88B relaxed both ways: the same structure to 0.001 A
#: on every heavy atom and 0.004 A on the hydrogens, in 58 steps
#: against 59.
FLOAT32_ABOVE = 2000


def prepared(name: str):
    """The COD file ``name`` through every preparation step."""
    from xtal.core import prepare
    from xtal.io import FORMATS

    structure = FORMATS.read(SOURCE / f"{name}.cif")
    out, _said = prepare.prepare(structure)
    out.meta["title"] = f"{name}_prepared"
    return out


def relax(structure):
    """Positions only, at this cell: ORB-v3 + D3(BJ).  Returns the
    structure with its sites moved and a line saying how it went."""
    import torch

    from xtal.core import p1

    n = p1.expand(structure).n_atoms
    precision = "float32-high" if n > FLOAT32_ABOVE else "float64"
    working = torch.float32 if n > FLOAT32_ABOVE else torch.float64
    default = torch.get_default_dtype()
    torch.set_default_dtype(working)
    try:
        from ase import Atoms
        from ase.calculators.mixing import SumCalculator
        from ase.optimize import LBFGS
        from ase.units import Bohr
        from orb_models.forcefield import pretrained
        from orb_models.forcefield.inference.calculator import (
            ORBCalculator,
        )
        from torch_dftd.torch_dftd3_calculator import (
            TorchDFTD3Calculator,
        )

        cell = p1.expand(structure)
        atoms = Atoms(symbols=list(cell.elements), positions=cell.cart,
                      cell=np.asarray(structure.lattice.matrix),
                      pbc=True)
        model, adapter = pretrained.orb_v3_conservative_inf_omat(
            device="cpu", precision=precision, compile=False)
        torch.set_default_dtype(working)
        d3 = TorchDFTD3Calculator(device="cpu", dtype=torch.float64,
                                  xc="pbe", damping="bj",
                                  cutoff=40.0 * Bohr)
        atoms.calc = SumCalculator(
            [ORBCalculator(model, adapter, device="cpu"), d3])
        search = LBFGS(atoms, logfile=None)
        converged = search.run(fmax=FMAX, steps=3000)
        inverse = np.linalg.inv(np.asarray(structure.lattice.matrix))
        out = moved(structure, np.mod(atoms.get_positions() @ inverse,
                                      1.0))
        worst = float(np.linalg.norm(atoms.get_forces(), axis=1).max())
        return out, (f"{precision}, {search.get_number_of_steps()} "
                     f"steps, largest force {worst:.3f} eV/A"
                     f"{'' if converged else ' -- NOT CONVERGED'}")
    finally:
        torch.set_default_dtype(default)


#: How far past the perception cutoff a relaxation may stretch a bond
#: before it counts as broken, A.
STRETCH = 0.1


def moved(structure, frac):
    """``structure`` with its atoms at ``frac``, refused if that changed
    the chemistry.

    No bond may appear, and none may break -- except by stretching a
    little past the distance rule: MIL-100's relaxation puts a
    quarter of its trimers' waters 2.28-2.31 A from their iron, the
    trans effect of the mu3-oxo, where the Fe-O rule stops at 2.28.
    The water is still on its iron; the rule no longer sees it, and
    opened as it was the model would show loose water, which a second
    Prepare would take out of the pores and leave the trimer charged.
    Such a bond is written into the file as a bond, which is what the
    CIF's bond loop is for.  Mn-BTT's relaxation, which bonded a Mn to
    a carbon, is what the rest of the rule refuses.
    """
    from xtal.core import bonding
    from xtal.core.structure import Bond

    out = structure.copy()
    for site, position in zip(out.sites, frac, strict=True):
        site.frac = np.asarray(position, dtype=float)
    out.touch()
    before, after = _bonds(structure), _bonds(out)
    if after - before:
        raise RuntimeError(f"the relaxation made {len(after - before)} "
                           f"new bond(s); not writing it")
    rules = bonding.BondRules.from_dict(structure.bond_rules)
    matrix = np.asarray(out.lattice.matrix)
    for i, j in sorted(before - after):
        delta = out.sites[j].frac - out.sites[i].frac
        image = -np.rint(delta)
        length = float(np.linalg.norm((delta + image) @ matrix))
        _lo, hi = rules.cutoff(out.sites[i].element,
                               out.sites[j].element)
        if length > hi + STRETCH:
            raise RuntimeError(f"the relaxation broke a bond, "
                               f"{out.sites[i].label}-"
                               f"{out.sites[j].label} at {length:.2f} "
                               f"A; not writing it")
        out.add_bond(Bond(i, j, tuple(int(t) for t in image)))
    return out


def _bonds(structure) -> set:
    """The perceived bonds, as atom pairs: a relaxation may move the
    atoms and never the chemistry."""
    from xtal.core import bonding

    return {(min(b.i, b.j), max(b.i, b.j))
            for b in bonding.perceive(structure)}


def _same_atoms(a, b) -> bool:
    from xtal.core import p1

    return list(p1.expand(a).elements) == list(p1.expand(b).elements)


def _same_positions(a, b, tolerance=1e-4) -> bool:
    from xtal.core import p1

    fa, fb = p1.expand(a).frac, p1.expand(b).frac
    if fa.shape != fb.shape:
        return False
    delta = fa - fb
    delta -= np.rint(delta)
    return float(np.abs(delta).max()) < tolerance


def main(argv=None) -> int:
    from xtal.io import FORMATS

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--relax", action="store_true",
                        help="relax the RELAXED frameworks again")
    parser.add_argument("--check", action="store_true",
                        help="write nothing; exit 1 if anything would "
                             "change")
    parser.add_argument("names", nargs="*",
                        help="only these (default: every COD sample)")
    args = parser.parse_args(argv)

    names = args.names or sorted(p.stem for p in SOURCE.glob("*.cif"))
    TARGET.mkdir(exist_ok=True)
    stale = []
    for name in names:
        fresh = prepared(name)
        target = TARGET / f"{name}.cif"
        shipped = FORMATS.read(target) if target.is_file() else None
        if name in RELAXED and args.relax and not args.check:
            fresh, said = relax(fresh)
            print(f"{name}: relaxed, {said}")
        elif name in RELAXED:
            # The relaxation is not repeated; the atoms still have to
            # be the ones a fresh preparation makes.
            if shipped is None or not _same_atoms(shipped, fresh):
                stale.append(name)
                print(f"{name}: prepared atoms differ from the shipped "
                      f"relaxed file -- run with --relax")
            continue
        if args.check:
            if shipped is None or not _same_positions(shipped, fresh):
                stale.append(name)
                print(f"{name}: would change")
            continue
        FORMATS.write(fresh, target)
        print(f"{name}: wrote {target.relative_to(ROOT)}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
