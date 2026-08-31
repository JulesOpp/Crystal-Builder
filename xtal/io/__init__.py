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
from xtal.io.cssr import (
    cssr_string,
    read_cssr,
    read_cssr_string,
    write_cssr,
)
from xtal.io.gen import gen_string, read_gen, read_gen_string, write_gen
from xtal.io.project import (
    is_project,
    read_project,
    read_project_structure,
    write_project,
)
from xtal.io.registry import FORMATS, Format, FormatRegistry
from xtal.io.trajectory import (
    Frame,
    Trajectory,
    TrajectoryWriter,
    frame_of,
    read_trajectory,
    write_trajectory,
)
from xtal.io.xyz import (
    read_xyz,
    read_xyz_all,
    read_xyz_string,
    write_xyz,
    xyz_string,
)

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
    name="xtalproj",
    description="Crystal Builder project",
    extensions=(".xtalproj",),
    read=read_project_structure,
    write=write_project,
    # A project keeps everything, which is the whole reason it exists.
    keeps=frozenset({"symmetry", "occupancy", "adp", "charges",
                     "bonds", "view"}),
))

FORMATS.register(Format(
    name="cssr",
    description="CSSR",
    extensions=(".cssr",),
    read=read_cssr,
    # Written in P1 and with the symmetry dropped, because that is
    # what every reader of this format assumes it is being given --
    # see xtal.io.cssr.
    write=write_cssr,
    keeps=frozenset({"charges"}),
))

FORMATS.register(Format(
    name="gen",
    description="DFTB+ geometry",
    extensions=(".gen",),
    read=read_gen,
    write=write_gen,
    keeps=frozenset(),
))

FORMATS.register(Format(
    name="xyz",
    description="Extended XYZ",
    extensions=(".xyz", ".extxyz"),
    read=read_xyz,
    # A relaxation is a hundred frames in one file, and reading only
    # the first of them silently answers a different question.
    read_all=read_xyz_all,
    write=write_xyz,
    keeps=frozenset({"occupancy"}),
))

__all__ = ["FORMATS", "Format", "FormatRegistry", "read_cif",
           "read_cif_all", "read_cif_string", "write_cif", "cif_string",
           "read_cssr", "read_cssr_string", "write_cssr", "cssr_string",
           "read_gen", "read_gen_string", "write_gen", "gen_string",
           "read_xyz", "read_xyz_all", "read_xyz_string", "write_xyz",
           "xyz_string", "read_project", "write_project", "is_project",
           "Frame", "Trajectory", "TrajectoryWriter", "frame_of",
           "read_trajectory", "write_trajectory"]
