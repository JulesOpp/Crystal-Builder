"""
xtal.references
===============
Where a method, a program or a database comes from, as a link.

The Force Field panel names the papers behind the method it is set
up with, the MOF and net builders the databases their nets and blocks
come from, and Preferences > Engines where each program lives.  One
small type for all of them, and the citations more than one of them
give written once here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reference:
    """The paper that defines something, or the code that is it, as a
    link somebody can follow.

    ``label`` names it the way a citation would at a glance -- authors,
    journal, year -- so the link says what it opens before it is
    clicked.
    """

    label: str                      # "Rappe et al., J. Am. Chem. Soc. 1992"
    url: str


def doi(label: str, identifier: str) -> Reference:
    return Reference(label, f"https://doi.org/{identifier}")


def arxiv(label: str, identifier: str) -> Reference:
    return Reference(label, f"https://arxiv.org/abs/{identifier}")


def github(repository: str) -> Reference:
    return Reference(f"{repository} on GitHub",
                     f"https://github.com/{repository}")


RCSR = (doi("RCSR: O'Keeffe et al., Acc. Chem. Res. 2008",
            "10.1021/ar800124u"),
        Reference("rcsr.net", "http://rcsr.net"))

PORMAKE = (doi("PORMAKE: Lee et al., ACS Appl. Mater. Interfaces 2021",
               "10.1021/acsami.1c02471"),
           github("Sangwon91/PORMAKE"))

#: The pacs papers: the symmetry-matching insertion the builder's
#: closed form follows, and the account of the family.
PACS = (doi("Pore-space partition: Zhao et al., J. Am. Chem. Soc. 2015",
            "10.1021/ja512137t"),
        doi("Pore-space partition: Zhai et al., Acc. Chem. Res. 2017",
            "10.1021/acs.accounts.6b00526"))

#: Supertetrahedra of M3O trimers on a zeolite net, their windows
#: bridged by an N-donor: the centring structure-directing agents.
SUPERTETRAHEDRA = (doi("Centring structure-directing agents: Barsukova "
                       "et al., Nat. Synth. 2024",
                       "10.1038/s44160-023-00401-8"),)

#: Merged nets: sph from spn and hxg, and the enumeration the explorer
#: lists.
MERGED_NETS = (doi("Merged nets: Jiang et al., J. Am. Chem. Soc. 2018",
                   "10.1021/jacs.8b04745"),
               doi("Merged-nets enumeration: Jiang et al., Science 2024",
                   "10.1126/science.ads7866"))

#: How a rod MOF's net is read off its points of extension.
RODS = (doi("Rod MOFs: Schoedel et al., Chem. Rev. 2016",
            "10.1021/acs.chemrev.6b00346"),)

TOPCRYST = (doi("TopCryst: Shevchenko et al., Sci. Technol. Adv. Mater. "
                "Methods 2022", "10.1080/27660400.2022.2088041"),
            Reference("topcryst.com", "https://topcryst.com/"))

#: What ORCA's own manual (6.1, "How to cite") asks for: the generic
#: reference and the update for the version an input is written for.
ORCA = (doi("ORCA: Neese, WIREs Comput. Mol. Sci. 2012",
            "10.1002/wcms.81"),
        doi("ORCA 6: Neese, WIREs Comput. Mol. Sci. 2025",
            "10.1002/wcms.70019"),
        Reference("ORCA at FACCTs", "https://www.faccts.de/orca/"))

NANOTUBE = (
    doi("Dresselhaus, Dresselhaus and Saito, Carbon 1995",
        "10.1016/0008-6223(95)00017-8"),
    doi("Hamada, Sawada and Oshiyama, Phys. Rev. Lett. 1992",
        "10.1103/PhysRevLett.68.1579"),
    doi("Saito et al., Appl. Phys. Lett. 1992", "10.1063/1.107080"),
    doi("Kane and Mele, Phys. Rev. Lett. 1997",
        "10.1103/PhysRevLett.78.1932"),
    doi("Blase et al., Phys. Rev. Lett. 1994",
        "10.1103/PhysRevLett.72.1878"),
    doi("Rubio, Corkill and Cohen, Phys. Rev. B 1994",
        "10.1103/PhysRevB.49.5081"),
    doi("Paszkowicz et al., Appl. Phys. A 2002",
        "10.1007/s003390100999"),
    doi("Pyykkö and Atsumi, Chem. Eur. J. 2009 (single-bond radii)",
        "10.1002/chem.200800987"),
    doi("Pyykkö and Atsumi, Chem. Eur. J. 2009 (double-bond radii)",
        "10.1002/chem.200901472"),
)


def rcsr_net(name: str, dimension: int = 3) -> Reference:
    """RCSR's own page for one net -- the address each page gives as
    its "RCSR reference".  http, because rcsr.net does not answer on
    https."""
    kind = "layers" if dimension == 2 else "nets"
    return Reference(f"{name} in the RCSR",
                     f"http://rcsr.net/{kind}/{name}")
