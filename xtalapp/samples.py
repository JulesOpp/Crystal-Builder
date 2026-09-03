"""
xtalapp.samples
===============
The structures that ship in ``resources/samples``, as menu entries.

Seven real frameworks, 164 KB in total, have been in the repository
since the early phases and were referenced from nowhere in the
application.  A freshly installed copy therefore opened an empty
window to somebody who may not own a CIF yet -- which is the only
first impression a packaged build gets, and it was of a program with
nothing in it.

**They open as new untitled documents.**  Not as the file in
``resources/``: a sample that carried its path would let ``Ctrl+S``
write inside the application folder, which on macOS is a signed
bundle and on Windows is under ``Program Files``, and the save would
either fail or land somewhere the user will never find it again.  With
no path, Save asks where to put it, which is the honest answer to
"I want to keep what I did to this".

**The label is the name the sample is known by, not the CIF's data
block.**  A document with no path takes its title from
``structure.meta["title"]``, and the blocks in these files say
``VESTA_phase_1``, ``CSD_CIF_POSWUS`` and ``sen-116-ds1``.  Opening
*MOF-5* and getting a tab called ``VESTA_phase_1`` is the sort of
detail that makes a program feel like somebody else's export.

The catalogue is here rather than in :mod:`xtal` because it is a menu
and a set of tooltips; nothing in it is crystallography.  Reading the
file is :data:`xtal.io.FORMATS`, the same as for any other structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Where the files are, under the tree root.  The same walk
#: :func:`xtal.modules.zeopp.bundled` and
#: :func:`xtal.ff.dftb.hsd.bundled` make, and it holds in a frozen
#: build for the same reason: the package sits directly under the
#: root, so its parent's parent is the root whether that is a checkout
#: or an unpacked bundle.
FOLDER = ("resources", "samples")

#: What to say when the folder is not there.  ``resources/`` is not
#: package data -- it is not in ``[tool.setuptools.package-data]`` --
#: so a ``pip install`` of the wheel has no samples, exactly as it has
#: no bundled Zeo++.  That is a supported state and it gets a sentence
#: rather than seven entries that do nothing.
MISSING = ("The sample structures are part of the source checkout "
           "and are not installed with the package.")


def folder() -> Path:
    """The directory the samples would be in."""
    return Path(__file__).resolve().parent.parent.joinpath(*FOLDER)


@dataclass(frozen=True)
class Sample:
    """One shipped structure: what it is called, and why it is here."""

    #: The registry name, as ``sample_<name>``.  Spelled the way the
    #: run-app driver and the tests have to type it.
    name: str
    file: str
    label: str
    description: str

    @property
    def path(self) -> Path | None:
        """The file, or ``None`` if this checkout has not got it."""
        candidate = folder() / self.file
        return candidate if candidate.is_file() else None


#: In the order they are worth meeting: the two everybody has heard
#: of, then the ones this project was written for.
SAMPLES = (
    Sample(
        "mof5", "MOF-5.cif", "MOF-5",
        "Zn4O nodes and benzene-1,4-dicarboxylate linkers -- the "
        "framework every other one gets compared to.  Written in P1, "
        "so Symmetry > Find symmetry has Fm-3m to recover from it"),
    Sample(
        "hkust1", "HKUST1.cif", "HKUST-1",
        "Copper paddlewheels and benzene-1,3,5-tricarboxylate, in "
        "Fm-3m with six sites in the asymmetric unit -- the small "
        "end of what a whole framework can be written as"),
    Sample(
        "zif8", "ZIF-8.cif", "ZIF-8",
        "Zinc 2-methylimidazolate: the zeolitic imidazolate "
        "framework, as a 102-atom cell with no symmetry on it"),
    Sample(
        "mfu4l", "MFU4l.cif", "MFU-4l",
        "Zn5Cl4 Kuratowski nodes and a bis(triazolyl) linker.  A "
        "31 A cubic cell, and this project's usual stress case: what "
        "a slow operation is measured against"),
    Sample(
        "ni2cl2btdd", "Ni2Cl2BTDD.cif", "Ni2Cl2(BTDD)",
        "Nickel-chloride chains bridged by a bis(triazolo)dioxine "
        "linker, with the solvent still in the pores.  Rhombohedral, "
        "R-3m -- a cell that is not orthogonal"),
    Sample(
        "cfa1", "CFA1.cif", "CFA-1",
        "Zn5(OAc)4(bibta)3: the Kuratowski node again, capped with "
        "acetate rather than chloride, in trigonal P321.  As "
        "deposited, so its acetate is disordered over two positions "
        "-- occupancies of 0.57 and 0.43 to look at"),
    Sample(
        "cfa1_p1", "zn_oac.cif", "CFA-1 in P1",
        "The same framework and the same cell, modelled ordered and "
        "written out in P1: 210 atoms, two formula units, every site "
        "fully occupied and none of them related by anything"),
)


def get(name: str) -> Sample:
    """The sample of that name.  ``KeyError`` if there is no such one."""
    for sample in SAMPLES:
        if sample.name == name:
            return sample
    raise KeyError(name)


def installed() -> tuple[Sample, ...]:
    """The samples that are actually on disk, which may be none."""
    return tuple(s for s in SAMPLES if s.path is not None)
