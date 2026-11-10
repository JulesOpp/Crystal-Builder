"""
xtal.mof.precedent
==================
What a synthesis is likely to make, read off the published syntheses
nearest to it.

**This is a vote, not a prediction.**  A query -- a metal salt, one to
three linkers, the solvents, a temperature -- is scored against every
stored precedent; the closest :data:`NEIGHBOURS` vote, each with its
similarity as its weight, on the node, the net and whether the
framework interpenetrated.  A share is the fraction of that weight,
which is not a calibrated probability, and every answer carries the
precedents themselves (by CSD refcode) and how far the query sits from
the nearest of them, so a person can see what the vote stood on.
``scripts/synthesis_precedents.py`` measures how often the net that
was actually made is in the first five, each synthesis held out of
the table in turn: 62 % of the 146 with conditions and a named net,
first in 24 % (:data:`BASIS` says so).  One refcode family is held
out at a time -- a compound's re-determinations go with it -- but a
paper's series of related structures stays in, and the table has no
DOI for a CSD entry to hold out a paper by, so the number is
generous.

**The precedents are two open tables joined by refcode**
(``scripts/synthesis_precedents.py`` writes :data:`TABLE`):

* *what formed*: CoRE MOF 2024's MOFid of each structure -- its nodes
  and linkers as SMILES and its net -- CC-BY 4.0, Zhao et al., Matter
  2025;
* *how it was made*: SynMOF-ME's metal, counter-ion, solvents and
  temperature, extracted from the papers and corrected by hand -- MIT,
  Luo et al., Angew. Chem. 2022.

Most structures have the first and not the second, and they are kept:
a framework whose conditions nobody extracted still says what that
metal and that linker make, and an unknown condition scores half
(:func:`similarity`) rather than nothing, so it neither wins nor
loses on a question it cannot answer.

**Where the precedents come from is a seam** (:class:`Source`).  The
bundled table is one source; a larger licensed one, or a remote
service, is another object with ``records()`` and ``linker_bits()``,
and nothing else here changes.

Numpy, json and strings.  RDKit is needed only to read a linker the
person typed (:func:`linker_key`), so a query needs the ``build``
extra; the table is fingerprinted ahead of time and costs no RDKit to
load.
"""

from __future__ import annotations

import gzip
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from xtal.core import elements

#: The precedent table, written by ``scripts/synthesis_precedents.py``.
TABLE = Path(__file__).with_name("data") / "precedents.json.gz"

#: How many of the nearest precedents vote.  Measured with
#: ``scripts/synthesis_precedents.py``, each of the 146 syntheses with
#: conditions and a named net left out in turn -- the made net first /
#: in the first five:
#:
#:     voters    5        10       25       50
#:              31/42 %  25/47 %  25/56 %  24/62 %
#:
#: Fewer voters win the first place and lose the list; the list is
#: what a person reads, and fifty costs one point of the first place
#: for six of the list.  146 is a small sample: a point or two either
#: way is noise.
NEIGHBOURS = 50

#: How much each part of a synthesis counts.  Metal and linker are
#: what decide a node and a net; the conditions move it within what
#: those two allow, and are missing for most of the table besides.
WEIGHTS = {"metal": 0.40, "linker": 0.40, "solvent": 0.10,
           "temperature": 0.05, "anion": 0.05}

#: An unknown condition scores this, on either side.  Half, so that a
#: precedent with no recorded solvent ranks below one with the same
#: solvent and above one with a different solvent.
UNKNOWN = 0.5

#: A temperature this many degrees away scores 1/e: solvothermal
#: syntheses are reported to the nearest five or ten, and 85 against
#: 120 is a different regime while 120 against 125 is not.
TEMPERATURE_SCALE = 40.0

#: Morgan fingerprints for linker similarity: radius and length.
#: Kept here because the table's bits and a query's must agree.
FP_RADIUS = 2
FP_BITS = 2048

#: Said with every answer, because the shares look like probabilities
#: and are not.
BASIS = ("A vote of the most similar published syntheses, each "
         "weighted by its similarity.  Shares are fractions of that "
         "weight, not calibrated probabilities.  With each synthesis "
         "left out in turn, the net that was made was among the first "
         "five in 62 % of 146 and first in 24 %.")

#: Not metals, for reading a node's SMILES.  B, Si, Ge, As, Sb and Te
#: are left out: MOFid writes a metalloid in a node only when it is
#: one.
NONMETALS = frozenset({"H", "D", "He", "C", "N", "O", "F", "Ne", "P",
                       "S", "Cl", "Ar", "Se", "Br", "Kr", "I", "Xe",
                       "X", "*"})


class PrecedentError(ValueError):
    """The query cannot be read: no metal, or no linker at all."""


# ======================================================================
#  READING A SYNTHESIS
# ======================================================================

#: Counter-ions by how a formula or a name writes them.  Order is the
#: order they are tried in a formula, longest first, so ClO4 is not
#: read as Cl and O.
ANIONS = (
    ("ClO4", ("ClO4",), ("perchlorate",)),
    ("BF4", ("BF4",), ("tetrafluoroborate",)),
    ("PF6", ("PF6",), ("hexafluorophosphate",)),
    ("OTf", ("OTf", "CF3SO3"), ("triflate",
                                "trifluoromethanesulfonate")),
    ("acac", ("acac",), ("acetylacetonate",)),
    ("OAc", ("OAc", "CH3COO", "CH3CO2", "Ac"), ("acetate",)),
    ("NO3", ("NO3",), ("nitrate",)),
    ("SO4", ("SO4",), ("sulfate", "sulphate")),
    ("CO3", ("CO3",), ("carbonate",)),
    ("OH", ("OH",), ("hydroxide",)),
    ("Cl", ("Cl",), ("chloride",)),
    ("Br", ("Br",), ("bromide",)),
    ("I", ("I",), ("iodide",)),
    ("F", ("F",), ("fluoride",)),
    ("O", ("O",), ("oxide", "oxy", "oxo")),
)

#: What SynMOF writes for a counter-ion, to the keys above.
ANION_ALIASES = {"CH3COO": "OAc", "Ac": "OAc", "OAC": "OAc",
                 "AcO": "OAc", "H2O": None, "unknown": None, "": None}

#: Solvents by PubChem CID, which is how SynMOF records them, with the
#: names and abbreviations a person types.
SOLVENTS = {
    962: ("water", "h2o", "o"),
    6228: ("dmf", "n,n-dimethylformamide", "dimethylformamide"),
    12051: ("def", "n,n-diethylformamide", "diethylformamide"),
    31374: ("dma", "dmac", "n,n-dimethylacetamide",
            "dimethylacetamide"),
    702: ("ethanol", "etoh"),
    887: ("methanol", "meoh"),
    6342: ("acetonitrile", "mecn", "ch3cn"),
    31275: ("1,4-dioxane", "dioxane"),
    13387: ("nmp", "n-methyl-2-pyrrolidone", "n-methylpyrrolidone"),
    679: ("dmso", "dimethyl sulfoxide", "dimethylsulfoxide"),
    1049: ("pyridine", "py"),
    8028: ("thf", "tetrahydrofuran"),
    174: ("ethylene glycol", "eg"),
    241: ("benzene",),
    1140: ("toluene",),
    6212: ("chloroform", "chcl3"),
    6344: ("dichloromethane", "dcm", "ch2cl2"),
    3776: ("isopropanol", "2-propanol", "ipa", "iproh"),
    263: ("1-butanol", "n-butanol", "buoh"),
}
_SOLVENT_BY_NAME = {name: cid for cid, names in SOLVENTS.items()
                    for name in names}

#: Linkers by the names they go by, to SMILES.  A convenience: any
#: SMILES is read as well, and a name not here is refused by name.
LINKER_NAMES = {
    "bdc": "OC(=O)c1ccc(cc1)C(=O)O",
    "terephthalic acid": "OC(=O)c1ccc(cc1)C(=O)O",
    "h2bdc": "OC(=O)c1ccc(cc1)C(=O)O",
    "nh2-bdc": "Nc1cc(ccc1C(=O)O)C(=O)O",
    "2-aminoterephthalic acid": "Nc1cc(ccc1C(=O)O)C(=O)O",
    "btc": "OC(=O)c1cc(cc(c1)C(=O)O)C(=O)O",
    "trimesic acid": "OC(=O)c1cc(cc(c1)C(=O)O)C(=O)O",
    "h3btc": "OC(=O)c1cc(cc(c1)C(=O)O)C(=O)O",
    "isophthalic acid": "OC(=O)c1cccc(c1)C(=O)O",
    "bpdc": "OC(=O)c1ccc(cc1)-c1ccc(cc1)C(=O)O",
    "biphenyl-4,4'-dicarboxylic acid":
        "OC(=O)c1ccc(cc1)-c1ccc(cc1)C(=O)O",
    "ndc": "OC(=O)c1ccc2cc(ccc2c1)C(=O)O",
    "2,6-ndc": "OC(=O)c1ccc2cc(ccc2c1)C(=O)O",
    "btb": "OC(=O)c1ccc(cc1)-c1cc(cc(c1)-c1ccc(cc1)C(=O)O)"
           "-c1ccc(cc1)C(=O)O",
    "dobdc": "OC(=O)c1cc(O)c(cc1O)C(=O)O",
    "h4dobdc": "OC(=O)c1cc(O)c(cc1O)C(=O)O",
    "fumaric acid": "OC(=O)/C=C/C(=O)O",
    "oxalic acid": "OC(=O)C(=O)O",
    "succinic acid": "OC(=O)CCC(=O)O",
    "2-methylimidazole": "Cc1ncc[nH]1",
    "hmim": "Cc1ncc[nH]1",
    "imidazole": "c1c[nH]cn1",
    "benzimidazole": "c1ccc2[nH]cnc2c1",
    "4,4'-bipyridine": "c1cc(ccn1)-c1ccncc1",
    "bipy": "c1cc(ccn1)-c1ccncc1",
    "bpy": "c1cc(ccn1)-c1ccncc1",
    "pyrazine": "c1cnccn1",
    "dabco": "C1CN2CCN1CC2",
    "1,2,4-triazole": "c1nc[nH]n1",
    "tetrazole": "c1nnn[nH]1",
}


@dataclass(frozen=True)
class Salt:
    """A metal source as read: the metal and what came with it."""

    text: str
    metal: str
    anions: tuple[str, ...] = ()
    oxidation: int | None = None


_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}
_HYDRATE = re.compile(
    r"\s*(?:[·.*•]\s*(?:x|n|\d+(?:\.\d+)?)?\s*H2O"
    r"|\b(?:mono|di|tri|tetra|penta|hexa|hepta|octa|nona|deca)?"
    r"hydrate\b|\bhydrated\b)", re.IGNORECASE)


def _metal_names() -> dict[str, str]:
    names = {}
    for symbol, name in elements._NAMES.items():
        if symbol not in NONMETALS:
            names[name.lower()] = symbol
    names["aluminum"] = "Al"
    names["sulphur"] = "S"
    names["zirconyl"] = "Zr"
    return names


def read_salt(text: str) -> Salt:
    """A metal salt by name or formula -- or a bare metal.

    ``'zinc nitrate hexahydrate'``, ``'Zn(NO3)2·6H2O'``, ``'ZrOCl2'``,
    ``'copper(II) acetate'``, ``'Zr'``.  Water of crystallisation is
    dropped; it says nothing about which counter-ion is there.
    Raises :class:`PrecedentError` when no metal can be found, which is
    the one thing the vote cannot do without.
    """
    raw = str(text or "").strip()
    if not raw:
        raise PrecedentError("No metal source was given.")
    cleaned = _HYDRATE.sub(" ", raw).strip()
    words = re.findall(r"[a-z]+", cleaned.lower())
    names = _metal_names()
    metal = next((names[w] for w in words if w in names), None)
    if metal is not None:
        oxidation = None
        roman = re.search(r"\(\s*([ivx]+)\s*\)", cleaned.lower())
        if roman and roman.group(1) in _ROMAN:
            oxidation = _ROMAN[roman.group(1)]
        anions = []
        for key, _, spoken in ANIONS:
            if any(re.search(rf"{word}", cleaned.lower())
                   for word in spoken) and key not in anions:
                anions.append(key)
        if "zirconyl" in words and "O" not in anions:
            anions.append("O")
        # "oxychloride" names chloride as well as oxide, and the loop
        # finds both; "hydroxide" contains "oxide" and must not.
        if "OH" in anions and "O" in anions \
                and not re.search(r"\boxy|oxo|\boxide", cleaned.lower()):
            anions.remove("O")
        return Salt(raw, metal, tuple(anions), oxidation)
    return _read_formula(raw, cleaned)


def _read_formula(raw: str, text: str) -> Salt:
    compact = re.sub(r"\s+", "", text)
    match = re.match(r"([A-Z][a-z]?)", compact)
    if not match or elements.canonical_symbol(match.group(1)) is None \
            or match.group(1) in NONMETALS:
        raise PrecedentError(
            f"No metal could be read from {raw!r}: give a salt by name "
            f"('zinc nitrate hexahydrate'), a formula ('Zn(NO3)2') or "
            f"the metal's symbol.")
    metal = match.group(1)
    rest = compact[match.end():]
    anions = []
    while rest:
        rest = rest.lstrip("()[]0123456789.")
        if not rest:
            break
        for key, spellings, _ in ANIONS:
            hit = next((s for s in spellings if rest.startswith(s)
                        and not rest[len(s):len(s) + 1].islower()),
                       None)
            if hit:
                if key not in anions:
                    anions.append(key)
                rest = rest[len(hit):]
                break
        else:
            rest = rest[1:]
    return Salt(raw, metal, tuple(anions), None)


def read_solvents(texts) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Solvents as PubChem CIDs, and the names that could not be read.

    A name not in :data:`SOLVENTS` is handed back rather than guessed
    at, and said in the answer: a solvent left out moves the vote, so
    the person should know it was.  ``'CID 6228'`` is read as it is.
    """
    read, unread = [], []
    for text in texts or ():
        name = str(text).strip()
        if not name:
            continue
        cid = _SOLVENT_BY_NAME.get(name.lower())
        found = re.fullmatch(r"(?i)cid\s*:?\s*(\d+)", name)
        if cid is None and found:
            cid = int(found.group(1))
        if cid is None:
            unread.append(name)
        elif cid not in read:
            read.append(cid)
    return tuple(read), tuple(unread)


def solvent_name(cid: int) -> str:
    names = SOLVENTS.get(int(cid))
    if not names:
        return f"CID {cid}"
    short = min(names, key=len)
    return short.upper() if len(short) <= 4 and short != "py" \
        else names[0]


@lru_cache(maxsize=512)
def linker_key(text: str) -> tuple[str, frozenset]:
    """A linker's canonical SMILES and fingerprint bits.

    A name from :data:`LINKER_NAMES` or any SMILES.  Read neutral --
    the table's linkers are MOFid's carboxylates, written as anions,
    and a person types the acid -- so both are uncharged before they
    are compared.  Needs RDKit; the ``build`` extra.
    """
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdFingerprintGenerator
    from rdkit.Chem.MolStandardize import rdMolStandardize

    RDLogger.DisableLog("rdApp.*")
    smiles = LINKER_NAMES.get(str(text).strip().lower(),
                              str(text).strip())
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise PrecedentError(
            f"{text!r} is neither a SMILES nor a linker this knows by "
            f"name ({', '.join(sorted(LINKER_NAMES)[:6])}, ...).")
    molecule = rdMolStandardize.Uncharger().uncharge(molecule)
    canonical = Chem.MolToSmiles(molecule)
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=FP_RADIUS, fpSize=FP_BITS)
    bits = frozenset(generator.GetFingerprint(molecule).GetOnBits())
    return canonical, bits


@dataclass(frozen=True)
class Query:
    """A synthesis, read: everything the vote compares."""

    salt: Salt
    linkers: tuple[tuple[str, frozenset], ...]
    solvents: tuple[int, ...] = ()
    unread_solvents: tuple[str, ...] = ()
    temperature: float | None = None

    @classmethod
    def read(cls, metal: str, linkers, solvents=(),
             temperature: float | None = None) -> Query:
        texts = [t for t in (linkers or ()) if str(t).strip()]
        if not texts:
            raise PrecedentError("At least one linker is needed.")
        if len(texts) > 3:
            raise PrecedentError("At most three linkers.")
        read, unread = read_solvents(solvents)
        if temperature is not None and not -80 <= temperature <= 400:
            raise PrecedentError(
                f"{temperature} C is outside -80 to 400 C.")
        return cls(read_salt(metal), tuple(linker_key(t) for t in texts),
                   read, unread, temperature)


# ======================================================================
#  THE PRECEDENTS
# ======================================================================

@dataclass(frozen=True)
class Precedent:
    """One published structure: what formed and, if known, how.

    ``linkers`` index :meth:`Source.linker_bits`.  ``net`` is ``None``
    where MOFid could not name one, and such a record still votes on
    the node.  ``conditions`` is ``None`` for a structure whose
    synthesis was never extracted.
    """

    refcode: str
    metals: tuple[str, ...]
    nodes: tuple[str, ...]
    linkers: tuple[int, ...]
    net: str | None
    interpenetrated: bool | None
    anions: tuple[str, ...] | None = None
    solvents: tuple[int, ...] | None = None
    temperature: float | None = None

    @property
    def has_conditions(self) -> bool:
        return self.solvents is not None or self.anions is not None \
            or self.temperature is not None


class Source(Protocol):
    """Where precedents come from."""

    name: str

    def records(self) -> tuple[Precedent, ...]: ...

    def linker_bits(self) -> tuple[tuple[str, frozenset], ...]: ...


@dataclass
class BundledSource:
    """The table that ships: CoRE MOF 2024 joined with SynMOF-ME."""

    path: Path = TABLE
    name: str = "CoRE MOF 2024 + SynMOF-ME"
    _loaded: tuple | None = field(default=None, repr=False)

    def _load(self):
        if self._loaded is None:
            with gzip.open(self.path, "rt", encoding="utf-8") as handle:
                data = json.load(handle)
            linkers = tuple((row["smiles"], frozenset(row["bits"]))
                            for row in data["linkers"])
            records = tuple(_precedent(row) for row in data["records"])
            self._loaded = (records, linkers, data.get("sources", ()))
        return self._loaded

    def records(self) -> tuple[Precedent, ...]:
        return self._load()[0]

    def linker_bits(self) -> tuple[tuple[str, frozenset], ...]:
        return self._load()[1]

    def citations(self) -> tuple[str, ...]:
        return tuple(self._load()[2])


def _precedent(row: dict) -> Precedent:
    conditions = row.get("conditions")
    return Precedent(
        refcode=row["refcode"],
        metals=tuple(row["metals"]),
        nodes=tuple(row["nodes"]),
        linkers=tuple(row["linkers"]),
        net=row.get("net"),
        interpenetrated=row.get("interpenetrated"),
        anions=tuple(conditions["anions"])
        if conditions and conditions.get("anions") is not None else None,
        solvents=tuple(conditions["solvents"])
        if conditions and conditions.get("solvents") is not None
        else None,
        temperature=conditions.get("temperature") if conditions else None)


@lru_cache(maxsize=1)
def bundled() -> BundledSource:
    return BundledSource()


def available() -> bool:
    return TABLE.is_file()


# ======================================================================
#  SIMILARITY
# ======================================================================

#: Metals a node is often made of in each other's place: the same
#: charge and much the same radius.  Half credit, against one for the
#: metal itself and nothing otherwise.
ANALOGUES = (
    frozenset({"Zr", "Hf", "Ce", "Th", "U"}),
    frozenset({"Sc", "Y", "La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd",
               "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"}),
    frozenset({"Zn", "Cd", "Co"}),
    frozenset({"Cu", "Ni", "Co", "Zn"}),
    frozenset({"Fe", "Cr", "Al", "Ga", "In", "V", "Sc"}),
    frozenset({"Mn", "Fe", "Co", "Ni", "Mg"}),
    frozenset({"Ca", "Sr", "Ba"}),
    frozenset({"Li", "Na", "K", "Rb", "Cs"}),
    frozenset({"Ag", "Cu"}),
)


def metal_score(metal: str, metals) -> float:
    if metal in metals:
        return 1.0
    if any(metal in group and any(m in group for m in metals)
           for group in ANALOGUES):
        return 0.5
    return 0.0


def tanimoto(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 0.0
    shared = len(a & b)
    return shared / (len(a) + len(b) - shared)


def similarity(query: Query, precedent: Precedent,
               linker_bits) -> float:
    """How alike a query and a precedent are, 0 to 1.

    A weighted mean over :data:`WEIGHTS`.  The linker term is each
    query linker's best match among the precedent's, averaged.  A
    condition missing on either side scores :data:`UNKNOWN`.
    """
    terms = {"metal": metal_score(query.salt.metal, precedent.metals)}
    if precedent.linkers:
        terms["linker"] = sum(
            max(tanimoto(bits, linker_bits[i][1])
                for i in precedent.linkers)
            for _, bits in query.linkers) / len(query.linkers)
    else:
        terms["linker"] = 0.0
    if query.solvents and precedent.solvents is not None:
        mine, theirs = set(query.solvents), set(precedent.solvents)
        terms["solvent"] = len(mine & theirs) / len(mine | theirs) \
            if mine | theirs else UNKNOWN
    else:
        terms["solvent"] = UNKNOWN
    if query.temperature is not None \
            and precedent.temperature is not None:
        terms["temperature"] = math.exp(
            -abs(query.temperature - precedent.temperature)
            / TEMPERATURE_SCALE)
    else:
        terms["temperature"] = UNKNOWN
    if query.salt.anions and precedent.anions is not None:
        mine, theirs = set(query.salt.anions), set(precedent.anions)
        terms["anion"] = len(mine & theirs) / len(mine | theirs) \
            if mine | theirs else UNKNOWN
    else:
        terms["anion"] = UNKNOWN
    return sum(WEIGHTS[k] * v for k, v in terms.items()) \
        / sum(WEIGHTS.values())


# ======================================================================
#  THE VOTE
# ======================================================================

@dataclass(frozen=True)
class Share:
    """One outcome and the weight that voted for it."""

    value: str
    share: float
    support: int


@dataclass(frozen=True)
class Neighbour:
    precedent: Precedent
    similarity: float


@dataclass(frozen=True)
class Novelty:
    """How far the query is from anything in the table.

    Read before the shares: a vote among strangers is a guess.
    """

    closest: float
    metal_seen: bool
    linker_seen: bool
    metal_with_linker_seen: bool
    precedents: int

    def sentence(self) -> str:
        if self.metal_with_linker_seen:
            return ("This metal has been made into a framework with "
                    "this linker before.")
        if self.metal_seen and self.linker_seen:
            return ("The metal and the linker are each in the table, "
                    "but never together: the vote is by analogy.")
        missing = [what for what, seen in (
            ("metal", self.metal_seen), ("linker", self.linker_seen))
            if not seen]
        return (f"No precedent has this {' or this '.join(missing)}: "
                f"the vote is by analogy only.")


@dataclass(frozen=True)
class Forecast:
    """The answer: what the nearest precedents formed."""

    query: Query
    nodes: tuple[Share, ...]
    nets: tuple[Share, ...]
    interpenetrated: Share | None
    neighbours: tuple[Neighbour, ...]
    novelty: Novelty
    source: str
    basis: str = BASIS


def forecast(query: Query, source: Source | None = None,
             neighbours: int = NEIGHBOURS) -> Forecast:
    """Vote the nearest precedents on what this synthesis makes."""
    source = source or bundled()
    records = source.records()
    linker_bits = source.linker_bits()
    if not records:
        raise PrecedentError(f"{source.name} has no precedents.")
    scored = sorted(
        (Neighbour(p, similarity(query, p, linker_bits))
         for p in records),
        key=lambda n: (-n.similarity, n.precedent.refcode))
    nearest = tuple(scored[:max(1, neighbours)])
    return Forecast(
        query=query,
        # By the metals, not the SMILES: two papers write one Zr6
        # cluster with its mu3-O and OH in different places, and as
        # SMILES they would split the vote between them.
        nodes=_tally(nearest,
                     lambda p: tuple(node_formula(n) for n in p.nodes)),
        nets=_tally(nearest, lambda p: (p.net,) if p.net else ()),
        interpenetrated=_interpenetration(nearest),
        neighbours=nearest,
        novelty=_novelty(query, records, linker_bits, scored),
        source=source.name)


def _tally(nearest, outcomes) -> tuple[Share, ...]:
    """Each outcome's share of the weight of those that have one.

    A precedent with no net does not vote on the net, so the shares of
    the nets are out of the weight that named one -- otherwise every
    share shrinks with the number of records MOFid could not name.
    """
    weight, support = defaultdict(float), defaultdict(int)
    total = 0.0
    for n in nearest:
        found = set(outcomes(n.precedent))
        if not found:
            continue
        total += n.similarity
        for value in found:
            weight[value] += n.similarity / len(found)
            support[value] += 1
    if total <= 0:
        return ()
    return tuple(sorted(
        (Share(v, round(w / total, 3), support[v])
         for v, w in weight.items()),
        key=lambda s: (-s.share, s.value)))


def _interpenetration(nearest) -> Share | None:
    known = [n for n in nearest
             if n.precedent.interpenetrated is not None]
    total = sum(n.similarity for n in known)
    if not known or total <= 0:
        return None
    yes = [n for n in known if n.precedent.interpenetrated]
    return Share("interpenetrated",
                 round(sum(n.similarity for n in yes) / total, 3),
                 len(yes))


def _novelty(query, records, linker_bits, scored) -> Novelty:
    smiles = {s for s, _ in query.linkers}
    linker_ids = {i for i, (s, _) in enumerate(linker_bits)
                  if s in smiles}
    metal = query.salt.metal
    metal_seen = any(metal in p.metals for p in records)
    linker_seen = any(linker_ids & set(p.linkers) for p in records)
    together = any(metal in p.metals and linker_ids & set(p.linkers)
                   for p in records)
    return Novelty(
        closest=round(scored[0].similarity, 3) if scored else 0.0,
        metal_seen=metal_seen, linker_seen=linker_seen,
        metal_with_linker_seen=together, precedents=len(records))


def node_formula(smiles: str) -> str:
    """A node's metals, for a person: ``[Cu][Cu]`` is ``Cu2``.

    Only the metals are counted -- MOFid's node SMILES is the metals
    and whatever bridges them, and the bridges are what differ
    between writers.  The SMILES is kept beside it.
    """
    counts: dict[str, int] = {}
    for symbol in re.findall(r"\[([A-Z][a-z]?)", smiles):
        if symbol not in NONMETALS:
            counts[symbol] = counts.get(symbol, 0) + 1
    if not counts:
        return smiles
    return "".join(f"{s}{n if n > 1 else ''}"
                   for s, n in sorted(counts.items()))
