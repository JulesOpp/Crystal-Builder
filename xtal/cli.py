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
    xtal types quartz.cif
    xtal energy quartz.cif
    xtal optimize quartz.cif -o relaxed.cif
    xtal modules
    xtal run stub.count quartz.cif --workspace ./ws -p steps=3
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


def _print_subgroups(structure) -> None:
    """The subgroups of the group the structure is in, with what each
    descent would cost.

    The split is the column worth having: most descents split nothing,
    and a list that does not say so reads as if it were broken.  The
    kind is the column after it: a group can appear twice at two
    different indices, once having lost rotations and once having lost
    the centring, and the two are not the same descent.
    """
    from xtal.core import subgroups

    found = subgroups.subgroups_of(structure.space_group)
    if not found:
        print("\nno proper subgroups: this is already the smallest "
              "group there is")
        return
    n_maximal = sum(1 for s in found if s.maximal)
    n_k = sum(1 for s in found if s.k_index > 1)
    n_big = sum(1 for s in found if s.enlarges_the_lattice)
    print(f"\nsubgroups ({len(found)}, {n_k} giving up translations, "
          f"{n_big} on a larger cell, {n_maximal} maximal; conjugates "
          f"share a row)")
    print(f"{'group':<14s} {'no.':>4s} {'idx':>4s} {'kind':>5s} "
          f"{'max':>4s} {'same':>5s}  {'splits':<24s} axes and origin")
    for sub in found:
        split = subgroups.describe_split(structure, sub)
        print(f"{sub.group.hm if sub.group else 'unnamed':<14s} "
              f"{sub.group.number if sub.group else '':>4} "
              f"{sub.index:>4} {sub.kind:>5s} "
              f"{'yes' if sub.maximal else '':>4} "
              f"{('' if sub.n_conjugates == 1 else f'x{sub.n_conjugates}'):>5}"
              f"  {split.summary():<24s} "
              f"{subgroups.basis_description(sub)}")


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
    print(f"hand           "
          f"{symmetry.hand_description(structure.space_group)}")

    if args.subgroups:
        _print_subgroups(structure)

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
    # _load reads the whole file before anything is written, so this
    # was never truncation -- it was a deposited CIF quietly replaced
    # by this program's minimal rendering of it, refinement and all
    # gone, with no prompt and no backup.
    output = Path(args.output)
    if output.exists() and output.resolve() == Path(args.input).resolve():
        raise ValueError(f"{args.output} is the input; convert writes "
                         f"a new file, so give it another name")
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


# ----------------------------------------------------------------------
#  FORCE FIELD
# ----------------------------------------------------------------------

def _calculator(structure, args):
    """Build the engine the arguments ask for, and say what it made of
    the structure before it is used for anything.

    An engine that declares its options (:attr:`Engine.options`) is
    given those and nothing else -- ``-p method=scc`` is how they are
    set here, the same spelling ``xtal run`` uses for a module's
    parameters -- and one that declares none keeps the two flags UFF
    has always had.  Passing both would mean handing an engine a
    keyword it has never heard of.
    """
    from xtal.ff import ENGINES

    engine = ENGINES.get(args.engine)
    options = _engine_options(args)
    # After the options, not before: half of what an external engine
    # needs to be available is in them.
    available = engine.availability(**options)
    if not available:
        raise ValueError(available.reason)
    # The engine, not ``engine.build``: the call is where dummy
    # atoms are held back -- see :mod:`xtal.ff.markers`.
    calculator = engine(structure, **options)
    for warning in calculator.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return calculator


def _engine_options(args) -> dict:
    """The options the arguments give the engine, asked once so the
    calculator and the run's log cannot be told two different things."""
    from xtal.ff import ENGINES

    engine = ENGINES.get(args.engine)
    if engine.options:
        return engine.coerce(_parsed_params(
            getattr(args, "param", None), engine.options))
    return {"coulomb": getattr(args, "coulomb", False),
            "charges": getattr(args, "charges", "site")}


def cmd_types(args) -> int:
    """The atom types, and why each one was chosen.

    Its own command because the typing is the part of a force field
    that decides whether the energy means anything, and it is worth
    being able to look at without running a calculation.
    """
    from xtal.core import p1
    from xtal.ff.uff import typer

    structure = _load(args.file)
    cell = p1.expand(structure)
    typing = typer.assign(structure)

    print("atom       type    confidence  why")
    for index, atom in enumerate(typing.types):
        name = f"{cell.elements[index]}{index}"
        print(f"{name:<10s} {atom.name:<7s} "
              f"{atom.confidence:<11s} {atom.reason}")
    print()
    print(typing.summary())
    return 0


def cmd_energy(args) -> int:
    from xtal.core import p1
    from xtal.ff import record as ff_record

    structure = _load(args.file)
    calculator = _calculator(structure, args)
    cell = p1.expand(structure)
    result = calculator.compute(cell.cart, structure.lattice.matrix)

    print(calculator.summary())
    print()
    print(result.breakdown())
    print()
    print(f"max force      {result.max_force:.5f} kcal/mol/A")
    print(f"rms force      {result.rms_force:.5f} kcal/mol/A")

    recorder = _recorder(args, structure, calculator, "single-point")
    if recorder is not None:
        ff_record.write_single_point(recorder, result)
        print(f"wrote {recorder.folder.path}")
    return 0


def _recorder(args, structure, calculator, kind: str):
    """A run folder in the workspace, when one was asked for.

    ``--workspace`` makes the CLI write exactly what the window writes
    -- the same folder, the same three files, the same log -- so a run
    started from a script is one the window can open.  Without it the
    CLI prints and writes nothing but ``--output``, which is what a
    pipeline wants.
    """
    if not getattr(args, "workspace", None):
        return None
    from xtal.ff import record as ff_record
    from xtal.workspace import Workspace

    workspace = Workspace.create(args.workspace)
    return ff_record.open_run(
        workspace.add_structure(args.file), args.engine, kind,
        structure, calculator, options=_engine_options(args))


def cmd_optimize(args) -> int:
    from xtal.ff import optimize
    from xtal.ff import record as ff_record

    structure = _load(args.file)
    calculator = _calculator(structure, args)
    recorder = _recorder(args, structure, calculator, "optimise")
    print(calculator.summary())
    print()
    print("step          energy            max force")
    if recorder is not None:
        recorder.begin_steps()

    def trace(step):
        if recorder is not None:
            recorder.step(step)
        if args.quiet:
            return True
        print(step.line())
        return True

    result = optimize.run(
        calculator, structure, method=args.method,
        max_steps=args.max_steps, force_tolerance=args.tolerance,
        stress_tolerance=args.stress_tolerance,
        relax_cell=args.relax_cell, pressure=args.pressure,
        callback=trace)

    print()
    print(result.summary())
    if not result.converged:
        print("note: the geometry is where the optimiser stopped, not "
              "a minimum", file=sys.stderr)

    for site, frac in zip(structure.sites, result.frac, strict=True):
        site.frac = frac
    if result.matrix is not None:
        from xtal.core.lattice import Lattice
        structure.lattice = Lattice(result.matrix)
        a, b, c, al, be, ga = structure.lattice.parameters
        print(f"cell           {a:.4f} {b:.4f} {c:.4f}  "
              f"{al:.3f} {be:.3f} {ga:.3f}   "
              f"({structure.lattice.volume:.2f} A^3)")
    structure.touch()
    if recorder is not None:
        ff_record.close_run(recorder, result, final=structure)
        print(f"wrote {recorder.folder.path}")
    if args.output:
        FORMATS.write(structure, args.output)
        print(f"wrote {args.output}")
    return 0 if result.converged else 2


# ----------------------------------------------------------------------
#  MODULES
# ----------------------------------------------------------------------
#
# The registry is headless, so it is runnable from here -- and that is
# not a convenience, it is the proof.  A module that can only be run by
# clicking it is one whose parameters, run folder and log cannot be
# tested without a display.

def cmd_modules(args) -> int:
    from xtal import plugins
    from xtal.modules import MODULES

    plugins.load()
    for module in MODULES:
        available = module.availability()
        mark = "" if available else f"   [unavailable: {available.reason}]"
        print(f"{module.name}{mark}")
        for action in module.actions:
            how = "  (in the window)" if action.shell else ""
            print(f"  {module.name}.{action.name:<16s} "
                  f"{action.label}{how}")
            for param in action.params:
                print(f"      -p {param.name}={param.default_value()!r}"
                      f"   {param.kind}, {param.title.lower()}")
    return 0


def cmd_engines(args) -> int:
    """The energy engines, and what each of them takes.

    The companion to ``xtal modules``, and here for the same reason:
    an engine that declares its options declares them for the dialog,
    the log and this list at once, so there is no second place for the
    spelling to drift.
    """
    from xtal.ff import ENGINES

    for engine in ENGINES:
        available = engine.availability()
        mark = "" if available \
            else f"   [unavailable: {available.reason}]"
        print(f"{engine.name:<8s} {engine.label}{mark}")
        for param in engine.options:
            print(f"      -p {param.name}={param.default_value()!r}"
                  f"   {param.kind}, {param.title.lower()}")
        if not engine.options:
            print("      --coulomb, --charges")
    return 0


def cmd_run(args) -> int:
    """Run one module action against a file, as the window would."""
    from xtal import plugins
    from xtal.modules import MODULES, Job
    from xtal.modules import record as module_record

    plugins.load()
    module, action = MODULES.find(args.action)
    if action.run is None:
        raise ValueError(
            f"{args.action} is performed by the application window "
            f"and has nothing to run from a script")
    available = module.availability()
    if not available:
        raise ValueError(available.reason)
    # A module that builds a structure rather than measuring one has
    # no input file, and the registry has said so since it was
    # written -- so FILE is optional here and required by the action
    # rather than by the parser.
    if action.needs_structure and not args.file:
        raise ValueError(f"{args.action} needs a structure to run "
                         f"against: give it a file")
    structure = _load(args.file) if args.file else None
    params = action.coerce(_parsed_params(args.param, action.params))

    folder = workspace = None
    if args.workspace:
        from xtal.workspace import Workspace
        workspace = Workspace.create(args.workspace)
        entry = (workspace.add_structure(args.file) if args.file
                 else workspace.add_document(module.label))
        folder = module_record.open_run(entry, module, action, params,
                                        structure)
    job = Job(structure=structure, params=params, folder=folder,
              label=args.action,
              on_progress=None if args.quiet else _echo)
    try:
        result = action.run(job)
    except KeyboardInterrupt:
        # Ctrl+C is the command line's Stop button, and a run folder
        # that says where it got to is worth more than a traceback.
        job.cancel.cancel()
        module_record.close_run(folder, error="interrupted")
        print("interrupted", file=sys.stderr)
        return 130
    module_record.close_run(folder, result)
    run_path = folder.path if folder is not None else None
    if workspace is not None and not action.needs_structure \
            and result.ok and result.structure is not None:
        # A build is filed the way the window files one: an entry
        # named after what was built, one CIF written from it, and
        # the run moved underneath.
        filed = workspace.adopt_build(
            result.structure, run=run_path,
            artifacts=getattr(result, "artifacts", ()))
        run_path = filed.run or run_path
        print(f"filed as {filed.path}")
    print(result.summary())
    # A run whose whole answer is a table has to print the table:
    # "peak at 18.75 A" is a headline, not a result.
    if getattr(result, "report", None):
        print()
        print(result.report.as_text())
    if result.detail:
        print(result.detail, file=sys.stderr)
    if args.output and result.structure is not None:
        FORMATS.write(result.structure, args.output)
        print(f"wrote {args.output}")
    if run_path is not None:
        print(f"run folder: {run_path}")
    return 0 if result.ok else 2


def _echo(text: str) -> None:
    print(text, flush=True)


def _parsed_params(pairs, params=None) -> dict:
    """``-p steps=3`` into ``{"steps": "3"}``.

    Left as strings: the parameter itself knows what type it is, and
    guessing here would mean guessing differently from the form.

    Given the ``params`` it is for, a name none of them has is
    refused.  ``coerce`` drops unknown names, which is right for a
    saved session and wrong here: a dialog cannot misspell a name and
    a person typing ``-p step=5`` can, and the run then succeeded
    having measured something else.
    """
    out = {}
    for pair in pairs or ():
        key, sep, value = str(pair).partition("=")
        if not sep or not key.strip():
            raise ValueError(
                f"--param wants name=value, not {pair!r}")
        out[key.strip()] = value
    if params is not None:
        known = [p.name for p in params]
        unknown = [key for key in out if key not in known]
        if unknown:
            raise ValueError(
                f"no parameter called {', '.join(map(repr, unknown))}; "
                f"this one takes {', '.join(known) or 'none'}")
    return out


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
    p.add_argument("--subgroups", action="store_true",
                   help="list the subgroups of the current group that "
                        "need no new cell -- translationengleiche and "
                        "klassengleiche -- and what descending to each "
                        "would split")
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

    p = sub.add_parser("types",
                       help="UFF atom types and why each was chosen")
    p.add_argument("file")
    p.set_defaults(func=cmd_types)

    for name, help_text in (("energy", "single-point energy"),
                            ("optimize", "relax the geometry")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("file")
        p.add_argument("--engine", default="uff",
                       choices=_engine_names(),
                       help="which force field (default: %(default)s)")
        p.add_argument("--coulomb", action="store_true",
                       help="include electrostatics (off by default, "
                            "as in UFF itself)")
        p.add_argument("--charges", default="site",
                       choices=["site", "qeq", "zero"],
                       help="where charges come from when "
                            "electrostatics are on")
        p.add_argument("-p", "--param", action="append",
                       metavar="NAME=VALUE",
                       help="an option of an engine that declares "
                            "them -- DFTB+'s method, parameter "
                            "directory, dispersion, k-point spacing.  "
                            "`xtal engines` lists them.")
        p.add_argument("--workspace", metavar="DIR",
                       help="write the run into a workspace: a run "
                            "folder with the log, the trajectory and "
                            "the final structure, in the layout the "
                            "application reads")
        if name == "optimize":
            p.add_argument("-o", "--output",
                           help="write the relaxed structure here")
            p.add_argument("--method", default="lbfgs",
                           choices=optimize_methods())
            p.add_argument("--max-steps", type=int,
                           default=optimize_default_max_steps(),
                           dest="max_steps")
            p.add_argument("--tolerance", type=float,
                           default=optimize_default_tolerance(),
                           help="stop when the largest force per atom "
                                "is below this, in kcal/mol/A "
                                "(default: %(default)g)")
            p.add_argument("--relax-cell", action="store_true",
                           dest="relax_cell",
                           help="relax the lattice as well, under a "
                                "symmetry-adapted strain")
            p.add_argument("--stress-tolerance", type=float,
                           default=optimize_default_stress_tolerance(),
                           dest="stress_tolerance",
                           help="with --relax-cell, also stop only "
                                "when the residual stress is below "
                                "this, in GPa (default: %(default)g)")
            p.add_argument("--pressure", type=float, default=0.0,
                           help="external pressure in GPa, as a P V "
                                "term; needs --relax-cell to have any "
                                "effect")
            p.add_argument("-q", "--quiet", action="store_true",
                           help="do not print a line per step")
        p.set_defaults(func=cmd_energy if name == "energy"
                       else cmd_optimize)

    p = sub.add_parser("formats", help="list supported file formats")
    p.set_defaults(func=cmd_formats)

    p = sub.add_parser("modules",
                       help="list the modules and what they take")
    p.set_defaults(func=cmd_modules)

    p = sub.add_parser("engines",
                       help="list the energy engines and what they "
                            "take")
    p.set_defaults(func=cmd_engines)

    p = sub.add_parser("run", help="run one module action")
    p.add_argument("action", metavar="MODULE.ACTION",
                   help="which entry to run; `xtal modules` lists them")
    p.add_argument("file", nargs="?",
                   help="the structure to run against; omitted for a "
                        "module that builds one instead of reading it")
    p.add_argument("-p", "--param", action="append", metavar="NAME=VALUE",
                   help="a parameter for the module; repeatable")
    p.add_argument("--workspace", metavar="DIR",
                   help="write the run into a workspace, in the "
                        "layout the application reads")
    p.add_argument("-o", "--output",
                   help="write the structure it produced here, if it "
                        "produced one")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="do not echo the run's progress")
    p.set_defaults(func=cmd_run)
    return parser


def _engine_names() -> list[str]:
    from xtal.ff import ENGINES
    return ENGINES.names()


def optimize_default_tolerance() -> float:
    from xtal.ff.optimize import DEFAULT_FORCE_TOLERANCE
    return DEFAULT_FORCE_TOLERANCE


def optimize_default_stress_tolerance() -> float:
    from xtal.ff.optimize import DEFAULT_STRESS_TOLERANCE
    return DEFAULT_STRESS_TOLERANCE


def optimize_default_max_steps() -> int:
    from xtal.ff.optimize import DEFAULT_MAX_STEPS
    return DEFAULT_MAX_STEPS


def optimize_methods() -> list[str]:
    from xtal.ff.optimize import METHODS
    return list(METHODS)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    # First: it is an OSError, and after that handler it never ran.
    except FileNotFoundError as exc:
        name = exc.filename or getattr(args, "file", None) or exc
        print(f"error: no such file: {name}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
