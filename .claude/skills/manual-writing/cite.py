"""Add a reference to the manual's bibliography, fetched, never typed.

    cite.py KEY 10.1021/jz3008485           # a DOI, from Crossref
    cite.py KEY arXiv:2504.06231            # a preprint, from arXiv
    cite.py --check                         # every entry still resolves

The manual cites by number, and a citation typed from memory is the
one kind of error a reader cannot catch: a plausible DOI that resolves
to the wrong paper, or a volume off by one.  So an entry is only ever
added by fetching it -- Crossref's own BibTeX for a DOI, the arXiv
API's metadata for a preprint -- and printed so the title can be read
against the paper the prose means before it is cited.

What is cleaned, and nothing else: HTML tags Crossref leaves in
titles (``<i>``, ``<scp>``), the box-drawing and hyphen characters
LaTeX has no glyph for, and acronyms braced so BibTeX keeps their
capitals.  Before citing a preprint, look for its published version
(``--check`` names any Crossref finds) and cite that instead.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BIB = ROOT / "docs" / "manual" / "references.bib"
AGENT = {"User-Agent": "CrystalBuilderManual/0.1 (cite.py)"}

#: Braced in titles so a BibTeX style's sentence case keeps them.
PROTECT = ["UFF", "UFF4MOF", "DFTB", "DFTB+", "DFTB3", "SCC-DFTB",
           "GFN2-xTB", "GFN-FF", "RCSR", "COD", "GEMMI", "MACE",
           "MOFSimBench", "MatterSim", "Orb-v3", "Spglib", "DFT-D",
           "Python", "Metal–Organic", "Metal—Organic", "Zeo++", "PXRD",
           "CIF", "MOF", "MOFs", "QEq", "EQeq"]
FIELDS = ["title", "author", "journal", "booktitle", "volume", "number",
          "pages", "year", "publisher", "doi", "eprint", "archiveprefix",
          "primaryclass"]


def _get(url: str) -> bytes:
    """One request, paced, and retried when the service says slow down:
    Crossref answers a burst of thirty lookups with 429."""
    for attempt in range(5):
        time.sleep(1.0 + 4.0 * attempt)
        request = urllib.request.Request(url, headers=AGENT)
        try:
            with urllib.request.urlopen(request, timeout=30) as reply:
                return reply.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
    raise RuntimeError(f"still rate-limited after five tries: {url}")


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", html.unescape(text))
    text = text.replace("─", "-").replace("‐", "-")
    return re.sub(r"\s+", " ", text).strip()


def _protect(title: str) -> str:
    for word in sorted(PROTECT, key=len, reverse=True):
        title = re.sub(rf"(?<![{{\w]){re.escape(word)}(?![\w}}])",
                       "{" + word + "}", title)
    return title


def from_doi(doi: str) -> tuple[str, dict]:
    raw = _get("https://api.crossref.org/works/"
               + urllib.parse.quote(doi)
               + "/transform/application/x-bibtex").decode("utf-8")
    match = re.match(r"\s*@(\w+)\{[^,]*,(.*)\}\s*$", raw, re.S)
    if not match:
        sys.exit(f"Crossref returned no BibTeX for {doi}")
    fields = dict(re.findall(r"(\w+)=\{((?:[^{}]|\{[^{}]*\})*)\}",
                             match.group(2)))
    kept = {k.lower(): _clean(v) for k, v in fields.items()
            if k.lower() in FIELDS}
    kept["title"] = _protect(kept["title"])
    return match.group(1), kept


def from_arxiv(ident: str) -> tuple[str, dict]:
    ns = {"a": "http://www.w3.org/2005/Atom",
          "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(_get("https://export.arxiv.org/api/query?id_list="
                              + ident))
    entry = root.find("a:entry", ns)
    if entry is None or entry.find("a:title", ns) is None:
        sys.exit(f"arXiv has no entry {ident}")
    return "misc", {
        "title": _protect(_clean(entry.find("a:title", ns).text)),
        "author": " and ".join(a.find("a:name", ns).text
                               for a in entry.findall("a:author", ns)),
        "year": entry.find("a:published", ns).text[:4],
        "eprint": ident, "archiveprefix": "arXiv",
        "primaryclass": entry.find("arxiv:primary_category",
                                   ns).get("term"),
    }


def render(key: str, kind: str, fields: dict) -> str:
    lines = [f"@{kind}{{{key},"]
    lines += [f"  {k} = {{{fields[k]}}}," for k in FIELDS if fields.get(k)]
    return "\n".join(lines + ["}", ""])


def keys(text: str) -> set[str]:
    return set(re.findall(r"^@\w+\{([^,]+),", text, re.M))


def check() -> int:
    """Every DOI still resolves on Crossref, and no preprint has a
    published version Crossref can find by its exact title."""
    text = BIB.read_text("utf-8")
    bad = 0
    for key, doi in re.findall(r"^@\w+\{([^,]+),[^@]*?doi = \{([^}]+)\}",
                               text, re.M | re.S):
        try:
            json.loads(_get("https://api.crossref.org/works/"
                            + urllib.parse.quote(doi)))
        except Exception as exc:                    # noqa: BLE001
            print(f"{key}: {doi} does not resolve ({exc})")
            bad += 1
    for key, title in re.findall(
            r"^@misc\{([^,]+),\s*title = \{(.+?)\},", text, re.M):
        plain = re.sub(r"[{}]", "", title)
        query = urllib.parse.urlencode({"query.title": plain, "rows": 3})
        items = json.loads(_get("https://api.crossref.org/works?"
                                + query))["message"]["items"]
        for item in items:
            found = _clean((item.get("title") or [""])[0])
            if found.lower() == plain.lower() and \
                    item.get("type") in ("journal-article",
                                         "proceedings-article"):
                print(f"{key}: published as {item['DOI']} -- cite that")
    print(f"{len(keys(text))} entries, {bad} unresolved")
    return 1 if bad else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("key", nargs="?")
    parser.add_argument("source", nargs="?",
                        help="a DOI, or arXiv:<identifier>")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    if not (args.key and args.source):
        parser.error("give a key and a DOI or arXiv:<id>")
    text = BIB.read_text("utf-8")
    if args.key in keys(text):
        sys.exit(f"{args.key} is already in {BIB.name}")
    if args.source.lower().startswith("arxiv:"):
        kind, fields = from_arxiv(args.source.split(":", 1)[1])
    else:
        kind, fields = from_doi(args.source)
    entry = render(args.key, kind, fields)
    BIB.write_text(text.rstrip("\n") + "\n\n" + entry, "utf-8")
    print(entry)
    print("Read the title against the paper you mean before citing it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
