"""
xtal.ff.uff.params
==================
The UFF parameter table -- Rappe, Casewit, Colwell, Goddard and Skiff,
*J. Am. Chem. Soc.* **1992**, 114, 10024, Table 1.

One frozen record per atom type, 126 of them, covering the whole
periodic table up to lawrencium.  Nothing here is computed; every
number is transcribed from the paper.  The formulas that consume them
live in :mod:`xtal.ff.uff.terms`, and which type an atom gets is
:mod:`xtal.ff.uff.typer`'s decision.

**The type name is data, not a label.**  UFF names a type in five
characters: the element right-padded with ``_`` to two, then one
character of geometry, then the formal oxidation state.  ``Fe6+2`` is
octahedral iron(II); ``C_R`` is a resonant (aromatic) carbon.  The
geometry character is what the typer keys on when it meets an element
it has no hand-written rule for, which is how a table of parameters
doubles as a table of expected coordination numbers -- and why adding a
type needs no code.

Units throughout: Angstrom, degrees, kcal/mol, and electron charges.
"""

from __future__ import annotations

from dataclasses import dataclass

# Geometry character -> the coordination number it describes.  ``R``
# (resonant) and ``_`` (no geometry given, e.g. ``H_``, ``Cl``) carry
# no coordination of their own and are handled by the typer.
GEOMETRY_COORDINATION = {
    "1": 1,      # linear / terminal
    "2": 3,      # trigonal planar
    "3": 4,      # tetrahedral
    "4": 4,      # square planar
    "5": 5,      # trigonal bipyramidal
    "6": 6,      # octahedral
}

# The same character, in words.  This is what the five-character name
# never says out loud: that the ``3`` of ``Zn3+2`` is a shape and the
# ``6`` of ``Fe6+2`` is another one.
GEOMETRY_WORDS = {
    "1": "linear",
    "2": "trigonal planar",
    "3": "tetrahedral",
    "4": "square planar",
    "5": "trigonal bipyramidal",
    "6": "octahedral",
    "R": "resonant",
    "b": "bridging",     # ``H_b``, the hydrogen between two borons
}

# And what it means for a main-group atom, where the same character is
# a hybridisation rather than a coordination polyhedron: the ``3`` of
# ``O_3`` is sp3, not tetrahedral oxygen.  Only the three that are a
# hybridisation are here; a main-group type with any other geometry
# character falls back to the shape word above.
HYBRIDISATION_WORDS = {
    "1": "sp",
    "2": "sp2",
    "3": "sp3",
    "R": "resonant",
}

# What is left over once the element, the geometry character and the
# oxidation state have been read off.  One entry, and it says the
# thing the name is otherwise silent about: ``O_3_z`` is the oxygen
# fitted to the Si-O-Si of a zeolite and not an ordinary ether oxygen.
QUALIFIERS = {
    "O_3_z": "zeolitic",
}

# The 1992 paper spells lawrencium ``Lw``; the periodic table this
# application ships calls it ``Lr``.
IUPAC_SYMBOL = {"Lw": "Lr"}

_ROMAN = ("0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII")


def roman(number: int) -> str:
    """``2`` -> ``"II"``.  Oxidation states, as chemists write them."""
    if 0 <= number < len(_ROMAN):
        return _ROMAN[number]
    return str(number)                              # pragma: no cover


@dataclass(frozen=True)
class UFFParams:
    """One row of Table 1."""

    name: str           # the five-character type, e.g. "C_R"
    r1: float           # valence bond radius, Angstrom
    theta0: float       # equilibrium valence angle, degrees
    x1: float           # van der Waals distance, Angstrom
    d1: float           # van der Waals well depth, kcal/mol
    zeta: float         # van der Waals scale (unused by LJ 12-6)
    z1: float           # effective charge Z*
    vi: float           # sp3 torsional barrier, kcal/mol
    uj: float           # sp2 torsional constant, kcal/mol
    chi: float          # GMP electronegativity, eV (QEq)
    hard: float         # idempotential / hardness, eV (QEq)
    radius: float       # QEq effective radius, Angstrom

    @property
    def element(self) -> str:
        """The element this type belongs to."""
        return self.name[:2].rstrip("_").rstrip("0123456789+-")

    @property
    def geometry(self) -> str:
        """The geometry character, or ``""`` when the name has none."""
        if len(self.name) < 3:
            return ""
        char = self.name[2]
        return "" if char in "_+-" else char

    @property
    def coordination(self) -> int | None:
        """How many neighbours this type expects, or ``None`` when the
        name does not say (``H_``, ``C_R``, the halogens)."""
        return GEOMETRY_COORDINATION.get(self.geometry)

    @property
    def oxidation_state(self) -> int | None:
        """The formal charge in the name, e.g. ``+2`` in ``Fe6+2``."""
        tail = self.name[3:]
        if tail[:1] in "+-" and tail[1:].isdigit():
            return int(tail[0] + tail[1:])
        return None

    @property
    def is_resonant(self) -> bool:
        return self.geometry == "R"

    @property
    def symbol(self) -> str:
        """The element, spelled the way the rest of the application
        spells it."""
        return IUPAC_SYMBOL.get(self.element, self.element)

    @property
    def is_metal(self) -> bool:
        from xtal.core import elements
        try:
            return elements.element(self.symbol).is_metal
        except ValueError:                          # pragma: no cover
            return False

    @property
    def shape(self) -> str:
        """The geometry character in words, or ``""``.

        A metal's geometry character is a coordination polyhedron and a
        main-group atom's is a hybridisation, so the same ``3`` reads
        as *tetrahedral* on zinc and as *sp3* on oxygen.  Both are the
        same fact about the same character; which word to say depends
        only on which half of the table the element is in.
        """
        char = "R" if self.is_resonant else self.geometry
        if not self.is_metal and char in HYBRIDISATION_WORDS:
            return HYBRIDISATION_WORDS[char]
        return GEOMETRY_WORDS.get(char, "")

    @property
    def description(self) -> str:
        """The type name as a sentence: ``"tetrahedral Zn(II)"``.

        Built from the parts of the name rather than looked up, so a
        type added to the table above needs no entry anywhere and is
        readable the moment it exists.  It never replaces the name --
        the name is what Rappe's Table 1 is indexed by and what an
        override is stored as -- it goes beside it.
        """
        from xtal.core import elements
        try:
            noun = elements.element(self.symbol).name.lower()
        except ValueError:                          # pragma: no cover
            noun = self.symbol
        state = self.oxidation_state
        if state is not None:
            noun = (f"{self.symbol}({roman(state)})" if self.is_metal
                    else f"{noun}({roman(state)})")
        parts = [w for w in (self.shape, noun) if w]
        out = " ".join(parts)
        qualifier = QUALIFIERS.get(self.name)
        return f"{out}, {qualifier}" if qualifier else out


def _rows() -> list[UFFParams]:
    """Table 1, in the paper's order.

    Written out rather than shipped as a data file: it is the module's
    subject, it never changes, and a reader looking for the number that
    made a bond too stiff should find it here and not in a JSON blob
    two directories away.
    """
    raw = """
    H_     0.354  180.00  2.886  0.044  12.000  0.712  0.000  0.000   4.5280   6.9452  0.371
    H_b    0.460   83.50  2.886  0.044  12.000  0.712  0.000  0.000   4.5280   6.9452  0.371
    He4+4  0.849   90.00  2.362  0.056  15.240  0.098  0.000  0.000   9.6600  14.9200  1.300
    Li     1.336  180.00  2.451  0.025  12.000  1.026  0.000  2.000   3.0060   2.3860  1.557
    Be3+2  1.074  109.47  2.745  0.085  12.000  1.565  0.000  2.000   4.8770   4.4430  1.240
    B_3    0.838  109.47  4.083  0.180  12.052  1.755  0.000  2.000   5.1100   4.7500  0.822
    B_2    0.828  120.00  4.083  0.180  12.052  1.755  0.000  2.000   5.1100   4.7500  0.822
    C_3    0.757  109.47  3.851  0.105  12.730  1.912  2.119  2.000   5.3430   5.0630  0.759
    C_R    0.729  120.00  3.851  0.105  12.730  1.912  0.000  2.000   5.3430   5.0630  0.759
    C_2    0.732  120.00  3.851  0.105  12.730  1.912  0.000  2.000   5.3430   5.0630  0.759
    C_1    0.706  180.00  3.851  0.105  12.730  1.912  0.000  2.000   5.3430   5.0630  0.759
    N_3    0.700  106.70  3.660  0.069  13.407  2.544  0.450  2.000   6.8990   5.8800  0.715
    N_R    0.699  120.00  3.660  0.069  13.407  2.544  0.000  2.000   6.8990   5.8800  0.715
    N_2    0.685  111.20  3.660  0.069  13.407  2.544  0.000  2.000   6.8990   5.8800  0.715
    N_1    0.656  180.00  3.660  0.069  13.407  2.544  0.000  2.000   6.8990   5.8800  0.715
    O_3    0.658  104.51  3.500  0.060  14.085  2.300  0.018  2.000   8.7410   6.6820  0.669
    O_3_z  0.528  145.45  3.500  0.060  14.085  2.300  0.018  2.000   8.7410   6.6820  0.669
    O_R    0.680  110.00  3.500  0.060  14.085  2.300  0.000  2.000   8.7410   6.6820  0.669
    O_2    0.634  120.00  3.500  0.060  14.085  2.300  0.000  2.000   8.7410   6.6820  0.669
    O_1    0.639  180.00  3.500  0.060  14.085  2.300  0.000  2.000   8.7410   6.6820  0.669
    F_     0.668  180.00  3.364  0.050  14.762  1.735  0.000  2.000  10.8740   7.4740  0.706
    Ne4+4  0.920   90.00  3.243  0.042  15.440  0.194  0.000  2.000  11.0400  10.5500  1.768
    Na     1.539  180.00  2.983  0.030  12.000  1.081  0.000  1.250   2.8430   2.2960  2.085
    Mg3+2  1.421  109.47  3.021  0.111  12.000  1.787  0.000  1.250   3.9510   3.6930  1.500
    Al3    1.244  109.47  4.499  0.505  11.278  1.792  0.000  1.250   4.0600   3.5900  1.201
    Si3    1.117  109.47  4.295  0.402  12.175  2.323  1.225  1.250   4.1680   3.4870  1.176
    P_3+3  1.101   93.80  4.147  0.305  13.072  2.863  2.400  1.250   5.4630   4.0000  1.102
    P_3+5  1.056  109.47  4.147  0.305  13.072  2.863  2.400  1.250   5.4630   4.0000  1.102
    P_3+q  1.056  109.47  4.147  0.305  13.072  2.863  2.400  1.250   5.4630   4.0000  1.102
    S_3+2  1.064   92.10  4.035  0.274  13.969  2.703  0.484  1.250   6.9280   4.4860  1.047
    S_3+4  1.049  103.20  4.035  0.274  13.969  2.703  0.484  1.250   6.9280   4.4860  1.047
    S_3+6  1.027  109.47  4.035  0.274  13.969  2.703  0.484  1.250   6.9280   4.4860  1.047
    S_R    1.077   92.20  4.035  0.274  13.969  2.703  0.000  1.250   6.9280   4.4860  1.047
    S_2    0.854  120.00  4.035  0.274  13.969  2.703  0.000  1.250   6.9280   4.4860  1.047
    Cl     1.044  180.00  3.947  0.227  14.866  2.348  0.000  1.250   8.5640   4.9460  0.994
    Ar4+4  1.032   90.00  3.868  0.185  15.763  0.300  0.000  1.250   9.4650   6.3550  2.108
    K_     1.953  180.00  3.812  0.035  12.000  1.165  0.000  0.700   2.4210   1.9200  2.586
    Ca6+2  1.761   90.00  3.399  0.238  12.000  2.141  0.000  0.700   3.2310   2.8800  2.000
    Sc3+3  1.513  109.47  3.295  0.019  12.000  2.592  0.000  0.700   3.3950   3.0800  1.750
    Ti3+4  1.412  109.47  3.175  0.017  12.000  2.659  0.000  0.700   3.4700   3.3800  1.607
    Ti6+4  1.412   90.00  3.175  0.017  12.000  2.659  0.000  0.700   3.4700   3.3800  1.607
    V_3+5  1.402  109.47  3.144  0.016  12.000  2.679  0.000  0.700   3.6500   3.4100  1.470
    Cr6+3  1.345   90.00  3.023  0.015  12.000  2.463  0.000  0.700   3.4150   3.8650  1.402
    Mn6+2  1.382   90.00  2.961  0.013  12.000  2.430  0.000  0.700   3.3250   4.1050  1.533
    Fe3+2  1.270  109.47  2.912  0.013  12.000  2.430  0.000  0.700   3.7600   4.1400  1.393
    Fe6+2  1.335   90.00  2.912  0.013  12.000  2.430  0.000  0.700   3.7600   4.1400  1.393
    Co6+3  1.241   90.00  2.872  0.014  12.000  2.430  0.000  0.700   4.1050   4.1750  1.406
    Ni4+2  1.164   90.00  2.834  0.015  12.000  2.430  0.000  0.700   4.4650   4.2050  1.398
    Cu3+1  1.302  109.47  3.495  0.005  12.000  1.756  0.000  0.700   4.2000   4.2200  1.434
    Zn3+2  1.193  109.47  2.763  0.124  12.000  1.308  0.000  0.700   5.1060   4.2850  1.400
    Ga3+3  1.260  109.47  4.383  0.415  11.000  1.821  0.000  0.700   3.6410   3.1600  1.211
    Ge3    1.197  109.47  4.280  0.379  12.000  2.789  0.701  0.700   4.0510   3.4380  1.189
    As3+3  1.211   92.10  4.230  0.309  13.000  2.864  1.500  0.700   5.1880   3.8090  1.204
    Se3+2  1.190   90.60  4.205  0.291  14.000  2.764  0.335  0.700   6.4280   4.1310  1.224
    Br     1.192  180.00  4.189  0.251  15.000  2.519  0.000  0.700   7.7900   4.4250  1.141
    Kr4+4  1.147   90.00  4.141  0.220  16.000  0.452  0.000  0.700   8.5050   5.7150  2.270
    Rb     2.260  180.00  4.114  0.040  12.000  1.592  0.000  0.200   2.3310   1.8460  2.770
    Sr6+2  2.052   90.00  3.641  0.235  12.000  2.449  0.000  0.200   3.0240   2.4400  2.415
    Y_3+3  1.698  109.47  3.345  0.072  12.000  3.257  0.000  0.200   3.8300   2.8100  1.998
    Zr3+4  1.564  109.47  3.124  0.069  12.000  3.667  0.000  0.200   3.4000   3.5500  1.758
    Nb3+5  1.473  109.47  3.165  0.059  12.000  3.618  0.000  0.200   3.5500   3.3800  1.603
    Mo6+6  1.467   90.00  3.052  0.056  12.000  3.400  0.000  0.200   3.4650   3.7550  1.530
    Mo3+6  1.484  109.47  3.052  0.056  12.000  3.400  0.000  0.200   3.4650   3.7550  1.530
    Tc6+5  1.322   90.00  2.998  0.048  12.000  3.400  0.000  0.200   3.2900   3.9900  1.500
    Ru6+2  1.478   90.00  2.963  0.056  12.000  3.400  0.000  0.200   3.5750   4.0150  1.500
    Rh6+3  1.332   90.00  2.929  0.053  12.000  3.508  0.000  0.200   3.9750   4.0050  1.509
    Pd4+2  1.338   90.00  2.899  0.048  12.000  3.210  0.000  0.200   4.3200   4.0000  1.544
    Ag1+1  1.386  180.00  3.148  0.036  12.000  1.956  0.000  0.200   4.4360   3.1340  1.622
    Cd3+2  1.403  109.47  2.848  0.228  12.000  1.650  0.000  0.200   5.0340   3.9570  1.600
    In3+3  1.459  109.47  4.463  0.599  11.000  2.070  0.000  0.200   3.5060   2.8960  1.404
    Sn3    1.398  109.47  4.392  0.567  12.000  2.961  0.199  0.200   3.9870   3.1240  1.354
    Sb3+3  1.407   91.60  4.420  0.449  13.000  2.704  1.100  0.200   4.8990   3.3420  1.404
    Te3+2  1.386   90.25  4.470  0.398  14.000  2.882  0.300  0.200   5.8160   3.5260  1.380
    I_     1.382  180.00  4.500  0.339  15.000  2.650  0.000  0.200   6.8220   3.7620  1.333
    Xe4+4  1.267   90.00  4.404  0.332  12.000  0.556  0.000  0.200   7.5950   4.9750  2.459
    Cs     2.570  180.00  4.517  0.045  12.000  1.573  0.000  0.100   2.1830   1.7110  2.984
    Ba6+2  2.277   90.00  3.703  0.364  12.000  2.727  0.000  0.100   2.8140   2.3960  2.442
    La3+3  1.943  109.47  3.522  0.017  12.000  3.300  0.000  0.100   2.8355   2.7415  2.071
    Ce6+3  1.841   90.00  3.556  0.013  12.000  3.300  0.000  0.100   2.7740   2.6920  1.925
    Pr6+3  1.823   90.00  3.606  0.010  12.000  3.300  0.000  0.100   2.8580   2.5640  2.007
    Nd6+3  1.816   90.00  3.575  0.010  12.000  3.300  0.000  0.100   2.8685   2.6205  2.007
    Pm6+3  1.801   90.00  3.547  0.009  12.000  3.300  0.000  0.100   2.8810   2.6730  2.000
    Sm6+3  1.780   90.00  3.520  0.008  12.000  3.300  0.000  0.100   2.9115   2.7195  1.978
    Eu6+3  1.771   90.00  3.493  0.008  12.000  3.300  0.000  0.100   2.8785   2.7875  2.227
    Gd6+3  1.735   90.00  3.368  0.009  12.000  3.300  0.000  0.100   3.1665   2.9745  1.968
    Tb6+3  1.732   90.00  3.451  0.007  12.000  3.300  0.000  0.100   3.0180   2.8340  1.954
    Dy6+3  1.710   90.00  3.428  0.007  12.000  3.300  0.000  0.100   3.0555   2.8715  1.934
    Ho6+3  1.696   90.00  3.409  0.007  12.000  3.416  0.000  0.100   3.1270   2.8910  1.925
    Er6+3  1.673   90.00  3.391  0.007  12.000  3.300  0.000  0.100   3.1865   2.9145  1.915
    Tm6+3  1.660   90.00  3.374  0.006  12.000  3.300  0.000  0.100   3.2514   2.9329  2.000
    Yb6+3  1.637   90.00  3.355  0.228  12.000  2.618  0.000  0.100   3.2889   2.9650  2.158
    Lu6+3  1.671   90.00  3.640  0.041  12.000  3.271  0.000  0.100   2.9629   2.4629  1.896
    Hf3+4  1.611  109.47  3.141  0.072  12.000  3.921  0.000  0.100   3.7000   3.4000  1.759
    Ta3+5  1.511  109.47  3.170  0.081  12.000  4.075  0.000  0.100   5.1000   2.8500  1.605
    W_6+6  1.392   90.00  3.069  0.067  12.000  3.700  0.000  0.100   4.6300   3.3100  1.538
    W_3+4  1.526  109.47  3.069  0.067  12.000  3.700  0.000  0.100   4.6300   3.3100  1.538
    W_3+6  1.380  109.47  3.069  0.067  12.000  3.700  0.000  0.100   4.6300   3.3100  1.538
    Re6+5  1.372   90.00  2.954  0.066  12.000  3.700  0.000  0.100   3.9600   3.9200  1.600
    Re3+7  1.314  109.47  2.954  0.066  12.000  3.700  0.000  0.100   3.9600   3.9200  1.600
    Os6+6  1.372   90.00  3.120  0.037  12.000  3.700  0.000  0.100   5.1400   3.6300  1.700
    Ir6+3  1.371   90.00  2.840  0.073  12.000  3.731  0.000  0.100   5.0000   4.0000  1.866
    Pt4+2  1.364   90.00  2.754  0.080  12.000  3.382  0.000  0.100   4.7900   4.4300  1.557
    Au4+3  1.262   90.00  3.293  0.039  12.000  2.625  0.000  0.100   4.8940   2.5860  1.618
    Hg1+2  1.340  180.00  2.705  0.385  12.000  1.750  0.000  0.100   6.2700   4.1600  1.600
    Tl3+3  1.518  120.00  4.347  0.680  11.000  2.068  0.000  0.100   3.2000   2.9000  1.530
    Pb3    1.459  109.47  4.297  0.663  12.000  2.846  0.100  0.100   3.9000   3.5300  1.444
    Bi3+3  1.512   90.00  4.370  0.518  13.000  2.470  1.000  0.100   4.6900   3.7400  1.514
    Po3+2  1.500   90.00  4.709  0.325  14.000  2.330  0.300  0.100   4.2100   3.1150  1.480
    At     1.545  180.00  4.750  0.284  15.000  2.240  0.000  0.100   4.7500   3.0000  1.470
    Rn4+4  1.420   90.00  4.765  0.248  16.000  0.583  0.000  0.100   5.3700   3.5000  2.200
    Fr     2.880  180.00  4.900  0.050  12.000  1.847  0.000  0.000   2.0000   2.0000  2.300
    Ra6+2  2.512   90.00  3.677  0.404  12.000  2.920  0.000  0.000   2.8430   2.4340  2.200
    Ac6+3  1.983   90.00  3.478  0.033  12.000  3.900  0.000  0.000   2.8350   2.8350  2.108
    Th6+4  1.721   90.00  3.396  0.026  12.000  4.202  0.000  0.000   3.1750   2.9050  2.018
    Pa6+4  1.711   90.00  3.424  0.022  12.000  3.900  0.000  0.000   2.9850   2.9050  1.800
    U_6+4  1.684   90.00  3.395  0.022  12.000  3.900  0.000  0.000   3.3410   2.8530  1.713
    Np6+4  1.666   90.00  3.424  0.019  12.000  3.900  0.000  0.000   3.5490   2.7170  1.800
    Pu6+4  1.657   90.00  3.424  0.016  12.000  3.900  0.000  0.000   3.2430   2.8190  1.840
    Am6+4  1.660   90.00  3.381  0.014  12.000  3.900  0.000  0.000   2.9895   3.0035  1.942
    Cm6+3  1.801   90.00  3.326  0.013  12.000  3.900  0.000  0.000   2.8315   3.1895  1.900
    Bk6+3  1.761   90.00  3.339  0.013  12.000  3.900  0.000  0.000   3.1935   3.0355  1.900
    Cf6+3  1.750   90.00  3.313  0.013  12.000  3.900  0.000  0.000   3.1970   3.1010  1.900
    Es6+3  1.724   90.00  3.299  0.012  12.000  3.900  0.000  0.000   3.3330   3.0890  1.900
    Fm6+3  1.712   90.00  3.286  0.012  12.000  3.900  0.000  0.000   3.4000   3.1000  1.900
    Md6+3  1.689   90.00  3.274  0.011  12.000  3.900  0.000  0.000   3.4700   3.1100  1.900
    No6+3  1.679   90.00  3.248  0.011  12.000  3.900  0.000  0.000   3.4750   3.1750  1.900
    Lw6+3  1.698   90.00  3.236  0.011  12.000  3.900  0.000  0.000   3.5000   3.2000  1.900
    """
    out = []
    for line in raw.strip().splitlines():
        name, *numbers = line.split()
        out.append(UFFParams(name, *(float(v) for v in numbers)))
    return out


PARAMS: dict[str, UFFParams] = {p.name: p for p in _rows()}

# Element -> its types, in table order.  The typer walks this when it
# has no hand-written rule for an element, which is most of the
# periodic table.
BY_ELEMENT: dict[str, list[UFFParams]] = {}
for _p in PARAMS.values():
    BY_ELEMENT.setdefault(_p.element, []).append(_p)

# The 1992 paper spells lawrencium ``Lw``; IUPAC settled on ``Lr`` in
# 1997, and that is what the rest of the application calls it.  The
# type name keeps the paper's spelling -- it is a quotation -- and the
# element lookup accepts ours.
BY_ELEMENT["Lr"] = BY_ELEMENT["Lw"]


# ======================================================================
#  LOOKUP
# ======================================================================

def get(name: str) -> UFFParams:
    """Parameters for a type name."""
    try:
        return PARAMS[name]
    except KeyError:
        raise KeyError(
            f"{name!r} is not a UFF atom type; "
            f"see xtal.ff.uff.params.PARAMS for the {len(PARAMS)} "
            f"types the force field knows") from None


def types_for(element: str) -> list[str]:
    """Every type this element has, in table order.

    Empty for an element UFF does not cover, which the typer reports
    as a refusal rather than guessing a substitute.
    """
    return [p.name for p in BY_ELEMENT.get(element, [])]


def has_element(element: str) -> bool:
    return element in BY_ELEMENT


def names() -> list[str]:
    return list(PARAMS)


# ======================================================================
#  DERIVED CONSTANTS
# ======================================================================
#
# The three numbers the UFF formulas carry that are not per-type.

# Bond-order correction coefficient, eq 3 of the paper.
LAMBDA = 0.1332
# Bond and angle force constants, eq 6 and 13.  Angstrom, kcal/mol.
FORCE_CONSTANT = 664.12
# Coulomb prefactor: e^2 / (4 pi eps0) in kcal A / mol.
COULOMB = 332.0637
