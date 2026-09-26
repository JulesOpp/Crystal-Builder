"""
xtal.powder.data
================
A measured pattern and the radiation it was measured with.

Neither needs RietX.  A pattern is three arrays read from a ``.xy``;
a radiation is a choice from a list and, for a synchrotron, a number.
What each *means* to a refinement -- which wavelengths, which
polarisation, which geometry -- is RietX's instrument presets, and
:func:`xtal.powder.bridge.instrument` is where one becomes the other.
Keeping the wavelengths out of this file is deliberate: the Kα
doublets are RietX's to state (from the same reference tables TOPAS
reads), and a second copy here is a second place for 1.5444 to be
1.5443.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from xtal.io.xy import read_columns

__all__ = ["RADIATIONS", "PowderData", "PowderError", "PowderStopped",
           "Radiation"]


class PowderError(ValueError):
    """A pattern or a radiation no refinement can be run against."""


class PowderStopped(Exception):
    """A fit was stopped before it finished.

    Not a :class:`PowderError`: nothing was wrong with what was asked,
    and a step reports it as stopped rather than failed.
    """


#: What the radiation box offers: ``(key, label, RietX preset)``.
#: A laboratory tube is a Kα doublet unless an incident-beam
#: monochromator removed Kα2, which is why each anode is offered both
#: ways -- TOPAS's ``CuKa2`` against ``CuKa1``.  ``synchrotron`` is
#: one wavelength, typed, on a capillary.
RADIATIONS = (
    ("cu", "Cu Kα1 + Kα2 (laboratory)", "CuKa"),
    ("cu-ka1", "Cu Kα1 only (monochromated)", "CuKa1"),
    ("mo", "Mo Kα1 + Kα2 (laboratory)", "MoKa"),
    ("mo-ka1", "Mo Kα1 only (monochromated)", "MoKa1"),
    ("co", "Co Kα1 + Kα2 (laboratory)", "CoKa"),
    ("co-ka1", "Co Kα1 only (monochromated)", "CoKa1"),
    ("synchrotron", "Synchrotron (the wavelength below)", ""),
)


@dataclass(frozen=True)
class Radiation:
    """Which X-rays, and for a laboratory tube, how they were filtered.

    ``wavelength`` is read only for ``synchrotron``, and is required
    there: a synchrotron pattern with a guessed wavelength refines to
    a cell that is wrong by exactly the ratio of the guess, and
    nothing downstream can tell.  ``monochromator_two_theta`` is a
    diffracted-beam monochromator's 2θ (TOPAS ``LP_Factor``), which
    changes the polarisation factor; ``None`` is none fitted.
    """

    kind: str = "cu"
    wavelength: float = 0.0
    monochromator_two_theta: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in {key for key, _l, _p in RADIATIONS}:
            raise PowderError(
                f"{self.kind!r} is not a radiation; have "
                f"{', '.join(key for key, _l, _p in RADIATIONS)}")
        if self.is_synchrotron and not self.wavelength > 0:
            raise PowderError(
                "a synchrotron pattern needs its wavelength -- the "
                "cell is only as right as the number given here")

    @property
    def is_synchrotron(self) -> bool:
        return self.kind == "synchrotron"

    @property
    def preset(self) -> str:
        """RietX's name for this tube, or ``""`` for a synchrotron."""
        return next(p for key, _l, p in RADIATIONS if key == self.kind)

    @property
    def label(self) -> str:
        if self.is_synchrotron:
            return f"Synchrotron, {self.wavelength:.5f} Å"
        return next(lab for key, lab, _p in RADIATIONS
                    if key == self.kind)


@dataclass
class PowderData:
    """A measured pattern: 2θ in degrees, counts, and their errors.

    ``sigma`` is ``None`` when the file gave none, and RietX then
    weights by counting statistics, which is what TOPAS's default
    weighting is too.
    """

    two_theta: np.ndarray
    intensity: np.ndarray
    sigma: np.ndarray | None = None
    name: str = ""
    path: Path | None = None

    def __post_init__(self) -> None:
        self.two_theta = np.asarray(self.two_theta, dtype=float)
        self.intensity = np.asarray(self.intensity, dtype=float)
        if self.sigma is not None:
            self.sigma = np.asarray(self.sigma, dtype=float)
        if len(self.two_theta) != len(self.intensity):
            raise PowderError(
                f"{len(self.two_theta)} angles against "
                f"{len(self.intensity)} intensities")
        if len(self.two_theta) < 10:
            raise PowderError(
                f"{len(self.two_theta)} points is not a pattern")
        if np.any(np.diff(self.two_theta) <= 0):
            raise PowderError(
                "2θ repeats a value -- two scans concatenated into one "
                "file refine as neither")

    @classmethod
    def from_xy(cls, path) -> PowderData:
        """Read a ``.xy`` (or ``.xye``) file: 2θ, counts, and errors if
        every row has a positive third column."""
        path = Path(path)
        try:
            x, y, sigma = read_columns(path)
        except ValueError as exc:
            raise PowderError(str(exc)) from None
        return cls(x, y, sigma, name=path.stem, path=path)

    def __len__(self) -> int:
        return len(self.two_theta)

    @property
    def range(self) -> tuple[float, float]:
        return float(self.two_theta[0]), float(self.two_theta[-1])

    def window(self, start: float | None = None,
               finish: float | None = None) -> PowderData:
        """The points between two angles (TOPAS ``start_X`` /
        ``finish_X``); either end left ``None`` is the file's."""
        lo = self.range[0] if start is None else float(start)
        hi = self.range[1] if finish is None else float(finish)
        keep = (self.two_theta >= lo) & (self.two_theta <= hi)
        if keep.sum() < 10:
            raise PowderError(
                f"{lo:g}-{hi:g}° holds {int(keep.sum())} points of "
                f"this pattern, which runs {self.range[0]:g}-"
                f"{self.range[1]:g}°")
        return PowderData(
            self.two_theta[keep], self.intensity[keep],
            None if self.sigma is None else self.sigma[keep],
            name=self.name, path=self.path)
