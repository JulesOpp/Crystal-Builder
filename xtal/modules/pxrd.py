"""
xtal.modules.pxrd
=================
A calculated powder pattern, as a registry entry.

The science is :mod:`xtal.analysis.pxrd` and nothing here computes
anything: this file is the parameters, the report and the two files
left in the run folder.  The same split as :mod:`xtal.modules.zeopp`,
which parses in :mod:`xtal.analysis.porosity` and runs here.

**It is the module the report grew a block for.**
:mod:`xtal.modules.report` said the second module that needed
something its three records could not say would get to add it against
a real use.  A pattern is that use -- ten thousand points on an angle
axis is not a histogram of anything -- and
:class:`~xtal.modules.report.Curve` is what came of it.

**Two files, and each is a different question.**  ``pattern.xy`` is
the calculation as two columns, which is what gets loaded into
whatever the group already plots with; ``reflections.txt`` is the
indexed list, which is what says *which plane* the peak at 27.4
degrees belongs to.  Neither is derivable from the other by anybody
reading the folder later.

**Nothing is greyed out.**  numpy and gemmi are core dependencies and
the calculation needs no binary, so -- like :mod:`xtal.modules.net` --
there is no ``check``, because there is no state in which the entry
is present and cannot run.  matplotlib is the extra, and it buys the
*overlay window*, not the pattern; the panel draws the answer without
it.
"""

from __future__ import annotations

from xtal.analysis import pxrd
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param
from xtal.modules.report import Curve, Report, Row, Table

__all__ = ["PARAMS", "PXRD", "register", "simulate_pattern"]

#: What every number in this report is worth reading against.  It is
#: the report note and the note on the intensity rows for the same
#: reason :class:`~xtal.modules.report.Row` has one at all: it is
#: where somebody reads the number, so it is where the caveat has to
#: be.
#: The reflection table's own columns -- five different quantities
#: across one row, which is not what :data:`Row.label` / ``value`` /
#: ``unit`` describes.  See :class:`xtal.modules.report.Row`.
REFLECTION_COLUMNS = ("No.", "hkl", "d (Å)", "2θ (°)",
                      "I (%)")

CAVEAT = (
    "Calculated intensities assume the structure is complete.  A "
    "framework refined without its disordered solvent, or with "
    "partial occupancies, gives peak positions that are right and "
    "intensities that need not be -- and a real powder shows "
    "preferred orientation on top of that.")

PARAMS = (
    Param("source", "Radiation", kind="choice",
          default="cu-ka1",
          choices=tuple((key, label) for key, label, _v
                        in pxrd.WAVELENGTHS),
          help="Which tube the pattern is calculated for.  2-theta "
               "moves when this does, so a pattern compared with a "
               "measurement has to be calculated for the same "
               "source."),
    Param("wavelength", "Wavelength", kind="float",
          default=pxrd.DEFAULT_WAVELENGTH, minimum=0.1, maximum=10.0,
          decimals=5, suffix=" A",
          help="Used only when the radiation above is 'Use the "
               "wavelength below'."),
    Param("two_theta_min", "2-theta from", kind="float", default=5.0,
          minimum=0.5, maximum=179.0, decimals=2, suffix=" deg",
          help="Below about half a degree the Lorentz-polarisation "
               "factor diverges and no instrument measures, so that "
               "is the floor."),
    Param("two_theta_max", "2-theta to", kind="float", default=50.0,
          minimum=1.0, maximum=180.0, decimals=2, suffix=" deg",
          help="A wider range is more reflections and a longer "
               "calculation.  Fifty degrees is where a laboratory "
               "MOF pattern stops being worth plotting."),
    Param("step", "Step", kind="float", default=0.01, minimum=0.001,
          maximum=1.0, decimals=4, suffix=" deg",
          help="The 2-theta grid the profiles are summed onto.  It "
               "has to be several times finer than the peak width "
               "or the peaks come out as spikes."),
    Param("shape", "Peak shape", kind="choice",
          default="pseudo-voigt",
          choices=(("pseudo-voigt", "Pseudo-Voigt"),
                   ("gaussian", "Gaussian"),
                   ("lorentzian", "Lorentzian")),
          help="Pseudo-Voigt is the usual choice for laboratory "
               "data: a Lorentzian fraction mixed with a Gaussian, "
               "approximating the convolution of sample and "
               "instrument broadening."),
    Param("eta", "Lorentzian fraction", kind="float",
          default=pxrd.DEFAULT_ETA, minimum=0.0, maximum=1.0,
          decimals=2,
          help="The Pseudo-Voigt mixing parameter: 0 is a pure "
               "Gaussian and 1 a pure Lorentzian.  Ignored by the "
               "other two shapes."),
    Param("caglioti_u", "Caglioti U", kind="float", default=0.004,
          minimum=-1.0, maximum=1.0, decimals=5,
          help="Peak width against angle: FWHM^2 = U tan^2(theta) + "
               "V tan(theta) + W, in degrees squared.  The three "
               "defaults are a typical laboratory diffractometer."),
    Param("caglioti_v", "Caglioti V", kind="float", default=-0.002,
          minimum=-1.0, maximum=1.0, decimals=5,
          help="The linear term of the width relation.  Often "
               "negative, which is why a very low-angle peak can "
               "come out with no width at all and is dropped."),
    Param("caglioti_w", "Caglioti W", kind="float", default=0.010,
          minimum=0.0, maximum=1.0, decimals=5,
          help="The constant term, which is most of the width at "
               "low angle."),
    Param("b_overall", "Overall B", kind="float", default=0.0,
          minimum=0.0, maximum=20.0, decimals=3, suffix=" A^2",
          help="One thermal displacement parameter for every atom: "
               "exp(-2 B sin^2(theta) / lambda^2).  Left at zero the "
               "high-angle peaks come out systematically too strong "
               "against a published pattern; 1 to 3 A^2 is typical."),
    Param("show_absences", "Mark systematic absences", kind="bool",
          default=False,
          help="Draw a second comb under the pattern, in its own "
               "colour, where this space group forbids a reflection.  "
               "An unexpected peak is either an impurity or the wrong "
               "space group, and which one depends on whether it sits "
               "over a forbidden position.  A structure in P1 has "
               "none, because P1 forbids nothing."),
)


def simulate_pattern(job) -> JobResult:
    """Calculate one pattern, and leave the two files behind.

    A range with nothing in it, a structure with no atoms and an
    unknown peak shape are all *failed runs* rather than crashes --
    the same answer :mod:`xtal.modules.build` gives a string that is
    not a molecule.
    """
    try:
        wavelength = pxrd.wavelength_of(
            job.param("source", "cu-ka1"),
            float(job.param("wavelength", pxrd.DEFAULT_WAVELENGTH)))
        simulation = pxrd.simulate(
            job.structure,
            wavelength=wavelength,
            two_theta_min=float(job.param("two_theta_min", 5.0)),
            two_theta_max=float(job.param("two_theta_max", 50.0)),
            step=float(job.param("step", 0.01)),
            shape=str(job.param("shape", "pseudo-voigt")),
            caglioti=(float(job.param("caglioti_u", 0.004)),
                      float(job.param("caglioti_v", -0.002)),
                      float(job.param("caglioti_w", 0.010))),
            eta=float(job.param("eta", pxrd.DEFAULT_ETA)),
            b_overall=float(job.param("b_overall", 0.0)),
            label=job.structure.meta.get("title", ""),
            with_absences=bool(job.param("show_absences", False)),
            cancel=job.cancel)
    except pxrd.PxrdError as exc:
        return JobResult.failure(str(exc))

    source = pxrd.wavelength_label(
        job.param("source", "cu-ka1"),
        float(job.param("wavelength", pxrd.DEFAULT_WAVELENGTH)))
    job.say(f"{len(simulation.reflections)} reflections, {source}")

    artifacts = _write_files(job, simulation, source)
    strongest = simulation.strongest
    return JobResult(
        message=(f"{len(simulation.reflections)} reflections between "
                 f"{simulation.pattern.range[0]:g} and "
                 f"{simulation.pattern.range[1]:g} deg, strongest "
                 f"{strongest.label} at {strongest.two_theta:.3f} deg"),
        artifacts=tuple(artifacts),
        report=report_for(simulation, source))


# ======================================================================
#  WHAT IT SHOWS
# ======================================================================

def report_for(simulation, source: str) -> Report:
    """The curve, the reflection list, and the caveat under both.

    **Every reflection, and no threshold.**  There was one, defaulting
    to a percent of the strongest, and it was the wrong shape of
    control: a weak reflection is exactly what somebody scanning the
    list is looking for when they are deciding whether a shoulder is a
    second phase.  The table sorts and scrolls; hiding rows to make it
    shorter answers a question nobody asked.
    """
    pattern = simulation.pattern
    ticks = [("allowed", _tick_positions(simulation))]
    if simulation.absent.size:
        ticks.append(("forbidden", simulation.absent))

    # Not the report's own title, which is right above it: the same
    # string twice is what `Report.as_text` prints from the CLI, and
    # this one also names the plot window and the PNG in the run
    # folder, so it says what the trace *is*.
    curve = Curve(
        title=f"Calculated pattern, {source}",
        x=pattern.x, y=pattern.y,
        x_label="2-theta (degrees)",
        y_label="calculated",
        tick_sets=tuple(ticks),
        note="Every reflection in range is a mark under the trace, "
             "including the ones too weak to see -- which is what "
             "says a shoulder on a peak is two reflections.")

    rows = []
    for number, (reflection, percent) in enumerate(
            simulation.scaled_reflections(), start=1):
        rows.append(Row.of(
            number, reflection.label, f"{reflection.d:.4f}",
            f"{reflection.two_theta:.3f}", f"{percent:.2f}",
            note=(f"multiplicity {reflection.multiplicity}, |F|^2 = "
                  f"{reflection.f_squared:.1f}.  {CAVEAT}")))
    table = Table(
        title=f"Reflections ({len(rows)})",
        columns=REFLECTION_COLUMNS,
        rows=tuple(rows),
        note="Symmetry-inequivalent reflections, one per orbit, with "
             "the equivalents counted into the intensity -- which is "
             "the list a reference pattern prints.  I is a percentage "
             "of the strongest reflection in range.")

    return Report(
        title=f"PXRD, {source}",
        blocks=(curve, table),
        note=f"{simulation.formula or 'the structure'}, "
             f"{simulation.space_group}.  {CAVEAT}")


def _tick_positions(simulation):
    """Where the comb under the curve goes.

    Every reflection, not only the listed ones: the comb is what says
    a shoulder on a peak is two reflections, and dropping the weak
    ones is exactly how that stops being visible.
    """
    import numpy as np

    return np.array([r.two_theta for r in simulation.reflections],
                    dtype=float)


def _write_files(job, simulation, source: str) -> list:
    """``pattern.xy`` and ``reflections.txt`` in the run folder.

    Nothing at all with no workspace open, which is not an error
    state: the answer is a picture and a table on screen, and where a
    file gets saved is the user's to choose.  The same argument
    :mod:`xtal.modules.zeopp` makes about a run in a temporary
    directory.
    """
    from xtal.io.xy import write_xy

    if job.folder is None:
        return []
    header = (f"Calculated powder pattern, {source}\n"
              f"{simulation.formula}  {simulation.space_group}\n"
              f"2-theta (degrees), intensity (% of the maximum)")
    pattern_path = write_xy(simulation.pattern.x, simulation.pattern.y,
                            job.file("pattern.xy"), header)
    lines = [f"# {line}" for line in header.splitlines()]
    lines.append("#  No.    h   k   l          d      2-theta"
                 "      I(%)   mult")
    for number, (reflection, percent) in enumerate(
            simulation.scaled_reflections(), start=1):
        h, k, ell = reflection.hkl
        lines.append(f"{number:6d}  {h:5d}{k:4d}{ell:4d}"
                     f"  {reflection.d:9.4f}"
                     f"  {reflection.two_theta:11.4f}"
                     f"  {percent:8.2f}  {reflection.multiplicity:5d}")
    list_path = job.file("reflections.txt")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    job.note(f"wrote {pattern_path.name} and {list_path.name}")
    return [pattern_path, list_path]


# ======================================================================
#  THE ENTRY
# ======================================================================

PXRD = Module(
    name="pxrd",
    label="PXRD",
    description="Calculate a powder X-ray diffraction pattern from "
                "the structure: peak positions from the cell and the "
                "space group, intensities from the atoms through "
                "structure factors.  The pattern is written as .xy "
                "beside the indexed reflection list, and a measured "
                "pattern can be overlaid on it.",
    order=50,
    actions=(
        Action(name="simulate", label="Simulate a pattern...",
               tip="Calculate a powder diffraction pattern from this "
                   "structure",
               kind="pxrd",
               params=PARAMS,
               run=simulate_pattern),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(PXRD)
