"""
xtalapp.dialogs.feedback
========================
Help ▸ Send Feedback..., and the crash box's *Send feedback...*: a
bug, a feature or a UI suggestion, written here and sent by the
person's own mail client.

**The preview is the email.**  What the mail client receives is
:attr:`xtalapp.feedback.Report.body`, and that is what the box below
the message shows, trimmed exactly as the link will be -- the log
names the files a person opened, and they should see it before it
goes.  Nothing is sent from here; Open in mail starts a draft.

The log goes with a bug and not, unless asked, with a suggestion: it
is a hundred lines nobody needs to read about a colour.  Once the
tick has been changed by hand, choosing another kind leaves it alone.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from xtalapp import applog, feedback
from xtalapp.dialogs.answered import answered
from xtalapp.widgets.tone import HINT, WARNING, set_tone


def open_report(report: feedback.Report) -> str:
    """Hand ``report`` to the mail client, or put it on the clipboard.

    Returns what to tell the person.  ``openUrl`` is False where no
    mail client is set up -- common on Windows and on a new Mac --
    and a button that did nothing would lose what they wrote.
    """
    url = QUrl.fromEncoded(report.url.encode("ascii"))
    if QDesktopServices.openUrl(url):
        return "A feedback email is ready in your mail client."
    QApplication.clipboard().setText(report.as_text())
    return (f"No mail client opened, so the report is on the "
            f"clipboard: paste it into an email to {feedback.ADDRESS}.")


class FeedbackDialog(QDialog):
    """What kind, what happened, and whether the log goes with it."""

    def __init__(self, parent=None, kind: str = feedback.BUG,
                 details: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Send Feedback")
        self.details = details
        self.log = applog.log_file()
        self.faults = (None if self.log is None
                       else self.log.parent / applog.FAULTS)
        self._log_chosen = False

        intro = QLabel(
            "A bug, a feature you would like, or something in the "
            "window that could be better.  This opens an email in "
            "your own mail client; nothing is sent until you send "
            "it there.")
        intro.setWordWrap(True)
        set_tone(intro, HINT)

        self.kind = QComboBox()
        self.kind.addItems(feedback.KINDS)
        self.kind.setCurrentText(kind)
        self.kind.currentTextChanged.connect(self._kind_changed)

        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(
            "What happened, or what you would like.  For a bug, what "
            "you did just before helps most.")
        self.text.setMinimumHeight(90)
        self.text.textChanged.connect(self._preview)

        self.include_log = QCheckBox("Include the end of the log")
        self.include_log.setChecked(kind == feedback.BUG)
        if self.log is None:
            self.include_log.setChecked(False)
            self.include_log.setEnabled(False)
            self.include_log.setToolTip(
                "This window was not started by the application, so "
                "nothing is being logged to a file.")
        else:
            self.include_log.setToolTip(
                f"The last {feedback.LOG_LINES} lines of "
                f"{applog.FILE}, with your home folder written ~, and "
                "a hard crash's stack if there was one this week.")
        self.include_log.toggled.connect(self._log_toggled)

        form = QFormLayout()
        form.addRow("Kind:", self.kind)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFontDatabase.systemFont(
            QFontDatabase.FixedFont))
        self.preview.setMinimumHeight(120)

        self.note = QLabel()
        self.note.setWordWrap(True)

        address = QLabel(f"To: {feedback.ADDRESS}")
        address.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.send = self.buttons.addButton(
            "Open in Mail", QDialogButtonBox.AcceptRole)
        self.copy = self.buttons.addButton(
            "Copy Report", QDialogButtonBox.ActionRole)
        self.copy.setToolTip(
            "Put the subject and the body on the clipboard, to paste "
            "into an email yourself")
        self.copy.clicked.connect(self.copy_report)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.include_log)
        layout.addWidget(QLabel("The email:"))
        layout.addWidget(self.preview, 2)
        layout.addWidget(self.note)
        layout.addWidget(address)
        layout.addWidget(self.buttons)
        self.resize(560, 560)
        self._preview()

    # -- the report ----------------------------------------------------

    def report(self) -> feedback.Report:
        return feedback.compose(
            self.kind.currentText(), self.text.toPlainText(),
            include_log=self.include_log.isChecked(), log=self.log,
            faults=self.faults, details=self.details)

    def copy_report(self) -> None:
        QApplication.clipboard().setText(self.report().as_text())
        self.note.setText("Copied.  Paste it into an email to "
                          f"{feedback.ADDRESS}.")
        set_tone(self.note, HINT)
        self.note.setVisible(True)

    # -- keeping it current --------------------------------------------

    def _kind_changed(self, kind: str) -> None:
        if not self._log_chosen and self.include_log.isEnabled():
            self.include_log.blockSignals(True)
            self.include_log.setChecked(kind == feedback.BUG)
            self.include_log.blockSignals(False)
        self._preview()

    def _log_toggled(self, _on: bool) -> None:
        self._log_chosen = True
        self._preview()

    def _preview(self) -> None:
        report = self.report()
        self.preview.setPlainText(report.body)
        self.send.setEnabled(bool(self.text.toPlainText().strip()
                                  or self.details))
        if report.too_long:
            self.note.setText(
                "This is longer than a mail link can carry here and "
                "may arrive cut short.  Copy Report and paste it "
                "instead.")
            set_tone(self.note, WARNING)
        elif report.dropped:
            self.note.setText(
                f"{report.dropped} older lines were left out so the "
                "email fits in a mail link.")
            set_tone(self.note, HINT)
        else:
            self.note.setText("")
            set_tone(self.note, HINT)
        self.note.setVisible(bool(self.note.text()))

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, parent=None, kind: str = feedback.BUG,
            details: str = "") -> str | None:
        """Open the report in the mail client; what to tell the
        person, or ``None`` if they cancelled."""
        with answered(cls(parent, kind, details)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return open_report(dialog.report())
