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

**A metal is put on its shape before anything else is placed.**
ETKDG has no coordination chemistry, so a molecule with a metal in it
is embedded with the metal and the atoms bonded to it pinned to a
polyhedron (:mod:`xtal.build.coordination`): directly for one metal,
both ends together for a metal-metal bond, round the shared atom for a
mu-oxo cluster, and as distance bounds otherwise.  The angles are
measured afterwards; the relax is our UFF4MOF with the shape held.  A
metal with one bond, or more than any shape has, has no shape and is
embedded as the organic part is.  **A drawing its shapes cannot take
is still built** -- a metal in a four-membered ring cannot be
tetrahedral -- as near as it will go, relaxed with nothing held, and
the build says so in ``notes`` rather than refusing: what was drawn is
what the person wants, and a refusal left them nothing to look at.  A
molecule with no metal never reaches any of it.

The one honest caveat is sterics: a hydrogen is smaller than the
carboxylate it stands in for, so a crowded ortho-substituted linker
relaxes a little more open than it would with its real neighbours.
The user relaxes further with the tools already here; guessing at the
substituent would be worse than being slightly loose.
"""

from __future__ import annotations

import importlib.util
import itertools
import math

import numpy as np

from xtal import install
from xtal.mof.block import pull_in
from xtal.params import Availability

NOT_INSTALLED = Availability(
    False, "RDKit is not installed, so there is nothing to build a "
           "molecule from", install.command("build"))
MISSING = NOT_INSTALLED.reason

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


def embed(smiles: str, seed: int = 0xf00d, optimise: bool = True,
          notes: list | None = None):
    """``(symbols, cart, bonds, connections)`` for one SMILES string.

    ``cart`` is centroid-centred, matching
    :meth:`xtal.commands.clipboard.Fragment.from_selection`, so the
    result drops straight into a paste.  ``bonds`` are ``(i, j,
    order)`` in local indices and ``connections`` indexes the ``X``
    atoms in the order their ``[*:n]`` map numbers ask for.

    ``notes``, given a list, is told what the build had to give up --
    a metal whose shape the drawing could not take -- in a sentence
    for a person.

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
    cart = _conformer(Chem, AllChem, mol, dummies, seed, optimise,
                      [] if notes is None else notes)

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


def _conformer(Chem, AllChem, mol, dummies, seed, optimise, notes):
    """Embed and relax a copy in which the connection points are
    hydrogens, and hand back the coordinates of ``mol``'s atoms.

    A point with several members keeps its own atom as the hydrogen on
    the first and gains one on each of the others, appended after
    every atom of ``mol`` so no index of it moves; their positions are
    read back to place the point and then dropped.
    """
    ladder = _ladder_caps(Chem, mol, dummies)
    if ladder is not None:
        return _embedded(Chem, AllChem, mol, *ladder, seed, optimise,
                         notes)
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
    cart = _coordinates(Chem, AllChem, mol, capped, seed, optimise,
                        notes)
    points = set(dummies)
    for index, pairs in caps.items():
        if len(pairs) > 1:
            members = [m for m, _ in pairs]
            outward = np.mean([_away(mol, cart, m, points)
                               for m in members], axis=0)
            cart[index] = cart[members].mean(axis=0) + outward
    return cart[:mol.GetNumAtoms()]


def _coordinates(Chem, AllChem, mol, capped, seed, optimise, notes):
    """Sanitize, embed and relax ``capped``; its positions."""
    try:
        Chem.SanitizeMol(capped)
    except (ValueError, RuntimeError) as exc:
        raise BuildError(f"{Chem.MolToSmiles(mol)} will not sanitize: "
                         f"{exc}") from None

    centres = _metal_centres(Chem, capped, notes)
    if centres:
        return _metal_coordinates(Chem, capped, centres, seed, optimise,
                                  notes)
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


# ======================================================================
#  METALS: put on their shape first, the rest grown round them
# ======================================================================

#: How far a built metal's angles may stray from its shape before the
#: build says so rather than hands it over (degrees).
SHAPE_TOLERANCE = 5.0
#: The same for a metal bonded to another metal.  The metal-metal
#: direction is never pinned -- a paddlewheel's Cu sits 0.2 A out of
#: its O4 plane in every crystal, so O-Cu-Cu is 84 degrees and pinning
#: it at 90 asks acetate's O...O bite for 2.6 A -- and the trans
#: angles that leaves are 168-170.
BRIDGED_TOLERANCE = 15.0


def _metal_centres(Chem, mol, notes: list | None = None) -> list:
    """``(metal, neighbours, shape, vertex_of, bridged)`` for every
    metal of the
    molecule, its shape the drawing's own or the default.  Empty for
    an organic molecule, which then embeds exactly as it always has.

    A metal with one bond has no geometry to keep, and one with more
    bonds than any shape has corners (a sandwich) none we know, so
    neither is a centre: they are embedded as the organic part is.  A
    shape chosen for another number of bonds -- the drawing changed
    after the right-click -- gives way to the default, and ``notes``
    says so.
    """
    from xtal.build import coordination
    from xtal.build.sketch import is_metal

    centres = []
    placed: dict = {}                   # donor -> (metal, its vector)
    for atom in mol.GetAtoms():
        if not is_metal(atom.GetSymbol()):
            continue
        neighbours = [n.GetIdx() for n in atom.GetNeighbors()]
        metals = [k for k, n in enumerate(neighbours)
                  if is_metal(mol.GetAtomWithIdx(n).GetSymbol())]
        shape = (atom.GetProp(SHAPE_PROP) if atom.HasProp(SHAPE_PROP)
                 else "")
        if len(neighbours) < 2:
            continue
        if shape and (shape not in coordination.SHAPES or len(
                coordination.SHAPES[shape][1]) != len(neighbours)):
            if notes is not None:
                notes.append(
                    f"{atom.GetSymbol()} was made "
                    f"{shape.replace('_', ' ')} but has "
                    f"{len(neighbours)} bonds, so it was built with "
                    f"the shape for that many")
            shape = ""
        if not shape:
            shape = coordination.default_shape(
                atom.GetSymbol(), len(neighbours), len(metals))
        if shape is None:
            if notes is not None:
                notes.append(
                    f"{atom.GetSymbol()} has {len(neighbours)} bonds, "
                    f"more than any shape here, so it was built "
                    f"without one")
            continue
        chelated = [(a, b) for a, b in _pairs(len(neighbours))
                    if _through_ligand(mol, neighbours[a], neighbours[b],
                                       atom.GetIdx())]
        wanted = _across_bridges(mol, neighbours, placed)
        vertex_of = coordination.assign(shape, chelated, metals, wanted)
        vectors = coordination.SHAPES[shape][1]
        for k, n in enumerate(neighbours):
            if k not in metals:
                placed[n] = (atom.GetIdx(), vectors[vertex_of[k]])
        centres.append((atom.GetIdx(), neighbours, shape, vertex_of,
                        frozenset(metals)))
    return centres


def _across_bridges(mol, neighbours, placed) -> dict:
    """``{(a, b): cosine}`` for pairs of this metal's donors bridged --
    O-C-O, two bonds through no metal -- to donors of one metal
    placed already: they should sit as their partners there do."""
    from xtal.build.sketch import is_metal

    partner = {}
    for k, donor in enumerate(neighbours):
        for middle in mol.GetAtomWithIdx(donor).GetNeighbors():
            if is_metal(middle.GetSymbol()):
                continue
            for far in middle.GetNeighbors():
                if far.GetIdx() != donor and far.GetIdx() in placed:
                    partner[k] = placed[far.GetIdx()]
    wanted = {}
    for a, b in _pairs(len(neighbours)):
        if a in partner and b in partner and \
                partner[a][0] == partner[b][0]:
            wanted[(a, b)] = float(partner[a][1] @ partner[b][1])
    return wanted


def _pairs(n):
    return [(a, b) for a in range(n) for b in range(a + 1, n)]


def _through_ligand(mol, a, b, metal, limit: int = 4) -> bool:
    """Whether ``a`` and ``b`` are joined within ``limit`` bonds without
    passing through the metal: one chelating ligand."""
    seen, frontier = {a}, {a}
    for _ in range(limit):
        nxt = set()
        for atom in frontier:
            for n in mol.GetAtomWithIdx(atom).GetNeighbors():
                k = n.GetIdx()
                if k == metal or k in seen:
                    continue
                if k == b:
                    return True
                nxt.add(k)
        seen |= nxt
        frontier = nxt
    return False


def _metal_coordinates(Chem, mol, centres, seed, optimise, notes):
    """Embed with every metal's neighbours on its shape.

    One metal: ETKDG with the metal and its donors pinned where the
    shape puts them -- exact angles on cisplatin, Fe(OH)6, Co(en)3.
    Where that cannot close a ring (Cu(en)2 measured -1) or there are
    several metals, whose places relative to one another nobody knows,
    the shapes go in as distances instead: each metal-donor bond and
    every donor-donor distance the shape implies, smoothed into the
    bounds ETKDG embeds from.  Either way the angles are measured.

    A molecule further than :data:`SHAPE_TOLERANCE` from its shapes
    is the closest attempt, or ETKDG's own geometry when no attempt
    embedded at all, relaxed with nothing held -- holding a shape the
    drawing cannot take only keeps the strain in -- and ``notes`` says
    which shapes were given up.  Only a molecule ETKDG cannot embed
    even without them is refused.
    """
    from rdkit.Chem import rdDistGeom


    attempts = []
    if len(centres) == 1:
        attempts.append("pinned")
    dimer = (_dimer_pins(Chem, mol, centres)
             or _hub_pins(Chem, mol, centres))
    if dimer is not None:
        attempts.append("dimer")
    attempts.append("bounds")
    bounds = _shape_bounds(Chem, mol, centres)
    worst, cart = math.inf, None
    for how in attempts:
        params = rdDistGeom.ETKDGv3()
        params.randomSeed = seed
        params.useRandomCoords = True
        params.ignoreSmoothingFailures = True
        if bounds is not None:
            params.SetBoundsMat(bounds)
        if how == "pinned":
            params.SetCoordMap(_pins(Chem, mol, centres))
        elif how == "dimer":
            params.SetCoordMap(dimer)
        elif bounds is None:
            continue
        if rdDistGeom.EmbedMolecule(mol, params) != 0:
            continue
        found = np.array(mol.GetConformer().GetPositions(), dtype=float)
        error = _shape_error(found, centres)
        if error < worst:
            worst, cart = error, found
        if error <= 0.0:
            break
    held = True
    if cart is None or worst > 0.0:
        off = (centres if cart is None
               else [c for c in centres if _shape_error(cart, [c]) > 0])
        names = ", ".join(sorted({
            f"{mol.GetAtomWithIdx(c[0]).GetSymbol()} "
            f"{c[2].replace('_', ' ')}" for c in off}))
        if cart is None:
            cart = _unshaped(mol, seed)
        if cart is None:
            raise BuildError(f"RDKit could not find a 3D geometry for "
                             f"{smiles_of(Chem, mol)}")
        held = False
        notes.append(
            f"this drawing does not fit {names}, so it was built as "
            f"near as it would go -- right-click a metal for another "
            f"shape")
    if optimise:
        cart = _relax_round_metals(mol, cart, centres, held)
    return cart


def _unshaped(mol, seed):
    """ETKDG's own geometry, no shape asked of any metal, or ``None``."""
    from rdkit.Chem import rdDistGeom

    for random in (False, True):
        params = rdDistGeom.ETKDGv3()
        params.randomSeed = seed
        params.useRandomCoords = random
        params.ignoreSmoothingFailures = True
        if rdDistGeom.EmbedMolecule(mol, params) == 0:
            return np.array(mol.GetConformer().GetPositions(),
                            dtype=float)
    return None


def _shape_error(cart, centres) -> float:
    """How far past its tolerance the worst metal is, in degrees;
    zero or less when every one is within it.  A metal neighbour's
    angles are not counted, because its direction is not pinned."""
    from xtal.build import coordination

    worst = -math.inf
    for metal, neighbours, shape, vertex_of, bridged in centres:
        keep = [k for k in range(len(neighbours)) if k not in bridged]
        if len(keep) < 2:
            continue
        error = coordination.angle_error(
            cart, metal, [neighbours[k] for k in keep], shape,
            [vertex_of[k] for k in keep])
        allowed = BRIDGED_TOLERANCE if bridged else SHAPE_TOLERANCE
        worst = max(worst, error - allowed)
    return 0.0 if worst == -math.inf else worst


def _pins(Chem, mol, centres):
    from rdkit.Geometry import Point3D

    from xtal.build import coordination

    (metal, neighbours, shape, vertex_of, _bridged), = centres
    vectors = coordination.SHAPES[shape][1]
    symbol = mol.GetAtomWithIdx(metal).GetSymbol()
    pins = {metal: Point3D(0.0, 0.0, 0.0)}
    for k, n in enumerate(neighbours):
        d = coordination.bond_length(
            symbol, mol.GetAtomWithIdx(n).GetSymbol())
        pins[n] = Point3D(*(vectors[vertex_of[k]] * d))
    return pins


#: How far a donor round a metal-metal bond leans towards the other
#: metal: O-Cu-Cu is 84-85 degrees in a paddlewheel, which is what
#: lets a carboxylate's 2.2 A bite span a 2.6 A Cu-Cu.
LEAN = math.radians(6.0)


def _dimer_pins(Chem, mol, centres):
    """Pins for two metals bonded to each other -- a paddlewheel --
    or ``None`` for anything else.

    The first metal's shape is laid out as it would be alone, with
    the donors at right angles to the metal-metal bond leaning
    :data:`LEAN` towards the other metal; the second metal goes along
    that bond, and each of its donors bridged to one of the first's
    is that donor's mirror image across the bond's midplane.  A donor
    of the second with no partner is left to the embedding.
    """
    from rdkit.Geometry import Point3D

    from xtal.build import coordination

    if len(centres) != 2:
        return None
    first, second = centres
    if second[0] not in first[1] or first[0] not in second[1]:
        return None
    m1, n1, shape1, vertex1, bridged1 = first
    m2, n2, _shape2, _vertex2, _bridged2 = second
    vectors = coordination.SHAPES[shape1][1]
    k_metal = n1.index(m2)
    axis = vectors[vertex1[k_metal]]
    s1 = mol.GetAtomWithIdx(m1).GetSymbol()
    s2 = mol.GetAtomWithIdx(m2).GetSymbol()
    d_mm = coordination.bond_length(s1, s2)
    where = {m1: np.zeros(3), m2: axis * d_mm}
    direction = {}
    for k, n in enumerate(n1):
        if k == k_metal:
            continue
        v = vectors[vertex1[k]]
        if abs(float(v @ axis)) < 1e-6:
            v = math.cos(LEAN) * v + math.sin(LEAN) * axis
        direction[n] = v / np.linalg.norm(v)
        where[n] = direction[n] * coordination.bond_length(
            s1, mol.GetAtomWithIdx(n).GetSymbol())
    for n in n2:
        if n == m1:
            continue
        partner = None
        for middle in mol.GetAtomWithIdx(n).GetNeighbors():
            for far in middle.GetNeighbors():
                if far.GetIdx() in direction and middle.GetIdx() != m2:
                    partner = far.GetIdx()
        if partner is None:
            continue
        v = direction[partner]
        mirrored = v - 2.0 * float(v @ axis) * axis
        where[n] = where[m2] + mirrored * coordination.bond_length(
            s2, mol.GetAtomWithIdx(n).GetSymbol())
    return {k: Point3D(*map(float, p)) for k, p in where.items()}


def _hub_pins(Chem, mol, centres):
    """Pins for metals that share one bridging atom -- Zn4O's central
    oxygen, a trimer's mu3-O -- or ``None`` for anything else.

    The shared atom is put at the origin with the metals on its own
    polyhedron (three trigonal, four tetrahedral), and each metal's
    shape is laid along its bond to it and turned about that bond, in
    5 degree steps, until its donors point as nearly as they can at
    the metals they bridge to -- which is where a carboxylate between
    two of them has to reach.
    """
    from rdkit.Geometry import Point3D

    from xtal.build import coordination

    if len(centres) < 3:
        return None
    metals = [c[0] for c in centres]
    shared = None
    for atom in mol.GetAtoms():
        around = {n.GetIdx() for n in atom.GetNeighbors()}
        if atom.GetIdx() not in metals and set(metals) <= around \
                and len(around) == len(metals):
            shared = atom.GetIdx()
    if shared is None:
        return None
    shape = {3: "trigonal_planar", 4: "tetrahedral",
             6: "octahedral"}.get(len(metals))
    if shape is None:
        return None
    hub = mol.GetAtomWithIdx(shared).GetSymbol()
    where = {shared: np.zeros(3)}
    for k, m in enumerate(metals):
        where[m] = coordination.SHAPES[shape][1][k] * \
            coordination.bond_length(mol.GetAtomWithIdx(m).GetSymbol(),
                                     hub)
    owner = {n: c[0] for c in centres for n in c[1] if n != shared}
    for index, (metal, neighbours, shape_m, vertex_of, bridged) in \
            enumerate(centres):
        vectors = coordination.SHAPES[shape_m][1]
        k_hub = neighbours.index(shared)
        back = -where[metal] / np.linalg.norm(where[metal])
        align = _rotation(vectors[vertex_of[k_hub]], back)
        aims = {}
        for k, n in enumerate(neighbours):
            if n == shared:
                continue
            for middle in mol.GetAtomWithIdx(n).GetNeighbors():
                for far in middle.GetNeighbors():
                    other = owner.get(far.GetIdx())
                    if other is not None and other != metal:
                        target = where[other] - where[metal]
                        aims[k] = target / np.linalg.norm(target)
        # Which donor on which corner is decided here, with the turn:
        # a corner's donor has to face the metal it bridges to, and
        # no assignment made without knowing where that metal is can.
        donors = [k for k in range(len(neighbours)) if k != k_hub]
        corners = [v for v in range(len(vectors))
                   if v != vertex_of[k_hub]]
        best, best_score = (align, vertex_of), -math.inf
        for step in range(72):
            turn = _rotation_about(back, math.radians(5.0 * step)) @ align
            turned = vectors @ turn.T
            for order in itertools.permutations(corners, len(donors)):
                score = sum(float(turned[v] @ aims[k])
                            for k, v in zip(donors, order, strict=True)
                            if k in aims)
                if score > best_score + 1e-9:
                    chosen = list(vertex_of)
                    for k, v in zip(donors, order, strict=True):
                        chosen[k] = v
                    best, best_score = (turn, chosen), score
        turn, vertex_of = best
        centres[index] = (metal, neighbours, shape_m, vertex_of, bridged)
        symbol = mol.GetAtomWithIdx(metal).GetSymbol()
        for k, n in enumerate(neighbours):
            if n == shared:
                continue
            where[n] = where[metal] + (turn @ vectors[vertex_of[k]]) * \
                coordination.bond_length(
                    symbol, mol.GetAtomWithIdx(n).GetSymbol())
    return {k: Point3D(*map(float, p)) for k, p in where.items()}


def _rotation(a, b) -> np.ndarray:
    """The rotation taking unit vector ``a`` onto unit vector ``b``."""
    a = np.asarray(a, float) / np.linalg.norm(a)
    b = np.asarray(b, float) / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        if c > 0:
            return np.eye(3)
        # Half a turn about any axis at right angles to a.
        ortho = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(ortho) < 1e-6:
            ortho = np.cross(a, [0.0, 1.0, 0.0])
        return _rotation_about(ortho / np.linalg.norm(ortho), math.pi)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k * (1.0 / (1.0 + c))


def _rotation_about(axis, angle: float) -> np.ndarray:
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]],
                  [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * k @ k


def _shape_bounds(Chem, mol, centres):
    """RDKit's distance bounds with each shape written into them, or
    ``None`` when they will not smooth.

    RDKit bounds a pair two or three bonds apart from the angles it
    guesses, and through a metal it guesses tetrahedral: square-planar
    Ni(CN)4's C-Ni-C at 90 degrees then contradicts its own N...N
    bounds and nothing smooths.  So every pair whose shortest path
    runs through a metal is first let go -- no closer than 1.0 A, no
    limit above -- and only the shape's own distances are written in;
    smoothing then derives the rest from those.
    """
    from rdkit.Chem import rdDistGeom
    from rdkit.DistanceGeometry import DoTriangleSmoothing

    from xtal.build import coordination

    bounds = rdDistGeom.GetMoleculeBoundsMatrix(mol)
    metals = {c[0] for c in centres}
    through = Chem.GetDistanceMatrix(mol, force=True)
    organic = Chem.RWMol(mol)
    for metal in sorted(metals, reverse=True):
        for n in [x.GetIdx() for x in
                  organic.GetAtomWithIdx(metal).GetNeighbors()]:
            organic.RemoveBond(metal, n)
    # force: RDKit caches the matrix on the molecule, and the copy
    # with the metal bonds removed would hand back the one with them.
    apart = Chem.GetDistanceMatrix(organic.GetMol(), force=True)
    n_atoms = mol.GetNumAtoms()
    for i in range(n_atoms):
        for j in range(i):
            if 1 < through[i, j] <= 4 and through[i, j] < apart[i, j]:
                bounds[i, j] = 1.0                  # lower, below
                bounds[j, i] = 1000.0               # upper, above

    def pin(i, j, d, slack):
        lo, hi = (i, j) if i < j else (j, i)
        bounds[hi, lo] = max(d - slack, 0.0)
        bounds[lo, hi] = d + slack

    for metal, neighbours, shape, vertex_of, bridged in centres:
        vectors = coordination.SHAPES[shape][1]
        symbol = mol.GetAtomWithIdx(metal).GetSymbol()
        lengths = [coordination.bond_length(
            symbol, mol.GetAtomWithIdx(n).GetSymbol()) for n in neighbours]
        for k, n in enumerate(neighbours):
            # A metal-metal bond's length is the loosest thing here:
            # Cu-Cu is 2.6 in a paddlewheel and 2.4 in a cluster, and
            # RDKit, with no radius it trusts, bounded it at 1.0.
            pin(metal, n, lengths[k], 0.3 if k in bridged else 0.02)
        for a, b in _pairs(len(neighbours)):
            u, v = vectors[vertex_of[a]], vectors[vertex_of[b]]
            if a in bridged or b in bridged:
                # Loose, not free: the shape's angle give or take the
                # tolerance, so the other metal is above the plane
                # and not over one of its own donors.
                ideal = math.acos(max(-1.0, min(1.0, float(u @ v))))
                swing = math.radians(BRIDGED_TOLERANCE)
                near, far = (_side(lengths[a], lengths[b], ideal + s)
                             for s in (-swing, swing))
                lo, hi = sorted((near, far))
                pin(neighbours[a], neighbours[b], (lo + hi) / 2,
                    (hi - lo) / 2)
                continue
            d = float(np.linalg.norm(u * lengths[a] - v * lengths[b]))
            pin(neighbours[a], neighbours[b], d, 0.05)
    if not DoTriangleSmoothing(bounds):
        return None
    return bounds


def _side(a: float, b: float, angle: float) -> float:
    """The third side of a triangle, by the law of cosines."""
    return math.sqrt(max(a * a + b * b - 2 * a * b * math.cos(angle),
                         0.0))


def _relax_round_metals(mol, cart, centres, hold: bool = True):
    """UFF4MOF -- ours, which has the metals RDKit's UFF lacks -- with
    every metal and its donors held, so the ligands relax and the
    shape stays the shape; nothing is held when the shape was given
    up.  Unrelaxed if it cannot be set up: the embedded geometry is
    already a sensible molecule."""
    from xtal.core import bonding, p1
    from xtal.core.lattice import Lattice
    from xtal.core.structure import Bond, Structure
    from xtal.ff import optimize
    from xtal.ff.api import CalculatorError
    from xtal.ff.registry import ENGINES

    symbols = [a.GetSymbol() if a.GetAtomicNum() else "H"
               for a in mol.GetAtoms()]
    span = float(np.ptp(cart, axis=0).max())
    lattice = Lattice.cubic(span + 20.0)
    centre = lattice.to_cart([0.5, 0.5, 0.5])
    shifted = cart - cart.mean(axis=0) + centre
    structure = Structure.from_arrays(
        lattice, symbols, lattice.to_frac(shifted), space_group="P1")
    for bond in mol.GetBonds():
        structure.add_bond(Bond(bond.GetBeginAtomIdx(),
                                bond.GetEndAtomIdx(), (0, 0, 0),
                                _ORDERS.get(str(bond.GetBondType()), 1.0)))
    # The bonds are the molecule's and no others: nothing perceived.
    structure.set_perceived(
        [], bonding.BondRules.from_dict(structure.bond_rules).signature(),
        p1.expand(structure))
    held = set()
    for metal, neighbours, *_rest in centres if hold else ():
        held.add(metal)
        held.update(neighbours)
    try:
        calculator = ENGINES.build("uff", structure)
        result = optimize.run(calculator, structure, method="lbfgs",
                              frozen=sorted(held), max_steps=500)
    except (CalculatorError, ValueError, RuntimeError):
        return cart
    relaxed = lattice.to_cart(np.asarray(result.frac, float))
    return relaxed - centre + cart.mean(axis=0)


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


def _embedded(Chem, AllChem, mol, capped, where, caps, seed, optimise,
              notes):
    """The coordinates of ``mol`` from a ladder-capped embedding: each
    point out from its members toward the copies standing in for the
    next unit."""
    cart = _coordinates(Chem, AllChem, mol, capped, seed, optimise,
                        notes)
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


# ======================================================================
#  THE SKETCH: a drawing to a string and back
# ======================================================================
#
# :mod:`xtal.build.sketch` holds no RDKit, so the two directions are
# here.  The string is CXSMILES: a plain SMILES when nothing but atoms
# and bonds was drawn -- every saved parameter still reads -- and an
# ``|atomProp:...|`` tail when a metal was given a shape by hand.

#: The atom property a hand-chosen metal shape rides under.
SHAPE_PROP = "xtal_shape"

_SKETCH_ORDERS = {"single": "SINGLE", "double": "DOUBLE",
                  "triple": "TRIPLE", "aromatic": "AROMATIC",
                  "dative": "DATIVE"}


def sketch_mol(sketch, sanitize: bool = True):
    """The RDKit molecule a drawing describes.

    Raises :class:`BuildError` saying why when it will not sanitize
    -- a ring drawn aromatic that has no Kekulé form, a carbon with
    five bonds -- because the canvas shows that sentence under the
    drawing.
    """
    if not installed():
        raise BuildError(MISSING)
    from rdkit import Chem, rdBase

    from xtal.build.sketch import CONNECTION as POINT
    from xtal.build.sketch import is_metal

    mol = Chem.RWMol()
    for atom in sketch.atoms:
        if atom.element == POINT:
            new = Chem.Atom(0)
            new.SetAtomMapNum(int(atom.map_number))
        else:
            new = Chem.Atom(atom.element)
            new.SetFormalCharge(int(atom.charge))
            if atom.hydrogens is not None or is_metal(atom.element):
                new.SetNumExplicitHs(int(atom.hydrogens or 0))
                new.SetNoImplicit(True)
            if atom.shape:
                new.SetProp(SHAPE_PROP, atom.shape)
        mol.AddAtom(new)
    for bond in sketch.bonds:
        kind = getattr(Chem.BondType, _SKETCH_ORDERS[bond.order])
        mol.AddBond(int(bond.a), int(bond.b), kind)
        if bond.order == "aromatic":
            mol.GetAtomWithIdx(bond.a).SetIsAromatic(True)
            mol.GetAtomWithIdx(bond.b).SetIsAromatic(True)
            mol.GetBondBetweenAtoms(bond.a, bond.b).SetIsAromatic(True)
    mol = mol.GetMol()
    if sanitize:
        with rdBase.BlockLogs():
            try:
                Chem.SanitizeMol(mol)
            except (ValueError, RuntimeError) as exc:
                raise BuildError(_sanitize_reason(exc)) from None
    return mol


def sketch_smiles(sketch) -> str:
    """The drawing as canonical CXSMILES, ``""`` for an empty page."""
    if not sketch.atoms:
        return ""
    from rdkit import Chem

    return Chem.MolToCXSmiles(sketch_mol(sketch))


def sketch_from_smiles(text: str):
    """A drawing of a string, laid out flat by RDKit.

    Hydrogens written as atoms stay atoms; ``[NH3]`` is an H count of
    three and a plain ``N`` is left to its valence, so the string the
    drawing writes back is the one it was given.
    """
    if not installed():
        raise BuildError(MISSING)
    from rdkit import Chem, rdBase
    from rdkit.Chem import rdDepictor

    from xtal.build.sketch import BOND, CONNECTION, Sketch

    text = str(text or "").strip()
    if not text:
        return Sketch()
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(text)
    if mol is None:
        raise BuildError(f"{text!r} is not a SMILES string RDKit can "
                         f"read")
    # Drawn as a chemist draws it: alternating single and double.
    # Sanitizing the drawing perceives the aromaticity again, so the
    # string written back is the one read.
    with rdBase.BlockLogs():
        try:
            Chem.Kekulize(mol, clearAromaticFlags=True)
        except (ValueError, RuntimeError):      # pragma: no cover
            pass
    rdDepictor.SetPreferCoordGen(True)
    rdDepictor.Compute2DCoords(mol)
    positions = mol.GetConformer().GetPositions()
    # The page draws a bond at BOND, whatever length the layout used:
    # RDKit's own is 1.5 and CoordGen's is not, and a drawing scaled
    # by the wrong one came out a third of the size.
    lengths = [np.linalg.norm(positions[b.GetBeginAtomIdx()]
                              - positions[b.GetEndAtomIdx()])
               for b in mol.GetBonds()]
    mean = float(np.mean(lengths)) if lengths else 1.5
    scale = BOND / (mean if mean > 1e-6 else 1.5)
    sketch = Sketch()
    for atom, (x, y, _z) in zip(mol.GetAtoms(), positions, strict=True):
        if atom.GetAtomicNum() == 0:
            k = sketch.add_atom(CONNECTION, x * scale, y * scale)
            sketch.atoms[k].map_number = atom.GetAtomMapNum()
            continue
        k = sketch.add_atom(atom.GetSymbol(), x * scale, y * scale)
        drawn = sketch.atoms[k]
        drawn.charge = atom.GetFormalCharge()
        if atom.GetNoImplicit():
            drawn.hydrogens = atom.GetNumExplicitHs()
        if atom.HasProp(SHAPE_PROP):
            drawn.shape = atom.GetProp(SHAPE_PROP)
    names = {v: k for k, v in _SKETCH_ORDERS.items()}
    for bond in mol.GetBonds():
        order = names.get(str(bond.GetBondType()), "single")
        sketch.bonds.append(_sketch_bond(bond, order))
    return sketch


def _sketch_bond(bond, order):
    from xtal.build.sketch import SketchBond

    return SketchBond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(),
                      order)


def canonical(text: str) -> str:
    """The string as RDKit would write it, or the string itself.

    Unchanged for anything unreadable, which is what makes this safe
    to compare with: two identical half-typed strings still match,
    and two different ones still differ.
    """
    text = str(text or "").strip()
    if not text or not installed():
        return text
    from rdkit import Chem, rdBase

    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(text)
    if mol is None:
        return text
    mol.RemoveAllConformers()
    # RDKit 2025.9 (the last with an Intel macOS wheel) labels every
    # parsed * as dummyLabel "*" and writes it into the CXSMILES; a
    # drawn point never has it, so the same molecule read two ways
    # gave two strings.  "*" is what a dummy is called anyway.
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 0 and atom.HasProp("dummyLabel") \
                and atom.GetProp("dummyLabel") == "*":
            atom.ClearProp("dummyLabel")
    return Chem.MolToCXSmiles(mol)


def _sanitize_reason(exc) -> str:
    """RDKit's complaint, said for a person drawing: which atom, and
    what is wrong with it."""
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    if "Explicit valence" in text or "valence" in text.lower():
        return f"too many bonds: {text}"
    if "kekulize" in text.lower():
        return ("a ring drawn aromatic has no alternating single and "
                f"double bonds: {text}")
    return text or "RDKit cannot make a molecule of this drawing"
