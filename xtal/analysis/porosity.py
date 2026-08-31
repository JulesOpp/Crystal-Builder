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

**The pore size distribution** (``.psd_histo``) is a thousand bins of
0.1 A, nearly all of them empty.  The interesting part is a window a
few Angstrom wide, and the histogram knows how to find it
(:meth:`PoreSizeDistribution.occupied`) so that neither the plot nor
the reader has to.
"""

from __future__ import annotations

import re
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
    """``.vol``: the pore volume a probe of that size can occupy."""

    accessible_per_gram: float = 0.0        # cm^3/g
    accessible_fraction: float = 0.0
    accessible_volume: float = 0.0          # A^3
    inaccessible_per_gram: float = 0.0      # cm^3/g
    channels: int = 0
    pockets: int = 0
    volume: float = 0.0                     # A^3
    density: float = 0.0                    # g/cm^3
    probe: float = 0.0
    summary_: Summary | None = None

    @classmethod
    def parse(cls, text: str, probe: float = 0.0) -> Volume:
        found = parse_summary(text)
        return cls(
            accessible_per_gram=found.get("AV_cm^3/g", default=0.0),
            accessible_fraction=found.get("AV_Volume_fraction",
                                          default=0.0),
            accessible_volume=found.get("AV_A^3", default=0.0),
            inaccessible_per_gram=found.get("NAV_cm^3/g", default=0.0),
            channels=int(found.get("Number_of_channels", default=0)),
            pockets=int(found.get("Number_of_pockets", default=0)),
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
