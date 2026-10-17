"""Write the merged-net table from the merged-nets paper's data.

    python scripts/merged_nets.py DATA_DIR SM.pdf            # rewrite
    python scripts/merged_nets.py DATA_DIR SM.pdf --rejects  # PORMAKE

``DATA_DIR`` is the paper's ``science.ads7866_data_s1_to_s8`` folder
and ``SM.pdf`` its supplementary text (Jiang et al., Science 386, 659
(2024)).  Neither is ours to ship, so only what this writes is in the
repository: ``xtal/mof/data/merged_nets.json`` (one row per net:
parents, coordinations, edge ratio, platforms, MOFs made, and what
each set of its edge kinds spans) and ``merged_nets.cgd.gz`` (Data
S6's ``.cgd`` for every net, Systre-relaxed).

* Data S1 (xlsx): the net, its two parents and their coordinations,
  the merged coordinations and the type.
* Data S6 (zip): ``cgd/<net>.cgd``; the ``-a`` augmented nets are
  left out.
* Data S7 (zip): ``sim_<net>_<clusters>.cif``, the proposed platforms.
* Data S8 (zip): ``<M>-<net>-MOF-<n>``, the MOFs the paper made.
* The SM's tables S9-S12, through Ghostscript's text device: each
  net's original and Systre edge ratio.  Three to a line, and a row
  the text device scrambled is left out rather than guessed (54).

The decomposition is :func:`xtal.analysis.components.components` on
each net's own file, three processes at a time (the slowest net is
about ten seconds), and it is what ``test_every_merged_net_row_
decomposes_into_its_listed_parents`` holds every row to.

``--rejects`` instead reads every net the catalogue would offer
through the vendored PORMAKE and prints the ones it refuses, for
:data:`xtal.mof.merged_nets.REJECTS`.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "xtal" / "mof" / "data"

#: Lines of the SM's text between which tables S9-S12 lie: after
#: Table S8's caption and before Table S13's.
_RATIO = re.compile(r"(?<![\w-])([a-z]{3}(?:-[a-z0-9]+)*)\s+"
                    r"(non|1|\d?\.\d+)\s+(non|1|\d?\.\d+)")

#: MOFs the SM names as made on a merged net besides Data S8's.
CITED = {"sph": ("Tb-sph-MOF-3",)}


def rows(data: Path) -> list[tuple]:
    import openpyxl

    book = openpyxl.load_workbook(
        next(data.glob("*data_s1.xlsx")), read_only=True)
    out = []
    for r in list(book.worksheets[0].iter_rows(values_only=True))[1:]:
        if r[0] and r[8]:
            out.append(tuple(r[:9]))
    return out


def cgd_texts(data: Path) -> dict[str, str]:
    out = {}
    with zipfile.ZipFile(next(data.glob("*data_s6.zip"))) as z:
        for info in z.infolist():
            path = info.filename
            if ("__MACOSX" in path or not path.endswith(".cgd")
                    or "/cgd/" not in path):
                continue
            stem = Path(path).stem
            if not stem or stem.endswith("-a"):
                continue
            out[stem] = z.read(info).decode("utf-8", "replace")
    return out


def proposed(data: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with zipfile.ZipFile(next(data.glob("*data_s7.zip"))) as z:
        for path in z.namelist():
            name = Path(path).name
            if "__MACOSX" in path or not name.startswith("sim_"):
                continue
            net, _, clusters = name[4:-4].partition("_")
            out.setdefault(net, []).append(clusters)
    return out


def made(data: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with zipfile.ZipFile(next(data.glob("*data_s8.zip"))) as z:
        for path in z.namelist():
            name = Path(path).name
            found = re.match(r"^([A-Z][a-z]?-([a-z-]+)-MOF(?:-\d+)?) - ",
                             name)
            if "__MACOSX" in path or not found or not name.endswith(".cif"):
                continue
            out.setdefault(found[2], []).append(found[1])
    for net, names in CITED.items():
        out.setdefault(net, []).extend(names)
    return out


def ratios(sm: Path, names: set[str]) -> dict[str, tuple[str, str]]:
    with tempfile.TemporaryDirectory() as tmp:
        text = Path(tmp) / "sm.txt"
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                        "-sDEVICE=txtwrite", f"-sOutputFile={text}",
                        str(sm)], check=True)
        lines = text.read_text(errors="replace").splitlines()
    lines = [re.sub(r"\s+", " ", line) for line in lines]
    start = next(i for i, line in enumerate(lines)
                 if line.strip().startswith("Table S8."))
    end = next(i for i, line in enumerate(lines)
               if i > start and line.strip().startswith("Table S13."))
    out: dict[str, tuple[str, str]] = {}
    for line in lines[start:end]:
        for m in _RATIO.finditer(line):
            if m[1] in names:
                out.setdefault(m[1], (m[2], m[3]))
    return out


def decompose(item) -> tuple[str, list[dict]]:
    name, text = item
    from xtal.analysis import components as C
    from xtal.io.cgd import read_cgd_string

    entry = read_cgd_string(text).entries[0]
    net, kinds = C.entry_kinds(entry)
    parts = []
    for c in C.components(net, kinds):
        part = {"kinds": list(c.kinds), "periodicity": c.periodicity}
        if c.name:
            part["name"] = c.name
        if c.periodicity == 0 and c.pieces:
            piece = c.net.components()[0]
            degrees = sorted({piece.degree(v)
                              for v in range(piece.n_vertices)})
            part["shape"] = [piece.n_vertices, degrees]
        parts.append(part)
    return name, parts


def write(data: Path, sm: Path, workers: int) -> int:
    table = rows(data)
    texts = cgd_texts(data)
    names = {r[0] for r in table}
    ratio = ratios(sm, names)
    plans, mofs = proposed(data), made(data)
    start = time.perf_counter()
    todo = sorted((n, texts[n]) for n in names if n in texts)
    with ProcessPoolExecutor(workers) as pool:
        parts = dict(pool.map(decompose, todo))
    print(f"decomposed {len(parts)} nets in "
          f"{time.perf_counter() - start:.0f} s", file=sys.stderr)
    out = []
    for name, pn1, cpn1, pn2, cpn2, c1, c2, c3, kind in table:
        if name not in texts:
            print(f"{name}: no .cgd in Data S6, left out",
                  file=sys.stderr)
            continue
        out.append({
            "name": name, "type": kind,
            "parents": [pn1, pn2],
            "parent_cn": [str(cpn1), str(cpn2)],
            "cn": [str(c) for c in (c1, c2, c3) if c is not None],
            **({"ratio": list(ratio[name])} if name in ratio else {}),
            **({"proposed": sorted(plans[name])} if name in plans else {}),
            **({"made": mofs[name]} if name in mofs else {}),
            "parts": parts[name],
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "merged_nets.json").write_text(
        json.dumps(out, indent=0, sort_keys=False) + "\n",
        encoding="utf-8")
    kept = [texts[r["name"]].strip() + "\n" for r in out]
    with gzip.open(OUT / "merged_nets.cgd.gz", "wt",
                   encoding="utf-8") as handle:
        handle.write("\n".join(kept))
    print(f"wrote {len(out)} rows", file=sys.stderr)
    return 0


def rejects() -> int:
    import logging

    from xtal.mof import catalog, merged_nets
    from xtal.mof.build import import_pormake

    pormake = import_pormake()
    logging.getLogger("pormake").setLevel(logging.CRITICAL)
    kept = merged_nets.REJECTS
    merged_nets.REJECTS = frozenset()
    merged_nets._topologies.cache_clear()
    try:
        nets = merged_nets.topologies(catalog.taken_names())
    finally:
        merged_nets.REJECTS = kept
        merged_nets._topologies.cache_clear()
    refused = []
    for topology in nets:
        try:
            topology._pormake(pormake)
        except Exception as exc:                    # noqa: BLE001
            refused.append(topology.name)
            print(f"refused {topology.name}: {exc}", file=sys.stderr)
    print(f"{len(nets)} nets read; {len(refused)} refused:")
    print(", ".join(f'"{n}"' for n in sorted(refused)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("data", type=Path, nargs="?")
    parser.add_argument("sm", type=Path, nargs="?")
    parser.add_argument("--rejects", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.rejects:
        return rejects()
    if not args.data or not args.sm:
        parser.error("DATA_DIR and SM.pdf are needed to write the table")
    return write(args.data, args.sm, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
