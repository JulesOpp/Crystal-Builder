"""
xtal.io.shelx
=============
SHELX ``.res``/``.ins`` files: read as a structure, and the PART each
atom was refined in.

A CIF from SHELXL usually carries the instruction file it was refined
from (``_shelx_res_file``, or ``_iucr_refine_instructions_details`` in
older ones), and that is where the disorder is written down as the
crystallographer meant it: ``PART 1`` and ``PART 2`` for the two
components, ``PART -1`` for a component lying on a symmetry element.
``_atom_site_disorder_group`` is SHELXL's copy of the same numbers, but
other programs drop or rewrite that column, and the instruction file
is the original.

A file opened on its own (:func:`read_shelx`) is read for the crystal
it describes -- cell, ``LATT`` and ``SYMM``, ``SFAC`` and the atoms --
and leaves its PARTs where a CIF's embedded file leaves them, so the
window makes the same groups of either.  What is refined (restraints,
weights, ``AFIX``) is not read, and nothing after ``HKLF`` is an atom.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import gemmi
import numpy as np

if TYPE_CHECKING:
    from xtal.core.structure import Structure

#: The tags a CIF puts its embedded instruction file under.
RES_TAGS = ("_shelx_res_file", "_iucr_refine_instructions_details")

#: Where the reader leaves :func:`site_parts`' answer, in
#: ``structure.meta``, for the window to make atom groups of.
PARTS_KEY = "shelx_parts"

#: SHELXL's instructions.  An atom line is told from one of these by
#: its first word, since ``UNIT 4 8 2 2 3`` has the shape of an atom
#: (a name, an integer, three numbers) as much as ``C1 1 0.1 0.2 0.3``.
INSTRUCTIONS = frozenset("""
    ABIN ACTA AFIX ANIS ANSC ANSR BASF BEDE BIND BLOC BOND BUMP CELL
    CGLS CHIV CONF CONN DAMP DANG DEFS DELU DFIX DISP EADP END EQIV
    EXTI EXYZ FEND FLAT FMAP FRAG FREE FVAR GRID HFIX HKLF HOPE HTAB
    ISOR L.S. LATT LAUE LIST LONE MERG MOLE MORE MOVE MPLA NCSY NEUT
    OMIT PART PLAN PRIG REM RESI RIGU RTAB SADI SAME SFAC SHEL SIMU
    SIZE SPEC STIR SUMP SWAT SYMM TEMP TIME TITL TWIN TWST UNIT WGHT
    WIGL WPDB XNPD ZERR
""".split())


def instruction_text(block) -> str:
    """The instruction file a CIF block carries, or ``""``."""
    for tag in RES_TAGS:
        value = block.find_value(tag)
        if value:
            text = gemmi.cif.as_string(value)
            if text.strip() not in ("", "?", "."):
                return text
    return ""


def atom_parts(text: str) -> dict[str, int]:
    """Each atom's PART, keyed by its upper-cased name.

    An atom in a residue is keyed twice, as ``C1`` and as ``C1_3``,
    because SHELXL's CIF names it the second way when the same name
    is used in more than one residue.  Reading stops at ``HKLF`` or
    ``END``: what follows in a ``.res`` is the difference peaks.
    """
    parts: dict[str, int] = {}
    part = residue = 0
    for line in _logical_lines(text):
        words = line.split()
        if not words:
            continue
        head = words[0].upper()
        keyword = head.split("_")[0]
        if keyword in ("HKLF", "END"):
            break
        if keyword == "PART":
            part = _int(words[1]) if len(words) > 1 else 0
            part = 0 if part is None else part
        elif keyword == "RESI":
            numbers = [n for n in map(_int, words[1:]) if n is not None]
            residue = numbers[0] if numbers else 0
        elif keyword not in INSTRUCTIONS and _is_atom(words):
            if residue:
                parts[f"{head}_{residue}"] = part
            parts.setdefault(head, part)
    return parts


def site_parts(labels, parts: dict[str, int]) -> list:
    """``[(part, [site, ...]), ...]`` for every non-zero PART, in the
    order the sites first use each, over sites named by ``labels``."""
    found: dict[int, list[int]] = {}
    for index, label in enumerate(labels):
        part = parts.get(str(label).upper())
        if part:
            found.setdefault(part, []).append(index)
    return [(part, sites) for part, sites in found.items()]


#: ``LATT``'s centring translations, in gemmi's 24ths, by ``|n|``.
CENTRINGS = {
    1: [(0, 0, 0)],
    2: [(0, 0, 0), (12, 12, 12)],
    3: [(0, 0, 0), (16, 8, 8), (8, 16, 16)],
    4: [(0, 0, 0), (0, 12, 12), (12, 0, 12), (12, 12, 0)],
    5: [(0, 0, 0), (0, 12, 12)],
    6: [(0, 0, 0), (12, 0, 12)],
    7: [(0, 0, 0), (12, 12, 0)],
}

#: A single U of -0.5 to -5 rides on the last atom before it that does
#: not: ``-1.2`` is 1.2 times that atom's U_eq.
_RIDING = (-5.0, -0.5)


def read_shelx(path) -> Structure:
    """Read a SHELX ``.ins`` or ``.res`` file."""
    from xtal.io.text import read_text
    path = Path(path)
    return read_shelx_string(read_text(path), path)


def read_shelx_string(text: str, name="<string>") -> Structure:
    """Read a SHELX instruction file held in memory.

    The site occupancy factor SHELXL refines includes the site
    symmetry -- a Zr on Fm-3m's 4mm site is written ``10.125`` -- so
    it is multiplied back by the order of the site's stabiliser, read
    at :data:`~xtal.core.p1.SPECIAL_POSITION_TOL` as every other
    special position is.  Free variables (``21.0``, ``-21.0``) are
    resolved against ``FVAR``.
    """
    from xtal.core.lattice import Lattice
    from xtal.core.p1 import SPECIAL_POSITION_TOL
    from xtal.core.site import Site
    from xtal.core.structure import Structure

    path = Path(name)
    title, cell, latt = "", None, 1
    symm: list[str] = []
    sfac: list[str] = []
    fvar: list[float] = []
    atoms = []
    part_sof = None
    residue = 0
    for line in _logical_lines(text):
        words = line.split()
        if not words:
            continue
        head = words[0].upper()
        keyword = head.split("_")[0]
        if keyword in ("HKLF", "END"):
            break
        if keyword == "TITL":
            title = line.split(None, 1)[1].strip() if len(words) > 1 \
                else ""
        elif keyword == "CELL":
            cell = _numbers(words[2:8], "CELL", 6)
        elif keyword == "LATT":
            latt = _int(words[1]) if len(words) > 1 else 1
            if latt is None or abs(latt) not in CENTRINGS:
                raise ValueError(f"{path.name}: unreadable {line.strip()!r}")
        elif keyword == "SYMM":
            symm.append(line.split(None, 1)[1])
        elif keyword == "SFAC":
            sfac.extend(_sfac_elements(words[1:]))
        elif keyword == "FVAR":
            fvar.extend(_numbers(words[1:], "FVAR"))
        elif keyword == "PART":
            numbers = [float(w) for w in words[2:3] if _float(w)]
            part_sof = numbers[0] if numbers else None
        elif keyword == "RESI":
            found = [n for n in map(_int, words[1:]) if n is not None]
            residue = found[0] if found else 0
        elif keyword not in INSTRUCTIONS and _is_atom(words):
            atoms.append((words, residue, part_sof))
    if cell is None:
        raise ValueError(
            f"{path.name} has no CELL, so it is not a SHELX instruction "
            f"file or has no unit cell to put its atoms in")
    if not atoms:
        raise ValueError(f"no atoms found in {path.name}")

    warnings: list[str] = []
    lattice = Lattice.from_parameters(*cell)
    group = _group(symm, latt, warnings)
    sites, seen = [], set()
    rides_on = None
    for words, residue, sof_default in atoms:
        label = words[0]
        if residue and label.upper() in seen:
            label = f"{label}_{residue}"
        seen.add(label.upper())
        number = _int(words[1])
        if not 1 <= number <= len(sfac):
            raise ValueError(
                f"{path.name}: {words[0]} is SFAC {number}, but only "
                f"{len(sfac)} elements are declared")
        values = _numbers(words[2:], words[0])
        frac = [_resolve(v, fvar) for v in values[:3]]
        sof = _resolve(values[3] if len(values) > 3
                       else sof_default if sof_default is not None
                       else 11.0, fvar)
        u_iso = u_aniso = None
        if len(values) >= 10:
            u11, u22, u33, u23, u13, u12 = (
                _resolve(v, fvar) for v in values[4:10])
            u_aniso = (u11, u22, u33, u12, u13, u23)
        elif len(values) > 4:
            u = values[4]
            if _RIDING[0] <= u <= _RIDING[1]:
                parent = rides_on.u_equivalent if rides_on else None
                u_iso = -u * parent if parent else None
            else:
                u_iso = _resolve(u, fvar)
        stabiliser = _stabiliser(group, lattice, frac,
                                 SPECIAL_POSITION_TOL)
        site = Site(element=sfac[number - 1], frac=frac,
                    occupancy=_occupancy(sof, stabiliser),
                    label=label, u_iso=u_iso, u_aniso=u_aniso)
        if site.element != "H":
            rides_on = site
        sites.append(site)

    structure = Structure(lattice=lattice, sites=sites,
                          space_group=group)
    structure.meta.update({"title": title or path.stem,
                           "source": str(path), "format": "shelx"})
    parts = site_parts([s.label for s in sites], atom_parts(text))
    if parts:
        structure.meta[PARTS_KEY] = parts
    if warnings:
        structure.meta["warnings"] = warnings
    structure.ensure_labels()
    renamed = structure.ensure_unique_labels()
    if renamed:
        structure.meta.setdefault("warnings", []).append(
            f"renamed {renamed} duplicate label"
            f"{'s' if renamed != 1 else ''} so that bonds can name "
            f"their atoms")
    return structure


def _group(symm, latt, warnings):
    """The space group ``SYMM`` and ``LATT`` generate together.

    ``SYMM`` lists neither the identity nor what the centring and a
    positive ``LATT``'s inversion add, so the whole group is built
    from them and looked up the way a CIF's operation loop is.
    """
    from xtal.core.spacegroup import SpaceGroup
    try:
        base = [gemmi.Op("x,y,z")] + [gemmi.Op(t) for t in symm]
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"unreadable SYMM: {exc}") from None
    if latt > 0:
        inversion = gemmi.Op("-x,-y,-z")
        base += [inversion.combine(op) for op in base]
    triplets = {}
    for op in base:
        for shift in CENTRINGS[abs(latt)]:
            moved = op.translated(list(shift)).wrap()
            triplets.setdefault(moved.triplet(), moved)
    try:
        found = gemmi.find_spacegroup_by_ops(
            gemmi.GroupOps(list(triplets.values())))
    except (RuntimeError, ValueError):
        found = None
    if found is None:
        warnings.append(
            f"the file's {len(triplets)} symmetry operations match no "
            f"tabulated setting and were not used; P1 was used instead")
        return SpaceGroup.p1()
    return SpaceGroup.from_hall(found.hall)


def _occupancy(sof: float, stabiliser: int) -> float:
    """``sof * stabiliser``, to the places that survive the product.

    SHELXL writes a sof to five places, so on a site of order 48 the
    product is good to three: ``10.02083`` is 0.99998 by arithmetic
    and a whole atom by intent, as SHELXL's own CIF says.
    """
    places = int(np.floor(-np.log10(1e-5 * stabiliser)))
    return round(sof * stabiliser, places) or 1.0


def _stabiliser(group, lattice, frac, tol) -> int:
    """How many of the group's operations leave ``frac`` where it is."""
    images = group.apply_all(np.asarray(frac, dtype=float))
    delta = images - frac
    delta -= np.round(delta)
    cart = np.asarray(lattice.to_cart(delta))
    return max(1, int(np.sum(np.linalg.norm(cart, axis=1) < tol)))


def _resolve(value: float, fvar) -> float:
    """A parameter as SHELXL reads it: ``10m + p``.

    ``m = 1`` is ``p`` held fixed, ``m > 1`` is ``p * fv(m)``, and the
    negative ``-(10m + p)`` is ``p * (fv(m) - 1)`` -- so ``-21.0`` is
    ``1 - fv(2)``.  ``fv(1)`` is ``FVAR``'s first number, the scale.
    """
    m = int(round(abs(value) / 10.0))
    if m == 0:
        return value
    # Rounded because 10.05 - 10 is 0.0500000000000007, and the file
    # was written to five places in any case.
    p = round(value - np.sign(value) * 10 * m, 8)
    if m == 1:
        return float(p)
    fv = fvar[m - 1] if m - 1 < len(fvar) else 1.0
    return float(p * fv if value > 0 else p * (fv - 1.0))


def _sfac_elements(words) -> list[str]:
    """``SFAC C H N`` is three elements; ``SFAC Zr a1 b1 ...`` (the
    long form, with its scattering factors) is one."""
    if len(words) > 1 and _float(words[1]):
        return [_element(words[0])]
    return [_element(w) for w in words if not _float(w)]


def _element(word: str) -> str:
    """``ZR`` and ``zr`` are ``Zr``."""
    return word[:1].upper() + word[1:].lower()


def _numbers(words, what, count=None) -> list[float]:
    try:
        values = [float(w) for w in words]
    except ValueError:
        raise ValueError(f"unreadable numbers in {what}: "
                         f"{' '.join(words)}") from None
    if count is not None and len(values) < count:
        raise ValueError(f"{what} needs {count} numbers")
    return values


def _float(word: str) -> bool:
    try:
        float(word)
    except ValueError:
        return False
    return True


def _logical_lines(text: str):
    """Lines with comments cut and ``=`` continuations joined."""
    pending = ""
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].rstrip()
        first = line.split(None, 1)
        if first and first[0].upper() == "REM":
            line = ""
        if line.endswith("="):
            pending += line[:-1] + " "
            continue
        yield pending + line
        pending = ""
    if pending:
        yield pending


def _is_atom(words) -> bool:
    """A name, its SFAC number and three coordinates."""
    if len(words) < 5 or _int(words[1]) is None:
        return False
    try:
        [float(w) for w in words[2:5]]
    except ValueError:
        return False
    return True


def _int(word: str) -> int | None:
    try:
        return int(word)
    except ValueError:
        return None
