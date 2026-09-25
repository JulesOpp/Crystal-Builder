# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""The flip is a *relative* property: one node cannot show it.

A single Kuratowski node in orientation A and the same node in
orientation B are the same object (a 90 deg turn about a cubic axis
carries one to the other and leaves the six linker axes where they
are).  What distinguishes them is what the *pair* across one edge
presents to the linker between them.
"""
import numpy as np

AX = np.array([1.0, 0.0, 0.0])                  # the shared edge
TET_A = np.array([[1,1,1],[1,-1,-1],[-1,1,-1],[-1,-1,1]], float)
TET_A /= np.linalg.norm(TET_A, axis=1)[:, None]
TET_B = -TET_A
OFF = np.radians(21.24)      # measured on MFU4l.cif, probe 10

def face(tet, axis):
    """The plane of the triazolate this node presents down ``axis``:
    the azimuth of the two peripheral metals on that side."""
    near = sorted(tet, key=lambda t: -np.dot(t, axis))[:2]
    perp = []
    for t in near:
        p = t - np.dot(t, axis) * axis
        perp.append(p / np.linalg.norm(p))
    return np.array(perp)

R90 = np.array([[1,0,0],[0,0,-1],[0,1,0]], float)   # 90 deg about x
print("a 90 deg turn about x carries A to B?",
      sorted(map(tuple, np.round(TET_A @ R90.T, 6)))
      == sorted(map(tuple, np.round(TET_B, 6))))
print("...and leaves the six linker axes alone, so ONE node in")
print("   orientation A is indistinguishable from one in B.\n")

def twist(t_left, t_right):
    """Angle between the triazolate planes the two ends of one edge
    present to the linker that has to bridge them."""
    a = face(t_left, AX)[0]
    b = face(t_right, -AX)
    ang = min(np.degrees(np.arccos(np.clip(abs(np.dot(a, v)), -1, 1)))
              for v in b)
    return ang

print("twist the linker must absorb across one edge:")
print("   A -- B  (the real MFU-4l alternation) : %5.1f deg"
      % twist(TET_A, TET_B))
print("   A -- A  (what a single-orbit build gives): %5.1f deg"
      % twist(TET_A, TET_A))
print("\nMFU-4l's linker is a rigid planar dibenzo[1,4]dioxin: its two")
print("triazolate rings are coplanar, so only the 0 deg case can be")
print("bridged.  Nothing in a single-X model sees this angle at all.")
