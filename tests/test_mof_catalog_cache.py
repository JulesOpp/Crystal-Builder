"""A catalogue reads a net or a block from disk once per process.

Opening the MOF builder makes a fresh :class:`~xtal.mof.Catalog`, and a
fresh catalogue used to read every one of PORMAKE's 2599 nets and 879
blocks again -- about 3300 files a time.  On a quiet machine that is
half a second; on one short of memory, where the files have fallen out
of the cache and every read queues behind the swap, it was 95 seconds
a dialog, and the test suite opens that dialog dozens of times.

So what a file parses to is kept, keyed by the file's path, size and
modification time, and a later catalogue is handed a copy of it.  A
file that is edited, added or removed is seen by the next catalogue
exactly as before.
"""

import os
import shutil

import pytest

from xtal.mof import catalog as cat
from xtal.mof.catalog import Catalog

PORMAKE = cat.database_root()

pytestmark = pytest.mark.skipif(PORMAKE is None,
                                reason="needs the vendored database")


@pytest.fixture
def folders(tmp_path):
    """Two nets and two blocks of PORMAKE's own, in folders of a test's
    own so that it can edit them."""
    nets, blocks = tmp_path / "nets", tmp_path / "bbs"
    nets.mkdir()
    blocks.mkdir()
    for name in ("pcu", "dia"):
        shutil.copy(PORMAKE / "topologies" / f"{name}.cgd", nets)
    for name in ("N16", "E14"):
        shutil.copy(PORMAKE / "bbs" / f"{name}.xyz", blocks)
    return nets, blocks


@pytest.fixture
def reads(monkeypatch):
    """How many files the two readers were asked to parse."""
    count = {"nets": 0, "blocks": 0}
    read_topology, read_block = cat.read_topology, cat.read_building_block

    def topology(path):
        count["nets"] += 1
        return read_topology(path)

    def block(path):
        count["blocks"] += 1
        return read_block(path)

    monkeypatch.setattr(cat, "read_topology", topology)
    monkeypatch.setattr(cat, "read_building_block", block)
    return count


def test_a_second_catalogue_parses_no_file_the_first_one_read(
        folders, reads):
    nets, blocks = folders
    first = Catalog((nets,), (blocks,))
    assert {t.name for t in first.topologies()} == {"pcu", "dia"}
    assert {b.name for b in first.building_blocks()} == {"N16", "E14"}
    assert reads == {"nets": 2, "blocks": 2}

    second = Catalog((nets,), (blocks,))

    assert {t.name for t in second.topologies()} == {"pcu", "dia"}
    assert {b.name for b in second.building_blocks()} == {"N16", "E14"}
    assert reads == {"nets": 2, "blocks": 2}


def test_an_edited_file_is_read_again(folders):
    nets, blocks = folders
    before = Catalog((nets,), (blocks,)).topology("pcu")
    path = nets / "pcu.cgd"
    text = path.read_text(encoding="utf-8")
    # A different space group, and a later modification time, as an
    # editor saving the file would leave it.
    path.write_text(text.replace(before.group, "P1", 1),
                    encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))

    after = Catalog((nets,), (blocks,)).topology("pcu")

    assert before.group != "P1"
    assert after.group == "P1"


def test_a_file_added_to_the_folder_is_found(folders):
    nets, blocks = folders
    assert Catalog((nets,), (blocks,)).building_blocks()
    shutil.copy(PORMAKE / "bbs" / "N59.xyz", blocks)

    names = {b.name for b in Catalog((nets,), (blocks,)).building_blocks()}

    assert "N59" in names


def test_a_file_removed_from_the_folder_is_gone(folders):
    nets, blocks = folders
    assert "dia" in {t.name for t in Catalog((nets,), (blocks,)).topologies()}
    (nets / "dia.cgd").unlink()

    names = {t.name for t in Catalog((nets,), (blocks,)).topologies()}

    assert names == {"pcu"}


def test_each_catalogue_has_its_own_copy(folders):
    """What one catalogue works out about a net, or does to a block's
    coordinates, is its own: the next catalogue starts from the file."""
    nets, blocks = folders
    first = Catalog((nets,), (blocks,))
    first.topology("pcu")._cache["layer"] = "worked out here"
    first.building_block("N16").positions[0, 0] += 100.0

    second = Catalog((nets,), (blocks,))

    assert "layer" not in second.topology("pcu")._cache
    assert second.building_block("N16").positions[0, 0] == pytest.approx(
        first.building_block("N16").positions[0, 0] - 100.0)


def test_a_file_that_will_not_read_is_reported_every_time(folders):
    """A failure is not remembered as a success, nor forgotten."""
    nets, blocks = folders
    (nets / "broken.cgd").write_text("CRYSTAL\nEND\n", encoding="utf-8")

    for _ in range(2):
        catalogue = Catalog((nets,), (blocks,))
        assert any("broken.cgd" in f for f in catalogue.failures)
        assert {t.name for t in catalogue.topologies()} == {"pcu", "dia"}
