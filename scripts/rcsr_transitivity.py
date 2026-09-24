"""Write the RCSR's transitivity table from the RCSR's own data files.

    python scripts/rcsr_transitivity.py            # rewrite the table
    python scripts/rcsr_transitivity.py --check    # exit 1 if it would change
    python scripts/rcsr_transitivity.py --fetch    # download both again first

Transitivity is four numbers, p q r s: how many kinds of vertex, edge,
face and tile a net has in its natural tiling.  The ``.cgd`` file the
application ships gives p and q, as NODE and EDGE lines, and nothing
about faces or tiles; the net search's r and s had nothing to match.
The RCSR publishes all four, in the files its own website reads:

* ``3dall.txt`` -- every 3-periodic net.  After a net's vertices and
  edges come the number of kinds of face and of tile; a net with no
  natural tiling on record writes 0 for both and an empty tiling line,
  and 0 is written here as *unknown*, not as a count.
* ``2dall.txt`` -- every layer, with p q r (vertex, edge, face) on one
  line.  A layer has no tiles, so its s is unknown.

The record layout is read the way the RCSR's own site reads it
(``rcsr.net/js/app.js``), because the files document themselves only
partly.  p and q are taken from here too, not from the ``.cgd``: the
two agree on all but 18 nets, and on those the ``.cgd`` repeats an
edge kind -- ``stz`` has nine EDGE lines for six kinds of edge.

Both downloads are kept in ``tests/data/rcsr/`` gzipped, exactly as
they arrived, so the suite can run this against them and fail if the
shipped table is not what they say.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tests" / "data" / "rcsr"
THREE_D = SOURCES / "3dall.txt.gz"
TWO_D = SOURCES / "2dall.txt.gz"
DOWNLOADED = "2026-09-24"
TABLE = (ROOT / "xtal" / "analysis" / "data"
         / f"rcsr-transitivity-{DOWNLOADED}.json.gz")

URLS = {THREE_D: "http://rcsr.net/data/3dall.txt",
        TWO_D: "http://rcsr.net/data/2dall.txt"}


def _lines(text: str) -> list[str]:
    """Every line trimmed, with the ``!`` comments the files carry
    (`` 3  !number of names``) taken off -- as the RCSR's site does."""
    return [re.sub(r"!.*$", "", line).strip()
            for line in text.split("\n")]


def _skip_block(lines, n: int, each: int = 1) -> int:
    """Past a counted block: a line holding a count, then that many
    items of ``each`` lines."""
    return n + 1 + int(lines[n]) * each


def _records(lines):
    """``(first line, symbol)`` of every record, up to the one whose
    serial number is negative -- the files end with one."""
    n = 0
    while True:
        while n < len(lines) and lines[n] != "start":
            n += 1
        if n >= len(lines) or int(lines[n + 1]) < 0:
            return
        yield n + 2, lines[n + 2]
        n += 3


def read_3d(text: str) -> dict[str, list]:
    """Name -> [p, q, r, s] for every 3-periodic net."""
    lines = _lines(text)
    out = {}
    for n, symbol in _records(lines):
        n += 2                                  # symbol, embed type
        for _ in range(5):   # other symbols, names, other names,
            n = _skip_block(lines, n)           # keywords, references
        n += 2                                  # space group, cell
        p = int(lines[n])
        n = _skip_block(lines, n, each=6)       # a vertex is six lines
        q = int(lines[n])
        n = _skip_block(lines, n, each=5)       # an edge is five
        faces, tiles = int(lines[n]), int(lines[n + 1])
        out[symbol] = [p, q, faces or None, tiles or None]
    return out


def read_2d(text: str) -> dict[str, list]:
    """Name -> [p, q, r, None] for every layer."""
    lines = _lines(text)
    out = {}
    for n, symbol in _records(lines):
        n += 1                          # the symbol; no embed type here
        for _ in range(4):   # other symbols, names, other names,
            n = _skip_block(lines, n)           # keywords
        n += 3                   # plane group, layer group, cell
        p, q, r = (int(v) for v in lines[n].split()[:3])
        out[symbol] = [p, q, r or None, None]
    return out


def table() -> dict:
    """The table this script writes, from the two kept downloads."""
    with gzip.open(THREE_D, "rt", encoding="utf-8",
                   errors="replace") as three, \
            gzip.open(TWO_D, "rt", encoding="utf-8",
                      errors="replace") as two:
        nets = {**read_3d(three.read()), **read_2d(two.read())}
    return {
        "format": 1,
        "about": ("Transitivity p q r s (kinds of vertex, edge, face, "
                  "tile) of every RCSR net, read from the RCSR's own "
                  "3dall.txt and 2dall.txt by "
                  "scripts/rcsr_transitivity.py.  null is unknown: a "
                  "3-D net with no natural tiling on record, and s for "
                  "every layer."),
        "sources": {"3d": URLS[THREE_D], "2d": URLS[TWO_D]},
        "downloaded": DOWNLOADED,
        "nets": dict(sorted(nets.items())),
    }


def _encoded(data: dict) -> bytes:
    # mtime=0 so that the same table is the same bytes, and --check can
    # compare them.
    text = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return gzip.compress(text, compresslevel=9, mtime=0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args(argv)
    if args.fetch:
        SOURCES.mkdir(parents=True, exist_ok=True)
        for path, url in URLS.items():
            with urllib.request.urlopen(url, timeout=120) as response:
                path.write_bytes(gzip.compress(response.read(),
                                               compresslevel=9, mtime=0))
    written = _encoded(table())
    if args.check:
        same = TABLE.exists() and TABLE.read_bytes() == written
        print("up to date" if same else f"{TABLE.name} would change")
        return 0 if same else 1
    TABLE.write_bytes(written)
    print(f"wrote {TABLE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
