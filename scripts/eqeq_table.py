"""Write EQeq's ionisation table from the two sources it is read off.

    python scripts/eqeq_table.py            # rewrite the table
    python scripts/eqeq_table.py --check    # exit 1 if it would change
    python scripts/eqeq_table.py --fetch    # download both again first

EQeq needs, for every element, the energy to take each successive
electron off and the energy an extra one gives back.  The published
implementations carry a table of those under GPL-2.0, and that table
is not what this application ships: ours is written by this script
from the sources themselves, so what each number is and where it came
from can be checked rather than trusted.

* **Ionisation energies**: the NIST Atomic Spectra Database's
  ionisation-energy export (Kramida, Ralchenko, Reader and NIST ASD
  Team), H to Pu, in eV.  A value NIST brackets as theoretical or
  interpolated is taken as it stands -- there is nothing better, and
  none of the elements a framework is made of needs one below the
  charge centres EQeq uses.
* **Electron affinities**: PubChem's periodic table (NCBI), in eV.  A
  blank there is an element whose anion is not bound -- N, the noble
  gases, Be, Mg, Zn, Mn, Cd -- and it is written blank here too;
  what a blank *means* is :mod:`xtal.ff.charges.eqeq`'s decision.

Both downloads are kept in ``tests/data/eqeq/`` exactly as they
arrived (the NIST one gzipped), so the suite can run this against them
and fail if the shipped table is not what they say.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tests" / "data" / "eqeq"
NIST = SOURCES / "nist_asd_ionization.csv.gz"
PUBCHEM = SOURCES / "pubchem_periodic_table.csv"
TABLE = ROOT / "xtal" / "ff" / "charges" / "data" / "ionization.csv"

NIST_URL = (
    "https://physics.nist.gov/cgi-bin/ASD/ie.pl?spectra=H-Pu&units=1"
    "&format=2&order=0&at_num_out=on&sp_name_out=on&ion_charge_out=on"
    "&el_name_out=on&unc_out=on&e_out=0&biblio=on"
    "&submit=Retrieve+Data")
PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/periodictable/CSV"

#: Ionisation energies kept per element.  EQeq's charge centres go no
#: higher than +4, which needs the fifth; eight is what the method's
#: authors tabulated, and room for a centre somebody adds.
N_IONISATIONS = 8

HEADER = """\
# EQeq ionisation table -- written by scripts/eqeq_table.py; do not edit.
# Ionisation energies: NIST Atomic Spectra Database, ionisation-energy
#   export (Kramida, Ralchenko, Reader and NIST ASD Team), eV.
# Electron affinities: PubChem periodic table (NCBI), eV; blank where
#   the anion is not bound.
# IEn is the energy to go from charge n-1 to charge n.
"""


def fetch() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(NIST_URL, timeout=120) as response:
        NIST.write_bytes(gzip.compress(response.read(), mtime=0))
    with urllib.request.urlopen(PUBCHEM_URL, timeout=120) as response:
        PUBCHEM.write_bytes(response.read())


def _cell(text: str) -> str:
    """NIST writes every field as ``="value"`` so a spreadsheet keeps
    it as text; the value is what is inside."""
    text = text.strip()
    if text.startswith("="):
        text = text[1:]
    return text.strip('"')


def ionisation_energies(raw: str) -> dict[int, dict[int, str]]:
    """``{Z: {charge after: eV as NIST wrote it}}``."""
    rows = csv.reader(io.StringIO(raw))
    header = [_cell(h) for h in next(rows)]
    z_col = header.index("At. num")
    charge_col = header.index("Ion Charge")
    energy_col = header.index("Ionization Energy (eV)")
    table: dict[int, dict[int, str]] = {}
    for row in rows:
        if len(row) <= energy_col:
            continue
        z = int(_cell(row[z_col]))
        charge = int(_cell(row[charge_col]))
        energy = _cell(row[energy_col])
        if energy and charge < N_IONISATIONS:
            table.setdefault(z, {})[charge + 1] = energy
    return table


def electron_affinities(raw: str) -> dict[int, tuple[str, str]]:
    """``{Z: (symbol, eV or "")}``."""
    return {int(row["AtomicNumber"]):
            (row["Symbol"], row["ElectronAffinity"].strip())
            for row in csv.DictReader(io.StringIO(raw))}


def table(nist_raw: str, pubchem_raw: str) -> str:
    energies = ionisation_energies(nist_raw)
    affinities = electron_affinities(pubchem_raw)
    out = io.StringIO()
    out.write(HEADER)
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Z", "symbol", "EA"]
                    + [f"IE{n}" for n in range(1, N_IONISATIONS + 1)])
    for z in sorted(energies):
        symbol, affinity = affinities[z]
        writer.writerow(
            [z, symbol, affinity]
            + [energies[z].get(n, "")
               for n in range(1, N_IONISATIONS + 1)])
    return out.getvalue()


def written() -> str:
    """The table the two kept downloads say, as this script writes
    it."""
    nist = gzip.decompress(NIST.read_bytes()).decode("utf-8")
    return table(nist, PUBCHEM.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--fetch", action="store_true",
                        help="download both sources again first")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the table would change")
    args = parser.parse_args(argv)
    if args.fetch:
        fetch()
    text = written()
    if args.check:
        same = TABLE.exists() and TABLE.read_text(encoding="utf-8") == text
        print("unchanged" if same else f"{TABLE} is out of date")
        return 0 if same else 1
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_text(text, encoding="utf-8")
    print(f"wrote {TABLE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
