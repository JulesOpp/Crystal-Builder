"""Diffractometer files written byte for byte, for the vendor readers.

No real ``.rasx`` or ``.raw`` can be vendored -- they are other
people's measurements -- and RietX ships none, so these are made to
the layouts its readers document: a Rigaku zip with its manifest, a
DIFFRAC-AT ``.uxd``, and a Bruker RAW v3, whose header is fixed
offsets.  One peak on a flat background, integral counts, so every
reader decides they are counts and σ is Poisson.
"""

from __future__ import annotations

import struct
import zipfile

import numpy as np

TWO_THETA = np.round(np.arange(10.0, 30.0, 0.02), 4)
COUNTS = np.round(100 + 1000 * np.exp(-((TWO_THETA - 20) / 0.1) ** 2))


def write_rasx(path, *, scans: int = 1, anode: str = "Cu"):
    """A SmartLab ``.rasx``; scan *i* is the counts plus *i*."""
    root = ['﻿<?xml version="1.0" encoding="utf-8"?>',
            '<Root Version="1.1.0.0">']
    with zipfile.ZipFile(path, "w") as archive:
        for i in range(scans):
            root.append(
                f'<Data{i} Type="Profile">'
                f'<ContentHashList Name="Profile{i}.txt" ContentHash="0"/>'
                f'<ContentHashList Name="MesurementConditions{i}.xml" '
                f'ContentHash="0"/></Data{i}>')
            archive.writestr(f"Data{i}/Profile{i}.txt", "\n".join(
                f"{a}\t{b + i:g}\t1" for a, b in zip(TWO_THETA, COUNTS,
                                                     strict=True)))
            archive.writestr(
                f"Data{i}/MesurementConditions{i}.xml",
                '<?xml version="1.0"?><MeasurementConditions>'
                "<ScanInformation><AxisName>TwoThetaTheta</AxisName>"
                "<IntensityUnit>counts</IntensityUnit></ScanInformation>"
                f"<XrayGenerator><TargetName>{anode}</TargetName>"
                "</XrayGenerator></MeasurementConditions>")
        root.append("</Root>")
        archive.writestr("root.xml", "\n".join(root).encode("utf-8"))
    return path


def write_uxd(path):
    lines = ["; written by a test", "_FILEVERSION=2", "_ANODE='Cu'",
             "_WL1=1.540600", "_DRIVE='COUPLED'", "_STEPTIME=1.0",
             "_STEPSIZE=0.02", "_START=10.0", "_2THETACOUNTS"]
    lines += [f"  {a:.4f}  {int(b)}" for a, b in zip(TWO_THETA, COUNTS,
                                                    strict=True)]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def write_bruker_raw(path):
    """RAW v3: a 712-byte file header, one 304-byte range header, then
    a float32 count a step (no varying parameters)."""
    head = bytearray(712)
    head[:7] = b"RAW1.01"
    struct.pack_into("<i", head, 12, 1)                 # ranges
    head[608:610] = b"Cu"
    rng = bytearray(304)
    struct.pack_into("<i", rng, 0, len(rng))
    struct.pack_into("<i", rng, 4, len(TWO_THETA))
    struct.pack_into("<d", rng, 16, TWO_THETA[0])
    struct.pack_into("<d", rng, 176, 0.02)
    struct.pack_into("<f", rng, 192, 1.0)               # s a step
    struct.pack_into("<i", rng, 196, 0)                 # locked coupled
    struct.pack_into("<d", rng, 240, 1.5406)
    struct.pack_into("<iii", rng, 248, 0, 4, 0)
    path.write_bytes(bytes(head) + bytes(rng)
                     + np.asarray(COUNTS, "<f4").tobytes())
    return path
