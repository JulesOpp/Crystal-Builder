"""
xtal.analysis.porosity
======================
What Zeo++ prints, as numbers a table can show.

Zeo++ answers three questions a porous-materials paper has to answer,
and writes each into a small text file of its own.  This module is the
half of that which does not need Zeo++ installed: the parsers, the
result records, and the sentences that say what each number means.
Running the binary is :mod:`xtal.modules.zeopp`; nothing here launches
anything, which is what lets the parsers be tested against a captured
output on a machine with no ``network`` on its PATH.

**The three diameters** (``.res``) are the ones every paper reports and
the ones most often reported wrongly, because the names are similar and
the file has no header:

* **D_i**, the largest *included* sphere -- the biggest cavity there
  is, whether or not anything can reach it.
* **D_f**, the largest *free* sphere -- the biggest sphere that can be
  pushed all the way through the crystal.  This is the one that decides
  what a framework will admit, and it is always the smallest of the
  three.
* **D_if**, the largest included sphere *along the free path* -- the
  widest point of the channel that D_f squeezes through.

**Surface area** (``.sa``) and **accessible volume** (``.vol``) share a
line format: ``@ name Key: value Key: value ...``, split into channels
(connected to the outside) and pockets (not).  A nitrogen probe --
1.86 A, half the 3.72 A kinetic diameter -- is what a BET measurement
sees, which is why it is the default and why the probe radius is
carried in the result: an area quoted without one is meaningless.
The volume file has two spellings and they are not interchangeable --
see :class:`Volume`.

**The channel network** (``.chan`` and ``-visVoro``'s pair of files)
is the half of a Zeo++ answer that is a picture: which pores a probe
can reach, how far they run, and where the widest of them sits.  See
:class:`PoreNetwork`, and the paragraph in it about the one thing no
Zeo++ output says.

**The pore size distribution** (``.psd_histo``) is a thousand bins of
0.1 A, nearly all of them empty.  The interesting part is a window a
few Angstrom wide, and the histogram knows how to find it
(:meth:`PoreSizeDistribution.occupied`) so that neither the plot nor
the reader has to.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

#: Probe radii in Angstrom, as half the kinetic diameter.  Offered as
#: a choice rather than a number because "N2" is the question a user
#: is actually asking and 1.86 is an answer they have to look up.
PROBES = (
    ("n2", "Nitrogen, N2 (1.86 A)", 1.86),
    ("ar", "Argon, Ar (1.72 A)", 1.72),
    ("co2", "Carbon dioxide, CO2 (1.65 A)", 1.65),
    ("h2", "Hydrogen, H2 (1.48 A)", 1.48),
    ("he", "Helium, He (1.30 A)", 1.30),
    ("ch4", "Methane, CH4 (1.86 A)", 1.86),
    ("custom", "Use the radius below", 0.0),
)

#: The default, and the one a BET surface area is measured with.
DEFAULT_PROBE = "n2"


def probe_radius(name: str, custom: float = 0.0) -> float:
    """The radius a probe name stands for, or ``custom`` for one."""
    for key, _label, radius in PROBES:
        if key == str(name) and radius > 0:
            return radius
    return float(custom)


def probe_label(name: str, custom: float = 0.0) -> str:
    """How to name a probe in a sentence, radius included.

    With the radius, always: "the surface area to nitrogen" is
    ambiguous between the several radii papers have used for it, and
    the number is what makes the sentence a measurement.
    """
    for key, label, radius in PROBES:
        if key == str(name) and radius > 0:
            return f"{label.split(',')[0]} ({radius:.2f} A)"
    return f"a {float(custom):.2f} A probe"


#: Zeo++'s own radii table, transcribed from ``initializeRadTable`` in
#: its ``networkinfo.cc`` (BSD-3; the source is vendored at
#: ``resources/zeo++-0.3`` and carries the notice).
#:
#: Here because the *picture* of a porosity run has to be drawn with
#: the radii the *numbers* were computed with, and this table is
#: compiled into the binary rather than written anywhere it could be
#: read back.  A surface drawn with this application's van der Waals
#: radii beside a volume measured with these would be the quiet
#: disagreement the rest of this module exists to prevent.
#: ``tests/test_porosity.py`` checks the transcription against the
#: vendored source, so a Zeo++ upgrade that changes a radius fails
#: rather than drifting.
ZEO_RADII = {
    "H": 1.09, "D": 1.09, "He": 1.4, "Li": 1.82, "Be": 2, "B": 2,
    "C": 1.7, "N": 1.55, "O": 1.52, "F": 1.47, "Ne": 1.54, "Na": 2.27,
    "Mg": 1.73, "Al": 2, "Si": 2.1, "P": 1.8, "S": 1.8, "Cl": 1.75,
    "Ar": 1.88, "K": 2.75, "Ca": 2, "Sc": 2, "Ti": 2, "V": 2, "Cr": 2,
    "Mn": 2, "Fe": 2, "Co": 2, "Ni": 1.63, "Cu": 1.4, "Zn": 1.39,
    "Ga": 1.87, "Ge": 2, "As": 1.85, "Se": 1.9, "Br": 1.85, "Kr": 2.02,
    "Rb": 2, "Sr": 2, "Y": 2, "Zr": 2, "Nb": 2, "Mo": 2, "Tc": 2,
    "Ru": 2, "Rh": 2, "Pd": 1.63, "Ag": 1.72, "Cd": 1.58, "In": 1.93,
    "Sn": 2.17, "Sb": 2, "Te": 2.06, "I": 1.98, "Xe": 2.16, "Cs": 2,
    "Ba": 2, "La": 2, "Ce": 2, "Pr": 2, "Nd": 2, "Pm": 2, "Sm": 2,
    "Eu": 2, "Gd": 2, "Tb": 2, "Dy": 2, "Ho": 2, "Er": 2, "Tm": 2,
    "Yb": 2, "Lu": 2, "Hf": 2, "Ta": 2, "W": 2, "Re": 2, "Os": 2,
    "Ir": 2, "Pt": 1.72, "Au": 1.66, "Hg": 1.55, "Tl": 1.96,
    "Pb": 2.02, "Bi": 2, "Po": 2, "At": 2, "Rn": 2, "Fr": 2, "Ra": 2,
    "Ac": 2, "Th": 2, "Pa": 2, "U": 1.86, "Np": 2, "Pu": 2, "Am": 2,
    "Cm": 2, "Bk": 2, "Cf": 2, "Es": 2, "Fm": 2, "Md": 2, "No": 2,
    "Lr": 2, "Rf": 2, "Db": 2, "Sg": 2, "Bh": 2, "Hs": 2, "Mt": 2,
    "Ds": 2,
}


def zeo_radius(symbol: str, default: float = 1.7) -> float:
    """Zeo++'s radius for an element, or ``default`` for one it has
    never heard of -- which is what Zeo++ itself does."""
    return ZEO_RADII.get(str(symbol).capitalize(), float(default))


class ZeoOutputError(ValueError):
    """Zeo++ wrote something this cannot read.

    Almost always means the run failed and left a partial file -- the
    log is where the reason is, so the message says so rather than
    quoting the bytes.
    """


# ======================================================================
#  THE THREE DIAMETERS
# ======================================================================

@dataclass(frozen=True)
class Diameters:
    """``.res``: the three pore diameters, in Angstrom."""

    included: float                 # D_i
    free: float                     # D_f
    included_along_free: float      # D_if
    name: str = ""

    #: What each one means, in one line, for the table that shows them.
    MEANINGS = (
        ("Largest included sphere", "included", "D_i",
         "the biggest cavity in the crystal, reachable or not"),
        ("Largest free sphere", "free", "D_f",
         "the biggest sphere that can pass all the way through -- "
         "what decides what the framework will admit"),
        ("Included sphere along free path", "included_along_free",
         "D_if", "the widest point of the channel D_f squeezes "
                 "through"),
    )

    def rows(self):
        """``(label, value, symbol, meaning)`` for each diameter."""
        return [(label, getattr(self, attr), symbol, meaning)
                for label, attr, symbol, meaning in self.MEANINGS]

    def summary(self) -> str:
        return (f"D_i {self.included:.3f} A, D_f {self.free:.3f} A, "
                f"D_if {self.included_along_free:.3f} A")


def parse_res(text: str) -> Diameters:
    """Read a ``.res`` file: ``<name> D_i D_f D_if``, one line.

    The name is whatever Zeo++ was told to call the output and may
    contain no spaces, so the three numbers are the last three fields
    -- which is more robust than counting from the left, and is what
    survives a name with a directory in it.
    """
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            included, free, along = (float(v) for v in parts[-3:])
        except ValueError:
            continue
        return Diameters(included, free, along,
                         name=" ".join(parts[:-3]))
    raise ZeoOutputError(
        "no diameters in the .res file -- the run did not get as far "
        "as writing them, so the log is where the reason is")


# ======================================================================
#  SURFACE AREA AND VOLUME
# ======================================================================

#: ``Key: value`` on the summary line.  The value may be missing --
#: Zeo++ writes ``Pocket_surface_area_A^2:`` with nothing after it when
#: there are no pockets -- so the value is optional and the *next* key
#: is what ends it.
_FIELD = re.compile(r"([A-Za-z][A-Za-z0-9_^/+-]*):\s*"
                    r"(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)?")


@dataclass(frozen=True)
class Summary:
    """``.sa`` or ``.vol``: a flat bag of ``Key: value``.

    Deliberately not a record with a field per key.  The two files
    share this shape and differ entirely in which keys they carry, and
    a class per file would be two nearly identical classes that both
    go stale the first time Zeo++ adds a key.
    """

    values: dict = field(default_factory=dict)
    lines: tuple = ()

    def get(self, *names, default=None):
        """The first of these keys that is present.

        Several, because the same quantity is spelled differently
        between the two files -- ``ASA_m^2/g`` and ``NASA_m^2/g`` are
        the accessible and the non-accessible halves of one number --
        and a caller should be able to ask for what it means.
        """
        for name in names:
            if name in self.values:
                return self.values[name]
        return default

    def __contains__(self, name) -> bool:
        return name in self.values

    def __getitem__(self, name):
        return self.values[name]


def parse_summary(text: str) -> Summary:
    """Read the ``@``-prefixed key/value lines of ``.sa`` or ``.vol``."""
    values: dict = {}
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        kept.append(stripped)
        for key, value in _FIELD.findall(stripped):
            if value:
                values[key] = float(value)
            else:
                values.setdefault(key, 0.0)
    if not values:
        raise ZeoOutputError(
            "nothing to read in the Zeo++ summary file -- the run did "
            "not get as far as writing it, so the log is where the "
            "reason is")
    return Summary(values, tuple(kept))


@dataclass(frozen=True)
class SurfaceArea:
    """``.sa``, named.

    Both halves are kept.  The *accessible* area is what a nitrogen
    isotherm measures; the *non-accessible* area belongs to pockets a
    probe cannot reach from outside, and a framework whose quoted area
    is mostly non-accessible is one whose number will not be
    reproduced by an experiment.
    """

    accessible_per_gram: float = 0.0        # m^2/g
    accessible_per_volume: float = 0.0      # m^2/cm^3
    accessible_area: float = 0.0            # A^2
    inaccessible_per_gram: float = 0.0      # m^2/g
    inaccessible_area: float = 0.0          # A^2
    channels: int = 0
    pockets: int = 0
    volume: float = 0.0                     # A^3
    density: float = 0.0                    # g/cm^3
    probe: float = 0.0                      # A
    summary_: Summary | None = None

    @classmethod
    def parse(cls, text: str, probe: float = 0.0) -> SurfaceArea:
        found = parse_summary(text)
        return cls(
            accessible_per_gram=found.get("ASA_m^2/g", default=0.0),
            accessible_per_volume=found.get("ASA_m^2/cm^3",
                                            default=0.0),
            accessible_area=found.get("ASA_A^2", default=0.0),
            inaccessible_per_gram=found.get("NASA_m^2/g", default=0.0),
            inaccessible_area=found.get("NASA_A^2", default=0.0),
            channels=int(found.get("Number_of_channels", default=0)),
            pockets=int(found.get("Number_of_pockets", default=0)),
            volume=found.get("Unitcell_volume", default=0.0),
            density=found.get("Density", default=0.0),
            probe=float(probe), summary_=found)

    def summary(self) -> str:
        return (f"{self.accessible_per_gram:.0f} m^2/g accessible "
                f"({self.accessible_per_volume:.0f} m^2/cm^3)")


@dataclass(frozen=True)
class Volume:
    """``.vol``: the pore volume a probe of that size can occupy.

    **Two files, two spellings, one record.**  ``-vol`` reports the
    volume the probe's *centre* can reach and writes ``AV_*``;
    ``-volpo`` reports the volume the probe *occupies* and writes
    ``POAV_*``.  The second is always the larger and is what a paper
    means by pore volume.  Reading only the first spelling -- which is
    what this did -- gives a confident 0.000 cm^3/g for a framework
    that is two thirds empty, because none of the keys it looked for
    are in the file.  So both are read, and :attr:`occupiable` says
    which the numbers are.

    ``-volpo`` writes no channel and pocket counts, so those are zero
    from it and :attr:`counted` is how a caller tells "none" from "not
    reported".
    """

    accessible_per_gram: float = 0.0        # cm^3/g
    accessible_fraction: float = 0.0
    accessible_volume: float = 0.0          # A^3
    inaccessible_per_gram: float = 0.0      # cm^3/g
    channels: int = 0
    pockets: int = 0
    counted: bool = False
    occupiable: bool = False
    volume: float = 0.0                     # A^3
    density: float = 0.0                    # g/cm^3
    probe: float = 0.0
    summary_: Summary | None = None

    @classmethod
    def parse(cls, text: str, probe: float = 0.0) -> Volume:
        found = parse_summary(text)
        return cls(
            accessible_per_gram=found.get("POAV_cm^3/g", "AV_cm^3/g",
                                          default=0.0),
            accessible_fraction=found.get("POAV_Volume_fraction",
                                          "AV_Volume_fraction",
                                          default=0.0),
            accessible_volume=found.get("POAV_A^3", "AV_A^3",
                                        default=0.0),
            inaccessible_per_gram=found.get("PONAV_cm^3/g",
                                            "NAV_cm^3/g", default=0.0),
            channels=int(found.get("Number_of_channels", default=0)),
            pockets=int(found.get("Number_of_pockets", default=0)),
            counted="Number_of_channels" in found,
            occupiable="POAV_A^3" in found,
            volume=found.get("Unitcell_volume", default=0.0),
            density=found.get("Density", default=0.0),
            probe=float(probe), summary_=found)

    def summary(self) -> str:
        return (f"{self.accessible_per_gram:.3f} cm^3/g "
                f"({self.accessible_fraction * 100:.1f}% of the cell)")


# ======================================================================
#  THE PORE SIZE DISTRIBUTION
# ======================================================================

@dataclass(frozen=True)
class PoreSizeDistribution:
    """``.psd_histo``: how much of the pore space is at each diameter.

    Four columns come out of Zeo++ and two of them are worth drawing.
    ``counts`` is how many sample points landed in each bin, which is
    the histogram; ``derivative`` is minus the slope of the cumulative
    distribution, which is *the* pore size distribution as a paper
    plots it.  They peak in the same place and have different shapes,
    and showing the histogram alone would be showing the sampling
    rather than the material.
    """

    bin_size: float                     # Angstrom
    diameters: np.ndarray               # (N,) the left edge of each bin
    counts: np.ndarray                  # (N,)
    cumulative: np.ndarray              # (N,)
    derivative: np.ndarray              # (N,)
    total_samples: int = 0
    accessible_samples: int = 0
    probe: float = 0.0

    @property
    def n_bins(self) -> int:
        return len(self.diameters)

    @property
    def accessible_fraction(self) -> float:
        if not self.total_samples:
            return 0.0
        return self.accessible_samples / self.total_samples

    def occupied(self, pad: float = 0.5) -> tuple[int, int]:
        """The slice worth drawing: the bins that have anything in
        them, plus a margin.

        A thousand bins of 0.1 A is a hundred Angstrom of axis for a
        material whose pores span four, and a plot drawn over the whole
        range is a spike at the origin.  The window is found here
        rather than in the plot so that the number quoted beside the
        picture and the picture agree about what is being shown.
        """
        filled = np.flatnonzero(self.counts > 0)
        if not len(filled):
            return 0, self.n_bins
        margin = max(1, int(round(pad / max(self.bin_size, 1e-9))))
        return (max(0, int(filled[0]) - margin),
                min(self.n_bins, int(filled[-1]) + margin + 1))

    def window(self, pad: float = 0.5) -> PoreSizeDistribution:
        """This distribution, cut down to :meth:`occupied`."""
        start, stop = self.occupied(pad)
        return PoreSizeDistribution(
            self.bin_size, self.diameters[start:stop],
            self.counts[start:stop], self.cumulative[start:stop],
            self.derivative[start:stop], self.total_samples,
            self.accessible_samples, self.probe)

    def mode(self) -> float:
        """The diameter with the most sample points in it.

        The centre of the bin, not its edge: a bin holds everything
        from its edge to one bin-width later, and quoting the edge
        reports every pore as half a bin narrower than it is.
        """
        if not len(self.counts) or not self.counts.any():
            return 0.0
        return float(self.diameters[int(np.argmax(self.counts))]
                     + self.bin_size / 2)

    def mean(self) -> float:
        """The count-weighted mean diameter."""
        total = float(self.counts.sum())
        if total <= 0:
            return 0.0
        centres = self.diameters + self.bin_size / 2
        return float((centres * self.counts).sum() / total)

    def summary(self) -> str:
        return (f"peak at {self.mode():.2f} A, mean "
                f"{self.mean():.2f} A")


def parse_psd(text: str, probe: float = 0.0) -> PoreSizeDistribution:
    """Read a ``.psd_histo`` file: a short header, then four columns."""
    header: dict = {}
    rows = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Bin ") and "Count" in stripped:
            in_table = True
            continue
        if not in_table:
            key, sep, value = stripped.partition(":")
            if sep:
                header[key.strip()] = value.strip()
            continue
        parts = stripped.split()
        if len(parts) < 4:
            continue
        try:
            rows.append([float(v) for v in parts[:4]])
        except ValueError:                          # pragma: no cover
            continue
    if not rows:
        raise ZeoOutputError(
            "no histogram in the Zeo++ .psd_histo file -- the run did "
            "not get as far as writing it, so the log is where the "
            "reason is")
    table = np.array(rows, dtype=float)
    diameters = table[:, 0]
    bin_size = _number(header.get("Bin size (A)"), 0.0)
    if bin_size <= 0:
        bin_size = float(diameters[1] - diameters[0]) if len(diameters) > 1 \
            else 0.1
    return PoreSizeDistribution(
        bin_size=bin_size, diameters=diameters, counts=table[:, 1],
        cumulative=table[:, 2], derivative=table[:, 3],
        total_samples=int(_number(header.get("Total samples"), 0)),
        accessible_samples=int(
            _number(header.get("Accessible samples"), 0)),
        probe=float(probe))


def _number(text, default: float) -> float:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return float(default)


# ======================================================================
#  THE CHANNEL NETWORK
# ======================================================================

@dataclass(frozen=True)
class Channel:
    """One row of a ``.chan`` file: a pore, and how far it runs.

    ``dimensionality`` is the number a paper reports and the one no
    other Zeo++ output carries: 1 means a channel that runs along one
    axis, 2 a layer of them, 3 a network a probe can cross in any
    direction.  Zero is a pocket, and ``-chan`` does not write those.
    """

    index: int
    dimensionality: int
    included: float                 # D_i of this channel
    free: float                     # D_f of this channel
    included_along_free: float      # D_if of this channel

    #: How to say the dimensionality in a table cell.
    NAMES = {1: "1D, along one axis",
             2: "2D, a layer of channels",
             3: "3D, crossable in any direction"}

    def label(self) -> str:
        return self.NAMES.get(self.dimensionality,
                              f"{self.dimensionality}D")


def dimensionality(channels) -> str:
    """The one sentence that summarises a whole ``.chan`` file.

    A framework with several channels usually has them all of the same
    dimensionality, and saying "3D" once is what the reader wants.
    Where they differ, every one is named -- averaging them would
    invent a number that describes none of the channels there are.
    """
    if not channels:
        return "no channels: nothing this probe can pass through"
    kinds = sorted({c.dimensionality for c in channels})
    if len(kinds) == 1:
        return channels[0].label()
    counts = Counter(c.dimensionality for c in channels)
    return ", ".join(f"{n}D x {counts[n]}" for n in kinds)


def parse_chan(text: str) -> tuple[Channel, ...]:
    """Read a ``.chan`` file.

    Two shapes in one file: a first line naming every channel's
    dimensionality in order, and a ``Channel i D_i D_f D_if`` line
    each.  They are paired by position, which is how Zeo++ writes
    them.  A structure with no channels gets the first line and no
    others, and that is an answer rather than an error -- a dense
    solid has no pores and the table should say so.
    """
    dims: list[int] = []
    rows: dict[int, tuple[float, float, float]] = {}
    # Whether the header was there at all, which is what tells "this
    # crystal has no channels" -- a real answer for a dense solid --
    # from "this file is not a .chan file", which is a failed run.
    said = False
    for line in text.splitlines():
        stripped = line.strip()
        if "dimensionality" in stripped:
            said = True
            _head, _sep, tail = stripped.partition("dimensionality")
            dims = [int(v) for v in tail.split() if _is_int(v)]
            continue
        parts = stripped.split()
        if len(parts) >= 5 and parts[0] == "Channel":
            try:
                rows[int(parts[1])] = tuple(
                    float(v) for v in parts[2:5])
            except ValueError:                      # pragma: no cover
                continue
    if not said:
        raise ZeoOutputError(
            "no channels in the Zeo++ .chan file -- the run did not "
            "get as far as writing them, so the log is where the "
            "reason is")
    count = max(len(dims), max(rows) + 1 if rows else 0)
    return tuple(
        Channel(index=i,
                dimensionality=dims[i] if i < len(dims) else 0,
                included=rows.get(i, _NO_SIZES)[0],
                free=rows.get(i, _NO_SIZES)[1],
                included_along_free=rows.get(i, _NO_SIZES)[2])
        for i in range(count))


_NO_SIZES = (0.0, 0.0, 0.0)


def _is_int(text: str) -> bool:
    try:
        int(text)
    except ValueError:
        return False
    return True


def parse_voro_nodes(text: str, lattice) -> tuple:
    """Read ``<name>_voro_accessible.xyz``: ``(frac, radii)``.

    **Not** :func:`xtal.io.xyz.read_xyz`, and the difference matters:
    the fifth column here is the radius of the sphere that fits at
    that node, and that reader takes a fifth column as an occupancy.
    The positions are cartesian in the file and fractional in the
    record, because the display range draws this in more than one cell
    and a cartesian point cannot be repeated.
    """
    cart, radii = [], []
    for line in text.splitlines()[2:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            values = [float(v) for v in parts[1:5]]
        except ValueError:                          # pragma: no cover
            continue
        cart.append(values[:3])
        radii.append(values[3])
    if not cart:
        return np.zeros((0, 3)), np.zeros(0)
    return (lattice.to_frac(np.array(cart, dtype=float)),
            np.array(radii, dtype=float))


def parse_voro_edges(text: str, lattice) -> tuple:
    """Read ``<name>_voro_accessible.vtk``: ``(starts, ends)``, fractional.

    Endpoints and not indices, deliberately.  That file's ``POINTS``
    block is every Voronoi node *followed by a second copy of the
    accessible ones*, and its ``LINES`` index into the combined list --
    which is a different list from the one
    :func:`parse_voro_nodes` reads.  Carrying coordinates instead of
    indices means the two files never have to be reconciled, and the
    scene wants segment endpoints anyway.

    Only ``POINTS`` and ``LINES`` are read; the rest of the VTK legacy
    format is not something this needs to understand.
    """
    lines = text.splitlines()
    points: list[list[float]] = []
    edges: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        parts = lines[index].split()
        index += 1
        if not parts:
            continue
        if parts[0] == "POINTS":
            count = int(parts[1])
            while len(points) < count and index < len(lines):
                row = lines[index].split()
                index += 1
                if len(row) >= 3:
                    points.append([float(v) for v in row[:3]])
        elif parts[0] == "LINES":
            count = int(parts[1])
            while len(edges) < count and index < len(lines):
                row = lines[index].split()
                index += 1
                if len(row) >= 3 and row[0] == "2":
                    edges.append((int(row[1]), int(row[2])))
    if not points or not edges:
        return np.zeros((0, 3)), np.zeros((0, 3))
    cart = np.array(points, dtype=float)
    pairs = np.array(edges, dtype=int)
    # An index past the end is a truncated file, not a segment.
    pairs = pairs[(pairs < len(cart)).all(axis=1)]
    return (lattice.to_frac(cart[pairs[:, 0]]),
            lattice.to_frac(cart[pairs[:, 1]]))


@dataclass(frozen=True)
class PoreNetwork:
    """Where the pores are, as something that can be drawn.

    The accessible Voronoi nodes with the radius that fits at each,
    the segments joining them, and the channels they belong to.  This
    is the half of a Zeo++ answer that is a picture rather than a
    number, and it is here rather than in the viewport for the same
    reason every parser in this module is: it has to be readable on a
    machine with no display and no ``network`` on its PATH.

    **The largest *free* sphere is not in here and cannot be.**  D_f is
    the width of a bottleneck *on an edge*, and Zeo++ writes no edge
    radii in any output -- so what this can say is where the largest
    *included* sphere sits, which is exact, and which path the free
    sphere travels along.  Drawing a ball at a plausible-looking
    constriction would be inventing a measurement.
    """

    nodes: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3)))   # (N,3) fractional
    radii: np.ndarray = field(
        default_factory=lambda: np.zeros(0))        # (N,) Angstrom
    edge_starts: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3)))   # (E,3) fractional
    edge_ends: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3)))   # (E,3) fractional
    #: The accessible surface, when one was asked for: triangles over
    #: a shared vertex list, fractional like everything else here.
    #: Not from Zeo++ -- see :mod:`xtal.analysis.grid` for why it
    #: cannot be -- but at the same probe and the same radii, so it is
    #: the boundary of the volume the run reported.
    surface_points: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3)))   # (P,3) fractional
    surface_faces: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3), int))
    probe: float = 0.0
    channels: tuple = ()

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_edges(self) -> int:
        return len(self.edge_starts)

    @property
    def n_surface_faces(self) -> int:
        return len(self.surface_faces)

    def largest(self):
        """``(frac, radius)`` of the widest node, or ``None``.

        Twice that radius is D_i, which is how the picture and the
        table are checked against each other.
        """
        if not len(self.radii):
            return None
        best = int(np.argmax(self.radii))
        return self.nodes[best], float(self.radii[best])

    def summary(self) -> str:
        if self.n_surface_faces and not self.n_nodes:
            return (f"an accessible surface of "
                    f"{self.n_surface_faces} triangles at a "
                    f"{self.probe:.2f} A probe")
        said = (f"{self.n_nodes} accessible node(s) in "
                f"{len(self.channels)} channel(s), "
                f"{dimensionality(self.channels)}")
        if self.n_surface_faces:
            said += f", and a surface of {self.n_surface_faces} triangles"
        return said

    def to_dict(self) -> dict:
        """Small enough to live in a project's session file.

        **The surface is deliberately not in here.**  MFU-4l's is
        190 000 triangles, which is 59 MB of JSON -- against three
        seconds to compute it again from the structure that is in the
        same file.  Every other field is kilobytes and is kept: the
        nodes and the channels came out of a binary the reader may not
        have, and the surface did not.
        """
        return {
            "nodes": np.asarray(self.nodes).tolist(),
            "radii": np.asarray(self.radii).tolist(),
            "edge_starts": np.asarray(self.edge_starts).tolist(),
            "edge_ends": np.asarray(self.edge_ends).tolist(),
            "probe": float(self.probe),
            "channels": [
                {"index": c.index, "dimensionality": c.dimensionality,
                 "included": c.included, "free": c.free,
                 "included_along_free": c.included_along_free}
                for c in self.channels],
        }

    @classmethod
    def from_dict(cls, data: dict) -> PoreNetwork:
        def array(key, width, dtype=float):
            values = np.array(data.get(key) or [], dtype=dtype)
            return values.reshape(-1, width) if width else values
        return cls(
            nodes=array("nodes", 3), radii=array("radii", 0),
            edge_starts=array("edge_starts", 3),
            edge_ends=array("edge_ends", 3),
            surface_points=array("surface_points", 3),
            surface_faces=array("surface_faces", 3, int),
            probe=float(data.get("probe", 0.0)),
            channels=tuple(Channel(**row)
                           for row in data.get("channels", ())))


# ======================================================================
#  WHAT ZEO++ MAY NOT BE ASKED
# ======================================================================

def refuse(structure) -> str:
    """Why this structure must not be sent to Zeo++, or ``""``.

    Every number Zeo++ returns is a function of where the atoms are and
    how big they are, and it has no way to express "half an atom".  A
    disordered structure handed to it does not fail -- it returns a
    confident number for a crystal that does not exist, which is worse.
    So the refusal is here, in front of the writer, and it names what
    to do about it.
    """
    if structure is None or structure.n_sites == 0:
        return "there are no atoms to measure the porosity of"
    partial = [s for s in structure.sites if s.occupancy < 1.0]
    if partial:
        names = ", ".join(sorted({s.label or s.element
                                  for s in partial})[:4])
        return (f"{len(partial)} site(s) are partially occupied "
                f"({names}).  Zeo++ has no way to express half an "
                f"atom, so it would return a confident number for a "
                f"crystal that does not exist -- resolve the disorder "
                f"first, by deleting the minor components or by "
                f"choosing one of them.")
    return ""
