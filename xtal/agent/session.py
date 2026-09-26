"""
xtal.agent.session
==================
A structure, its undo stack and its workspace entry, driven by verbs.

This is what an agent -- or a script, or a notebook -- holds instead
of a window.  It is to :mod:`xtal.commands` what
:class:`xtalapp.document.Document` is: the one way the structure
changes.  **Every verb is one command on the stack**, the same command
the window pushes for the same gesture, so an agent's edit is exactly
a person's, ``undo()`` takes it back, and the product decisions the
commands carry come with them:

- bonds change only in :meth:`Session.recalculate_bonds`; an added
  atom is bonded to what it was told to be bonded to and nothing else;
- a force field never changes the atoms or the bonds, and markers are
  held back at the door by the engine registry, not here;
- :meth:`Session.prepare` never runs the chemistry-changing step
  unless it is named, and says so in warning tone either way.

A refusal is an answer, not an exception.  A verb the core refuses --
a bad space group, a placement that collides, an engine that cannot
type an atom -- comes back as a :class:`VerbResult` with ``ok=False``
and a coded diagnostic, and nothing is pushed.  A *programming* error
(a wrong argument type) still raises, because that is a bug in the
caller and an agent should see the traceback.

Site verbs take **site indices** (the asymmetric unit, as
:func:`~xtal.agent.inspect.inspect` lists them); bond verbs take
**atom indices** of the P1 cell, because a bond joins two drawn atoms
and not two orbits.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from xtal.agent.answers import VerbResult
from xtal.agent.diagnostics import Diagnostic
from xtal.commands import atoms as atom_commands
from xtal.commands import bonds as bond_commands
from xtal.commands import cell as cell_commands
from xtal.commands import symmetry as symmetry_commands
from xtal.commands.base import CommandStack
from xtal.core import bonding, p1
from xtal.core.structure import Structure

#: The file beside the structure that records what the agent did, one
#: JSON object per verb.  The GUI reads it to say that an entry was
#: built by an agent, and a person reads it to see how.
LOG_NAME = "agent-session.jsonl"

PROJECT_EXTENSION = ".xtalproj"


class Session:
    """One structure, edited through verbs, with undo and a log.

    Build one with :meth:`open`, :meth:`new` or :meth:`build` rather
    than the constructor.
    """

    def __init__(self, structure: Structure, path: Path | None = None,
                 entry=None, view: dict | None = None,
                 project_session: dict | None = None):
        self.structure = structure
        self.path = Path(path) if path is not None else None
        self.entry = entry
        self.stack = CommandStack()
        self.log: list[dict] = []
        # A project's view and selection are the person's, and an
        # agent that opened and saved it must hand them back as found.
        self._view = view or {}
        self._project_session = project_session or {}

    # ------------------------------------------------------------------
    #  GETTING ONE
    # ------------------------------------------------------------------

    @classmethod
    def open(cls, path, workspace=None) -> Session:
        """Open a structure file or a project.

        With ``workspace`` (a directory, made if it is not one yet) the
        file is **copied in** and the session follows the copy, as the
        window does: the original belongs to whoever it came from.  A
        file already inside a workspace is used where it is.
        """
        from xtal.io import FORMATS
        from xtal.io.project import is_project, read_project
        from xtal.workspace import Workspace

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"no such file: {path}")
        # Read before copying, as the window does: what the reader
        # records as the source is the file the user named, not the
        # workspace's copy of it.
        view = project_session = None
        if is_project(path):
            structure, view, project_session = read_project(path)
        else:
            structure = FORMATS.read(path)
        entry = None
        found = Workspace.find(path)
        if found is not None:
            entry = found.entry_for(path)
        elif workspace is not None:
            entry = Workspace.create(workspace).add_structure(path)
            structure.meta.setdefault("source", str(path))
            path = entry.path / path.name
        session = cls(structure, path, entry, view, project_session)
        session._record("open", {"path": str(path)},
                        VerbResult("open", True, f"opened {path.name}",
                                   atoms_after=session.n_atoms))
        return session

    @classmethod
    def new(cls, a: float, b: float, c: float, alpha: float = 90.0,
            beta: float = 90.0, gamma: float = 90.0,
            space_group: str = "P1", name: str = "untitled",
            workspace=None) -> Session:
        """An empty cell to build into -- File > New, from a script."""
        from xtal.core.lattice import Lattice
        from xtal.core.spacegroup import SpaceGroup
        from xtal.workspace import Workspace

        structure = Structure(
            Lattice.from_parameters(a, b, c, alpha, beta, gamma),
            space_group=SpaceGroup.from_any(space_group))
        entry = path = None
        if workspace is not None:
            entry = Workspace.create(workspace).new_document(name)
            path = entry.project_path
        session = cls(structure, path, entry)
        session._record("new", {"cell": [a, b, c, alpha, beta, gamma],
                                "space_group": space_group},
                        VerbResult("new", True, f"new {space_group} cell"))
        return session

    @classmethod
    def build(cls, action: str, workspace, **params) -> Session:
        """Run a builder (``mof.build``, ``build.smiles`` ...) and open
        what it built, filed in ``workspace`` as the window files it.

        Raises :class:`BuildFailed` carrying the :class:`VerbResult`
        when nothing was built, because there is no session to hand
        back.
        """
        from xtal import plugins
        from xtal.modules import MODULES, Job
        from xtal.modules import record as module_record
        from xtal.workspace import Workspace

        plugins.load()
        module, entry_action = MODULES.find(action)
        refused = _unavailable(module, entry_action)
        if refused is not None:
            raise BuildFailed(VerbResult(action, False, refused.message,
                                         diagnostics=[refused]))
        if entry_action.needs_structure:
            raise ValueError(f"{action} measures a structure rather "
                             f"than building one; open the structure "
                             f"and call session.run({action!r})")
        ws = Workspace.create(workspace)
        coerced = entry_action.coerce(_as_strings(params))
        folder = module_record.open_run(ws.add_document(module.label),
                                        module, entry_action, coerced)
        job = Job(structure=None, params=coerced, folder=folder,
                  label=action)
        result = entry_action.run(job)
        module_record.close_run(folder, result)
        if not result.ok or result.structure is None:
            message = result.message or "nothing was built"
            raise BuildFailed(VerbResult(
                action, False, message,
                diagnostics=[Diagnostic("MODULE_FAILED", message)]))
        filed = ws.adopt_build(
            result.structure, run=folder.path if folder else None,
            artifacts=getattr(result, "artifacts", ()))
        session = cls.open(filed.path)
        answer = VerbResult(
            action, True, result.summary(),
            atoms_after=session.n_atoms,
            data={"path": str(filed.path),
                  "run": str(filed.run) if filed.run else "",
                  **_report_data(result)},
            diagnostics=_result_warnings(result))
        session._record(action, params, answer)
        session.built = answer
        return session

    # ------------------------------------------------------------------
    #  STATE
    # ------------------------------------------------------------------

    @property
    def cell(self):
        """The P1 cell: every atom, with the site it came from."""
        return p1.expand(self.structure)

    @property
    def n_atoms(self) -> int:
        return self.cell.n_atoms

    @property
    def modified(self) -> bool:
        return not self.stack.is_clean

    def history(self) -> list[str]:
        """The undo stack's labels, oldest first."""
        return [c.label for c in self.stack._done]

    def inspect(self, symprec: float | None = None):
        """:func:`xtal.agent.inspect.inspect` of the current structure."""
        from xtal.agent.inspect import DEFAULT_SYMPREC, inspect
        return inspect(self.structure, symprec or DEFAULT_SYMPREC)

    def render(self, path, view="diagonal", size=(800, 600),
               style: str = "ball_stick", highlight=(),
               show_cell: bool = True) -> VerbResult:
        """A PNG of the current structure -- see
        :func:`xtal.agent.render.render`.  ``highlight`` names P1 atoms
        to draw selected, which is how to find the atoms a diagnostic
        names."""
        from xtal.agent.render import render
        answer = render(self.structure, path, view=view, size=size,
                        style=style, highlight=highlight,
                        show_cell=show_cell)
        self._record("render", {"path": str(path), "view": view},
                     answer)
        return answer

    # ------------------------------------------------------------------
    #  ATOMS
    # ------------------------------------------------------------------

    def add_atom(self, element: str, frac=None, cart=None,
                 bonded_to: int | None = None, occupancy: float = 1.0,
                 label: str = "") -> VerbResult:
        """Place one atom, at fractional ``frac`` or cartesian ``cart``.

        Bonded to nothing, unless ``bonded_to`` names a P1 atom -- then
        to that atom, explicitly, in the same undo step, as a click on
        an atom in Add-atom mode does.  Perception is never run over
        it: :meth:`recalculate_bonds` is how it joins by distance.
        """
        frac = self._position(frac, cart)
        site = atom_commands.new_site(element, frac, occupancy, label)
        if bonded_to is None:
            command = atom_commands.AddSites([site], perceive=False)
            said = f"added {element}"
        else:
            self._check_atom(bonded_to)
            command = atom_commands.AddBondedSite(site, int(bonded_to))
            anchor = self.cell.labels[bonded_to] or \
                self.cell.elements[bonded_to]
            said = f"added {element}, bonded to {anchor}"
        return self._push("add_atom", command, said,
                          {"element": element, "frac": list(frac),
                           "bonded_to": bonded_to},
                          notes=[Diagnostic(
                              "BONDS_NOT_RECALCULATED",
                              "the new atom has no bonds but the one it "
                              "was given" if bonded_to is not None
                              else "the new atom has no bonds")],
                          data={"site": self.structure.n_sites})

    def delete_sites(self, sites) -> VerbResult:
        """Remove whole sites -- every atom of each orbit."""
        sites = self._check_sites(sites)
        return self._push("delete_sites",
                          atom_commands.DeleteSites(sites),
                          f"deleted {len(sites)} site(s)",
                          {"sites": sites})

    def set_element(self, sites, element: str) -> VerbResult:
        sites = self._check_sites(sites)
        return self._push("set_element",
                          atom_commands.SetElement(sites, element),
                          f"{len(sites)} site(s) are now {element}",
                          {"sites": sites, "element": element})

    def move_sites(self, sites, frac_delta=None, cart_delta=None,
                   to=None) -> VerbResult:
        """Move sites by a fractional or cartesian delta, or ``to``
        explicit fractional coordinates (one row per site).

        Bonds are not re-perceived: a bond stays drawn as the atoms
        move, which is what the window does for a drag.
        """
        sites = self._check_sites(sites)
        given = [x is not None for x in (frac_delta, cart_delta, to)]
        if sum(given) != 1:
            raise ValueError("give exactly one of frac_delta, "
                             "cart_delta or to")
        if to is not None:
            rows = np.asarray(to, dtype=float).reshape(len(sites), 3)
            command = atom_commands.MoveSites(
                {k: row for k, row in zip(sites, rows, strict=True)})
        elif frac_delta is not None:
            command = atom_commands.MoveSites.by_delta(
                self.structure, sites, np.asarray(frac_delta, float))
        else:
            command = atom_commands.MoveSites.by_cartesian_delta(
                self.structure, sites, np.asarray(cart_delta, float))
        return self._push("move_sites", command,
                          f"moved {len(sites)} site(s)",
                          {"sites": sites},
                          notes=[Diagnostic(
                              "BONDS_NOT_RECALCULATED",
                              "the moved sites keep the bonds they had")])

    # ------------------------------------------------------------------
    #  CELL AND SYMMETRY
    # ------------------------------------------------------------------

    def set_cell(self, a, b, c, alpha, beta, gamma,
                 keep: str = "fractional") -> VerbResult:
        from xtal.core.lattice import Lattice
        lattice = Lattice.from_parameters(a, b, c, alpha, beta, gamma)
        return self._push("set_cell",
                          cell_commands.SetLattice(lattice, keep),
                          f"cell set to {a:g} {b:g} {c:g} "
                          f"{alpha:g} {beta:g} {gamma:g}",
                          {"cell": [a, b, c, alpha, beta, gamma],
                           "keep": keep})

    def supercell(self, na: int, nb: int, nc: int) -> VerbResult:
        return self._operate("supercell",
                             cell_commands.Supercell(na, nb, nc),
                             {"n": [na, nb, nc]})

    def reduce_to_p1(self) -> VerbResult:
        return self._operate("reduce_to_p1",
                             symmetry_commands.ReduceToP1(), {})

    def find_symmetry(self, symprec: float = 1e-2) -> VerbResult:
        """Detect the group and keep it: the cell becomes its
        asymmetric unit.  ``symprec`` defaults to the inspection's."""
        return self._operate("find_symmetry",
                             symmetry_commands.FindSymmetry(symprec),
                             {"symprec": symprec})

    def standardize(self, symprec: float = 1e-2,
                    to_primitive: bool = False) -> VerbResult:
        return self._operate(
            "standardize",
            symmetry_commands.Standardize(symprec, to_primitive),
            {"symprec": symprec, "to_primitive": to_primitive})

    def set_space_group(self, group: str,
                        mode: str = "reinterpret") -> VerbResult:
        return self._operate(
            "set_space_group",
            symmetry_commands.SetSpaceGroup(group, mode),
            {"group": group, "mode": mode})

    def merge_duplicates(self, tol: float | None = None) -> VerbResult:
        command = (symmetry_commands.MergeDuplicates(tol)
                   if tol is not None
                   else symmetry_commands.MergeDuplicates())
        return self._operate("merge_duplicates", command, {"tol": tol})

    # ------------------------------------------------------------------
    #  BONDS
    # ------------------------------------------------------------------

    def recalculate_bonds(self) -> VerbResult:
        """Perceive the bonds again, over the geometry as it is now.

        The only verb that bonds by distance.  Bonds drawn or removed
        by hand survive it, and are counted when there are any.
        """
        before = {b.key() for b in bonding.perceive(self.structure)}
        answer = self._push("recalculate_bonds",
                            bond_commands.RecomputeBonds(),
                            "bonds recalculated", {})
        after = {b.key() for b in bonding.perceive(self.structure)}
        added, removed = len(after - before), len(before - after)
        answer.message = (
            f"bonds recalculated: {added} added, {removed} removed -- "
            f"{len(after)} bonds" if added or removed else
            f"bonds recalculated, unchanged: {len(after)} bonds")
        answer.data.update(added=added, removed=removed,
                           bonds=len(after))
        drawn = sum(1 for b in self.structure.bonds
                    if b.kind in ("explicit", "suppressed"))
        if drawn:
            answer.diagnostics.append(Diagnostic(
                "BOND_OVERRIDES_KEPT",
                f"{drawn} bond(s) drawn or removed by hand were kept"))
        return answer

    def add_bond(self, atom_a: int, atom_b: int) -> VerbResult:
        """Draw a bond between two P1 atoms, at their nearest images."""
        image_a, image_b = self._images(atom_a, atom_b)
        command = bond_commands.AddBond.between_atoms(
            self.structure, self.cell, atom_a, atom_b, image_a, image_b)
        return self._push("add_bond", command,
                          f"bonded atoms {atom_a} and {atom_b}",
                          {"atoms": [atom_a, atom_b]})

    def remove_bond(self, atom_a: int, atom_b: int) -> VerbResult:
        """Suppress the bond between two P1 atoms -- and, as in the
        window, the whole orbit of it the group generates."""
        image_a, image_b = self._images(atom_a, atom_b)
        command = bond_commands.SuppressBond.between_atoms(
            self.structure, self.cell, atom_a, atom_b, image_a, image_b)
        return self._push("remove_bond", command,
                          f"removed the bond {atom_a}-{atom_b}",
                          {"atoms": [atom_a, atom_b]})

    def set_bond_type(self, atom_a: int, atom_b: int,
                      order) -> VerbResult:
        """State a bond's order: 1, 1.5 (aromatic), 2, 3, or a name
        from ``bond_commands.BOND_TYPE_ORDERS``.  A stated order wins
        over anything perception would infer."""
        if isinstance(order, str):
            order = bond_commands.BOND_TYPE_ORDERS[order]
        image_a, image_b = self._images(atom_a, atom_b)
        command = bond_commands.SetBondType.between_atoms(
            self.structure, self.cell, atom_a, atom_b, order,
            image_a, image_b)
        return self._push("set_bond_type", command,
                          f"bond {atom_a}-{atom_b} set to order {order}",
                          {"atoms": [atom_a, atom_b], "order": order})

    def add_hydrogens(self, xray: bool = False) -> VerbResult:
        """Complete main-group valences with hydrogens -- the one edit
        that bonds what it adds, because that is the operation."""
        from xtal.commands.ff import AddHydrogens

        command = AddHydrogens(xray=xray)
        plan = command.preview(self.structure)
        if not plan:
            return self._refused("add_hydrogens", {"xray": xray},
                                 plan.message(), "NOTHING_TO_DO")
        return self._push("add_hydrogens", command, plan.message(),
                          {"xray": xray})

    # ------------------------------------------------------------------
    #  WHOLE-STRUCTURE OPERATIONS
    # ------------------------------------------------------------------

    def prepare(self, steps=None) -> VerbResult:
        """Make a deposited structure ready for a calculation.

        ``steps`` from :data:`xtal.core.prepare.STEPS`; the default is
        every step but ``cap``, which changes the chemistry and runs
        only when named.  Each step's sentence and every caution come
        back as diagnostics.
        """
        from xtal.commands.prepare import Prepare
        from xtal.core import prepare as core

        chosen = tuple(core.DEFAULT_STEPS if steps is None else steps)
        unknown = sorted(set(chosen) - set(core.STEPS))
        if unknown:
            return self._refused(
                "prepare", {"steps": list(chosen)},
                f"no preparation step called {', '.join(unknown)}; the "
                f"steps are {', '.join(core.STEPS)}")
        command = Prepare(chosen)
        answer = self._operate("prepare", command,
                               {"steps": list(chosen)})
        report = command.report or command.preview(self.structure)[1]
        ran = [s for s in core.STEPS if s in chosen]
        for step, said in zip(ran, getattr(report, "warnings", []),
                              strict=False):
            answer.diagnostics.append(
                Diagnostic("PREPARE_STEP", said, where=step))
        for caution in getattr(report, "cautions", []):
            code = ("CHEMISTRY_CHANGED" if "changes the chemistry of"
                    in caution else "CELL_NOT_NEUTRAL")
            answer.diagnostics.append(Diagnostic(code, caution))
        self._rewrite_last_log(answer)
        return answer

    def interpenetrate(self, n: int = 2) -> VerbResult:
        """``n`` copies of the framework, placed where the detector
        finds the most room.  Refused by name when nothing fits."""
        from xtal.analysis import interpenetrate
        from xtal.commands.interpenetrate import Interpenetrate

        try:
            placement = interpenetrate.best(self.structure, n)
        except interpenetrate.InterpenetrationError as exc:
            return self._refused("interpenetrate", {"n": n}, str(exc))
        return self._operate("interpenetrate",
                             Interpenetrate(placement), {"n": n})

    # ------------------------------------------------------------------
    #  CALCULATIONS
    # ------------------------------------------------------------------

    def energy(self, engine: str = "uff", **options) -> VerbResult:
        """A single point.  Changes nothing, so it is not on the stack."""
        args = {"engine": engine, **options}
        calculator, refused = self._calculator(engine, options)
        if refused is not None:
            return self._answer_refused("energy", args, refused)
        try:
            result = calculator.compute(self.cell.cart,
                                        self.structure.lattice.matrix)
        except Exception as exc:        # noqa: BLE001 -- said, not lost
            return self._calculation_failed("energy", args, exc)
        answer = VerbResult(
            "energy", True,
            f"{result.energy:.4f} kcal/mol, |F|max "
            f"{result.max_force:.4f} kcal/mol/A",
            atoms_before=self.n_atoms, atoms_after=self.n_atoms,
            data={"energy": float(result.energy),
                  "max_force": float(result.max_force),
                  "rms_force": float(result.rms_force),
                  "terms": {k: float(v)
                            for k, v in result.terms.items()},
                  "engine": calculator.summary()},
            diagnostics=_engine_notes(calculator))
        self._record("energy", args, answer)
        return answer

    def optimize(self, engine: str = "uff", relax_cell: bool = False,
                 max_steps: int | None = None,
                 tolerance: float | None = None,
                 method: str = "lbfgs", **options) -> VerbResult:
        """Relax the geometry, as one undo step, and file the run.

        The atoms and the bonds are the same afterwards: only
        positions (and the cell, with ``relax_cell``) move.  An
        unconverged run is applied -- the window applies it too -- and
        says ``NOT_CONVERGED``, because its energy is not a minimum.
        """
        from xtal.commands import ff as ff_commands
        from xtal.ff import optimize as ff_optimize
        from xtal.ff import record as ff_record

        args = {"engine": engine, "relax_cell": relax_cell,
                "max_steps": max_steps, "tolerance": tolerance,
                "method": method, **options}
        calculator, refused = self._calculator(engine, options)
        if refused is not None:
            return self._answer_refused("optimize", args, refused)
        kwargs = {"method": method, "relax_cell": relax_cell}
        if max_steps is not None:
            kwargs["max_steps"] = int(max_steps)
        if tolerance is not None:
            kwargs["force_tolerance"] = float(tolerance)
        recorder = ff_record.open_run(self.entry, engine, "optimise",
                                      self.structure, calculator,
                                      options=options)
        if recorder is not None:
            recorder.begin_steps()

        def trace(step):
            if recorder is not None:
                recorder.step(step)
            return True

        before = [s.frac.copy() for s in self.structure.sites]
        try:
            result = ff_optimize.run(calculator, self.structure,
                                     callback=trace, **kwargs)
        except Exception as exc:        # noqa: BLE001 -- said, not lost
            ff_record.close_run(recorder, error=str(exc))
            return self._calculation_failed("optimize", args, exc)
        command = ff_commands.ApplyOptimizedGeometry(
            result.frac, before=before,
            matrix=getattr(result, "matrix", None))
        moved = command.displacement(self.structure)
        notes = _engine_notes(calculator)
        if not result.converged:
            notes.append(Diagnostic(
                "NOT_CONVERGED",
                f"stopped after {result.steps} steps with |F|max "
                f"{result.max_force:.4f} kcal/mol/A"))
        data = {"converged": bool(result.converged),
                "steps": int(result.steps),
                "initial_energy": float(result.initial_energy),
                "energy": float(result.energy),
                "max_force": float(result.max_force),
                "max_displacement": float(moved)}
        if moved < 1e-9:
            ff_record.close_run(recorder, result, final=self.structure)
            answer = VerbResult(
                "optimize", True, f"{result.summary()}; nothing moved",
                atoms_before=self.n_atoms, atoms_after=self.n_atoms,
                data=data, diagnostics=notes)
            self._record("optimize", args, answer)
            return answer
        answer = self._push("optimize", command,
                            f"{result.summary()}; the furthest atom "
                            f"moved {moved:.3f} A", args, notes=notes,
                            data=data)
        ff_record.close_run(recorder, result, final=self.structure)
        if recorder is not None:
            answer.data["run"] = str(recorder.folder.path)
            self._rewrite_last_log(answer)
        return answer

    def run(self, action: str, **params) -> VerbResult:
        """Run a module action against this structure (``zeopp.pores``,
        ``pxrd.pattern`` ...) and hand back its report.

        A module that *returns* a structure does not change this
        session: the structure is in the run folder, and
        ``RESULT_NOT_APPLIED`` says where.  ``xtal modules`` or
        :func:`~xtal.agent.capabilities.capabilities` list the actions
        and their parameters.
        """
        from xtal import plugins
        from xtal.modules import MODULES, Job
        from xtal.modules import record as module_record

        plugins.load()
        module, entry_action = MODULES.find(action)
        refused = _unavailable(module, entry_action)
        if refused is not None:
            return self._answer_refused(action, params, refused)
        if not entry_action.needs_structure:
            raise ValueError(f"{action} builds a structure rather than "
                             f"measuring one: Session.build({action!r}, "
                             f"workspace, ...)")
        coerced = entry_action.coerce(_as_strings(params))
        folder = module_record.open_run(self.entry, module, entry_action,
                                        coerced, self.structure)
        job = Job(structure=self.structure, params=coerced,
                  folder=folder, label=action)
        try:
            result = entry_action.run(job)
        except Exception as exc:        # noqa: BLE001 -- said, not lost
            module_record.close_run(folder, error=str(exc))
            return self._answer_refused(
                action, params, Diagnostic("MODULE_FAILED", str(exc)))
        module_record.close_run(folder, result)
        notes = _result_warnings(result)
        if not result.ok:
            notes.insert(0, Diagnostic("MODULE_FAILED",
                                       result.message or "failed"))
        data = _report_data(result)
        if folder is not None:
            data["run"] = str(folder.path)
        if result.structure is not None and result.structure is not \
                self.structure:
            notes.append(Diagnostic(
                "RESULT_NOT_APPLIED",
                "the run returned a structure; it is in the run folder",
                where=data.get("run", "")))
        answer = VerbResult(action, bool(result.ok), result.summary(),
                            atoms_before=self.n_atoms,
                            atoms_after=self.n_atoms, data=data,
                            diagnostics=notes)
        self._record(action, params, answer)
        return answer

    # ------------------------------------------------------------------
    #  HISTORY AND FILES
    # ------------------------------------------------------------------

    def undo(self) -> VerbResult:
        before = self.n_atoms
        command = self.stack.undo(self)
        answer = VerbResult(
            "undo", command is not None,
            f"undid {command.label}" if command else "nothing to undo",
            atoms_before=before, atoms_after=self.n_atoms)
        self._record("undo", {}, answer)
        return answer

    def redo(self) -> VerbResult:
        before = self.n_atoms
        command = self.stack.redo(self)
        answer = VerbResult(
            "redo", command is not None,
            f"redid {command.label}" if command else "nothing to redo",
            atoms_before=before, atoms_after=self.n_atoms)
        self._record("redo", {}, answer)
        return answer

    def save(self, path=None) -> Path:
        """Write the session as a project -- what Save does in the
        window.  A structure opened as a CIF becomes the ``.xtalproj``
        of the same name beside it; the CIF is left as it is."""
        from xtal.io.project import write_project

        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("this session has no file yet; give "
                             "save() a path")
        target = target.with_suffix(PROJECT_EXTENSION)
        write_project(self.structure, target, view=self._view,
                      session=self._project_session)
        self.path = target
        self.stack.mark_clean()
        self._record("save", {"path": str(target)},
                     VerbResult("save", True, f"saved {target.name}",
                                atoms_after=self.n_atoms))
        return target

    def export(self, path) -> Path:
        """Write a copy for another program: no markers, no net, no
        suppressions -- :func:`xtal.io.export.for_export`."""
        from xtal.io import FORMATS
        from xtal.io.export import for_export

        path = Path(path)
        FORMATS.write(for_export(self.structure), path)
        self._record("export", {"path": str(path)},
                     VerbResult("export", True, f"exported {path.name}",
                                atoms_after=self.n_atoms))
        return path

    @property
    def log_path(self) -> Path | None:
        return self.entry.path / LOG_NAME if self.entry else None

    # ------------------------------------------------------------------
    #  PLUMBING
    # ------------------------------------------------------------------

    def _push(self, verb, command, message, args, notes=(),
              data=None) -> VerbResult:
        before = self.n_atoms
        self.stack.push(command, self)
        answer = VerbResult(verb, True, message, undo_label=command.label,
                            atoms_before=before, atoms_after=self.n_atoms,
                            data=dict(data or {}),
                            diagnostics=list(notes))
        self._record(verb, args, answer)
        return answer

    def _operate(self, verb, command, args) -> VerbResult:
        """A :class:`StructureOperation`, previewed first and pushed
        only if its report says it did something -- as
        ``Document.operate`` does, so a refusal leaves no no-op on the
        stack for undo to lie about."""
        _new, report = command.preview(self.structure)
        if report is not None and not report.ok:
            code = ("NOTHING_TO_DO" if "nothing to" in report.message
                    else "OPERATION_REFUSED")
            return self._refused(verb, args, report.message, code)
        notes = [Diagnostic("SYMMETRY_NOTE", w)
                 for w in getattr(report, "warnings", [])
                 if verb != "prepare"]
        message = getattr(report, "message", "") or command.label
        return self._push(verb, command, message, args, notes=notes)

    def _refused(self, verb, args, message,
                 code="OPERATION_REFUSED") -> VerbResult:
        return self._answer_refused(verb, args,
                                    Diagnostic(code, message))

    def _answer_refused(self, verb, args, diagnostic) -> VerbResult:
        answer = VerbResult(verb, False, diagnostic.message,
                            atoms_before=self.n_atoms,
                            atoms_after=self.n_atoms,
                            diagnostics=[diagnostic])
        self._record(verb, args, answer)
        return answer

    def _calculation_failed(self, verb, args, exc) -> VerbResult:
        from xtal.ff.api import CalculatorError
        if not isinstance(exc, (CalculatorError, ValueError,
                                RuntimeError)):
            raise exc
        return self._answer_refused(
            verb, args, Diagnostic("CALCULATION_REFUSED", str(exc)))

    def _calculator(self, engine, options):
        """``(calculator, None)`` or ``(None, diagnostic)``."""
        from xtal.ff import ENGINES
        from xtal.ff.api import CalculatorError

        try:
            chosen = ENGINES.get(engine)
        except (KeyError, ValueError) as exc:
            return None, Diagnostic("ENGINE_UNAVAILABLE", str(exc))
        if chosen.options:
            options = chosen.coerce(_as_strings(options))
        available = chosen.availability(**options)
        if not available:
            return None, Diagnostic("ENGINE_UNAVAILABLE",
                                    available.reason)
        try:
            # The engine and not ``engine.build``: the call is where
            # markers are held back (xtal.ff.markers).
            return chosen(self.structure, **options), None
        except (CalculatorError, ValueError) as exc:
            return None, Diagnostic("CALCULATION_REFUSED", str(exc))

    def _position(self, frac, cart) -> list[float]:
        if (frac is None) == (cart is None):
            raise ValueError("give exactly one of frac or cart")
        if cart is not None:
            frac = self.structure.lattice.to_frac(
                np.asarray(cart, dtype=float))
        return [float(x) for x in np.asarray(frac, dtype=float)]

    def _check_sites(self, sites) -> list[int]:
        sites = sorted({int(k) for k in np.atleast_1d(sites)})
        bad = [k for k in sites
               if not 0 <= k < self.structure.n_sites]
        if bad:
            raise IndexError(f"no site {bad[0]}; there are "
                             f"{self.structure.n_sites} sites (inspect() "
                             f"lists them)")
        return sites

    def _check_atom(self, atom) -> None:
        if not 0 <= int(atom) < self.n_atoms:
            raise IndexError(f"no atom {atom}; the cell has "
                             f"{self.n_atoms} atoms")

    def _images(self, atom_a, atom_b):
        """The translations that put two P1 atoms nearest each other:
        ``a`` where it is, ``b`` in the image closest to it."""
        self._check_atom(atom_a)
        self._check_atom(atom_b)
        cell = self.cell
        delta = cell.frac[atom_b] - cell.frac[atom_a]
        return (0, 0, 0), tuple(int(x) for x in -np.round(delta))

    def _record(self, verb, args, answer: VerbResult) -> None:
        row = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "verb": verb, "args": _jsonable(args),
               "ok": answer.ok, "message": answer.message,
               "atoms": answer.atoms_after,
               "diagnostics": [f"{d.level}:{d.code}"
                               for d in answer.diagnostics]}
        self.log.append(row)
        if self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(row) + "\n")

    def _rewrite_last_log(self, answer: VerbResult) -> None:
        """A verb that adds to its answer after pushing: the log's row
        says what the answer finally said."""
        if not self.log:
            return
        row = self.log[-1]
        row.update(message=answer.message,
                   diagnostics=[f"{d.level}:{d.code}"
                                for d in answer.diagnostics])
        if self.log_path is not None and self.log_path.exists():
            lines = self.log_path.read_text(
                encoding="utf-8").splitlines()
            if lines:
                lines[-1] = json.dumps(row)
                self.log_path.write_text("\n".join(lines) + "\n",
                                         encoding="utf-8")

    def __repr__(self) -> str:
        name = self.path.name if self.path else "unsaved"
        return (f"<Session {name}: {self.structure.n_sites} sites, "
                f"{self.n_atoms} atoms, "
                f"{self.structure.space_group.short_name}>")


#: Verbs that record without changing anything worth counting.
_NOT_STEPS = frozenset({"open", "save", "render", "export", "energy"})


def summarise_log(path) -> tuple[int, int] | None:
    """``(steps, warnings)`` from an entry's log, or ``None`` if there is
    none -- what the window says when it opens something an agent made.

    A step is a verb that ran and changed something or measured it;
    opening, saving and drawing are not steps.  A line that is not JSON
    is skipped rather than refused: the log is advisory.
    """
    path = Path(path)
    if not path.is_file():
        return None
    steps = warnings = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("verb") in _NOT_STEPS or not row.get("ok"):
            continue
        steps += 1
        warnings += sum(1 for d in row.get("diagnostics", ())
                        if not str(d).startswith("info:"))
    return steps, warnings


class BuildFailed(RuntimeError):
    """:meth:`Session.build` built nothing; ``.result`` says why."""

    def __init__(self, result: VerbResult):
        super().__init__(result.message)
        self.result = result


def _unavailable(module, action) -> Diagnostic | None:
    available = module.availability()
    if available:
        available = action.availability()
    if not available:
        return Diagnostic("MODULE_UNAVAILABLE", available.reason)
    if action.run is None:
        return Diagnostic("MODULE_UNAVAILABLE",
                          f"{module.name}.{action.name} is performed by "
                          f"the application window and has nothing to "
                          f"run from a script")
    return None


def _as_strings(params: dict) -> dict:
    """What ``coerce`` takes: the form's own spelling of each value, so
    a Python ``True`` or ``3`` is read the way ``-p x=3`` would be."""
    out = {}
    for key, value in params.items():
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            out[key] = " ".join(str(v) for v in value)
        else:
            out[key] = str(value)
    return out


def _engine_notes(calculator) -> list[Diagnostic]:
    return [Diagnostic("ENGINE_NOTE", str(w))
            for w in getattr(calculator, "warnings", []) or []]


def _result_warnings(result) -> list[Diagnostic]:
    return [Diagnostic("ENGINE_NOTE", str(w))
            for w in getattr(result, "warnings", []) or []]


def _report_data(result) -> dict:
    """A module's report: its tables as rows an agent can read, and
    the whole report as the text the CLI prints."""
    report = getattr(result, "report", None)
    if not report:
        return {}
    tables = []
    for table in report.tables:
        rows = []
        for row in table.rows:
            if row.cells:
                rows.append(dict(zip(table.columns, row.cells,
                                     strict=False)))
            else:
                rows.append({k: v for k, v in (
                    ("label", row.label), ("value", row.value),
                    ("unit", row.unit), ("symbol", row.symbol),
                    ("note", row.note)) if v})
        tables.append({"title": table.title, "rows": rows,
                       **({"note": table.note} if table.note else {})})
    return {"tables": tables, "report_text": report.as_text()}


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
