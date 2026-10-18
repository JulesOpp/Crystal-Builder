"""Write the shipped rods into ``xtal/mof/library/rods``.

    python scripts/rod_blocks.py MOF303.cif          # write them
    python scripts/rod_blocks.py MOF303.cif --check  # exit 1 if changed

Each rod is cut out of a crystal with :func:`xtal.mof.rod.from_structure`
and its PoE shape chosen there, once, as the reading that gives the
net the literature names (measured in the rod track's E0):

* MIL-53 (Cr), the prepared COD sample: the relative-neighbourhood
  graph, **sra**;
* MOF-74 (Zn), the prepared COD sample: the first five shells, to
  3.67 A, **msf** -- with Zn-O bonded to 2.3 A, since perception at the
  default misses the fifth Zn-O at 2.17;
* Ni2Cl2BTDD, the COD sample prepared here: the relative-neighbourhood
  graph, **etb**;
* MOF-303 (Al), CCDC 2078717 (activated, 100 K), given on the command
  line since it is not shipped: the first eight shells, to 4.83 A,
  **xhh**;
* Co(BDP), the COD sample (Taylor et al. 2016, P4_122): the first four
  shells, 7.13-7.47 A, below the gap to 8.99, **snp**.  The pyrazolate
  ring stays on the rod, as BTDD's triazolate does, so the linker is
  the phenylene and each point is bonded to the ring's C4.

Then the metal swaps the families are made with, geometry unrelaxed and
said so in the file: MOF-74 Mg, Co, Ni; Ni2Cl2BTDD Co; MIL-53 Al, Fe;
Co(BDP) Zn, whose Zn(BDP) is not in the COD.

A chiral rod says how its neighbours sat in its crystal (``hands``),
which is what a build's ``auto`` makes: MOF-74's and Ni2Cl2BTDD's
alternate, Co(BDP)'s are all one hand.

And from each crystal its linker, into ``rods/linkers``, cut by
:func:`xtal.mof.rod.linker_from_structure` where the rod was cut, so the
two meet at the crystal's own lengths: BDC, dobdc, BTDD, pzdc and BDP.  A
linker whose donors are all named (carboxylates, phenolates) is written
whole, its donor groups kept, so each point a build makes of it says
which donor it is; BTDD's triazolate is no named donor, and BTDD keeps
its bare ``X``, and so does BDP.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xtal.core import bonding, p1, prepare  # noqa: E402
from xtal.core import elements as el  # noqa: E402
from xtal.io import read_cif  # noqa: E402
from xtal.mof import rod  # noqa: E402

SAMPLES = ROOT / "resources" / "samples"

#: name, file, prepare first, shape, bond rules, swaps, linker, hands.
RODS = (
    ("MIL-53_Cr", SAMPLES / "prepared" / "MIL-53.cif", False, "rng",
     None, ("Al", "Fe"), "BDC", ""),
    ("MOF-74_Zn", SAMPLES / "prepared" / "MOF-74.cif", False, 5,
     bonding.BondRules(pair_ranges={("O", "Zn"): (1.5, 2.3)}),
     ("Mg", "Co", "Ni"), "dobdc", "alternating"),
    ("Ni2Cl2BTDD_Ni", SAMPLES / "Ni2Cl2BTDD.cif", True, "rng", None,
     ("Co",), "BTDD", "alternating"),
    ("MOF-303_Al", None, False, 8, None, (), "pzdc", ""),
    ("MBDP_Co", SAMPLES / "cod" / "Co-BDP.cif", False, 4, None,
     ("Zn",), "BDP", "same"),
)


def crystal(path, prepared):
    structure = read_cif(path)
    if prepared:
        structure = prepare.run(structure).structure
    return structure


def cut(path, prepared, shape, rules, name, hands="") -> rod.Rod:
    structure = crystal(path, prepared)
    cell = p1.expand(structure)
    seed = next(i for i, s in enumerate(cell.elements)
                if s != "X" and el.element(s).is_metal)
    made = rod.from_structure(structure, seed, shape=shape, rules=rules,
                              name=name)
    return replace(made, hands=hands)


def rods(mof303) -> dict[str, rod.Rod]:
    made = {}
    for name, path, prepared, shape, rules, swaps, _linker, hands in RODS:
        source = Path(mof303) if path is None else path
        parent = cut(source, prepared, shape, rules, name, hands)
        made[name] = parent
        stem = name.rsplit("_", 1)[0]
        for metal in swaps:
            made[f"{stem}_{metal}"] = replace(parent.with_metal(metal),
                                              name=f"{stem}_{metal}")
    return made


def linker_text(structure, rules) -> str:
    """A crystal's linker as the text of its file: whole when every
    donor it meets is named, else with its bare ``X``."""
    from xtal.mof import donors

    bare = rod.linker_from_structure(structure, rules=rules)
    whole = rod.linker_from_structure(structure, rules=rules, whole=True)
    named = len(donors.find(whole)) == len(bare.connections)
    return (whole if named else bare).text()


def linkers(mof303) -> dict[str, str]:
    """Each crystal's linker, as the text of its file."""
    made = {}
    for _name, path, prepared, _shape, rules, _swaps, linker, _hands \
            in RODS:
        source = Path(mof303) if path is None else path
        made[linker] = linker_text(crystal(source, prepared), rules)
    return made


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mof303", help="MOF-303's CIF (CCDC 2078717)")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    changed = []
    for name, made in rods(args.mof303).items():
        target = rod.LIBRARY / f"{name}.xyz"
        text = made.text()
        old = target.read_text(encoding="utf-8") if target.exists() \
            else None
        if old != text:
            changed.append(name)
            if not args.check:
                made.write(target)
        print(f"{name}: {len(made.symbols)} atoms, "
              f"{len(made.connections)} points, {len(made.edges)} "
              f"shape edges, screw {made.screw()[0]}, hand {made.hand}")
    for name, text in linkers(args.mof303).items():
        target = rod.LINKERS / f"{name}.xyz"
        old = target.read_text(encoding="utf-8") if target.exists() \
            else None
        if old != text:
            changed.append(name)
            if not args.check:
                target.parent.mkdir(exist_ok=True)
                target.write_text(text, encoding="utf-8")
        print(f"{name}: linker, {text.count(chr(10)) - 2} lines")
    if args.check and changed:
        print("would change:", ", ".join(changed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
