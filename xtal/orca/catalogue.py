"""
xtal.orca.catalogue
===================
What ORCA 6.1 offers to an input file, as its manual lists it.

The functionals are ORCA's native ones, Tables 3.1-3.9 of the 6.1
manual, written here by hand: under a hundred rows, in tables whose
narrow columns wrap the keywords, so reading them by program would be
the less reliable of the two.  The LibXC table (3.12) is left out on
purpose -- it is written ``LibXC(KEY)``, and the functionals people
ask for by name are native.

The basis sets (Tables 2.12-2.33, about 450) and the solvents (Table
2.56) are read off the manual by ``scripts/orca_tables.py`` into
``data/tables.json``, with the elements each basis covers: a structure
with zinc and a basis that stops at krypton is said before the file is
written, not when ORCA aborts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources

from xtal.core import elements as el

#: The families, in the order the dialog lists them.
LOCAL = "Local (LDA)"
GGA = "GGA"
META_GGA = "meta-GGA"
HYBRID = "Global hybrid"
META_HYBRID = "Global hybrid meta-GGA"
RANGE_SEPARATED = "Range-separated hybrid"
DOUBLE_HYBRID = "Double hybrid"
RS_DOUBLE_HYBRID = "Range-separated double hybrid"
COMPOSITE = "Composite (3c)"

#: The ones that need RIJCOSX rather than RI-J -- what ORCA does by
#: default for each, and so what "ORCA's default" means in the preview.
HYBRID_FAMILIES = frozenset({HYBRID, META_HYBRID, RANGE_SEPARATED,
                             DOUBLE_HYBRID, RS_DOUBLE_HYBRID})
DOUBLE_HYBRIDS = frozenset({DOUBLE_HYBRID, RS_DOUBLE_HYBRID})

# A dispersion correction, or VV10, already in the functional's name.
_OWN_DISPERSION = re.compile(r"-(V|D3|D3BJ|D4|D4REV|3C)(/\d+)?$")


@dataclass(frozen=True)
class Functional:
    key: str                # what goes on the ! line
    label: str              # what the manual calls it
    family: str
    table: str
    hybrid: bool = False    # in some hybrid family

    @property
    def carries_dispersion(self) -> bool:
        """Whether a D3/D4 or VV10 is already part of it, so adding
        one would count dispersion twice."""
        return bool(_OWN_DISPERSION.search(self.key.upper()))

    @property
    def own_basis(self) -> bool:
        """A 3c method brings its own basis set; one written beside it
        replaces the one it was fitted with."""
        return self.family == COMPOSITE

    @property
    def double_hybrid(self) -> bool:
        return self.family in DOUBLE_HYBRIDS


def _family(family: str, table: str, *rows) -> tuple[Functional, ...]:
    hybrid = family in HYBRID_FAMILIES
    return tuple(Functional(key, label, family, table, hybrid)
                 for key, label in rows)


FUNCTIONALS: dict[str, tuple[Functional, ...]] = {
    LOCAL: _family(
        LOCAL, "3.1",
        ("HFS", "Hartree-Fock-Slater"),
        ("LDA", "Local density approximation (VWN5)"),
        ("VWN5", "Vosko-Wilk-Nusair, parameter set V"),
        ("VWN3", "Vosko-Wilk-Nusair, parameter set III"),
        ("PWLDA", "Perdew-Wang LDA")),
    GGA: _family(
        GGA, "3.2",
        ("BP86", "Becke 88 exchange, Perdew 86 correlation"),
        ("BLYP", "Becke 88 exchange, Lee-Yang-Parr correlation"),
        ("OLYP", "Handy's optimal exchange, LYP correlation"),
        ("GLYP", "Gill 96 exchange, LYP correlation"),
        ("XLYP", "Xu-Goddard exchange, LYP correlation"),
        ("PW91", "Perdew-Wang 91"),
        ("MPWPW", "Modified PW exchange, PW correlation"),
        ("MPWLYP", "Modified PW exchange, LYP correlation"),
        ("PBE", "Perdew-Burke-Ernzerhof"),
        ("RPBE", "Modified PBE"),
        ("REVPBE", "Revised PBE"),
        ("RPW86PBE", "Refitted Perdew 86 exchange, PBE correlation"),
        ("PWP", "PW91 exchange, Perdew 86 correlation")),
    META_GGA: _family(
        META_GGA, "3.2",
        ("B97M-V", "Head-Gordon's B97M-V, VV10 nonlocal"),
        ("B97M-D3BJ", "B97M-V with D3(BJ) in place of VV10"),
        ("B97M-D4", "B97M-V with D4 in place of VV10"),
        ("SCANFUNC", "SCAN"),
        ("RSCAN", "Regularized SCAN"),
        ("R2SCAN", "r2SCAN"),
        ("M06L", "Minnesota M06-L"),
        ("TPSS", "TPSS"),
        ("REVTPSS", "Revised TPSS")),
    HYBRID: _family(
        HYBRID, "3.4",
        ("B1LYP", "One-parameter B88/LYP hybrid, 25 % HF"),
        ("B3LYP", "B3LYP as in TURBOMOLE (VWN5), 20 % HF"),
        ("B3LYP/G", "B3LYP as in Gaussian (VWN3), 20 % HF"),
        ("O3LYP", "Handy's hybrid, 11.61 % HF"),
        ("X3LYP", "Xu-Goddard hybrid, 21.8 % HF"),
        ("B1P86", "One-parameter hybrid BP86, 25 % HF"),
        ("B3P86", "Three-parameter hybrid BP86, 20 % HF"),
        ("B3PW91", "Three-parameter hybrid PW91, 20 % HF"),
        ("PW1PW", "One-parameter hybrid PW91, 25 % HF"),
        ("MPW1PW", "One-parameter hybrid mPWPW, 25 % HF"),
        ("MPW1LYP", "One-parameter hybrid mPWLYP, 25 % HF"),
        ("PBE0", "PBE0, 25 % HF"),
        ("REVPBE0", "Revised PBE0, 25 % HF"),
        ("REVPBE38", "Revised PBE0, 37.5 % HF"),
        ("BHANDHLYP", "Becke's half-and-half, 50 % HF")),
    META_HYBRID: _family(
        META_HYBRID, "3.4",
        ("TPSSH", "TPSSh, 10 % HF"),
        ("TPSS0", "TPSS0, 25 % HF"),
        ("R2SCANH", "r2SCANh, 10 % HF"),
        ("R2SCAN0", "r2SCAN0, 25 % HF"),
        ("R2SCAN50", "r2SCAN50, 50 % HF")),
    RANGE_SEPARATED: _family(
        RANGE_SEPARATED, "3.6",
        ("WB97", "wB97"),
        ("WB97X", "wB97X"),
        ("WB97X-V", "wB97X-V, VV10 nonlocal"),
        ("WB97X-D3", "wB97X-D3, zero damping"),
        ("WB97X-D3BJ", "wB97X-D3(BJ)"),
        ("WB97X-D4", "wB97X-D4"),
        ("WB97X-D4REV", "wB97X-D4rev"),
        ("CAM-B3LYP", "CAM-B3LYP"),
        ("LC-BLYP", "LC-BLYP"),
        ("LC-PBE", "LC-PBE"),
        ("WB97M-V", "wB97M-V, VV10 nonlocal"),
        ("WB97M-D3BJ", "wB97M-D3(BJ)"),
        ("WB97M-D4", "wB97M-D4"),
        ("WB97M-D4REV", "wB97M-D4rev"),
        ("WR2SCAN", "wr2SCAN")),
    DOUBLE_HYBRID: _family(
        DOUBLE_HYBRID, "3.8",
        ("B2PLYP", "B2PLYP"),
        ("MPW2PLYP", "mPW2PLYP"),
        ("B2GP-PLYP", "B2GP-PLYP"),
        ("B2K-PLYP", "B2K-PLYP"),
        ("B2T-PLYP", "B2T-PLYP"),
        ("B2NC-PLYP", "B2NC-PLYP"),
        ("DSD-BLYP", "DSD-BLYP (add D3BJ)"),
        ("DSD-BLYP/2013", "DSD-BLYP (2013)"),
        ("DSD-PBEP86", "DSD-PBEP86 (add D3BJ)"),
        ("DSD-PBEP86/2013", "DSD-PBEP86 (2013)"),
        ("DSD-PBEB95", "DSD-PBEB95"),
        ("REVDSD-PBEP86/2021", "revDSD-PBEP86 (2021)"),
        ("REVDSD-PBEP86-D4/2021", "revDSD-PBEP86-D4 (2021)"),
        ("REVDOD-PBEP86/2021", "revDOD-PBEP86 (2021)"),
        ("REVDOD-PBEP86-D4/2021", "revDOD-PBEP86-D4 (2021)"),
        ("PWPB95", "PWPB95"),
        ("PBE-QIDH", "PBE-QIDH"),
        ("PBE0-DH", "PBE0-DH"),
        ("R2SCAN-CIDH", "SOS1-r2SCAN-CIDH"),
        ("R2SCAN-QIDH", "SOS1-r2SCAN-QIDH"),
        ("R2SCAN0-2", "SOS1-r2SCAN0-2"),
        ("R2SCAN0-DH", "SOS1-r2SCAN0-DH"),
        ("PR2SCAN50", "Pr2SCAN50"),
        ("PR2SCAN69", "Pr2SCAN69"),
        ("KPR2SCAN50", "kPr2SCAN50")),
    RS_DOUBLE_HYBRID: _family(
        RS_DOUBLE_HYBRID, "3.9",
        ("WB97X-2", "wB97X-2"),
        ("WPR2SCAN50", "wPr2SCAN50"),
        ("RSX-QIDH", "RSX-QIDH"),
        ("RSX-0DH", "RSX-0DH"),
        ("WB2PLYP", "wB2PLYP"),
        ("WB2GP-PLYP", "wB2GP-PLYP"),
        ("WB88PP86", "wB88PP86"),
        ("WPBEPP86", "wPBEPP86")),
    COMPOSITE: (
        Functional("B97-3C", "B97-3c (GGA, own basis)", COMPOSITE, "3.2"),
        Functional("R2SCAN-3C", "r2SCAN-3c (meta-GGA, own basis)",
                   COMPOSITE, "3.2"),
        Functional("PBEH-3C", "PBEh-3c (hybrid, own basis)", COMPOSITE,
                   "3.4", hybrid=True),
        Functional("B3LYP-3C", "B3LYP-3c (hybrid, own basis)",
                   COMPOSITE, "3.4", hybrid=True),
        Functional("WB97X-3C", "wB97X-3c (range-separated, own basis)",
                   COMPOSITE, "3.6", hybrid=True)),
}

#: Functionals ORCA 6.1 can follow an excited state with -- an
#: analytic TD-DFT gradient, which ``Opt`` or ``Freq`` beside a
#: ``%tddft`` block asks for.  Measured, not read: every native
#: functional on H2, ``Opt`` with ``%tddft iroot 1`` and one geometry
#: step, ORCA 6.1.0 (2026-10-04).  The rest refuse before the first
#: SCF: B88 exchange (BP86, B3LYP, B2PLYP...) for want of its third
#: derivative, the mPW, TPSS and M06-L families and four of the wB97X
#: dispersion variants for want of a native kernel, PWPB95 and
#: DSD-PBEB95 without NumGrad, and every double hybrid ("not yet
#: implemented").  A spectrum *at* an optimised ground state needs
#: none of this, which is why that is the default route.
EXCITED_GRADIENT = frozenset({
    "HFS", "LDA", "VWN5", "VWN3", "PWLDA",
    "GLYP", "OLYP", "XLYP", "PW91", "PBE", "RPBE", "REVPBE", "PWP",
    "B97M-D3BJ", "B97M-D4", "SCANFUNC", "RSCAN", "R2SCAN",
    "O3LYP", "X3LYP", "PW1PW", "PBE0", "REVPBE0", "REVPBE38",
    "R2SCANH", "R2SCAN0", "R2SCAN50",
    "WB97", "WB97X", "WB97X-D3", "CAM-B3LYP", "LC-BLYP",
    "WB97M-D3BJ", "WB97M-D4", "WB97M-D4REV",
    "B97-3C", "PBEH-3C", "R2SCAN-3C",
})

#: VV10's nonlocal correlation has no TD-DFT in ORCA 6.1 at all, not
#: even for a single point: "DFT-NL dispersion correction is not yet
#: possible with TDDFT", and the run is skipped.
NO_TDDFT = frozenset({"B97M-V", "WB97X-V", "WB97M-V"})

DEFAULT_FUNCTIONAL = "BP86"
DEFAULT_BASIS = "def2-SVP"


@dataclass(frozen=True)
class Basis:
    key: str
    family: str
    table: str
    elements: str           # as the manual writes it: "H–Rn"
    ecp: str = ""           # "def2-ECP(Rb–Rn)"
    relativistic: str = ""  # "DKH2", "ZORA", "X2C"

    @property
    def covers(self) -> frozenset[str]:
        return _covered(self.elements)

    @property
    def def2(self) -> bool:
        """A Karlsruhe def2 set, for which def2/J is the auxiliary."""
        return self.family == "Karlsruhe def2" or \
            self.key.lower().startswith("def2-")


@cache
def _covered(text: str) -> frozenset[str]:
    out = set()
    for part in text.split(","):
        ends = part.split("–")
        lo, hi = el.atomic_number(ends[0]), el.atomic_number(ends[-1])
        out.update(el.symbol_from_z(z) for z in range(lo, hi + 1))
    return frozenset(out)


@cache
def _tables() -> dict:
    data = resources.files("xtal.orca").joinpath("data/tables.json")
    return json.loads(data.read_text(encoding="utf-8"))


@cache
def bases() -> dict[str, tuple[Basis, ...]]:
    """Family -> its basis sets, in the manual's order."""
    return {f["family"]: tuple(Basis(b["key"], f["family"], f["table"],
                                     b["elements"], b.get("ecp", ""),
                                     b.get("relativistic", ""))
                               for b in f["bases"])
            for f in _tables()["families"]}


@dataclass(frozen=True)
class Solvent:
    names: tuple[str, ...]  # "water", "h2o"
    cpcm: bool
    smd: bool

    @property
    def name(self) -> str:
        return self.names[0]


@cache
def solvents() -> tuple[Solvent, ...]:
    return tuple(Solvent(tuple(s["names"]), s["cpcm"], s["smd"])
                 for s in _tables()["solvents"])


def solvent(name: str) -> Solvent | None:
    """By any of its names, as ORCA takes any of them."""
    wanted = name.strip().lower()
    return next((s for s in solvents()
                 if wanted in (n.lower() for n in s.names)), None)


def functional(key: str) -> Functional | None:
    wanted = key.strip().upper()
    return next((f for family in FUNCTIONALS.values() for f in family
                 if f.key.upper() == wanted), None)


def basis(key: str) -> Basis | None:
    wanted = key.strip().lower()
    return next((b for family in bases().values() for b in family
                 if b.key.lower() == wanted), None)


def find(entries, text: str) -> list:
    """The entries whose key or label holds ``text``, case aside --
    what a search box offers as it is typed into."""
    wanted = text.strip().lower()
    return [e for e in entries
            if wanted in e.key.lower()
            or wanted in getattr(e, "label", "").lower()]


def all_functionals() -> list[Functional]:
    return [f for family in FUNCTIONALS.values() for f in family]


def all_bases() -> list[Basis]:
    return [b for family in bases().values() for b in family]


#: Auxiliary sets for RI-MP2 in a double hybrid (Table 2.36): the
#: orbital basis's own "/C" where the manual lists one, AutoAux else.
C_AUXILIARY = frozenset({
    "def2-SVP", "def2-TZVP", "def2-TZVPP", "def2-QZVPP", "def2-SVPD",
    "def2-TZVPD", "def2-TZVPPD", "def2-QZVPPD",
    "cc-pVDZ", "cc-pVTZ", "cc-pVQZ", "cc-pV5Z", "cc-pV6Z",
    "aug-cc-pVDZ", "aug-cc-pVTZ", "aug-cc-pVQZ", "aug-cc-pV5Z",
    "aug-cc-pV6Z", "cc-pwCVDZ", "cc-pwCVTZ", "cc-pwCVQZ", "cc-pwCV5Z",
})

#: (keyword or "", label).  "" writes nothing and leaves ORCA's own
#: choice, which is the right one far more often than not.
DISPERSIONS = (("", "None"), ("D3BJ", "D3(BJ)"),
               ("D3ZERO", "D3(0)"), ("D4", "D4"))
RI_CHOICES = (("", "ORCA's default"), ("RIJCOSX", "RIJCOSX"),
              ("RI", "RI-J"), ("RIJK", "RI-JK"), ("NORI", "No RI"))
#: Tables 2.9 and 2.10.  "" is ORCA's own, which tightens itself for
#: an optimisation or frequencies.
SCF_THRESHOLDS = (("", "ORCA's default"), ("SloppySCF", "Sloppy"),
                  ("LooseSCF", "Loose"), ("MediumSCF", "Medium"),
                  ("NormalSCF", "Normal"), ("StrongSCF", "Strong"),
                  ("TightSCF", "Tight"),
                  ("VeryTightSCF", "Very tight"),
                  ("ExtremeSCF", "Extreme"))
#: Table 2.11's solver parameter sets.
SCF_SOLVERS = (("", "ORCA's default"), ("EasyConv", "EasyConv"),
               ("SlowConv", "SlowConv"),
               ("VerySlowConv", "VerySlowConv"))
SCF_GUESSES = (("", "ORCA's default"), ("PModel", "PModel"),
               ("PAtom", "PAtom"), ("Hueckel", "Hueckel"),
               ("HCore", "HCore"))
#: Table 4.1.
OPT_LEVELS = (("Opt", "Normal"), ("LooseOpt", "Loose"),
              ("TightOpt", "Tight"), ("VeryTightOpt", "Very tight"))
RUNS = (("sp", "Single point"), ("opt", "Optimise (Opt)"),
        ("optts", "Transition state (OptTS)"))
SOLVATIONS = (("", "Gas phase"), ("CPCM", "C-PCM"), ("SMD", "SMD"))
TDDFT_STATES = (
    ("ground", "Ground state, then the spectrum (two steps)"),
    ("excited", "Excited state IRoot (one step)"))
