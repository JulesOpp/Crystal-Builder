"""Help ▸ Send Feedback, and the crash box's way into it.

The form is built and driven here and never ``exec``'d (conftest makes
that raise), and ``openUrl`` is patched in every test that would
reach it, so the suite never opens a mail client.
"""

from urllib.parse import parse_qs, urlsplit

import pytest

from xtalapp import applog, feedback


@pytest.fixture
def log(tmp_path):
    applog.reset()
    path = applog.setup(tmp_path)
    path.write_text("INFO opened MOF-5.cif\n", encoding="utf-8")
    yield path
    applog.reset()


@pytest.fixture
def no_log():
    applog.reset()
    yield
    applog.reset()


@pytest.fixture
def window(qtbot, tmp_path):
    from PySide6.QtWidgets import QWidget

    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    class Stub(QWidget):
        def __init__(self, document, parent=None):
            super().__init__(parent)
            self.document = document

    settings = AppSettings("CrystalBuilderTest", f"Fb{tmp_path.name}")
    settings.clear_window()
    win = MainWindow(viewport_factory=Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def dialog(qtbot, **kwargs):
    from xtalapp.dialogs.feedback import FeedbackDialog
    form = FeedbackDialog(**kwargs)
    qtbot.addWidget(form)
    return form


def test_the_help_menu_offers_feedback_after_the_log(window):
    help_menu = next(action.menu() for action in
                     window.menuBar().actions()
                     if action.text() == "&Help")
    names = [action.objectName() or action.text()
             for action in help_menu.actions()]
    keys = {window.actions_[key]: key
            for key in ("show_log", "send_feedback", "about")}
    order = [keys[a] for a in help_menu.actions() if a in keys]
    assert order == ["show_log", "send_feedback", "about"], names


def test_a_bug_includes_the_log_by_default_and_a_feature_does_not(
        qtbot, log):
    form = dialog(qtbot)
    assert form.include_log.isChecked()
    assert "opened MOF-5.cif" in form.preview.toPlainText()

    form.kind.setCurrentText(feedback.FEATURE)
    assert not form.include_log.isChecked()
    assert "opened MOF-5.cif" not in form.preview.toPlainText()


def test_a_tick_changed_by_hand_survives_a_change_of_kind(qtbot, log):
    """Somebody who asked for the log with a UI suggestion meant it."""
    form = dialog(qtbot, kind=feedback.UI)
    form.include_log.setChecked(True)
    form.kind.setCurrentText(feedback.FEATURE)
    assert form.include_log.isChecked()


def test_the_log_box_is_disabled_when_nothing_is_logged(qtbot, no_log):
    """A window built directly has never had a log; a tick that adds
    nothing would be a promise the email does not keep."""
    form = dialog(qtbot)
    assert not form.include_log.isEnabled()
    assert not form.include_log.isChecked()


def test_the_preview_is_what_the_mail_client_receives(qtbot, log,
                                                      monkeypatch):
    from PySide6.QtGui import QDesktopServices
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url) or True)
    from xtalapp.dialogs.feedback import open_report

    form = dialog(qtbot)
    form.text.setPlainText("It closed when I pressed Optimise")
    message = open_report(form.report())

    url = bytes(opened[0].toEncoded()).decode()
    body = parse_qs(urlsplit(url).query)["body"][0]
    assert body == form.preview.toPlainText()
    assert url.startswith("mailto:juliuso@princeton.edu?")
    assert "mail client" in message


def test_when_no_mail_client_opens_the_report_is_on_the_clipboard(
        qtbot, no_log, monkeypatch):
    """Otherwise what was written is lost to a button that did
    nothing."""
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: False)
    from xtalapp.dialogs.feedback import open_report

    form = dialog(qtbot, kind=feedback.UI)
    form.text.setPlainText("The Style panel is too wide")
    message = open_report(form.report())

    pasted = QApplication.clipboard().text()
    assert pasted.startswith("To: juliuso@princeton.edu")
    assert "The Style panel is too wide" in pasted
    assert "clipboard" in message


def test_nothing_written_is_nothing_to_send(qtbot, no_log):
    form = dialog(qtbot, kind=feedback.FEATURE)
    assert not form.send.isEnabled()
    form.text.setPlainText("Colour by charge")
    assert form.send.isEnabled()


def test_the_menu_entry_says_what_happened_in_the_status_bar(
        window, monkeypatch):
    from xtalapp.dialogs import feedback as dialogs_feedback
    monkeypatch.setattr(dialogs_feedback.FeedbackDialog, "ask",
                        classmethod(lambda cls, parent: "ready"))
    window.actions_["send_feedback"].trigger()
    assert window.statusBar().currentMessage() == "ready"


def test_the_crash_box_sends_its_traceback_as_a_bug(qapp, log,
                                                    monkeypatch):
    """The moment of a crash is when a report is most likely to be
    sent, and its traceback is the report."""
    from PySide6.QtWidgets import QMessageBox

    from xtalapp.dialogs import feedback as dialogs_feedback

    def exec_(box):
        button = next(b for b in box.buttons()
                      if b.text() == "Send feedback...")
        button.click()
        return 0

    asked = []
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(applog, "_told", set())
    monkeypatch.setattr(
        dialogs_feedback.FeedbackDialog, "ask",
        classmethod(lambda cls, parent, details="": asked.append(details)))

    try:
        raise ZeroDivisionError("redraw")
    except ZeroDivisionError as exc:
        applog._tell_somebody(type(exc), exc, exc.__traceback__)

    assert len(asked) == 1
    assert "ZeroDivisionError: redraw" in asked[0]
