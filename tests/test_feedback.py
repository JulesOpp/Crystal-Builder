"""Help ▸ Send Feedback composes a report a mail client can take.

A ``mailto:`` link carries no attachment and, on Windows, nothing
past about 2 000 characters, so the log goes in the body and is
trimmed to fit.  Each of these is a way the email that arrives could
be wrong with nobody noticing: no version in it, an account name in
it, a body cut off mid-line, or the person's own words trimmed to
make room for a log.
"""

import os
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from xtalapp import feedback

ENV = "Crystal Builder 9.9 (from source)\nPython 3.x\nTestOS"


def fields(url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    return (unquote(parts.path), query["subject"][0], query["body"][0])


def write_log(tmp_path, lines):
    path = tmp_path / "crystal-builder.log"
    path.write_text("".join(f"{line}\n" for line in lines),
                    encoding="utf-8")
    return path


def test_the_link_is_addressed_to_the_feedback_address():
    report = feedback.compose(feedback.FEATURE, "Colour by charge",
                              env=ENV)
    address, subject, body = fields(report.url)
    assert address == "juliuso@princeton.edu"
    assert subject == report.subject
    assert body == report.body


def test_the_subject_names_the_kind_and_the_first_line():
    subject = feedback.subject(feedback.UI, "\nThe Style panel\nis wide")
    assert subject == "[Crystal Builder] UI suggestion: The Style panel"


def test_a_long_first_line_is_cut_in_the_subject_not_the_body():
    text = "word " * 40
    report = feedback.compose(feedback.BUG, text, env=ENV)
    assert len(report.subject) <= feedback.SUBJECT_LENGTH
    assert report.subject.endswith("...")
    assert text.strip() in report.body


def test_the_report_names_the_version_and_the_platform():
    """Without it, the first reply to every bug is "which version?"."""
    from xtal import __version__
    env = feedback.environment()
    assert __version__ in env
    assert "Python" in env and "PySide6" in env
    report = feedback.compose(feedback.BUG, "x")
    assert env in report.body


def test_the_log_is_left_out_unless_asked_for(tmp_path):
    log = write_log(tmp_path, ["INFO started"])
    report = feedback.compose(feedback.FEATURE, "x", log=log, env=ENV)
    assert "started" not in report.body


def test_the_log_tail_hides_the_home_folder(tmp_path):
    """The log names every file opened, and the home folder is the
    account's name."""
    home = str(Path.home())
    log = write_log(tmp_path, [f"INFO opened {home}/MOFs/MOF-5.cif"])
    report = feedback.compose(feedback.BUG, "x", include_log=True,
                              log=log, env=ENV)
    assert "~/MOFs/MOF-5.cif" in report.body
    assert home not in report.body


def test_only_the_end_of_a_long_log_is_offered(tmp_path):
    log = write_log(tmp_path, [f"line {i}" for i in range(1000)])
    tail = feedback.log_tail(log)
    assert len(tail) == feedback.LOG_LINES
    assert tail[-1] == "line 999"


def test_a_long_log_is_trimmed_from_its_oldest_line_to_fit_the_budget(
        tmp_path):
    """Outlook cuts a link near 2 000 characters and says nothing; a
    body trimmed here at least ends where the log does."""
    log = write_log(tmp_path, [f"INFO line {i:04d} " + "x" * 30
                               for i in range(400)])
    report = feedback.compose(feedback.BUG, "It closed", include_log=True,
                              log=log, env=ENV, limit=1900)
    assert len(report.url) <= 1900
    assert report.dropped > 0 and not report.too_long
    assert "INFO line 0399" in report.body
    assert "INFO line 0250" not in report.body


def test_the_persons_own_text_is_never_trimmed(tmp_path):
    log = write_log(tmp_path, ["INFO started"] * 50)
    text = "A long account of what happened. " * 80
    report = feedback.compose(feedback.BUG, text, include_log=True,
                              log=log, env=ENV, limit=1900)
    assert text.strip() in report.body
    assert report.too_long
    assert "started" not in report.body


def test_a_traceback_keeps_the_line_naming_the_exception(tmp_path):
    details = "\n".join(
        ["Traceback (most recent call last):"]
        + [f'  File "x.py", line {i}, in f\n    f()' for i in range(80)]
        + ["ZeroDivisionError: redraw"])
    report = feedback.compose(feedback.BUG, "crash", details=details,
                              env=ENV, limit=1900)
    assert len(report.url) <= 1900
    assert "Traceback (most recent call last):" in report.body
    assert "ZeroDivisionError: redraw" in report.body


def test_without_a_log_the_report_says_none_was_kept():
    report = feedback.compose(feedback.BUG, "x", include_log=True,
                              log=None, env=ENV)
    assert "No log" in report.body


def test_a_recent_hard_crash_is_included_and_an_old_one_is_not(tmp_path):
    log = write_log(tmp_path, ["INFO started"])
    faults = tmp_path / "faults.log"
    faults.write_text(
        "Fatal Python error: Aborted\n\nThread 0x1:\n  File \"a.py\"\n"
        "Fatal Python error: Segmentation fault\n\nCurrent thread 0x2:\n"
        '  File "vtk_scene.py", line 12 in render\n', encoding="utf-8")
    report = feedback.compose(feedback.BUG, "x", include_log=True,
                              log=log, faults=faults, env=ENV)
    assert "Segmentation fault" in report.body
    assert "Aborted" not in report.body

    old = time.time() - feedback.FAULT_AGE - 60
    os.utime(faults, (old, old))
    report = feedback.compose(feedback.BUG, "x", include_log=True,
                              log=log, faults=faults, env=ENV)
    assert "Segmentation fault" not in report.body


def test_the_clipboard_copy_says_where_to_send_it():
    report = feedback.compose(feedback.UI, "x", env=ENV)
    assert report.as_text().startswith("To: juliuso@princeton.edu\n")
