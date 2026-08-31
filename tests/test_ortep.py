"""Thermal ellipsoids: the picture a crystallographer expects from a
refined structure, and the one that makes a bad refinement obvious.

The tests run from the CIF inwards, because every step between is a
place the answer can be right-looking and wrong: the aniso loop has to
be read and written back, the U values have to be converted out of the
reciprocal basis they are defined in, the probability level has to be
the chi-squared one and not a plain multiple of the RMS displacement,
and the ellipsoid has to be turned by the symmetry operation that
placed the atom it belongs to.

The three fallbacks are tested as hard as the measurement is.  An
ellipsoid picture whose atoms are half of them guesses looks exactly
like one whose atoms were all measured.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core.site import Site
from xtal.core.transforms import (
    ellipsoid_transform,
    is_non_positive_definite,
    probability_scale,
)
from xtal.io import cif_string, read_cif_string
from xtalapp.viewport import scene as scene_module
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.view_settings import ViewSettings

ANISO = (0.020, 0.024, 0.075, 0.003, 0.0, 0.0)


def a_refined_ring(box=12.0, group="P1") -> Structure:
    """Three atoms: one refined anisotropically, one isotropically,
    one not at all -- which is what a real CIF looks like."""
    return Structure(
        lattice=Lattice.cubic(box),
        sites=[Site("C", [0.30, 0.30, 0.30], u_aniso=ANISO),
               Site("N", [0.50, 0.50, 0.50], u_iso=0.035),
               Site("O", [0.70, 0.20, 0.40])],
        space_group=group)


def ortep_settings(probability=0.5) -> ViewSettings:
    settings = ViewSettings(style="ortep", show_cell=False)
    settings.ellipsoid_probability = probability
    return settings


# ================================================== the numbers matter

def test_the_probability_levels_are_the_published_ones():
    """1.5382 and 2.5003 are in every ORTEP manual.  An ellipsoid drawn
    at one RMS displacement encloses 20% of the density and looks far
    too small for a refinement that is perfectly fine."""
    assert probability_scale(0.50) == pytest.approx(1.5382, abs=1e-4)
    assert probability_scale(0.90) == pytest.approx(2.5003, abs=1e-4)
    assert probability_scale(0.99) == pytest.approx(3.3682, abs=1e-4)


def test_a_probability_outside_zero_to_one_is_refused():
    for bad in (0.0, 1.0, -0.5, 2.0):
        with pytest.raises(ValueError):
            probability_scale(bad)


def test_the_semi_axes_are_the_scaled_rms_displacements():
    u = np.diag([0.01, 0.04, 0.09])
    axes = np.linalg.svd(ellipsoid_transform(u, 0.5))[1]
    expected = probability_scale(0.5) * np.array([0.3, 0.2, 0.1])
    assert np.allclose(sorted(axes), sorted(expected))


def test_raising_the_probability_grows_every_ellipsoid():
    u = np.diag([0.01, 0.04, 0.09])
    small = np.linalg.svd(ellipsoid_transform(u, 0.5))[1]
    large = np.linalg.svd(ellipsoid_transform(u, 0.9))[1]
    assert np.all(large > small)


def test_an_orthogonal_cell_leaves_the_u_values_alone():
    """Which is why the conversion below is easy to get wrong and hard
    to notice: in an orthorhombic cell the CIF's U *is* the cartesian
    tensor, and the bug only shows up in a monoclinic one."""
    site = Site("C", [0, 0, 0], u_aniso=ANISO)
    u = site.u_cartesian(Lattice.from_parameters(5, 6, 7, 90, 90, 90))
    assert np.allclose(np.diag(u), ANISO[:3])
    assert u[0, 1] == pytest.approx(ANISO[3])


def test_a_skewed_cell_shears_the_tensor():
    """The U^ij are defined against the reciprocal basis.  Drawing them
    straight gives an ellipsoid that leans the wrong way."""
    site = Site("C", [0, 0, 0], u_aniso=ANISO)
    skewed = site.u_cartesian(
        Lattice.from_parameters(5, 6, 7, 90, 100, 90))
    assert not np.allclose(np.diag(skewed), ANISO[:3])
    assert np.allclose(skewed, skewed.T)        # still a tensor


def test_a_site_with_no_aniso_has_no_tensor():
    assert Site("C", [0, 0, 0]).u_cartesian(Lattice.cubic(5.0)) is None
    assert Site("C", [0, 0, 0], u_iso=0.02).u_cartesian(
        Lattice.cubic(5.0)) is None


def test_u_equivalent_is_a_third_of_the_trace():
    assert Site("C", [0, 0, 0], u_aniso=ANISO).u_equivalent == \
        pytest.approx(sum(ANISO[:3]) / 3.0)
    assert Site("C", [0, 0, 0], u_iso=0.02).u_equivalent == 0.02
    assert Site("C", [0, 0, 0]).u_equivalent is None


def test_six_values_or_none():
    with pytest.raises(ValueError):
        Site("C", [0, 0, 0], u_aniso=(0.01, 0.02, 0.03))


def test_a_refinement_that_went_wrong_is_recognised():
    """An NPD atom is the single most useful thing an ellipsoid picture
    can tell you, and it must not be quietly rounded up to something
    drawable."""
    assert is_non_positive_definite(np.diag([0.01, -0.001, 0.02]))
    assert not is_non_positive_definite(np.diag([0.01, 0.001, 0.02]))


def test_a_non_positive_tensor_still_draws_something_finite():
    matrix = ellipsoid_transform(np.diag([0.01, -0.004, 0.02]), 0.5)
    assert np.all(np.isfinite(matrix))
    assert np.all(np.linalg.svd(matrix)[1] > 0)


# ======================================================= the CIF loops

def test_the_aniso_loop_round_trips():
    text = cif_string(a_refined_ring())
    assert "_atom_site_aniso_U_11" in text
    back = read_cif_string(text)
    assert back.sites[0].u_aniso == pytest.approx(ANISO)


def test_the_aniso_loop_is_sparse():
    """A real CIF gives the hydrogens no aniso row.  Padding the loop
    with zeros would claim six measurements nobody made."""
    text = cif_string(a_refined_ring())
    rows = [line for line in text.splitlines()
            if line.startswith(("C1", "N1", "O1"))]
    aniso = text[text.index("_atom_site_aniso_label"):]
    assert len(rows) >= 3                       # all three atom sites
    assert "C1" in aniso
    assert "N1" not in aniso and "O1" not in aniso


def test_a_file_with_no_aniso_loop_gives_none_and_not_zero():
    """Zero displacement is not a measurement; it is the absence of
    one, and gemmi hands both back as six zeros."""
    plain = Structure(lattice=Lattice.cubic(5.0),
                      sites=[Site("C", [0, 0, 0], u_iso=0.02)],
                      space_group="P1")
    back = read_cif_string(cif_string(plain))
    assert back.sites[0].u_aniso is None
    assert back.sites[0].u_iso == pytest.approx(0.02)


def test_the_project_file_keeps_the_tensor(tmp_path):
    from xtal.io import read_project_structure, write_project
    path = write_project(a_refined_ring(), tmp_path / "p.xtal")
    back = read_project_structure(path)
    assert back.sites[0].u_aniso == pytest.approx(ANISO)


# ======================================================== the picture

def test_the_ortep_style_puts_a_tensor_on_every_drawn_atom():
    model = build_scene(a_refined_ring(), ortep_settings())
    assert model.draws_ellipsoids
    assert model.atom_tensors.shape == (model.n_atoms, 3, 3)
    assert len(model.atom_thermal) == model.n_atoms


def test_other_styles_draw_spheres_and_carry_no_tensors():
    model = build_scene(a_refined_ring(), ViewSettings())
    assert not model.draws_ellipsoids
    assert len(model.atom_tensors) == 0


def test_each_fallback_is_marked_for_what_it_is():
    model = build_scene(a_refined_ring(), ortep_settings())
    kinds = {}
    for index in range(model.n_atoms):
        kinds[int(model.atom_index[index])] = int(
            model.atom_thermal[index])
    assert set(kinds.values()) == {scene_module.ANISOTROPIC,
                                   scene_module.ISOTROPIC,
                                   scene_module.UNMEASURED}
    report = model.thermal_report()
    assert "anisotropic" in report and "no displacement" in report


def test_an_isotropic_atom_is_drawn_as_a_sphere():
    """Because that is what an isotropic refinement *is*, and a sphere
    among ellipsoids says so without a caption."""
    model = build_scene(a_refined_ring(), ortep_settings())
    index = int(np.flatnonzero(
        model.atom_thermal == scene_module.ISOTROPIC)[0])
    axes = np.linalg.svd(model.atom_tensors[index])[1]
    assert np.allclose(axes, axes[0])


def test_an_unmeasured_atom_does_not_grow_with_the_probability():
    """Everything measured swells when the level is raised and it
    stands still, which is the tell that it was never measured."""
    kind = scene_module.UNMEASURED
    at_50 = build_scene(a_refined_ring(), ortep_settings(0.5))
    at_90 = build_scene(a_refined_ring(), ortep_settings(0.9))
    small = int(np.flatnonzero(at_50.atom_thermal == kind)[0])
    large = int(np.flatnonzero(at_90.atom_thermal == kind)[0])
    assert np.allclose(at_50.atom_tensors[small],
                       at_90.atom_tensors[large])

    measured = int(np.flatnonzero(
        at_50.atom_thermal == scene_module.ANISOTROPIC)[0])
    grown = int(np.flatnonzero(
        at_90.atom_thermal == scene_module.ANISOTROPIC)[0])
    assert (np.linalg.svd(at_90.atom_tensors[grown])[1]
            > np.linalg.svd(at_50.atom_tensors[measured])[1]).all()


def test_symmetry_turns_the_ellipsoid_with_the_atom():
    """A symmetry image is the same ellipsoid turned by the operation
    that placed it.  Drawing every image with the parent's tensor
    unturned is visibly wrong in anything below cubic -- and invisible
    in P1, which is where it would be tested by accident."""
    structure = Structure(
        lattice=Lattice.from_parameters(6.0, 6.0, 9.0, 90, 90, 90),
        sites=[Site("C", [0.20, 0.31, 0.11], u_aniso=ANISO)],
        space_group="P4")
    model = build_scene(structure, ortep_settings())
    assert model.n_atoms >= 4
    tensors = [model.atom_tensors[k] for k in range(model.n_atoms)]
    assert not all(np.allclose(tensors[0], t) for t in tensors)
    # every image is still the same shape, just pointed elsewhere
    axes = [sorted(np.linalg.svd(t)[1]) for t in tensors]
    for other in axes[1:]:
        assert np.allclose(axes[0], other, atol=1e-5)


def test_the_ellipsoid_points_where_the_tensor_says():
    """A tensor loose along c must draw an ellipsoid long along z."""
    structure = Structure(
        lattice=Lattice.cubic(12.0),
        sites=[Site("C", [0.5, 0.5, 0.5],
                    u_aniso=(0.01, 0.01, 0.09, 0, 0, 0))],
        space_group="P1")
    model = build_scene(structure, ortep_settings())
    matrix = model.atom_tensors[0]
    rotation, axes, _ = np.linalg.svd(matrix)
    longest = rotation[:, int(np.argmax(axes))]
    assert abs(float(longest @ np.array([0.0, 0.0, 1.0]))) == \
        pytest.approx(1.0, abs=1e-6)
