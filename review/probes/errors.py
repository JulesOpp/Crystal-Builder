"""What the user is told when something goes wrong."""
import traceback
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

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


def status():
    return (repr(win.status_label.text()),
            repr(win.statusBar().currentMessage()),
            repr(win.selection_label.text()))


def try_open(path, label):
    print(f"== {label}: {path}")
    try:
        win.open_path(Path(path))
        settle(600)
    except Exception as exc:
        print("   RAISED:", repr(exc))
        traceback.print_exc()
    print("   status_label / message / selection:", status())
    print("   tabs:", win.tabs.count())


try_open("review/probes/does-not-exist.cif", "missing file")
try_open("review/probes/corrupt.cif", "corrupt CIF")
try_open("review/probes/empty.cif", "empty CIF")
try_open("review/probes/errors.py", "a python file as a structure")

print("== status bar overlap: a transient message over the permanent line")
win.show_message("workspace: /somewhere/long/path/workspace")
settle(200)
print("   status_label visible:", win.status_label.isVisible())
print("   permanent text:", repr(win.status_label.text()))
print("   temporary text:", repr(win.statusBar().currentMessage()))
win.grab().save("review/shots/30-statusbar-overlap.png")

print("== open the same file twice")
win.open_path(Path("resources/samples/MOF-5.cif"))
settle(400)
print("   tabs:", win.tabs.count(),
      [win.tabs.tabText(i) for i in range(win.tabs.count())])
win.open_path(Path("resources/samples/MOF-5.cif"))
settle(400)
print("   tabs after re-open:", win.tabs.count(),
      [win.tabs.tabText(i) for i in range(win.tabs.count())])

print("== selection summary")
doc2 = win.current_document()
if doc2 is not None:
    win.select_all()
    settle(300)
    print("   selection_label:", repr(win.selection_label.text()))
    print("   status_label:", repr(win.status_label.text()))

print("== a module whose binary is missing (Zeo++)")
from xtal.modules import registry as modreg
names = [m for m in dir(modreg)]
try:
    from xtal.modules.registry import MODULES
    for key, mod in MODULES.items():
        avail = getattr(mod, "available", None)
        print(f"   module {key}: available="
              f"{avail() if callable(avail) else avail}")
except Exception as exc:
    print("   registry:", repr(exc))

for key in ("module.zeopp.volume", "module.dftb.charges",
            "module.pxrd.simulate", "module.scan.run"):
    if key in win.actions_:
        a = win.actions_[key]
        print(f"   {key}: enabled={a.isEnabled()} tip={a.toolTip()!r}")

print("== log dock")
win.log_dock.setVisible(True)
settle(300)
w = win.log_dock.widget()
print("   log dock class:", type(w).__name__)
for attr in ("text", "view", "list"):
    if hasattr(w, attr):
        obj = getattr(w, attr)
        if hasattr(obj, "toPlainText"):
            body = obj.toPlainText()
            print(f"   {attr} has {len(body.splitlines())} lines; first 15:")
            for line in body.splitlines()[:15]:
                print("      |", line)
win.log_dock.setFloating(True)
win.log_dock.resize(760, 420)
settle(400)
win.log_dock.grab().save("review/shots/31-log-dock.png")
win.log_dock.setFloating(False)
win.log_dock.setVisible(False)

print("== unsaved-change / quit warning while a run is going")
print("   confirm_quit:", hasattr(win, "confirm_quit"),
      "closeEvent overridden:", "closeEvent" in vars(type(win)))
print("   autosave attrs:",
      [n for n in dir(win) if "autosav" in n.lower()
       or "recover" in n.lower()])
print("seen dialogs:", seen)
