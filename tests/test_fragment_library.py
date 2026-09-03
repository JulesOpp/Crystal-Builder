"""The shipped fragment library.

Text, and deliberately so: the picker fills whether or not RDKit is
installed, because a library that could not be *looked at* without a
400 MB dependency is one people find out about after installing it.
The half that needs RDKit is the one test that builds every entry.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from xtal.build import MISSING, installed, library

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)


def test_the_library_is_there_and_has_things_in_it():
    entries = library.entries()
    assert len(entries) > 20
    assert all(entry.name and entry.smiles for entry in entries)


def test_listing_the_library_does_not_need_rdkit():
    """In a subprocess, because the claim is about a fresh
    interpreter: any earlier test that built a molecule has RDKit in
    ``sys.modules`` already."""
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; from xtal.build import library; "
         "print(len(library.entries()), 'rdkit' in sys.modules)"],
        capture_output=True, text=True, check=True)
    count, imported = out.stdout.split()

    assert int(count) > 20
    assert imported == "False"


def test_the_entries_are_grouped_and_the_groups_are_in_file_order():
    """Solvents before linkers, because that is the order somebody
    looks for them in.  Sorting would throw that away."""
    assert library.categories()[0] == "Solvent"
    assert "Linker" in library.categories()


def test_a_fragment_is_found_by_name_however_it_is_typed():
    assert library.find("DMF").smiles == "CN(C)C=O"
    assert library.find("dmf") is library.find("DMF")
    assert library.find("nothing called this") is None


def test_connection_points_are_counted_from_the_string():
    """``*`` in SMILES is a dummy atom and is nothing else, which is
    what lets this be answered without RDKit."""
    assert library.find("Water").n_connections == 0
    assert not library.find("Water").is_block
    assert library.find("Phenylene").n_connections == 2
    assert library.find("Benzene tritopic").n_connections == 3
    assert library.find("Tetraphenylmethane").n_connections == 4


def test_the_box_that_pastes_is_offered_no_connection_points():
    """It refuses a starred string, so offering it a linker would be
    offering an entry that answers with a refusal."""
    plain = library.matching(connection_points=False)

    assert plain and len(plain) < len(library.entries())
    assert all(not entry.is_block for entry in plain)
    assert library.find("Water") in plain
    assert library.find("Phenylene") not in plain


def test_every_name_is_used_once():
    names = [entry.name.lower() for entry in library.entries()]
    assert len(set(names)) == len(names)


@needs_rdkit
def test_every_fragment_in_the_library_actually_builds():
    """The one test that would catch a typo in the data file.

    A SMILES string nobody has built is a string nobody knows is a
    molecule, and the failure a user would see is the picker offering
    something that refuses when it is chosen.
    """
    from xtal.build import from_smiles

    for entry in library.entries():
        molecule = from_smiles(entry.smiles, name=entry.name,
                               optimise=False)
        assert molecule.n_atoms > 0
        assert molecule.n_connections == entry.n_connections
