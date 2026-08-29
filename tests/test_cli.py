"""The headless command line."""

import pytest

from xtal.cli import main


def test_info(rutile_cif, capsys):
    assert main(["info", rutile_cif]) == 0
    out = capsys.readouterr().out
    assert "TiO2" in out
    assert "P42/mnm" in out
    assert "4.2" in out                     # density


def test_symmetry(rutile_cif, capsys):
    assert main(["symmetry", rutile_cif]) == 0
    out = capsys.readouterr().out
    assert "P4_2/mnm" in out
    assert "#136" in out
    assert "-P 4n 2n" in out                # the Hall symbol
    assert "operations     16" in out


def test_symmetry_with_wyckoff(rutile_cif, capsys):
    assert main(["symmetry", rutile_cif, "--wyckoff"]) == 0
    out = capsys.readouterr().out
    assert "wyckoff" in out
    assert "m.mm" in out                    # Ti site symmetry


def test_symmetry_tolerance_is_exposed(tmp_path, rutile, capsys):
    """A distorted structure looks triclinic at a tight tolerance and
    tetragonal at a loose one -- from the command line too."""
    from xtal.core import symmetry as sym
    from xtal.io import write_cif
    flat = sym.reduce_to_p1(rutile)
    flat.sites[2].frac = flat.sites[2].frac + 0.004
    flat.touch()
    path = tmp_path / "bent.cif"
    write_cif(flat, path)

    main(["symmetry", str(path), "--symprec", "1e-5"])
    tight = capsys.readouterr().out
    main(["symmetry", str(path), "--symprec", "0.1"])
    loose = capsys.readouterr().out
    assert "#136" not in tight
    assert "#136" in loose


def test_symmetry_writes_a_symmetrised_file(tmp_path, rutile, capsys):
    from xtal.core import symmetry as sym
    from xtal.io import read_cif, write_cif
    flat = sym.reduce_to_p1(rutile)
    src = tmp_path / "flat.cif"
    write_cif(flat, src)
    out = tmp_path / "sym.cif"

    assert main(["symmetry", str(src), "-o", str(out)]) == 0
    assert "wrote" in capsys.readouterr().out
    back = read_cif(out)
    assert back.n_sites == 2
    assert back.space_group.number == 136


def test_convert_between_formats(rutile_cif, tmp_path, capsys):
    out = tmp_path / "out.xyz"
    assert main(["convert", rutile_cif, str(out)]) == 0
    assert out.exists()
    assert "wrote" in capsys.readouterr().out


def test_convert_applies_transforms(rutile_cif, tmp_path, capsys):
    out = tmp_path / "big.cif"
    assert main(["convert", rutile_cif, str(out), "--supercell",
                 "2", "2", "1", "--p1"]) == 0
    text = capsys.readouterr().out
    assert "24 sites" in text               # 6 atoms x 4 cells
    assert "P1" in text


def test_bonds(rutile_cif, capsys):
    assert main(["bonds", rutile_cif]) == 0
    out = capsys.readouterr().out
    assert "12 bonds" in out
    assert "framework" in out
    assert "1.9" in out                     # Ti-O distances


def test_formats(capsys):
    assert main(["formats"]) == 0
    out = capsys.readouterr().out
    assert "cif" in out and "xyz" in out


def test_warnings_go_to_stderr(tmp_path, capsys):
    path = tmp_path / "bare.cif"
    path.write_text(
        "data_x\n_cell_length_a 4\n_cell_length_b 4\n"
        "_cell_length_c 4\n_cell_angle_alpha 90\n"
        "_cell_angle_beta 90\n_cell_angle_gamma 90\n"
        "loop_\n_atom_site_label\n_atom_site_fract_x\n"
        "_atom_site_fract_y\n_atom_site_fract_z\nNa1 0 0 0\n")
    assert main(["info", str(path)]) == 0
    captured = capsys.readouterr()
    assert "assuming P1" in captured.err
    assert "assuming P1" not in captured.out


def test_unreadable_file_fails_cleanly(tmp_path, capsys):
    bad = tmp_path / "bad.cif"
    bad.write_text("this is not a cif\n")
    assert main(["info", str(bad)]) == 1
    assert "error" in capsys.readouterr().err


def test_unknown_extension_fails_cleanly(tmp_path, capsys):
    path = tmp_path / "thing.wat"
    path.write_text("x")
    assert main(["info", str(path)]) == 1
    assert "error" in capsys.readouterr().err


def test_version_and_help():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    with pytest.raises(SystemExit):
        main([])                            # no subcommand
