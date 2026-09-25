"""Find repeated normalised N-line windows across different files."""
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def norm(line):
    line = line.split("#")[0].rstrip()
    return re.sub(r"\s+", " ", line.strip())


def main(argv):
    win = int(argv[0]) if argv else 8
    cross_only = "--same-file" not in argv
    buckets = defaultdict(list)
    for pkg in ("xtal", "xtalapp"):
        for path in sorted((ROOT / pkg).rglob("*.py")):
            if "pormake" in path.parts or "modules/data" in str(path):
                continue
            raw = path.read_text().splitlines()
            keep = [
                (i + 1, norm(ln)) for i, ln in enumerate(raw)
                if norm(ln) and not norm(ln).startswith(('"""', "'''"))
            ]
            for s in range(len(keep) - win + 1):
                chunk = keep[s:s + win]
                body = "\n".join(c[1] for c in chunk)
                if len(set(c[1] for c in chunk)) < win - 2:
                    continue
                h = hashlib.md5(body.encode()).hexdigest()
                buckets[h].append(
                    (str(path.relative_to(ROOT)), chunk[0][0], body)
                )
    groups = []
    for h, hits in buckets.items():
        files = {f for f, _, _ in hits}
        if len(hits) < 2:
            continue
        if cross_only and len(files) < 2:
            continue
        groups.append(hits)
    # drop windows contained in a larger reported one
    groups.sort(key=lambda g: -len(g[0][2]))
    seen = []
    for g in groups:
        sig = tuple(sorted((f, ln) for f, ln, _ in g))
        if any(
            all(
                any(f == pf and abs(ln - pln) < 12 for pf, pln in prev)
                for f, ln in sig
            )
            for prev in seen
        ):
            continue
        seen.append(sig)
        print("=" * 60)
        for f, ln, _ in g:
            print(f"  {f}:{ln}")
        print("  ---")
        for line in g[0][2].splitlines():
            print("   |", line)
    print(f"\n{len(seen)} distinct repeated {win}-line windows")


main(sys.argv[1:])
