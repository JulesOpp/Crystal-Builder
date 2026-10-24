"""Line-level similarity between two files, ignoring blanks/comments."""
import difflib
import re
import sys
from pathlib import Path


def norm(p):
    out = []
    for ln in Path(p).read_text().splitlines():
        s = re.sub(r"\s+", " ", ln.split("#")[0].strip())
        if s:
            out.append(s)
    return out


a, b = sys.argv[1], sys.argv[2]
A, B = norm(a), norm(b)
sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
same = sum(bl.size for bl in sm.get_matching_blocks())
runs = sorted((bl.size for bl in sm.get_matching_blocks() if bl.size >= 5),
              reverse=True)
print(f"{a} ({len(A)}) vs {b} ({len(B)}): {same} identical lines "
      f"({100 * same / min(len(A), len(B)):.0f}% of the smaller); "
      f"runs>=5: {runs[:8]}")
