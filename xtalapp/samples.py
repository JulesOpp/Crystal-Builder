"""
xtalapp.samples
===============
The structures that ship in ``resources/samples``, as menu entries.

Seven real frameworks, 164 KB in total, had been in the repository
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

**Two groups, and the second is the Crystallography Open Database's.**
The first seven are what this project was written against, and four
of them carry the CCDC's header, which is a decision recorded in
``resources/samples/PROVENANCE.md`` rather than a licence.  The COD's
thirteen are CC0 and exactly as deposited -- the asymmetric unit in its
published group, less the reflections -- so a framework everybody
cites is there in the form it was cited, disorder and all.  They are
written by ``scripts/fetch_cod_samples.py``.

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


#: The sections of Open Sample, in menu order, as (group, title).
SHIPPED = "shipped"
COD = "cod"
PREPARED = "prepared"
GROUPS = ((SHIPPED, "Shipped"), (COD, "From the &COD"),
          (PREPARED, "&Prepared for simulation"))


@dataclass(frozen=True)
class Sample:
    """One shipped structure: what it is called, and why it is here."""

    #: The registry name, as ``sample_<name>``.  Spelled the way the
    #: run-app driver and the tests have to type it.
    name: str
    #: Relative to :func:`folder`.
    file: str
    label: str
    description: str
    group: str = SHIPPED
    #: The COD's number for it, for a sample that came from there.
    cod_id: int | None = None

    @property
    def entry_name(self) -> str:
        """What its workspace entry is called.

        The label, and for a COD sample the number too: there is a
        MOF-5 in each group, and two entries told apart only by
        ``add_structure`` appending ``-2`` would leave nobody knowing
        which was the deposited one.
        """
        if self.cod_id is None:
            return self.label
        if self.group == PREPARED:
            return f"{self.label} prepared COD {self.cod_id}"
        return f"{self.label} COD {self.cod_id}"

    @property
    def path(self) -> Path | None:
        """The file, or ``None`` if this checkout has not got it."""
        candidate = folder() / self.file
        return candidate if candidate.is_file() else None


#: In the order they are worth meeting: the two everybody has heard
#: of, then the ones this project was written for, then the COD's.
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
    Sample(
        "cod_mof5", "cod/MOF-5.cif", "MOF-5", group=COD,
        cod_id=1516287, description=(
            "Lock et al., J. Phys. Chem. C 2010: MOF-5 as refined, in "
            "Fm-3m with seven sites, where the one above is written "
            "out in P1")),
    Sample(
        "cod_hkust1", "cod/HKUST-1.cif", "HKUST-1", group=COD,
        cod_id=4002052, description=(
            "Peterson et al., Chem. Mater. 2014: Cu3(BTC)2 in Fm-3m "
            "from in-situ diffraction, with no guest in the file")),
    Sample(
        "cod_zif8", "cod/ZIF-8.cif", "ZIF-8", group=COD,
        cod_id=7249359, description=(
            "De Zitter et al., CrystEngComm 2024: ZIF-8 in I-43m, with "
            "each methyl hydrogen disordered over two positions")),
    Sample(
        "cod_uio66", "cod/UiO-66.cif", "UiO-66", group=COD,
        cod_id=4512072, description=(
            "Oien et al., Cryst. Growth Des. 2014: UiO-66 with its "
            "defects refined -- linkers at 73 % and the cluster oxygens "
            "split over two positions")),
    Sample(
        "cod_mil101", "cod/MIL-101.cif", "MIL-101(Cr)", group=COD,
        cod_id=4000663, description=(
            "Lebedev et al., Chem. Mater. 2005: an 89 A cubic cell in "
            "Fd-3m, 16 000 atoms with no hydrogens, 4304 of them the "
            "oxygens of the water in its cages -- the largest thing in "
            "this menu")),
    Sample(
        "cod_nu1000", "cod/NU-1000.cif", "NU-1000", group=COD,
        cod_id=7230579, description=(
            "Islamoglu et al., CrystEngComm 2018: Zr6 nodes and a "
            "pyrene tetracarboxylate in P6/mmm, 510 atoms in the cell")),
    Sample(
        "cod_mil100", "cod/MIL-100.cif", "MIL-100(Fe)", group=COD,
        cod_id=7102029, description=(
            "Horcajada et al., Chem. Commun. 2007: Fe3O trimers and "
            "trimesate in Fd-3m, a 73 A cell of 13 552 atoms with no "
            "hydrogens -- MIL-101's smaller sibling")),
    Sample(
        "cod_mof74", "cod/MOF-74.cif", "MOF-74(Zn)", group=COD,
        cod_id=1517474, description=(
            "Queen et al., Chem. Sci. 2014: Zn2(dobdc) evacuated, from "
            "neutron powder diffraction -- the honeycomb of open metal "
            "sites, 162 atoms in R-3")),
    Sample(
        "cod_pcn222", "cod/PCN-222.cif", "PCN-222(Fe)", group=COD,
        cod_id=4329555, description=(
            "Morris et al., Inorg. Chem. 2012, as MOF-545(Fe): Zr6 "
            "nodes and iron porphyrin linkers in P6/mmm, the chloride "
            "on each iron split over two positions")),
    Sample(
        "cod_mof808", "cod/MOF-808.cif", "MOF-808", group=COD,
        cod_id=4121463, description=(
            "Furukawa et al., J. Am. Chem. Soc. 2014: six-connected "
            "Zr6 nodes and trimesate in Fd-3m, with the formate caps "
            "and pore water as partly occupied sites")),
    Sample(
        "cod_mil53", "cod/MIL-53.cif", "MIL-53(Cr)", group=COD,
        cod_id=1502688, description=(
            "Mulder et al., J. Phys. Chem. C 2010: the large-pore form, "
            "Cr(OH) chains and terephthalate, from neutron diffraction "
            "-- so its hydrogens are deuterium")),
    Sample(
        "cod_mil88b", "cod/MIL-88B.cif", "MIL-88B(Cr)", group=COD,
        cod_id=7100637, description=(
            "Serre et al., Chem. Commun. 2006: Cr3O trimers and "
            "terephthalate in P-62c, as refined, with pyridine and "
            "water in the pores and no hydrogens")),
    Sample(
        "cod_mnbtt", "cod/Mn-BTT.cif", "Mn-BTT", group=COD,
        cod_id=4111257, description=(
            "Dinca et al., J. Am. Chem. Soc. 2006: "
            "Mn3[(Mn4Cl)3(BTT)8]2 desolvated, square Mn4Cl units and "
            "a tritetrazolate in Pm-3m -- the exposed Mn2+ sites")),
    Sample(
        "cod_euhotp", "cod/cubic-EuHOTP.cif", "cubic-EuHOTP", group=COD,
        cod_id=4134597, description=(
            "Skorupskii et al., J. Am. Chem. Soc. 2020: europium and "
            "hexaoxytriphenylene in Fd-3m, a porous conductor, with "
            "the nitrate in its pores over three positions")),
    Sample(
        "cod_pbzmof1", "cod/pbz-MOF-1.cif", "pbz-MOF-1", group=COD,
        cod_id=4130966, description=(
            "Alezi et al., J. Am. Chem. Soc. 2016: Zr6 nodes on the "
            "pbz net in Fd-3m, a 45 A cell of 3488 atoms")),
    Sample(
        "cod_alsocmof1", "cod/Al-soc-MOF-1.cif", "Al-soc-MOF-1",
        group=COD, cod_id=4129499, description=(
            "Alezi et al., J. Am. Chem. Soc. 2015: Al3O trimers on the "
            "soc net in Pm-3n, 1208 atoms, with the chloride that "
            "balances the charge spread thin over its site")),
)


#: What preparing each COD framework did, by file.  Written from the
#: messages ``scripts/prepare_samples.py`` prints, which is also what
#: makes the files; ``PROVENANCE.md`` has the longer account.
PREPARED_NOTES = {
    "MOF-5": "the primitive cell, 106 atoms.  Nothing else was needed",
    "HKUST-1": "the primitive cell, 156 atoms, with its copper sites "
               "open",
    "ZIF-8": "each methyl's hydrogens in one of their two orientations, "
             "in the primitive cell",
    "UiO-66": "Zr6O4(OH)4(bdc)6 with its four mu3-OH pointing out: the "
              "ideal framework, not the CIF's average over about 27 % "
              "missing linkers",
    "MIL-101": "the primitive cell of 4080 atoms, one OH and two waters "
               "on each Cr3O trimer, and the powder model's linkers "
               "relaxed with ORB-v3 + D3(BJ) at the experimental cell",
    "NU-1000": "Zr6O4(OH)4(OH)4(H2O)4: four hydroxides and four waters "
               "on the eight-connected node, not the eight hydroxides "
               "that leave it charged",
    "MIL-100": "the primitive cell, one OH and two waters on each Fe3O "
               "trimer, ring hydrogens by ring, and the powder model's "
               "bent linkers relaxed with ORB-v3 + D3(BJ)",
    "MOF-74": "the primitive cell, 54 atoms.  Nothing else was needed",
    "PCN-222": "the disordered chloride ordered, and the node's "
               "terminal ligands replaced by four OH and four waters",
    "MOF-808": "Zr6O4(OH)4(btc)2(HCOO)6 exactly: the disordered "
               "formate and water ordered, the solvent removed",
    "MIL-53": "Cr(OH)(bdc): deuterium as hydrogen, the mu2-OH the "
              "neutron structure never located, and relaxed with "
              "ORB-v3 + D3(BJ)",
    "MIL-88B": "the pyridine and water taken out of the pores, one OH "
               "and two waters on each trimer, relaxed with ORB-v3 + "
               "D3(BJ)",
    "Mn-BTT": "the methanol on each framework Mn made whole, CH3OH.  "
              "One extra-framework Mn per cell where the charge wants "
              "one and a half",
    "cubic-EuHOTP": "every Eu with one whole chelating nitrate -- the "
                    "CIF shares an oxygen between two -- and the cluster "
                    "nitrate ordered.  Its charge is not settled: HOTP's "
                    "oxidation state is not in the file",
    "pbz-MOF-1": "one acetate in six missing, as refined, each gap left "
                 "as a hydroxide and a water; relaxed with ORB-v3 + "
                 "D3(BJ)",
    "Al-soc-MOF-1": "one tilt of each terphenyl ring -- the CIF gives "
                    "both at full occupancy -- a chloride per trimer "
                    "and three waters on it; relaxed with ORB-v3 + "
                    "D3(BJ)",
}

#: The COD frameworks again, prepared for simulation: ordered, the
#: solvent out, charge-balanced, hydrogens where they belong, and some
#: relaxed.  Made by ``scripts/prepare_samples.py`` from the COD files,
#: which stay as deposited.
SAMPLES = SAMPLES + tuple(
    Sample(f"prep_{s.name.removeprefix('cod_')}",
           "prepared/" + s.file.removeprefix("cod/"), s.label,
           group=PREPARED, cod_id=s.cod_id,
           description=(f"COD {s.cod_id} prepared for simulation: "
                        + PREPARED_NOTES[Path(s.file).stem]))
    for s in SAMPLES if s.group == COD)


def get(name: str) -> Sample:
    """The sample of that name.  ``KeyError`` if there is no such one."""
    for sample in SAMPLES:
        if sample.name == name:
            return sample
    raise KeyError(name)


def in_group(group: str) -> tuple[Sample, ...]:
    """The samples of one section of the menu, in catalogue order."""
    return tuple(s for s in SAMPLES if s.group == group)


def installed() -> tuple[Sample, ...]:
    """The samples that are actually on disk, which may be none."""
    return tuple(s for s in SAMPLES if s.path is not None)
