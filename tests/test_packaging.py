"""What the spec files collect, checked without building anything.

The ordinary suite tests a source checkout and can say nothing about a
bundle.  This is the cheapest of the three layers in PACKAGING.md 8
and the highest-value one: it needs no PyInstaller, no display and no
build, and it is what fails when somebody adds a data file and forgets
that a frozen application does not get one for free.

Everything here reads ``packaging/bundle.py``'s pure half.  Anything
that needs ``PyInstaller.utils.hooks`` lives behind a function the
specs call and this file does not, because CI's test job installs
``[gui,build,test]`` and PyInstaller is in ``[dev]``.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import bundle  # noqa: E402


@pytest.fixture
def destinations():
    """Where each collected file lands, keyed by its source path."""
    return {Path(source): destination
            for source, destination in bundle.project_datas()}


def test_the_packaging_folder_is_not_an_importable_package():
    """``packaging`` is also a real distribution that pip, setuptools
    and PyInstaller all import.

    A directory with no ``__init__.py`` is only a *candidate* for a
    namespace package, so the regular one in site-packages still wins
    and our folder shadows nothing.  Adding an ``__init__.py`` here
    would reverse that and break the build tools from inside the
    repository, which is a confusing afternoon.  The specs reach
    ``bundle`` by path, and that is why.
    """
    import packaging.version  # noqa: F401

    assert not (ROOT / "packaging" / "__init__.py").exists()
    assert "site-packages" in packaging.__file__


def test_every_sample_in_the_menu_is_collected(destinations):
    """File > Open Sample builds its entries from the files on disk,
    so a sample missing from the bundle is a menu entry that greys out
    naming a source checkout, in a build that has no source checkout.

    It is also what ``--selftest`` opens, so this failing means the
    smoke test in CI has nothing to prove anything with.
    """
    from xtalapp import samples

    installed = samples.installed()
    assert installed, "no samples on this checkout to check against"

    for sample in installed:
        assert sample.path in destinations, f"{sample.path.name} missing"
        assert destinations[sample.path] == "resources/samples"


def test_the_samples_land_where_the_application_looks_for_them(
        destinations):
    """``samples.folder()`` is ``parent.parent / resources / samples``
    from ``xtalapp``, which in a onedir bundle is
    ``_internal/resources/samples``.

    That is a free win and the destination below is what preserves it.
    Flattening ``resources/`` into the package, or collecting the
    samples anywhere else, means adding a ``sys.frozen`` branch to
    code that does not need one.
    """
    from xtalapp import samples

    relative = samples.folder().relative_to(ROOT)
    assert set(destinations.values()) >= {relative.as_posix()}


def test_the_chooser_art_travels_with_the_application(destinations):
    """The chooser is the first thing a launch shows, and it is drawn
    from files: without them a bundle opens on a side panel with a
    name and nothing above or below it."""
    from xtalapp.dialogs import workspace_chooser

    for name in ("app.svg", "framework.png"):
        path = workspace_chooser.ART / name
        assert path.is_file(), name
        assert destinations[path] == "resources/chooser"


def test_the_rcsr_index_is_collected(destinations):
    """Without it the net panel cannot name a single topology.

    It is package data rather than a resource for exactly this reason
    -- see the note in pyproject.toml -- and it is read through a
    plain filesystem join, so it has to be a file in the bundle and
    not merely an importable module.
    """
    from xtal.analysis import rcsr

    assert rcsr.INDEX.is_file()
    assert rcsr.INDEX in destinations
    assert destinations[rcsr.INDEX] == "xtal/analysis/data"


def test_the_fragment_library_is_collected(destinations):
    """A picker with nothing in it is not a smaller feature, it is a
    broken one.

    Read through ``importlib.resources``, which finds it in a wheel
    and in a checkout alike -- and in a bundle only if it is put
    beside the module it belongs to, which is what the destination
    asserts.
    """
    from xtal.build import library

    path = ROOT / "xtal" / "build" / "data" / library.FILE
    assert path.is_file()
    assert path in destinations
    assert destinations[path] == "xtal/build/data"


def test_the_mof_database_is_collected(destinations):
    """The MOF builder is only in the bundle if its database is.

    PORMAKE is vendored precisely so a packaged user gets the builder
    -- and the code alone builds nothing.  ``database_root`` looks
    beside :mod:`xtal.mof.pormake` for 2404 nets and 867 blocks, and
    :func:`xtal.modules.mof.available` greys the entry out when it
    finds none, which in a shipped build would read as the feature
    having quietly gone away again.

    3271 files, so this asserts the counts and the two destinations
    rather than naming them: the failure being caught is "the glob
    stopped matching", and that shows up as a count of zero.
    """
    root = ROOT / "xtal" / "mof" / "pormake" / "database"
    nets = sorted((root / "topologies").glob("*.cgd"))
    blocks = sorted((root / "bbs").glob("*.xyz"))
    assert len(nets) > 2000
    assert len(blocks) > 800

    for path in (nets[0], nets[-1]):
        assert path in destinations
        assert destinations[path] == "xtal/mof/pormake/database/topologies"
    for path in (blocks[0], blocks[-1]):
        assert path in destinations
        assert destinations[path] == "xtal/mof/pormake/database/bbs"

    collected = {p for p in destinations if p.is_relative_to(root)}
    assert len(collected) == len(nets) + len(blocks)


def test_the_vendored_licence_and_provenance_are_collected(
        destinations):
    """Vendoring somebody else's MIT code obliges the notice to travel
    with it, including into a DMG and an installer.

    ``PROVENANCE.md`` travels for a different reason and an equally
    good one: it is the only record of what was changed and why, and a
    copy of the code without it is a fork nobody can diff.
    """
    root = ROOT / "xtal" / "mof" / "pormake"
    for name in ("LICENSE.md", "PROVENANCE.md"):
        path = root / name
        assert path.is_file()
        assert path in destinations
        assert destinations[path] == "xtal/mof/pormake"


def test_pormake_is_no_longer_excluded_from_the_bundle():
    """The change this whole vendoring was for, as an assertion.

    ``pormake`` and ``ase`` were both on the exclude list, and the
    first of them made the MOF builder the single feature a packaged
    user could not have.  Excluding either name now would cut a piece
    out of ``xtal`` itself: the builder is :mod:`xtal.mof.pormake`,
    and it is written over ``ase``.

    The three that came with PORMAKE stay excluded, and that is the
    other half of the claim -- 889 MB became 23 because they went, so
    a build that quietly reacquired one has lost the benefit.
    """
    assert "pormake" not in bundle.EXCLUDES
    assert "ase" not in bundle.EXCLUDES
    for gone in ("jax", "jaxlib", "pymatgen", "networkx"):
        assert gone in bundle.EXCLUDES


def test_a_dialog_an_action_only_names_is_still_named_to_pyinstaller():
    """A dialog reached through ``importlib`` has to be listed, or the
    button raises in a bundle and nowhere else.

    ``xtalapp.dialogs.module_dialog`` turns a module's declared dialog
    name into a class at click time, which PyInstaller's analysis
    cannot follow.  The first build that carried the MOF builder was
    missing both modules behind that mapping, so *Build MOF*, *Build
    molecule* and *Insert molecule* all died on
    ``ModuleNotFoundError`` -- while a source checkout, and therefore
    every other test in this file, imported them perfectly.

    This asserts the two lists are the same list.  ``bundle.py`` reads
    the mapping instead of copying it, so what is really being guarded
    is that nobody replaces that with a hand-written copy.
    """
    from xtalapp.dialogs import dialog_actions, dialog_modules, module_dialog

    named = bundle.dialog_imports()

    assert named, "no dialog modules named to PyInstaller at all"
    assert set(named) == set(dialog_modules())
    for action in dialog_actions():
        found = module_dialog(action)
        assert found is not None, f"{action} resolves to nothing"
        assert found.__module__ in named


def test_the_package_data_globs_still_match_pyproject():
    """``pyproject.toml`` is what a wheel ships and ``bundle.py`` is
    what the application ships, and they have to agree.

    This is the test that fails when a third data file is added to
    ``pyproject.toml`` and the bundle is left behind -- which produces
    an application that works perfectly in every test and is missing a
    file once frozen.
    """
    with (ROOT / "pyproject.toml").open("rb") as handle:
        declared = tomllib.load(handle)["tool"]["setuptools"][
            "package-data"]

    ours = {package.replace("/", "."): list(patterns)
            for package, patterns in bundle.PACKAGE_DATA.items()}
    assert ours == declared


def test_nothing_enormous_is_collected_by_accident(destinations):
    """The four refusals in ``bundle.OMITTED`` are decisions, and each
    has a reason recorded beside it.

    ``resources/`` is 1.5 GB on a developer's machine.  Collecting the
    tree wholesale rather than the one subfolder that ships is a
    plausible edit that nothing else would catch until somebody
    downloaded it.
    """
    assert bundle.OMITTED, "the refusals are the point of this test"

    for relative, reason in bundle.OMITTED.items():
        folder = ROOT / relative
        assert reason.strip(), f"{relative} is refused with no reason"
        for source in destinations:
            assert not source.is_relative_to(folder), \
                f"{source} comes from {relative}, which does not ship"


def test_no_third_party_binary_is_carried(destinations):
    """Zeo++ and the Slater-Koster sets are found, never shipped.

    They carry their own licences and citation obligations, they are
    gitignored so CI could not bundle them even if we wanted to, and
    Preferences > Engines plus the environment variables give
    three ways to point at a local copy.
    """
    from xtal.ff.dftb import hsd
    from xtal.modules import zeopp

    # The first two components, because one of these names a binary
    # and the other names a directory; `resources/<tree>` is the thing
    # that must not ship in both cases.
    for parts in (zeopp.BUNDLED, hsd.BUNDLED):
        refused = ROOT.joinpath(*parts[:2])
        assert refused.relative_to(ROOT).as_posix() in bundle.OMITTED
        for source in destinations:
            assert not source.is_relative_to(refused), \
                f"{source} is part of {refused}"


def test_no_path_is_a_reserved_name_on_windows():
    """A Windows checkout fails outright on one of these, and it takes
    the whole clone with it rather than the one file.

    ``resources/topo/TopCIF/nul.cif`` was such a path, and the Windows
    CI job had been failing at the *checkout* step because of it, long
    before it installed anything or ran a test:

        error: invalid path 'resources/topo/TopCIF/nul.cif'

    The names are reserved with any extension and in any directory, so
    the check is on the stem.  There is no way to test this from macOS
    or Linux other than by looking, which is what this does.
    """
    reserved = {"con", "prn", "aux", "nul"}
    reserved |= {f"com{n}" for n in range(1, 10)}
    reserved |= {f"lpt{n}" for n in range(1, 10)}

    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if listed.returncode != 0:            # not a checkout; nothing to say
        pytest.skip("not a git checkout")

    offenders = [
        line for line in listed.stdout.splitlines()
        if PurePosixPath(line).stem.lower() in reserved
    ]
    assert not offenders, (
        f"{offenders} cannot be checked out on Windows, and the "
        "failure takes the entire clone with it")


def test_every_icon_the_specs_name_exists():
    """A spec naming an icon that is not there fails the build late,
    after the several minutes of analysis, which is a slow way to find
    a typo.
    """
    for stem in ("app", "cif", "xtalproj"):
        assert (bundle.ICONS / f"{stem}.svg").is_file()
        assert (bundle.ICONS / f"{stem}.icns").is_file()
        assert (bundle.ICONS / f"{stem}.ico").is_file()


def test_the_windows_version_is_four_integers():
    """A Windows version resource cannot hold ``0.1.dev70+gaebc1f5cf``
    and fails the build if handed one.

    The full string still goes in the resource's text fields, so the
    properties dialog shows what was actually built; this is only the
    numeric tuple beside it.
    """
    numbers = bundle.windows_version()

    assert len(numbers) == 4
    assert all(isinstance(n, int) and n >= 0 for n in numbers)


def test_the_bundled_extras_are_the_ones_the_extras_page_promises():
    """Preferences > Engines tells the user which extras a
    packaged build includes.

    If that page and the spec disagree, the page is lying to somebody
    who cannot check -- which is the exact failure the page was built
    to avoid.
    """
    from xtalapp import extras

    promised = {extra.package for extra in extras.EXTRAS if extra.bundled}
    refused = {extra.package for extra in extras.EXTRAS
               if not extra.bundled}

    assert promised <= set(bundle.COLLECT)
    assert refused <= set(bundle.EXCLUDES)


def test_a_link_to_a_removed_framework_is_removed_with_it(tmp_path):
    """PyInstaller links every framework in by its short name, and
    postbuild deletes the unused Qt ones.  A link left pointing at
    nothing fails ``codesign --verify --strict`` with a message that
    names only the bundle, and ``spctl`` rejects the application.
    """
    import postbuild

    (tmp_path / "QtGui.framework").mkdir()
    (tmp_path / "QtGui").symlink_to("QtGui.framework")
    (tmp_path / "QtQuick").symlink_to("QtQuick.framework")

    assert postbuild.drop_dangling_links(tmp_path) == 1
    assert (tmp_path / "QtGui").is_symlink()
    assert not (tmp_path / "QtQuick").is_symlink()


def test_the_macos_floor_is_the_one_ci_installs_wheels_for():
    """CI swaps numpy and scipy for the builds that run on the oldest
    macOS the bundle declares; the macOS 14 builds pip picks on its
    own die at import on 13 with a selftest that passed on the runner.

    The wheel tag CI asks for, the deployment target anything it
    compiles is built for, and the Info.plist floor are written in two
    files, so this is what keeps them the same.
    """
    spec = (ROOT / "packaging" / "macos.spec").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8")
    floor = spec.split('"LSMinimumSystemVersion": "')[1].split('"')[0]

    assert f"macosx_{floor.split('.')[0]}_0_" in workflow
    assert f'MACOSX_DEPLOYMENT_TARGET: "{floor}"' in workflow
