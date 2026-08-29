"""
xtal.io
=======
File formats.  Importing this package registers everything that ships
in-tree; third-party formats register themselves through the
``crystal_builder.plugins`` entry point (see ``xtal.plugins``).

    from xtal.io import FORMATS
    structure = FORMATS.read("quartz.cif")
    FORMATS.write(structure, "quartz_out.cif")
"""

from xtal.io.cif_reader import read_cif, read_cif_all, read_cif_string
from xtal.io.cif_writer import cif_string, write_cif
from xtal.io.registry import FORMATS, Format, FormatRegistry
from xtal.io.xyz import read_xyz, read_xyz_string, write_xyz, xyz_string

FORMATS.register(Format(
    name="cif",
    description="Crystallographic Information File",
    extensions=(".cif", ".mcif"),
    read=read_cif,
    read_all=read_cif_all,
    write=write_cif,
    keeps=frozenset({"symmetry", "occupancy", "adp", "charges"}),
))

FORMATS.register(Format(
    name="xyz",
    description="Extended XYZ",
    extensions=(".xyz", ".extxyz"),
    read=read_xyz,
    write=write_xyz,
    keeps=frozenset({"occupancy"}),
))

__all__ = ["FORMATS", "Format", "FormatRegistry", "read_cif",
           "read_cif_all", "read_cif_string", "write_cif", "cif_string",
           "read_xyz", "read_xyz_string", "write_xyz", "xyz_string"]
