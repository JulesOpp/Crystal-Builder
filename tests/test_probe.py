"""Asking a program whether it runs -- the half of the Test button
that needs no window.

The programs themselves are stood in for by small Python programs
that print what the real ones were measured printing, so that these
run on a machine with none of them installed -- Windows included,
which is why they are not shell scripts.
"""

import sys

from tests.conftest_program import write_program
from xtal.modules import probe


def _script(directory, name, body):
    return write_program(directory, name, "import sys\n" + body)


DFTB_BANNER = """\
print('|===============================================================')
print('|')
print('|  DFTB+ release 24.1')
print('|')
print('|  Copyright (C) 2006 - 2024  DFTB+ developers group')
print('ERROR!')
print('-> No input file found')
sys.exit(1)
"""


def test_a_dftb_banner_counts_as_found_whatever_the_exit_code(
        tmp_path):
    """DFTB+ has no --version.  With no input it prints its banner and
    exits 1; reading that exit code as failure would call every
    working install broken."""
    dftb = _script(tmp_path, "dftb+", DFTB_BANNER)

    ok, sentence = probe.run(probe.probe_for("tools/dftb", dftb))

    assert ok
    assert sentence == "DFTB+ release 24.1"


def test_waveplot_and_modes_name_themselves_in_the_banner(tmp_path):
    for key, name, line in (("tools/waveplot", "waveplot",
                             "DFTB+ (WAVEPLOT 0.3)"),
                            ("tools/modes", "modes",
                             "DFTB+ (MODES 0.03)")):
        tool = _script(tmp_path, name,
                       f"print('|  {line}')\nsys.exit(1)\n")
        assert probe.run(probe.probe_for(key, tool)) == (True, line)


def test_a_dftb_probe_runs_where_no_input_file_can_be(tmp_path,
                                                      monkeypatch):
    """Run in the current directory, a Test button would start
    whatever dftb_in.hsd happened to be lying there."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dftb_in.hsd").write_text("Geometry = {}")
    dftb = _script(tmp_path, "dftb+",
                   "import os\n"
                   "if os.path.exists('dftb_in.hsd'):\n"
                   "    print('dftb_in.hsd')\n"
                   "    sys.exit(0)\n" + DFTB_BANNER)

    ok, sentence = probe.run(probe.probe_for("tools/dftb", dftb))

    assert ok and "dftb_in.hsd" not in sentence


def test_tblite_is_asked_its_version(tmp_path):
    tblite = _script(tmp_path, "tblite",
                     "if sys.argv[1:] != ['--version']:\n"
                     "    sys.exit(2)\n"
                     "print('tblite version 0.3.0')\n")

    found = probe.probe_for("tools/tblite", tblite)

    assert found.argv == (str(tblite), "--version")
    assert probe.run(found) == (True, "tblite version 0.3.0")


def test_zeopp_is_found_by_its_usage_message(tmp_path):
    network = _script(tmp_path, "network",
                      "print('Network commandline invocation syntax:')\n"
                      "print('')\nprint('./network [-cssr]')\n")

    ok, sentence = probe.run(probe.probe_for("tools/zeopp", network))

    assert ok
    assert sentence.splitlines()[0] == (
        "Network commandline invocation syntax:")


def test_a_program_that_answers_wrongly_says_what_it_printed(tmp_path):
    broken = _script(tmp_path, "tblite",
                     "print('dyld: Library not loaded: libgfortran.5')\n"
                     "sys.exit(134)\n")

    ok, sentence = probe.run(probe.probe_for("tools/tblite", broken))

    assert not ok
    assert "exit code 134" in sentence
    assert "libgfortran" in sentence


def test_a_probe_that_times_out_says_so_rather_than_found(tmp_path):
    slow = _script(tmp_path, "blender", "import time\ntime.sleep(5)\n")
    asked = probe.Probe((str(slow), "--version"), timeout=0.3)

    ok, sentence = probe.run(asked)

    assert not ok
    assert "did not answer within 0.3 s" in sentence


def test_a_missing_binary_is_named_not_found(tmp_path):
    gone = tmp_path / "nowhere" / "xtb"

    ok, sentence = probe.run(probe.probe_for("tools/xtb", gone))

    assert not ok
    assert str(gone) in sentence
    assert "not found" in sentence


def test_a_folder_preference_has_nothing_to_run():
    assert probe.probe_for("tools/dftb_parameters", "/tmp") is None
    assert probe.probe_for("mof/bb_dir", "/tmp") is None


def test_a_package_is_imported_in_another_interpreter():
    """In this interpreter a broken compiled package could abort the
    application that asked about it."""
    asked = probe.probe_for_package("json")

    assert asked.argv[0] == sys.executable
    ok, sentence = probe.run(asked)
    assert ok
    assert sentence.startswith("json")


def test_a_package_that_warns_on_import_still_shows_its_version():
    """Measured on MACE: e3nn warns about ``torch.load`` as it
    imports, and the result shown was two lines of that warning."""
    asked = probe.probe_for_package("mace.calculators", timeout=60)
    output = ("/site-packages/e3nn/o3/_wigner.py:10: UserWarning: "
              "Environment variable TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD\n"
              "  _Jd, _W3j_flat = torch.load(path)\n"
              "mace 0.3.14\n")

    ok, sentence = probe.summarise(asked, 0, output)

    assert ok
    assert sentence == "mace 0.3.14"
    assert asked.timeout == 60


def test_a_module_inside_a_package_is_what_gets_imported():
    """``import mace`` never touches torch; the submodule does."""
    ok, sentence = probe.run(probe.probe_for_package("email.mime"))

    assert ok
    assert sentence.startswith("email")


def test_a_package_that_will_not_import_says_why():
    ok, sentence = probe.run(
        probe.probe_for_package("no_such_package_here"))

    assert not ok
    assert "No module named" in sentence


def test_a_frozen_build_is_asked_through_its_own_flag():
    asked = probe.probe_for_package("rdkit", frozen=True,
                                    executable="/Apps/Crystal Builder")

    assert asked.argv == ("/Apps/Crystal Builder", probe.IMPORT_FLAG,
                          "rdkit")


def test_a_package_name_cannot_carry_a_statement():
    import pytest
    with pytest.raises(ValueError):
        probe.probe_for_package("os; os.remove('x')")


def test_the_application_answers_the_flag_the_probe_sends():
    """Two spellings of one flag, in two packages that must not import
    each other at start-up; this is what keeps them one."""
    from xtalapp import main

    assert main.IMPORT_FLAG == probe.IMPORT_FLAG


def test_a_frozen_build_imports_one_package_and_names_its_version():
    import io

    from xtalapp import selftest

    out = io.StringIO()
    assert selftest.import_one("json", out) == 0
    assert out.getvalue().startswith("json")
    out = io.StringIO()
    assert selftest.import_one("no_such_package_here", out) == 1
    assert "ModuleNotFoundError" in out.getvalue()
