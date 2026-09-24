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


def rcsr_net(name: str, dimension: int = 3) -> Reference:
    """RCSR's own page for one net -- the address each page gives as
    its "RCSR reference".  http, because rcsr.net does not answer on
    https."""
    kind = "layers" if dimension == 2 else "nets"
    return Reference(f"{name} in the RCSR",
                     f"http://rcsr.net/{kind}/{name}")
