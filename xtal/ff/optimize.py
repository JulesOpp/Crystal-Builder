"""
xtal.ff.optimize
================
Geometry optimisation: FIRE and L-BFGS, over degrees of freedom that
respect the space group.

**The variables are the asymmetric unit, not the cell.**  A calculator
works on the P1 cell, because that is what has an energy; an optimiser
that moved those atoms independently would break the symmetry of the
structure on the first step, and there would then be no way to write
the answer back -- a structure in P4_2/mnm has nowhere to put six
independently displaced oxygens.  So the variables here are the sites
of the asymmetric unit, the P1 cell is regenerated from them at every
step, and the gradient is carried back through the symmetry operations
that generated it.

That one decision gives three things at once.  Symmetry is preserved
exactly, and for free.  An atom on a special position stays on it,
because the step is projected onto the subspace its site symmetry
leaves invariant -- the oxygen of rutile relaxes along the [110]
direction it is free in and nowhere else.  And a structure already in
P1 falls out as the ordinary case, with every atom free, no projection,
and no special path through the code.

**The cell can be a variable too.**  Six strain components sit
alongside the site coordinates in the same flat vector, so FIRE and
L-BFGS relax a lattice constant without either of them knowing that is
what they are doing.  The strain is *symmetry-adapted* by the same
argument that keeps an atom on its special position -- averaged over
the point group, which leaves a cubic cell with one free strain and a
hexagonal one with two -- and an external pressure enters as a ``P V``
term.  See :class:`SymmetryDOF`.

**Optimisers are generators.**  Each yields a :class:`Step` per
iteration and then waits.  The GUI's worker thread uses that to draw
the geometry as it moves, to pause, and to cancel without leaving a
half-applied structure behind; the CLI uses it to print a line per
step; the tests use it to assert on the trajectory rather than only on
the answer.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace

import numpy as np

from xtal.core import p1
from xtal.core.lattice import PARAMETER_NAMES
from xtal.ff.api import CalculatorError, CalculatorStopped

# Convergence: the largest force on any atom, in kcal/mol/Angstrom.
# Loose enough to reach on a framework, tight enough that the geometry
# has stopped moving visibly.
DEFAULT_FORCE_TOLERANCE = 0.05
# Five hundred, not two hundred.  Two hundred stopped every
# variable-cell relaxation of UiO-66 and ZIF-8 short with the atoms
# still moving, and "run it again" then restarted the optimiser's
# history from nothing -- which is why a cell took three runs.
DEFAULT_MAX_STEPS = 500
# The residual stress a relaxed cell may keep, in GPa, over the strains
# the space group allows.  Its own number and not the force tolerance
# rescaled: the per-atom strain gradient that was the only criterion
# let MOF-5 call itself converged under about 0.2 GPa, which is a
# percent of its volume.
DEFAULT_STRESS_TOLERANCE = 0.05
# No single step moves an atom further than this, whatever the
# optimiser asks for.  A bad first guess -- two atoms almost on top of
# each other, which happens whenever someone builds by hand -- gives a
# force of tens of thousands, and without a cap the first step throws
# the atom out of the crystal.
DEFAULT_MAX_STEP = 0.2

# 1 GPa, in the units everything here works in.  A pressure times a
# volume has to come out as an energy, and this is the one place a
# factor can quietly go missing: energies are kcal/mol, volumes are
# Angstrom^3, and 1 GPa is 10^9 J/m^3 = 10^-21 J/A^3, which is
# 10^-21 * N_A / 4184 kcal/mol per A^3.  The inverse, 6.9477, is the
# number of GPa in one kcal/mol/A^3 and is worth recognising.
GPA = 1e-21 * 6.02214076e23 / 4184.0        # 0.143933 kcal/mol/A^3


@dataclass(frozen=True)
class Step:
    """One iteration, as the caller sees it."""

    iteration: int
    energy: float
    max_force: float                # per atom, after symmetry projection
    rms_force: float
    frac: np.ndarray                # (n_sites, 3) asymmetric unit
    terms: dict = field(default_factory=dict)
    converged: bool = False
    # The cell at this step, when the cell is being relaxed too, and
    # ``None`` when it is not.  Fractional coordinates are unchanged by
    # a strain, so ``frac`` means the same thing either way and only
    # this is added.
    matrix: np.ndarray | None = None
    cell_force: float = 0.0         # the strain gradient, per atom
    #: The largest residual stress the space group lets the cell feel,
    #: pressure included, in GPa; 0 when the cell is fixed.
    stress: float = 0.0
    #: Why the run ended here without converging, when it did -- a
    #: line search that could not go downhill.  Empty otherwise.
    reason: str = ""
    #: Which algorithm took this step.  Only the cascade says anything
    #: different from the one asked for.
    method: str = ""

    def line(self) -> str:
        cell = ("" if self.matrix is None else
                f"  |sigma| = {self.stress:8.4f} GPa")
        return (f"{self.iteration:5d}  E = {self.energy:14.5f}  "
                f"|F|max = {self.max_force:10.5f}{cell}")


@dataclass
class OptimizationResult:
    """What the optimisation did, for the report and the command."""

    converged: bool
    steps: int
    initial_energy: float
    energy: float
    max_force: float
    frac: np.ndarray
    terms: dict = field(default_factory=dict)
    history: list = field(default_factory=list)   # (step, E, |F|max)
    message: str = ""
    matrix: np.ndarray | None = None        # the relaxed cell, or None
    initial_matrix: np.ndarray | None = None
    stress: float = 0.0                     # GPa, the last step's
    #: Whether the run ended because somebody pressed Stop rather than
    #: because it converged or ran out of steps.  A caller that can
    #: present a partial relaxation (the Force Field panel) shows it;
    #: one that cannot (a scan point) turns it into a hole, because a
    #: half-relaxed geometry recorded as an energy is a false minimum
    #: that looks exactly like a real one.
    stopped: bool = False

    @property
    def energy_change(self) -> float:
        return self.energy - self.initial_energy

    @property
    def volume_change(self) -> float:
        """Fractional change in the cell volume, 0 if it was fixed."""
        if self.matrix is None or self.initial_matrix is None:
            return 0.0
        before = abs(float(np.linalg.det(self.initial_matrix)))
        after = abs(float(np.linalg.det(self.matrix)))
        return (after - before) / before if before else 0.0

    def summary(self) -> str:
        verdict = ("converged" if self.converged
                   else "stopped without converging")
        cell = ("" if self.matrix is None else
                f", cell {self.volume_change * 100:+.2f}% by volume")
        return (f"{verdict} after {self.steps} steps: "
                f"{self.energy_change:+.4f} kcal/mol to "
                f"{self.energy:.4f}, |F|max {self.max_force:.4f} "
                f"kcal/mol/A{cell}")


# ======================================================================
#  WHICH STRAINS THE CELL MAY STILL USE
# ======================================================================
#
# A strain is six numbers and a space group already forbids most of
# them.  A relaxed scan forbids more: it holds a lattice parameter, or
# the volume, and asks the cell to relax in whatever is left.  Both
# restrictions are linear subspaces of the same six-dimensional space,
# so the answer is their intersection and the tool is a projector onto
# it.
#
# The strains are handled in a metric-normalised coordinate -- the
# shears scaled by root two -- because only there is the tensor inner
# product the ordinary dot product, and only there is the space
# group's average an *orthogonal* projector.  Intersecting subspaces
# with a skew metric silently gives the wrong subspace.


def _w_of(tensor) -> np.ndarray:
    """A symmetric tensor as six numbers with a Euclidean norm."""
    t = np.asarray(tensor, dtype=float)
    root = np.sqrt(2.0)
    return np.array([t[0, 0], t[1, 1], t[2, 2],
                     root * t[1, 2], root * t[0, 2],
                     root * t[0, 1]])


def _tensor_of(w) -> np.ndarray:
    a, b, c, d, e, f = (float(v) / np.sqrt(2.0) for v in w)
    a, b, c = a * np.sqrt(2.0), b * np.sqrt(2.0), c * np.sqrt(2.0)
    return np.array([[a, f, e], [f, b, d], [e, d, c]])


def _reading(lattice, name):
    """A cell quantity as a function of the lattice, by name."""
    if name == "volume":
        return abs(float(np.linalg.det(lattice.matrix)))
    return float(lattice.parameters[PARAMETER_NAMES.index(name)])


@dataclass(frozen=True)
class CellFreedom:
    """Which cell quantities a relaxation must leave where they are.

    ``held`` names them: any of a, b, c, alpha, beta, gamma, or
    ``"volume"``.  Nothing held is the ordinary variable cell, and the
    projector is then the space group's own.

    Holding the volume while the *shape* relaxes is the scan the
    literature on flexible frameworks actually runs, and is the reason
    this is not simply a list of lattice parameters: a profile taken
    at a frozen cell shape depends on which shape was frozen, which
    makes it a measurement of the constraint rather than of the
    material.
    """

    held: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in self.held:
            if name != "volume" and name not in PARAMETER_NAMES:
                raise ValueError(
                    f"{name!r} is not a cell quantity; expected "
                    f"'volume' or one of "
                    f"{', '.join(PARAMETER_NAMES)}")

    def __bool__(self) -> bool:
        return bool(self.held)

    @classmethod
    def free(cls) -> CellFreedom:
        return cls()

    @classmethod
    def constant_volume(cls) -> CellFreedom:
        return cls(("volume",))

    @classmethod
    def fixing(cls, names) -> CellFreedom:
        return cls(tuple(names))

    def describe(self) -> str:
        if not self.held:
            return "the cell relaxes freely"
        return "holding " + ", ".join(self.held)

    def rows(self, lattice, step: float = 1e-6) -> np.ndarray:
        """``d(held quantity)/d(strain)``, one row each.

        Central differences, for the same reason the constraint
        matrix uses them: this differentiates arithmetic rather than
        an energy, it is built once, and writing the derivative of an
        angle between two lattice rows by hand is three chances to put
        a factor of two in the wrong place.
        """
        matrix = lattice.matrix
        out = np.zeros((len(self.held), 6))
        for column in range(6):
            basis = np.zeros(6)
            basis[column] = step
            high = type(lattice)(matrix @ (np.eye(3)
                                           + _tensor_of(basis)))
            low = type(lattice)(matrix @ (np.eye(3)
                                          - _tensor_of(basis)))
            for row, name in enumerate(self.held):
                out[row, column] = (
                    (_reading(high, name) - _reading(low, name))
                    / (2.0 * step))
        return out

    def projector(self, lattice, symmetry) -> np.ndarray:
        """The 6x6 projector onto the strains still allowed.

        ``symmetry`` is the space group's own projector in the same
        coordinate.  The answer is the intersection of its image with
        the null space of :meth:`rows`, and it subsumes ``symmetry``
        rather than composing with it: every strain it permits was
        already one the group permits.
        """
        left, values, _right = np.linalg.svd(symmetry)
        allowed = left[:, values > 0.5]
        if not self.held:
            return allowed @ allowed.T
        if allowed.shape[1] == 0:       # pragma: no cover
            return np.zeros((6, 6))
        restricted = self.rows(lattice) @ allowed
        _u, singular, right = np.linalg.svd(restricted)
        rank = int(np.sum(singular > 1e-8 * max(
            float(singular.max()) if singular.size else 0.0, 1e-30)))
        null = right[rank:].T
        if null.shape[1] == 0:
            raise CalculatorError(
                f"{self.describe()} leaves the cell nothing to relax "
                f"in this space group -- every strain it allows would "
                f"change something being held.  Relax the atoms alone "
                f"instead.")
        basis = allowed @ null
        return basis @ basis.T


# ======================================================================
#  DEGREES OF FREEDOM
# ======================================================================

class SymmetryDOF:
    """The asymmetric unit as the variables, the P1 cell as the value.

    Every atom of the cell is ``x_parent @ W + b`` for a rotation ``W``
    and an offset ``b`` fixed by the operation that generated it, so
    moving a site moves its whole orbit rigidly and correctly.  The
    gradient comes back the same way, through ``W`` transposed.

    ``project`` is the part that keeps special positions special.  The
    operations that map a site onto itself form its site-symmetry
    group, and the average of their (orthogonal) cartesian matrices is
    the projector onto the displacements they all leave alone.  A site
    on a three-fold axis is projected onto that axis; a site on a
    general position is projected onto everything, which is no
    projection at all.

    **With ``relax_cell``, six more variables.**  The cell is deformed
    by ``F = I + e`` for a symmetric strain ``e``: the lattice matrix
    becomes ``M F``, and every atom is carried with it, ``r F``.  The
    site variables stay in the *undeformed* frame, which is what makes
    the two sets of variables independent and the fractional
    coordinates -- what a structure actually stores -- unchanged by a
    strain.

    The strain is symmetry-adapted by the same argument as the site
    projection, one rank up.  A strain is a rank-2 tensor, so the
    operation that acts on a displacement as ``u W`` acts on it as
    ``W^T e W``, and the average of that over the group is the
    projector onto the strains the group allows.  It needs no table of
    crystal systems: a cubic group leaves one free strain (the
    isotropic one), a hexagonal group two, a triclinic group all six,
    and the cell cannot leave its crystal system because there is no
    variable that would take it there.

    Two scalings make the six new variables behave like the old ones,
    so that FIRE's step cap and L-BFGS's line search need no special
    case.  The variable stored is the strain times a cell length, so a
    step in it is a distance; and the gradient is divided by the number
    of atoms, so the number compared against the force tolerance is a
    force per atom rather than a quantity that grows with the cell.
    """

    def __init__(self, structure, frozen=(), relax_cell: bool = False,
                 pressure: float = 0.0, constraints=None,
                 freedom=None):
        self.structure = structure
        self.constraints = constraints or None
        self.freedom = freedom or CellFreedom.free()
        self.cell = p1.expand(structure)
        self.matrix = structure.lattice.matrix
        self.inverse = np.linalg.inv(self.matrix)
        self.n_sites = structure.n_sites
        self.frozen = {int(i) for i in frozen}
        self.relax_cell = bool(relax_cell)
        self.pressure = float(pressure)         # GPa
        self.volume = abs(float(np.linalg.det(self.matrix)))
        # One cell length, to give the strain variables the units of a
        # distance.  Without it a "step" of 0.2 would be a 20% strain.
        self.cell_scale = self.volume ** (1.0 / 3.0) if self.volume \
            else 1.0

        ops = structure.space_group.operations
        n = self.cell.n_atoms
        self.parent = np.asarray(self.cell.site_idx, dtype=int)
        rotations = np.zeros((n, 3, 3))
        offsets = np.zeros((n, 3))
        for k in range(n):
            op = ops[int(self.cell.op_idx[k])]
            rotations[k] = self.inverse @ op.rot.T @ self.matrix
            offsets[k] = (op.trans + self.cell.tau[k]) @ self.matrix
        self.rotations = rotations
        self.offsets = offsets
        self.multiplicity = np.maximum(
            self.cell.multiplicities(self.n_sites), 1)
        self.projectors = self._projectors(ops)
        self.point_group = np.array(
            [self.inverse @ op.rot.T @ self.matrix for op in ops])

        self._at = None
        # Built once, from the point group and whatever the scan is
        # holding.  ``None`` while it is being built, because
        # :meth:`project_strain` is what builds it.
        self.strain_mask = None
        if self.relax_cell:
            self.strain_mask = self.freedom.projector(
                structure.lattice, self._symmetry_strains())
        self.free = np.array([i not in self.frozen
                              for i in range(self.n_sites)])
        if not self.free.any():
            raise CalculatorError(
                "every site is frozen, so there is nothing to relax")

    def _projectors(self, ops) -> np.ndarray:
        """One (3,3) projector per site: what its site symmetry lets it
        do.

        "Maps the site onto itself" is decided by
        :data:`xtal.core.p1.SPECIAL_POSITION_TOL`, the rule the
        expansion uses, and not by rounding slack.  MFU-4l writes its
        chloride 0.0006 A off the three-fold axis; the expansion puts
        it on the axis and so did the cell, but a stabiliser taken to
        1e-6 left it only the mirror.  The energy's gradient is
        symmetric and never noticed, but a held Cl-Cl distance is one
        pair's gradient and is not: it walked the chloride off the
        axis, and past 0.05 A the cell had three times the chlorides.
        """
        out = np.zeros((self.n_sites, 3, 3))
        tol = p1.SPECIAL_POSITION_TOL
        for index, site in enumerate(self.structure.sites):
            stabiliser = []
            for op in ops:
                shift = op.apply(site.frac) - site.frac
                shift = (shift - np.round(shift)) @ self.matrix
                if float(np.linalg.norm(shift)) < tol:
                    stabiliser.append(
                        self.inverse @ op.rot.T @ self.matrix)
            out[index] = (np.mean(stabiliser, axis=0) if stabiliser
                          else np.eye(3))
        return out

    # -- the strain ----------------------------------------------------

    def strain(self, x) -> np.ndarray:
        """The (3,3) symmetric strain these variables describe.

        Projected on the way out, so the answer is always one the
        space group allows however the optimiser got here -- and so
        the energy really is a function of the projected variables,
        which is what makes the projected gradient the right one.
        """
        if not self.relax_cell:
            return np.zeros((3, 3))
        voigt = np.asarray(x[self.n_sites:]).reshape(6) \
            / self.cell_scale
        return self.project_strain(_from_voigt(voigt))

    def project_strain(self, tensor) -> np.ndarray:
        """The part of a strain the space group leaves alone.

        A displacement transforms as ``u W`` and a strain, being one
        rank up, as ``W^T e W``; averaging that over the group is the
        projector onto the strains every operation preserves.  For a
        cubic group the image is the isotropic strain alone, which is
        why a cubic cell relaxed here stays cubic -- not because
        anything checks that it did.
        """
        averaged = self._average_strain(tensor)
        if self.strain_mask is None:
            return averaged
        return _tensor_of(self.strain_mask @ _w_of(averaged))

    def _average_strain(self, tensor) -> np.ndarray:
        tensor = np.asarray(tensor, dtype=float)
        tensor = 0.5 * (tensor + tensor.T)
        if not len(self.point_group):                # pragma: no cover
            return tensor
        averaged = np.einsum("gji,jk,gkl->il", self.point_group,
                             tensor, self.point_group)
        averaged /= len(self.point_group)
        return 0.5 * (averaged + averaged.T)

    def _symmetry_strains(self) -> np.ndarray:
        """The space group's own strain projector, as a 6x6.

        Read off the operator rather than derived a second way, so
        that the mask is intersected with exactly the subspace the
        rest of this class works in.
        """
        out = np.zeros((6, 6))
        for column in range(6):
            basis = np.zeros(6)
            basis[column] = 1.0
            out[:, column] = _w_of(
                self._average_strain(_tensor_of(basis)))
        return out

    def deformation(self, x) -> np.ndarray:
        """``F = I + e``: what the cell and every atom are multiplied
        by."""
        return np.eye(3) + self.strain(x)

    def matrix_of(self, x) -> np.ndarray:
        """The lattice at these variables."""
        if not self.relax_cell:
            return self.matrix
        return self.matrix @ self.deformation(x)

    def residual_stress(self, stress) -> float:
        """The largest stress the cell can still relax, in GPa.

        The external pressure is added first -- a cell at 5 GPa is
        relaxed when its own stress balances it, not when it is zero
        -- and the part the space group forbids is projected away,
        because no allowed strain can remove it and a criterion on it
        could never be met.
        """
        total = np.asarray(stress, dtype=float)
        if self.pressure:
            total = total + self.pressure * GPA * np.eye(3)
        return float(np.abs(self.project_strain(total)).max()) / GPA

    def pressure_energy(self, x) -> float:
        """``P V`` in kcal/mol, so that "what does this do at 5 GPa" is
        a number in the panel rather than a separate script."""
        if not (self.relax_cell and self.pressure):
            return 0.0
        volume = self.volume * abs(float(np.linalg.det(
            self.deformation(x))))
        return self.pressure * GPA * volume

    # -- the mapping ---------------------------------------------------

    @property
    def start(self) -> np.ndarray:
        """Cartesian coordinates of the sites, the initial variables.

        With the cell relaxing, two more rows carrying the six strain
        components -- all zero, because the strain is measured from the
        cell the user handed us.
        """
        sites = self.structure.frac @ self.matrix
        if not self.relax_cell:
            return sites
        return np.vstack([sites, np.zeros((2, 3))])

    def sites_of(self, x) -> np.ndarray:
        """The site rows of the variable vector."""
        return x[:self.n_sites] if self.relax_cell else x

    def positions(self, x) -> np.ndarray:
        """P1 cartesian positions for these variables."""
        undeformed = (np.einsum("kj,kji->ki",
                                self.sites_of(x)[self.parent],
                                self.rotations) + self.offsets)
        if not self.relax_cell:
            return undeformed
        return undeformed @ self.deformation(x)

    def gradient(self, cell_gradient, x=None,
                 stress=None) -> np.ndarray:
        """The P1 gradient, carried back onto the variables.

        Summing over the orbit is not an approximation: displacing a
        site displaces every one of its images, so the derivative with
        respect to the site really is the sum of the derivatives with
        respect to them.

        With the cell relaxing there are two more things to do.  The
        atomic gradient is carried out of the deformed frame (through
        ``F^T``, because a site variable reaches the energy as
        ``x F``), and the strain gradient is read off the **stress**,
        which is what a stress is: ``dE/de = V sigma``.
        """
        out = self.carry(cell_gradient, x)
        if self.relax_cell:
            out = np.vstack([out, self.strain_gradient(x, stress)])
        if self.constraints is not None and x is not None:
            # Projected *after* everything else, so that a held
            # coordinate can only take freedom away.  What is left is
            # the residual force in the directions still open, which
            # is what "this point is relaxed" has to mean under a
            # constraint -- measuring the whole gradient would leave
            # the component the constraint is holding in it, and no
            # constrained point would ever converge.
            out = self.constraints.project(self, out, x)
        return out

    def carry(self, cell_gradient, x=None) -> np.ndarray:
        """A P1 gradient on the *site* variables, whatever it is of.

        The energy's own gradient is the first caller and a held
        coordinate's is the second: both are functions of where the
        atoms of the cell are, and both reach the variables by the
        same three steps -- out of the deformed frame, summed over
        each orbit, projected onto what site symmetry and the frozen
        set allow.  Only the strain rows differ, because a stress is
        not the sum of position-times-force over a periodic cell and a
        constraint's dependence on the cell is not a stress.
        """
        if self.relax_cell:
            cell_gradient = cell_gradient @ self.deformation(x).T
        per_atom = np.einsum("kj,kij->ki", cell_gradient,
                             self.rotations)
        out = np.zeros((self.n_sites, 3))
        np.add.at(out, self.parent, per_atom)
        out = np.einsum("sj,sji->si", out, self.projectors)
        out[~self.free] = 0.0
        return out

    def strain_gradient(self, x, stress) -> np.ndarray:
        """``dE/de``, projected, in Voigt order and in the variable's
        own scaling.

        The pressure rides along here: ``d(P V)/de = P V I``, so an
        external pressure is one term added to the diagonal of the
        stress and nothing else in the optimiser changes.
        """
        deformation = self.deformation(x)
        volume = self.volume * abs(float(np.linalg.det(deformation)))
        total = np.asarray(stress, dtype=float)
        if self.pressure:
            total = total + self.pressure * GPA * np.eye(3)
        # The stress is the derivative with respect to a strain
        # applied to the *current* cell (``F -> F(I+d)``), while the
        # variable enters additively (``F -> F + dF``).  The two are
        # related by ``d = F^-1 dF``, so the derivative with respect to
        # the variable carries the inverse of the deformation already
        # there -- which is the identity on the first step and a few
        # percent by the last.
        gradient = np.linalg.inv(deformation).T @ (volume * total)
        gradient = self.project_strain(gradient)
        return (_to_voigt(gradient).reshape(2, 3)
                / self.cell_scale)

    def project(self, direction) -> np.ndarray:
        """A step direction with nothing in it the variables may not do.

        The gradient is projected already, so a direction made of
        gradients is too -- to within rounding.  One made of a
        subspace solve is not even that, and a frozen atom or a site
        on a mirror that drifts 1e-12 a step is visibly elsewhere after
        a few hundred.  The strain rows need nothing: :meth:`strain`
        projects them wherever they are.
        """
        out = np.array(direction, dtype=float, copy=True)
        sites = out[:self.n_sites]
        sites[:] = np.einsum("sj,sji->si", sites, self.projectors)
        sites[~self.free] = 0.0
        if self.constraints is not None and self._at is not None:
            out = self.constraints.project(self, out, self._at)
        return out

    def restore(self, x) -> np.ndarray:
        """``x`` put back on any held coordinates; itself when there
        are none."""
        if self.constraints is None:
            return x
        return self.constraints.restore(self, x)

    def hold_at(self, x) -> None:
        """Where to linearise a constraint for the next projection.

        :meth:`project` is handed a direction and nothing else -- the
        line-search rules have no notion of where they are -- but a
        constraint is only linear near a point.  The loop says where
        it is before it asks.
        """
        self._at = None if x is None else np.array(x, dtype=float)

    def to_frac(self, x) -> np.ndarray:
        """Fractional coordinates of the sites.

        A strain leaves these alone -- it multiplies the atoms and the
        cell by the same thing -- which is why a step reports them
        whether the cell is relaxing or not.
        """
        return self.sites_of(x) @ self.inverse

    def force_scale(self) -> np.ndarray:
        """Divide a site gradient by this to get a force per atom.

        A site of multiplicity four collects four atoms' worth of
        gradient, so the raw number is four times what a
        crystallographer would call the force on that atom -- and a
        tolerance of 0.05 would mean something different for every
        Wyckoff position.  The strain rows are divided by the whole
        cell for the same reason: the stress is a sum over every atom
        in it.
        """
        scale = self.multiplicity.astype(float)[:, None]
        if not self.relax_cell:
            return scale
        atoms = max(self.cell.n_atoms, 1)
        return np.vstack([scale, np.full((2, 1), float(atoms))])


def _to_voigt(tensor) -> np.ndarray:
    """A symmetric tensor as six numbers.

    The off-diagonals are doubled because the variable is one number
    standing for two equal components, so its derivative collects both.
    """
    return np.array([tensor[0, 0], tensor[1, 1], tensor[2, 2],
                     2 * tensor[1, 2], 2 * tensor[0, 2],
                     2 * tensor[0, 1]])


def _from_voigt(voigt) -> np.ndarray:
    a, b, c, d, e, f = (float(v) for v in voigt)
    return np.array([[a, f, e], [f, b, d], [e, d, c]])


# ======================================================================
#  THE OPTIMISERS
# ======================================================================

class _StopBetweenEvaluations:
    """A calculator that checks for Stop before each evaluation.

    Everything but :meth:`compute` is the wrapped engine's, so an
    optimiser, a report or a panel asking this for its summary, its
    atom types or its charges gets the real answers.
    """

    def __init__(self, calculator, cancel):
        self._calculator = calculator
        self._cancel = cancel

    def __getattr__(self, name):
        return getattr(self._calculator, name)

    def compute(self, positions, matrix=None, *args, **kwargs):
        if getattr(self._cancel, "requested", False):
            raise CalculatorStopped("stopped between evaluations")
        return self._calculator.compute(positions, matrix,
                                        *args, **kwargs)


class _Problem:
    """Energy and gradient in the variables the optimisers see."""

    def __init__(self, calculator, dof):
        self.calculator = calculator
        self.dof = dof
        self.evaluations = 0
        self.terms: dict = {}
        self.stress = 0.0

    def __call__(self, x):
        self.evaluations += 1
        matrix = self.dof.matrix_of(x)
        positions = self.dof.positions(x)
        result = self.calculator.compute(positions, matrix)
        self.terms = result.terms
        if not self.dof.relax_cell:
            return result.energy, self.dof.gradient(-result.forces)

        # An engine that computes its own stress is asked for it; one
        # that does not gets it by central differences, which is
        # twelve more energy evaluations a step.  UFF returns its
        # virial (9x faster a step on MFU-4l); xTB, DFTB+ and UFF with
        # an Ewald sum still pay the twelve.
        stress = result.stress
        if stress is None:
            stress = self.calculator.numeric_stress(positions, matrix)
        self.stress = self.dof.residual_stress(stress)
        energy = result.energy + self.dof.pressure_energy(x)
        return energy, self.dof.gradient(-result.forces, x=x,
                                         stress=stress)

    def forces(self, gradient):
        """``(max, rms)`` force per atom, over the *atoms*.

        Deliberately not over the strain rows as well: |F|max is a
        number a user compares between runs and against a tolerance
        they know, and quietly redefining it the moment the cell is
        allowed to move would make two runs of the same structure
        incomparable.  The cell's own convergence is
        :meth:`cell_force`, reported beside it.
        """
        scaled = (gradient / self.dof.force_scale())[:self.dof.n_sites]
        norms = np.linalg.norm(scaled, axis=1)
        if not len(norms):                          # pragma: no cover
            return 0.0, 0.0
        return float(norms.max()), float(
            np.sqrt(np.mean(norms ** 2)))

    def cell_force(self, gradient) -> float:
        """How far from relaxed the cell is, per atom.

        The same units and the same scaling as an atomic force, so the
        one tolerance covers both -- which is the whole reason the
        strain variables were given the units of a distance.
        """
        if not self.dof.relax_cell:
            return 0.0
        scaled = (gradient / self.dof.force_scale())[self.dof.n_sites:]
        return float(np.abs(scaled).max())


def _step(iteration: int, energy: float, gradient, x, dof, problem,
          force_tolerance: float,
          stress_tolerance: float = DEFAULT_STRESS_TOLERANCE,
          method: str = "") -> Step:
    """One iteration, packaged for the caller.

    Convergence is both halves when both are variables: a cell still
    under a stress is not a relaxed structure, however still its atoms
    are.  The cell's half is the residual stress in GPa, which is the
    number that says whether the lattice constant is still moving.
    """
    peak, rms = problem.forces(gradient)
    cell = problem.cell_force(gradient)
    stress = problem.stress if dof.relax_cell else 0.0
    converged = peak <= force_tolerance
    if dof.relax_cell:
        converged = converged and stress <= stress_tolerance
    return Step(
        iteration, energy, peak, rms, dof.to_frac(x),
        dict(problem.terms),
        converged=converged,
        matrix=(dof.matrix_of(x) if dof.relax_cell else None),
        cell_force=cell,
        stress=stress,
        method=method,
    )


def unconverged(step, force_tolerance: float,
                stress_tolerance: float = DEFAULT_STRESS_TOLERANCE
                ) -> str:
    """What is still short of the tolerance, as a phrase: "the
    forces", "the cell", or both -- so a run that stopped says which
    half to look at.  ``step`` is a :class:`Step` or an
    :class:`OptimizationResult`; both carry the three numbers."""
    parts = []
    if step.max_force > force_tolerance:
        parts.append(f"the forces ({step.max_force:.3g} kcal/mol/A)")
    if step.matrix is not None and step.stress > stress_tolerance:
        parts.append(f"the cell ({step.stress:.3g} GPa)")
    return " and ".join(parts)


def _capped(step, limit: float) -> np.ndarray:
    """Nothing moves further than ``limit`` in one iteration."""
    longest = np.linalg.norm(step, axis=1).max() if len(step) else 0.0
    if longest > limit:
        step = step * (limit / longest)
    return step


def fire(calculator, structure, dof=None, max_steps=DEFAULT_MAX_STEPS,
         force_tolerance=DEFAULT_FORCE_TOLERANCE,
         stress_tolerance=DEFAULT_STRESS_TOLERANCE,
         max_step=DEFAULT_MAX_STEP, dt=0.1, dt_max=1.0, n_min=5,
         f_inc=1.1, f_dec=0.5, alpha_start=0.1,
         f_alpha=0.99) -> Iterator[Step]:
    """FIRE (Bitzek et al., *Phys. Rev. Lett.* **2006**, 97, 170201).

    Molecular dynamics with the velocity steered towards the force and
    the time step grown while progress continues, thrown away the
    moment it stops.  Slower than L-BFGS near a minimum and far more
    forgiving a long way from one, which is what a hand-built
    structure needs.
    """
    dof = dof or SymmetryDOF(structure)
    problem = _Problem(calculator, dof)
    x = dof.restore(dof.start.copy())
    velocity = np.zeros_like(x)
    alpha = alpha_start
    since_uphill = 0

    dof.hold_at(x)
    energy, gradient = problem(x)
    for iteration in range(max_steps + 1):
        yield (step := _step(iteration, energy, gradient, x, dof,
                             problem, force_tolerance,
                             stress_tolerance, "fire"))
        if step.converged or iteration == max_steps:
            return

        force = -gradient
        power = float(np.sum(force * velocity))
        if power > 0.0:
            norm_f = np.linalg.norm(force)
            norm_v = np.linalg.norm(velocity)
            if norm_f > 0:
                velocity = ((1.0 - alpha) * velocity
                            + alpha * norm_v * force / norm_f)
            if since_uphill > n_min:
                dt = min(dt * f_inc, dt_max)
                alpha *= f_alpha
            since_uphill += 1
        else:
            velocity = np.zeros_like(x)
            since_uphill = 0
            dt *= f_dec
            alpha = alpha_start

        velocity = velocity + dt * force
        dof.hold_at(x)
        x = dof.restore(x + dof.project(
            _capped(dt * velocity, max_step)))
        dof.hold_at(x)
        energy, gradient = problem(x)


# ----------------------------------------------------------------------
#  The line-search family
# ----------------------------------------------------------------------
#
# Steepest descent, conjugate gradient, quasi-Newton, ABNR and L-BFGS
# differ only in which way they point.  Everything else -- the step
# cap, the search along the direction, what to do when it fails, when
# to stop -- is one loop, and a direction is a small object that is
# asked for one and told what the step it chose did.

class _Direction:
    """Which way to go, and what to learn from having gone."""

    name = ""

    def direction(self, x, gradient) -> np.ndarray:
        raise NotImplementedError

    def learn(self, x, gradient, new_x, new_gradient,
              length: float) -> None:
        """A step was accepted."""

    def reset(self) -> None:
        """Forget everything: the last direction led nowhere."""

    def first_length(self) -> float:
        """The length the search tries first, before the cap."""
        return 1.0


class _SteepestDescent(_Direction):
    """Straight down the gradient, with a length that remembers.

    The gradient has the wrong units for a step, so the length that
    worked last time is where the next search starts -- grown a
    little, because a search that always accepts its first try is
    being too timid.
    """

    name = "steepest descent"

    def __init__(self):
        self.length = 1.0

    def direction(self, x, gradient):
        return -gradient

    def learn(self, x, gradient, new_x, new_gradient, length):
        self.length = length * 1.2

    def reset(self):
        self.length = 1.0

    def first_length(self):
        return self.length


class _ConjugateGradient(_SteepestDescent):
    """Polak-Ribiere with the non-negative restart (PR+).

    Each direction is the new gradient plus a share of the last
    direction, which is what stops steepest descent zig-zagging down a
    long valley.  The share is clipped at zero, and the whole history
    is dropped every ``n`` steps or whenever the result stops pointing
    downhill -- the two conditions under which the conjugacy it relies
    on no longer holds.
    """

    name = "conjugate gradient"

    def __init__(self, n_variables: int):
        super().__init__()
        self.restart_every = max(int(n_variables), 1)
        self.previous = None
        self.previous_gradient = None
        self.count = 0

    def direction(self, x, gradient):
        if (self.previous is None
                or self.count >= self.restart_every):
            self.count = 0
            return -gradient
        old = self.previous_gradient
        beta = max(0.0, float(np.sum(gradient * (gradient - old)))
                   / max(float(np.sum(old * old)), 1e-300))
        direction = -gradient + beta * self.previous
        if float(np.sum(direction * gradient)) >= 0.0:
            self.count = 0
            return -gradient
        return direction

    def learn(self, x, gradient, new_x, new_gradient, length):
        super().learn(x, gradient, new_x, new_gradient, length)
        self.previous = (new_x - x) / max(length, 1e-300)
        self.previous_gradient = gradient
        self.count += 1

    def reset(self):
        super().reset()
        self.previous = self.previous_gradient = None
        self.count = 0


#: Above this many variables the quasi-Newton inverse Hessian -- the
#: square of it, in doubles -- stops being worth holding: 6000 is
#: 290 MB, and L-BFGS reaches the same minimum in the same number of
#: steps near it without the matrix.
QUASI_NEWTON_MAX_VARIABLES = 6000


class _QuasiNewton(_Direction):
    """BFGS: the whole inverse Hessian, built up one step at a time.

    What Materials Studio calls quasi-Newton.  Over the
    symmetry-reduced variables that is small for most crystals -- MOF-5
    in Fm-3m is seven sites and two strain rows -- and holding all of
    it is what makes it faster than L-BFGS once it is near a minimum.
    """

    name = "quasi-Newton"

    def __init__(self, n_variables: int):
        self.check(n_variables)
        self.n = int(n_variables)
        self.inverse = None

    @staticmethod
    def check(n_variables: int) -> None:
        if n_variables > QUASI_NEWTON_MAX_VARIABLES:
            raise CalculatorError(
                f"quasi-Newton would hold a {n_variables} x "
                f"{n_variables} matrix; above "
                f"{QUASI_NEWTON_MAX_VARIABLES} variables use L-BFGS, "
                f"which reaches the same minimum without it")

    def direction(self, x, gradient):
        flat = gradient.reshape(-1)
        if self.inverse is None:
            return -gradient
        return -(self.inverse @ flat).reshape(gradient.shape)

    def learn(self, x, gradient, new_x, new_gradient, length):
        s = (new_x - x).reshape(-1)
        y = (new_gradient - gradient).reshape(-1)
        sy = float(s @ y)
        if sy <= 1e-12:
            return                  # would make the matrix indefinite
        if self.inverse is None:
            # Scaled so the first quasi-Newton step has the length the
            # curvature just measured asks for, not the gradient's.
            self.inverse = np.eye(self.n) * (sy / float(y @ y))
        rho = 1.0 / sy
        hy = self.inverse @ y
        self.inverse += (rho * rho * float(y @ hy) + rho) \
            * np.outer(s, s) - rho * (np.outer(hy, s) + np.outer(s, hy))

    def reset(self):
        self.inverse = None


class _LBFGS(_Direction):
    """L-BFGS: the last ``memory`` steps stand in for the Hessian.

    The inverse Hessian is never formed; the two-loop recursion applies
    it.  Curvature pairs that fail the ``s . y > 0`` test are dropped
    rather than stored: keeping one makes the approximation indefinite,
    and the next direction points uphill.
    """

    name = "L-BFGS"

    def __init__(self, memory: int = 10):
        self.memory = memory
        self.history: list[tuple[np.ndarray, np.ndarray, float]] = []

    def direction(self, x, gradient):
        return -_two_loop(gradient, self.history)

    def learn(self, x, gradient, new_x, new_gradient, length):
        s = new_x - x
        y = new_gradient - gradient
        curvature = float(np.sum(s * y))
        if curvature > 1e-12:
            self.history.append((s, y, 1.0 / curvature))
            if len(self.history) > self.memory:
                self.history.pop(0)

    def reset(self):
        self.history.clear()


class _ABNR(_Direction):
    """Adopted-basis Newton-Raphson, after CHARMM's (Brooks et al.,
    *J. Comput. Chem.* **1983**, 4, 187).

    A Newton step taken in the small space the last few steps span,
    where the Hessian can be measured from how the gradient changed
    along them, plus a steepest-descent step for the part of the
    gradient that space does not reach.  Cheap per step like steepest
    descent, and converging like Newton along the directions that
    matter -- which is why Materials Studio hands it the middle of a
    minimisation.

    A subspace Hessian with a non-positive curvature is not a Newton
    step to anywhere; its eigenvalues are taken in magnitude, floored,
    so the step still goes downhill.
    """

    name = "ABNR"

    def __init__(self, basis: int = 5):
        self.basis = basis
        self.points: list[tuple[np.ndarray, np.ndarray]] = []

    def direction(self, x, gradient):
        if len(self.points) < 2:
            return -gradient
        flat_g = gradient.reshape(-1)
        flat_x = x.reshape(-1)
        s = np.array([p.reshape(-1) - flat_x for p, _g in self.points]).T
        y = np.array([g.reshape(-1) - flat_g for _p, g in self.points]).T
        # An SVD and not a QR: the last few steps are often nearly
        # parallel, and a QR of a rank-deficient set hands back basis
        # vectors pointing anywhere -- into a frozen atom, or off a
        # special position.  The singular vectors that are kept lie in
        # the span of the steps and nowhere else.
        u, sizes, vt = np.linalg.svd(s, full_matrices=False)
        keep = sizes > 1e-8 * max(float(sizes.max()), 1e-300)
        if not keep.any():
            return -gradient
        q = u[:, keep]
        coordinates = sizes[keep, None] * vt[keep]
        # y = H s and s = q c, so q^T y = (q^T H q) c.
        hessian = (q.T @ y) @ np.linalg.pinv(coordinates)
        hessian = 0.5 * (hessian + hessian.T)
        values, vectors = np.linalg.eigh(hessian)
        values = np.maximum(np.abs(values),
                            1e-6 * max(np.abs(values).max(), 1e-12))
        inside = q.T @ flat_g
        newton = -(vectors @ ((vectors.T @ inside) / values))
        outside = flat_g - q @ inside
        descent = -outside / float(np.mean(values))
        return (q @ newton + descent).reshape(gradient.shape)

    def learn(self, x, gradient, new_x, new_gradient, length):
        self.points.append((x.copy(), gradient.copy()))
        if len(self.points) > self.basis:
            self.points.pop(0)

    def reset(self):
        self.points.clear()


def _line_search(problem, x, energy, gradient, direction, max_step,
                 first_length=1.0, c1=1e-4, attempts=20):
    """Backtrack along ``direction`` until the energy has gone down
    enough, or give up and return ``None``.

    The cut is a quadratic through the two energies and the slope
    rather than a halving, kept between a tenth and a half of the last
    try: halving wastes evaluations when the first try overshot by a
    long way, which the first steepest-descent step always does.
    """
    slope = float(np.sum(gradient * direction))
    length = float(first_length)
    longest = float(np.linalg.norm(direction, axis=1).max()) \
        if len(direction) else 0.0
    if longest * length > max_step:
        length = max_step / longest
    for _attempt in range(attempts):
        # Restored before it is evaluated, not after it is accepted.
        # The search then walks along the constraint instead of along
        # the tangent to it, and the energy it compares is the energy
        # of a point that really satisfies the coordinate -- which
        # also costs nothing, where restoring afterwards would need
        # the whole step evaluated a second time.
        trial = problem.dof.restore(x + length * direction)
        new_energy, new_gradient = problem(trial)
        if new_energy <= energy + c1 * length * slope:
            return trial, new_energy, new_gradient, length
        curvature = (new_energy - energy - slope * length) \
            / (length * length)
        guess = (-slope / (2.0 * curvature) if curvature > 0
                 else 0.5 * length)
        length = min(max(guess, 0.1 * length), 0.5 * length)
    return None


def _descend(calculator, structure, dof, rule_for, max_steps,
             force_tolerance, stress_tolerance,
             max_step) -> Iterator[Step]:
    """The loop every line-search method shares.

    ``rule_for(step, n_variables)`` returns the direction rule to use
    for the next step -- the same one every time, except for the
    cascade, which changes rule as the forces fall.

    **A search that fails is not the end of the run.**  The rule's
    memory is dropped and steepest descent is tried once from the same
    point; only if that cannot go downhill either does the run stop,
    and then it says so on the last step.  L-BFGS used to return
    silently here, which looked exactly like the step limit.
    """
    dof = dof or SymmetryDOF(structure)
    problem = _Problem(calculator, dof)
    x = dof.restore(dof.start.copy())
    n_variables = x.size
    dof.hold_at(x)
    energy, gradient = problem(x)
    rule = None
    for iteration in range(max_steps + 1):
        step = _step(iteration, energy, gradient, x, dof, problem,
                     force_tolerance, stress_tolerance,
                     rule.name if rule is not None else "")
        chosen = rule_for(step, n_variables)
        if chosen is not rule:
            rule = chosen
            step = replace(step, method=rule.name)
        yield step
        if step.converged or iteration == max_steps:
            return

        dof.hold_at(x)
        found = _line_search(problem, x, energy, gradient,
                             dof.project(rule.direction(x, gradient)),
                             max_step, rule.first_length())
        if found is None:
            rule.reset()
            found = _line_search(problem, x, energy, gradient,
                                 dof.project(-gradient), max_step)
        if found is None:
            problem(x)          # the terms and stress of where it is
            yield replace(step, reason=(
                "the line search could not lower the energy from "
                "here, even straight down the gradient -- the forces "
                "are finer than the energy can resolve, or the "
                "tolerance is tighter than this engine can reach"))
            return
        new_x, new_energy, new_gradient, length = found
        rule.learn(x, gradient, new_x, new_gradient, length)
        x, energy, gradient = new_x, new_energy, new_gradient


def _fixed(make):
    """A ``rule_for`` that builds its rule once and keeps it."""
    held = {}

    def rule_for(_step, n_variables):
        if "rule" not in held:
            held["rule"] = make(n_variables)
        return held["rule"]
    return rule_for


def steepest_descent(calculator, structure, dof=None,
                     max_steps=DEFAULT_MAX_STEPS,
                     force_tolerance=DEFAULT_FORCE_TOLERANCE,
                     stress_tolerance=DEFAULT_STRESS_TOLERANCE,
                     max_step=DEFAULT_MAX_STEP) -> Iterator[Step]:
    """Down the gradient, searched.  The slowest near a minimum and the
    safest far from one."""
    return _descend(calculator, structure, dof,
                    _fixed(lambda n: _SteepestDescent()), max_steps,
                    force_tolerance, stress_tolerance, max_step)


def conjugate_gradient(calculator, structure, dof=None,
                       max_steps=DEFAULT_MAX_STEPS,
                       force_tolerance=DEFAULT_FORCE_TOLERANCE,
                       stress_tolerance=DEFAULT_STRESS_TOLERANCE,
                       max_step=DEFAULT_MAX_STEP) -> Iterator[Step]:
    """Polak-Ribiere conjugate gradient; see :class:`_ConjugateGradient`."""
    return _descend(calculator, structure, dof,
                    _fixed(_ConjugateGradient), max_steps,
                    force_tolerance, stress_tolerance, max_step)


def quasi_newton(calculator, structure, dof=None,
                 max_steps=DEFAULT_MAX_STEPS,
                 force_tolerance=DEFAULT_FORCE_TOLERANCE,
                 stress_tolerance=DEFAULT_STRESS_TOLERANCE,
                 max_step=DEFAULT_MAX_STEP) -> Iterator[Step]:
    """BFGS with a line search; see :class:`_QuasiNewton`."""
    dof = dof or SymmetryDOF(structure)
    # Refused now rather than at the first step, so a caller asking
    # for it on a structure too big hears so before a run begins.
    _QuasiNewton.check(dof.start.size)
    return _descend(calculator, structure, dof, _fixed(_QuasiNewton),
                    max_steps, force_tolerance, stress_tolerance,
                    max_step)


def abnr(calculator, structure, dof=None, max_steps=DEFAULT_MAX_STEPS,
         force_tolerance=DEFAULT_FORCE_TOLERANCE,
         stress_tolerance=DEFAULT_STRESS_TOLERANCE,
         max_step=DEFAULT_MAX_STEP) -> Iterator[Step]:
    """Adopted-basis Newton-Raphson; see :class:`_ABNR`."""
    return _descend(calculator, structure, dof,
                    _fixed(lambda n: _ABNR()), max_steps,
                    force_tolerance, stress_tolerance, max_step)


def lbfgs(calculator, structure, dof=None,
          max_steps=DEFAULT_MAX_STEPS,
          force_tolerance=DEFAULT_FORCE_TOLERANCE,
          stress_tolerance=DEFAULT_STRESS_TOLERANCE,
          max_step=DEFAULT_MAX_STEP, memory=10) -> Iterator[Step]:
    """L-BFGS with a line search; see :class:`_LBFGS`."""
    return _descend(calculator, structure, dof,
                    _fixed(lambda n: _LBFGS(memory)), max_steps,
                    force_tolerance, stress_tolerance, max_step)


#: Where the cascade hands over, as the largest force per atom in
#: kcal/mol/A.  Materials Studio's Smart does the same three stages in
#: the same order and does not say where it switches; these are where
#: each one stops paying on the frameworks in ``resources/samples``.
SMART_DESCENT_UNTIL = 10.0
SMART_ABNR_UNTIL = 1.0


def smart(calculator, structure, dof=None, max_steps=DEFAULT_MAX_STEPS,
          force_tolerance=DEFAULT_FORCE_TOLERANCE,
          stress_tolerance=DEFAULT_STRESS_TOLERANCE,
          max_step=DEFAULT_MAX_STEP) -> Iterator[Step]:
    """Steepest descent, then ABNR, then quasi-Newton, as the forces
    fall -- each where it is best.

    Steepest descent survives a structure with two atoms on top of
    each other that would send a Newton step anywhere; ABNR is quick
    through the middle; quasi-Newton finishes.  It never goes back a
    stage: a force that rises again on the way down is a line search
    overshooting, not a structure that has become hand-built.  Where
    there are too many variables for quasi-Newton, L-BFGS finishes.
    """
    rules: dict = {}

    def rule_for(step, n_variables):
        stage = rules.get("stage", 0)
        if stage == 0 and step.max_force <= SMART_DESCENT_UNTIL:
            stage = 1
        if stage == 1 and step.max_force <= SMART_ABNR_UNTIL:
            stage = 2
        if stage != rules.get("stage"):
            rules["stage"] = stage
            if stage == 0:
                rules["rule"] = _SteepestDescent()
            elif stage == 1:
                rules["rule"] = _ABNR()
            elif n_variables <= QUASI_NEWTON_MAX_VARIABLES:
                rules["rule"] = _QuasiNewton(n_variables)
            else:
                rules["rule"] = _LBFGS()
        return rules["rule"]

    return _descend(calculator, structure, dof, rule_for, max_steps,
                    force_tolerance, stress_tolerance, max_step)


def _two_loop(gradient, history) -> np.ndarray:
    """The L-BFGS two-loop recursion: the inverse Hessian applied to
    the gradient without ever building it."""
    q = gradient.copy()
    alphas = []
    for s, y, rho in reversed(history):
        alpha = rho * float(np.sum(s * q))
        alphas.append(alpha)
        q = q - alpha * y
    if history:
        s, y, _rho = history[-1]
        scale = float(np.sum(s * y)) / float(np.sum(y * y))
        q = q * scale
    for (s, y, rho), alpha in zip(history, reversed(alphas),
                                  strict=True):
        beta = rho * float(np.sum(y * q))
        q = q + s * (alpha - beta)
    return q


#: Every optimiser, in the order the panel offers them: the two that
#: were here first, then Materials Studio's set.
METHODS = {"lbfgs": lbfgs, "fire": fire, "smart": smart,
           "steepest_descent": steepest_descent,
           "conjugate_gradient": conjugate_gradient,
           "quasi_newton": quasi_newton, "abnr": abnr}


# ======================================================================
#  RUNNING ONE TO THE END
# ======================================================================

def steps(calculator, structure, method: str = "lbfgs",
          frozen=(), relax_cell: bool = False, pressure: float = 0.0,
          cancel=None, constraints=None, freedom=None,
          poll_evaluations: bool = False,
          **kwargs) -> Iterator[Step]:
    """The chosen optimiser, as a generator of steps.

    ``relax_cell`` adds the six symmetry-adapted strain components to
    the variables; ``pressure`` is in GPa and is applied only when the
    cell can respond to it.  ``cancel`` is handed to the calculator,
    so an engine that runs a program can be stopped in the middle of
    an evaluation and not only between steps.

    ``constraints`` is a :class:`xtal.ff.constraints.Holonomic`: the
    coordinates a relaxed scan holds while the rest of the crystal
    relaxes around them.  They are checked before the first step
    rather than discovered to be impossible on the hundredth.

    ``freedom`` is a :class:`CellFreedom`: which cell quantities the
    relaxation must leave alone.  It only means anything with
    ``relax_cell``, because with a fixed cell there is nothing to
    hold back.
    """
    if cancel is not None:
        if hasattr(calculator, "stop_with"):
            # An engine that runs a program can be stopped in the
            # middle of one; that is all ``stop_with`` ever did.
            calculator.stop_with(cancel)
        if poll_evaluations:
            # An engine that computes in this process cannot be
            # stopped that way, so the poll goes where every optimiser
            # has to come: the call that asks for an energy.
            #
            # Off by default, and on for :func:`run`.  A caller that
            # drives the generator itself -- the Force Field panel's
            # worker -- already stops at the step boundary and keeps
            # what it reached; arriving mid-step would leave it with
            # no step to report and turn Stop into a failure.  A scan
            # point is the other case: one point is hundreds of steps
            # and waiting for the boundary made Stop look dead for up
            # to 3.7 minutes on Ni2Cl2BTDD.
            calculator = _StopBetweenEvaluations(calculator, cancel)
    try:
        optimizer = METHODS[method]
    except KeyError:
        raise ValueError(
            f"unknown optimiser {method!r}; "
            f"have {', '.join(sorted(METHODS))}") from None
    dof = SymmetryDOF(structure, frozen, relax_cell=relax_cell,
                      pressure=pressure, constraints=constraints,
                      freedom=freedom)
    if constraints:
        constraints.check(dof, dof.start)
    return optimizer(calculator, structure, dof=dof, **kwargs)


def run(calculator, structure, method: str = "lbfgs", frozen=(),
        callback=None, **kwargs) -> OptimizationResult:
    """Optimise to convergence (or to the step limit) and report.

    ``callback(step)`` is called after each iteration and may return
    ``False`` to stop early -- which is how the CLI prints a running
    trace, and how a caller without a thread cancels.
    """
    history = []
    first = last = None
    stopped = False
    # A Stop raised between evaluations is the same event as a
    # callback returning False, only noticed sooner: one step of a
    # relaxing cell is about fourteen energy evaluations, so waiting
    # for the step boundary is what made Stop feel dead. Both land
    # here, so a stopped run keeps the steps it finished rather than
    # becoming a failure -- the Force Field panel says "stopped
    # without converging" and leaves the trace on screen.
    try:
        for step in steps(calculator, structure, method, frozen,
                          poll_evaluations=True, **kwargs):
            history.append((step.iteration, step.energy,
                            step.max_force))
            if first is None:
                first = step
            last = step
            if callback is not None and callback(step) is False:
                stopped = True
                break
    except CalculatorStopped:
        stopped = True
        if last is None:
            raise

    if last is None:                                # pragma: no cover
        raise CalculatorError("the optimiser produced no steps")
    message = last.reason or last.line()
    if stopped:
        message = f"stopped by the caller at step {last.iteration}"
        # So a caller that cannot use a half-relaxed geometry -- a
        # scan point, which would otherwise record a finite energy for
        # a structure nobody asked about -- can tell.

    return OptimizationResult(
        converged=last.converged and not stopped,
        steps=last.iteration,
        initial_energy=first.energy,
        energy=last.energy,
        max_force=last.max_force,
        frac=last.frac,
        terms=dict(last.terms),
        history=history,
        message=message,
        matrix=last.matrix,
        initial_matrix=(None if last.matrix is None
                        else structure.lattice.matrix),
        stress=last.stress,
        stopped=stopped,
    )
