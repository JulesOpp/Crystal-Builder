"""What the ORCA input dialog offers, held to ORCA's manual."""

from __future__ import annotations

import importlib.util
import shutil
from collections import Counter
from pathlib import Path

import pytest

from xtal.orca import catalogue

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "JulesWork" / "orca_manual_6_1_0.pdf"


def test_the_defaults_are_in_the_catalogue():
    """The dialog opens on these; without them it opens on nothing."""
    assert catalogue.functional(catalogue.DEFAULT_FUNCTIONAL).family \
        == catalogue.GGA
    assert catalogue.basis(catalogue.DEFAULT_BASIS).family \
        == "Karlsruhe def2"


def test_every_keyword_appears_once_per_catalogue():
    """Two rows writing one keyword is a picker offering one thing
    twice, under two families -- and a lookup that finds the first."""
    for entries in (catalogue.all_functionals(), catalogue.all_bases()):
        keys = Counter(e.key.lower() for e in entries)
        assert [k for k, n in keys.items() if n > 1] == []


def test_def2_svp_covers_hydrogen_to_radon():
    """The element range, read from the manual's "H–Rn"."""
    covers = catalogue.basis("def2-SVP").covers
    assert len(covers) == 86
    assert {"H", "Zn", "Rn"} <= covers and "Fr" not in covers


def test_a_wrapped_element_list_is_read_whole():
    """LANL2DZ's elements wrap three lines in the manual, one range cut
    in half ("U–" over "Pu"); read a line at a time it was
    H, Li–La and Pu."""
    covers = catalogue.basis("LANL2DZ").covers
    assert {"H", "Li", "La", "Hf", "Bi", "U", "Np", "Pu"} <= covers
    assert "Ce" not in covers


def test_a_basis_is_found_whatever_its_case():
    assert catalogue.basis("DEF2-tzvp").key == "def2-TZVP"
    assert catalogue.functional("b3lyp").key == "B3LYP"


def test_searching_finds_by_key_or_by_label():
    found = {f.key for f in catalogue.find(catalogue.all_functionals(),
                                           "lyp")}
    assert {"BLYP", "B3LYP", "CAM-B3LYP", "B2PLYP"} <= found
    by_label = catalogue.find(catalogue.all_functionals(), "gaussian")
    assert [f.key for f in by_label] == ["B3LYP/G"]


def test_dispersion_in_the_name_is_known():
    """Adding D3BJ to wB97X-D3BJ counts dispersion twice."""
    for key in ("WB97X-D3BJ", "B97M-V", "R2SCAN-3C",
                "REVDSD-PBEP86-D4/2021"):
        assert catalogue.functional(key).carries_dispersion, key
    for key in ("BP86", "B3LYP", "WB97X", "DSD-BLYP"):
        assert not catalogue.functional(key).carries_dispersion, key


def test_only_the_composites_bring_their_own_basis():
    owners = {f.key for f in catalogue.all_functionals() if f.own_basis}
    assert owners == {"B97-3C", "R2SCAN-3C", "PBEH-3C", "B3LYP-3C",
                      "WB97X-3C"}


def test_a_solvent_is_found_by_any_of_its_names():
    """ORCA takes "dmf" for N,N-dimethylformamide, so the box does."""
    assert catalogue.solvent("DMF").name == "n,n-dimethylformamide"
    assert catalogue.solvent("water").smd
    assert catalogue.solvent("ammonia").cpcm
    assert not catalogue.solvent("ammonia").smd


def _orca_tables():
    spec = importlib.util.spec_from_file_location(
        "orca_tables", ROOT / "scripts" / "orca_tables.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not MANUAL.exists() or shutil.which("gs") is None,
                    reason="needs the ORCA 6.1 manual and Ghostscript")
def test_the_shipped_tables_are_what_the_manual_says():
    """The basis sets and solvents are written by a script from the
    manual, and this is the script run again: a hand edit to the JSON,
    or a parser change that was never re-run, fails here."""
    tables = _orca_tables()
    manual = tables.manual_text(MANUAL)
    expected = tables.render(tables.read_tables(manual),
                             tables.read_solvents(manual))
    assert tables.OUT.read_text(encoding="utf-8") == expected


@pytest.mark.skipif(not MANUAL.exists() or shutil.which("gs") is None,
                    reason="needs the ORCA 6.1 manual and Ghostscript")
def test_every_functional_is_in_its_table():
    """The functionals are written by hand; each keyword must be in
    the manual's text of the table it cites."""
    tables = _orca_tables()
    text = tables.manual_text(MANUAL, pages=((230, 247),))
    squeezed = text.replace(" ", "").upper()

    def found(key):
        # "DSD-BLYP/2013" is printed "DSD-BLYP/" over "2013".
        stem, _, year = key.upper().partition("/")
        return (stem + _ if year else stem) in squeezed and \
            year in squeezed

    assert [f.key for f in catalogue.all_functionals()
            if not found(f.key)] == []
