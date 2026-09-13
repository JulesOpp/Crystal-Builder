"""Record what the real PORMAKE says, for tests/test_mof_vendored.py.

    python tests/data/record_pormake_upstream.py            # rewrite the file
    python tests/data/record_pormake_upstream.py --check    # compare a sample

The vendored tree is compared against upstream PORMAKE 0.2.3.  Neither
side changes unless somebody means it to, so upstream's answers are
recorded once, in ``pormake_upstream.json`` beside this file, and the
suite compares the vendored code against the recording.  That keeps
pymatgen, jax, h5py and pandas out of the test process altogether:
they were several hundred shared libraries loaded half way through a
long run, and that load is where every aborted run on macOS 13.2 died.

``--check`` recomputes a sample and exits non-zero if it no longer
matches, which is what the suite runs -- in a subprocess, in a
temporary directory, because upstream writes ``runtime.log`` into the
current one at import.

Run from anywhere; it needs the real ``pormake`` importable.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RECORDING = Path(__file__).with_name("pormake_upstream.json")

#: The same lists the tests use; the recording is keyed by them.
TOPOLOGIES = ("pcu", "tbo", "dia", "srs", "nbo", "bcu", "soc", "rht",
              "acs-f", "act-a", "ahq-a", "ahr-a")
BUILDS = (("pcu", {"0": "N59"}, "E32"), ("pcu", {"0": "N59"}, ""),
          ("dia", {"0": "N12"}, "E32"))
STRIDE = 120


def _database():
    from xtal.mof import database_root
    return database_root()


def expansion(name):
    import pormake.utils as upstream_utils

    atoms = upstream_utils.read_cgd(
        filename=str(_database() / "topologies" / f"{name}.cgd"))
    return {"tags": [int(t) for t in atoms.get_tags()],
            "cn": [int(c) for c in atoms.info["cn"]],
            "symbols": atoms.get_chemical_symbols(),
            "frac": [[round(float(x), 6) for x in row]
                     for row in atoms.get_scaled_positions()]}


def slots(path):
    import pormake.utils as upstream_utils

    try:
        atoms = upstream_utils.read_cgd(filename=str(path))
    except Exception:
        return None
    return {"slots": len(atoms), "tags": [int(t) for t in atoms.get_tags()]}


def build(name, nodes, edge):
    import pormake

    root = _database()
    topology = pormake.Topology(str(root / "topologies" / f"{name}.cgd"))
    node_bbs = {int(k): pormake.BuildingBlock(str(root / "bbs" / f"{v}.xyz"))
                for k, v in nodes.items()}
    edge_bbs = ({tuple(sorted(t)): pormake.BuildingBlock(
                    str(root / "bbs" / f"{edge}.xyz"))
                 for t in topology.unique_edge_types} if edge else None)
    built = pormake.Builder().build_by_type(
        topology=topology, node_bbs=node_bbs, edge_bbs=edge_bbs)
    return {"n_atoms": len(built.atoms),
            "elements": dict(sorted(Counter(
                built.atoms.get_chemical_symbols()).items())),
            "max_rmsd": float(built.info["max_rmsd"]),
            "mean_rmsd": float(built.info["mean_rmsd"])}


def build_key(name, nodes, edge):
    return f"{name}|{','.join(f'{k}={v}' for k, v in nodes.items())}|{edge}"


def record() -> dict:
    import pormake

    files = sorted((_database() / "topologies").glob("*.cgd"))
    return {
        "pormake": getattr(pormake, "__version__", "0.2.3"),
        "of": len(files),
        "stride": STRIDE,
        "slots": {p.stem: slots(p) for p in files[::STRIDE]},
        "expansions": {name: expansion(name) for name in TOPOLOGIES},
        "builds": {build_key(*b): build(*b) for b in BUILDS},
    }


def write(data: dict) -> None:
    """One entry per line, so a change to the recording reads as a diff."""
    lines = ["{"]
    for key in ("pormake", "of", "stride"):
        lines.append(f" {json.dumps(key)}: {json.dumps(data[key])},")
    sections = ("slots", "expansions", "builds")
    for s, section in enumerate(sections):
        lines.append(f" {json.dumps(section)}: {{")
        items = list(data[section].items())
        for i, (name, value) in enumerate(items):
            comma = "," if i < len(items) - 1 else ""
            lines.append(f"  {json.dumps(name)}: "
                         f"{json.dumps(value, separators=(',', ':'))}{comma}")
        lines.append(" }" + ("," if s < len(sections) - 1 else ""))
    lines.append("}")
    RECORDING.write_text("\n".join(lines) + "\n")


def check() -> int:
    """Recompute a sample; the builds are compared to the same tolerance
    the tests use, because upstream's jax gradient is float32."""
    recorded = json.loads(RECORDING.read_text())
    wrong = []
    for name in list(recorded["slots"])[:3]:
        path = _database() / "topologies" / f"{name}.cgd"
        if slots(path) != recorded["slots"][name]:
            wrong.append(f"slots of {name}")
    for name in ("pcu", "rht"):
        if expansion(name) != recorded["expansions"][name]:
            wrong.append(f"expansion of {name}")
    name, nodes, edge = BUILDS[0]
    theirs = build(name, nodes, edge)
    mine = recorded["builds"][build_key(name, nodes, edge)]
    if (theirs["n_atoms"], theirs["elements"]) != (mine["n_atoms"],
                                                   mine["elements"]):
        wrong.append(f"build of {name}")
    for key in ("max_rmsd", "mean_rmsd"):
        if abs(theirs[key] - mine[key]) > 5e-3:
            wrong.append(f"{key} of {name}")
    print("\n".join(wrong) if wrong else "recording matches upstream")
    return 1 if wrong else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        raise SystemExit(check())
    write(record())
    print(f"wrote {RECORDING}")
