"""Which 3-periodic RCSR nets PORMAKE cannot read as the RCSR embeds them.

Reads every net :func:`xtal.mof.catalog.rcsr_nets` would offer, with
:data:`xtal.mof.catalog.RCSR_REJECTS` emptied, through the vendored
PORMAKE, and prints the ones it refuses: the list to paste back into
``RCSR_REJECTS``.  About four minutes; ``mcx`` alone is half of one.

    python scripts/rcsr_net_rejects.py
"""

import logging
import sys
import time

from xtal.mof import catalog
from xtal.mof.build import import_pormake


def main() -> int:
    pormake = import_pormake()
    logging.getLogger("pormake").setLevel(logging.CRITICAL)
    kept = catalog.RCSR_REJECTS
    catalog.RCSR_REJECTS = frozenset()
    catalog._rcsr_nets.cache_clear()
    try:
        nets = catalog.rcsr_nets()
    finally:
        catalog.RCSR_REJECTS = kept
        catalog._rcsr_nets.cache_clear()
    refused = []
    start = time.perf_counter()
    for topology in nets:
        try:
            topology._pormake(pormake)
        except Exception as exc:                    # noqa: BLE001
            refused.append(topology.name)
            print(f"refused {topology.name}: {exc}", file=sys.stderr)
    print(f"{len(nets)} nets read in {time.perf_counter() - start:.0f} s; "
          f"{len(refused)} refused:")
    print(", ".join(f'"{name}"' for name in sorted(refused)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
