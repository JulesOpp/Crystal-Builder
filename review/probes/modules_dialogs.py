"""Module dialogs, the subgroup dialog, and the menu bar as built."""
import os
import traceback

from PySide6.QtWidgets import QDialogButtonBox, QPushButton, QMenu

os.makedirs("review/shots/dlg", exist_ok=True)

print("== module dialogs ==")
from xtal.modules.registry import MODULES               # noqa: E402
from xtalapp.dialogs import module_dialog   # noqa: E402
from xtalapp.dialogs.module_form import ModuleDialog    # noqa: E402

wanted = [("zeopp", "volume"), ("zeopp", "psd"), ("pxrd", "simulate"),
          ("scan", "run"), ("mof", "build"), ("net", "draw"),
          ("build", "molecule"), ("dftb", "charges"),
          ("dftb", "band-structure"), ("blender", "export-stl")]
for mname, aname in wanted:
    try:
        module, action = MODULES.find(f"{mname}.{aname}")
        cls = module_dialog(action.dialog) or ModuleDialog
        dlg = cls(module, action, win, None)
        dlg.show()
        settle(500)
        path = f"review/shots/dlg/mod-{mname}-{aname}.png"
        dlg.grab().save(path)
        print(f"  {mname}.{aname}: {type(dlg).__name__} "
              f"title={dlg.windowTitle()!r} "
              f"hint={dlg.sizeHint().width()}x{dlg.sizeHint().height()}")
        for b in dlg.findChildren(QDialogButtonBox):
            print("     buttons:", ", ".join(
                f"{x.text()!r}{'*DEF' if x.isDefault() else ''}"
                for x in b.buttons()))
        print("     params:", [(p.name, getattr(p, 'suffix', ''),
                                p.default)
                               for p in action.params][:12])
        print("     ->", path)
        dlg.close()
        dlg.deleteLater()
    except Exception as exc:
        print(f"  {mname}.{aname}: FAILED {exc!r}")
        traceback.print_exc()
    settle(150)

print("== subgroup dialog ==")
try:
    C = imp("xtalapp.dialogs.subgroup.SubgroupDialog")
    dlg = C(doc, win)
    dlg.show()
    dlg.resize(760, 620)
    settle(800)
    dlg.grab().save("review/shots/dlg/subgroup.png")
    for b in dlg.findChildren(QDialogButtonBox):
        print("   buttons:", ", ".join(
            f"{x.text()!r}{'*DEF' if x.isDefault() else ''}"
            for x in b.buttons()))
    dlg.close()
except Exception as exc:
    print("   subgroup FAILED", repr(exc))

print("== context menu in the viewport ==")
vp = win.current_viewport()
menus = win.findChildren(QMenu)
print("   menus in window:", len(menus))
