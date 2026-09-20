"""P1b: the two candidate cost definitions, side by side."""
import sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import p1_mfu4l as P   # noqa: E402  (runs the extraction)
from common import laterals, pair_cost, direction_cost   # noqa: E402

pos, centre, att = P.pos, P.centre, P.att
print("\n--- spans ---")
for k, (mem, par) in enumerate(att[:2]):
    print(f"  attachment {k}: node members {np.linalg.norm(mem[0]-mem[1]):.3f} A"
          f"   linker members {np.linalg.norm(par[0]-par[1]):.3f} A")


def score(costfn):
    ends = [par for _, par in att]
    dirs = [(p.mean(axis=0) - centre) / np.linalg.norm(p.mean(axis=0) - centre)
            for p in ends]
    out = []
    for R in P.octahedral():
        turned = {i: centre + (p - centre) @ R.T for i, p in pos.items()}
        ta = P.attachments(turned)
        ax = [(m.mean(axis=0) - centre) / np.linalg.norm(m.mean(axis=0) - centre)
              for m, _ in ta]
        tot = 0.0
        for end, u in zip(ends, dirs):
            k = int(np.argmax([u @ t for t in ax]))
            a = ta[k][0]
            mid = 0.5 * (a.mean(axis=0) + end.mean(axis=0))
            axis = end.mean(axis=0) - a.mean(axis=0)
            axis = axis / np.linalg.norm(axis)
            tot += costfn(laterals(a, mid, axis), laterals(end, mid, axis))
        out.append((tot / len(ends), np.allclose(R, np.eye(3))))
    out.sort()
    best = out[0][0]
    tied = sum(1 for v, _ in out if v < best + 1e-6)
    ident = next(v for v, is_id in out if is_id)
    return best, out[-1][0], tied, ident


for name, fn in (("absolute laterals", pair_cost),
                 ("lateral directions", direction_cost)):
    best, worst, tied, ident = score(fn)
    print(f"\n{name}:")
    print(f"   best {best:.6f}   worst {worst:.6f}   "
          f"separation {worst / max(best, 1e-12):9.1f}x")
    print(f"   tied at minimum {tied}   identity {ident:.6f}"
          f"   {'OK' if ident < best + 1e-6 else 'WRONG'}")
