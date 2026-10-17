"""Write which nets take a linker set, for the mixed-linker builder.

    python scripts/linker_set_nets.py          # rewrite
    python scripts/linker_set_nets.py --check  # exit 1 if changed

A linker set is worked out round one cluster on a 3-periodic net with
more than one kind of edge, every edge meeting the cluster
(:func:`xtal.mof.merged.plan`).  Asking that of a net is its freedom
-- an expansion -- and the catalogue holds 3227 nets, so the builder's
list cannot ask it as it fills; it reads this file instead, as the
picker reads PORMAKE's nets as told 3-periodic.  Written to
``xtal/mof/data/linker_set_nets.json``: each net's name and the node
slots a cluster can stand on.  ``test_a_recorded_linker_set_net_is_
one`` re-derives a sample.

Only nets the header already allows are asked: not a layer, two node
types or more, two ``EDGE`` lines or more.  Three processes.
"""

from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "xtal" / "mof" / "data" / "linker_set_nets.json"


def candidates() -> list[str]:
    from xtal.mof.catalog import Catalog

    return [t.name for t in Catalog.default().topologies()
            if not t.is_layer and t.n_node_types >= 2
            and t.edge_lines >= 2]


def slots_of(name: str) -> tuple[str, list[int]]:
    from xtal.mof import merged
    from xtal.mof.catalog import Catalog

    topology = Catalog.default().topology(name)
    found = []
    for slot in range(topology.n_node_types):
        try:
            merged.plan(topology, slot)
        except Exception:                           # noqa: BLE001
            continue
        found.append(slot)
    return name, found


def table() -> dict[str, list[int]]:
    names = candidates()
    out = {}
    with Pool(3) as pool:
        for k, (name, slots) in enumerate(
                pool.imap_unordered(slots_of, names, chunksize=4), 1):
            if slots:
                out[name] = slots
            if k % 100 == 0:
                print(f"{k}/{len(names)}: {len(out)} take a set",
                      flush=True)
    return dict(sorted(out.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(table(), indent=0, sort_keys=True) + "\n"
    if args.check:
        same = OUT.is_file() and OUT.read_text() == text
        print("unchanged" if same else "changed")
        return 0 if same else 1
    OUT.write_text(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
