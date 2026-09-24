"""Write the COD half of Open Sample from the Crystallography Open Database.

    python scripts/fetch_cod_samples.py            # download and rewrite
    python scripts/fetch_cod_samples.py --check    # exit 1 if it would change
    python scripts/fetch_cod_samples.py --from DIR # strip files already here

Six frameworks everybody meets, each as the depositors wrote it: the
asymmetric unit, in its published space group and setting, with the
citation, the COD's own record and the refinement statistics kept.
What is taken out is what describes the *experiment* rather than the
crystal -- the reflection list, the diffractometer, and the SHELX
``.res`` / ``.hkl`` files and PLATON SQUEEZE report some depositions
embed whole.  Those are 97 % of UiO-66's 286 KB and NU-1000's 301 KB,
and nothing in this application reads them.

**The strip is by whole item and whole loop, never by reformatting.**
A CIF parsed and written back comes out in the writer's layout, which
would make every file a diff against the COD's and leave nobody able
to tell what was changed from what was re-spelled.  Each item or loop
here is kept byte for byte or dropped whole, and the result is read
back through gemmi, which must find every tag it found before except
the dropped ones.

COD data are CC0 (https://www.crystallography.net/cod/): no licence
travels with them, which is why these may ship where the CCDC-headed
files beside them are a decision recorded in ``PROVENANCE.md``.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import gemmi

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "resources" / "samples" / "cod"

URL = "https://www.crystallography.net/cod/{}.cif"

#: COD ID -> the file it is written as.  The names are what the tab
#: and the workspace entry are called, so they are the framework's.
ENTRIES = {
    1516287: "MOF-5.cif",
    4002052: "HKUST-1.cif",
    7249359: "ZIF-8.cif",
    4512072: "UiO-66.cif",
    4000663: "MIL-101.cif",
    7230579: "NU-1000.cif",
}

#: Tag prefixes whose items and loops are dropped.  Each describes the
#: measurement or the refinement program's files, never the structure.
STRIPPED = (
    "_refln",
    "_diffrn",
    "_shelx_",
    "_platon_squeeze",
)


def _stripped(tag: str) -> bool:
    return tag.lower().startswith(STRIPPED)


def _chunks(lines: list[str]):
    """The file as (tags, lines) pieces: one item, one loop, or text
    between them with no tags at all.

    A value in a ``;`` text field may start a line with ``_`` or say
    ``loop_``, so the fields are stepped over whole rather than read
    for keywords.
    """
    i, n = 0, len(lines)
    loose: list[str] = []
    while i < n:
        word = lines[i].strip().split(maxsplit=1)
        head = word[0].lower() if word else ""
        if head == "loop_":
            if loose:
                yield [], loose
                loose = []
            start, i = i, i + 1
            tags = []
            while i < n and lines[i].lstrip().startswith("_"):
                tags.append(lines[i].split()[0])
                i += 1
            i = _values(lines, i)
            yield tags, lines[start:i]
        elif head.startswith("_"):
            if loose:
                yield [], loose
                loose = []
            start = i
            tag = lines[i].split()[0]
            i += 1
            if len(lines[start].split(maxsplit=1)) == 1:
                i = _one_value(lines, i)
            yield [tag], lines[start:i]
        else:
            loose.append(lines[i])
            i += 1
    if loose:
        yield [], loose


def _text_field_end(lines: list[str], i: int) -> int:
    """The line after the ``;`` that closes the field opened at ``i``."""
    i += 1
    while not lines[i].startswith(";"):
        i += 1
    return i + 1


def _one_value(lines: list[str], i: int) -> int:
    """Past the value of an item whose tag stood alone on its line."""
    while not lines[i].strip() or lines[i].lstrip().startswith("#"):
        i += 1
    if lines[i].startswith(";"):
        return _text_field_end(lines, i)
    return i + 1


def _values(lines: list[str], i: int) -> int:
    """Past a loop's values: up to the next tag, loop or block."""
    n = len(lines)
    while i < n:
        if lines[i].startswith(";"):
            i = _text_field_end(lines, i)
            continue
        head = lines[i].strip().split(maxsplit=1)
        word = head[0].lower() if head else ""
        if (word.startswith("_") or word == "loop_"
                or word.startswith(("data_", "save_", "global_"))):
            break
        i += 1
    return i


def _tags(text: str) -> set[str]:
    document = gemmi.cif.read_string(text)
    block = document.sole_block()
    tags = set()
    for item in block:
        if item.pair is not None:
            tags.add(item.pair[0].lower())
        elif item.loop is not None:
            tags.update(t.lower() for t in item.loop.tags)
    return tags


def strip(text: str) -> str:
    """``text`` without the experiment, every other byte as it was."""
    lines = text.splitlines(keepends=True)
    kept = []
    for tags, chunk in _chunks(lines):
        if tags and all(_stripped(t) for t in tags):
            continue
        if any(_stripped(t) for t in tags):
            raise ValueError(f"a loop mixes kept and stripped tags: "
                             f"{tags}")
        kept.extend(chunk)
    result = "".join(kept)
    before = {t for t in _tags(text) if not _stripped(t)}
    if _tags(result) != before:
        raise ValueError("stripping changed what gemmi reads")
    return result


def fetch(cod_id: int) -> str:
    request = urllib.request.Request(
        URL.format(cod_id), headers={"User-Agent": "crystal-builder"})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8")
    return text.replace("\r\n", "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if a file would change")
    parser.add_argument("--from", dest="source", type=Path,
                        help="read <id>.cif from here, not the COD")
    args = parser.parse_args(argv)

    changed = []
    for cod_id, name in ENTRIES.items():
        if args.source is not None:
            raw = (args.source / f"{cod_id}.cif").read_text("utf-8")
        else:
            raw = fetch(cod_id)
        text = strip(raw)
        target = TARGET / name
        if target.is_file() and target.read_text("utf-8") == text:
            continue
        changed.append(name)
        if not args.check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, "utf-8")
        print(f"{name:14} {cod_id}  {len(raw):7d} -> {len(text):6d} B")
    if args.check and changed:
        print("would change: " + ", ".join(changed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
