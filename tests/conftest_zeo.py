"""Zeo++'s output, captured, and a stand-in that reproduces it.

``network`` is a nine-megabyte binary that takes twenty seconds on a
framework, and no test machine can be assumed to have it.  So the
tests that need one run against a script named by ``XTAL_ZEOPP`` that
reads the command line the module built, records it, and writes the
file Zeo++ would have written.

Helpers rather than fixtures, following ``conftest_ff.py``: two test
modules want the stand-in, and a fixture defined in one and imported
into the other is a redefinition rather than a share.

The captured text is from a real run of ``network`` 0.3 on MFU-4l.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest_program import write_program

RES = "   MFU4l.res    18.72736 9.18223  18.72243\n"

SA = (
    "@ MFU4l.sa Unitcell_volume: 29955.3   Density: 0.559382   "
    "ASA_A^2: 5358.14 ASA_m^2/cm^3: 1788.71 ASA_m^2/g: 3197.65 "
    "NASA_A^2: 0 NASA_m^2/cm^3: 0 NASA_m^2/g: 0\n"
    "Number_of_channels: 1 Channel_surface_area_A^2: 5358.14  \n"
    "Number_of_pockets: 0 Pocket_surface_area_A^2: \n")

VOL = (
    "@ MFU4l.vol Unitcell_volume: 29955.3   Density: 0.559382   "
    "AV_A^3: 13827.4 AV_Volume_fraction: 0.4616 AV_cm^3/g: 0.825196 "
    "NAV_A^3: 0 NAV_Volume_fraction: 0 NAV_cm^3/g: 0\n"
    "Number_of_channels: 1 Channel_volume_A^3: 13827.4  \n"
    "Number_of_pockets: 0 Pocket_volume_A^3: \n")

#: ``-chan``: one line naming every channel's dimensionality, then the
#: three diameters of each.  MFU-4l is one 3D channel.
CHAN = (
    "channels.chan   1 channels identified of dimensionality 3 \n"
    "Channel  0  18.7273  9.18228  18.7225\n"
    "channels.chan summary(Max_of_columns_above)   18.7273 "
    "9.18228  18.7225  probe_rad: 1.2  probe_diam: 2.4\n")

#: ``-visVoro``'s accessible nodes, trimmed to six of the 912 a real
#: run writes.  Cartesian Angstrom, and the **fifth column is a
#: radius** -- the widest node here is the one whose 9.371 A doubles
#: to the 18.74 A D_i the .chan file above reports.
VORO_NODES = (
    "6\n"
    "Voronoi accessible diagram for structure with probe radius 1.200\n"
    "Ac 7.782 3.983 3.983 1.629\n"
    "Ac 7.741 3.962 3.962 1.601\n"
    "Ac 3.962 7.740 3.962 1.601\n"
    "Ac 15.528 0.000 0.000 9.371\n"
    "Ac 6.580 6.580 6.580 1.660\n"
    "Ac 0.000 15.528 0.000 5.010\n")

#: ``-visVoro``'s accessible edges.  Its POINTS block is every node
#: followed by a second copy of the accessible ones, and its LINES
#: index into that combined list -- which is why the parser carries
#: coordinates out rather than indices.
VORO_EDGES = (
    "# vtk DataFile Version 2.0\n"
    "vtk data for file structure\n"
    "ASCII\n"
    "DATASET POLYDATA\n"
    "POINTS 4 double\n"
    "7.782 3.983 3.983\n"
    "7.741 3.962 3.962\n"
    "15.528 0.000 0.000\n"
    "6.580 6.580 6.580\n"
    "LINES 3 9\n"
    "2 0 1\n"
    "2 1 2\n"
    "2 2 3\n")


def psd_text(counts=((11.5, 40), (18.7, 900))) -> str:
    """A histogram of a thousand bins with a few of them filled --
    which is the shape Zeo++ actually writes."""
    lines = ["Pore size distribution histogram",
             "Bin size (A): 0.1",
             "Number of bins: 1000",
             "From: 0", "To: 100",
             "Total samples: 5000",
             "Accessible samples: 2910",
             "Fraction of sample points in node spheres: 0.582",
             "Fraction of sample points outside node spheres: 0",
             "", "Bin Count Cumulative_dist Derivative_dist"]
    filled = {round(d, 1): n for d, n in counts}
    total = sum(filled.values()) or 1
    seen = 0
    for index in range(1000):
        diameter = round(index * 0.1, 1)
        count = filled.get(diameter, 0)
        seen += count
        remaining = (total - seen) / total
        lines.append(f"{diameter} {count} {remaining:.6f} 0")
    return "\n".join(lines) + "\n"


#: The stand-in itself.  It records the command line beside its output
#: so a test can assert on the arguments the module chose without
#: reading them out of a log.
_SCRIPT = '''import sys, pathlib
argv = sys.argv[1:]
pathlib.Path("argv.txt").write_text("\\n".join(argv))
print("Reading input file: " + argv[-1], flush=True)
print("Performing Voronoi decomposition.", flush=True)
{body}
'''

_WRITERS = {
    "-res": 'pathlib.Path(argv[argv.index("-res") + 1]).write_text(RES)',
    "-sa": 'pathlib.Path(argv[argv.index("-sa") + 4]).write_text(SA)',
    "-psd": 'pathlib.Path(argv[argv.index("-psd") + 4]).write_text(PSD)',
    "-vol": 'pathlib.Path(argv[argv.index("-vol") + 4]).write_text(VOL)',
    "-chan": 'pathlib.Path(argv[argv.index("-chan") + 2]).write_text(CHAN)',
    # -visVoro is the one flag whose output name is not ours to
    # choose: it names its six files after the input stem.
    "-visVoro": ('stem = pathlib.Path(argv[-1]).stem\n'
                 'pathlib.Path(stem + "_voro_accessible.xyz")'
                 '.write_text(NODES)\n'
                 'pathlib.Path(stem + "_voro_accessible.vtk")'
                 '.write_text(EDGES)'),
}


def write_fake_network(directory) -> Path:
    """A stand-in for ``network`` that answers every flag we pass."""
    body = "\n".join([
        f"RES = {RES!r}", f"SA = {SA!r}", f"VOL = {VOL!r}",
        f"PSD = {psd_text()!r}", f"CHAN = {CHAN!r}",
        f"NODES = {VORO_NODES!r}", f"EDGES = {VORO_EDGES!r}",
        # Indented under the `if`, so a multi-line writer works.
        *(f'if "{flag}" in argv:\n'
          + "\n".join(f"    {row}" for row in writer.splitlines())
          for flag, writer in _WRITERS.items()),
    ])
    return write_program(directory, "network",
                         _SCRIPT.format(body=body))
