"""Embed the isoreticular linker series and store what each spans.

Writes ``xtal/mof/data/linker_series.json``, which
:func:`xtal.mof.linkers.stored` reads so that suggesting a linker
costs no RDKit.  Re-run when :func:`xtal.mof.linkers.series` changes;
``tests/test_mof_linkers.py`` re-embeds the table and fails if it has
drifted from its SMILES.

    python scripts/linker_series.py
"""

import json
import sys
import time

from xtal.mof import linkers


def main() -> int:
    rows = []
    start = time.perf_counter()
    for name, topicity, donor, smiles in linkers.series():
        try:
            value, formula = linkers.measure_smiles(smiles)
        except Exception as exc:                    # noqa: BLE001
            print(f"skipped {name}: {exc}", file=sys.stderr)
            continue
        rows.append({"name": name, "topicity": topicity,
                     "donor": donor, "value": round(value, 3),
                     "formula": formula, "smiles": smiles})
    linkers.SERIES.parent.mkdir(parents=True, exist_ok=True)
    linkers.SERIES.write_text(json.dumps(rows, indent=1) + "\n",
                              encoding="utf-8")
    print(f"{len(rows)} linkers in {time.perf_counter() - start:.1f} s "
          f"-> {linkers.SERIES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
