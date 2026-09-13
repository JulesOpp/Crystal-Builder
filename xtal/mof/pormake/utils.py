"""I/O and geometry helpers shared across the PORMAKE pipeline.

This module collects the low-level utilities that translate between the
file formats PORMAKE consumes (``.cgd`` nets, building-block ``.xyz``
files) and the in-memory :class:`ase.Atoms` representation, plus small
geometric helpers used during assembly and a CIF writer for individual
molecules.

It also defines the module-level constant ``METAL_LIKE``: a list of
element symbols treated as "metal-like". It is used elsewhere to detect
which nodes correspond to metal clusters when classifying building
blocks, since metal nodes and organic linkers play different roles in a
Metal-Organic Framework.
"""

from pathlib import Path

import ase
import ase.io
import ase.neighborlist
import numpy as np

try:
    from ase.utils import natural_cutoffs
except Exception as e:
    e
    from ase.neighborlist import natural_cutoffs

from xtal.analysis.rcsr import space_group_operations
from xtal.core.lattice import Lattice
from xtal.core.neighbors import neighbor_pairs

from .log import logger

# Metal species.
METAL_LIKE = [
    "Li",
    "Be",
    "B",
    "Na",
    "Mg",
    "Al",
    "Si",
    "K",
    "Ca",
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Ga",
    "Ge",
    "As",
    "Rb",
    "Sr",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "In",
    "Sn",
    "Sb",
    "Te",
    "Cs",
    "Ba",
    "La",
    "Ce",
    "Pr",
    "Nd",
    "Pm",
    "Sm",
    "Eu",
    "Gd",
    "Tb",
    "Dy",
    "Ho",
    "Er",
    "Tm",
    "Yb",
    "Lu",
    "Hf",
    "Ta",
    "W",
    "Re",
    "Os",
    "Ir",
    "Pt",
    "Au",
    "Hg",
    "Tl",
    "Pb",
    "Bi",
    "Po",
    "Fr",
    "Ra",
    "Ac",
    "Th",
    "Pa",
    "U",
    "Np",
    "Pu",
    "Am",
    "Cm",
    "Bk",
    "Cf",
    "Es",
    "Fm",
    "Md",
    "No",
    "Lr",
]


def bound_values(x, eps=1e-4):
    """Nudge fractional coordinates away from the exact cell boundary.

    Values that sit essentially at 0 or 1 are pushed inward by ``eps``.
    Fractional coordinates lying exactly on a periodic boundary cause
    ambiguous wrapping and edge-case artifacts when neighbor lists are
    rebuilt, so this clamp keeps positions strictly inside ``(0, 1)``.

    Parameters
    ----------
    x : numpy.ndarray
        Array of fractional coordinates.
    eps : float, optional
        Minimum distance to keep from the 0 and 1 boundaries.

    Returns
    -------
    numpy.ndarray
        Coordinates with values near 0 replaced by ``eps`` and values
        near 1 replaced by ``1 - eps``.
    """
    x = np.where(np.abs(x - 0) < eps, np.full_like(x, 0 + eps), x)
    x = np.where(np.abs(x - 1) < eps, np.full_like(x, 1 - eps), x)

    return x


def covalent_neighbor_list(
    atoms, scale=1.2, neglected_species=[], neglected_indices=[]
):
    """Build a bonded neighbor list from scaled covalent radii.

    Wraps :func:`ase.neighborlist.neighbor_list` using per-atom cutoffs
    derived from ASE's natural (covalent) radii, scaled by ``scale`` so
    that atoms within roughly bonding distance are treated as
    neighbors. Selected species or indices can be excluded from bonding
    by zeroing their cutoff, which is useful for ignoring connection
    markers or specific atoms when inferring molecular bonds.

    Parameters
    ----------
    atoms : ase.Atoms
        Atoms to analyze.
    scale : float, optional
        Multiplier applied to each natural cutoff radius.
    neglected_species : list of str, optional
        Element symbols whose atoms should not form bonds.
    neglected_indices : list of int, optional
        Atom indices that should not form bonds.

    Returns
    -------
    tuple of numpy.ndarray
        The ``("ijD")`` neighbor-list arrays: first-atom indices,
        second-atom indices, and the distance vectors between them.
    """
    cutoffs = natural_cutoffs(atoms)
    cutoffs = [scale * c for c in cutoffs]
    # Remove radii to neglect them.
    species_indices = [
        i for i, a in enumerate(atoms) if a.symbol in neglected_species
    ]

    for i in neglected_indices + species_indices:
        cutoffs[i] = 0.0

    return ase.neighborlist.neighbor_list("ijD", atoms, cutoff=cutoffs)


# ======================================================================
#  EXPANDING A NET, WHICH USED TO COST 250 MB
# ======================================================================
#
# ``read_cgd`` below expanded its asymmetric unit with
# ``pymatgen.Structure.from_spacegroup``.  That one call was the only
# use of pymatgen in the whole of PORMAKE and it brought sympy, pandas,
# plotly and matplotlib with it -- about 250 MB.  These two functions
# replace it over gemmi, which this project already depends on.
#
# Both reproduce pymatgen's conventions deliberately rather than
# incidentally, because the result is not just a set of points: the
# order the sites come out in is the slot order of the topology, and
# ``Topology.node_indices``, the builder's block placement and
# ``xtal.mof.build._representatives`` are all indices into it.  See
# PROVENANCE.md.


def cell_from_parameters(a, b, c, alpha, beta, gamma):
    """Cell vectors from lengths and angles, as rows.

    The convention is ``pymatgen.Lattice.from_parameters``': **b** in
    the xy-half-plane fixed by the reciprocal angle gamma*, and **c**
    along z.  It is not ase's or gemmi's, and it is kept because the
    positions below are fractional and the cell is arbitrary anyway --
    matching means a vendored net is the same numbers as an upstream
    one rather than a rotation of them, which is what makes the two
    comparable at all.

    Parameters
    ----------
    a, b, c : float
        Cell lengths, in Angstrom.
    alpha, beta, gamma : float
        Cell angles, in degrees.

    Returns
    -------
    numpy.ndarray
        A ``(3, 3)`` array, one lattice vector per row.
    """
    alpha_r, beta_r, gamma_r = np.radians([alpha, beta, gamma])
    cos_alpha, cos_beta, cos_gamma = np.cos([alpha_r, beta_r, gamma_r])
    sin_alpha, sin_beta = np.sin([alpha_r, beta_r])

    value = (cos_alpha * cos_beta - cos_gamma) / (sin_alpha * sin_beta)
    # Rounding can push this a hair outside the domain of arccos.
    gamma_star = np.arccos(np.clip(value, -1.0, 1.0))

    return np.array([
        [a * sin_beta, 0.0, a * cos_beta],
        [-b * sin_alpha * np.cos(gamma_star),
         b * sin_alpha * np.sin(gamma_star),
         b * cos_alpha],
        [0.0, 0.0, float(c)],
    ])


def expand_asymmetric_unit(spacegroup, coords, tol=1e-5):
    """Apply a space group to each site, keeping the orbits in order.

    One orbit per input site, in input order, and within an orbit in
    the order the group's operations are listed -- which is what makes
    the returned array a slot list and not merely a point set.  A
    position is a duplicate when it is within ``tol`` of one already
    found, compared modulo one lattice translation, exactly as
    pymatgen's ``SpaceGroup.get_orbit`` compares them.

    Parameters
    ----------
    spacegroup : str
        Hermann-Mauguin symbol, as written in the ``.cgd`` file.
    coords : array_like
        Fractional coordinates of the symmetry-unique sites.
    tol : float, optional
        Fractional tolerance for calling two positions the same site.

    Returns
    -------
    positions : numpy.ndarray
        Every generated site, shape ``(n, 3)``, wrapped into the cell.
    sizes : list of int
        The length of each input site's orbit, so per-site properties
        can be repeated onto the expansion.
    """
    operations = space_group_operations(spacegroup)

    positions = []
    sizes = []
    for point in np.asarray(coords, dtype=float):
        orbit = []
        for rotation, translation in operations:
            image = np.mod(np.round(rotation @ point + translation, 10), 1.0)
            # Wrapping leaves 0 and 1 as separate numbers, so a
            # difference is only small once it is taken modulo one.
            if orbit:
                delta = np.abs(np.asarray(orbit) - image)
                delta -= np.round(delta)
                if (np.abs(delta) < tol).all(axis=1).any():
                    continue
            orbit.append(image)
        positions.extend(orbit)
        sizes.append(len(orbit))

    return np.array(positions), sizes


def read_cgd(filename, node_symbol="C", edge_center_symbol="O"):
    """Parse a ``.cgd`` net file into an :class:`ase.Atoms` topology.

    A ``.cgd`` file describes an abstract net by its space group, cell
    parameters, symmetry-unique node positions (with coordination
    numbers), and edges. This function expands the asymmetric unit by
    the space group via :mod:`gemmi`, places a placeholder atom at
    every node and edge center, removes symmetry-generated duplicates,
    and returns the result as an :class:`ase.Atoms` object that the rest
    of PORMAKE treats as the topology skeleton.

    Nodes are tagged with non-negative ``type`` values and edge centers
    with negative ones, and each site carries its coordination number
    ``cn`` so building blocks can later be matched by connectivity.

    Parameters
    ----------
    filename : str or pathlib.Path
        Path to the ``.cgd`` net file.
    node_symbol : str, optional
        Element symbol used as a placeholder for net nodes.
    edge_center_symbol : str, optional
        Element symbol used as a placeholder for edge centers.

    Returns
    -------
    ase.Atoms
        The topology, with ``tags`` encoding site types and ``info``
        holding the space group, name, and per-site coordination
        numbers.
    """
    with open(filename, "r") as f:
        # Neglect "CRYSTAL" and "END"
        lines = f.readlines()[1:-1]
    lines = [line for line in lines if not line.startswith("#")]

    # Get topology name.
    name = lines[0].split()[1]
    # Get spacegroup.
    spacegroup = lines[1].split()[1]

    # Get cell paremeters and expand cell lengths by 10.
    cellpar = np.array(lines[2].split()[1:], dtype=np.float32)

    # Parse node information.
    node_positions = []
    coordination_numbers = []
    for line in lines[3:]:
        tokens = line.split()

        if tokens[0] != "NODE":
            continue

        coordination_number = int(tokens[2])
        pos = [float(r) for r in tokens[3:]]
        node_positions.append(pos)
        coordination_numbers.append(coordination_number)

    node_positions = np.array(node_positions)
    # coordination_numbers = np.array(coordination_numbers)

    # Parse edge information.
    edge_center_positions = []
    for line in lines[3:]:
        tokens = line.split()

        if tokens[0] != "EDGE":
            continue

        pos_i = np.array([float(r) for r in tokens[1:4]])
        pos_j = np.array([float(r) for r in tokens[4:]])

        edge_center_pos = 0.5 * (pos_i + pos_j)
        edge_center_positions.append(edge_center_pos)

    # New feature. Read EDGE_CENTER.
    for line in lines[3:]:
        tokens = line.split()

        if tokens[0] != "EDGE_CENTER":
            continue

        edge_center_pos = np.array([float(r) for r in tokens[1:]])
        edge_center_positions.append(edge_center_pos)

    edge_center_positions = np.array(edge_center_positions)

    # Carbon for nodes, oxygen for edges.
    n_nodes = node_positions.shape[0]
    n_edges = edge_center_positions.shape[0]
    species = np.concatenate(
        [
            np.full(shape=n_nodes, fill_value=node_symbol),
            np.full(shape=n_edges, fill_value=edge_center_symbol),
        ]
    )

    coords = np.concatenate([node_positions, edge_center_positions], axis=0)

    # Pymatget can handle : indicator in spacegroup.
    # Mark symmetrically equivalent sites.
    node_types = [i for i, _ in enumerate(node_positions)]
    edge_types = [-(i + 1) for i, _ in enumerate(edge_center_positions)]
    site_properties = {
        "type": node_types + edge_types,
        "cn": coordination_numbers + [2 for _ in edge_center_positions],
    }

    # Neither pymatgen nor gemmi parses this one under its old name.
    if spacegroup == "Cmca":
        spacegroup = "Cmce"

    cell = cell_from_parameters(*cellpar)
    all_coords, orbit_sizes = expand_asymmetric_unit(spacegroup, coords)

    all_species = np.repeat(species, orbit_sizes)
    all_types = np.repeat(site_properties["type"], orbit_sizes)
    all_cn = np.repeat(site_properties["cn"], orbit_sizes)

    # Add information.
    info = {
        "spacegroup": spacegroup,
        "name": name,
        "cn": [int(v) for v in all_cn],
    }

    atoms = ase.Atoms(
        symbols=list(all_species),
        positions=all_coords @ cell,
        cell=cell,
        tags=[int(v) for v in all_types],
        pbc=True,
        info=info,
    )

    # Remove overlap.  A KD-tree over the cell and its neighbouring
    # images, not ase's neighbor_list: a 0.1 cutoff on a net cell whose
    # edges are about one unit long makes ase bin the cell into a
    # hundred thousand boxes and resize its arrays per box -- 3.9 s of
    # the 4.0 s naz-x took to read, on the path a build waits on.  The
    # pairs are the same (each once, i < j, overlaps at zero distance
    # included), which the comparison in PROVENANCE.md measured.
    pairs = neighbor_pairs(all_coords, Lattice(np.asarray(cell)), 0.1,
                           min_distance=0.0)
    # Remove higher index.
    J = pairs.j[pairs.j > pairs.i]
    if len(J) > 0:
        # Save original size of atoms.
        n = len(atoms)
        removed_indices = set(J)

        del atoms[list(removed_indices)]

        cn = atoms.info["cn"]
        # Remove old cn info.
        cn = [cn[i] for i in range(n) if i not in removed_indices]

        atoms.info["cn"] = cn

        logger.debug("Overlapped positions are removed: index %s", set(J))

    return atoms


def read_budiling_block_xyz(bb_file):
    """Parse a building-block ``.xyz`` file into an :class:`ase.Atoms`.

    Reads an extended ``.xyz`` describing a molecular building block:
    each atom line carries an element symbol, Cartesian position, and an
    optional partial charge. Dummy ``"X"`` atoms mark the connection
    points where the fragment attaches to neighboring blocks, and their
    indices are recorded so the assembly step can align them onto a
    topology slot. Any lines beyond the atom block are parsed as bonds
    (atom-index pairs plus a bond type) for CIF export.

    Parameters
    ----------
    bb_file : str or pathlib.Path
        Path to the building-block ``.xyz`` file.

    Returns
    -------
    ase.Atoms
        The building block, whose ``info`` dict holds the connection
        point indices (``"cpi"``), name, and optional ``bonds`` and
        ``bond_types``. Per-atom partial charges are stored as the
        atoms' initial charges.

    Notes
    -----
    The misspelled function name (``budiling``) is intentional and kept
    for backward compatibility.
    """
    name = Path(bb_file).stem

    with open(bb_file, "r") as f:
        lines = f.readlines()

    n_atoms = int(lines[0])

    symbols = []
    positions = []
    charges = []
    connection_point_indices = []
    for i, line in enumerate(lines[2 : n_atoms + 2]):
        tokens = line.split()
        symbol = tokens[0]
        position = [float(v) for v in tokens[1:4]]
        if len(tokens) == 5:
            charge = float(tokens[4])
        else:
            charge = 0.0

        symbols.append(symbol)
        positions.append(position)
        charges.append(charge)
        if symbol == "X":
            connection_point_indices.append(i)

    bonds = None
    bond_types = None
    if len(lines) > n_atoms + 2:
        logger.debug("There are bonds in building block xyz. Reading...")
        bonds = []
        bond_types = []

        for line in lines[n_atoms + 2 :]:
            tokens = line.split()
            if len(tokens) < 3:
                logger.debug("%s: len(line.split()) < 3 %s", bb_file, line)
                continue

            i = int(tokens[0])
            j = int(tokens[1])
            t = tokens[2]
            bonds.append((i, j))
            bond_types.append(t)
        bonds = np.array(bonds)

    info = {}
    info["cpi"] = connection_point_indices
    info["name"] = name
    info["bonds"] = bonds
    info["bond_types"] = bond_types

    atoms = ase.Atoms(symbols=symbols, positions=positions, charges=charges, info=info)

    return atoms


def write_molecule_cif(filename, atoms, bond_pairs, bond_types):
    """Write a single molecule to a P1 CIF file with bonds.

    Places the molecule, centered on its center of mass, inside a cubic
    ``P1`` cell sized to comfortably enclose it, then writes fractional
    coordinates, partial charges, and the supplied bond list. This is
    used to export an individual building block or fragment for
    inspection in crystallographic viewers.

    Parameters
    ----------
    filename : str or pathlib.Path
        Output path; a ``.cif`` suffix is enforced.
    atoms : ase.Atoms
        The molecule to write.
    bond_pairs : list of tuple of int
        Bonded atom-index pairs ``(i, j)``.
    bond_types : list of str
        Bond type for each pair, one of ``"S"``, ``"D"``, ``"T"``, or
        ``"A"`` (single, double, triple, aromatic).

    Returns
    -------
    None
    """

    path = Path(filename).resolve()
    if path.suffix != ".cif":
        path = path.with_suffix(".cif")

    stem = path.stem.replace(" ", "_")
    with path.open("w") as f:
        f.write("data_{}\n".format(stem))

        f.write("_symmetry_space_group_name_H-M    P1\n")
        f.write("_symmetry_Int_Tables_number       1\n")
        f.write("_symmetry_cell_setting            triclinic\n")

        f.write("loop_\n")
        f.write("_symmetry_equiv_pos_as_xyz\n")
        f.write("'x, y, z'\n")

        # Calculate cell parameters.
        positions = atoms.get_positions()
        com = atoms.get_center_of_mass()

        distances = np.linalg.norm(positions - com, axis=1)
        max_distances = np.max(distances)

        box_length = 2 * max_distances + 4

        f.write("_cell_length_a     {:.3f}\n".format(box_length))
        f.write("_cell_length_b     {:.3f}\n".format(box_length))
        f.write("_cell_length_c     {:.3f}\n".format(box_length))
        f.write("_cell_angle_alpha  90.0\n")
        f.write("_cell_angle_beta   90.0\n")
        f.write("_cell_angle_gamma  90.0\n")

        f.write("loop_\n")
        f.write("_atom_site_label\n")
        f.write("_atom_site_type_symbol\n")
        f.write("_atom_site_fract_x\n")
        f.write("_atom_site_fract_y\n")
        f.write("_atom_site_fract_z\n")
        f.write("_atom_type_partial_charge\n")

        # Get fractional coordinates
        # fractional coordinate of C.O.M is (0.5, 0.5, 0.5).
        symbols = atoms.get_chemical_symbols()
        charges = atoms.get_initial_charges()
        fracts = (positions - com) / box_length + 0.5

        # Write label and pos information.
        for i, (sym, fract, charge) in enumerate(zip(symbols, fracts, charges)):
            label = "{}{}".format(sym, i)
            f.write(
                "{} {} {:.5f} {:.5f} {:.5f} {:.5f}\n".format(label, sym, *fract, charge)
            )

        # Write bonds information.
        f.write("loop_\n")
        f.write("_geom_bond_atom_site_label_1\n")
        f.write("_geom_bond_atom_site_label_2\n")
        f.write("_geom_bond_distance\n")
        f.write("_geom_bond_site_symmetry_2\n")
        f.write("_ccdc_geom_bond_type\n")

        for (i, j), t in zip(bond_pairs, bond_types):
            label_i = "{}{}".format(symbols[i], i)
            label_j = "{}{}".format(symbols[j], j)

            distance = np.linalg.norm(positions[i] - positions[j])

            f.write("{} {} {:.3f} . {}\n".format(label_i, label_j, distance, t))
