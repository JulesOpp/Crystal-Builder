"""The Zeo++ module, end to end, without Zeo++.

``network`` is a nine-megabyte binary that takes twenty seconds on a
framework, so the tests that matter run against a stand-in: a Python
script named by ``XTAL_ZEOPP`` that reads the command line the module
built, checks it, and writes the file Zeo++ would have written.  That
covers everything the module is actually responsible for -- what it
writes, what it launches, what it reads back and what it refuses --
and none of what Zeo++ is responsible for.

The one test that does use the real binary is skipped when it is not
there.
"""

import pytest

from tests.conftest_program import write_program
from tests.conftest_zeo import CHAN, RES, write_fake_network
from xtal.analysis import porosity
from xtal.modules import MODULES, Job, zeopp
from xtal.modules.registry import ModuleRegistry
from xtal.workspace import Workspace


@pytest.fixture
def fake_network(tmp_path, monkeypatch):
    """Every flag the module can pass, answered."""
    script = write_fake_network(tmp_path)
    monkeypatch.setenv("XTAL_ZEOPP", str(script))
    return script


@pytest.fixture
def workspace(tmp_path, rutile):
    space = Workspace.create(tmp_path / "space")
    return space.add_document("rutile")


def run(name, structure, entry=None, **params):
    module, action = MODULES.find(f"zeopp.{name}")
    folder = None
    if entry is not None:
        folder = entry.next_run(module.name, action.run_kind)
    job = Job(structure=structure, params=action.coerce(params),
              folder=folder, label=name)
    return action.run(job), folder


def argv_of(folder):
    return (folder.path / "argv.txt").read_text().splitlines()


# ------------------------------------------------------- the declaration

def test_it_registers_four_entries():
    module = MODULES.get("zeopp")
    assert [a.name for a in module.actions] == [
        "diameters", "surface-area", "volume", "psd"]


def test_registering_touches_no_existing_file():
    """The point of the registry: a fresh one gets the module from
    the module's own ``register``."""
    registry = ModuleRegistry()
    zeopp.register(registry)
    assert "zeopp" in registry
    assert registry.find("zeopp.psd")[1].run is not None


def test_a_missing_binary_greys_it_out_and_says_why(monkeypatch):
    """The state an external engine will usually be in, and the one
    the module tree greys out and puts a sentence on."""
    from dataclasses import replace

    monkeypatch.setenv("XTAL_ZEOPP", "/nowhere/network")
    monkeypatch.setattr(zeopp, "bundled", lambda: None)
    monkeypatch.setattr(
        zeopp, "PROGRAM",
        replace(zeopp.PROGRAM, name="network-that-is-not-installed"))

    available = zeopp.available()
    assert not available
    assert "zeoplusplus" in available.reason
    assert "XTAL_ZEOPP" in available.reason


def test_every_entry_offers_the_radii(monkeypatch):
    """Every number Zeo++ returns is a function of them, so no entry
    may be missing the control."""
    for action in MODULES.get("zeopp").actions:
        assert "radii" in action.defaults()
        assert "high_accuracy" in action.defaults()


# ------------------------------------------------------------- diameters

def test_the_diameters_come_back_as_a_report(fake_network, rutile,
                                             workspace):
    result, folder = run("diameters", rutile, workspace)

    assert result.ok
    assert "D_f" in result.message
    assert result.report.tables
    labels = [r.label for r in result.report.tables[0].rows]
    assert "Largest free sphere" in labels


def test_the_channels_are_asked_for_in_the_same_run(
        fake_network, rutile, workspace):
    """One Voronoi decomposition, two commands over it.  Zeo++ builds
    the decomposition once per invocation and it is the whole cost of
    a run, so a second invocation for -chan would double a run to
    learn one number."""
    _result, folder = run("diameters", rutile, workspace)
    argv = argv_of(folder)
    assert "-res" in argv and "-chan" in argv
    assert argv.count(str(zeopp.binary() or argv[0])) <= 1


def test_the_dimensionality_reaches_the_table(fake_network, rutile,
                                              workspace):
    """The number every porous-materials paper reports and the one no
    other Zeo++ output carries."""
    result, _folder = run("diameters", rutile, workspace)
    rows = {r.label: r.value for r in result.report.tables[0].rows}
    assert rows["Dimensionality"].startswith("3D")
    assert rows["Channels"] == "1"
    assert "3D" in result.message


def test_the_probe_decides_which_channels_count(fake_network, rutile,
                                                workspace):
    """The three diameters measure the crystal and ignore the probe;
    -chan does not, so the radius it is given has to be the one the
    user chose."""
    _r, folder = run("diameters", rutile, workspace, gas="he")
    argv = argv_of(folder)
    assert argv[argv.index("-chan") + 1] == "1.3"


def test_a_channel_radius_of_its_own_overrides_the_probe(
        fake_network, rutile, workspace):
    _r, folder = run("diameters", rutile, workspace, gas="he",
                     channel_radius=2.5)
    argv = argv_of(folder)
    assert argv[argv.index("-chan") + 1] == "2.5"


def test_the_channel_file_is_kept_beside_the_diameters(
        fake_network, rutile, workspace):
    result, folder = run("diameters", rutile, workspace)
    kept = {p.name for p in result.artifacts}
    assert {"diameters.res", "channels.chan"} <= kept


def test_one_channel_gets_no_second_table(fake_network, rutile,
                                          workspace):
    """A single channel is already described by the rows above it, and
    repeating its three numbers underneath would be noise."""
    result, _folder = run("diameters", rutile, workspace)
    assert len(result.report.tables) == 1


def test_several_channels_each_get_a_row():
    """A framework with a wide 1D channel and a narrow 3D one is two
    materials to a gas, and the maximum over them -- which is all the
    .res file reports -- describes neither."""
    channels = (porosity.Channel(0, 1, 12.0, 11.0, 12.0),
                porosity.Channel(1, 3, 6.0, 4.0, 5.5))
    report = zeopp._diameter_report(
        porosity.parse_res("out.res 12.0 4.0 12.0"), channels,
        "Nitrogen (1.86 A)", "radii from Zeo++'s own table")
    assert len(report.tables) == 2
    rows = report.tables[1].rows
    assert len(rows) == 2
    assert "1D" in rows[0].texts[1] and "3D" in rows[1].texts[1]


def test_the_report_says_where_d_f_is_not_known():
    """The half of CLAUDE.md's porosity rule that is words: D_f is a
    bottleneck on an edge, no Zeo++ output gives edge radii, so what
    is drawn for it is the channel it travels along -- and the report
    says so.  The meanings test beside it only asked that each meaning
    was not empty, so this sentence could have become anything."""
    channels = (porosity.Channel(0, 1, 12.0, 11.0, 12.0),)
    report = zeopp._diameter_report(
        porosity.parse_res("out.res 12.0 4.0 12.0"), channels,
        "Nitrogen (1.86 A)", "radii from Zeo++'s own table")
    note = report.tables[0].note

    assert "bottleneck" in note
    assert "no output carries it" in note


def test_the_run_comes_back_with_something_to_draw(
        fake_network, rutile, workspace):
    """The whole point of the entry: where the pores are is an answer
    no table can give."""
    result, folder = run("diameters", rutile, workspace)
    assert "-visVoro" in argv_of(folder)
    network = result.overlay
    assert network is not None
    assert network.n_nodes == 6
    assert network.n_edges == 3
    node, radius = network.largest()
    assert 2 * radius == pytest.approx(18.742, abs=0.01)
    assert len(node) == 3


def test_the_drawing_can_be_turned_off(fake_network, rutile,
                                       workspace):
    """-visVoro writes six files and reads the whole Voronoi network
    back; somebody who only wants the three numbers should not pay
    for it."""
    result, folder = run("diameters", rutile, workspace, draw=False)
    assert "-visVoro" not in argv_of(folder)
    assert result.overlay is None
    assert result.ok


def test_the_network_carries_the_channels_it_belongs_to(
        fake_network, rutile, workspace):
    """One record, so a picture can never be shown beside somebody
    else's dimensionality."""
    result, _folder = run("diameters", rutile, workspace)
    assert result.overlay.channels[0].dimensionality == 3
    assert result.overlay.probe == pytest.approx(1.86)


def test_a_run_that_could_not_be_drawn_still_answers(
        rutile, workspace, tmp_path, monkeypatch):
    """The three diameters are already read and correct.  Refusing the
    whole answer because the drawing is missing would be the tail
    wagging the dog."""
    script = write_program(tmp_path, "network", (
        "import sys, pathlib\n"
        "argv = sys.argv[1:]\n"
        'pathlib.Path("argv.txt").write_text("\\n".join(argv))\n'
        f"pathlib.Path(argv[argv.index('-res') + 1])"
        f".write_text({RES!r})\n"
        f"pathlib.Path(argv[argv.index('-chan') + 2])"
        f".write_text({CHAN!r})\n"))
    monkeypatch.setenv("XTAL_ZEOPP", str(script))

    result, folder = run("diameters", rutile, workspace)
    assert result.ok
    assert result.overlay is None
    assert "D_f" in result.message
    assert "nothing to draw" in folder.run.log_path.read_text()


def test_it_writes_the_whole_cell_as_cssr(fake_network, rutile,
                                          workspace):
    _result, folder = run("diameters", rutile, workspace)
    written = (folder.path / zeopp.INPUT_NAME).read_text()
    assert "SPGR =  1 P 1" in written
    assert argv_of(folder)[-1] == zeopp.INPUT_NAME


def test_high_accuracy_is_on_by_default_and_can_be_turned_off(
        fake_network, rutile, workspace):
    _r, folder = run("diameters", rutile, workspace)
    assert "-ha" in argv_of(folder)

    _r, other = run("diameters", rutile, workspace,
                    high_accuracy=False)
    assert "-ha" not in argv_of(other)


# ---------------------------------------------------------- surface area

def test_the_surface_area_defaults_to_nitrogen(fake_network, rutile,
                                               workspace):
    result, folder = run("surface-area", rutile, workspace)

    assert "Nitrogen" in result.message
    argv = argv_of(folder)
    at = argv.index("-sa")
    # channel radius, probe radius, samples -- and the channel radius
    # follows the probe when it was left at zero.
    assert float(argv[at + 1]) == pytest.approx(1.86)
    assert float(argv[at + 2]) == pytest.approx(1.86)
    assert int(argv[at + 3]) == 2000


def test_a_channel_radius_of_its_own_is_passed_through(
        fake_network, rutile, workspace):
    _r, folder = run("surface-area", rutile, workspace,
                     channel_radius=1.2)
    argv = argv_of(folder)
    at = argv.index("-sa")
    assert float(argv[at + 1]) == pytest.approx(1.2)
    assert float(argv[at + 2]) == pytest.approx(1.86)


def test_a_custom_probe_is_used(fake_network, rutile, workspace):
    _r, folder = run("surface-area", rutile, workspace,
                     gas="custom", probe_radius=1.4)
    argv = argv_of(folder)
    assert float(argv[argv.index("-sa") + 2]) == pytest.approx(1.4)


def test_a_probe_of_zero_is_refused(fake_network, rutile, workspace):
    with pytest.raises(ValueError, match="measures nothing"):
        run("surface-area", rutile, workspace, gas="custom",
            probe_radius=0.0)


def test_the_area_report_names_the_probe_and_the_radii(
        fake_network, rutile, workspace):
    """An area quoted without either is not reproducible."""
    result, _folder = run("surface-area", rutile, workspace)
    text = result.report.as_text()
    assert "1.86" in text
    assert "radii" in text


# ------------------------------------------------------ the distribution

def test_the_distribution_comes_back_as_a_histogram(
        fake_network, rutile, workspace):
    result, _folder = run("psd", rutile, workspace)

    assert result.ok
    histogram = result.report.histograms[0]
    assert histogram.n_bins < 1000          # only the occupied window
    assert histogram.curve is not None      # the bars and the curve
    assert histogram.markers                # where the probe stops


def test_the_distribution_uses_a_small_probe_by_default(
        fake_network, rutile, workspace):
    _r, folder = run("psd", rutile, workspace)
    argv = argv_of(folder)
    assert float(argv[argv.index("-psd") + 2]) == pytest.approx(1.2)


# ------------------------------------------------------------ the radii

def test_the_builtin_table_passes_no_radii_file(fake_network, rutile,
                                                workspace):
    _r, folder = run("diameters", rutile, workspace)
    assert "-r" not in argv_of(folder)


def test_our_own_table_is_written_and_passed(fake_network, rutile,
                                             workspace):
    _r, folder = run("diameters", rutile, workspace, radii="vdw")
    argv = argv_of(folder)
    assert "-r" in argv
    written = (folder.path / zeopp.RADII_NAME).read_text()
    assert written.splitlines()[0].split()[0] in ("O", "Ti")
    assert len(written.splitlines()) == 2


def test_a_radii_file_of_your_own_wins(fake_network, rutile,
                                       workspace, tmp_path):
    mine = tmp_path / "mine.rad"
    mine.write_text("Ti 1.0\nO 1.0\n")
    _r, folder = run("diameters", rutile, workspace, radii="vdw",
                     radii_file=str(mine))
    argv = argv_of(folder)
    assert argv[argv.index("-r") + 1] == str(mine)


def test_a_radii_file_that_is_not_there_stops_the_run(
        fake_network, rutile, workspace, tmp_path):
    """Silently falling back would make it a different calculation."""
    with pytest.raises(ValueError, match="radii file"):
        run("diameters", rutile, workspace,
            radii_file=str(tmp_path / "gone.rad"))


# ------------------------------------------------------- what it refuses

def test_a_disordered_structure_never_reaches_zeopp(fake_network,
                                                    rutile, workspace):
    rutile.sites[1].occupancy = 0.5
    with pytest.raises(ValueError, match="partially occupied"):
        run("diameters", rutile, workspace)
    # Nothing was written and nothing was launched: the refusal is in
    # front of the writer, not after it.
    assert not list(workspace.path.rglob("*.cssr"))
    assert not list(workspace.path.rglob("argv.txt"))


def test_a_run_that_writes_nothing_says_so(tmp_path, rutile,
                                           workspace, monkeypatch):
    silent = write_program(tmp_path, "silent",
                           "print('did nothing')\n")
    monkeypatch.setenv("XTAL_ZEOPP", str(silent))

    with pytest.raises(ValueError, match="without writing"):
        run("diameters", rutile, workspace)


def test_a_failing_binary_is_a_failed_result_not_an_exception(
        tmp_path, rutile, workspace, monkeypatch):
    broken = write_program(
        tmp_path, "broken",
        "import sys\n"
        "print('cannot read that file')\nsys.exit(2)\n")
    monkeypatch.setenv("XTAL_ZEOPP", str(broken))

    result, _folder = run("diameters", rutile, workspace)
    assert not result.ok
    assert "cannot read that file" in result.detail


# ---------------------------------------------------- with no workspace

def test_it_still_answers_with_no_workspace(fake_network, rutile):
    """The answer is a table on screen and not only a file on disk,
    so losing the files is better than refusing."""
    result, _folder = run("diameters", rutile, None)
    assert result.ok
    assert result.report.tables
    assert result.artifacts == ()


# ------------------------------------------------------- the real thing

@pytest.mark.skipif(zeopp.binary() is None,
                    reason="Zeo++ is not installed")
def test_the_real_binary_reads_what_we_write(quartz, workspace,
                                             monkeypatch):
    """The one thing the stand-in cannot check: that Zeo++ accepts the
    CSSR this application writes."""
    monkeypatch.delenv("XTAL_ZEOPP", raising=False)
    result, folder = run("diameters", quartz, workspace)

    assert result.ok, result.detail
    found = porosity.parse_res(
        (folder.path / "diameters.res").read_text())
    # Quartz is dense: nothing of any size gets through it.
    assert 0.0 <= found.free < found.included
    assert "D_f" in result.message


# --------------------------------------------------------------- volume

def test_the_volume_comes_back_as_a_report(fake_network, rutile,
                                           workspace):
    result, _folder = run("volume", rutile, workspace)
    assert result.ok
    assert "cm^3/g" in result.message
    labels = [r.label for r in result.report.tables[0].rows]
    assert "Accessible volume" in labels


def test_the_pore_volume_is_the_occupiable_one_by_default(
        fake_network, rutile, workspace):
    """-vol reports the volume the probe's centre can reach and
    -volpo the volume it occupies.  The second is always the larger
    and is what a paper means by pore volume, so quoting one for the
    other is the mistake this defaults away from."""
    _r, folder = run("volume", rutile, workspace)
    assert "-volpo" in argv_of(folder)

    _r, other = run("volume", rutile, workspace, occupiable=False)
    argv = argv_of(other)
    assert "-vol" in argv and "-volpo" not in argv


def test_the_occupiable_volume_is_actually_read(fake_network, rutile,
                                                workspace):
    """-volpo spells every key POAV_* and the default runs it, so a
    parser that only knew AV_* would answer a confident zero."""
    result, _folder = run("volume", rutile, workspace)
    assert "0.000 cm^3/g" not in result.message
    rows = {r.label: r.value for r in result.report.tables[0].rows}
    assert rows["Accessible volume"] == "1.3250"
    # -volpo writes no counts, so no row claims there are none.
    assert "Channels" not in rows


def test_the_volume_run_draws_the_surface_of_what_it_measured(
        fake_network, rutile, workspace):
    """Zeo++ cannot supply it -- both its grid writers fail -- so the
    surface is marched here, at the run's own probe and radii, and it
    is the boundary of the volume in the table."""
    result, _folder = run("volume", rutile, workspace, spacing=0.15,
                          gas="custom", probe_radius=0.05)
    network = result.overlay
    assert network is not None
    assert network.n_surface_faces > 100
    assert network.probe == pytest.approx(0.05)
    assert "surface" in network.summary()


def test_the_surface_can_be_turned_off(fake_network, rutile,
                                       workspace):
    result, _folder = run("volume", rutile, workspace, draw=False,
                          gas="custom", probe_radius=0.05)
    assert result.overlay is None
    assert result.ok


def test_the_surface_uses_the_radii_the_run_used(fake_network, rutile,
                                                 workspace):
    """A picture drawn from a different table beside a number measured
    with this one is the disagreement the whole module avoids."""
    assert zeopp._radius_function(
        Job(structure=rutile, params={"radii": "builtin"}))[0] \
        is porosity.zeo_radius

    from xtal.core import elements
    assert zeopp._radius_function(
        Job(structure=rutile, params={"radii": "vdw"}))[0] \
        is elements.vdw_radius


def test_a_radii_file_gets_no_surface_and_says_why(fake_network,
                                                   rutile, workspace,
                                                   tmp_path):
    """The one case that cannot be matched: we do not read the user's
    table, so a surface from ours would not be the volume above."""
    table = tmp_path / "mine.rad"
    table.write_text("Ti 1.0\nO 1.0\n")
    result, folder = run("volume", rutile, workspace,
                         gas="custom", probe_radius=0.05,
                         radii_file=str(table))
    assert result.ok
    assert result.overlay is None
    assert "radii file of its own" in folder.run.log_path.read_text()


def test_a_dense_solid_gets_no_surface_and_that_is_an_answer(
        fake_network, rutile, workspace):
    """Nothing in rutile is anything like 1.86 A from an atom, so
    there is nothing to draw -- and the volume in the table is still
    right.  A probe that fits nowhere is an answer, not a failure."""
    result, folder = run("volume", rutile, workspace, spacing=0.4)
    assert result.ok
    assert result.overlay is None
    assert "nothing to draw" in folder.run.log_path.read_text()


def test_the_row_says_which_of_the_two_was_measured(fake_network,
                                                    rutile, workspace):
    result, _folder = run("volume", rutile, workspace)
    note = result.report.tables[0].rows[0].note
    assert "occupies" in note

    other, _f = run("volume", rutile, workspace, occupiable=False)
    assert "centre" in other.report.tables[0].rows[0].note
