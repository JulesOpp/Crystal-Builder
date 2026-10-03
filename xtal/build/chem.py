"""
xtal.build.chem
===============
The RDKit half, and the only file that imports it.

Every ``import rdkit`` in this package is in here and is inside a
function, so that :func:`installed` can answer in microseconds and the
rest of the application can ask on every menu rebuild.  The module is
called ``chem`` and not ``rdkit`` deliberately: a module of that name
containing ``import rdkit`` is legal under absolute imports and is a
trap for whoever reads it next.

**A connection point is capped with hydrogen before anything touches
it.**  RDKit's MMFF has no parameters for an atom of atomic number
zero, so a molecule embedded and relaxed with ``*`` atoms still in it
either refuses to optimise or falls back silently.  Replacing each
``*`` with an H first makes it an ordinary organic molecule that ETKDG
and MMFF both handle with no special case, and costs nothing that
matters: a hydrogen points exactly where a substituent would, so the
direction that comes back is the direction the connection point wants,
and the direction is the whole of what a connection point carries.
The atoms are relabelled ``X`` and pulled in to
:data:`~xtal.mof.block.CONNECTION_DISTANCE` afterwards.

This is the fourth place markers are held back at the door rather than
refused -- :func:`xtal.ff.markers.hold_back`,
:func:`xtal.ff.hydrogens.plan` and
:func:`xtal.modules.job.without_dummies` are the other three -- and it
is the same argument each time.

**A connection point bonded to two atoms is capped on each of them.**
A chelating block and a ladder polymer's repeat (PIM-1's dioxin, a
Troger's base) meet the next unit through two atoms, and the ``*`` that
says so is bonded to both -- the convention
:func:`xtal.mof.attach.members_of` reads.  One hydrogen in its place
is a hydrogen with two bonds, which RDKit refuses ("Explicit valence
for atom H, 3"), so each member gets a hydrogen of its own and the
``X`` is put back at the members' centroid, out along the mean of the
directions away from the molecule at each.  **A ladder repeat** -- two
points of two members each -- is capped instead with a copy of the
other end's member path, which closes the ring the joint will close
(:func:`_ladder_caps` says why).  A ``*`` with one bond is capped
exactly as it always was.

The one honest caveat is sterics: a hydrogen is smaller than the
carboxylate it stands in for, so a crowded ortho-substituted linker
relaxes a little more open than it would with its real neighbours.
The user relaxes further with the tools already here; guessing at the
substituent would be worse than being slightly loose.
"""

from __future__ import annotations

import importlib.util

import numpy as np

from xtal import install
from xtal.mof.block import pull_in

MISSING = ("RDKit is not installed, so there is nothing to build a "
           f"molecule from -- {install.command('build')}")

#: RDKit bond type -> the order this application stores.  Aromatic
#: stays 1.5 rather than being kekulized, because
#: :data:`xtal.commands.bonds.BOND_TYPES` has an aromatic type and the
#: viewport draws it -- a benzene whose bonds alternate single and
#: double is a less faithful answer, not a more portable one.
_ORDERS = {"SINGLE": 1.0, "DOUBLE": 2.0, "TRIPLE": 3.0,
           "AROMATIC": 1.5}

#: What a connection point becomes.  The same symbol
#: :data:`xtal.mof.catalog.CONNECTION` uses, which is the point.
CONNECTION = "X"


class BuildError(ValueError):
    """A string that is not a molecule, or one that will not embed."""


def installed() -> bool:
    """Whether ``rdkit`` is importable -- without importing it.

    ``find_spec`` reads the package's location off the path and stops.
    That is the difference between a menu that greys an entry out in
    microseconds and one that stalls every time it is rebuilt.
    """
    try:
        return importlib.util.find_spec("rdkit") is not None
    except (ImportError, ValueError):           # pragma: no cover
        return False


def embed(smiles: str, seed: int = 0xf00d, optimise: bool = True):
    """``(symbols, cart, bonds, connections)`` for one SMILES string.

    ``cart`` is centroid-centred, matching
    :meth:`xtal.commands.clipboard.Fragment.from_selection`, so the
    result drops straight into a paste.  ``bonds`` are ``(i, j,
    order)`` in local indices and ``connections`` indexes the ``X``
    atoms in the order their ``[*:n]`` map numbers ask for.

    ``seed`` is fixed rather than random on purpose: a test that
    asserts a bond length has to get the same conformer every run, and
    a user who builds the same linker twice should get the same
    molecule.
    """
    if not installed():
        raise BuildError(MISSING)
    from rdkit import Chem, rdBase
    from rdkit.Chem import AllChem

    text = str(smiles).strip()
    if not text:
        raise BuildError("no SMILES string to build from")
    if _looks_like_xyz(text):
        # What a Copy from this application puts on the clipboard, in
        # the box that wants a SMILES string.  Quoted back as "not a
        # SMILES string RDKit can read" it is three lines of XYZ and no
        # advice; the two ways of turning atoms into a block are worth
        # naming instead, because the user already has the atoms.
        raise BuildError(
            "those are atoms copied from a structure, not a SMILES "
            "string -- draw the block here, or open the atoms in a "
            "tab, mark their connection points and use Save as a "
            "building block")

    # RDKit reports why a string failed to its own log and returns
    # None, so the reason has to be captured or the user is told only
    # that something did not work.
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(text)
    if mol is None:
        raise BuildError(f"{text!r} is not a SMILES string RDKit can "
                         f"read")

    dummies = _dummies(mol)
    # AddHs appends, so every index taken above stays valid and no
    # remapping is needed after this point.
    mol = Chem.AddHs(mol)
    cart = _conformer(Chem, AllChem, mol, dummies, seed, optimise)

    symbols = [CONNECTION if atom.GetAtomicNum() == 0
               else atom.GetSymbol() for atom in mol.GetAtoms()]
    cart = cart - cart.mean(axis=0)
    bonds = tuple(
        (bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(),
         _ORDERS.get(str(bond.GetBondType()), 1.0))
        for bond in mol.GetBonds())
    connections = tuple(dummies)
    return (tuple(symbols), pull_in(cart, bonds, connections), bonds,
            connections)


def stereocentres(smiles: str) -> int:
    """How many stereocentres a starred string has, its connection
    points told apart.

    Each ``*`` is given an isotope of its own first, in the order
    :func:`_dummies` reads them: two bare dummies are the same atom to
    RDKit, and the backbone carbon of ``[*:1]CC([*:2])C`` would then
    have two identical substituents and no hand at all.
    """
    if not installed():
        raise BuildError(MISSING)
    from rdkit import Chem

    mol = Chem.MolFromSmiles(str(smiles).strip())
    if mol is None:
        raise BuildError(f"{smiles!r} is not a SMILES string RDKit "
                         f"can read")
    for k, index in enumerate(_dummies(mol)):
        mol.GetAtomWithIdx(index).SetIsotope(k + 1)
    return len(Chem.FindMolChiralCenters(
        mol, includeUnassigned=True, useLegacyImplementation=False))


def _looks_like_xyz(text: str) -> bool:
    """Whether this is atoms rather than a string.

    An XYZ fragment starts with an atom count, and the box it gets
    pasted into is a single line -- which flattens the newlines, so the
    count, the comment and the first atom all arrive together.  Both
    forms answer to the same test: a leading whole number, and three
    numbers in a row somewhere after it.  No SMILES begins with a bare
    number, so this cannot swallow one.
    """
    tokens = text.split()
    if len(tokens) < 2:
        return False
    try:
        int(tokens[0])
    except ValueError:
        return False
    run = 0
    for token in tokens[1:]:
        try:
            float(token)
        except ValueError:
            run = 0
            continue
        run += 1
        if run >= 3:
            return True
    return False


def _dummies(mol) -> list[int]:
    """The connection points, in the order their map numbers ask for.

    Atomic number and not the symbol: RDKit spells a dummy ``*`` in
    SMILES, ``R`` or ``*`` in a molblock depending on the writer, and
    an empty string for some query atoms.  Zero is the one answer that
    is the same every way in.

    ``[*:1]`` and ``[*:2]`` let the user say which connection point is
    which, which matters because a slot is filled in order; an
    unnumbered ``*`` falls back on the order it was typed.
    """
    found = [(atom.GetAtomMapNum(), atom.GetIdx())
             for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0]
    numbered = [pair for pair in found if pair[0] > 0]
    if numbered and len(numbered) != len(found):
        raise BuildError(
            "number every connection point or none of them -- "
            f"{len(numbered)} of {len(found)} carry a map number, so "
            f"there is no order to put them in")
    return [index for _, index in sorted(found)]


def _conformer(Chem, AllChem, mol, dummies, seed, optimise):
    """Embed and relax a copy in which the connection points are
    hydrogens, and hand back the coordinates of ``mol``'s atoms.

    A point with several members keeps its own atom as the hydrogen on
    the first and gains one on each of the others, appended after
    every atom of ``mol`` so no index of it moves; their positions are
    read back to place the point and then dropped.
    """
    ladder = _ladder_caps(Chem, mol, dummies)
    if ladder is not None:
        return _embedded(Chem, AllChem, mol, *ladder, seed, optimise)
    capped = Chem.RWMol(mol)
    caps = {}
    for index in dummies:
        atom = capped.GetAtomWithIdx(index)
        atom.SetAtomicNum(1)
        atom.SetAtomMapNum(0)
        atom.SetNoImplicit(True)
        members = sorted(n.GetIdx() for n in atom.GetNeighbors())
        if len(members) > 1:
            # Written into a ring -- ``c1c[*]1`` -- RDKit may call the
            # point aromatic, and a hydrogen cannot be.
            atom.SetIsAromatic(False)
            bond = capped.GetBondBetweenAtoms(index, members[0])
            bond.SetBondType(Chem.BondType.SINGLE)
            bond.SetIsAromatic(False)
        caps[index] = [(members[0], index)] if members else []
        for member in members[1:]:
            capped.RemoveBond(index, member)
            hydrogen = capped.AddAtom(Chem.Atom(1))
            capped.AddBond(member, hydrogen, Chem.BondType.SINGLE)
            caps[index].append((member, hydrogen))
    capped = capped.GetMol()
    cart = _coordinates(Chem, AllChem, mol, capped, seed, optimise)
    points = set(dummies)
    for index, pairs in caps.items():
        if len(pairs) > 1:
            members = [m for m, _ in pairs]
            outward = np.mean([_away(mol, cart, m, points)
                               for m in members], axis=0)
            cart[index] = cart[members].mean(axis=0) + outward
    return cart[:mol.GetNumAtoms()]


def _coordinates(Chem, AllChem, mol, capped, seed, optimise):
    """Sanitize, embed and relax ``capped``; its positions."""
    try:
        Chem.SanitizeMol(capped)
    except (ValueError, RuntimeError) as exc:
        raise BuildError(f"{Chem.MolToSmiles(mol)} will not sanitize: "
                         f"{exc}") from None

    if AllChem.EmbedMolecule(capped, randomSeed=seed) != 0:
        # A ring system ETKDG cannot reach from its distance bounds
        # sometimes embeds from random coordinates instead, so this is
        # a second chance rather than a different algorithm.
        if AllChem.EmbedMolecule(capped, randomSeed=seed,
                                 useRandomCoords=True) != 0:
            raise BuildError("RDKit could not find a 3D geometry "
                             f"for {smiles_of(Chem, mol)}")
    if optimise:
        _relax(AllChem, capped)
    return np.array(capped.GetConformer().GetPositions(), dtype=float)


def _ladder_caps(Chem, mol, dummies):
    """``(capped, where, caps)`` for a ladder repeat, or ``None``.

    A repeat with exactly two connection points of two members each
    joins the next copy of itself through a ring: the tail's members,
    the path between the next head's members, and two bonds.  Capped
    with a hydrogen on each member that ring is open, and nothing
    holds the members where the ring would -- PIM-EA-TB's Troger's base
    came out with its nitrogen and methylene 3.8 A apart, where the
    closed bicycle has them 2.5 -- so no placement could bond both.
    Each end is capped instead with a copy of the *other* end's member
    path, closing the joint ring as the chain will, and the conformer
    is the one a unit inside a chain has.

    ``where`` maps each atom of ``mol`` but the points to its index in
    ``capped``; ``caps`` maps each point to the indices of the copied
    atoms bonded to its members.
    """
    if len(dummies) != 2:
        return None
    ends = []
    for index in dummies:
        members = sorted(n.GetIdx()
                         for n in mol.GetAtomWithIdx(index).GetNeighbors())
        if len(members) != 2:
            return None
        ends.append(members)
    kekule = Chem.Mol(mol)
    try:
        Chem.Kekulize(kekule, clearAromaticFlags=True)
    except (ValueError, RuntimeError):
        return None
    capped = Chem.RWMol(kekule)
    caps = {}
    for point, members, other in ((dummies[0], ends[0], ends[1]),
                                  (dummies[1], ends[1], ends[0])):
        path = _path(mol, other[0], other[1], set(dummies))
        if path is None:
            return None
        copies = []
        for atom in path:
            source = mol.GetAtomWithIdx(atom)
            copy = Chem.Atom(source.GetAtomicNum())
            copies.append(capped.AddAtom(copy))
        for k in range(len(path) - 1):
            order = kekule.GetBondBetweenAtoms(path[k], path[k + 1])
            capped.AddBond(copies[k], copies[k + 1], order.GetBondType())
        for member, copy in ((members[0], copies[0]),
                             (members[1], copies[-1])):
            capped.RemoveBond(point, member)
            capped.AddBond(member, copy, Chem.BondType.SINGLE)
        caps[point] = (copies[0], copies[-1])
    for point in sorted(dummies, reverse=True):
        capped.RemoveAtom(point)
    removed = sorted(dummies)

    def moved(index: int) -> int:
        return index - sum(1 for r in removed if r < index)

    where = {i: moved(i) for i in range(mol.GetNumAtoms())
             if i not in dummies}
    caps = {p: tuple(moved(c) for c in copies)
            for p, copies in caps.items()}
    capped = capped.GetMol()
    for atom in capped.GetAtoms():
        atom.SetNoImplicit(False)
    try:
        Chem.SanitizeMol(capped)
    except (ValueError, RuntimeError):
        return None
    return Chem.AddHs(capped), where, caps


def _path(mol, start: int, goal: int, avoid) -> tuple | None:
    """The shortest path of bonds from ``start`` to ``goal`` that
    passes through none of ``avoid`` -- RDKit's own would go through
    the connection point both members are bonded to."""
    before = {start: start}
    queue = [start]
    while queue and goal not in before:
        atom = queue.pop(0)
        for other in mol.GetAtomWithIdx(atom).GetNeighbors():
            k = other.GetIdx()
            if k not in before and k not in avoid:
                before[k] = atom
                queue.append(k)
    if goal not in before:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(before[path[-1]])
    return tuple(reversed(path))


def _embedded(Chem, AllChem, mol, capped, where, caps, seed, optimise):
    """The coordinates of ``mol`` from a ladder-capped embedding: each
    point out from its members toward the copies standing in for the
    next unit."""
    cart = _coordinates(Chem, AllChem, mol, capped, seed, optimise)
    out = np.zeros((mol.GetNumAtoms(), 3))
    for i, j in where.items():
        out[i] = cart[j]
    for point, copies in caps.items():
        members = [n.GetIdx()
                   for n in mol.GetAtomWithIdx(point).GetNeighbors()]
        middle = out[members].mean(axis=0)
        beyond = cart[list(copies)].mean(axis=0) - middle
        out[point] = middle + beyond / np.linalg.norm(beyond)
    return out


def _away(mol, cart, member: int, points) -> np.ndarray:
    """The unit direction out of the molecule at one member, judged
    one bond in: from the middle of its other neighbours to it.

    Not along its capping hydrogen: a catechol's two O-H turn to
    hydrogen-bond each other, and their mean put PIM-1's head 0.67 A
    from one oxygen and 2.08 from the other.
    """
    inner = [n.GetIdx() for n in mol.GetAtomWithIdx(member).GetNeighbors()
             if n.GetIdx() not in points]
    if not inner:
        return np.zeros(3)
    direction = cart[member] - cart[inner].mean(axis=0)
    return direction / np.linalg.norm(direction)


def _relax(AllChem, mol) -> None:
    """MMFF where it has the parameters, UFF where it does not, and
    the ETKDG geometry where neither does.

    Failing to relax is not failing to build: what ETKDG produces is
    already a chemically sensible molecule, and the user has a force
    field in the application to take it further.
    """
    try:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            AllChem.MMFFOptimizeMolecule(mol)
        elif AllChem.UFFHasAllMoleculeParams(mol):
            AllChem.UFFOptimizeMolecule(mol)
    except (ValueError, RuntimeError):          # pragma: no cover
        pass


def smiles_of(Chem, mol) -> str:
    """The canonical SMILES of a mol, for a message."""
    try:
        return Chem.MolToSmiles(mol)
    except (ValueError, RuntimeError):          # pragma: no cover
        return "the molecule"
