"""
xtal.cli
========
The headless command line: read a structure, inspect or transform it,
write it back out.

Everything here is a thin wrapper over the core, which is the point --
if a task needs the GUI to be scriptable, the answer is to expose it
here (and in the Python console) rather than to automate the widgets.

    xtal info quartz.cif
    xtal symmetry quartz.cif --symprec 1e-3
    xtal convert quartz.cif quartz.xyz --supercell 2 2 2
    xtal bonds quartz.cif
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xtal.core import bonding, properties, supercell, symmetry
from xtal.io import FORMATS


def _load(path: str):
    structure = FORMATS.read(path)
    for warning in structure.meta.get("warnings", []):
        print(f"warning: {warning}", file=sys.stderr)
    return structure


def _apply_transforms(structure, args):
    if getattr(args, "supercell", None):
        na, nb, nc = args.supercell
        structure = supercell.supercell(structure, na, nb, nc)
    if getattr(args, "p1", False):
        structure = symmetry.reduce_to_p1(structure)
    if getattr(args, "niggli", False):
        structure = supercell.niggli_reduce(structure)
    if getattr(args, "wrap", False):
        structure = supercell.wrap_into_cell(structure)
    return structure


# ======================================================================
#  COMMANDS
# ======================================================================

def cmd_info(args) -> int:
    structure = _load(args.file)
    print(properties.info(structure).text())
    if structure.meta.get("title"):
        print(f"title          {structure.meta['title']}")
    return 0


def cmd_symmetry(args) -> int:
    structure = _load(args.file)
    try:
        info = symmetry.detect(structure, symprec=args.symprec,
                               angle_tolerance=args.angle_tolerance)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"space group    {info.international} (#{info.number})")
    print(f"Hall           {info.hall}")
    print(f"point group    {info.pointgroup}")
    print(f"operations     {info.n_operations}")
    print(f"orbits         {info.n_orbits}")
    print(f"standard cell  "
          f"{'yes' if info.is_standard_setting else 'no'}")
    print(f"current group  {structure.space_group.short_name} "
          f"(#{structure.space_group.number})")

    if args.wyckoff:
        print("\natom  wyckoff  site symmetry")
        from xtal.core import p1
        cell = p1.expand(structure)
        for k in range(cell.n_atoms):
            print(f"{cell.elements[k]:<5s} {info.wyckoffs[k]:<8s} "
                  f"{info.site_symmetry[k]}")

    if args.output:
        reduced, report = symmetry.asymmetrize(
            structure, symprec=args.symprec, standardize_cell=True)
        print(f"\n{report.message}")
        for warning in report.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if not report.ok:
            return 1
        FORMATS.write(reduced, args.output)
        print(f"wrote {args.output}")
    return 0


def cmd_convert(args) -> int:
    structure = _apply_transforms(_load(args.input), args)
    FORMATS.write(structure, args.output)
    info = properties.info(structure)
    print(f"wrote {args.output}: {info.formula}, "
          f"{info.n_sites} sites, {info.n_atoms} atoms, "
          f"{structure.space_group.short_name}")
    return 0


def cmd_bonds(args) -> int:
    from xtal.core import p1
    structure = _load(args.file)
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    coordination = graph.coordination()

    print(f"{len(graph.bonds)} bonds in the cell\n")
    print("atom      coordination  neighbours")
    for k in range(cell.n_atoms):
        partners = ", ".join(
            f"{cell.elements[j]}{j} {b.distance:.3f} A"
            for j, b in zip(graph.neighbors(k), graph.bonds_of(k),
                            strict=True))
        name = f"{cell.elements[k]}{k}"
        print(f"{name:<9s} {coordination[k]:<12d} {partners}")

    fragments = graph.fragments()
    print(f"\n{len(fragments)} fragment(s)")
    for frag in fragments:
        print(f"  {len(frag):4d} atoms  {frag.kind}")
    return 0


def cmd_formats(args) -> int:
    print("name   read  write  extensions")
    for fmt in FORMATS:
        print(f"{fmt.name:<6s} {'yes' if fmt.can_read else ' - ':<5s} "
              f"{'yes' if fmt.can_write else ' - ':<6s} "
              f"{' '.join(fmt.extensions)}")
    return 0


# ======================================================================
#  ENTRY POINT
# ======================================================================

def build_parser() -> argparse.ArgumentParser:
    from xtal import __version__

    parser = argparse.ArgumentParser(
        prog="xtal",
        description="Build, inspect and convert crystal structures.")
    parser.add_argument("--version", action="version",
                        version=f"Crystal Builder {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="cell, formula, density")
    p.add_argument("file")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("symmetry", help="detect the space group")
    p.add_argument("file")
    p.add_argument("--symprec", type=float,
                   default=symmetry.DEFAULT_SYMPREC,
                   help="distance tolerance in Angstrom "
                        "(default: %(default)g)")
    p.add_argument("--angle-tolerance", type=float,
                   default=symmetry.DEFAULT_ANGLE_TOLERANCE,
                   help="angle tolerance in degrees, negative to "
                        "derive it from symprec")
    p.add_argument("--wyckoff", action="store_true",
                   help="list Wyckoff letters and site symmetries")
    p.add_argument("-o", "--output",
                   help="write the symmetrised structure here")
    p.set_defaults(func=cmd_symmetry)

    p = sub.add_parser("convert", help="convert and transform")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--supercell", nargs=3, type=int,
                   metavar=("NA", "NB", "NC"))
    p.add_argument("--p1", action="store_true",
                   help="expand to P1 before writing")
    p.add_argument("--niggli", action="store_true",
                   help="Niggli-reduce the cell")
    p.add_argument("--wrap", action="store_true",
                   help="fold every atom into the cell")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("bonds", help="bonds, coordination, fragments")
    p.add_argument("file")
    p.set_defaults(func=cmd_bonds)

    p = sub.add_parser("formats", help="list supported file formats")
    p.set_defaults(func=cmd_formats)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"error: no such file: {Path(args.file).name}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
