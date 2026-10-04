"""Write ORCA's basis sets and solvents from the ORCA manual's tables.

    python scripts/orca_tables.py MANUAL.pdf            # rewrite it
    python scripts/orca_tables.py MANUAL.pdf --check    # exit 1 if stale

The ORCA input dialog offers every orbital basis set ORCA 6.1 has
built in, family by family, and says when one does not cover an
element of the structure.  Both need the manual's Tables 2.12-2.33:
the keyword, the elements it covers, and the ECP or relativistic
Hamiltonian it comes with.  The solvation box needs Table 2.56: which
solvents C-PCM and SMD each know.  There are some 450 basis rows and
270 solvents, and copied out by hand they would be wrong somewhere
nobody looked, so this reads them off the manual -- through
Ghostscript's text device, which keeps the table columns where they
were printed.

The manual is not ours to ship, so only what this writes is in the
repository (``xtal/orca/data/tables.json``); the functionals,
fewer than a hundred and in tables whose columns wrap their keywords,
are written out by hand in :mod:`xtal.orca.catalogue`.

A row is read by the columns its table's header puts the words at,
because an element list can wrap ("H-He, B-" over "Ne,Al-Ar") and so
can a keyword ("6-311++G(2df," over "2pd)").  Anything that is not a
keyword over a list of real elements -- a sub-heading, a page footer,
the prose after a table -- is skipped rather than guessed at.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xtal.core import elements as el  # noqa: E402

OUT = ROOT / "xtal" / "orca" / "data" / "tables.json"

#: Table number -> the family the dialog shows it under.
FAMILIES = {
    "2.12": "Pople",
    "2.13": "Ahlrichs (def)",
    "2.14": "Karlsruhe def2",
    "2.15": "Karlsruhe dhf",
    "2.16": "Jensen (pc)",
    "2.17": "Hydrogenic Gaussian (HGBS)",
    "2.18": "Sapporo",
    "2.19": "Partridge",
    "2.20": "CRENB",
    "2.21": "LANL",
    "2.22": "Correlation-consistent",
    "2.23": "F12",
    "2.24": "ANO",
    "2.25": "Miscellaneous",
    "2.26": "Relativistic Ahlrichs",
    "2.27": "Relativistic Karlsruhe",
    "2.28": "Relativistic SARC",
    "2.29": "Relativistic SARC2",
    "2.30": "Relativistic x2c",
    "2.31": "Relativistic Sapporo",
    "2.32": "Relativistic correlation-consistent",
    "2.33": "Relativistic ANO-RCC",
}

_TITLE = re.compile(r"^\s*Table (2\.\d+)(:| – continued)")
_KEYWORD = re.compile(r"^[A-Za-z0-9][\w\-()+*,/'.]*$")
_SYMBOL = r"[A-Z][a-z]?"
_RANGE_TAIL = re.compile(rf"({_SYMBOL}(?:–{_SYMBOL})?)$")
_FURNITURE = ("ORCAManual", "continues on next page",
              "Essential Calculation Elements", "2.7. Basis Sets")


#: The PDF pages (not the printed numbers, which are 18 fewer) that
#: hold Tables 2.12-2.33 and 2.56 in the 6.1 manual, with a page to
#: spare each side.  Reading only these is a second; the whole manual
#: is thirty-four.
PAGES = ((78, 98), (143, 152))


def manual_text(pdf: Path, pages=PAGES) -> str:
    """The manual as Ghostscript lays it out, columns kept."""
    gs = shutil.which("gs")
    if gs is None:
        raise RuntimeError("Ghostscript (gs) is needed to read the "
                           "manual")
    parts = []
    with tempfile.TemporaryDirectory() as tmp:
        for first, last in pages:
            out = Path(tmp) / f"{first}.txt"
            subprocess.run([gs, "-q", "-dNOPAUSE", "-dBATCH",
                            "-sDEVICE=txtwrite", f"-dFirstPage={first}",
                            f"-dLastPage={last}", f"-sOutputFile={out}",
                            str(pdf)], check=True)
            parts.append(out.read_text(encoding="utf-8",
                                       errors="replace"))
    return "\n".join(parts)


def symbols(text: str) -> list[str] | None:
    """``"H–He, B–Ne,Al–Ar"`` as every symbol it covers, or None when
    it is not an element list at all."""
    text = text.replace(" ", "").strip(",")
    if not text:
        return None
    out: list[str] = []
    for part in text.split(","):
        ends = part.split("–")
        if len(ends) > 2 or not all(re.fullmatch(_SYMBOL, e)
                                    for e in ends):
            return None
        try:
            lo, hi = (el.atomic_number(e) for e in (ends[0], ends[-1]))
        except Exception:
            return None
        if lo < 1 or hi < lo:
            return None
        out += [el.symbol_from_z(z) for z in range(lo, hi + 1)]
    return out


def _partial(text: str) -> bool:
    """Whether ``text`` is an element list, or one cut off mid-range
    by a line break ("Hf–Bi,U–" before "Pu")."""
    text = text.rstrip(",")
    return symbols(text[:-1] if text.endswith("–") else text) \
        is not None


def _balanced(word: str) -> bool:
    return word.count("(") == word.count(")") and not word.endswith(",")


def read_tables(text: str) -> list[dict]:
    families: dict[str, list[dict]] = {}
    table = None
    columns = None
    for line in text.splitlines():
        title = _TITLE.match(line)
        if title:
            number = title.group(1)
            table = number if number in FAMILIES else None
            columns = None
            continue
        if table is None:
            continue
        if "Basis Set" in line and "Elem." in line:
            columns = (line.index("Basis Set"), line.index("Elem."),
                       line.index("Comment"))
            third = re.search(r"Elem\.\s+(\S+)", line)
            columns += (line.index(third.group(1), columns[1] + 5),)
            continue
        if columns is None or any(f in line for f in _FURNITURE):
            continue
        start, elem, comment, third = columns
        if not line.strip() or line[start - 1:start].strip():
            continue                    # prose, starting left of it
        # Split on words rather than at the column: a long keyword
        # pushes the element list a place right ("DKH-def2-TZVP(-f)
        # H–Kr"), and a longer one runs into it.
        words = line[start:third].split(None, 1)
        if line[start:start + 1].strip():
            lead = words[0]
            span = words[1].strip() if len(words) > 1 else ""
            tail = _RANGE_TAIL.search(lead)
            if not span and tail and symbols(tail.group(1)) and \
                    len(lead) > elem - start:
                # "Sapporo-DKH3-DZP-2012K–Rn"
                lead, span = lead[:tail.start()], tail.group(1)
        else:
            lead, span = "", " ".join(words)
        rest = line[third:comment].strip()
        rows = families.setdefault(table, [])
        if lead and not span:
            # A keyword that wrapped, or a sub-heading.
            if rows and not _balanced(rows[-1]["key"]):
                rows[-1]["key"] += lead
            continue
        if not lead and span:
            # A wrapped element list, and the ECP cell beside it.
            # Only then: the prose under a table is indented as far.
            joined = rows[-1]["elements"] + span.replace(" ", "") \
                if rows else ""
            if rows and _partial(joined):
                rows[-1]["elements"] = joined
                if rest:
                    rows[-1]["extra"] += " " + rest
            continue
        if not lead and not span:
            if rows and rest and rows[-1]["extra"].count("(") > \
                    rows[-1]["extra"].count(")"):
                rows[-1]["extra"] += " " + rest    # an ECP cell wraps
            continue
        if not (lead and _KEYWORD.match(lead)):
            continue
        rows.append({"key": lead, "elements": span.replace(" ", ""),
                     "extra": rest})
    out = []
    for number, name in FAMILIES.items():
        rows = families.get(number, [])
        bases = []
        seen = set()
        for row in rows:
            if row["key"] in seen or symbols(row["elements"]) is None:
                continue
            seen.add(row["key"])
            extra = re.sub(r"–\s+", "–",
                           " ".join(row["extra"].split())).rstrip(",")
            kind = "relativistic" if number >= "2.26" else "ecp"
            bases.append({"key": row["key"],
                          "elements": row["elements"],
                          kind: "" if extra in ("–", "-") else extra})
        out.append({"family": name, "table": number, "bases": bases})
    return out


#: Where Table 2.56's X falls, past its C-PCM heading, for each model.
#: The marks are not under their headings -- the heading row is set
#: tighter than the rows -- and drift a column or two page to page,
#: so a mark is the nearest of these.
_SOLVENT_COLUMNS = (("CPCM", 0), ("SMD", 11), ("COSMO-RS", 20),
                    ("ALPB", 36))


def read_solvents(text: str) -> list[dict]:
    """Table 2.56: every solvent, its names, and the models that know
    it.  Only C-PCM and SMD are kept: COSMO-RS is a separate run type
    and ALPB is xTB's."""
    out = []
    inside = False
    heading = None
    for line in text.splitlines():
        title = re.match(r"^\s*Table (2\.\d+)", line)
        if title:
            inside = title.group(1) == "2.56"
            heading = None
            continue
        if not inside:
            continue
        if "Solvent" in line and "C-PCM" in line:
            heading = line.index("C-PCM")
            continue
        if heading is None or any(f in line for f in _FURNITURE):
            continue
        marks = [m.start() - heading
                 for m in re.finditer(r"(?<=\s)X(?=\s|$)", line)]
        if not marks:
            continue
        name = line[:heading + _SOLVENT_COLUMNS[0][1] - 2].strip()
        if not name:
            continue
        models = {min(_SOLVENT_COLUMNS, key=lambda c: abs(c[1] - x))[0]
                  for x in marks}
        names = [n.strip() for n in name.split(" / ")]
        out.append({"names": names,
                    "cpcm": "CPCM" in models, "smd": "SMD" in models})
    return [s for s in out if s["cpcm"] or s["smd"]]


def render(families: list[dict], solvents: list[dict]) -> str:
    doc = {"source": "ORCA 6.1 manual, Tables 2.12-2.33 and 2.56",
           "written_by": "scripts/orca_tables.py",
           "families": families,
           "solvents": solvents}
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manual", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    manual = manual_text(args.manual)
    text = render(read_tables(manual), read_solvents(manual))
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("up to date" if same else f"{OUT} would change")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    doc = json.loads(text)
    count = sum(len(f["bases"]) for f in doc["families"])
    print(f"wrote {count} basis sets and {len(doc['solvents'])} "
          f"solvents to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
