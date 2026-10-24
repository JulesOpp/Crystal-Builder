# Written 2026-09-19 against Crystal-Builder e35ebe1 (base 3cd15e2, v0.2.1).
"""Every door a non-positive tolerance can walk through, one
subprocess each, so a segfault names its door instead of taking the
probe with it."""
import subprocess
import sys

CASES = {
    "symmetry.detect(-1)":
        "s=r();symmetry.detect(s, -1.0)",
    "symmetry.detect(0)":
        "s=r();symmetry.detect(s, 0.0)",
    "symmetry.assign_wyckoff(-1)":
        "s=r();symmetry.assign_wyckoff(s, -1.0)",
    "symmetry.standardize(-1)":
        "s=r();symmetry.standardize(s, -1.0)",
    "symmetry.asymmetrize(-1)":
        "s=r();symmetry.asymmetrize(s, -1.0)",
    "subgroups at -1":
        "s=r();from xtal.core import subgroups;"
        "subgroups.descend(s, symmetry.detect(s))",
    "supercell.niggli(eps=-1)":
        "s=r();from xtal.core import supercell;"
        "supercell.niggli_reduce(s, eps=-1.0)",
    "commands FindSymmetry(-1)":
        "s=r();from xtal.commands import symmetry as cs;"
        "c=cs.FindSymmetry(symprec=-1.0);print(c)",
}
HEAD = ("from xtal.core import symmetry\n"
        "from xtal.io import FORMATS\n"
        "def r():\n"
        "    return FORMATS.read('resources/samples/ZIF-8.cif')\n")

for label, body in CASES.items():
    p = subprocess.run([sys.executable, "-c", HEAD + body],
                       capture_output=True, text=True)
    last = (p.stderr.strip().splitlines() or [""])[-1]
    print(f"{label:32s} rc={p.returncode:<5d} {last[:88]}")

print("\nand the CLI, which is the reported door:")
for args in (["--symprec", "-1"], ["--symprec", "0"],
             ["--symprec", "-1", "--wyckoff"]):
    p = subprocess.run([".venv/bin/xtal", "symmetry",
                        "resources/samples/ZIF-8.cif", *args],
                       capture_output=True, text=True)
    last = (p.stderr.strip().splitlines() or [""])[-1]
    print(f"  xtal symmetry {' '.join(args):28s} rc={p.returncode:<5d} "
          f"{last[:70]}")
