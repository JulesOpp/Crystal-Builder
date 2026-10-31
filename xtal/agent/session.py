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
import os
import time
import weakref
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import numpy as np

from xtal.agent import changes
from xtal.agent.answers import VerbResult
from xtal.agent.diagnostics import Diagnostic
from xtal.agent.render import VIEWS
from xtal.commands import atoms as atom_commands
from xtal.commands import bonds as bond_commands
from xtal.commands import cell as cell_commands
from xtal.commands import symmetry as symmetry_commands
from xtal.commands.base import CommandStack
from xtal.core import bonding, groups, limits, p1
from xtal.core.structure import Structure
from xtal.view.settings import VIEW_CHOICES, ViewSettings, coerce_view

#: The file beside the structure that records what the agent did, one
#: JSON object per verb.  The GUI reads it to say that an entry was
#: built by an agent, and a person reads it to see how.
LOG_NAME = "agent-session.jsonl"

PROJECT_EXTENSION = ".xtalproj"

#: What :meth:`Session.render` looks along, spelled out for an MCP
#: client, which can only send what a parameter's schema says it takes.
View = Literal[VIEWS] | Sequence[float] | dict[str, Sequence[int]]

#: A path as either caller has one: text from an MCP client (the schema
#: says string), a ``Path`` from a script, which ``str`` alone told a
#: type checker it could not pass.
PathName = str | os.PathLike[str]

#: A bond's order by name, the window's Set Bond Type menu.
BondTypeName = Literal[tuple(bond_commands.BOND_TYPE_ORDERS)]


class Session:
    """One structure, edited through verbs, with undo and a log.

    Build one with :meth:`open`, :meth:`new` or :meth:`build` rather
    than the constructor.
    """

    # What _record reads before a session has run _init_bursts: the
    # window's session skips __init__, and logging must not depend on
    # it having opened a burst.
    _tagged = None
    # Nothing answered yet, so nothing to tell: not the same as having
    # answered over an empty history, after which every step is news.
    _mark = None

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
        self._view = dict(view or {})
        self._project_session = project_session or {}
        #: What opening said, for a session made by :meth:`open`.
        self.opened: VerbResult | None = None
        self._init_bursts()

    # ------------------------------------------------------------------
    #  GETTING ONE
    # ------------------------------------------------------------------

    @classmethod
    def open(cls, path: PathName,
             workspace: PathName | None = None) -> Session:
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
        notes = []
        if found is not None and workspace is not None and \
                found.root != Path(workspace).resolve():
            # The file stays where it belongs, so an agent that named
            # a workspace would otherwise look for its runs there.
            notes.append(Diagnostic(
                "WORKSPACE_IGNORED",
                f"{path} already belongs to the workspace at "
                f"{found.root}; {workspace} was not used"))
        project = path.with_suffix(PROJECT_EXTENSION)
        if not is_project(path) and project.is_file():
            # A session lives as long as its process.  An agent that
            # runs one script per step and reopens the CIF each time
            # repeats every step before it -- measured: six opens and
            # six prepares for one prepared structure.
            saved = time.localtime(project.stat().st_mtime)
            notes.append(Diagnostic(
                "PROJECT_EXISTS",
                f"{project.name} was saved here "
                f"{time.strftime('%Y-%m-%d %H:%M', saved)}",
                where=str(project)))
        session.opened = VerbResult("open", True, f"opened {path.name}",
                                    atoms_after=session.n_atoms,
                                    diagnostics=notes)
        session._record("open", {"path": str(path)}, session.opened)
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
    def build(cls, action: str, workspace: PathName,
              **params) -> Session:
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
        found = inspect(self.structure, symprec or DEFAULT_SYMPREC)
        found.diagnostics.extend(self._noticed())
        return found

    def render(self, path: PathName, view: View = "diagonal",
               size: tuple[int, int] = (800, 600),
               style: str | None = None, highlight: Sequence[int] = (),
               show_cell: bool | None = None) -> VerbResult:
        """A PNG of the current structure, drawn with the view
        ``set_view`` gave it -- see :func:`xtal.agent.render.render`.
        ``view`` is ``"diagonal"``, ``"a"``, ``"b"``, ``"c"``, a
        lattice direction ``[u, v, w]``, or a plane ``{"hkl": [h, k,
        l]}`` seen face on, along its normal.  ``style`` and
        ``show_cell`` draw this picture otherwise without changing the
        view; left out, they are the view's own.  ``highlight`` names
        P1 atoms to draw selected, which is how to find the atoms a
        diagnostic names."""
        from xtal.agent.render import render
        answer = render(self.structure, path, view=view, size=size,
                        style=style, highlight=highlight,
                        show_cell=show_cell, view_settings=self._view)
        answer.atoms_before = answer.atoms_after = self.n_atoms
        self._record("render", {"path": str(path), "view": view},
                     answer)
        return answer

    def view(self) -> VerbResult:
        """How the structure is drawn: every view setting (the Style
        panel's and the View menu's), and the choices of those that
        take one of a list.  Change them with ``set_view``."""
        n = self.n_atoms
        answer = VerbResult(
            "view", True, f"the view of {self._document_name()}",
            atoms_before=n, atoms_after=n,
            data={"view": self._current_view(),
                  "choices": {name: list(values)
                              for name, values in VIEW_CHOICES.items()}})
        self._record("view", {}, answer)
        return answer

    def set_view(self, settings: dict) -> VerbResult:
        """Change how the structure is drawn: ``settings`` is an object
        of view setting names to values, e.g. ``{"style": "polyhedra",
        "show_rings": true}``; ``view`` lists them and their choices.
        All or nothing -- one bad name or value and nothing changes.
        Not an undo step, and the structure is never touched.  The
        answer's ``was`` holds the old values: send it back to put the
        view as it was."""
        args = {"settings": settings}
        cleaned = coerce_view(settings)
        if isinstance(cleaned, str):
            return self._refused("set_view", args, cleaned,
                                 "VIEW_SETTING_REFUSED")
        n = self.n_atoms
        if not cleaned:
            answer = VerbResult("set_view", True,
                                "no view settings given",
                                atoms_before=n, atoms_after=n,
                                data={"changed": {}, "was": {}})
            self._record("set_view", args, answer)
            return answer
        before = self._current_view()
        too_big = self._range_too_big(before, cleaned)
        if too_big is not None:
            return self._answer_refused("set_view", args, too_big)
        self._apply_view(cleaned)
        after = self._current_view()
        # As view() spells them, so ``was`` can be sent straight back.
        answer = VerbResult(
            "set_view", True, "set " + ", ".join(cleaned),
            atoms_before=n, atoms_after=n,
            data={"changed": {k: after[k] for k in cleaned},
                  "was": {k: before[k] for k in cleaned}})
        self._record("set_view", args, answer)
        return answer

    def _range_too_big(self, view: dict, cleaned: dict):
        """The refusal for a display range the person's Display Range
        dialog would not draw unasked, or None.  Over the hard limit
        it is refused there too; over the soft one the person is
        asked, and an assistant cannot be -- unless it draws no more
        than the range already does, which the person has accepted.
        Answered ok, fifty cells a side of MOF-5 was 53 M atoms and
        froze the window."""
        axes = ("range_a", "range_b", "range_c")
        if not any(axis in cleaned for axis in axes):
            return None
        ranges = [cleaned.get(axis, view[axis]) for axis in axes]
        verdict = limits.check_drawn(self.n_atoms, ranges)
        if verdict.refused:
            return Diagnostic("SIZE_LIMIT", verdict.sentence)
        # A picture the person already accepted is theirs: narrowing
        # it, or leaving it as it is, is no new question to ask.
        drawn_now = limits.drawn_atoms(
            self.n_atoms, [view[axis] for axis in axes])
        if verdict.warned and verdict.estimate > drawn_now:
            soft, _hard = limits.bounds("drawn")
            return Diagnostic(
                "VIEW_SETTING_REFUSED",
                f"the picture would draw {limits.count(verdict.estimate)}"
                f" atoms, over the {limits.count(soft)} the person is "
                "asked about; ask the person to widen the display range "
                "themselves")
        return None

    def _current_view(self) -> dict:
        """Every view setting as ``ViewSettings.to_dict`` writes them:
        the defaults, overlaid with what was opened or set."""
        return ViewSettings.from_dict(self._view).to_dict()

    def _apply_view(self, cleaned: dict) -> None:
        """Settings :func:`coerce_view` passed, merged into the view a
        saved project carries.  Only what was set is kept, so a project
        does not pin every default of the version that wrote it."""
        settings = ViewSettings.from_dict(self._view)
        for name, value in cleaned.items():
            setattr(settings, name, value)
        written = settings.to_dict()
        self._view.update({k: written[k] for k in cleaned})

    def select(self, rule: str, atoms: Sequence[int] = (),
               **args) -> VerbResult:
        """P1 atoms, bonds or net edges by one rule -- the rules of the
        window's Select dialog (:func:`xtal.core.selection.pick`).

        Changes nothing: the answer is ``data["atoms"]``,
        ``data["bonds"]`` and ``data["net_edges"]``, to hand to a verb
        that takes atoms.  ``atoms`` are what ``shell``, ``neighbours``
        and ``radius`` grow from.  An unknown rule raises, as any
        wrong argument does.
        """
        from xtal.core import selection as sel

        for atom in atoms:
            self._check_atom(atom)
        extra = {}
        if rule == "bonds" and args.get("order") is not None:
            extra["orders"] = bonding.orders(self.structure)
        if rule == "net":
            extra["topology"] = bonding.topology_graph(self.structure)
        if rule == "group":
            extra["groups"] = groups.matches(self.structure)
        chosen = sel.pick(rule, self.cell, bonding.graph(self.structure),
                          self.structure.lattice, atoms, **extra, **args)
        data = {"atoms": sorted(chosen.atoms),
                "bonds": [list(key) for key in sorted(chosen.bonds)],
                "net_edges": [list(key)
                              for key in sorted(chosen.topology)]}
        count = len(chosen.atoms) + len(chosen.bonds) + len(
            chosen.topology)
        message = (f"{len(chosen.atoms)} atoms, {len(chosen.bonds)} "
                   f"bonds, {len(chosen.topology)} net edges"
                   if count else "nothing matched")
        answer = VerbResult("select", True, message,
                            atoms_before=self.n_atoms,
                            atoms_after=self.n_atoms, data=data)
        self._record("select", {"rule": rule, "atoms": list(atoms),
                                **args}, answer)
        return answer

    # ------------------------------------------------------------------
    #  ATOMS
    # ------------------------------------------------------------------

    def add_atom(self, element: str, frac: Sequence[float] | None = None,
                 cart: Sequence[float] | None = None,
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

    def delete_sites(self, sites: int | Sequence[int]) -> VerbResult:
        """Remove whole sites -- every atom of each orbit."""
        sites = self._check_sites(sites)
        return self._push("delete_sites",
                          atom_commands.DeleteSites(sites),
                          f"deleted {len(sites)} site(s)",
                          {"sites": sites})

    def set_element(self, sites: int | Sequence[int],
                    element: str) -> VerbResult:
        sites = self._check_sites(sites)
        return self._push("set_element",
                          atom_commands.SetElement(sites, element),
                          f"{len(sites)} site(s) are now {element}",
                          {"sites": sites, "element": element})

    def move_sites(self, sites: int | Sequence[int],
                   frac_delta: Sequence[float] | None = None,
                   cart_delta: Sequence[float] | None = None,
                   to: Sequence[float] | Sequence[Sequence[float]]
                   | None = None) -> VerbResult:
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

    def set_cell(self, a: float, b: float, c: float, alpha: float,
                 beta: float, gamma: float,
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

    def slab(self, hkl: Sequence[int], layers: int = 1, vacuum: float = 15.0,
             shift: float = 0.0) -> VerbResult:
        """A slab along (hkl), ``layers`` spacings thick, with
        ``vacuum`` Angstrom above.  The bonds are carried, never
        perceived; the ones the surfaces cut are counted."""
        args = {"hkl": [int(v) for v in hkl], "layers": layers,
                "vacuum": vacuum, "shift": shift}
        command = cell_commands.MakeSlab(hkl, layers, vacuum, shift)
        try:
            command.preview(self.structure)
        except ValueError as exc:
            return self._refused("slab", args, str(exc))
        return self._operate("slab", command, args)

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
                      order: float | BondTypeName) -> VerbResult:
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

    def substitute(self, group: str, atoms: Sequence[int] | None = None,
                   per_ring: bool = False, fraction: float = 1.0,
                   seed: int = 0) -> VerbResult:
        """Replace hydrogens with ``group`` -- a library name
        (``"Amino"``), a formula (``"NH2"``) or a SMILES string with
        one connection point -- as one undo step.

        ``atoms`` are P1 hydrogens (or F, Cl, Br, I: any atom on one
        bond), each standing for its whole orbit; or ``per_ring`` puts
        one on every aromatic ring.  ``fraction`` below one takes that
        share of ``atoms``, drawn by ``seed``.  What a
        reduction to P1 or a group with no room owes the caller comes
        back as diagnostics.  Nothing is perceived.
        """
        from xtal.build.substitute import SubstituteError
        from xtal.commands.atoms import SubstituteHydrogens

        args = {"group": group, "atoms": atoms, "per_ring": per_ring,
                "fraction": fraction, "seed": seed}
        chosen = [] if atoms is None else [int(a) for a in atoms]
        for atom in chosen:
            self._check_atom(atom)
        if not per_ring and not chosen:
            return self._refused("substitute", args,
                                 "name the hydrogens, or per_ring=True",
                                 "NOTHING_TO_DO")
        try:
            command = SubstituteHydrogens(group, chosen,
                                          per_ring=per_ring,
                                          fraction=fraction, seed=seed)
        except SubstituteError as exc:
            return self._refused("substitute", args, str(exc))
        answer = self._operate("substitute", command, args)
        if not answer.ok:
            return answer
        for warning in command.report.warnings:
            code = ("SYMMETRY_NOTE" if warning.startswith("reduced")
                    else "CLOSE_CONTACT" if " A from an atom " in warning
                    else "NOTHING_TO_DO")
            answer.diagnostics.append(Diagnostic(code, warning))
        self._rewrite_last_log(answer)
        return answer

    def fill_pores(self, guest: str, count: int = 20,
                   beside: Sequence[int] | None = None,
                   near: tuple[float, float] | None = None,
                   overlap_scale: float | None = None,
                   seed: int = 0) -> VerbResult:
        """Copies of a molecule where there is room -- or, ``beside``,
        one by each of those P1 atoms: the counter-ions of a charged
        framework.

        ``guest`` is an element symbol, for an ion or an atom, or the
        path of a structure whose first discrete molecule is taken.
        One undo step, a symmetric host reduced to P1 inside it, and
        nothing bonded -- see :func:`xtal.build.fill.place`.  An atom
        with no room beside it is named in ``data["missed"]``.
        """
        from xtal.build import fill
        from xtal.commands.clipboard import InsertMolecules

        args = {"guest": guest, "count": count, "beside": beside,
                "near": near, "overlap_scale": overlap_scale,
                "seed": seed}
        try:
            molecule = _guest(guest)
        except ValueError as exc:
            return self._refused("fill_pores", args, str(exc))
        anchors = None
        if beside is not None:
            anchors = [int(a) for a in beside]
            for atom in anchors:
                self._check_atom(atom)
            if not anchors:
                return self._refused("fill_pores", args,
                                     "beside names no atoms",
                                     "NOTHING_TO_DO")
        placement = fill.place(
            self.structure, molecule, count, anchors=anchors,
            near=fill.NEAR if near is None else tuple(near),
            overlap_scale=(fill.DEFAULT_OVERLAP_SCALE
                           if overlap_scale is None else overlap_scale),
            seed=seed)
        if not placement.placed:
            return self._refused(
                "fill_pores", args,
                f"no room was found for {molecule.formula}")
        return self._push(
            "fill_pores",
            InsertMolecules(molecule, placement.positions),
            placement.message(), args,
            notes=[Diagnostic("BONDS_NOT_RECALCULATED",
                              "what was placed is bonded to nothing "
                              "but itself")],
            data={"placed": placement.placed,
                  "missed": list(placement.missed)})

    def place_molecule(self, guest: str, at: Sequence[float],
                       turn: bool = False,
                       keep_group: bool = False,
                       overlap_scale: float | None = None,
                       seed: int = 0) -> VerbResult:
        """One copy of a molecule with its centroid at fractional
        ``at`` -- the place somebody already knows: a template in its
        cage, a guest a diffraction study located.

        ``guest`` as for :meth:`fill_pores`.  As drawn unless ``turn``;
        ``keep_group`` lets the host's group copy it, otherwise the
        host is reduced to P1 in the same undo step.  A crowded point
        is placed anyway, with ``CLOSE_CONTACT`` naming the contact,
        and copies the group lays over each other are
        ``SYMMETRY_NOTE`` -- see :func:`xtal.build.fill.at_point`.
        """
        from xtal.build import fill

        args = {"guest": guest, "at": list(at), "turn": turn,
                "keep_group": keep_group,
                "overlap_scale": overlap_scale, "seed": seed}
        try:
            molecule = _guest(guest)
        except ValueError as exc:
            return self._refused("place_molecule", args, str(exc))
        if len(args["at"]) != 3:
            return self._refused("place_molecule", args,
                                 "at is three fractional coordinates")
        placement = fill.at_point(
            self.structure, molecule, args["at"], turn=turn,
            keep_group=keep_group,
            overlap_scale=(fill.DEFAULT_OVERLAP_SCALE
                           if overlap_scale is None else overlap_scale),
            seed=seed)
        notes = []
        if placement.special:
            notes.append(Diagnostic("SYMMETRY_NOTE",
                                    placement.warnings()[0]))
        elif not keep_group and not self.structure.space_group.is_p1:
            notes.append(Diagnostic(
                "SYMMETRY_NOTE", "the host was reduced to P1 so that "
                "this is the one molecule added"))
        if placement.crowded:
            notes.append(Diagnostic("CLOSE_CONTACT",
                                    placement.contact.sentence()))
        notes.append(Diagnostic("BONDS_NOT_RECALCULATED",
                                "what was placed is bonded to nothing "
                                "but itself"))
        contact = placement.contact
        return self._push(
            "place_molecule", fill.insert_command(placement),
            placement.message(), args, notes=notes,
            data={"atoms_made": placement.atoms_made,
                  "contact": None if contact is None else {
                      "atom": contact.atom, "other": contact.other,
                      "of": contact.of,
                      "distance": round(contact.distance, 3),
                      "ratio": round(contact.ratio, 3)}})

    # ------------------------------------------------------------------
    #  WHOLE-STRUCTURE OPERATIONS
    # ------------------------------------------------------------------

    def prepare(self, steps: Sequence[str] | None = None) -> VerbResult:
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
        self._hear()
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
        args = {"engine": engine, "relax_cell": relax_cell,
                "max_steps": max_steps, "tolerance": tolerance,
                "method": method, **options}
        relaxed = self._relax(args, options)
        if isinstance(relaxed, VerbResult):
            return relaxed
        return self._apply_relaxation(relaxed, args)

    def _relax(self, args, options):
        """The calculation half of :meth:`optimize`: the engine built
        over this structure, its run folder opened, the optimiser run.
        Nothing is pushed.  A :class:`_Relaxation`, or the refusal.

        Apart from :meth:`_apply_relaxation` because the window runs
        this half over a copy, off its GUI thread, and the other half
        on the tab.
        """
        from xtal.ff import optimize as ff_optimize
        from xtal.ff import record as ff_record

        self._hear()
        engine = args["engine"]
        calculator, refused = self._calculator(engine, options)
        if refused is not None:
            return self._answer_refused("optimize", args, refused)
        kwargs = {"method": args["method"],
                  "relax_cell": args["relax_cell"]}
        if args["max_steps"] is not None:
            kwargs["max_steps"] = int(args["max_steps"])
        if args["tolerance"] is not None:
            kwargs["force_tolerance"] = float(args["tolerance"])
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
        start = self.structure.copy()
        try:
            result = ff_optimize.run(calculator, self.structure,
                                     callback=trace, **kwargs)
        except Exception as exc:        # noqa: BLE001 -- said, not lost
            ff_record.close_run(recorder, error=str(exc))
            return self._calculation_failed("optimize", args, exc)
        return _Relaxation(calculator, recorder, result, before, start)

    def _apply_relaxation(self, relaxed, args) -> VerbResult:
        """The other half: the relaxed geometry pushed as one step, the
        run closed, and the answer."""
        from xtal.ff import record as ff_record

        result, recorder = relaxed.result, relaxed.recorder
        command = relaxed.command()
        moved = command.displacement(self.structure)
        notes = _engine_notes(relaxed.calculator)
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
        # Said as start and end rather than the core's summary, whose
        # first number is the *change*: "-2774 kcal/mol to 3076" read
        # as two energies to an agent seeing it for the first time.
        said = (f"{'converged' if result.converged else 'NOT converged'}"
                f" after {result.steps} steps: energy "
                f"{result.initial_energy:.4f} -> {result.energy:.4f} "
                f"kcal/mol, |F|max {result.max_force:.4f} kcal/mol/A")
        if result.matrix is not None:
            said += f", volume {result.volume_change * 100:+.2f}%"
        if moved < 1e-9:
            ff_record.close_run(recorder, result, final=self.structure)
            answer = VerbResult(
                "optimize", True, f"{said}; nothing moved",
                atoms_before=self.n_atoms, atoms_after=self.n_atoms,
                data=data, diagnostics=notes)
            self._record("optimize", args, answer)
            return answer
        answer = self._push("optimize", command,
                            f"{said}; the furthest atom moved "
                            f"{moved:.3f} A", args, notes=notes,
                            data=data)
        ff_record.close_run(recorder, result, final=self.structure)
        if recorder is not None:
            answer.data["run"] = str(recorder.folder.path)
        changed = _bonding_would_change(relaxed.start, self.structure)
        if changed is not None:
            answer.diagnostics.append(changed)
        if recorder is not None or changed is not None:
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
        return self._run_module(action, action, params)[0]

    def thermochemistry(self, engine: str = "uff",
                        temperature: float = 298.15,
                        system: str = "auto", quasi_rrho: bool = False,
                        method: str = "auto", relax_first: bool = True,
                        ir: bool = False, **options) -> VerbResult:
        """H, S and G from the vibrations -- ``forcefield.thermo``, the
        run Force Field ▸ Thermochemistry... makes.

        A copy is relaxed (``relax_first``) and its Hessian taken; the
        session's structure is not changed and nothing is pushed.
        ``**options`` are the run's own (``tolerance``, ``supercell``,
        ``freeze`` ...; ``help_for("forcefield.thermo")``) and the
        engine's (``help_for("mace")``), told apart by name.  ``data``
        has the numbers at ``temperature`` in kcal/mol (``g``, ``h``,
        ``ts``, ``zpe``, ``e_elec``) and cal/(mol K) (``s``, ``cv``),
        per cell or per molecule, beside the report's tables.
        ``IMAGINARY_MODES`` says when the structure was not at a
        minimum, and ``SIZE_LIMIT`` refuses what would not fit.
        """
        from xtal.ff import ENGINES
        from xtal.modules import MODULES

        args = {"engine": engine, "temperature": temperature,
                "system": system, "quasi_rrho": quasi_rrho,
                "method": method, "relax_first": relax_first, "ir": ir,
                **options}
        try:
            chosen = ENGINES.get(engine)
        except (KeyError, ValueError) as exc:
            return self._answer_refused(
                "thermochemistry", args,
                Diagnostic("ENGINE_UNAVAILABLE", str(exc)))
        _module, action = MODULES.find("forcefield.thermo")
        own = {p.name for p in action.params}
        theirs = {o.name for o in chosen.options}
        unknown = sorted(set(options) - own - theirs)
        if unknown:
            raise TypeError(f"thermochemistry() got an unexpected "
                            f"keyword argument {unknown[0]!r}: neither "
                            f"the run's nor {engine}'s")
        settings = chosen.coerce(_as_strings(
            {k: v for k, v in options.items() if k in theirs}))
        available = chosen.availability(**settings)
        if not available:
            return self._answer_refused(
                "thermochemistry", args,
                Diagnostic("ENGINE_UNAVAILABLE", available.reason))
        params = {k: v for k, v in args.items() if k in own}
        answer, result = self._run_module(
            "thermochemistry", "forcefield.thermo", params,
            extra={"engine_options": settings}, args=args)
        found = None if result is None else result.answer
        if found is not None:
            answer.data.update({
                "temperature": float(found.temperature),
                "system": found.kind,
                **{name: float(getattr(found, name)) for name in (
                    "e_elec", "zpe", "h", "ts", "g", "s", "cv")},
                "z": int(found.z),
                "imaginary_modes": int(found.vibrations.n_imaginary)})
        return answer

    def _run_module(self, verb, action, params, extra=None,
                    args=None):
        """:meth:`run`'s body, under the verb that asked: ``extra`` is
        added after coercing, for what no form row holds (an engine's
        options), and ``args`` is what the log records.  The answer
        and the run's :class:`JobResult`, ``None`` if it never ran."""
        from xtal import plugins
        from xtal.modules import MODULES, Job
        from xtal.modules import record as module_record

        self._hear()
        args = params if args is None else args
        plugins.load()
        module, entry_action = MODULES.find(action)
        refused = _unavailable(module, entry_action)
        if refused is not None:
            return self._answer_refused(verb, args, refused), None
        if not entry_action.needs_structure:
            raise ValueError(f"{action} builds a structure rather than "
                             f"measuring one: Session.build({action!r}, "
                             f"workspace, ...)")
        coerced = entry_action.coerce(_as_strings(params))
        coerced.update(extra or {})
        # Said before the run and kept whatever it does: a grid of
        # hours that fails at its first point was still that size.
        size = _scan_size(action, coerced)
        sized = [size] if size is not None else []
        folder = module_record.open_run(self.entry, module, entry_action,
                                        coerced, self.structure)
        job = Job(structure=self.structure, params=coerced,
                  folder=folder, label=action)
        try:
            result = entry_action.run(job)
        except Exception as exc:        # noqa: BLE001 -- said, not lost
            module_record.close_run(folder, error=str(exc))
            return self._answer_refused(
                verb, args, Diagnostic("MODULE_FAILED", str(exc)),
                notes=sized), None
        module_record.close_run(folder, result)
        notes = sized + _result_warnings(result)
        if not result.ok and not any(n.code == "SIZE_LIMIT"
                                     for n in notes):
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
        answer = VerbResult(verb, bool(result.ok), result.summary(),
                            atoms_before=self.n_atoms,
                            atoms_after=self.n_atoms, data=data,
                            diagnostics=notes)
        self._record(verb, args, answer)
        return answer, result

    # ------------------------------------------------------------------
    #  HISTORY AND FILES
    # ------------------------------------------------------------------

    def undo(self) -> VerbResult:
        before = self.n_atoms
        command, told = self._own_move(lambda: self.stack.undo(self))
        if command is not None:
            self._kept_after_own_move()
        answer = VerbResult(
            "undo", command is not None,
            f"undid {command.label}" if command else "nothing to undo",
            atoms_before=before, atoms_after=self.n_atoms,
            diagnostics=told)
        self._record("undo", {}, answer)
        return answer

    def redo(self) -> VerbResult:
        before = self.n_atoms
        command, told = self._own_move(lambda: self.stack.redo(self))
        if command is not None:
            self._kept_after_own_move()
        answer = VerbResult(
            "redo", command is not None,
            f"redid {command.label}" if command else "nothing to redo",
            atoms_before=before, atoms_after=self.n_atoms,
            diagnostics=told)
        self._record("redo", {}, answer)
        return answer

    def save(self, path: PathName | None = None) -> Path:
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

    def export(self, path: PathName) -> Path:
        """Write a copy for another program: no markers, no net, no
        suppressions -- :func:`xtal.io.export.for_export`."""
        from xtal.io import FORMATS
        from xtal.io.export import for_export

        path = Path(path)
        settled = FORMATS.by_extension(path).settles_bonds
        FORMATS.write(self.structure if settled
                      else for_export(self.structure), path)
        self._record("export", {"path": str(path)},
                     VerbResult("export", True, f"exported {path.name}",
                                atoms_after=self.n_atoms))
        return path

    @property
    def log_path(self) -> Path | None:
        return self.entry.path / LOG_NAME if self.entry else None

    # ------------------------------------------------------------------
    #  BURSTS: which of the history's steps were this session's
    # ------------------------------------------------------------------

    def _init_bursts(self) -> None:
        """No burst open yet.  A separate method because the window's
        session does not run ``__init__``."""
        self._burst = 0
        self._step = 0
        self._burst_label = ""
        self._next_label = ""
        self._closed = True
        self._last_call: float | None = None
        self._began: float | None = None  # a long call, when it began
        self._last_pushed = None          # weakref to our last step
        self._ours_empty = False          # an empty history is ours
        self._tagged = None               # the Origin this verb pushed
        self._mark: list | None = None    # (weakref, origin) we saw

    def close_burst(self) -> None:
        """End the burst: the next edit is a new request.  What a host
        calls when the assistant opens or switches documents.  A
        checkpoint's name goes too: it was for the request on the
        document being left."""
        self._closed = True
        self._next_label = ""

    def _tag(self, verb: str, command) -> None:
        """Say ``command`` is this verb's, in the right burst.

        A new burst opens when the last one was closed (``checkpoint``,
        ``close_burst``), when the assistant had been quiet for
        :data:`~xtal.agent.changes.BURST_GAP` when this call began
        (:meth:`_hear`), or when its last step is
        no longer the newest applied one -- the person edited, undid or
        reverted since.  A person's undo then redo of that step puts it
        back on top, so the burst goes on, and so does the assistant's
        own undo or redo (:meth:`_kept_after_own_move`).  Sealing the
        stack either side keeps the step its own: merged into the
        person's, it would be one undo step with two authors.
        """
        now = changes.clock()
        began = self._began if self._began is not None else now
        last = self._last_pushed() if self._last_pushed else None
        done = self.stack.done()
        ours = done[-1] is last if done else self._ours_empty
        if (self._closed or self._last_call is None
                or began - self._last_call > changes.BURST_GAP
                or not ours):
            self._burst = changes.next_burst(self.stack)
            self._step = 0
            self._closed = False
            self._burst_label, self._next_label = self._next_label, ""
        self._step += 1
        command.origin = changes.Origin(self._burst, self._step, verb,
                                        self._burst_label, now)
        self._last_pushed = weakref.ref(command)
        self._ours_empty = False
        self._tagged = command.origin
        self.stack.break_merge()

    def _kept_after_own_move(self) -> None:
        """The assistant's own undo or redo moved the stack: whatever
        is now the newest applied step -- or the empty history -- is
        where its burst goes on from.  Taking back its own misstep is
        still the same request.

        Unless a step of the burst is still applied under one that is
        not the burst's: a redo that re-applied the person's edit puts
        it on top of the burst, and going on would put their step
        inside the assistant's, for a Revert to take unsaid.  The
        burst ends there.

        Its next step is numbered after the burst's last *applied*
        one: the step it undid goes when that is pushed, and a burst
        whose numbers skip one reads as one whose start the history
        let go (:func:`xtal.agent.changes.bursts`)."""
        done = self.stack.done()
        steps = [o.step for c in done
                 if (o := changes.origin_of(c)) is not None
                 and o.burst == self._burst]
        top = changes.origin_of(done[-1]) if done else None
        if steps and (top is None or top.burst != self._burst):
            self._last_pushed = None
            self._ours_empty = False
            return
        self._last_pushed = weakref.ref(done[-1]) if done else None
        self._ours_empty = not done
        self._step = max(steps, default=0)

    #: What :meth:`_tag` moves, put back when the push it tagged for
    #: fails -- or a failed step spends the checkpoint's name, or ends
    #: the burst the next step belongs to.
    _BURST_STATE = ("_burst", "_step", "_burst_label", "_next_label",
                    "_closed", "_last_pushed", "_ours_empty", "_tagged")

    def _burst_state(self) -> dict:
        return {name: getattr(self, name) for name in self._BURST_STATE}

    def checkpoint(self, label: str) -> VerbResult:
        """End the current burst of changes and name the next one.

        Call it when starting on a person's request, with what they
        asked for ("Prepared MIL-88B"): the window lists the assistant's
        changes under that name, and Revert takes them back as one.
        Not an undo step, and answered while the window is busy.
        """
        name = " ".join(str(label).split())[:changes.LABEL_LENGTH]
        self._closed = True
        self._next_label = name
        answer = VerbResult(
            "checkpoint", True,
            f"the next changes are '{name}'" if name
            else "the next changes start a new burst",
            atoms_before=self.n_atoms, atoms_after=self.n_atoms)
        self._record("checkpoint", {"label": label}, answer)
        return answer

    def _hear(self) -> None:
        """A call that may run longer than the gap has begun.  The gap
        is the assistant's silence before a call, so it is measured to
        here and not to when the call's step lands: a two-minute
        relaxation is the assistant working, not the person pausing."""
        self._began = changes.clock()

    def _heard(self) -> None:
        """A call has been answered: the assistant's silence starts
        now."""
        self._last_call = changes.clock()
        self._began = None

    def _noticed(self) -> list[Diagnostic]:
        """What changed in the history behind this session's back since
        its last answer, said once, and the mark moved to now.

        Undone: the steps applied at the last answer that are no longer
        applied, counted from the top, since Undo and Revert take from
        the top.  Said as a revert only when some were the assistant's,
        and counted by those: the person undoing their own edit is the
        person editing.  A trimmed history usually loses only the bottom, but
        a trim past the step that was on top at the last answer reads
        as undone too.  Edited: the person's steps applied above the
        last one we saw.  Where both happened -- the person undid ours
        and then edited -- the revert is what is said: it is the one
        that makes the assistant's own account wrong.

        The mark keeps each step's origin beside it: a push clears the
        redo list, so a step undone before this verb pushed is gone by
        the time its answer is recorded, and its label with it.
        """
        done = self.stack.done()
        here = {id(c) for c in done}
        mark = self._mark
        self._remark()
        if mark is None:
            return []
        seen = [(ref(), origin) for ref, origin in mark]
        undone = 0
        for command, _origin in reversed(seen):
            if command is not None and id(command) in here:
                break
            undone += 1
        name = self._document_name()
        if undone:
            mine = [o for _c, o in list(reversed(seen))[:undone] if o]
            if not mine:
                return [Diagnostic(
                    "PERSON_EDITED",
                    f"the person undid {undone} step(s) on {name} since "
                    f"your last call; inspect before deciding anything")]
            latest = mine[0]
            return [Diagnostic(
                "AGENT_CHANGES_REVERTED",
                f"{len(mine)} step(s) applied to {name} at your last "
                f"call were undone or reverted -- the latest, "
                f"'{latest.label or latest.verb}'; inspect before going "
                f"on")]
        top = next((c for c, _o in reversed(seen) if c is not None),
                   None)
        start = next((i + 1 for i, c in enumerate(done) if c is top), 0)
        added = sum(1 for c in done[start:]
                    if changes.origin_of(c) is None)
        if added:
            return [Diagnostic(
                "PERSON_EDITED",
                f"the person made {added} edit(s) to {name} since your "
                f"last call; inspect before deciding anything")]
        return []

    def _remark(self) -> None:
        """Take the history as it is now as seen, saying nothing."""
        self._mark = [(weakref.ref(c), changes.origin_of(c))
                      for c in self.stack.done()]

    def _own_move(self, move):
        """``move()`` -- the assistant's own undo or redo -- with what
        the person did before it said, and the move itself not: told
        its own undo reverted its steps, an assistant inspects for
        nothing or puts them back.  Returns what ``move`` returned and
        the notices, for the answer; ``_record`` then finds the mark
        current and adds none.  A move that raises (the window's, on a
        held tab) puts the mark back: the notices it took went nowhere,
        and the next answer must still give them."""
        previous = self._mark
        told = self._noticed()
        try:
            moved = move()
        except BaseException:
            self._mark = previous
            raise
        self._remark()
        return moved, told

    def _document_name(self) -> str:
        return self.path.name if self.path else "the structure"

    # ------------------------------------------------------------------
    #  PLUMBING
    # ------------------------------------------------------------------

    def _push(self, verb, command, message, args, notes=(),
              data=None) -> VerbResult:
        before = self.n_atoms
        bursting = self._burst_state()
        self._tag(verb, command)
        try:
            self.stack.push(command, self)
        except BaseException:
            # Never reached the history: no row may name its burst,
            # and the burst goes on as if it had not been tried.
            for name, value in bursting.items():
                setattr(self, name, value)
            raise
        self.stack.break_merge()
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
            code = (getattr(report, "code", "")
                    or ("NOTHING_TO_DO" if "nothing to" in report.message
                        else "OPERATION_REFUSED"))
            return self._refused(verb, args, report.message, code)
        notes = [Diagnostic("SYMMETRY_NOTE", w)
                 for w in getattr(report, "warnings", [])
                 if verb != "prepare"]
        message = getattr(report, "message", "") or command.label
        return self._push(verb, command, message, args, notes=notes)

    def _named(self, answer):
        """``answer`` as given.  The window's sessions say which of its
        documents it is about; a script's session is its one
        structure, and its answers are left as they were."""
        return answer

    def _refused(self, verb, args, message,
                 code="OPERATION_REFUSED") -> VerbResult:
        return self._answer_refused(verb, args,
                                    Diagnostic(code, message))

    def _answer_refused(self, verb, args, diagnostic,
                        notes=()) -> VerbResult:
        answer = VerbResult(verb, False, diagnostic.message,
                            atoms_before=self.n_atoms,
                            atoms_after=self.n_atoms,
                            diagnostics=[diagnostic, *notes])
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
        answer.diagnostics.extend(self._noticed())
        row = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "verb": verb, "args": _jsonable(args),
               "ok": answer.ok, "message": answer.message,
               "atoms": answer.atoms_after,
               "diagnostics": [f"{d.level}:{d.code}"
                               for d in answer.diagnostics]}
        tagged, self._tagged = self._tagged, None
        if tagged is not None:
            row["burst"] = tagged.burst
        self._heard()
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


class _Relaxation:
    """What :meth:`Session._relax` hands :meth:`Session._apply_relaxation`:
    the optimiser's result, the run it is filed in, and the geometry it
    started from -- which is what ``before`` and the bonding check
    compare against, whichever structure ends up taking it."""

    def __init__(self, calculator, recorder, result, before, start):
        self.calculator = calculator
        self.recorder = recorder
        self.result = result
        self.before = before
        self.start = start

    def command(self):
        from xtal.commands import ff as ff_commands
        return ff_commands.ApplyOptimizedGeometry(
            self.result.frac, before=self.before,
            matrix=getattr(self.result, "matrix", None))


#: Verbs that record without changing anything worth counting.
_NOT_STEPS = frozenset({"open", "save", "render", "export", "energy",
                        "view", "set_view"})


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


def _bonding_would_change(start, result) -> Diagnostic | None:
    """``BONDING_WOULD_CHANGE`` when the relaxation moved atoms into or
    out of bonding distance: perception of the result against
    perception of the start, both afresh.

    Afresh, on copies with the stored graph dropped, as a
    recalculation would: perception otherwise answers from the stored
    graph, which does not follow a geometry, and passing the rules
    does not get past its memo.  Not against the drawn graph either: a
    graph left stale by an earlier move would be blamed on the
    relaxation.  The start is read in the result's wrap, so an atom
    that crossed a cell face is not a bond lost and found.

    An orbit that merged on a special position, or split off one,
    leaves two cells whose atom indices name different atoms: there
    is no bond-for-bond comparison to make, and ``rebase`` would raise
    after the geometry was already applied.  Nothing is said then.
    """
    if p1.expand(start).n_atoms != p1.expand(result).n_atoms:
        return None
    then, then_tau = _perceived_afresh(start)
    now, now_tau = _perceived_afresh(result)
    before = {b.key() for b in bonding.rebase(then, then_tau, now_tau)}
    after = {b.key() for b in now}
    into, out = len(after - before), len(before - after)
    if not into and not out:
        return None
    return Diagnostic(
        "BONDING_WOULD_CHANGE",
        f"the relaxation moved {into} bond(s) into and {out} out of "
        f"bonding distance; bonds were left as they were")


def _perceived_afresh(structure):
    """The bonds perception finds now, and the wrap they are read in;
    ``structure`` itself and its stored graph are not touched."""
    fresh = structure.copy()
    fresh.clear_perceived()
    return bonding.perceive(fresh), p1.expand(fresh).tau


def _scan_size(action: str, params: dict) -> Diagnostic | None:
    """``SCAN_SIZE`` for a scan of more than one point, from the
    coerced parameters: each axis that is walked multiplies the count
    by its steps, and walking both ways doubles it.

    An axis whose coordinate is empty is not walked (``axes_from``
    skips it), and its steps still arrive filled in by ``coerce``:
    counted, a one-axis scan of 5 read as 45.
    """
    if not action.startswith("scan."):
        return None
    points, any_axis = 1, False
    for name, value in params.items():
        axis = name.removesuffix("_steps")
        if axis == name or not axis.startswith("axis"):
            continue
        if axis in params and not str(params[axis] or "").strip():
            continue
        points *= int(value)
        any_axis = True
    if not any_axis:
        return None
    if any("direction" in name and value == "both"
           for name, value in params.items()):
        points *= 2
    if points <= 1:
        return None
    return Diagnostic("SCAN_SIZE", f"{points} points, each a relaxation, "
                                   f"written as it finishes")


def _engine_notes(calculator) -> list[Diagnostic]:
    return [Diagnostic("ENGINE_NOTE", str(w))
            for w in getattr(calculator, "warnings", []) or []]


def _guest(spec: str):
    """What :meth:`Session.fill_pores` places: one atom of an element,
    or the first molecule in a file."""
    from xtal.build import fill
    from xtal.commands.clipboard import Fragment
    from xtal.core import elements as el
    from xtal.io import FORMATS

    text = str(spec).strip()
    try:
        symbol = el.parse_symbol(text)
    except (ValueError, KeyError):
        symbol = None
    # Exactly a symbol: the parser reads a label (``Na1``) or a stray
    # suffix as an element too, and a mistyped path is not sodium.
    if symbol is not None and symbol == text.capitalize():
        return Fragment(elements=(symbol,), cart=np.zeros((1, 3)),
                        occupancies=(1.0,), labels=(f"{symbol}1",))
    path = Path(text).expanduser()
    if not path.is_file():
        raise ValueError(f"{text!r} is neither an element nor a file")
    molecules = fill.guest_molecules(FORMATS.read(path))
    if not molecules:
        raise ValueError(f"{path.name} has no discrete molecule in it")
    return molecules[0]


def _result_warnings(result) -> list[Diagnostic]:
    """A run's warnings as diagnostics: a ``(code, sentence)`` pair
    keeps its code, and a bare sentence is an engine's note."""
    out = []
    for warning in getattr(result, "warnings", ()) or ():
        if isinstance(warning, tuple):
            code, said = warning
            out.append(Diagnostic(str(code), str(said)))
        else:
            out.append(Diagnostic("ENGINE_NOTE", str(warning)))
    return out


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
