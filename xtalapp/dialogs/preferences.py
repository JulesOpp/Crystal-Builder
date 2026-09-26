"""
xtalapp.dialogs.preferences
===========================
Everything the application remembers between sessions, in one window.

Settings this application already had could be reached from nowhere
at all: the default workspace folder was hard-coded, and the default
bond rules could only be set from a dialog that needs a structure
open.  A preference nobody can find is a constant with extra steps.
In a packaged build it is worse than that: there is no shell to export
an environment variable in, so for the external tools (a later page)
this dialog is the only way in at all.

**A list and a stack, not tabs.**  Five pages is where a tab bar
starts eliding its own labels; a list grows to a sixth without a
redesign, and it is what both platforms' own settings windows look
like.

**Applied live, and Close is the only button.**  Every value here is a
QSettings write plus at most a refresh, so there is nothing to roll
back and an OK/Cancel pair would imply a transaction that does not
exist.

**It talks to** :class:`~xtalapp.settings.AppSettings` **and nothing
else**, injected the way every other dialog takes what it works on, so
a test hands it a scratch domain instead of the developer's real
preferences.  The three settings that have to reach further than the
next session leave as signals -- the recent list has to be rebuilt in
the File menu, the layout is the window's own, and a program's path
has to reach the Modules menu and the run panels.
"""

from __future__ import annotations

import shutil
import tempfile

from PySide6.QtCore import QProcess, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from xtal.core import bonding
from xtal.modules import probe as probes
from xtalapp import external, extras
from xtalapp.dialogs.bond_rules import BondRulesDialog
from xtalapp.viewport import styles
from xtalapp.viewport.view_settings import (
    BACKGROUNDS,
    FOLLOW_THE_SYSTEM,
)
from xtalapp.widgets.links import SourceLinks
from xtalapp.widgets.tone import HINT, WARNING, set_tone


def _hint(text: str) -> QLabel:
    """A sentence under a control, in the application's own voice.

    Every setting on these pages is one somebody has to decide about
    without being able to see what it does, so each gets a line saying
    what happens rather than a name and a checkbox.
    """
    label = QLabel(text)
    label.setWordWrap(True)
    set_tone(label, HINT)
    # A wrapped label's height depends on the width it is given, and a
    # layout that does not ask draws the second line over whatever is
    # under it.  Minimum vertical policy is what makes the layout ask.
    policy = label.sizePolicy()
    policy.setVerticalPolicy(QSizePolicy.Policy.Minimum)
    policy.setHeightForWidth(True)
    label.setSizePolicy(policy)
    return label


class GeneralPage(QWidget):
    """What the application does on its own: start, remember, forget."""

    TITLE = "General"

    #: The recent list was emptied; the File menu shows it.
    recentCleared = Signal()
    #: The saved window layout should be thrown away and rebuilt.  The
    #: window owns that -- it is the same operation as
    #: ``Window > Reset layout`` and is that method, not a copy of it.
    layoutReset = Signal()
    #: How often unsaved tabs are autosaved changed; the window's
    #: timer is restarted from it.
    autosaveChanged = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        layout = QVBoxLayout(self)
        layout.addWidget(self._saving_box())
        layout.addWidget(self._workspace_box())
        layout.addWidget(self._forget_box())
        layout.addStretch(1)

    # -- the boxes -----------------------------------------------------

    def _saving_box(self) -> QGroupBox:
        box = QGroupBox("Saving")
        outer = QVBoxLayout(box)
        self.confirm_overwrite = QCheckBox(
            "Ask before Save File writes over an existing file")
        self.confirm_overwrite.setChecked(
            self.settings.confirm_overwrite)
        self.confirm_overwrite.toggled.connect(
            lambda on: setattr(self.settings, "confirm_overwrite", on))
        outer.addWidget(self.confirm_overwrite)
        outer.addWidget(_hint(
            "Off by default: Save File writes the session over the "
            "file the tab is, and a box on every Ctrl+S is one "
            "nobody reads by the third time.  A structure opened as "
            "a CIF becomes the project beside it on its first save, "
            "and that CIF is left where it is."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Keep unsaved changes every"))
        self.autosave_minutes = QSpinBox()
        self.autosave_minutes.setRange(0, 60)
        self.autosave_minutes.setSuffix(" min")
        self.autosave_minutes.setSpecialValueText("never")
        self.autosave_minutes.setValue(
            round(self.settings.autosave_interval / 60))
        self.autosave_minutes.valueChanged.connect(self._set_autosave)
        row.addWidget(self.autosave_minutes)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addWidget(_hint(
            "Unsaved edits are copied into the workspace's .autosave "
            "folder, never over the file, and offered back the next "
            "time the file is opened."))
        return box

    def _set_autosave(self, minutes: int) -> None:
        self.settings.autosave_interval = minutes * 60
        self.autosaveChanged.emit()

    def _workspace_box(self) -> QGroupBox:
        box = QGroupBox("Workspaces")
        outer = QVBoxLayout(box)
        row = QHBoxLayout()
        self.workspace_root = QLineEdit(
            str(self.settings.default_workspace_root))
        # Shown from its start rather than its end: a long path
        # scrolled to the last characters reads as the wrong folder.
        self.workspace_root.setCursorPosition(0)
        self.workspace_root.textChanged.connect(self._root_typed)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_for_root)
        row.addWidget(QLabel("New workspaces in"))
        row.addWidget(self.workspace_root, 1)
        row.addWidget(browse)
        outer.addLayout(row)
        outer.addWidget(_hint(
            "Where New Workspace starts from.  Emptied, it goes back "
            "to your home folder."))
        return box

    def _forget_box(self) -> QGroupBox:
        box = QGroupBox("Remembered")
        outer = QVBoxLayout(box)

        row = QHBoxLayout()
        self.recent_label = QLabel()
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_recent)
        row.addWidget(self.recent_label, 1)
        row.addWidget(clear)
        outer.addLayout(row)

        row = QHBoxLayout()
        reset = QPushButton("Reset")
        reset.clicked.connect(lambda: self.layoutReset.emit())
        row.addWidget(QLabel("Window layout and dock positions"), 1)
        row.addWidget(reset)
        outer.addLayout(row)
        outer.addWidget(_hint(
            "A layout that once went wrong is otherwise permanent: "
            "the bad state is what gets saved on quit."))
        self._show_recent_count()
        return box

    # -- what the controls do ------------------------------------------

    def _root_typed(self, text: str) -> None:
        self.settings.default_workspace_root = text

    def _browse_for_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Folder for new workspaces",
            str(self.settings.default_workspace_root))
        if chosen:
            # Through the field, so the one write is the one the
            # textChanged above already does.
            self.workspace_root.setText(chosen)

    def _clear_recent(self) -> None:
        self.settings.clear_recent_files()
        self._show_recent_count()
        self.recentCleared.emit()

    def _show_recent_count(self) -> None:
        count = len(self.settings.recent_files())
        self.recent_label.setText(
            "No recent files" if not count else
            f"{count} recent file{'s' if count != 1 else ''}")


class ViewDefaultsPage(QWidget):
    """What a newly opened structure starts as.

    These two settings existed and were written from the View menu,
    which is the confusion this page fixes rather than moves.  Choosing
    *Ball and stick* there changed **this** document and silently
    recorded a default for the next one, and said nothing about the
    second half -- and, since nothing ever read the default back, the
    silent half did not even happen.  The View menu now acts on the
    open document alone and this page owns the default, which is
    applied to every document that does not arrive with a view of its
    own.
    """

    TITLE = "View defaults"

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        current = settings.default_view()

        layout = QVBoxLayout(self)
        box = QGroupBox("What a newly opened structure starts as")
        form = QFormLayout(box)

        self.style = QComboBox()
        for name in styles.names():
            style = styles.get(name)
            self.style.addItem(style.label, name)
            self.style.setItemData(self.style.count() - 1,
                                   style.description,
                                   Qt.ItemDataRole.ToolTipRole)
        self.style.setCurrentIndex(
            max(0, self.style.findData(current["style"])))
        self.style.currentIndexChanged.connect(
            lambda _i: self.settings.set_default_view(
                style=self.style.currentData()))

        # Each entry carries the *name* of a background and not the
        # colour: QComboBox.findData compares through QVariant, which
        # does not match a Python tuple against the one it stored --
        # it answers -1 for a colour that is in the list.
        self.background = QComboBox()
        self.background.addItem("Follow the system", FOLLOW_THE_SYSTEM)
        for name in BACKGROUNDS:
            self.background.addItem(name.capitalize(), name)
        self._follows_theme = current["background_follows_theme"]
        self._custom_background = tuple(current["background"])
        if self._custom_background not in BACKGROUNDS.values():
            # A colour chosen with View > Background > Custom, back
            # when that menu wrote the default as well.  Kept as an
            # entry rather than silently replaced by white.
            self.background.insertItem(0, "Custom", "custom")
        self.background.setCurrentIndex(
            max(0, self.background.findData(self._background_name())))
        self.background.currentIndexChanged.connect(
            lambda _i: self._background_chosen())

        form.addRow("Style", self.style)
        form.addRow("Background", self.background)
        form.addRow(_hint(
            "The View menu changes the document you are looking at "
            "and nothing else.  A project keeps the view it was saved "
            "with."))
        # No redraw rate here: the Force Field and DFTB+ panels each
        # have one beside the run it governs, and a second copy on this
        # page was the same setting in a place nobody looks mid-run.
        layout.addWidget(box)
        layout.addStretch(1)

    def _background_name(self) -> str:
        """Which entry the stored default is, by name."""
        if self._follows_theme:
            return FOLLOW_THE_SYSTEM
        for name, colour in BACKGROUNDS.items():
            if tuple(colour) == self._custom_background:
                return name
        return "custom"

    def _chosen_background(self) -> tuple:
        name = self.background.currentData()
        return tuple(BACKGROUNDS.get(name, self._custom_background))

    def _background_chosen(self) -> None:
        """Both halves of the answer: which colour, and whether it is
        a colour at all."""
        follows = self.background.currentData() == FOLLOW_THE_SYSTEM
        self._follows_theme = follows
        self.settings.set_default_view(
            background=self._chosen_background(),
            background_follows_theme=follows)


class BondingPage(QWidget):
    """When bonds are worked out again, and what they start from.

    Both settings existed and one of them could only be reached
    through a door that needs a structure open: the default rules are
    written by ticking a box in the Bond Rules dialog, which is
    disabled with no document.  So a user with no file open could not
    set what their files would open with -- which is the one moment
    they might want to.
    """

    TITLE = "Bonding"

    #: The same setting as ``Structure > Bonds follow the geometry``.
    #: It is one QAction and the window keeps the two in step, because
    #: the menu entry also has to apply it to the documents that are
    #: already open.
    followGeometryChanged = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        layout = QVBoxLayout(self)

        box = QGroupBox("When bonds are worked out")
        inner = QVBoxLayout(box)
        self.follow = QCheckBox("Bonds follow the geometry")
        self.follow.setChecked(settings.bonds_follow_geometry)
        self.follow.toggled.connect(self._follow_toggled)
        inner.addWidget(self.follow)
        inner.addWidget(_hint(
            "Off: bonds change when you ask them to, with Recalculate "
            "bonds.  On, they are worked out again after every edit "
            "that moves an atom -- which is what somebody building a "
            "molecule by hand wants, and what somebody watching a "
            "relaxation does not."))
        layout.addWidget(box)

        box = QGroupBox("What a newly opened structure starts from")
        inner = QVBoxLayout(box)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        inner.addWidget(self.summary)
        row = QHBoxLayout()
        edit = QPushButton("Edit defaults...")
        edit.clicked.connect(self._edit_defaults)
        self.reset = QPushButton("Reset to built-in")
        self.reset.clicked.connect(self._reset_defaults)
        row.addWidget(edit)
        row.addWidget(self.reset)
        row.addStretch(1)
        inner.addLayout(row)
        inner.addWidget(_hint(
            "A structure carries its own rules and a project keeps "
            "the ones it was saved with, so this is a starting point "
            "and never an override."))
        layout.addWidget(box)
        layout.addStretch(1)
        self._show_defaults()

    # -- what the controls do ------------------------------------------

    def _follow_toggled(self, on: bool) -> None:
        self.settings.bonds_follow_geometry = on
        self.followGeometryChanged.emit(on)

    def _edit_defaults(self) -> None:
        if BondRulesDialog.edit_defaults(self.settings, self):
            self._show_defaults()

    def _reset_defaults(self) -> None:
        self.settings.set_default_bond_rules(None)
        self._show_defaults()

    def _show_defaults(self) -> None:
        stored = self.settings.default_bond_rules()
        self.reset.setEnabled(bool(stored))
        self.summary.setText(describe_rules(stored))


def describe_rules(stored: dict) -> str:
    """The stored default criteria, in a sentence.

    A dialog is where they are edited; what a page like this owes is
    an answer to "what are they now" that does not need one opened.
    """
    if not stored:
        return ("The built-in criteria: a radius factor of "
                f"{bonding.DEFAULT_SCALE:g}, no extra allowance, and "
                "no metal-metal bonds.")
    rules = bonding.BondRules.from_dict(stored)
    parts = [f"Radius factor {rules.scale:g}"]
    if rules.delta:
        parts.append(f"{rules.delta:+g} A allowance")
    parts.append("metal-metal bonds allowed" if rules.allow_metal_metal
                 else "no metal-metal bonds")
    named = len(rules.pair_ranges) + len(rules.forbidden)
    if named:
        parts.append(f"{named} element pair(s) named")
    return ", ".join(parts) + "."


class _Command(QWidget):
    """A command to type, and the button that saves typing it.

    A line of shell in a dialog is a thing somebody has to retype by
    hand into a terminal, and mistyping a quoted extra is the most
    likely way to end up believing the advice was wrong.
    """

    def __init__(self, command: str, parent=None):
        super().__init__(parent)
        self.field = QLineEdit(command)
        self.field.setReadOnly(True)
        self.field.setCursorPosition(0)
        self.copy = QPushButton("Copy")
        self.copy.clicked.connect(self._copy)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.field, 1)
        row.addWidget(self.copy)

    def text(self) -> str:
        return self.field.text()

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.field.text())
        self.copy.setText("Copied")


#: The programs, in the order the page lists them.  DFTB+'s two tools
#: and its parameters sit under it, indented, because none of them
#: means anything without it.
_PROGRAM_ROWS = ("tools/zeopp", "tools/dftb", "tools/tblite",
                 "tools/xtb", "tools/blender")
_UNDER = {"tools/dftb": ("tools/waveplot", "tools/modes",
                         external.SLATER_KOSTER)}
#: Not engines: data a program reads.  Their own group, last.
_OWN_DATA = ("mof/topology_dir", "mof/bb_dir")


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    font.setPointSizeF(font.pointSizeF() * 1.15)
    label.setFont(font)
    return label


class EnginesPage(QWidget):
    """Every program and package a feature runs on, whether it is
    here, and a button that finds out whether it *works*.

    This was two pages, External tools and Optional features, and they
    answered one question -- "why is this greyed out" -- in two places.
    One page now, in three groups: the programs this application shells
    out to, the Python packages it imports, and the folders of nets and
    blocks a user adds to PORMAKE's, which are not engines but are
    still paths somebody has to be able to set.

    **Every row carries a status line, and that line is the feature.**
    A path field that turns red says nothing anybody can act on; "Not
    found.  Looked at XTAL_ZEOPP, which is not set, and on PATH" is the
    sentence that saves an afternoon.  See :mod:`xtalapp.external`.

    **Test runs the program.**  Found is not the same as working -- a
    binary for the other architecture is found -- so the button starts
    it for a moment and shows what it printed.  Through ``QProcess``,
    never a worker thread: a probe is a child process with nothing to
    compute in Python, and a ``QThread`` would put the button on the
    path of the deadlock described in ``CLAUDE.md``.  How each program
    is asked is :mod:`xtal.modules.probe`.

    **A packaged build says different things.**  There is no
    environment to install into, and advice to install something is a
    polished way of saying something untrue; the wording, and the
    decision behind it, are :mod:`xtalapp.extras`.
    """

    TITLE = "Engines"

    #: A path was changed.  The window pushes the new one into
    #: :mod:`xtal`'s lookup and asks the Modules menu again, which is
    #: what makes a greyed-out module light up without a restart.
    toolPathsChanged = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        #: Path fields and status lines, by preference key.
        self.fields: dict = {}
        self.status: dict = {}
        #: Status lines of the packages, by package name.
        self.rows: dict = {}
        #: Test buttons and what they last reported, by preference key
        #: for a program and by package name for a package.
        self.tests: dict = {}
        self.results: dict = {}
        self._running: dict = {}
        tools = {tool.key: tool for tool in external.TOOLS}

        layout = QVBoxLayout(self)
        layout.addWidget(_heading("Programs"))
        for key in _PROGRAM_ROWS:
            layout.addWidget(self._tool_row(tools[key]))
            for under in _UNDER.get(key, ()):
                indented = QWidget()
                inner = QVBoxLayout(indented)
                inner.setContentsMargins(24, 0, 0, 0)
                inner.addWidget(self._tool_row(tools[under]))
                layout.addWidget(indented)

        layout.addWidget(_heading("Python packages"))
        layout.addWidget(_hint(
            "This is a packaged build: the Python inside it is not "
            "yours and has no pip." if extras.frozen() else
            "Running from a source checkout, so these commands are "
            "for the environment it is running in."))
        for extra in extras.EXTRAS:
            layout.addWidget(self._extra_row(extra))
        layout.addWidget(self._packages_box())

        layout.addWidget(_heading("Your own nets and blocks"))
        for key in _OWN_DATA:
            layout.addWidget(self._tool_row(tools[key]))
        layout.addStretch(1)

    # -- the rows ------------------------------------------------------

    def _tool_row(self, tool) -> QGroupBox:
        box = QGroupBox(tool.label)
        inner = QVBoxLayout(box)
        inner.addWidget(_hint(tool.hint))
        if tool.references:
            inner.addWidget(SourceLinks(tool.references))

        field = QLineEdit(self.settings.path_setting(tool.key))
        field.setCursorPosition(0)
        field.setPlaceholderText("Found automatically")
        field.textChanged.connect(
            lambda text, t=tool: self._typed(t, text))
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda _c=False, t=tool: self._browse(t))
        row = QHBoxLayout()
        row.addWidget(field, 1)
        row.addWidget(browse)
        if external.program_for(tool.key) is not None:
            row.addWidget(self._test_button(tool.key))
        inner.addLayout(row)

        status = QLabel()
        status.setWordWrap(True)
        inner.addWidget(status)
        self.fields[tool.key] = field
        self.status[tool.key] = status
        self._show_status(tool)
        if tool.key in self.tests:
            inner.addWidget(self.results[tool.key])
        return box

    def _extra_row(self, extra) -> QGroupBox:
        ok, sentence = extras.status(extra)
        box = QGroupBox(f"{extra.label} ({extra.package})")
        inner = QVBoxLayout(box)
        inner.addWidget(_hint(extra.powers))
        if extra.references:
            inner.addWidget(SourceLinks(extra.references))
        state = QLabel(sentence)
        state.setWordWrap(True)
        set_tone(state, None if ok else WARNING)
        row = QHBoxLayout()
        row.addWidget(state, 1)
        row.addWidget(self._test_button(extra.package), 0, Qt.AlignTop)
        inner.addLayout(row)
        if not ok and not extras.frozen():
            inner.addWidget(_Command(extra.command()))
            if extra.note:
                inner.addWidget(_hint(extra.note))
        inner.addWidget(self.results[extra.package])
        self.rows[extra.package] = state
        return box

    def _test_button(self, key: str) -> QPushButton:
        button = QPushButton("Test")
        button.setToolTip("Run it for a moment and show what it says")
        button.setAutoDefault(False)
        button.clicked.connect(lambda _c=False, k=key: self.test(k))
        result = QLabel()
        result.setWordWrap(True)
        result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        result.hide()
        self.tests[key] = button
        self.results[key] = result
        return button

    def _packages_box(self) -> QGroupBox:
        """The folder a frozen build can have a package added to.

        This used to be "Having the MOF builder anyway", offering two
        routes to a PORMAKE that was not in the bundle.  PORMAKE is
        vendored now, so the box is what it always really was: the one
        mechanism a build with no pip has for adding a package at all.
        The caveat in ``extras.TARGET_WARNING`` is unchanged and was
        never specific to PORMAKE.
        """
        box = QGroupBox("Adding a package to this copy")
        inner = QVBoxLayout(box)
        inner.addWidget(_hint(extras.PACKAGES_REASON))

        self.target_command = _Command(extras.target_command())
        inner.addWidget(self.target_command)
        warning = QLabel(extras.TARGET_WARNING)
        warning.setWordWrap(True)
        set_tone(warning, WARNING)
        inner.addWidget(warning)
        self.reveal = QPushButton("Show the folder")
        self.reveal.clicked.connect(lambda: extras.reveal())
        row = QHBoxLayout()
        row.addWidget(self.reveal)
        row.addStretch(1)
        inner.addLayout(row)
        return box

    # -- what the controls do ------------------------------------------

    def _typed(self, tool, text: str) -> None:
        self.settings.set_path_setting(tool.key, text)
        self._show_status(tool)
        self.toolPathsChanged.emit()

    def _browse(self, tool) -> None:
        field = self.fields[tool.key]
        if tool.kind == "folder":
            chosen = QFileDialog.getExistingDirectory(
                self, tool.label, field.text())
        else:
            chosen = QFileDialog.getOpenFileName(
                self, tool.label, field.text())[0]
        if chosen:
            # Through the field, so the write and the status line are
            # the ones typing already does.
            field.setText(chosen)

    def _show_status(self, tool) -> None:
        ok, sentence = external.status(self.settings, tool)
        label = self.status[tool.key]
        label.setText(sentence)
        # Not grey when it is found: the description above it is
        # grey, and the answer must not read as more of the blurb.
        set_tone(label, None if ok else WARNING)

    # -- Test ----------------------------------------------------------

    def _probe(self, key: str):
        """How to ask the program or package ``key``, or the sentence
        saying there is nothing to ask."""
        extra = next((e for e in extras.EXTRAS if e.package == key),
                     None)
        if extra is not None:
            return probes.probe_for_package(
                extra.module or extra.package, frozen=extras.frozen(),
                timeout=extra.timeout, prepend=extras.on_path())
        tool = next(t for t in external.TOOLS if t.key == key)
        path = external.locate(self.settings, tool)
        if path is None:
            return "Not found, so there is nothing to run."
        return probes.probe_for(key, path)

    def is_testing(self, key: str) -> bool:
        return key in self._running

    def test(self, key: str) -> None:
        """Run the probe for ``key`` without waiting for it."""
        if key in self._running:
            return
        probe = self._probe(key)
        if isinstance(probe, str):
            self._report(key, False, probe)
            return

        process = QProcess(self)
        process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels)
        empty = None
        if probe.empty_cwd:
            empty = tempfile.mkdtemp(prefix="xtal-probe-")
            process.setWorkingDirectory(empty)
        timer = QTimer(self)
        timer.setSingleShot(True)
        state = {"timed_out": False}

        def timed_out():
            state["timed_out"] = True
            process.kill()

        def finished(code, _status):
            output = process.readAll().data().decode(
                "utf-8", errors="replace")
            self._done(key, *probes.summarise(
                probe, code, output, timed_out=state["timed_out"]))

        def failed(error):
            if error == QProcess.ProcessError.FailedToStart:
                self._done(key, *probes.summarise(
                    probe, None, "", error=process.errorString()))

        timer.timeout.connect(timed_out)
        process.finished.connect(finished)
        process.errorOccurred.connect(failed)
        self._running[key] = (process, timer, empty)
        self.tests[key].setEnabled(False)
        self._report(key, None, "Running...")
        timer.start(int(probe.timeout * 1000))
        process.start(str(probe.argv[0]),
                      [str(a) for a in probe.argv[1:]])
        process.closeWriteChannel()

    def _done(self, key: str, ok: bool, sentence: str) -> None:
        running = self._running.pop(key, None)
        if running is None:
            return
        process, timer, empty = running
        timer.stop()
        process.deleteLater()
        timer.deleteLater()
        if empty is not None:
            shutil.rmtree(empty, ignore_errors=True)
        self.tests[key].setEnabled(True)
        self._report(key, ok, sentence)

    def _report(self, key: str, ok, sentence: str) -> None:
        label = self.results[key]
        label.setText(sentence)
        set_tone(label, WARNING if ok is False else None)
        label.show()

    def stop_tests(self) -> None:
        """Kill whatever is still running: a dialog closed on a
        three-second Blender must not leave it behind."""
        for key in list(self._running):
            process, _timer, _empty = self._running[key]
            process.finished.disconnect()
            process.errorOccurred.disconnect()
            process.kill()
            process.waitForFinished(1000)
            self._done(key, False, "Stopped.")


#: The pages, in the order the list shows them.
PAGES = (GeneralPage, ViewDefaultsPage, BondingPage, EnginesPage)


class PreferencesDialog(QDialog):
    """The settings window: a list of pages, and Close."""

    recentCleared = Signal()
    layoutReset = Signal()
    followGeometryChanged = Signal(bool)
    toolPathsChanged = Signal()
    autosaveChanged = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.settings = settings

        self.list = QListWidget()
        self.list.setMaximumWidth(180)
        self.stack = QStackedWidget()
        self.pages = []
        for factory in PAGES:
            page = factory(settings)
            self.pages.append(page)
            self.list.addItem(page.TITLE)
            # Each page scrolls rather than being squeezed.  A page is
            # a column of controls with a sentence under each, and a
            # window shorter than the column has to put the rest
            # somewhere -- overlapping the sentences is what a plain
            # layout does.
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QScrollArea.Shape.NoFrame)
            area.setWidget(page)
            self.stack.addWidget(area)
            for name in ("recentCleared", "layoutReset",
                         "followGeometryChanged", "toolPathsChanged",
                         "autosaveChanged"):
                signal = getattr(page, name, None)
                if signal is not None:
                    signal.connect(getattr(self, name))
        self.list.setCurrentRow(0)
        self.list.currentRowChanged.connect(self.stack.setCurrentIndex)

        # Close alone: everything here is applied as it is changed, and
        # an OK button would promise a transaction that does not exist.
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        body = QHBoxLayout()
        body.addWidget(self.list)
        body.addWidget(self.stack, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)
        self.resize(680, 620)

    def done(self, result: int) -> None:
        for page in self.pages:
            stop = getattr(page, "stop_tests", None)
            if stop is not None:
                stop()
        super().done(result)

    def page(self, title: str) -> QWidget:
        """The page of that name, for tests and for ``show_page``."""
        for page in self.pages:
            if page.TITLE == title:
                return page
        raise KeyError(title)

    def show_page(self, title: str) -> None:
        page = self.page(title)
        self.list.setCurrentRow(self.pages.index(page))

    def current_page(self) -> QWidget:
        """The page on show.  The stack holds each one in a scroll
        area, so this is not ``stack.currentWidget()``."""
        return self.pages[self.stack.currentIndex()]
