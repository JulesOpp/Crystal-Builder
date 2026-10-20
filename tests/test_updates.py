"""Help ▸ Check for Updates decides from GitHub's latest release.

Each of these is a way the answer could be wrong with nobody
noticing: a developer build offered a "newer" release that is older
than it, 1.10 read as older than 1.9, the link pointing nowhere, or a
reply GitHub sends when rate limited raising out of the slot that
reads it.
"""

import json

from xtalapp import updates

PAGE = "https://github.com/JulesOpp/Crystal-Builder/releases/tag/v1.1.0"


def release(tag="v1.1.0", url=PAGE, **extra):
    return {"tag_name": tag, "html_url": url, "draft": False,
            "prerelease": False, **extra}


def test_an_older_build_is_told_a_newer_release_exists():
    verdict = updates.judge("1.0.0", release())
    assert verdict.state == updates.NEWER_AVAILABLE
    assert verdict.latest == "1.1.0"
    assert "1.1.0" in verdict.message()
    assert "1.0.0" in verdict.message()


def test_the_latest_release_itself_is_current():
    verdict = updates.judge("1.1.0", release())
    assert verdict.state == updates.CURRENT


def test_a_dev_build_past_the_release_is_not_offered_a_downgrade():
    """setuptools_scm numbers a checkout after v1.0.0 as 1.0.1.devN;
    reading only "1.0.1" or only "dev" would get it wrong one way or
    the other."""
    verdict = updates.judge("1.0.1.dev95+ge5e6ae961",
                            release("v1.0.0"))
    assert verdict.state == updates.AHEAD


def test_a_dev_build_of_the_release_number_is_behind_it():
    verdict = updates.judge("1.0.1.dev3", release("v1.0.1"))
    assert verdict.state == updates.NEWER_AVAILABLE


def test_minor_versions_compare_as_numbers():
    assert updates.judge("1.9.0", release("v1.10.0")).state == \
        updates.NEWER_AVAILABLE
    assert updates.judge("1.10.0", release("v1.9.0")).state == \
        updates.AHEAD


def test_a_two_part_tag_is_its_zero_patch_release():
    assert updates.judge("2.0.0", release("v2.0")).state == \
        updates.CURRENT


def test_the_reply_may_be_the_raw_bytes_of_the_response():
    raw = json.dumps(release()).encode()
    assert updates.judge("1.0.0", raw).state == updates.NEWER_AVAILABLE


def test_a_malformed_reply_is_unknown_not_an_exception():
    for reply in (b"", b"<html>", b"[1, 2]", {"tag_name": "nightly"},
                  {"message": "API rate limit exceeded"}):
        verdict = updates.judge("1.0.0", reply)
        assert verdict.state == updates.UNKNOWN
        assert verdict.message()


def test_github_s_own_complaint_is_the_reason_given():
    verdict = updates.judge("1.0.0",
                            {"message": "API rate limit exceeded"})
    assert "rate limit" in verdict.message()


def test_a_draft_or_prerelease_is_never_offered():
    for flag in ("draft", "prerelease"):
        verdict = updates.judge("1.0.0", release(**{flag: True}))
        assert verdict.state == updates.UNKNOWN


def test_the_link_is_the_release_page_falling_back_to_latest():
    assert updates.judge("1.0.0", release()).url == PAGE
    reply = release()
    del reply["html_url"]
    assert updates.judge("1.0.0", reply).url == updates.RELEASES_PAGE
    assert updates.judge("1.0.0", b"").url == updates.RELEASES_PAGE


def test_an_unreadable_running_version_is_unknown():
    verdict = updates.judge("unknown", release())
    assert verdict.state == updates.UNKNOWN
