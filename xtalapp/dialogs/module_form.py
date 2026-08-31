"""
xtalapp.dialogs.module_form
===========================
A module's parameters, rendered.

Every external engine wants a dialog, and every hand-written dialog is
a hundred lines that drift apart: one remembers its values and the
next does not, one puts units in the label and the next in a suffix,
one validates and the next crashes on an empty field.  So a module
declares :class:`~xtal.modules.registry.Param` objects and this builds
the form from them.

The mapping is deliberately boring -- a bool is a checkbox, a choice is
a combo box -- because the interesting decisions belong to the module
and not to its dialog.  What the form does add is the two things every
one of those hand-written dialogs would have had to remember:

**It says what a parameter is for.**  ``Param.help`` becomes the
tooltip and, where there is room, the line under the widget.  A number
whose meaning is only in the module author's head is one nobody
changes from its default.

**It hands back what was typed, typed.**  ``values()`` runs the
declared coercion, so a module gets an ``int`` from an int parameter
whether the value came from a spinbox, a saved session or a command
line.

There is no layout language, no conditional enabling and no validation
beyond the parameter's own range.  Three modules is not enough to know
what the fourth needs, and each of those is cheap to add later against
a module that actually strains the form.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ParamForm(QWidget):
    """The widgets for one action's parameters, and their values."""

    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.params = tuple(params)
        self.widgets: dict = {}
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for param in self.params:
            widget = self._widget(param)
            self.widgets[param.name] = widget
            if param.help:
                widget.setToolTip(param.help)
            # A checkbox carries its own label; giving it a second one
            # in the left column says the same word twice.
            if param.kind == "bool":
                layout.addRow(widget)
            else:
                label = QLabel(param.title)
                label.setToolTip(param.help)
                layout.addRow(label, widget)

    def _widget(self, param) -> QWidget:
        if param.kind == "bool":
            widget = QCheckBox(param.title)
            widget.setChecked(bool(param.default_value()))
            return widget
        if param.kind == "int":
            widget = QSpinBox()
            widget.setRange(int(param.minimum if param.minimum
                                is not None else -10**9),
                            int(param.maximum if param.maximum
                                is not None else 10**9))
            if param.step:
                widget.setSingleStep(int(param.step))
            widget.setSuffix(param.suffix)
            widget.setValue(int(param.default_value()))
            return widget
        if param.kind == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(int(param.decimals))
            widget.setRange(float(param.minimum if param.minimum
                                  is not None else -1e12),
                            float(param.maximum if param.maximum
                                  is not None else 1e12))
            if param.step:
                widget.setSingleStep(float(param.step))
            widget.setSuffix(param.suffix)
            widget.setValue(float(param.default_value()))
            return widget
        if param.kind == "choice":
            widget = QComboBox()
            for value, label in param.values_and_labels():
                widget.addItem(label, value)
            index = widget.findData(param.default_value())
            widget.setCurrentIndex(max(index, 0))
            return widget
        if param.kind == "path":
            return _PathEdit(param)
        widget = QLineEdit(str(param.default_value()))
        return widget

    # -- values --------------------------------------------------------

    def values(self) -> dict:
        """What the form says, in the types the module declared."""
        raw = {}
        for param in self.params:
            widget = self.widgets[param.name]
            raw[param.name] = _value_of(widget)
        return {p.name: p.coerce(raw[p.name]) for p in self.params}

    def set_values(self, values: dict | None) -> None:
        """Show what was used last time.

        Unknown keys are ignored rather than refused: a saved set of
        values outlives the parameter it was saved for, and the module
        that dropped one should not be unable to open its own form.
        """
        for name, value in dict(values or {}).items():
            widget = self.widgets.get(name)
            if widget is None:
                continue
            param = next(p for p in self.params if p.name == name)
            try:
                _set_value(widget, param.coerce(value))
            except Exception:                       # noqa: BLE001, S110
                pass


class _PathEdit(QWidget):
    """A file path, and the button nobody wants to type one without."""

    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.edit = QLineEdit(str(param.default_value()))
        button = QPushButton("Browse...")
        button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def _browse(self) -> None:                      # pragma: no cover
        chosen = QFileDialog.getOpenFileName(
            self, self.param.title, self.edit.text())[0]
        if chosen:
            self.edit.setText(chosen)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, text: str) -> None:           # noqa: N802
        self.edit.setText(str(text))

    def setToolTip(self, text: str) -> None:        # noqa: N802
        super().setToolTip(text)
        self.edit.setToolTip(text)


def _value_of(widget):
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QSpinBox | QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentData()
    return widget.text()


def _set_value(widget, value) -> None:
    if isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QSpinBox):
        widget.setValue(int(value))
    elif isinstance(widget, QDoubleSpinBox):
        widget.setValue(float(value))
    elif isinstance(widget, QComboBox):
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)
    else:
        widget.setText(str(value))


class ModuleDialog(QDialog):
    """Ask for an action's parameters, then let it run."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(parent)
        self.module = module
        self.action = action
        self.setWindowTitle(f"{module.label}: "
                            f"{action.label.rstrip('.')}")

        self.form = ParamForm(action.params, self)
        self.form.set_values(initial)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        # "Run" rather than "OK", because that is what pressing it
        # does and the difference matters when the thing it starts
        # takes an hour.
        buttons.button(QDialogButtonBox.Ok).setText("Run")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        note = action.tip or module.description
        if note:
            label = QLabel(note)
            label.setWordWrap(True)
            label.setStyleSheet("color: palette(mid);")
            layout.addWidget(label)
        layout.addWidget(self.form)
        layout.addStretch(1)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return self.form.values()

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        """The values to run with, or ``None`` if it was cancelled.

        An action with no parameters is not worth a dialog, so it does
        not get one -- clicking *Optimise* and being asked to confirm
        that there is nothing to confirm is the kind of ceremony a
        generated form makes it easy to add by accident.
        """
        if not action.params:
            return {}
        dialog = cls(module, action, parent, initial)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.values()
