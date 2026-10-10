"""The workflow's Linux half: the test row, the AppImage and its release.

Read as YAML rather than grepped, because a step that is there but on
the wrong job, or a row that names the wrong spec, greps exactly like a
right one.  A real build is the bundle job itself; this is what keeps
the pieces it needs from being edited away without anybody noticing
until a tag.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _step(job: dict, name: str) -> dict:
    (step,) = [s for s in job["steps"] if s.get("name") == name]
    return step


def test_the_workflow_is_yaml(workflow):
    """A tab or a stray colon in a `run:` block and GitHub refuses the
    whole file -- every job, not the one that was edited -- with an
    error on the Actions page and nothing on the pull request."""
    assert {"test", "lint", "build", "release"} <= set(workflow["jobs"])


def test_the_test_matrix_runs_linux_again(workflow):
    """Linux left the matrix because nothing was released for it, and
    an AppImage is now; without the row the suite's Linux-only paths
    (the AppImage launcher, the desktop entry) run nowhere."""
    rows = workflow["jobs"]["test"]["strategy"]["matrix"]["include"]

    assert {"os": "ubuntu-latest", "python": "3.12"} in rows


def test_the_linux_bundle_is_built_on_the_glibc_floor(workflow):
    """An AppImage runs on the glibc it was built against and anything
    newer, never older: built on ubuntu-latest it would refuse to start
    on 22.04 with `GLIBC_2.38 not found`, and say so only there."""
    rows = workflow["jobs"]["build"]["strategy"]["matrix"]["include"]
    (linux,) = [row for row in rows if row["label"] == "linux-x86_64"]

    assert linux["os"] == "ubuntu-22.04"
    assert linux["spec"] == "packaging/linux.spec"


def test_the_linux_selftest_runs_the_appimage_and_reads_its_output(
        workflow):
    """The AppImage is what a user downloads; the folder it was packed
    from has a different launcher path, so a selftest of the folder
    says nothing about `launcher_command()` answering from the file.
    And the exit code alone is what let a Windows run go green having
    died inside the 3D view, so its output is read back."""
    build = workflow["jobs"]["build"]
    run = _step(build, "Selftest (Linux)")["run"]

    assert ".AppImage" in run
    assert "--selftest" in run
    assert "selftest passed" in run
    assert "xtal launcher" in run
    assert "APPIMAGE_EXTRACT_AND_RUN=1" in run or (
        _step(build, "Selftest (Linux)").get("env", {})
        .get("APPIMAGE_EXTRACT_AND_RUN") == "1")


def test_appimagetool_is_checked_against_a_pinned_checksum(workflow):
    """A release asset can be replaced under the same URL, and
    appimagetool's `continuous` tag is replaced weekly; the checksum is
    what makes the tool that packs a release the one that was looked
    at, and a download that changed fails the job instead."""
    run = _step(workflow["jobs"]["build"], "appimagetool")["run"]

    assert "sha256sum -c" in run
    assert re.search(r"\b[0-9a-f]{64}\b", run)
    assert "appimagetool/releases/download" in run


def test_the_appimage_is_built_and_uploaded_on_every_bundle_run(
        workflow):
    """The selftest runs the AppImage, so it is made on a plain push as
    well as a tag, and `if-no-files-found: error` then asks whether it
    was."""
    build = workflow["jobs"]["build"]
    names = [s.get("name") for s in build["steps"]]
    packing = _step(build, "AppImage (Linux)")
    (upload,) = [s for s in build["steps"]
                 if s.get("uses", "").startswith(
                     "actions/upload-artifact")]

    assert "refs/tags" not in packing.get("if", "")
    assert (names.index("Build") < names.index("Strip (Linux)")
            < names.index("appimagetool") < names.index("AppImage (Linux)")
            < names.index("Selftest (Linux)"))
    assert "*.AppImage" in upload["with"]["path"].split()
    assert upload["with"]["if-no-files-found"] == "error"


def test_every_linux_step_runs_on_linux_only(workflow):
    """The bundle job's matrix is three operating systems; a Linux step
    without its `if:` runs `sudo apt-get` on macOS and bash's arrays
    under Windows' shell, and fails a bundle that was fine."""
    build = workflow["jobs"]["build"]

    for name in ("Qt's system libraries (Linux bundle)",
                 "Strip (Linux)", "appimagetool", "AppImage (Linux)",
                 "Selftest (Linux)"):
        assert _step(build, name).get("if") == "runner.os == 'Linux'", (
            name)


def test_appimagetool_is_handed_a_pinned_runtime(workflow):
    """appimagetool downloads the type2 runtime at pack time unless it
    is given one, and that runtime is the start of every AppImage
    shipped -- pinning the tool alone leaves the part a user runs
    first unpinned."""
    build = workflow["jobs"]["build"]
    fetch = _step(build, "appimagetool")["run"]
    packing = _step(build, "AppImage (Linux)")["run"]

    assert "type2-runtime/releases/download" in fetch
    assert len(re.findall(r"\b[0-9a-f]{64}\b", fetch)) == 2
    assert fetch.count("sha256sum -c") == 2
    assert "--runtime" in packing


def test_the_release_attaches_the_appimage(workflow):
    """The draft release is assembled from the artifacts by pattern;
    without one for the AppImage it is built, uploaded and then left
    out of the release beside the DMG and setup.exe."""
    release = _step(workflow["jobs"]["release"], "Release")

    assert "artifacts/**/*.AppImage" in release["with"]["files"].split()
