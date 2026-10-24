import os

out = "review/shots"

print("== status bar ==")
print("status_label visible:", win.status_label.isVisible(),
      repr(win.status_label.text()))
print("selection_label:", repr(win.selection_label.text()))
print("currentMessage:", repr(win.statusBar().currentMessage()))
print("status_label geom:", win.status_label.geometry())

print("== toolbar ==")
bar = win.findChild(type(win.findChildren(__import__(
    'PySide6.QtWidgets', fromlist=['QToolBar']).QToolBar)[0]))
tb = win.findChildren(__import__('PySide6.QtWidgets',
                                 fromlist=['QToolBar']).QToolBar)[0]
print("toolbar sizeHint:", tb.sizeHint(), "width now:", tb.width())
print("window size:", win.size())

print("== docks: minimum widths (MAXIMUM_MINIMUM is 200) ==")
from xtalapp import docks as _d
print("MAXIMUM_MINIMUM =", _d.MAXIMUM_MINIMUM)
for name in dir(win):
    if name.endswith("_dock"):
        dk = getattr(win, name)
        w = dk.widget()
        if w is None:
            continue
        print(f"  {name:18s} minW={w.minimumSizeHint().width():4d} "
              f"minH={w.minimumSizeHint().height():4d} "
              f"hint={w.sizeHint().width():4d} shown={dk.isVisible()}")

for wd, ht in [(1280, 800), (1024, 700), (900, 600)]:
    win.resize(wd, ht)
    settle()
    settle()
    p = f"{out}/10-window-{wd}x{ht}.png"
    win.grab().save(p)
    left = win.width()
    print(f"resized {wd}x{ht}: actual {win.width()}x{win.height()} -> {p}")
    print("   central viewport width:", win.centralWidget().width(),
          " toolbar hint:", tb.sizeHint().width())
