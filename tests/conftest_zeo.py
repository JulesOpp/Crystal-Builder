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
}


def write_fake_network(directory) -> Path:
    """A stand-in for ``network`` that answers every flag we pass."""
    body = "\n".join([
        f"RES = {RES!r}", f"SA = {SA!r}", f"PSD = {psd_text()!r}",
        *(f'if "{flag}" in argv: {writer}'
          for flag, writer in _WRITERS.items()),
    ])
    return write_program(directory, "network",
                         _SCRIPT.format(body=body))
