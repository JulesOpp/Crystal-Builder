"""
xtalapp.docks.trajectory
========================
The transport bar: play the run back.

Play, pause, step, a frame slider and a speed control, driving
``Document.show_frame`` -- which goes through
:meth:`~xtalapp.document.Document.preview_positions`, so scrubbing
never touches the undo stack and never marks the document modified.

**A frame is not an editable structure.**  Opening a trajectory puts
the document into a preview state that refuses edits, because an edit
made against a frame would be silently wiped by the next one.  There
are two ways out and the bar shows both: *Adopt this frame*, which
pushes one undoable command and keeps the geometry, and *Close*, which
puts the atoms back where they were.

Anything that is a trajectory opens here, not only this application's
own runs: an ASE relaxation, a DFTB+ MD, a LAMMPS dump converted to
extxyz.  What is refused is a trajectory of a *different* crystal --
matching atom counts alone would let one run drive another structure,
which would be nonsense drawn convincingly.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from xtal.io.trajectory import read_trajectory
from xtalapp.playback import IncompatibleTrajectory

#: Label -> milliseconds between frames.
SPEEDS = (
    ("0.5x", 160),
    ("1x", 80),
    ("2x", 40),
    ("4x", 20),
    ("As fast as it draws", 0),
)


class TrajectoryDock(QDockWidget):
    """Scrub a trajectory against the open structure."""

    statusMessage = Signal(str)
    historyLoaded = Signal(object)      # [(step, energy, force), ...]
    frameShown = Signal(int)            # the step of the frame shown

    def __init__(self, parent=None):
        super().__init__("Trajectory", parent)
        self.setObjectName("TrajectoryDock")
        self.document = None

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_play)
        self.back_button = QPushButton("<")
        self.back_button.setToolTip("The frame before")
        self.back_button.clicked.connect(lambda: self.step(-1))
        self.forward_button = QPushButton(">")
        self.forward_button.setToolTip("The frame after")
        self.forward_button.clicked.connect(lambda: self.step(1))

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider)

        self.loop = QCheckBox("Loop")
        self.loop.setToolTip(
            "Start again at the first frame when the last one is "
            "reached.  A relaxation watched once is rarely watched "
            "once.")

        self.speed = QComboBox()
        for label, value in SPEEDS:
            self.speed.addItem(label, value)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self._on_speed)

        self.frame_label = QLabel("")
        self.frame_label.setMinimumWidth(220)
        self.name_label = QLabel("No trajectory open")
        self.name_label.setStyleSheet("color: palette(mid);")

        self.adopt_button = QPushButton("Adopt this frame")
        self.adopt_button.setToolTip(
            "Keep the geometry on screen as one undoable edit, and "
            "stop playing")
        self.adopt_button.clicked.connect(self.adopt)
        self.close_button = QPushButton("Close")
        self.close_button.setToolTip(
            "Stop playing and put the atoms back where they were")
        self.close_button.clicked.connect(self.close_trajectory)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

        self.setWidget(self._build())
        self.set_document(None)

    def _build(self) -> QWidget:
        transport = QHBoxLayout()
        transport.setContentsMargins(0, 0, 0, 0)
        for widget in (self.back_button, self.play_button,
                       self.forward_button):
            widget.setMaximumWidth(90)
            transport.addWidget(widget)
        transport.addWidget(self.slider, 1)
        transport.addWidget(self.loop)
        transport.addWidget(QLabel("Speed"))
        transport.addWidget(self.speed)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(self.frame_label)
        footer.addWidget(self.name_label, 1)
        footer.addWidget(self.adopt_button)
        footer.addWidget(self.close_button)

        body = QVBoxLayout()
        body.setContentsMargins(8, 6, 8, 6)
        body.setSpacing(4)
        body.addLayout(transport)
        body.addLayout(footer)
        container = QWidget()
        container.setLayout(body)
        return container

    # ==================================================================
    #  BINDING
    # ==================================================================

    def set_document(self, document) -> None:
        """Follow a different tab.

        The playback belongs to the document, not to this bar, so
        switching tabs shows whatever that document was doing --
        including nothing.
        """
        self.stop()
        self.document = document
        self.refresh()

    @property
    def playback(self):
        return None if self.document is None else self.document.playback

    @property
    def is_open(self) -> bool:
        return self.playback is not None

    def refresh(self) -> None:
        playback = self.playback
        enabled = playback is not None
        for widget in (self.play_button, self.back_button,
                       self.forward_button, self.slider, self.speed,
                       self.loop, self.adopt_button,
                       self.close_button):
            widget.setEnabled(enabled)
        if not enabled:
            self.slider.blockSignals(True)
            self.slider.setMaximum(0)
            self.slider.setValue(0)
            self.slider.blockSignals(False)
            self.frame_label.setText("")
            self.name_label.setText("No trajectory open")
            return
        self.slider.blockSignals(True)
        self.slider.setMaximum(max(playback.n_frames - 1, 0))
        self.slider.setValue(playback.index)
        self.slider.blockSignals(False)
        self.frame_label.setText(playback.label())
        self.name_label.setText(playback.name)

    # ==================================================================
    #  OPENING
    # ==================================================================

    def open_path(self, path) -> bool:
        """Read a trajectory file and play it against the document."""
        if self.document is None:
            self.statusMessage.emit(
                "open a structure before a trajectory: a trajectory "
                "is played against the crystal it is of")
            return False
        try:
            trajectory = read_trajectory(path)
        except (OSError, ValueError) as exc:
            self.statusMessage.emit(f"could not read {Path(path).name}"
                                    f": {exc}")
            return False
        return self.open_trajectory(trajectory, path)

    def open_trajectory(self, trajectory, path=None) -> bool:
        if self.document is None:
            return False
        try:
            self.document.open_trajectory(trajectory, path)
        except IncompatibleTrajectory as exc:
            self.statusMessage.emit(f"that trajectory is not of this "
                                    f"structure: {exc}")
            return False
        self.refresh()
        self.historyLoaded.emit(_history(trajectory))
        self.show()
        self.raise_()
        self.statusMessage.emit(
            f"{trajectory.n_frames} frames; editing is off until you "
            f"adopt a frame or close the trajectory")
        return True

    def close_trajectory(self) -> None:
        self.stop()
        if self.document is not None:
            self.document.close_playback()
        self.refresh()
        self.statusMessage.emit("closed the trajectory")

    def adopt(self) -> None:
        self.stop()
        if self.document is None or not self.is_open:
            return
        message = self.document.adopt_frame()
        self.refresh()
        self.statusMessage.emit(message)

    # ==================================================================
    #  PLAYING
    # ==================================================================

    def toggle_play(self) -> None:
        self.stop() if self._timer.isActive() else self.play()

    def play(self) -> None:
        if not self.is_open:
            return
        playback = self.playback
        if playback.index >= playback.n_frames - 1:
            self.show_frame(0)          # replay rather than sit still
        self._timer.start(int(self.speed.currentData()))
        self.play_button.setText("Pause")

    def stop(self) -> None:
        self._timer.stop()
        self.play_button.setText("Play")

    @property
    def is_playing(self) -> bool:
        return self._timer.isActive()

    def _advance(self) -> None:
        playback = self.playback
        if playback is None:
            self.stop()
            return
        if playback.index >= playback.n_frames - 1:
            if not self.loop.isChecked():
                self.stop()
                return
            self.show_frame(0)
            return
        self.show_frame(playback.index + 1)

    def step(self, delta: int) -> None:
        if self.is_open:
            self.show_frame(self.playback.index + delta)

    def show_frame(self, index: int) -> None:
        """Draw one frame and tell everything that shows a frame."""
        if self.document is None or not self.is_open:
            return
        self.document.show_frame(index)
        playback = self.playback
        self.slider.blockSignals(True)
        self.slider.setValue(playback.index)
        self.slider.blockSignals(False)
        self.frame_label.setText(playback.label())
        frame = playback.frame
        self.frameShown.emit(int(frame.step if frame.step is not None
                                 else playback.index))

    def show_step(self, step: int) -> None:
        """Jump to the frame with this step number.

        Clicking the energy trace lands here: the plot and the
        trajectory are the same run seen two ways.
        """
        if not self.is_open:
            return
        steps = self.playback.trajectory.steps
        if not steps:
            return                                  # pragma: no cover
        nearest = min(range(len(steps)),
                      key=lambda i: abs(steps[i] - step))
        self.show_frame(nearest)

    def _on_slider(self, value: int) -> None:
        self.show_frame(int(value))

    def _on_speed(self, _index: int) -> None:
        if self._timer.isActive():
            self._timer.start(int(self.speed.currentData()))

    def closeEvent(self, event):                    # pragma: no cover
        self.stop()
        super().closeEvent(event)


def _history(trajectory) -> list:
    """``(step, energy, force)`` per frame, for the energy plot.

    A trajectory this application wrote carries both numbers on every
    comment line.  One from elsewhere usually carries neither, and a
    plot of nothing is better than a plot of zeros presented as
    measurements -- so a frame without an energy is left out.
    """
    out = []
    for index, frame in enumerate(trajectory):
        if frame.energy is None:
            continue
        step = frame.step if frame.step is not None else index
        force = frame.info.get("max_force")
        out.append((int(step), float(frame.energy),
                    float(force) if force is not None else 0.0))
    return out
