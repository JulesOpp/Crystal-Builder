"""The headless command line."""

from pathlib import Path

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


def test_symmetry_reports_the_hand(quartz_cif, capsys):
    assert main(["symmetry", quartz_cif]) == 0
    out = capsys.readouterr().out
    assert "hand           chiral, enantiomorph P3121" in out


def test_symmetry_lists_the_subgroups(quartz_cif, capsys):
    assert main(["symmetry", quartz_cif, "--subgroups"]) == 0
    out = capsys.readouterr().out
    assert ("subgroups (6, 3 giving up translations, 3 on a "
            "larger cell, 5 maximal") in out
    assert "P 32" in out
    assert "2 -> 3 sites" in out            # the oxygen splits
    assert "same axes, same origin" in out
    assert "x3" in out                      # the three conjugate C2


def test_subgroups_of_p1_say_there_are_none(tmp_path, rutile, capsys):
    from xtal.core import symmetry as sym
    from xtal.io import write_cif
    path = tmp_path / "p1.cif"
    write_cif(sym.reduce_to_p1(rutile), path)
    assert main(["symmetry", str(path), "--subgroups"]) == 0
    assert "no proper subgroups" in capsys.readouterr().out


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


def test_convert_refuses_to_write_over_its_input(rutile_cif, capsys):
    """It read the whole file first, so this was never truncation: it
    was somebody's deposited CIF replaced by this program's minimal
    rendering of it, with no prompt."""
    before = Path(rutile_cif).read_bytes()

    assert main(["convert", rutile_cif, rutile_cif]) == 1

    assert "is the input" in capsys.readouterr().err
    assert Path(rutile_cif).read_bytes() == before


def test_bonds(rutile_cif, capsys):
    assert main(["bonds", rutile_cif]) == 0
    out = capsys.readouterr().out
    assert "12 bonds" in out
    assert "framework" in out
    assert "1.9" in out                     # Ti-O distances


def test_optimize_can_relax_the_cell_and_writes_it_out(rutile_cif,
                                                       tmp_path,
                                                       capsys):
    """The same relaxation the panel runs, from a script -- including
    the lattice, which is the part a file has to carry back out."""
    from xtal.io import read_cif

    out = tmp_path / "relaxed.cif"
    main(["optimize", rutile_cif, "--relax-cell", "--max-steps", "12",
          "-o", str(out), "-q"])
    printed = capsys.readouterr().out
    assert "cell " in printed
    assert "by volume" in printed

    before = read_cif(rutile_cif).lattice.parameters
    after = read_cif(out).lattice.parameters
    assert after[0] != pytest.approx(before[0], abs=1e-6)
    # Still tetragonal: a = b, and every angle still a right one.
    assert after[1] == pytest.approx(after[0], abs=1e-6)
    assert after[3:] == pytest.approx(before[3:], abs=1e-6)


def test_optimize_leaves_the_cell_alone_unless_asked(rutile_cif,
                                                     tmp_path,
                                                     capsys):
    from xtal.io import read_cif

    out = tmp_path / "relaxed.cif"
    main(["optimize", rutile_cif, "--max-steps", "5", "-o", str(out),
          "-q"])
    assert "by volume" not in capsys.readouterr().out
    assert read_cif(out).lattice.parameters == pytest.approx(
        read_cif(rutile_cif).lattice.parameters, abs=1e-9)


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


# ------------------------------------------------------------ modules
#
# The registry is headless, so it is runnable from a script -- and that
# is the proof, not the convenience: a module that could only be run by
# clicking it is one whose parameters, run folder and log could not be
# tested without a display.

@pytest.fixture
def stub_module():
    from xtal.modules import MODULES, stub
    stub.register(MODULES)
    yield MODULES
    MODULES.unregister("stub")


def test_modules_lists_what_can_be_run(stub_module, capsys):
    assert main(["modules"]) == 0
    out = capsys.readouterr().out
    assert "forcefield.single-point" in out
    assert "(in the window)" in out         # the panel performs it
    assert "stub.count" in out
    assert "-p steps=5" in out              # and what it takes


def test_run_executes_a_module_against_a_file(stub_module, rutile_cif,
                                              capsys):
    assert main(["run", "stub.count", rutile_cif,
                 "-p", "steps=2", "-p", "interval=0"]) == 0
    out = capsys.readouterr().out
    assert "step 1 of 2" in out
    assert "counted to 2" in out


def test_run_writes_the_same_run_folder_the_window_does(
        stub_module, tmp_path, rutile_cif, capsys):
    root = tmp_path / "ws"
    assert main(["run", "stub.count", rutile_cif, "--workspace",
                 str(root), "-p", "steps=1", "-p", "interval=0",
                 "-q"]) == 0
    folder = root / "rutile" / "stub-count-001"
    assert (folder / "counted.txt").exists()
    log = (folder / "run.log").read_text()
    assert "module         stub.count" in log
    assert "Stub: Count here" in log


def test_run_reports_a_failed_module_with_a_status(stub_module,
                                                   rutile_cif):
    assert main(["run", "stub.count", rutile_cif, "-p", "steps=1",
                 "-p", "interval=0", "-p", "fail=true", "-q"]) == 2


def test_run_refuses_an_entry_the_window_performs(stub_module,
                                                  rutile_cif, capsys):
    assert main(["run", "forcefield.optimise", rutile_cif]) == 1
    assert "application window" in capsys.readouterr().err


def test_run_says_what_there_is_when_the_name_is_wrong(stub_module,
                                                       rutile_cif,
                                                       capsys):
    assert main(["run", "nonesuch.go", rutile_cif]) == 1
    assert "unknown module" in capsys.readouterr().err


def test_a_parameter_needs_a_value(stub_module, rutile_cif, capsys):
    assert main(["run", "stub.count", rutile_cif, "-p", "steps"]) == 1
    assert "name=value" in capsys.readouterr().err


def test_a_misspelt_param_is_refused_by_name(stub_module, rutile_cif,
                                            capsys):
    """`step=2` for `steps=2` used to run on every default and exit 0,
    having measured something other than what was asked."""
    assert main(["run", "stub.count", rutile_cif, "-p", "step=2"]) == 1

    err = capsys.readouterr().err
    assert "'step'" in err
    assert "steps" in err                   # and what it does take


def test_a_param_with_no_name_is_refused(stub_module, rutile_cif,
                                         capsys):
    assert main(["run", "stub.count", rutile_cif, "-p", "=2"]) == 1
    assert "name=value" in capsys.readouterr().err


def test_a_missing_file_is_named_not_quoted_from_the_c_library(
        tmp_path, capsys):
    """The handler that said so sat behind the OSError one and never
    ran."""
    missing = tmp_path / "nowhere.xyz"

    assert main(["info", str(missing)]) == 1

    err = capsys.readouterr().err
    assert "no such file" in err
    assert "nowhere.xyz" in err


def test_a_module_that_builds_a_structure_runs_with_no_file(capsys):
    """FILE is what the action needs, not what the parser demands.

    ``needs_structure = False`` has meant "a module that fetches or
    builds one" since the registry was written, and such a module has
    nothing to be given.  Checked against the MOF builder's own
    availability so that it says the same thing on every machine.
    """
    from xtal.modules.mof import available

    code = main(["run", "mof.build", "-p", "topology=", "-q"])
    said = "".join(capsys.readouterr()).lower()
    # It got as far as the module's own refusal rather than being
    # stopped by the parser for a file it was never going to read.
    # Which refusal it is depends on the machine: a build with no net
    # named when the builder works, and otherwise whatever
    # `available` gives as the reason -- a missing database, or a
    # missing ase.  All three are the module's own.
    assert code != 0
    assert "needs a structure" not in said
    availability = available()
    expected = ("topology" if availability.ok
                else availability.reason.lower())
    assert expected in said


def test_a_module_that_needs_a_structure_still_asks_for_one(
        stub_module, capsys):
    assert main(["run", "stub.count"]) == 1
    assert "needs a structure" in capsys.readouterr().err
