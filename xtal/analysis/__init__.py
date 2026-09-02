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

**Topology is the other half of it and answers a different kind of
question.**  :mod:`~xtal.analysis.topology` is a net as a periodic
graph and its invariants; :mod:`~xtal.analysis.rcsr` is the catalogue
those invariants are looked up in, and the answer it returns is a
*name* -- **pcu** -- rather than a number.  The same split as above
holds: nothing in either launches anything, and the RCSR index they
read is package data.

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
from xtal.analysis.rcsr import (
    Catalogue,
    CatalogueEntry,
    Identification,
    NetReport,
    RcsrError,
    catalogue,
    describe,
    identify,
    placement,
)
from xtal.analysis.topology import (
    Edge,
    Fingerprint,
    Net,
    TopologyError,
    net_of,
)

__all__ = ["Catalogue", "CatalogueEntry", "Diameters", "Edge",
           "Fingerprint", "Identification", "Net", "NetReport",
           "PoreSizeDistribution", "RcsrError", "SurfaceArea",
           "TopologyError", "Volume", "ZeoOutputError", "catalogue",
           "describe",
           "identify", "net_of", "parse_psd", "parse_res",
           "parse_summary", "placement", "probe_label",
           "probe_radius", "refuse"]
