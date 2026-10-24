"""Grab every dock, then run a module whose binary is missing."""
import os

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMessageBox

os.makedirs("review/shots/dock", exist_ok=True)
seen = []


def record(name):
    def f(*a, **k):
        texts = [x for x in a if isinstance(x, str)]
        seen.append((name, texts))
        print(f"   >>> QMessageBox.{name}{texts}")
        return QMessageBox.StandardButton.Ok
    return staticmethod(f)


for n in ("question", "warning", "information", "critical", "about"):
    setattr(QMessageBox, n, record(n))

print("== docks ==")
for name in sorted(n for n in dir(win) if n.endswith("_dock")):
    dock = getattr(win, name)
    try:
        floating, visible = dock.isFloating(), dock.isVisible()
        dock.setFloating(True)
        dock.show()
        dock.raise_()
        dock.move(win.geometry().topLeft() + QPoint(60, 60))
        dock.resize(440, 700)
        settle(350)
        path = f"review/shots/dock/{name}.png"
        dock.grab().save(path)
        print(f"  {name:16s} title={dock.windowTitle()!r} -> {path}")
        dock.setFloating(floating)
        dock.setVisible(visible)
    except Exception as exc:
        print(f"  {name}: FAILED {exc!r}")
    settle(80)

print("== module availability ==")
from xtal.modules.registry import MODULES        # noqa: E402

for module in MODULES:
    av = module.availability()
    print(f"  {module.name:12s} ok={bool(av)}  {getattr(av, 'reason', '')}")
    for action in module:
        aav = action.availability()
        if not aav:
            print(f"      {action.name}: {aav.reason}")

print("== run a module whose binary is missing ==")
from xtalapp.dialogs.module_form import ModuleDialog   # noqa: E402

ModuleDialog.ask = classmethod(
    lambda cls, module, action, parent=None, initial=None:
    dict(action.defaults()))

before = win.statusBar().currentMessage()
act = win.actions_["module.zeopp.volume"]
print("  action enabled:", act.isEnabled())
act.trigger()
settle(1500)
print("  status message after clicking Zeo++ volume:",
      repr(win.statusBar().currentMessage()))
print("  permanent line:", repr(win.status_label.text()))
print("  message boxes:", seen)
win.grab().save("review/shots/32-zeopp-missing.png")

print("== the same for DFTB+ ==")
act = win.actions_["dftb_single_point"]
print("  dftb_single_point enabled:", act.isEnabled(),
      "tip:", act.toolTip()[:80])
if act.isEnabled():
    act.trigger()
    settle(1500)
    print("  status:", repr(win.statusBar().currentMessage()))

print("== the force field panel (energy units) ==")
ff = win.ff_dock.widget()
from PySide6.QtWidgets import QLabel, QComboBox       # noqa: E402
for lab in ff.findChildren(QLabel):
    if lab.text().strip():
        print("   label:", repr(lab.text()[:70]))
for cb in ff.findChildren(QComboBox):
    print("   combo:", [cb.itemText(i) for i in range(cb.count())][:12])
