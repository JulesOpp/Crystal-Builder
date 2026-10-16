# Written 2026-09-19 against Crystal-Builder e35ebe1 (base 3cd15e2, v0.2.1).
"""Measure the set-of-identities fix for Structure.add_bond.

Baseline is the shipped O(n^2) scan; "fixed" monkeypatches the exact
body the plan specifies (a lazily built set of ``_bond_identity``
tuples, invalidated by TOPOLOGY|SYMMETRY, updated in place on a
successful add).  Nothing tracked is written; the projects go to a
temp directory.
"""
import os
import tempfile
import time

from xtal import Bond
from xtal.core import bonding, p1, symmetry
from xtal.core.structure import Change, Structure
from xtal.io import FORMATS
from xtal.io import project as proj

SAMPLES = ("MOF-5", "MFU4l", "HKUST1")
_MASK = Change.TOPOLOGY | Change.SYMMETRY
_ORIGINAL = Structure.add_bond


def _ids(self):
    stamp = self._stamp(_MASK)
    cached = getattr(self, "_ids_cache", None)
    if cached is None or cached[0] != stamp:
        cached = (stamp, {self._bond_identity(b) for b in self.bonds})
        self._ids_cache = cached
    return cached[1]


def _fast_add_bond(self, bond) -> bool:
    self._check_bond(bond)
    identity = self._bond_identity(bond)
    ids = _ids(self)
    if identity in ids:
        return False
    self.bonds.append(bond)
    self.touch(Change.TOPOLOGY)
    ids.add(identity)
    self._ids_cache = (self._stamp(_MASK), ids)
    return True


def make_project(tmp, name):
    s = FORMATS.read(f"resources/samples/{name}.cif")
    bonds = [Bond(b.i, b.j, b.image) for b in bonding.perceive(s)
             if b.i != b.j or b.image != (0, 0, 0)]
    p1s = symmetry.reduce_to_p1(s)
    p1s.set_bonds(bonds)
    path = os.path.join(tmp, f"{name}.xtalproj")
    proj.write_project(p1s, path)
    return path, len(p1s.sites), len(bonds)


def timed(fn, *a):
    t = time.perf_counter()
    fn(*a)
    return (time.perf_counter() - t) * 1000.0


def main():
    tmp = tempfile.mkdtemp(prefix="tier1-addbond")
    print("read_project (the add_bond loop at xtal/io/project.py:191)")
    print(f"{'sample':12s} {'sites':>6s} {'bonds':>6s} "
          f"{'before ms':>10s} {'after ms':>9s} {'speedup':>8s}")
    rows = []
    for name in SAMPLES:
        try:
            path, n_sites, n_bonds = make_project(tmp, name)
        except Exception as exc:                    # noqa: BLE001
            print(f"{name:12s} skipped: {exc}")
            continue
        Structure.add_bond = _ORIGINAL
        before = min(timed(proj.read_project, path) for _ in range(3))
        Structure.add_bond = _fast_add_bond
        after = min(timed(proj.read_project, path) for _ in range(3))
        Structure.add_bond = _ORIGINAL
        rows.append((name, n_sites, n_bonds, before, after))
        print(f"{name:12s} {n_sites:6d} {n_bonds:6d} "
              f"{before:10.1f} {after:9.1f} {before / after:7.1f}x")

    print("\nreduce_to_p1 with stored bonds "
          "(the loop at xtal/core/symmetry.py:243)")
    for name in SAMPLES:
        s = FORMATS.read(f"resources/samples/{name}.cif")
        try:
            s.set_bonds([Bond(b.i, b.j, b.image)
                         for b in bonding.perceive(s)][:len(s.sites) * 4])
        except Exception as exc:                    # noqa: BLE001
            print(f"{name:12s} skipped: {exc}")
            continue
        Structure.add_bond = _ORIGINAL
        before = min(timed(symmetry.reduce_to_p1, s) for _ in range(3))
        Structure.add_bond = _fast_add_bond
        after = min(timed(symmetry.reduce_to_p1, s) for _ in range(3))
        Structure.add_bond = _ORIGINAL
        out = symmetry.reduce_to_p1(s)
        print(f"{name:12s} {len(s.bonds):5d} stored -> "
              f"{len(out.bonds):6d} bonds   "
              f"before {before:8.1f} ms  after {after:7.1f} ms  "
              f"{before / after:5.1f}x")

    print("\nidentical answers check (same bonds, same order):")
    for name in SAMPLES:
        path, _, _ = make_project(tmp, name)
        Structure.add_bond = _ORIGINAL
        a = proj.read_project(path)[0]
        Structure.add_bond = _fast_add_bond
        b = proj.read_project(path)[0]
        Structure.add_bond = _ORIGINAL
        same = [x.to_dict() for x in a.bonds] == [
            x.to_dict() for x in b.bonds]
        print(f"  {name:12s} {len(a.bonds):6d} bonds  identical={same}")


if __name__ == "__main__":
    main()
