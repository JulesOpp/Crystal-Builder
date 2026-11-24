"""Join CoRE MOF 2024 and SynMOF-ME into the precedent table.

Writes ``xtal/mof/data/precedents.json.gz``, which
:mod:`xtal.mof.precedent` votes over.  Neither source is shipped or
fetched by this script; download them and name them:

* CoRE MOF 2024's ``mofid-v2.zip`` (CC-BY 4.0, Zenodo record
  15055758), unpacked -- the table read is
  ``mofid-v2/errors/ASR_mofid.csv``, one MOFid per structure;
* SynMOF's ``Synmof_Me_210618.csv`` (MIT,
  github.com/aimat-lab/MOF_Literature_Extraction, ``Literature
  Extraction/Databases/``).

    python scripts/synthesis_precedents.py ASR_mofid.csv \\
        Synmof_Me_210618.csv

Then it holds the table to itself: a sample of the syntheses with
conditions and a named net, each voted on with its own record taken
out, and how often the net that was made is among the first five.
That is the number to quote, and it is printed, not stored.  Needs
RDKit.
"""

import csv
import gzip
import json
import random
import re
import sys
import time
from pathlib import Path

from xtal.mof import precedent

SOURCES = (
    "CoRE MOF 2024 (MOFid v1 of the ASR set): Zhao, G. et al., "
    "Matter 8, 102140 (2025); doi:10.5281/zenodo.15055758; CC-BY 4.0.",
    "SynMOF-ME: Luo, Y. et al., Angew. Chem. Int. Ed. 61, e202200242 "
    "(2022); github.com/aimat-lab/MOF_Literature_Extraction; MIT.",
)

#: MOFid's words for a net it could not name.  Every RCSR symbol is
#: lower case, and these are what the upper-case ones in the table
#: are; a new one is a vote for a net called TIMEOUT.
NOT_A_NET = {"UNKNOWN", "ERROR", "NA", "MISMATCH", "TIMEOUT", ""}


def refcode(name: str) -> str:
    """The CSD refcode family a CoRE file or a SynMOF row is named for.

    ``ZUYSEU_ASR_pacman`` and ``ZUYSEU_clean`` are both ``ZUYSEU``,
    and so is ``ZUYSEU01``: the two digits are a re-determination of
    the same compound, and UiO-66's eleven (``WIZMAV02`` to ``13``)
    were eleven votes for one paper's ``fcu``.  A structure from a
    paper's SI has no refcode and keeps its name.
    """
    head = re.split(r"[_.]", name)[0]
    return head[:6].upper() \
        if re.fullmatch(r"[A-Za-z]{6}(\d\d)?", head) else name


def read_mofid(text: str):
    """Nodes, linkers, net and interpenetration from one MOFid v1."""
    smiles, _, tail = text.partition(" MOFid-v1.")
    if not tail:
        return None
    fields = tail.split(";")[0].split(".")
    nets = fields[0].split(",") if fields else []
    net = next((n for n in nets if n not in NOT_A_NET), None)
    cat = fields[1] if len(fields) > 1 else ""
    found = re.fullmatch(r"cat(\d+)", cat)
    interpenetrated = int(found.group(1)) > 0 if found else None
    nodes, linkers = [], []
    for fragment in smiles.split("."):
        atoms = re.findall(r"\[([A-Z][a-z]?)", fragment)
        if any(a not in precedent.NONMETALS for a in atoms):
            nodes.append(fragment)
        elif fragment:
            linkers.append(fragment)
    return nodes, linkers, net, interpenetrated


def read_conditions(row: dict) -> tuple[str, dict]:
    anions, solvents = [], []
    for i in range(1, 6):
        for part in (row.get(f"counterions{i}") or "").split("|"):
            key = precedent.ANION_ALIASES.get(part.strip(), part.strip())
            if key and key not in anions:
                anions.append(key)
        cid = (row.get(f"solvent{i}") or "").strip()
        if cid:
            solvents.append(int(float(cid)))
    temperature = None
    try:
        temperature = float(row["temperature_Celsius"])
    except (KeyError, ValueError):
        pass
    return refcode(row["filename"]), {
        "metal": row.get("metal_ele1") or None,
        "anions": anions or None,
        "solvents": solvents or None,
        "temperature": temperature}


def build(core_csv: Path, synmof_csv: Path) -> dict:
    conditions = {}
    with open(synmof_csv, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            code, found = read_conditions(row)
            conditions.setdefault(code, found)
    linkers, index, records = [], {}, []
    skipped = 0
    with open(core_csv, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            parsed = read_mofid(row["mofid"])
            if parsed is None or not parsed[0]:
                skipped += 1
                continue
            nodes, smiles, net, interpenetrated = parsed
            ids = []
            for text in smiles:
                try:
                    canonical, bits = precedent.linker_key(text)
                except precedent.PrecedentError:
                    continue
                if canonical not in index:
                    index[canonical] = len(linkers)
                    linkers.append({"smiles": canonical,
                                    "bits": sorted(bits)})
                if index[canonical] not in ids:
                    ids.append(index[canonical])
            metals = sorted({a for n in nodes
                             for a in re.findall(r"\[([A-Z][a-z]?)", n)
                             if a not in precedent.NONMETALS})
            code = refcode(row["cifname"])
            known = conditions.get(code)
            records.append({
                "refcode": code, "metals": metals,
                "nodes": sorted(set(nodes)), "linkers": ids,
                "net": net, "interpenetrated": interpenetrated,
                "conditions": {k: known[k] for k in
                               ("anions", "solvents", "temperature")}
                if known else None})
    # One compound determined twice is one precedent, not two votes;
    # the determination MOFid could name a net for stands for it.
    best = {}
    for record in records:
        kept = best.get(record["refcode"])
        if kept is None or (record["net"] and not kept["net"]):
            best[record["refcode"]] = record
    unique = list(best.values())
    print(f"{len(unique)} precedents ({skipped} MOFids unread, "
          f"{len(records) - len(unique)} duplicates), "
          f"{sum(1 for r in unique if r['conditions'])} with "
          f"conditions, {sum(1 for r in unique if r['net'])} with a "
          f"named net, {len(linkers)} distinct linkers")
    return {"version": 1, "sources": list(SOURCES),
            "linkers": linkers, "records": unique}


def held_out(source, sample: int = 300, seed: int = 1,
             neighbours: int = precedent.NEIGHBOURS):
    """How often the made net is first, and in the first five.

    Each synthesis with conditions and a named net is voted on with
    its own refcode family taken out.  Returns ``(n, first, five)``,
    the last two as fractions; :data:`precedent.BASIS` quotes them,
    and a test holds the two together.
    """
    records = source.records()
    bits = source.linker_bits()
    testable = [r for r in records
                if r.net and r.has_conditions and r.linkers and r.metals]
    rng = random.Random(seed)
    chosen = rng.sample(testable, min(sample, len(testable)))
    top1 = top5 = 0
    for record in chosen:
        query = precedent.Query(
            salt=precedent.Salt(record.refcode, record.metals[0],
                                record.anions or ()),
            linkers=tuple(bits[i] for i in record.linkers),
            solvents=record.solvents or (),
            temperature=record.temperature)
        rest = _Without(source, record)
        nets = [s.value for s in precedent.forecast(
            query, rest, neighbours=neighbours).nets]
        top1 += bool(nets) and nets[0] == record.net
        top5 += record.net in nets[:5]
    n = len(chosen)
    return n, top1 / n, top5 / n


class _Without:
    def __init__(self, source, record):
        self.name = source.name
        self._records = tuple(r for r in source.records()
                              if r.refcode != record.refcode)
        self._bits = source.linker_bits()

    def records(self):
        return self._records

    def linker_bits(self):
        return self._bits


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    start = time.perf_counter()
    table = build(Path(argv[0]), Path(argv[1]))
    precedent.TABLE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(precedent.TABLE, "wt", encoding="utf-8",
                   compresslevel=9) as handle:
        json.dump(table, handle, separators=(",", ":"))
    print(f"-> {precedent.TABLE} "
          f"({precedent.TABLE.stat().st_size / 1e6:.1f} MB) in "
          f"{time.perf_counter() - start:.0f} s")
    n, first, five = held_out(precedent.BundledSource())
    print(f"held out {n} syntheses with conditions: the net made was "
          f"first in {first:.0%} and in the first five in {five:.0%} "
          f"-- if these differ from precedent.BASIS, update it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
