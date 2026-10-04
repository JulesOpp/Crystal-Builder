"""A drawn metal is built with its shape (``xtal.build.coordination``
and the metal path of ``xtal.build.chem.embed``).

ETKDG alone gave cisplatin Cl-Pt-Cl angles of 97-120 degrees and
Fe(OH)6 angles from 65 to 151, and said nothing.  Each case here is one
the plan named; a regression is a complex that builds wrong or refuses.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from xtal.build import MISSING, chem, coordination, installed

pytestmark = pytest.mark.skipif(not installed(), reason=MISSING)

PADDLEWHEEL = (
    "CC1[O][Cu]234[O]C(C)=[O]->[Cu]2([O]C(C)=[O]->3)([O]C(C)=[O]-"
    ">4)<-[O]=1")
ZN4O = (
    "CC1[O][Zn]23[O]C(C)=[O]->[Zn]45[O]C(C)=[O]->[Zn]6(<-[O]=C(C)"
    "[O]2)<-[O]=C(C)[O][Zn]([O]C(C)=[O]->4)(<-[O]=1)[O]->5->63")

COMPLEXES = {
    "cisplatin": ("Cl[Pt](Cl)(<-[NH3])<-[NH3]", ["square_planar"]),
    "Fe(OH)6": ("O[Fe](O)(O)(O)(O)O", ["octahedral"]),
    "Co(en)3": ("N1CCN->[Co]123(<-NCCN->2)<-NCCN->3", ["octahedral"]),
    "Cu(en)2": ("N1CCN->[Cu]12<-NCCN->2", ["square_planar"]),
    "Ru(bpy)3": ("c1ccc2n(c1)->[Ru]34(<-n5ccccc5-2)(<-n2ccccc2-c2cccc"
                 "[n]->32)<-n2ccccc2-c2cccc[n]->42", ["octahedral"]),
    "ZnCl4": ("Cl[Zn](Cl)(Cl)Cl", ["tetrahedral"]),
    "Ni(CN)4": ("N#C[Ni](C#N)(C#N)C#N", ["square_planar"]),
    "Ag(NH3)2": ("[NH3]->[Ag]<-[NH3]", ["linear"]),
    "Fe(CO)5": ("[O+]#[C-][Fe]([C-]#[O+])([C-]#[O+])([C-]#[O+])"
                "[C-]#[O+]", ["trigonal_bipyramidal"]),
    "Cu(acac)2": ("CC1=CC(C)=O->[Cu]2(O1)OC(C)=CC(C)=O->2",
                  ["square_planar"]),
    "Cu2(OAc)4": (PADDLEWHEEL, ["square_pyramidal"] * 2),
    "Zn4O(OAc)6": (ZN4O, ["tetrahedral"] * 4),
}


def _centres(smiles):
    from rdkit import Chem

    return chem._metal_centres(Chem, Chem.AddHs(Chem.MolFromSmiles(smiles)))


@pytest.mark.parametrize("name", sorted(COMPLEXES))
def test_every_complex_embeds_on_its_shape(name):
    """Within five degrees of the ideal angles -- fifteen for a metal
    bonded to another, whose own direction is left free."""
    smiles, shapes = COMPLEXES[name]
    _symbols, cart, _bonds, _points = chem.embed(smiles)
    centres = _centres(smiles)
    assert [c[2] for c in centres] == shapes
    assert chem._shape_error(cart, centres) <= 0.0


def test_an_organic_molecule_never_reaches_the_metal_path(monkeypatch):
    """The organic path is the one every MOF linker takes; it embeds
    exactly as it did before metals were drawn (measured: bit for bit
    on four molecules), which is held by never going near the new
    code."""
    def refuse(*_args, **_kwargs):
        raise AssertionError("an organic molecule took the metal path")

    monkeypatch.setattr(chem, "_metal_coordinates", refuse)
    chem.embed("OC(=O)c1ccccc1")
    chem.embed("[*:1]c1ccc([*:2])cc1")


def test_an_override_beats_the_default_shape():
    """Platinum with four neighbours is square planar unless somebody
    right-clicked it and said tetrahedral."""
    smiles = "Cl[Pt](Cl)(<-[NH3])<-[NH3] |atomProp:1.xtal_shape.tetrahedral|"
    _symbols, cart, _bonds, _points = chem.embed(smiles)
    centres = _centres(smiles)
    assert centres[0][2] == "tetrahedral"
    metal, donors = centres[0][0], centres[0][1]
    for a, b in itertools.combinations(donors, 2):
        u, v = cart[a] - cart[metal], cart[b] - cart[metal]
        angle = math.degrees(math.acos(
            u @ v / np.linalg.norm(u) / np.linalg.norm(v)))
        assert angle == pytest.approx(109.47, abs=5.0)


def test_the_relax_leaves_the_metal_and_its_donors_where_they_were():
    """UFF4MOF relaxes the ligands; the shape is held, so the Pt-Cl
    bond is the length it was put at."""
    symbols, cart, _bonds, _points = chem.embed("Cl[Pt](Cl)(<-[NH3])<-[NH3]")
    pt = symbols.index("Pt")
    cl = symbols.index("Cl")
    assert np.linalg.norm(cart[cl] - cart[pt]) == pytest.approx(
        coordination.bond_length("Pt", "Cl"), abs=0.03)


def test_a_sandwich_is_refused_with_a_reason():
    with pytest.raises(chem.BuildError, match="sandwich"):
        chem.embed("[CH]12[CH]3[CH]4[CH]5[CH]1[Fe]23456789[CH]%10[CH]6"
                   "[CH]7[CH]8[CH]9%10")


def test_a_shape_with_the_wrong_number_of_corners_is_refused():
    with pytest.raises(chem.BuildError, match="corners"):
        chem.embed("Cl[Zn](Cl)(Cl)Cl |atomProp:1.xtal_shape.octahedral|")


# --------------------------------------------- the shapes on their own

def test_four_neighbours_are_square_planar_only_for_the_d8_metals():
    assert coordination.default_shape("Pt", 4) == "square_planar"
    assert coordination.default_shape("Zn", 4) == "tetrahedral"
    assert coordination.default_shape("Cu", 5, 1) == "square_pyramidal"
    assert coordination.default_shape("Fe", 5) == "trigonal_bipyramidal"
    assert coordination.default_shape("Fe", 10) is None


def test_the_square_planar_metals_are_the_ones_uff_types_so():
    """The four d8 metals UFF gives no tetrahedral type at all."""
    from xtal.ff.uff.params import types_for

    for metal in ("Ni", "Pd", "Pt", "Au"):
        rappe = [t for t in types_for(metal) if "f" not in t[3:]]
        assert all(t[2] == "4" for t in rappe), metal
        assert metal in coordination.SQUARE_PLANAR


def test_a_chelate_takes_neighbouring_corners():
    """en across a trans pair of an octahedron is a ring that cannot
    close; the assignment puts each chelate's donors cis."""
    vertex_of = coordination.assign("octahedral", [(0, 1), (2, 3),
                                                   (4, 5)])
    vectors = coordination.SHAPES["octahedral"][1]
    for a, b in [(0, 1), (2, 3), (4, 5)]:
        assert vectors[vertex_of[a]] @ vectors[vertex_of[b]] == \
            pytest.approx(0.0, abs=1e-9)


def test_every_shape_has_unit_corners_and_a_menu_name():
    for name, (label, vectors) in coordination.SHAPES.items():
        assert label
        assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0), name
    assert coordination.shapes_for(4) == ["tetrahedral", "square_planar"]
