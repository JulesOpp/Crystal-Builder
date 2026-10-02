"""
Find a ``mof.build`` combination that answers ``BUILD_OVERLAP``: one
node on one net, with the catalogue's two-connected blocks tried
largest first, until a build overlaps.

    .venv/bin/python tools/agent_eval/tasks/build-overlap/find_overlap.py
    .venv/bin/python .../find_overlap.py --topology pcu --node N16

Not run by the eval: it is how the task's combination was chosen, kept
so that it can be chosen again if the catalogue or the builder changes
under it.  The result is recorded in ``task.md``.  Needs ``ase``.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


def main(argv=None) -> int:
    from xtal.mof.build import BuildRequest, build
    from xtal.mof.catalog import Catalog

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--topology", default="pcu")
    parser.add_argument("--node", default="N16",
                        help="the node block (MOF-5's own by default)")
    parser.add_argument("--tries", type=int, default=20,
                        help="how many linkers to try at most")
    args = parser.parse_args(argv)

    catalog = Catalog.default()
    linkers = sorted(catalog.fitting(2), key=lambda b: -len(b.symbols))
    for block in linkers[:args.tries]:
        with tempfile.TemporaryDirectory() as folder:
            outcome = build(BuildRequest.parse(args.topology, args.node,
                                               block.name),
                            Path(folder), catalog)
        print(f"{args.topology} {args.node} {block.name} "
              f"({len(block.symbols)} atoms): "
              f"{len(outcome.overlaps)} overlapping pair(s)", flush=True)
        if outcome.overlaps:
            print(outcome.warning())
            return 0
    print("no overlap among the linkers tried")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
