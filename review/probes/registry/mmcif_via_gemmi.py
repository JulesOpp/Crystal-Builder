# Written 2026-09-19 against Crystal-Builder source commit 3cd15e2 (v0.2.1).
# How many lines does an mmCIF/PDBx reader cost, given that gemmi is
# already in [project].dependencies?  The claim under test: the whole
# reader is gemmi's mx->sx bridge plus the CIF reader's existing
# `_from_small_structure`.  Run with .venv/bin/python.
from pathlib import Path
import sys
import tempfile
import gemmi
from xtal.io.cif_reader import _from_small_structure

#: A minimal PDBx/mmCIF: the categories are `_cell.`, `_symmetry.`
#: and `_atom_site.` with a dot, which is what makes it a *different*
#: dialect from core CIF's `_cell_length_a` / `_atom_site_label`.
SAMPLE = """data_TEST
_cell.entry_id      TEST
_cell.length_a      10.000
_cell.length_b      20.000
_cell.length_c      30.000
_cell.angle_alpha   90.00
_cell.angle_beta    90.00
_cell.angle_gamma   90.00
_symmetry.entry_id                TEST
_symmetry.space_group_name_H-M   'P 21 21 21'
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.auth_seq_id
_atom_site.auth_asym_id
_atom_site.pdbx_PDB_model_num
ATOM 1 N N  . ALA A 1 1 1.000 2.000 3.000 1.00 11.0 1 A 1
ATOM 2 C CA . ALA A 1 1 2.000 3.000 4.000 1.00 12.0 1 A 1
ATOM 3 C C  . ALA A 1 1 3.000 4.000 5.000 1.00 13.0 1 A 1
ATOM 4 O O  . ALA A 1 1 4.000 5.000 6.000 1.00 14.0 1 A 1
"""

if len(sys.argv) > 1:
    MMCIF = Path(sys.argv[1])
else:
    MMCIF = Path(tempfile.gettempdir()) / "xtal_review_mmcif_probe.cif"
    MMCIF.write_text(SAMPLE, encoding="utf-8")


def read_mmcif(path):
    """The whole candidate reader, verbatim: eight lines."""
    doc = gemmi.cif.read_file(str(path))
    for block in doc:
        st = gemmi.make_structure_from_block(block)
        st.setup_entities()
        small = gemmi.mx_to_sx_structure(st)
        if small.sites and small.cell.volume > 0:
            s = _from_small_structure(small, block, Path(path))
            s.meta["format"] = "mmcif"
            return s
    raise ValueError("no atoms in that mmCIF")


s = read_mmcif(MMCIF)
print("atoms      ", s.n_sites)
print("lattice    ", [round(v, 3) for v in s.lattice.parameters])
print("space group", s.space_group)
print("elements   ", sorted({x.element for x in s.sites}))
print("labels     ", [x.label for x in s.sites][:6])
print("u_iso      ", [round(x.u_iso, 4) if x.u_iso else None
                      for x in s.sites][:6])
print("meta       ", {k: s.meta[k] for k in ("title", "format")
                      if k in s.meta})

# And the writer, which is gemmi's too.
st = gemmi.read_structure(str(MMCIF))
print("writer     ", len(st.make_mmcif_document().as_string()), "chars")
