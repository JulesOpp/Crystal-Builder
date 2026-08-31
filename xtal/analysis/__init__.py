"""
xtal.analysis
=============
Numbers about a structure that are not its energy.

The line between this package and :mod:`xtal.ff` is what the answer
*is*: a force field returns an energy and forces, and everything here
returns a measurement -- a pore diameter, a surface area, a
distribution.  The line between it and :mod:`xtal.modules` is that
nothing here launches anything: :mod:`~xtal.analysis.porosity` holds
the records and the parsers for what Zeo++ writes, and
:mod:`xtal.modules.zeopp` is what runs it.  That split is what lets
the parsers be tested on a machine with no ``network`` installed.

RDF, coordination statistics and PXRD are named in
[docs/PLAN.md](../../docs/PLAN.md) as the rest of this package and are
not here yet.
"""

from xtal.analysis.porosity import (
    Diameters,
    PoreSizeDistribution,
    SurfaceArea,
    Volume,
    ZeoOutputError,
    parse_psd,
    parse_res,
    parse_summary,
    probe_label,
    probe_radius,
    refuse,
)

__all__ = ["Diameters", "PoreSizeDistribution", "SurfaceArea",
           "Volume", "ZeoOutputError", "parse_psd", "parse_res",
           "parse_summary", "probe_label", "probe_radius", "refuse"]
