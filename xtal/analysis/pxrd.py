"""
xtal.analysis.pxrd
==================
A powder diffraction pattern, calculated from the structure on screen.

Peak *positions* need only the cell and the space group's systematic
absences.  Peak *intensities* need the atoms, through structure
factors -- and the intensities are the whole reason to calculate a
pattern rather than a comb of tick marks, because a phase is
identified by which peaks are strong and not only by where they are.

**The science came from somewhere and it is worth saying where.**  The
Lorentz-polarisation factor, the multiplicity count, the Debye-Waller
attenuation, the pseudo-Voigt profile and the Caglioti width relation
are ported from the ``DataPlotter`` application the same author wrote
for measured patterns, which had already been checked against
published ones.  What changed in the port is the input: that code read
a CIF from disk, and this runs against the
:class:`~xtal.core.structure.Structure` that is open --
:func:`to_small_structure` is the whole of the difference.

**Nothing here launches or draws anything**, which is the line this
package is on the right side of: :mod:`xtal.modules.pxrd` is what runs
it and puts the answer in a report, and the overlay window is Qt's.
The consequence worth having is that the numbers can be checked
against a published pattern with no display attached.

**A calculated intensity assumes the structure is complete.**  It is
the caveat that belongs next to every number this module returns, and
it is the row note and the report note for that reason: MOF structures
routinely omit disordered solvent and carry partial occupancies, and a
real powder shows preferred orientation.  Positions can be exactly
right while intensities are not.

**A dummy atom is held back at the door.**  ``X`` has no scattering
factor, and gemmi would either refuse it or treat it as something it
is not; a marker is not chemistry, so :func:`to_small_structure`
leaves it out.  A module run has already had them removed by
:func:`xtal.modules.job.without_dummies`, and this is the same answer
for a direct call -- the fifth place the invariant is enforced rather
than the first place it is broken.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import gemmi
import numpy as np

from xtal.core import elements as el

__all__ = ["DEFAULT_CAGLIOTI", "DEFAULT_ETA", "DEFAULT_WAVELENGTH",
           "PROFILE_SHAPES", "WAVELENGTHS", "Pattern", "PxrdError",
           "Reflection", "Simulation", "absences", "build_pattern",
           "caglioti_fwhm", "d_min_for", "debye_waller",
           "equivalents", "hkl_text", "lorentz_polarization",
           "multiplicity", "profile", "reflections",
           "representative", "simulate", "to_small_structure",
           "two_theta_from_d", "wavelength_label",
           "wavelength_of"]


class PxrdError(ValueError):
    """A structure or a range that no pattern can be calculated from."""


# ======================================================================
#  CONSTANTS
# ======================================================================

#: Common laboratory sources, in Angstrom.  Offered by name because
#: "Cu Ka1" is the question a user is asking and 1.5406 is an answer
#: they would otherwise look up -- the same argument
#: :data:`xtal.analysis.porosity.PROBES` makes about probe radii.
WAVELENGTHS = (
    ("cu-ka1", "Cu Ka1 (1.5406 A)", 1.5406),
    ("cu-ka", "Cu Ka average (1.5418 A)", 1.5418),
    ("mo-ka1", "Mo Ka1 (0.7093 A)", 0.70930),
    ("co-ka1", "Co Ka1 (1.7890 A)", 1.78900),
    ("ag-ka1", "Ag Ka1 (0.5594 A)", 0.55941),
    ("custom", "Use the wavelength below", 0.0),
)

DEFAULT_WAVELENGTH = 1.5406

#: Caglioti coefficients giving a typical laboratory diffractometer
#: profile: ``FWHM^2 = U tan^2(theta) + V tan(theta) + W``, in
#: degrees squared.
DEFAULT_CAGLIOTI = (0.004, -0.002, 0.010)

PROFILE_SHAPES = ("pseudo-voigt", "gaussian", "lorentzian")

DEFAULT_ETA = 0.5

GAUSSIAN_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))

#: How far from a peak centre to evaluate its profile, in FWHM.
#: Beyond this a pseudo-Voigt contributes nothing that survives being
#: scaled to 100, and the cutoff is what keeps a thousand reflections
#: on a ten-thousand-point grid from being a ten-million-point sum.
PROFILE_CUTOFF_FWHM = 12.0

#: Below this the Lorentz-polarisation factor diverges and no
#: instrument measures there, so a peak at 0.2 degrees would be the
#: only thing visible on a pattern scaled to its tallest peak.
MIN_TWO_THETA = 0.5


def wavelength_of(name: str, custom: float = 0.0) -> float:
    """The wavelength a source name stands for, or ``custom``."""
    for key, _label, value in WAVELENGTHS:
        if key == str(name) and value > 0:
            return value
    value = float(custom)
    if not value > 0:
        raise PxrdError(
            f"{name!r} is not a known source and no wavelength was "
            f"given instead; have "
            f"{', '.join(k for k, _l, v in WAVELENGTHS if v > 0)}")
    return value


def wavelength_label(name: str, custom: float = 0.0) -> str:
    """How to name a wavelength in a sentence, the number included.

    With the number, always: a pattern quoted without its radiation is
    not comparable with anything, and 2-theta is the one axis that
    moves when the source does.
    """
    for key, label, value in WAVELENGTHS:
        if key == str(name) and value > 0:
            return label
    return f"{float(custom):.5g} A"


# ======================================================================
#  THE BRIDGE
# ======================================================================

def to_small_structure(structure, name: str = ""):
    """``Structure`` -> :class:`gemmi.SmallStructure`, for gemmi's
    structure-factor calculator.

    :mod:`xtal.io.cif_reader` already comes *through*
    ``make_small_structure_from_block``, so the field mapping is known
    in both directions and this is the other one.  It exists because
    ``StructureFactorCalculatorX.calculate_sf_from_small_structure``
    wants a ``SmallStructure`` and this application's documents are
    not files.

    **The symmetry has to arrive as operations.**  Setting
    ``spacegroup_hm`` alone leaves ``cell.images`` empty, and an empty
    image list means ``get_all_unit_cell_sites`` returns the
    asymmetric unit -- so every intensity would be calculated from a
    fraction of the atoms and the systematic absences would not be
    absent.  Halite's 100, which F centring forbids, comes back as a
    peak a third the height of 200.  Writing the operations as
    triplets and letting gemmi resolve the group from *them*
    (``determine_and_set_spacegroup("symops")``) is what fills the
    images in, and it is the same route reading a CIF takes.
    """
    small = gemmi.SmallStructure()
    small.name = (name or structure.meta.get("title", "")
                  or "structure")
    small.cell = gemmi.UnitCell(*structure.lattice.parameters)
    small.spacegroup_hm = structure.space_group.hm
    small.symops = [op.triplet() for op in
                    gemmi.symops_from_hall(structure.space_group.hall)]

    for index, site in enumerate(structure.sites):
        if el.is_dummy(site.element):
            continue                    # a marker, not chemistry
        entry = gemmi.SmallStructure.Site()
        entry.label = site.label or f"{site.element}{index + 1}"
        entry.type_symbol = site.element
        entry.element = gemmi.Element(site.element)
        entry.fract = gemmi.Fractional(*(float(v) for v in site.frac))
        entry.occ = float(site.occupancy)
        # U_eq rather than U_iso, so a refinement that gave only
        # anisotropic parameters still attenuates its own atoms
        # instead of being treated as if it were at absolute zero.
        entry.u_iso = float(site.u_equivalent or 0.0)
        small.add_site(entry)

    if not small.sites:
        raise PxrdError(
            "there are no atoms to calculate a pattern from -- a "
            "cell and a space group place the peaks, but the "
            "intensities are the atoms")
    small.determine_and_set_spacegroup("symops")
    small.setup_cell_images()
    return small


# ======================================================================
#  GEOMETRY
# ======================================================================

def two_theta_from_d(d_spacings, wavelength: float) -> np.ndarray:
    """Bragg's law: ``lambda = 2 d sin(theta)``.

    ``nan`` where ``|sin theta| > 1``, which is a reflection this
    wavelength cannot reach rather than an error.
    """
    d = np.asarray(d_spacings, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        sin_theta = wavelength / (2.0 * d)
        sin_theta = np.where(np.abs(sin_theta) <= 1.0, sin_theta,
                             np.nan)
        return np.degrees(2.0 * np.arcsin(sin_theta))


def d_min_for(wavelength: float, two_theta_max: float) -> float:
    """The smallest d-spacing still inside the requested range."""
    theta_max = np.radians(min(float(two_theta_max), 179.9) / 2.0)
    return float(wavelength / (2.0 * np.sin(theta_max)))


def lorentz_polarization(two_theta_deg) -> np.ndarray:
    """The Lorentz-polarisation factor of an unmonochromated powder::

        LP = (1 + cos^2(2theta)) / (sin^2(theta) cos(theta))

    This is what turns ``|F|^2`` into an observable powder intensity.
    Without it the low-angle peaks -- which are the ones a MOF is
    identified by -- come out far too weak.
    """
    angle = np.asarray(two_theta_deg, dtype=float)
    theta = np.radians(angle) / 2.0
    denominator = np.sin(theta) ** 2 * np.cos(theta)
    with np.errstate(divide="ignore", invalid="ignore"):
        lp = (1.0 + np.cos(np.radians(angle)) ** 2) / denominator
    return np.where(np.isfinite(lp), lp, 0.0)


def equivalents(hkl, operations) -> set:
    """Every reflection symmetry-equivalent to this one.

    Friedel pairs are in the set because they are indistinguishable
    without anomalous scattering -- Friedel's law, and why 111 and
    -1-1-1 are one peak.
    """
    indices = tuple(int(i) for i in hkl)
    out = set()
    for op in operations:
        equivalent = tuple(op.apply_to_hkl(indices))
        out.add(equivalent)
        out.add(tuple(-i for i in equivalent))
    return out


def multiplicity(hkl, operations) -> int:
    """How many symmetry-equivalent reflections share this d-spacing.

    A powder superimposes all of them onto one peak, so the intensity
    scales with the count.
    """
    return len(equivalents(hkl, operations))


def representative(equivalent_set):
    """The member of an orbit a reference pattern would print.

    gemmi's asymmetric unit is a correct choice and not the *familiar*
    one: it hands back ``0 2 0`` where every powder diffraction file
    in the world writes ``200``, and a table that disagrees with the
    card the user is comparing it against is a table they have to
    translate.  So the orbit is enumerated anyway -- ``multiplicity``
    needs it -- and this picks from it.

    Fewest negative indices first, then the largest index earliest,
    which is ``h >= k >= l >= 0`` wherever the group permutes the
    axes and leaves everything else alone.  Cubic gives 200, 220, 111,
    311, 420; orthorhombic keeps 020 as 020, because 200 is a
    different reflection there and choosing it would be wrong rather
    than tidy.
    """
    return min(equivalent_set,
               key=lambda hkl: (sum(1 for i in hkl if i < 0),
                                tuple(-i for i in hkl)))


def debye_waller(two_theta_deg, wavelength: float,
                 b_overall: float) -> np.ndarray:
    """Thermal attenuation: ``exp(-2 B sin^2(theta) / lambda^2)``.

    An overall B rather than per-atom displacement parameters, because
    most structures carry none and one number is the honest amount of
    detail to offer.  Without it the high-angle peaks come out
    systematically too strong against a published pattern.
    """
    angle = np.asarray(two_theta_deg, dtype=float)
    if b_overall <= 0:
        return np.ones_like(angle)
    sin_theta = np.sin(np.radians(angle) / 2.0)
    return np.exp(-2.0 * b_overall * sin_theta ** 2 / wavelength ** 2)


# ======================================================================
#  REFLECTIONS
# ======================================================================

@dataclass(frozen=True)
class Reflection:
    """One allowed reflection, and its contribution to the powder.

    **One reflection, not one peak.**  Several can land at the same
    2-theta -- 333 and 511 share a d-spacing in any cubic cell, and a
    structure written in P1 puts 100, 010 and 001 together with no
    symmetry involved at all -- and they are *not* folded into one
    record.  Folding them was tried and taken back out: it made the
    table shorter and it made the reflection list stop describing the
    structure it was calculated from, which is the one thing the list
    is for.  A user who expands a crystal to P1 and simulates is
    entitled to see what P1 says, and P1 says there are three of them.

    The pattern is unaffected either way, because the profiles are
    summed onto the grid whether or not the records were merged first.
    """

    hkl: tuple[int, int, int]
    d: float                        # Angstrom
    two_theta: float                # degrees
    intensity: float                # arbitrary, scaled by the caller
    multiplicity: int = 1
    f_squared: float = 0.0

    @property
    def label(self) -> str:
        """``(1 1 1)``, with a bar for a negative index -- which is
        how every table of reflections anybody will compare this with
        writes them."""
        return hkl_text(self.hkl)


def hkl_text(hkl) -> str:
    return "(" + " ".join(
        (f"-{abs(i)}" if i < 0 else str(i)) for i in hkl) + ")"


def reflections(small, wavelength: float = DEFAULT_WAVELENGTH,
                two_theta_min: float = MIN_TWO_THETA,
                two_theta_max: float = 50.0,
                b_overall: float = 0.0,
                cancel=None) -> list[Reflection]:
    """Every symmetry-inequivalent reflection in range.

    ``gemmi.make_miller_array`` returns the *asymmetric* reflections
    for the group -- one per orbit, which is exactly the list a
    reference pattern prints -- and :func:`multiplicity` puts the
    equivalents back into the intensity.  98 of them cover MFU-4l to
    50 degrees where the same crystal expanded to P1 has 3177, and
    both are right: they are answers to "what does *this* structure
    allow", and the structure is what the user chose.

    ``cancel`` is an optional
    :class:`~xtal.modules.job.Cancellation`; the loop is the only part
    of a simulation long enough to be worth stopping.
    """
    group = gemmi.find_spacegroup_by_name(small.spacegroup_hm)
    if group is None:                                # pragma: no cover
        raise PxrdError(
            f"gemmi does not recognise the space group "
            f"{small.spacegroup_hm!r}")
    operations = list(group.operations())
    calculator = gemmi.StructureFactorCalculatorX(small.cell)
    lower = max(float(two_theta_min), MIN_TWO_THETA)

    out: list[Reflection] = []
    hkls = gemmi.make_miller_array(
        small.cell, group, d_min_for(wavelength, two_theta_max))
    for count, hkl in enumerate(hkls):
        if cancel is not None and count % 256 == 0:
            cancel.check()
        indices = tuple(int(i) for i in hkl)
        d = small.cell.calculate_d(indices)
        if not np.isfinite(d) or d <= 0:             # pragma: no cover
            continue
        two_theta = float(two_theta_from_d(d, wavelength))
        if not np.isfinite(two_theta) or two_theta > two_theta_max:
            continue
        if two_theta < lower:
            continue
        f_squared = abs(calculator.calculate_sf_from_small_structure(
            small, indices)) ** 2
        orbit = equivalents(indices, operations)
        intensity = (f_squared * len(orbit)
                     * float(lorentz_polarization(two_theta))
                     * float(debye_waller(two_theta, wavelength,
                                          b_overall)))
        if intensity > 0:
            out.append(Reflection(representative(orbit), float(d),
                                  two_theta, intensity, len(orbit),
                                  f_squared))
    out.sort(key=lambda r: (r.two_theta, r.hkl))
    return out


def absences(small, wavelength: float = DEFAULT_WAVELENGTH,
             two_theta_min: float = MIN_TWO_THETA,
             two_theta_max: float = 50.0) -> np.ndarray:
    """Where the space group forbids a reflection, in 2-theta.

    The other half of the comb under a pattern, and the one that
    answers a question the allowed half cannot: an unexpected peak is
    either an impurity or the space group being wrong, and *which*
    depends on whether it sits over a position this group forbids.

    Every hkl the *lattice* offers in range, minus the ones the group
    allows -- which is what ``is_systematically_absent`` decides.  So
    a structure in P1 has none at all, because P1 forbids nothing, and
    that is the honest answer rather than an empty result to explain
    away.
    """
    group = gemmi.find_spacegroup_by_name(small.spacegroup_hm)
    if group is None:                                # pragma: no cover
        return np.zeros(0)
    operations = group.operations()
    lower = max(float(two_theta_min), MIN_TWO_THETA)
    out = []
    # P1 offers every hkl the lattice has; the group then forbids
    # some of them, and those are what this is.
    for hkl in gemmi.make_miller_array(
            small.cell, gemmi.find_spacegroup_by_number(1),
            d_min_for(wavelength, two_theta_max)):
        indices = tuple(int(i) for i in hkl)
        if not operations.is_systematically_absent(indices):
            continue
        d = small.cell.calculate_d(indices)
        if not np.isfinite(d) or d <= 0:             # pragma: no cover
            continue
        two_theta = float(two_theta_from_d(d, wavelength))
        if np.isfinite(two_theta) and lower <= two_theta \
                <= two_theta_max:
            out.append(two_theta)
    return np.array(sorted(out), dtype=float)


# ======================================================================
#  PROFILE
# ======================================================================

def profile(x, centre: float, fwhm: float,
            shape: str = "pseudo-voigt",
            eta: float = DEFAULT_ETA) -> np.ndarray:
    """A unit-area peak shape centred at ``centre``.

    Pseudo-Voigt is the usual choice for laboratory data: a Lorentzian
    fraction ``eta`` mixed with a Gaussian, which approximates the
    true Voigt convolution of sample and instrument broadening at a
    fraction of the cost and to well inside the accuracy anybody
    reads off a pattern.
    """
    x = np.asarray(x, dtype=float)
    if fwhm <= 0:
        return np.zeros_like(x)
    key = str(shape).strip().lower()
    if key == "gaussian":
        return _gaussian(x, centre, fwhm)
    if key == "lorentzian":
        return _lorentzian(x, centre, fwhm)
    if key == "pseudo-voigt":
        mix = min(max(float(eta), 0.0), 1.0)
        return (mix * _lorentzian(x, centre, fwhm)
                + (1.0 - mix) * _gaussian(x, centre, fwhm))
    raise PxrdError(
        f"unknown peak shape: {shape!r}; have "
        f"{', '.join(PROFILE_SHAPES)}")


def _gaussian(x, centre, fwhm):
    sigma = fwhm * GAUSSIAN_FWHM_TO_SIGMA
    return (np.exp(-0.5 * ((x - centre) / sigma) ** 2)
            / (sigma * np.sqrt(2.0 * np.pi)))


def _lorentzian(x, centre, fwhm):
    half = fwhm / 2.0
    return half / (np.pi * ((x - centre) ** 2 + half ** 2))


def caglioti_fwhm(two_theta_deg: float, u: float, v: float,
                  w: float) -> float:
    """The peak width at an angle, from the Caglioti relation.

    Zero rather than a complex number where the parabola dips
    negative, which some published U/V/W triples do at low angle; the
    caller drops a reflection with no width rather than drawing an
    imaginary one.
    """
    tan_theta = np.tan(np.radians(two_theta_deg) / 2.0)
    squared = u * tan_theta ** 2 + v * tan_theta + w
    return float(np.sqrt(squared)) if squared > 0 else 0.0


# ======================================================================
#  THE PATTERN
# ======================================================================

@dataclass(frozen=True)
class Pattern:
    """The calculated trace: intensity against 2-theta, and the
    radiation it is against.

    The wavelength travels with the numbers rather than beside them
    because 2-theta is the one axis that moves when the source does,
    and a pattern compared with a measurement taken on a different
    tube is being compared with the wrong thing.  It is the caption a
    plot and an ``.xy`` header both need, and neither could reconstruct
    it.

    A *measured* pattern is two arrays out of :func:`xtal.io.xy.read_xy`
    and is not one of these.  It could be, and the tempting version of
    this record has a ``measured`` flag on it -- but nothing would read
    the flag: the overlay draws whatever it is given and scales each
    trace to its own maximum, which is the only handling the difference
    calls for.
    """

    x: np.ndarray = field(default_factory=lambda: np.zeros(0))
    y: np.ndarray = field(default_factory=lambda: np.zeros(0))
    label: str = ""
    wavelength: float = DEFAULT_WAVELENGTH

    def __len__(self) -> int:
        return len(self.x)

    @property
    def range(self) -> tuple[float, float]:
        if not len(self.x):                          # pragma: no cover
            return (0.0, 0.0)
        return (float(self.x[0]), float(self.x[-1]))


def build_pattern(peaks, two_theta_min: float, two_theta_max: float,
                  step: float = 0.01, shape: str = "pseudo-voigt",
                  caglioti=DEFAULT_CAGLIOTI, eta: float = DEFAULT_ETA,
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Sum the reflection profiles onto a 2-theta grid, scaled to 100.

    Each peak is evaluated only on the slice of the grid near it --
    see :data:`PROFILE_CUTOFF_FWHM`.  Scaled to 100 because the
    absolute value is in electrons squared times a geometry factor and
    means nothing next to a measured pattern's counts.
    """
    if step <= 0:
        raise PxrdError(f"the step has to be positive, got {step}")
    if two_theta_max <= two_theta_min:
        raise PxrdError(
            f"the 2-theta range is empty: {two_theta_min} to "
            f"{two_theta_max}")
    x = np.arange(two_theta_min, two_theta_max + step, step)
    y = np.zeros_like(x)
    u, v, w = caglioti

    for peak in peaks:
        fwhm = caglioti_fwhm(peak.two_theta, u, v, w)
        if fwhm <= 0:
            continue
        span = PROFILE_CUTOFF_FWHM * fwhm
        low = int(np.searchsorted(x, peak.two_theta - span))
        high = int(np.searchsorted(x, peak.two_theta + span))
        if high <= low:
            continue
        y[low:high] += peak.intensity * profile(
            x[low:high], peak.two_theta, fwhm, shape, eta)

    top = float(np.max(y)) if len(y) else 0.0
    if top > 0:
        y = 100.0 * y / top
    return x, y


@dataclass(frozen=True)
class Simulation:
    """A calculated pattern and the reflections it was summed from.

    Both, because they answer different questions: the curve is what
    is compared with a measurement, and the list is what says which
    plane a peak belongs to.  A module that returned only the curve
    would have thrown the indexing away.
    """

    pattern: Pattern
    reflections: tuple[Reflection, ...] = ()
    #: 2-theta of the reflections the space group forbids, when they
    #: were asked for -- see :func:`absences`.
    absent: np.ndarray = field(default_factory=lambda: np.zeros(0))
    wavelength: float = DEFAULT_WAVELENGTH
    space_group: str = ""
    formula: str = ""

    @property
    def strongest(self) -> Reflection | None:
        if not self.reflections:                     # pragma: no cover
            return None
        return max(self.reflections, key=lambda r: r.intensity)

    def scaled_reflections(self) -> list[tuple[Reflection, float]]:
        """Each reflection with its intensity as a percentage of the
        strongest, which is how every reference pattern lists them."""
        top = max((r.intensity for r in self.reflections), default=0.0)
        if top <= 0:                                 # pragma: no cover
            return [(r, 0.0) for r in self.reflections]
        return [(r, 100.0 * r.intensity / top)
                for r in self.reflections]


def simulate(structure, wavelength: float = DEFAULT_WAVELENGTH,
             two_theta_min: float = 5.0, two_theta_max: float = 50.0,
             step: float = 0.01, shape: str = "pseudo-voigt",
             caglioti=DEFAULT_CAGLIOTI, eta: float = DEFAULT_ETA,
             b_overall: float = 0.0, label: str = "",
             with_absences: bool = False,
             cancel=None) -> Simulation:
    """The whole calculation, from an open structure to a curve.

    **The structure is simulated as it is.**  Nothing here detects,
    standardises or otherwise improves the symmetry: a crystal the
    user expanded to P1 is calculated in P1, which gives the same
    pattern and a reflection list three times as long -- and the list
    is what the user asked to see.
    """
    small = to_small_structure(structure, label)
    found = reflections(small, wavelength, two_theta_min,
                        two_theta_max, b_overall, cancel)
    if not found:
        raise PxrdError(
            f"no reflection falls between {two_theta_min:g} and "
            f"{two_theta_max:g} degrees at {wavelength:g} A -- a "
            f"wider range, or a shorter wavelength, would reach some")
    x, y = build_pattern(found, two_theta_min, two_theta_max, step,
                         shape, caglioti, eta)
    name = label or structure.meta.get("title", "") or "structure"
    return Simulation(
        pattern=Pattern(x, y, f"{name} (calculated)", wavelength),
        reflections=tuple(found),
        absent=(absences(small, wavelength, two_theta_min,
                         two_theta_max) if with_absences
                else np.zeros(0)),
        wavelength=wavelength,
        space_group=structure.space_group.hm,
        formula=_formula(structure))


def _formula(structure) -> str:
    """The asymmetric unit's occupancy-weighted composition, for the
    heading -- not the cell contents, which would need the
    multiplicities and is not what this line is for."""
    counts = structure.composition()
    return " ".join(
        f"{symbol}{value:g}" if abs(value - 1.0) > 1e-6 else symbol
        for symbol, value in
        sorted((k, round(float(v), 3)) for k, v in counts.items()))
