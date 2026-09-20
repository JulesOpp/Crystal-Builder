"""Can we find MFU-4l's Zn5Cl4 clusters and triazole rings from the CIF?"""
from collections import Counter, defaultdict
import numpy as np
from xtal.io import FORMATS
from xtal.core import bonding, p1

s = FORMATS.read("resources/samples/MFU4l.cif")
cell = p1.expand(s)
g = bonding.graph(s)
el = [str(e) for e in cell.elements]
print("atoms", cell.n_atoms, Counter(el))

# neighbours with images, as element multisets
def nb(i):
    return [(int(j), tuple(im)) for j, im in g.neighbors_with_images(i)]

kinds = defaultdict(list)
for i in range(cell.n_atoms):
    sig = (el[i], tuple(sorted(el[j] for j, _ in nb(i))))
    kinds[sig].append(i)
for sig in sorted(kinds, key=lambda k: (k[0], len(kinds[k]))):
    print(f"  {sig[0]:3s} {len(kinds[sig]):4d}  bonded to {sig[1]}")
