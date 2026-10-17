"""
xtal.mof.invent
===============
New linkers for a requirement: an isoreticular series wider than the
stored one, put together on asking.

:func:`xtal.mof.linkers.series` is 114 molecules embedded once and
stored, so a suggestion is one of them or a catalogue block -- and a
span between two of them is a span nothing is offered for.  Here the
same idea is taken further, in carbon, hydrogen, nitrogen and oxygen
only: a chain of units (phenylene and its amino, hydroxy, methyl and
methoxy forms, the pyridine, pyrazine, pyrimidine and tetrazine rings,
naphthalene, anthracene, ethynylene, vinylene, azo) between two
donors, or arms of them round a core.  That is thousands of molecules,
too many to embed, so each is **estimated first**: a unit and the bond
that joins it add a length that is the same wherever it sits
(:data:`LENGTHS`, measured: a ring and its bond 4.2-4.3 A, an
ethynylene 2.54), and a core's own offset is read off the stored
series' shortest member on it.  Only the few estimated nearest are
embedded, and those are judged by what they measure, never by the
estimate; an embedding is kept for the process.

A name spells its molecule (``G-L-P_Pn_P-aryl``, ``G-T-amine-P-py``),
so a build asked for by name -- from the dialog, an agent or ``xtal
run`` -- makes the same molecule in a process that never suggested it
(:func:`by_name`).  Needs RDKit to embed; without it nothing is
invented.
"""

from __future__ import annotations

import itertools
import re

from xtal.mof import linkers

#: Each unit as a SMILES fragment from the atom that joins the unit
#: before it to the one the next joins, para or straight through.
#: Ring closures 2 and 3, so the core's 1 is never closed by an arm.
UNITS = {
    "P": "c2ccc(cc2)",                 # 1,4-phenylene
    "Pn": "c2c(N)cc(cc2)",             # 2-amino-, as in IRMOF-3
    "Po": "c2c(O)cc(cc2)",             # 2-hydroxy-
    "Pm": "c2c(C)cc(cc2)",             # 2-methyl-
    "Pmm": "c2c(C)cc(c(C)c2)",         # 2,5-dimethyl-
    "Poo": "c2c(O)cc(c(O)c2)",         # 2,5-dihydroxy-, as in dobdc
    "Pom": "c2c(OC)cc(cc2)",           # 2-methoxy-
    "Y": "c2ccc(nc2)",                 # pyridine-2,5-diyl
    "Z": "c2cnc(cn2)",                 # pyrazine-2,5-diyl
    "M": "c2ncc(cn2)",                 # pyrimidine-2,5-diyl
    "T": "c2nnc(nn2)",                 # 1,2,4,5-tetrazine-3,6-diyl
    "N": "c2ccc(c3ccccc23)",           # naphthalene-1,4-diyl
    "A": "c2c3ccccc3c(c3ccccc23)",     # anthracene-9,10-diyl
    "E": "C#C",                        # ethynylene
    "V": "/C=C/",                      # trans-vinylene
    "D": "/N=N/",                      # trans-azo
}

#: What a unit and the single bond joining it add to a span or a
#: radius, A: ``span(P-u-P) - span(P-P)`` with RDKit's embedding,
#: aryl-donor chains.  A test re-measures them.
LENGTHS = {
    "P": 4.32, "Pn": 4.31, "Po": 4.31, "Pm": 4.30, "Pmm": 4.29,
    "Poo": 4.32, "Pom": 4.31, "Y": 4.27, "Z": 4.30, "M": 4.23,
    "T": 4.18, "N": 4.27, "A": 4.30, "E": 2.54, "V": 2.37, "D": 1.85,
}

#: Units that are a ring, so may carry an aryl donor's point.
RINGS = tuple(u for u in UNITS if u not in ("E", "V", "D"))

#: What an arm is built of: the plain units.  A functional group or a
#: fused ring goes in the middle of a linear linker, once, as an
#: isoreticular series puts it (IRMOF-3's amine on BDC's ring).
ARM_UNITS = ("P", "E", "V", "Y")

#: Cores of branched linkers, the stored series' and the amine
#: (tris(4-pyridyl)amine and its extended cousins).
CORES = {3: dict(linkers._TRIGONAL, amine="N({R})({R}){R}"),
         4: linkers._TETRAGONAL, 6: linkers._HEXAGONAL}

#: How many of the estimated nearest are embedded on one asking.
EMBED = 6

#: An estimate this far outside the range is not embedded, A.
SLACK = 0.6

PREFIX = "G-"

_LETTERS = {2: "L", 3: "T", 4: "Q", 6: "H"}
_TOPICITY = {v: k for k, v in _LETTERS.items()}

#: smiles -> (value, formula), or None where it would not embed.
_embedded: dict[str, tuple[float, str] | None] = {}


def _arms(length: int):
    yield ()
    for n in range(1, length + 1):
        yield from itertools.product(ARM_UNITS, repeat=n)


def _linear_smiles(chain: tuple[str, ...], donor: str) -> str:
    body = "".join(UNITS[u] for u in chain)
    if donor == "aryl":
        return "*" + body + "*"
    return "*[n+]1ccc(cc1)" + body + "c1cc[n+](*)cc1"


def _branched_smiles(topicity: int, core: str, arm: tuple[str, ...],
                     donor: str) -> str:
    units = "".join(UNITS[u] for u in arm)
    end = "*" if donor == "aryl" else "c3cc[n+](*)cc3"
    return CORES[topicity][core].format(R=units + end)


def name_of(topicity: int, core: str, chain: tuple[str, ...],
            donor: str) -> str:
    """The name that spells a molecule; :func:`by_name` reads it."""
    units = "_".join(chain) or "0"
    tail = "aryl" if donor == "aryl" else "py"
    if topicity == 2:
        return f"{PREFIX}L-{units}-{tail}"
    return f"{PREFIX}{_LETTERS[topicity]}-{core}-{units}-{tail}"


_NAME = re.compile(r"^G-(?P<letter>[LTQH])-(?:(?P<core>[a-z]+)-)?"
                   r"(?P<units>[A-Za-z0-9_]+)-(?P<donor>aryl|py)$")


def by_name_is_one(name: str) -> bool:
    """Whether ``name`` is spelled as an invented linker's, asked
    without embedding it."""
    return bool(_NAME.match(str(name)))


def by_name(name: str) -> linkers.Candidate | None:
    """The invented linker ``name`` spells, embedded, or ``None`` for a
    name that is not one (or will not embed)."""
    found = _NAME.match(str(name))
    if not found:
        return None
    topicity = _TOPICITY[found["letter"]]
    units = () if found["units"] == "0" else tuple(
        found["units"].split("_"))
    donor = "aryl" if found["donor"] == "aryl" else "pyridyl"
    if any(u not in UNITS for u in units):
        return None
    if topicity == 2:
        if found["core"] or not units and donor == "aryl":
            return None
        smiles = _linear_smiles(units, donor)
    else:
        core = found["core"]
        if core not in CORES.get(topicity, {}):
            return None
        smiles = _branched_smiles(topicity, core, units, donor)
    return _candidate(name, topicity, donor, smiles)


def _candidate(name, topicity, donor, smiles):
    measured = _measure(smiles)
    if measured is None:
        return None
    value, formula = measured
    return linkers.Candidate(name, topicity, donor, value, "invented",
                             smiles, formula)


def _measure(smiles: str):
    if smiles not in _embedded:
        try:
            _embedded[smiles] = linkers.measure_smiles(smiles)
        except Exception:                           # noqa: BLE001
            # RDKit refusing one molecule is one fewer suggestion.
            _embedded[smiles] = None
    return _embedded[smiles]


def _bases() -> dict[tuple[int, str, str], float]:
    """(topicity, core, donor) -> the length a core and its donors add
    with no arm, read off the stored series: its shortest member on
    that core, less what its arm adds."""
    out = {}
    for c in linkers.stored():
        if c.topicity == 2:
            continue
        parts = c.name.split("-")
        if len(parts) != 4:
            continue
        _letter, core, arm, tail = parts
        donor = "aryl" if tail == "ar" else "pyridyl"
        arm = "" if arm == "0" else arm
        base = c.value - sum(LENGTHS[u] for u in arm)
        out.setdefault((c.topicity, core, donor), base)
    return out


#: The length two donors add to a linear chain, from ``L-P-*``.
_LINEAR_BASE = {"aryl": 4.29 - LENGTHS["P"],
                "pyridyl": 12.84 - LENGTHS["P"]}


def estimates(requirement) -> list[tuple[float, str, str]]:
    """``(estimate, name, smiles)`` for every molecule of the space
    that could meet ``requirement``, nearest first.  No RDKit."""
    donors = (("aryl", "pyridyl") if requirement.donor == "any"
              else (requirement.donor,))
    donors = [d for d in donors if d in ("aryl", "pyridyl")]
    out = []
    topicity = requirement.topicity
    if topicity == 2:
        for donor in donors:
            for arm in _arms(2):
                for core in ((),) + tuple((u,) for u in UNITS):
                    chain = arm + core + arm[::-1]
                    if donor == "aryl" and (not chain
                                            or chain[0] not in RINGS):
                        continue
                    value = _LINEAR_BASE[donor] + sum(
                        LENGTHS[u] for u in chain)
                    out.append((value, name_of(2, "", chain, donor),
                                _linear_smiles(chain, donor)))
    elif topicity in CORES:
        bases = _bases()
        trigonal = bases.get((3, "benzene", "pyridyl"))
        for donor in donors:
            for core in CORES[topicity]:
                base = bases.get((topicity, core, donor))
                if base is None and core == "amine" and trigonal:
                    # The amine's N to ring carbon is 1.42 against
                    # benzene's 1.40 out to its ring's edge: start
                    # from benzene's and let the embedding say.
                    base = (trigonal - 1.4 if donor == "pyridyl" else
                            bases.get((3, "benzene", "aryl"), 0) - 1.4)
                if base is None:
                    continue
                for arm in _arms(2 if topicity == 3 else 1):
                    if donor == "aryl" and (not arm
                                            or arm[-1] not in RINGS):
                        continue
                    if core == "amine" and arm and arm[0] not in RINGS:
                        continue
                    value = base + sum(LENGTHS[u] for u in arm)
                    out.append((value, name_of(topicity, core, arm,
                                               donor),
                                _branched_smiles(topicity, core, arm,
                                                 donor)))
    out.sort(key=lambda e: (abs(e[0] - requirement.value), e[1]))
    return out


def invent(requirement, n: int = EMBED,
           exclude=()) -> list[linkers.Candidate]:
    """Up to ``n`` new molecules that measure inside ``requirement``,
    nearest first: the estimates nearest it embedded, at most ``n``
    of them and none whose estimate is :data:`SLACK` outside the
    range.  ``exclude`` is SMILES already offered (the stored
    series).  Empty without RDKit."""
    from xtal.build import chem

    if not chem.installed():
        return []
    skip = set(exclude)
    tried, found = 0, []
    for value, name, smiles in estimates(requirement):
        if tried >= n:
            break
        if (value < requirement.low - SLACK
                or value > requirement.high + SLACK):
            break
        if smiles in skip:
            continue
        tried += 1
        made = _candidate(name, requirement.topicity,
                          "aryl" if name.endswith("aryl") else "pyridyl",
                          smiles)
        if made is not None and requirement.admits(made):
            found.append(made)
    found.sort(key=lambda c: abs(c.value - requirement.value))
    return found
