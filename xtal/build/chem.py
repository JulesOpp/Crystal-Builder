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

The one honest caveat is sterics: a hydrogen is smaller than the
carboxylate it stands in for, so a crowded ortho-substituted linker
relaxes a little more open than it would with its real neighbours.
The user relaxes further with the tools already here; guessing at the
substituent would be worse than being slightly loose.
"""

from __future__ import annotations

import importlib.util

import numpy as np

from xtal.mof.block import pull_in

MISSING = ("RDKit is not installed, so there is nothing to build a "
           "molecule from -- pip install 'crystal-builder[build]'")

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
    conformer = _conformer(Chem, AllChem, mol, dummies, seed, optimise)

    symbols = [CONNECTION if atom.GetAtomicNum() == 0
               else atom.GetSymbol() for atom in mol.GetAtoms()]
    cart = np.array(conformer.GetPositions(), dtype=float)
    cart = cart - cart.mean(axis=0)
    bonds = tuple(
        (bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(),
         _ORDERS.get(str(bond.GetBondType()), 1.0))
        for bond in mol.GetBonds())
    connections = tuple(dummies)
    return (tuple(symbols), pull_in(cart, bonds, connections), bonds,
            connections)


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
    hydrogens, and hand back its coordinates."""
    capped = Chem.RWMol(mol)
    for index in dummies:
        atom = capped.GetAtomWithIdx(index)
        atom.SetAtomicNum(1)
        atom.SetAtomMapNum(0)
        atom.SetNoImplicit(True)
    capped = capped.GetMol()
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
    return capped.GetConformer()


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
