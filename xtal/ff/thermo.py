"""
xtal.ff.thermo
==============
Enthalpy, entropy and free energy from vibrational frequencies.

Statistical mechanics over a list of frequencies and nothing else:
where the frequencies came from -- a Gamma-point Hessian, a phonopy
q-mesh, DFTB+'s own modes -- is somebody else's business, so all of
them give an H, S and G that read alike.  The formulas are a page of
numpy and are owned here rather than borrowed from phonopy or ase,
because phonopy's are harmonic only, ase's take a different list per
case, and the quasi-RRHO entropy and the ideal gas need our own
anyway.  phonopy's harmonic numbers are the check, in a test.

Three things are left out of the sum rather than put in it, and
counted so that the report can say so:

* **an imaginary mode** (below :data:`IMAGINARY_BELOW`, the mode
  table's own threshold) has no partition function.  G over a saddle
  point is not a free energy of anything, and the run says that in
  warning tone rather than quietly dropping the mode;
* **a zero mode** (between that and :data:`ZERO_BELOW`) is a
  translation, a free rotation or a Gamma acoustic mode -- zero in
  principle and a few wavenumbers either side of it from finite
  differences.  Its harmonic entropy is ``-ln(nu)``, which is
  infinite at zero and enormous near it, and a molecule's rotations
  are counted again by the ideal gas;
* nothing else.  A **soft mode** (below the quasi-RRHO cutoff) is
  summed either way and counted either way: harmonically by default,
  interpolated towards a free rotor's entropy when asked.

Units are the Force Field panel's: energies kcal/mol, entropy and
heat capacity cal/(mol K), both per cell (or per molecule) unless
:meth:`Thermochemistry.per_unit` divides by Z.  ``thermo.dat`` also
carries kJ/mol and J/(mol K).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# CODATA 2018, exact where the SI now makes them so.
H = 6.62607015e-34              # J s
KB = 1.380649e-23               # J/K
C_CM = 2.99792458e10            # cm/s
NA = 6.02214076e23              # 1/mol
R = KB * NA                     # J/(mol K)
AMU = 1.66053906660e-27         # kg
CAL = 4.184                     # J per cal
BAR = 1.0e5                     # Pa

#: One wavenumber as a molar energy, kcal/mol (0.0028591).
CM_TO_KCAL = H * C_CM * NA / (CAL * 1000.0)
#: h c / k: a wavenumber over this many kelvin is x = h c nu / k T.
CM_TO_K = H * C_CM / KB

#: The mode table's threshold (`report.Modes.IMAGINARY_BELOW`), kept
#: equal by a test: the core cannot import the module layer, and the
#: table and the sum must never disagree about which mode is
#: imaginary.
IMAGINARY_BELOW = -50.0

#: Below this, a mode that is not imaginary is a zero mode.
ZERO_BELOW = 5.0

#: Grimme's cutoff and exponent for the quasi-RRHO entropy, and the
#: moment that limits a free rotor's (Chem. Eur. J. 2012, 18, 9955).
QRRHO_CUTOFF = 100.0
QRRHO_ALPHA = 4
QRRHO_B_AV = 1.0e-44            # kg m^2

#: A principal moment below this (amu A^2) is a linear molecule's.
LINEAR_MOMENT = 1.0e-3


@dataclass(frozen=True)
class Terms:
    """The vibrational part, summed over the modes that count.

    ``zpe``, ``u_vib`` (thermal, above the zero point) and ``f_vib``
    (zero point included) in kcal/mol; ``s_vib`` and ``cv`` in
    cal/(mol K).  The counts are entries of the frequency list."""

    zpe: float
    u_vib: float
    s_vib: float
    cv: float
    f_vib: float
    n_used: int
    n_imaginary: int
    n_zero: int
    n_soft: int


def _split(frequencies, weights, zero_below):
    nu = np.asarray(frequencies, dtype=float).ravel()
    w = (np.ones_like(nu) if weights is None
         else np.asarray(weights, dtype=float).ravel())
    if w.shape != nu.shape:
        raise ValueError("one weight per frequency")
    imaginary = nu < IMAGINARY_BELOW
    used = nu >= max(zero_below, 0.0) if zero_below > 0 else nu > 0.0
    zero = ~imaginary & ~used
    return nu, w, used, int(imaginary.sum()), int(zero.sum())


def _harmonic_entropy(x):
    """S / R per mode at x = h c nu / k T, finite as x grows."""
    with np.errstate(over="ignore"):
        return np.where(x > 700.0, 0.0,
                        x / np.expm1(np.minimum(x, 700.0))
                        - np.log(-np.expm1(-x)))


def harmonic(frequencies, weights=None, *, temperature: float,
             zero_below: float = ZERO_BELOW,
             soft_below: float = QRRHO_CUTOFF) -> Terms:
    """The harmonic vibrational terms of ``frequencies`` (cm^-1).

    ``weights`` make a q-mesh one cell: a mode at each of n points
    weighs 1/n.  Gamma alone is all ones."""
    return _vibrational(frequencies, weights, temperature, zero_below,
                        soft_below, rotor=None)


def quasi_rrho(frequencies, weights=None, *, temperature: float,
               cutoff: float = QRRHO_CUTOFF, alpha: int = QRRHO_ALPHA,
               zero_below: float = ZERO_BELOW) -> Terms:
    """Grimme's quasi-RRHO: the entropy of each mode interpolated
    between the harmonic one and a free rotor's with weight
    ``1 / (1 + (cutoff/nu)^alpha)``.  Only the entropy: the zero point
    and the thermal energy are harmonic, as in Grimme's paper."""
    return _vibrational(frequencies, weights, temperature, zero_below,
                        cutoff, rotor=(cutoff, alpha))


def _vibrational(frequencies, weights, temperature, zero_below,
                 soft_below, rotor) -> Terms:
    nu, w, used, n_imaginary, n_zero = _split(frequencies, weights,
                                              zero_below)
    nu, w = nu[used], w[used]
    n_soft = int(np.count_nonzero(nu < soft_below))
    zpe = float(np.sum(w * 0.5 * nu)) * CM_TO_KCAL
    if temperature <= 0.0 or not len(nu):
        return Terms(zpe, 0.0, 0.0, 0.0, zpe, int(used.sum()),
                     n_imaginary, n_zero, n_soft)
    x = nu * CM_TO_K / temperature
    clipped = np.minimum(x, 700.0)
    with np.errstate(over="ignore", under="ignore"):
        occupation = np.where(x > 700.0, 0.0, 1.0 / np.expm1(clipped))
        heat = np.where(x > 700.0, 0.0,
                        x * x * np.exp(-clipped)
                        / np.expm1(-clipped) ** 2)
    s_mode = _harmonic_entropy(x)
    if rotor is not None:
        cutoff, alpha = rotor
        weight = 1.0 / (1.0 + (cutoff / nu) ** alpha)
        s_mode = weight * s_mode + (1.0 - weight) * _rotor_entropy(
            nu, temperature)
    kt = R * temperature / (CAL * 1000.0)
    u_vib = kt * float(np.sum(w * x * occupation))
    s_vib = R / CAL * float(np.sum(w * s_mode))
    cv = R / CAL * float(np.sum(w * heat))
    f_vib = zpe + u_vib - temperature * s_vib / 1000.0
    return Terms(zpe, u_vib, s_vib, cv, f_vib, int(used.sum()),
                 n_imaginary, n_zero, n_soft)


def _rotor_entropy(nu, temperature):
    """S / R of a free rotor with the moment of a mode at ``nu``,
    capped by :data:`QRRHO_B_AV` so a vanishing mode stays finite."""
    mu = H / (8.0 * np.pi ** 2 * nu * C_CM)
    mu = mu * QRRHO_B_AV / (mu + QRRHO_B_AV)
    return 0.5 + np.log(np.sqrt(
        8.0 * np.pi ** 3 * mu * KB * temperature / H ** 2))


@dataclass(frozen=True)
class GasTerms:
    """Translation, rotation and spin of one ideal-gas molecule:
    ``h_*`` in kcal/mol (translation includes PV), ``s_*`` in
    cal/(mol K)."""

    h_trans: float
    s_trans: float
    h_rot: float
    s_rot: float
    s_elec: float
    linear: bool
    atomic: bool

    @property
    def h(self) -> float:
        return self.h_trans + self.h_rot

    @property
    def s(self) -> float:
        return self.s_trans + self.s_rot + self.s_elec


@dataclass(frozen=True)
class IdealGas:
    """A molecule as an ideal gas: its masses (amu), its cartesian
    geometry (A), its rotational symmetry number, its spin
    multiplicity, and the pressure (bar) its translation is at."""

    masses: tuple
    cart: np.ndarray
    sigma: int = 1
    multiplicity: int = 1
    pressure: float = 1.0

    def moments(self) -> np.ndarray:
        """Principal moments of inertia, amu A^2, ascending."""
        m = np.asarray(self.masses, dtype=float)
        r = np.asarray(self.cart, dtype=float)
        r = r - (m[:, None] * r).sum(axis=0) / m.sum()
        inertia = (np.eye(3) * np.sum(m * np.sum(r * r, axis=1))
                   - np.einsum("i,ij,ik->jk", m, r, r))
        return np.linalg.eigvalsh(inertia)

    def terms(self, temperature: float) -> GasTerms:
        if temperature <= 0.0:
            raise ValueError("an ideal gas needs a temperature above 0")
        kt = KB * temperature
        rt = R * temperature / (CAL * 1000.0)
        mass = float(np.sum(self.masses)) * AMU
        volume = kt / (self.pressure * BAR)
        q_trans = (2.0 * np.pi * mass * kt / H ** 2) ** 1.5 * volume
        s_trans = R * (np.log(q_trans) + 2.5) / CAL
        s_elec = R * np.log(self.multiplicity) / CAL
        moments = self.moments()
        atomic = len(self.masses) == 1 or moments[-1] < LINEAR_MOMENT
        if atomic:
            return GasTerms(2.5 * rt, s_trans, 0.0, 0.0, s_elec,
                            False, True)
        si = moments * AMU * 1e-20
        linear = bool(moments[0] < LINEAR_MOMENT)
        if linear:
            q_rot = 8.0 * np.pi ** 2 * si[-1] * kt / (self.sigma * H ** 2)
            s_rot, h_rot = R * (np.log(q_rot) + 1.0) / CAL, rt
        else:
            q_rot = (np.sqrt(np.pi) / self.sigma
                     * (8.0 * np.pi ** 2 * kt / H ** 2) ** 1.5
                     * np.sqrt(np.prod(si)))
            s_rot, h_rot = R * (np.log(q_rot) + 1.5) / CAL, 1.5 * rt
        return GasTerms(2.5 * rt, s_trans, h_rot, s_rot, s_elec,
                        linear, False)


@dataclass(frozen=True)
class Thermochemistry:
    """H, S and G at one temperature.

    Energies kcal/mol and entropies cal/(mol K), per cell (a crystal)
    or per molecule (a gas); :meth:`per_unit` divides by ``z``.  For a
    crystal ``g`` is the Helmholtz energy: PV of a solid at one bar is
    a few thousandths of a kcal/mol per cell, and the report says G is
    F rather than pretending to a term it did not compute."""

    temperature: float
    kind: str                   # "crystal" or "molecule"
    e_elec: float
    zpe: float
    h: float
    s: float
    g: float
    cv: float
    z: int
    vibrations: Terms
    gas: GasTerms | None = None
    quasi_rrho: bool = False
    pressure: float = 1.0

    @property
    def ts(self) -> float:
        """T S in kcal/mol."""
        return self.temperature * self.s / 1000.0

    def per_unit(self, value: float) -> float:
        return value / self.z

    def as_rows(self) -> list[tuple[str, float, float, str]]:
        """``(label, per cell, per formula unit, unit)``, the Summary
        table's quantities in the order the report shows them."""
        g = "G" if self.kind == "molecule" else "G (= F)"
        rows = [("E (electronic)", self.e_elec, "kcal/mol"),
                ("Zero-point energy", self.zpe, "kcal/mol"),
                (f"H({self.temperature:g} K)", self.h, "kcal/mol"),
                (f"T S({self.temperature:g} K)", self.ts, "kcal/mol"),
                (f"{g}({self.temperature:g} K)", self.g, "kcal/mol"),
                ("S", self.s, "cal/(mol K)"),
                ("Cv", self.cv, "cal/(mol K)")]
        return [(label, value, self.per_unit(value), unit)
                for label, value, unit in rows]


def thermochemistry(frequencies, weights=None, *, temperature: float,
                    e_elec: float = 0.0, gas: IdealGas | None = None,
                    quasi_rrho: bool = False,
                    cutoff: float = QRRHO_CUTOFF,
                    z: int = 1) -> Thermochemistry:
    """H, S and G at ``temperature`` from ``frequencies`` (cm^-1).

    With ``gas`` the frequencies are a molecule's and translation,
    rotation, spin and PV are added; without it they are a crystal's
    and G is F."""
    if quasi_rrho:
        vib = globals()["quasi_rrho"](frequencies, weights,
                                      temperature=temperature,
                                      cutoff=cutoff)
    else:
        vib = harmonic(frequencies, weights, temperature=temperature,
                       soft_below=cutoff)
    h = e_elec + vib.zpe + vib.u_vib
    s, cv = vib.s_vib, vib.cv
    rigid = None
    if gas is not None:
        rigid = gas.terms(temperature)
        h += rigid.h
        s += rigid.s
        # Cp of the rigid body less R: Cv of translation and rotation.
        cv += (rigid.h * 1000.0 / temperature) - R / CAL
    g = h - temperature * s / 1000.0
    return Thermochemistry(
        temperature=temperature,
        kind="crystal" if gas is None else "molecule",
        e_elec=e_elec, zpe=vib.zpe, h=h, s=s, g=g, cv=cv, z=max(int(z), 1),
        vibrations=vib, gas=rigid, quasi_rrho=bool(quasi_rrho),
        pressure=gas.pressure if gas is not None else 1.0)


def as_dat(results) -> str:
    """``thermo.dat``: one row per temperature, per cell, in kcal and
    in kJ, so neither unit system has to be converted by hand."""
    kj = CAL
    head = ("# T(K)  H(kcal/mol)  TS(kcal/mol)  G(kcal/mol)  "
            "S(cal/mol/K)  Cv(cal/mol/K)  ZPE(kcal/mol)  "
            "H(kJ/mol)  TS(kJ/mol)  G(kJ/mol)  S(J/mol/K)  Cv(J/mol/K)")
    lines = []
    if results:
        first = results[0]
        lines.append(f"# {first.kind}, per cell; Z = {first.z}; "
                     f"E(electronic) = {first.e_elec:.6f} kcal/mol")
        if first.kind == "crystal":
            lines.append("# G is the Helmholtz energy F: PV of a solid "
                         "is left out")
    lines.append(head)
    for r in results:
        lines.append("  ".join(f"{v:.6f}" for v in (
            r.temperature, r.h, r.ts, r.g, r.s, r.cv, r.zpe,
            r.h * kj, r.ts * kj, r.g * kj, r.s * kj, r.cv * kj)))
    return "\n".join(lines) + "\n"
