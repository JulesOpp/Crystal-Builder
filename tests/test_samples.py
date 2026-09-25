"""Twenty-three real structures ship in resources/samples, and now open.

They had been in the repository since the early phases with nothing in
the application referring to them, so a fresh installation opened an
empty window to somebody who may not own a CIF yet.

The part with teeth is *how* they open: copied into the workspace and
opened from there.  The files live inside the application's own folder
-- a signed bundle on macOS, under Program Files on Windows -- so a
sample that adopted its own path would answer Ctrl+S by trying to
write there.  The copy is what makes a sample an ordinary structure of
this workspace instead.
"""

import re

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QFileDialog, QWidget  # noqa: E402

from xtal.io import FORMATS  # noqa: E402
from xtalapp import menus, samples  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Sample{tmp_path.name}")
    settings.clear_window()
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_every_sample_in_the_catalogue_is_a_file_that_is_there():
    """A renamed CIF turns an entry into a dialog saying nothing is
    installed, which reads as the whole feature being broken."""
    missing = [s.label for s in samples.SAMPLES if s.path is None]

    assert missing == []
    assert len(samples.SAMPLES) == 39


def test_every_sample_is_a_structure_this_application_can_read():
    """The menu offers them, so each has to survive the reader that
    the menu will hand it to."""
    for sample in samples.SAMPLES:
        structure = FORMATS.read(sample.path)
        assert structure.n_sites > 0, sample.label


def test_a_sample_is_copied_into_the_workspace(window):
    """Never opened in place: the application's own folder is signed
    on macOS and under Program Files on Windows."""
    document = window.open_sample("mof5")

    assert document is not None
    assert window.tabs.count() == 1
    assert document.entry is not None
    assert document.path == document.entry.structure_path
    assert document.path.parent.parent == window.workspace.root
    assert str(samples.folder()) not in str(document.path)


def test_the_entry_is_named_after_the_sample_not_the_data_block(window):
    """MOF-5.cif calls its block VESTA_phase_1.  The folder the copy
    goes in is named from the catalogue instead."""
    document = window.open_sample("mof5")

    assert document.entry.name == "MOF-5"
    assert window.tabs.tabText(0) == document.path.name


def test_saving_a_sample_never_writes_inside_the_application(
        window, monkeypatch):
    """The whole reason they used to open without a path.  It is the
    copy that is saved now, so Ctrl+S asks nothing and still cannot
    reach resources/samples -- a signed bundle on macOS, and under
    Program Files on Windows."""
    def refuse(*args, **kwargs):
        raise AssertionError("Save File asked where")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", refuse)
    document = window.open_sample("hkust1")

    window.save_document()

    assert document.path.suffix == ".xtalproj"
    assert document.path.parent == document.entry.path
    assert str(samples.folder()) not in str(document.path)
    assert document.path.is_file()
    assert not document.modified


def test_last_directory_never_moves_into_the_application(window,
                                                         tmp_path):
    """The copy is what is opened, so the directory that is remembered
    is the workspace and never resources/samples."""
    window.open_sample("hkust1")

    assert str(samples.folder()) not in window.settings.last_directory
    assert window.settings.recent_files() != []


def test_the_same_sample_twice_returns_to_the_one_entry(window):
    """The bytes are compared, so the second click is the same file
    and the same tab -- not a second copy of it."""
    first = window.open_sample("hkust1")
    second = window.open_sample("hkust1")

    assert first is second
    assert window.tabs.count() == 1
    assert len(window.workspace.entries()) == 1


def test_a_sample_opened_over_an_edited_copy_opens_the_clicked_one(
        window):
    """Same name, different bytes: what opens is what was clicked, and
    the work already in that entry is not written over."""
    first = window.open_sample("hkust1")
    first.path.write_text(first.path.read_text() + "\n# edited\n")

    second = window.open_sample("hkust1")

    assert second is not first
    assert second.entry.name == "HKUST-1-2"
    assert "# edited" in first.path.read_text()


def test_a_freshly_opened_sample_is_not_modified(window):
    """Closing it asks nothing, because nothing has been done to it."""
    document = window.open_sample("hkust1")

    assert not document.modified


def test_the_file_menu_offers_every_sample(window):
    """The submenu is asked which menu it is in, rather than the File
    menu being asked what is in it.  ``QAction.menu()`` is the obvious
    way to reach a submenu from the menu bar and it destroys the menu
    it hands back the moment the wrapper is collected -- which kills
    ``window.modules_menu`` on a checkout with none of this in it."""
    labels = [a.text() for a in window.sample_menu.actions()
              if not a.isSeparator()]
    groups = [group for group, _title in samples.GROUPS
              if group != samples.SHIPPED]
    submenus = [window.sample_group_menus[group] for group in groups]

    assert labels == [s.label for s in samples.in_group(samples.SHIPPED)
                      ] + [menu.title() for menu in submenus]
    for group, menu in zip(groups, submenus, strict=True):
        assert [a.text() for a in menu.actions()] == [
            s.label for s in samples.in_group(group)]
    assert window.sample_menu.isEnabled()
    assert window.sample_menu.parentWidget().title() == "&File"


def test_every_sample_has_an_action_of_its_own(window):
    """Named the way the run-app driver and a keyboard shortcut would
    have to type it."""
    for sample in samples.SAMPLES:
        name = f"sample_{sample.name}"
        assert name in window.actions_
        assert window.actions_[name].toolTip() == sample.description


def test_pressing_a_sample_entry_opens_it(window):
    """Through the QAction, which is what a menu click reaches."""
    window.actions_["sample_zif8"].trigger()

    assert window.tabs.count() == 1
    assert window.current_document().entry.name == "ZIF-8"


def test_an_installation_without_the_samples_says_so(window, tmp_path,
                                                     monkeypatch):
    """resources/ is not package data, so a wheel install has none of
    them -- a supported state that gets a sentence, not twenty-three
    entries that each raise a dialog."""
    monkeypatch.setattr(samples, "folder", lambda: tmp_path / "nothing")
    menus.build_sample_menu(window)

    assert not window.sample_menu.isEnabled()
    assert window.sample_menu.toolTip() == samples.MISSING
    assert not window.actions_["sample_mof5"].isEnabled()


#: What each COD file must read as: the space group it was published
#: in, and the atoms that group makes of it.  UiO-66 and ZIF-8 carry
#: their disorder as deposited, so both halves of each split site are
#: counted, as are MOF-808's formate caps and water; MIL-101, MIL-100
#: and MIL-88B were refined with no hydrogens.
COD_EXPECTED = {
    "cod_mof5": ("Fm-3m", 7, 424),
    "cod_hkust1": ("Fm-3m", 6, 624),
    "cod_zif8": ("I-43m", 9, 348),
    "cod_uio66": ("Fm-3m", 13, 688),
    "cod_mil101": ("Fd-3m", 108, 16000),
    "cod_nu1000": ("P6/mmm", 26, 510),
    "cod_mil100": ("Fd-3m", 97, 13552),
    "cod_mof74": ("H-3", 9, 162),         # R-3, hexagonal axes
    "cod_pcn222": ("P6/mmm", 38, 690),
    "cod_mof808": ("Fd-3m", 25, 2960),
    "cod_mil53": ("Imcm", 7, 72),
    "cod_mil88b": ("P-62c", 15, 138),
    "cod_mnbtt": ("Pm-3m", 12, 303),
    "cod_euhotp": ("Fd-3m", 20, 2112),
    "cod_pbzmof1": ("Fd-3m", 24, 3488),
    "cod_alsocmof1": ("Pm-3n", 29, 1208),
}


def test_every_cod_sample_opens_in_its_published_space_group():
    """Read as the depositors wrote them: the asymmetric unit in its
    own group, no coincident atoms, and the cell the formula says.  A
    strip that took a symmetry loop with the reflections, or a reader
    that fell back to P1, changes all three."""
    from xtal.core import p1

    for sample in samples.in_group(samples.COD):
        group, n_sites, n_atoms = COD_EXPECTED[sample.name]
        structure = FORMATS.read(sample.path)

        assert structure.space_group.short_name == group, sample.label
        assert structure.n_sites == n_sites, sample.label
        assert p1.expand(structure).n_atoms == n_atoms, sample.label
        assert not structure.meta.get("warnings"), sample.label


def test_the_cod_samples_are_what_the_script_writes():
    """Stripped of the experiment and nothing else, byte for byte, so
    the files are the COD's and the script is how they came to be."""
    import importlib.util

    script = samples.folder().parent.parent / "scripts" / (
        "fetch_cod_samples.py")
    spec = importlib.util.spec_from_file_location("fetch_cod", script)
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)

    assert sorted(fetch.ENTRIES.values()) == sorted(
        s.file.removeprefix("cod/")
        for s in samples.in_group(samples.COD))
    for sample in samples.in_group(samples.COD):
        text = sample.path.read_text("utf-8")
        assert fetch.strip(text) == text, sample.label
        assert re.search(
            rf"^_cod_database_code\s+{sample.cod_id}$", text,
            re.MULTILINE), sample.label


def test_every_file_in_the_samples_folder_is_named_in_provenance():
    """A structure with no source written down is one nobody can say
    may be shipped.  Fails the moment a file is added without it."""
    folder = samples.folder()
    provenance = (folder / "PROVENANCE.md").read_text("utf-8")
    files = sorted(p.relative_to(folder).as_posix()
                   for p in folder.rglob("*.cif"))

    unnamed = [f for f in files if f"`{f}`" not in provenance]

    assert len(files) == 42
    assert unnamed == []


def test_the_cod_samples_are_in_their_own_section_of_open_sample(window):
    """Two entries called MOF-5 a separator apart, with nothing to
    say which is the deposited one, is what the submenu is for.  And
    the workspace entry carries the number, so the two never share a
    folder name told apart only by a -2."""
    cod = window.sample_group_menus[samples.COD]

    assert cod.title() == "From the &COD"
    assert "sample_cod_mof5" in window.actions_
    assert window.actions_["sample_cod_mof5"] in cod.actions()
    assert window.actions_["sample_mof5"] not in cod.actions()

    document = window.open_sample("cod_mof5")

    assert document.entry.name == "MOF-5_COD_1516287"
    assert document.path.name == "MOF-5.cif"


def test_every_cod_framework_has_a_prepared_copy_beside_it():
    """Two groups that drift apart -- a COD sample with no prepared
    copy, or a prepared one whose original went -- leave the menu
    offering a model nobody can trace to its crystal."""
    cod = {s.cod_id for s in samples.in_group(samples.COD)}
    prepared = {s.cod_id for s in samples.in_group(samples.PREPARED)}
    assert prepared == cod
    assert samples.get("prep_mil101").entry_name == \
        "MIL-101(Cr) prepared COD 4000663"


def test_a_prepared_sample_needs_nothing_more_to_be_simulated():
    """Whole atoms, nothing the preparation would still change, and in
    P1 -- which is what ordering the disorder leaves."""
    from xtal.core import prepare

    for sample in samples.in_group(samples.PREPARED):
        structure = FORMATS.read(sample.path)
        assert all(site.occupancy == 1.0 for site in structure.sites)
        assert not prepare.diagnose(structure), sample.label


@pytest.mark.slow
def test_the_prepared_samples_are_what_the_script_writes():
    """Coordinate for coordinate where nothing was relaxed, atom for
    atom where something was: a change to the preparation that would
    make a different model fails here until the files are written
    again."""
    import importlib.util

    script = samples.folder().parent.parent / "scripts" / (
        "prepare_samples.py")
    spec = importlib.util.spec_from_file_location("prepare_samples",
                                                  script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0
