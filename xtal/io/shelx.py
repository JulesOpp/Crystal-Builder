"""
xtal.io.shelx
=============
The PART each atom was refined in, read off a SHELX ``.res``/``.ins``.

A CIF from SHELXL usually carries the instruction file it was refined
from (``_shelx_res_file``, or ``_iucr_refine_instructions_details`` in
older ones), and that is where the disorder is written down as the
crystallographer meant it: ``PART 1`` and ``PART 2`` for the two
components, ``PART -1`` for a component lying on a symmetry element.
``_atom_site_disorder_group`` is SHELXL's copy of the same numbers, but
other programs drop or rewrite that column, and the instruction file
is the original.

Only what is needed to tell an atom line from an instruction is read
here; nothing is refined, and no number but the PART is taken.
"""

from __future__ import annotations

import gemmi

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
