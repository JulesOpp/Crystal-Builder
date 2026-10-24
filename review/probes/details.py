"""Squeezed panels, enabled-with-nothing-selected, a11y names, DFTB+."""
import os

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (QMessageBox, QPushButton, QWidget,
                               QAbstractSpinBox, QLineEdit, QComboBox,
                               QCheckBox, QAbstractItemView, QLabel)

os.makedirs("review/shots/squeeze", exist_ok=True)
seen = []


def record(name):
    def f(*a, **k):
        seen.append((name, [x for x in a if isinstance(x, str)]))
        print(f"   >>> QMessageBox.{name}"
              f"{[x for x in a if isinstance(x, str)]}")
        return QMessageBox.StandardButton.Ok
    return staticmethod(f)


for n in ("question", "warning", "information", "critical", "about"):
    setattr(QMessageBox, n, record(n))

print("== squeezed panels ==")
for name in ("trajectory_dock", "move_dock", "measure_dock",
             "style_dock", "ff_dock"):
    dock = getattr(win, name)
    floating, visible = dock.isFloating(), dock.isVisible()
    dock.setFloating(True)
    dock.show()
    dock.move(win.geometry().topLeft() + QPoint(60, 60))
    for w in (240, 300):
        dock.resize(w, 420)
        settle(300)
        p = f"review/shots/squeeze/{name}-{w}.png"
        dock.grab().save(p)
    inner = dock.widget()
    print(f"  {name}: dock min {dock.minimumSizeHint().width()} "
          f"content min {inner.minimumSizeHint().width()} "
          f"hint {inner.sizeHint().width()}")
    dock.setFloating(floating)
    dock.setVisible(visible)

print("== buttons enabled with nothing selected ==")
win.select_none()
settle(200)
for name in ("move_dock", "measure_dock", "inspector_dock"):
    dock = getattr(win, name)
    dock.setVisible(True)
    settle(150)
    for b in dock.findChildren(QPushButton):
        print(f"  {name}: {b.text()!r} enabled={b.isEnabled()}")
    dock.setVisible(False)

print("== accessibleName coverage ==")
kinds = (QAbstractSpinBox, QLineEdit, QComboBox, QCheckBox,
         QAbstractItemView)
total = named = 0
for kind in kinds:
    for w in win.findChildren(kind):
        total += 1
        if w.accessibleName():
            named += 1
print(f"  input widgets in the window: {total}, with an "
      f"accessibleName: {named}")
print("  window accessibleName:", repr(win.accessibleName()))
for d in win.docks:
    if d.accessibleName():
        print("   dock named:", d.windowTitle(), d.accessibleName())

print("== tooltips on toolbar buttons ==")
from PySide6.QtWidgets import QToolBar                   # noqa: E402
tb = win.findChildren(QToolBar)[0]
missing = [a.text() for a in tb.actions()
           if not a.isSeparator() and not a.toolTip()]
print("  toolbar actions without a tooltip:", missing)
noTip = [n for n in win.actions_.names()
         if not win.actions_[n].toolTip()
         or win.actions_[n].toolTip() == win.actions_[n].text()]
print(f"  registry actions with no tip beyond their text: "
      f"{len(noTip)} of {len(list(win.actions_.names()))}")
print("   e.g.", noTip[:25])

print("== DFTB+ menu action with no binary ==")
act = win.actions_["dftb_single_point"]
print("  enabled:", act.isEnabled())
act.trigger()
settle(4000)
print("  status message:", repr(win.statusBar().currentMessage()))
print("  dftb dock visible now:", win.dftb_dock.isVisible())
print("  message boxes:", seen)
win.grab().save("review/shots/33-after-dftb-click.png")

print("== keyboard: does Tab reach the docks? ==")
win.setFocus()
settle(100)
fw = app.focusWidget()
print("  focus widget at start:", type(fw).__name__ if fw else None)
for i in range(6):
    ok = win.focusNextChild()
    fw = app.focusWidget()
    print(f"   tab {i + 1}: moved={ok} -> "
          f"{type(fw).__name__ if fw else None} "
          f"{getattr(fw, 'text', lambda: '')() if fw else ''}"[:90])

print("== font scaling ==")
f = app.font()
print("  app font:", f.family(), f.pointSizeF())
print("  any fixed pixel font sizes:",
      [w.font().pixelSize() for w in win.findChildren(QLabel)
       if w.font().pixelSize() > 0][:10])
