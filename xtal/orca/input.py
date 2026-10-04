"""
xtal.orca.input
===============
An ORCA input file, and the coordinates it reads, for a structure.

ORCA is molecular: it has no cell.  So what it is handed is a
*cluster* -- every atom of the cell, or the selected ones, with each
molecule made whole across the cell faces by the stored bond graph.
Written as the cell wraps them, a CO2 lying across a face is a carbon
with its oxygens four angstroms away on the far side, and ORCA would
optimise three atoms nobody meant.  A piece that never closes (a
framework) has no whole to make, and is written as cut from the
cell, with a caution saying so.

**The spin is refused, not corrected.**  The electrons are the atomic
numbers less the charge; an even count needs an odd multiplicity and
an odd count an even one, and no multiplicity exceeds the count plus
one.  ORCA says the same thing, but only after the queue: here it is
said before anything is written.  An ECP takes an even number of
electrons away, so the parity holds with one.

What is written is ``<name>.inp``, which reads
``<name>_from_crystal_builder.xyz`` beside it by ``*xyzfile``.  Not
``<name>.xyz``: that is the name ORCA writes an optimised geometry
to, over the file it started from, and the structure that was handed
to it is then gone and a second run starts somewhere else.  The line
takes the name **unquoted** and has **no closing asterisk** -- either
is an ORCA input error -- so the name is made of characters that need
no quotes.

**TD-DFT beside an optimisation or frequencies is two different
questions**, and ORCA answers only one of them by default: with a
``%tddft`` block, ``Opt`` and ``Freq`` follow the excited state IRoot
(manual, section 5.6.16).  A UV-Vis spectrum of the relaxed structure
is the other one -- the ground state optimised, then the excitations
at that geometry -- and is written as a ``%compound`` job of two
steps, the second taking the first's geometry.  ``tddft_state`` says
which; ``"ground"`` is the default because it is what a spectrum
usually means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from xtal.core import bonding, p1
from xtal.core import elements as el
from xtal.orca import catalogue


@dataclass
class OrcaInput:
    """Everything the ``!`` line and the blocks are written from.

    ``None`` or ``""`` is ORCA's own default, which writes nothing.
    """

    functional: str = catalogue.DEFAULT_FUNCTIONAL
    basis: str = catalogue.DEFAULT_BASIS
    dispersion: str = ""
    ri: str = ""
    scf_threshold: str = ""
    scf_solver: str = ""
    run: str = "sp"                 # "sp" | "opt" | "optts"
    opt_level: str = "Opt"
    cartesian: bool = False         # COpt
    freq: bool = False
    max_iter: int | None = None     # %geom
    calc_hess: bool = False         # %geom, for OptTS
    scf_max_iter: int | None = None  # %scf
    scf_guess: str = ""             # %scf
    tddft_nroots: int = 0           # 0 is no %tddft block
    tddft_triplets: bool = False
    #: With an optimisation or frequencies: the ground state then the
    #: spectrum ("ground", two steps), or excited state ``tddft_iroot``
    #: itself ("excited", one step).
    tddft_state: str = "ground"
    tddft_iroot: int = 1
    tddft_iroot_triplet: bool = False
    solvation: str = ""             # "" | "CPCM" | "SMD"
    solvent: str = "water"
    nprocs: int = 1                 # %pal, only above one
    maxcore_mb: int | None = None   # %maxcore
    charge: int = 0
    multiplicity: int = 1
    extra_keywords: str = ""
    extra_blocks: str = ""


@dataclass
class Cluster:
    """The atoms ORCA is given, in angstrom."""

    elements: list[str]
    cart: np.ndarray
    #: Pieces that close on their own image: a framework, a chain, a
    #: sheet.  Written as cut from the cell, never made whole.
    periodic_pieces: int = 0
    partial: int = 0                # atoms of occupancy below one
    markers: int = 0                # dummy atoms left out
    atoms: list[int] = field(default_factory=list)  # their cell indices

    @property
    def n_atoms(self) -> int:
        return len(self.elements)


def cluster(structure, atoms=None) -> Cluster:
    """Every atom of the cell -- or of ``atoms``, cell indices -- with
    molecules made whole by the stored bonds.

    Read off the stored graph and never perceived: what is whole is
    what the person's bonds say is one molecule.  Markers are left
    out here rather than by removing their sites, because that would
    renumber the cell under a selection made over it.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    wanted = range(cell.n_atoms) if atoms is None else \
        sorted({int(a) for a in atoms if 0 <= int(a) < cell.n_atoms})
    keep = [a for a in wanted if not el.is_dummy(cell.elements[a])]
    markers = len(wanted) - len(keep)
    offsets = {a: np.zeros(3) for a in keep}
    periodic = 0
    if atoms is None:
        for piece in graph.fragments():
            periodic += piece.periodic
            for a in piece.atoms:
                if a in offsets:
                    offsets[a] = np.asarray(piece.offsets[a], float)
    else:
        for a, shift in graph.unwrap(keep).items():
            offsets[a] = np.asarray(shift, float)
        chosen = set(keep)
        periodic = sum(1 for piece in graph.fragments()
                       if piece.periodic and set(piece.atoms) <= chosen)
    frac = np.array([cell.frac[a] + offsets[a] for a in keep]) \
        .reshape(-1, 3)
    return Cluster(
        elements=[_symbol(cell.elements[a]) for a in keep],
        cart=cell.lattice.to_cart(frac) if keep else np.zeros((0, 3)),
        periodic_pieces=int(periodic),
        partial=int(sum(1 for a in keep if cell.occupancy[a] < 1.0)),
        markers=markers, atoms=keep)


def _symbol(element: str) -> str:
    # ORCA knows hydrogen, not deuterium, by symbol; the mass is the
    # %coords block's business, and nobody asked for it here.
    return "H" if element in ("D", "T") else element


def electrons(elements, charge: int) -> int:
    return sum(el.atomic_number(e) for e in elements) - int(charge)


def check_spin(n_electrons: int, multiplicity: int) -> str:
    """Why this multiplicity cannot be, or ``""`` when it can."""
    if n_electrons < 0:
        return (f"The charge leaves {n_electrons} electrons; "
                f"it can be at most the sum of the atomic numbers")
    if multiplicity < 1:
        return "The multiplicity is 2S+1 and is at least 1"
    if multiplicity > n_electrons + 1:
        return (f"{n_electrons} electrons allow a multiplicity of at "
                f"most {n_electrons + 1}; {multiplicity} was given")
    if (n_electrons + multiplicity) % 2 == 0:
        parity, first = ("an odd", 1) if n_electrons % 2 == 0 \
            else ("an even", 2)
        return (f"{n_electrons} electrons need {parity} multiplicity "
                f"({first}, {first + 2}, ...); {multiplicity} was given")
    return ""


SPIN_NAMES = {1: "singlet", 2: "doublet", 3: "triplet", 4: "quartet",
              5: "quintet", 6: "sextet", 7: "septet"}


def describe(n_electrons: int, multiplicity: int) -> str:
    """ "143 electrons, doublet" """
    name = SPIN_NAMES.get(multiplicity, f"multiplicity {multiplicity}")
    return f"{n_electrons} electrons, {name}"


def follows_geometry(inp: OrcaInput) -> bool:
    """Whether the job moves or differentiates the geometry -- what a
    ``%tddft`` block turns into an excited-state question."""
    return inp.run != "sp" or bool(inp.freq)


def two_steps(inp: OrcaInput) -> bool:
    """The ground state optimised (or its frequencies), then the
    spectrum at that geometry: a ``%compound`` job."""
    return inp.tddft_nroots > 0 and follows_geometry(inp) \
        and inp.tddft_state == "ground"


def excited(inp: OrcaInput) -> bool:
    """One step that optimises excited state IRoot itself."""
    return inp.tddft_nroots > 0 and follows_geometry(inp) \
        and inp.tddft_state == "excited"


def problems(inp: OrcaInput, found: Cluster) -> tuple[list, list]:
    """``(refusals, cautions)``: what stops the file being written,
    and what it is written with but should be read first."""
    refusals: list[str] = []
    cautions: list[str] = []
    if found.n_atoms == 0:
        refusals.append("There are no atoms to write")
    functional = catalogue.functional(inp.functional)
    if functional is None:
        refusals.append(f"{inp.functional!r} is not one of ORCA's "
                        f"functionals")
    basis = catalogue.basis(inp.basis)
    own_basis = functional is not None and functional.own_basis
    if basis is None and not own_basis:
        refusals.append(f"{inp.basis!r} is not one of ORCA's basis sets")
    if found.n_atoms:
        why = check_spin(electrons(found.elements, inp.charge),
                         inp.multiplicity)
        if why:
            refusals.append(why)
    if inp.tddft_nroots < 0:
        refusals.append("The number of TD-DFT roots cannot be negative")
    if inp.tddft_nroots > 0 and functional is not None \
            and functional.key in catalogue.NO_TDDFT:
        refusals.append(f"ORCA has no TD-DFT with {functional.key}'s "
                        f"VV10 correlation; use its -D3BJ or -D4 "
                        f"variant")
    if excited(inp) and functional is not None \
            and functional.key not in catalogue.NO_TDDFT \
            and functional.key not in catalogue.EXCITED_GRADIENT:
        refusals.append(f"ORCA cannot follow an excited state with "
                        f"{functional.key} (no TD-DFT gradient for it); "
                        f"take the ground state then the spectrum, or "
                        f"e.g. PBE0, CAM-B3LYP or wB97X-D3")
    if excited(inp):
        if not 1 <= inp.tddft_iroot <= inp.tddft_nroots:
            refusals.append(f"IRoot {inp.tddft_iroot} is not one of "
                            f"the {inp.tddft_nroots} roots")
        if inp.tddft_iroot_triplet and not inp.tddft_triplets:
            refusals.append("A triplet IRoot needs the triplets "
                            "computed")
    if inp.solvation:
        solvent = catalogue.solvent(inp.solvent)
        if solvent is None:
            refusals.append(f"{inp.solvent!r} is not in ORCA's solvent "
                            f"list")
        elif not getattr(solvent, inp.solvation.lower()):
            refusals.append(f"{inp.solvation} has no parameters for "
                            f"{solvent.name}")
    if basis is not None and not own_basis and found.n_atoms:
        missing = sorted(set(found.elements) - basis.covers,
                         key=el.atomic_number)
        if missing:
            cautions.append(f"{basis.key} has no functions for "
                            f"{', '.join(missing)} (it covers "
                            f"{basis.elements})")
        if basis.relativistic:
            cautions.append(f"{basis.key} is contracted for "
                            f"{basis.relativistic}; add that keyword "
                            f"under More")
    if found.periodic_pieces:
        cautions.append(
            f"{found.periodic_pieces} piece"
            f"{'s are' if found.periodic_pieces > 1 else ' is'} "
            f"periodic (a framework, chain or sheet) and written as "
            f"cut from the cell, with dangling bonds")
    if found.partial:
        cautions.append(f"{found.partial} atoms are partly occupied and "
                        f"all are written; Prepare for simulation "
                        f"orders the disorder")
    if functional is not None:
        if inp.dispersion and functional.carries_dispersion:
            cautions.append(f"{functional.key} already includes "
                            f"dispersion; {inp.dispersion} counts it "
                            f"twice")
        if own_basis and inp.basis:
            cautions.append(f"{functional.key} brings its own basis "
                            f"set, so none is written")
        if functional.double_hybrid and inp.run != "sp" and inp.freq:
            cautions.append("Double-hybrid frequencies are numerical "
                            "and slow")
    if inp.run == "optts" and not inp.calc_hess:
        cautions.append("OptTS works best from an exact Hessian; "
                        "consider Calc_Hess")
    if excited(inp) and inp.freq:
        cautions.append("Excited-state frequencies are numerical: a "
                        "calculation per displacement")
    return refusals, cautions


def safe_name(stem: str) -> str:
    """A name ``*xyzfile`` can take unquoted."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return name or "structure"


def keywords(inp: OrcaInput, geometry: bool = True) -> list[str]:
    """The ``!`` line, in the order a person writes one; without the
    optimisation and frequencies for ``geometry=False``, the spectrum
    step of a two-step job."""
    functional = catalogue.functional(inp.functional)
    basis = catalogue.basis(inp.basis)
    own_basis = functional is not None and functional.own_basis
    words = [functional.key if functional else inp.functional]
    if inp.dispersion:
        words.append(inp.dispersion)
    if not own_basis:
        words.append(basis.key if basis else inp.basis)
    if inp.ri:
        words.append(inp.ri)
        if not own_basis and basis is not None and inp.ri != "NORI":
            if basis.def2:
                words.append("def2/JK" if inp.ri == "RIJK" else "def2/J")
            else:
                words.append("AutoAux")
    if functional is not None and functional.double_hybrid \
            and basis is not None:
        words.append(f"{basis.key}/C" if basis.key in
                     catalogue.C_AUXILIARY else "AutoAux")
    if inp.solvation == "CPCM" or inp.solvation == "SMD":
        solvent = catalogue.solvent(inp.solvent)
        name = solvent.name if solvent else inp.solvent
        if " " in name:
            words.append("CPCM")        # named in the %cpcm block
        else:
            words.append(f"{inp.solvation}({name})")
    words += [w for w in (inp.scf_threshold, inp.scf_solver) if w]
    if geometry:
        if inp.run == "opt":
            words.append(inp.opt_level)
        elif inp.run == "optts":
            words.append("OptTS")
        if inp.run != "sp" and inp.cartesian:
            words.append("COpt")
        if inp.freq:
            words.append("Freq")
    words += inp.extra_keywords.split()
    return list(dict.fromkeys(words))


def resources(inp: OrcaInput) -> list[str]:
    """%pal and %maxcore: the whole job's, never a step's."""
    out = []
    if inp.nprocs and inp.nprocs > 1:
        out.append(f"%pal\n  nprocs {inp.nprocs}\nend")
    if inp.maxcore_mb:
        out.append(f"%maxcore {inp.maxcore_mb}")
    return out


def blocks(inp: OrcaInput, geometry: bool = True,
           tddft: bool = True) -> list[str]:
    """The blocks of one step: %scf, %geom when it moves the
    geometry, %tddft when it computes the spectrum, %cpcm, the extras.
    """
    out = []
    scf = []
    if inp.scf_max_iter:
        scf.append(f"  MaxIter {inp.scf_max_iter}")
    if inp.scf_guess:
        scf.append(f"  Guess {inp.scf_guess}")
    if scf:
        out.append("%scf\n" + "\n".join(scf) + "\nend")
    if geometry and inp.run != "sp":
        geom = []
        if inp.max_iter:
            geom.append(f"  MaxIter {inp.max_iter}")
        if inp.calc_hess:
            geom.append("  Calc_Hess true")
        if geom:
            out.append("%geom\n" + "\n".join(geom) + "\nend")
    if tddft and inp.tddft_nroots > 0:
        lines = [f"  nroots {inp.tddft_nroots}",
                 f"  triplets {'true' if inp.tddft_triplets else 'false'}"]
        if excited(inp):
            lines.append(f"  iroot {inp.tddft_iroot}")
            if inp.tddft_iroot_triplet:
                lines.append("  irootmult triplet")
        out.append("%tddft\n" + "\n".join(lines) + "\nend")
    if inp.solvation:
        solvent = catalogue.solvent(inp.solvent)
        name = solvent.name if solvent else inp.solvent
        if " " in name:
            lines = ([f'  smd true\n  SMDsolvent "{name}"']
                     if inp.solvation == "SMD"
                     else [f'  solvent "{name}"'])
            out.append("%cpcm\n" + "\n".join(lines) + "\nend")
    if inp.extra_blocks.strip():
        out.append(inp.extra_blocks.strip())
    return out


def render(inp: OrcaInput, xyz_name: str, title: str = "") -> str:
    """The whole ``.inp``."""
    lines = []
    if title:
        lines.append(f"# {title}")
    # No closing "*": with *xyzfile that is an input error.
    coordinates = f"*xyzfile {inp.charge} {inp.multiplicity} {xyz_name}"
    if not two_steps(inp):
        lines += ["! " + " ".join(keywords(inp)), ""]
        for block in resources(inp) + blocks(inp):
            lines += [block, ""]
        lines.append(coordinates)
        return "\n".join(lines) + "\n"
    # A step with no coordinates of its own takes the geometry the
    # step before it ended on (manual, section 8, NewStep).
    for block in resources(inp):
        lines += [block, ""]
    lines += [coordinates, "", "%compound"]
    steps = (("Step 1: the ground state, " + (
                  "optimised" if inp.run != "sp" else "frequencies")
              + (" with frequencies" if inp.run != "sp" and inp.freq
                 else ""), True, False),
             ("Step 2: the excited states at that geometry", False,
              True))
    for comment, geometry, tddft in steps:
        lines += [f"  # {comment}", "  NewStep",
                  "  ! " + " ".join(keywords(inp, geometry=geometry))]
        for block in blocks(inp, geometry=geometry, tddft=tddft):
            lines += ["  " + line for line in block.splitlines()]
        lines.append("  StepEnd")
    lines.append("End")
    return "\n".join(lines) + "\n"


def xyz_text(found: Cluster, comment: str = "") -> str:
    """Plain XYZ, four columns: no cell, so no ``Lattice=``."""
    lines = [str(found.n_atoms), comment.replace("\n", " ")]
    for symbol, (x, y, z) in zip(found.elements, found.cart,
                                 strict=True):
        lines.append(f"{symbol:<3s} {x: 14.8f} {y: 14.8f} {z: 14.8f}")
    return "\n".join(lines) + "\n"
