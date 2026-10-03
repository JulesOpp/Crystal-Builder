"""Write build/THIRD_PARTY_NOTICES.md: what a packaged build carries
that is somebody else's, and under what terms.

    python scripts/third_party_notices.py

**Built, not committed, and by the bundle job**, just before
PyInstaller, as the manual is: the list is the environment's, and the
one a bundle is built in (``pip install -e
".[gui,build,sketch,ase,pxrd,refine,mcp]"`` from PyPI) is not a
developer's -- a conda PySide6 carries no requirement metadata, and
an extra not installed lists none of its packages.  ``packaging/
bundle.py`` collects it to the bundle's root, where
:func:`xtalapp.manual.notices` finds it for Help > About, and
``--selftest`` fails a build without it.

The packages are read from the environment's own metadata, starting at
this project's requirements and the extras a bundle installs and
following each package's requirements in turn, so a package that is
merely installed beside them is not listed and one a dependency
brings in is.  Read with :mod:`importlib.metadata` rather than
pip-licenses, which would be one more thing to install for a file
written a few times a year.

Each package's licence *files* are copied in whole, because the
BSD and MIT licences most of them carry ask that a binary
redistribution reproduce the notice, and a licence named in one word
does not.

The entries a package index cannot answer for -- vendored code and
data this project transcribed or ships -- are :data:`HAND`, written
here and checked by ``tests/test_packaging.py``.
"""

from __future__ import annotations

import argparse
import re
import sys
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "THIRD_PARTY_NOTICES.md"
PROJECT = "crystal-builder"
#: The extras a bundle installs, as the bundle job spells them.
EXTRAS = ("gui", "build", "sketch", "ase", "pxrd", "refine", "mcp")
#: Build tools that are installed beside the bundle and never in it.
NOT_SHIPPED = {"pyinstaller", "pyinstaller-hooks-contrib", "pip",
               "setuptools", "wheel", "altgraph", "macholib",
               "pefile", "pywin32-ctypes"}

#: Code and data in the build that no package's metadata describes.
HAND = (
    ("PORMAKE", "MIT",
     "Vendored, trimmed, at `xtal/mof/pormake/`: the MOF builder's "
     "code and its database of nets and building blocks.  Its licence "
     "is `xtal/mof/pormake/LICENSE.md` and what was changed is "
     "`xtal/mof/pormake/PROVENANCE.md`; both ship with it.  Lee et "
     "al., *Matter* 4, 1 (2021)."),
    ("RCSR nets", "data, cited",
     "`xtal/analysis/data/RCSRnets-2019-06-01.cgd.gz` and "
     "`rcsr-2019-06-01.json.gz`: the Reticular Chemistry Structure "
     "Resource's nets and index, as downloaded on 2019-06-01 from "
     "http://rcsr.net, used to name and draw topologies.  Please cite "
     "O'Keeffe, Peskov, Ramsden and Yaghi, *Acc. Chem. Res.* 41, 1782 "
     "(2008)."),
    ("Zeo++ radii", "BSD-3-Clause-LBNL",
     "The atomic radii table `xtal.analysis.porosity.ZEO_RADII` is "
     "transcribed from Zeo++ 0.3, Copyright (c) 2011, The Regents of "
     "the University of California, through Lawrence Berkeley "
     "National Laboratory, so that a pore surface is drawn with the "
     "radii its numbers were measured with.  Zeo++ itself is not "
     "bundled; the application finds it where it is installed."),
    ("COD sample structures", "CC0",
     "The structures under `resources/samples/cod/` and "
     "`resources/samples/simple/` are the Crystallography Open "
     "Database's (https://www.crystallography.net/cod/), whose data "
     "are CC0.  Each is listed with its COD number and publication in "
     "`resources/samples/PROVENANCE.md`, which also records where "
     "every other sample came from."),
    ("EQeq ionisation table", "data, cited",
     "`xtal/ff/charges/data/ionization.csv`: ionisation energies from "
     "the NIST Atomic Spectra Database (Kramida, Ralchenko, Reader and "
     "NIST ASD Team) and electron affinities from the PubChem periodic "
     "table (NCBI), written by `scripts/eqeq_table.py`."),
)


def _environment(extra: str = "") -> dict:
    env = dict(default_environment())
    env["extra"] = extra
    return env


def _requirements(dist, extras=()) -> list[str]:
    """The names ``dist`` requires here, with ``extras`` asked for."""
    out = []
    for line in dist.requires or ():
        requirement = Requirement(line)
        marker = requirement.marker
        if marker is not None and not any(
                marker.evaluate(_environment(e)) for e in ("", *extras)):
            continue
        out.append(canonicalize_name(requirement.name))
    return out


def shipped() -> list:
    """Every installed distribution a bundle carries, by name."""
    project = metadata.distribution(PROJECT)
    seen: dict = {}
    queue = _requirements(project, EXTRAS)
    while queue:
        name = queue.pop()
        if name in seen or name in NOT_SHIPPED or name == PROJECT:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        seen[name] = dist
        queue.extend(_requirements(dist))
    return [seen[name] for name in sorted(seen)]


def licence_of(dist) -> str:
    """The licence as the package names it: its SPDX expression,
    else a one-line License field, else its classifiers."""
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression.strip()
    field = (meta.get("License") or "").strip()
    if field and "\n" not in field and len(field) < 80:
        return field
    classifiers = [c.split(" :: ")[-1]
                   for c in meta.get_all("Classifier") or ()
                   if c.startswith("License ::")]
    if classifiers:
        return ", ".join(classifiers)
    return "see the licence text below" if _texts(dist) else "unstated"


def _texts(dist) -> list[tuple[str, str]]:
    """``(name, text)`` of each licence file the package installed."""
    out = []
    for path in dist.files or ():
        name = path.name.upper()
        if not re.match(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", name):
            continue
        parts = [p.lower() for p in path.parts]
        if not any(p.endswith((".dist-info", ".egg-info"))
                   or p == "licenses" for p in parts):
            continue
        try:
            text = path.locate().read_text(encoding="utf-8",
                                           errors="replace")
        except OSError:
            continue
        out.append((path.name, text.strip()))
    return out


def render() -> str:
    dists = shipped()
    lines = [
        "# Third-party notices",
        "",
        "Crystal Builder is MIT-licensed (`LICENSE`).  A packaged build "
        "also carries the work below, each under its own terms.  "
        "Written by `scripts/third_party_notices.py`; do not edit.",
        "",
        "## Vendored code and data",
        "",
    ]
    for name, terms, said in HAND:
        lines += [f"### {name} ({terms})", "", said, ""]
    lines += ["## Python packages", "",
              "| Package | Version | Licence |", "|---|---|---|"]
    for dist in dists:
        licence = licence_of(dist).replace("|", "/")
        lines.append(f"| {dist.metadata['Name']} | {dist.version} | "
                     f"{licence} |")
    lines += ["", "## Licence texts", ""]
    for dist in dists:
        texts = _texts(dist)
        if not texts:
            continue
        lines += [f"### {dist.metadata['Name']} {dist.version}", ""]
        for filename, text in texts:
            lines += [f"`{filename}`", "", "```text", text, "```", ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(), encoding="utf-8")
    print(f"wrote {args.out}: {len(shipped())} packages",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
