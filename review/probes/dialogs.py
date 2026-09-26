"""Build every dialog, grab it, and report its button box / keys."""
import traceback

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QPushButton,
                               QAbstractSpinBox, QLineEdit, QComboBox,
                               QCheckBox, QRadioButton, QLabel)

out = "review/shots/dlg"
import os
os.makedirs(out, exist_ok=True)

S = imp("xtalapp.dialogs")


def spec():
    d = {}
    d["workspace_chooser"] = (
        "xtalapp.dialogs.workspace_chooser.WorkspaceChooser",
        lambda C: C(win.settings, win), (760, 560))
    d["preferences"] = ("xtalapp.dialogs.preferences.PreferencesDialog",
                        lambda C: C(win.settings, win), (900, 640))
    d["supercell"] = ("xtalapp.dialogs.supercell.SupercellDialog",
                      lambda C: C(doc, win), None)
    d["cell_edit"] = ("xtalapp.dialogs.cell_edit.CellEditDialog",
                      lambda C: C(doc.structure, win), None)
    d["find_symmetry"] = ("xtalapp.dialogs.find_symmetry.FindSymmetryDialog",
                          lambda C: C(doc, win), None)
    d["spacegroup"] = ("xtalapp.dialogs.spacegroup.SpaceGroupDialog",
                       lambda C: C(doc, win), None)
    d["merge_duplicates"] = (
        "xtalapp.dialogs.merge_duplicates.MergeDuplicatesDialog",
        lambda C: C(doc, win), None)
    d["display_range"] = ("xtalapp.dialogs.display_range.DisplayRangeDialog",
                          lambda C: C(doc, win), None)
    d["add_atom"] = ("xtalapp.dialogs.add_atom.AddAtomDialog",
                     lambda C: C(doc.structure.lattice, win), None)
    d["add_centroid"] = ("xtalapp.dialogs.add_centroid.AddCentroidDialog",
                         lambda C: C(3, win), None)
    d["add_hydrogens"] = ("xtalapp.dialogs.add_hydrogens.AddHydrogensDialog",
                          lambda C: C(doc, win), None)
    d["bond_rules"] = ("xtalapp.dialogs.bond_rules.BondRulesDialog",
                       lambda C: C(doc, win), (760, 620))
    d["export"] = ("xtalapp.dialogs.export.ExportDialog",
                   lambda C: C(doc, win), None)
    d["image_export"] = ("xtalapp.dialogs.image_export.ImageExportDialog",
                         lambda C: C(win), None)
    d["run_progress"] = ("xtalapp.dialogs.run_progress.RunProgressDialog",
                         lambda C: C(win), (560, 360))
    d["help"] = ("xtalapp.dialogs.help.HelpWindow",
                 lambda C: C(win, win), (900, 640))
    d["save_block"] = ("xtalapp.dialogs.save_block.SaveBlockDialog",
                       lambda C: C(doc.structure, win), None)
    d["fill_pores"] = ("xtalapp.dialogs.fill_pores.FillPoresDialog",
                       lambda C: C(doc, (), win), None)
    return d


def describe(name, dlg):
    print(f"--- {name}: {type(dlg).__name__}")
    print(f"    title: {dlg.windowTitle()!r}  modal={dlg.isModal()} "
          f"sizeHint={dlg.sizeHint().width()}x{dlg.sizeHint().height()}")
    boxes = dlg.findChildren(QDialogButtonBox)
    if not boxes:
        print("    NO QDialogButtonBox")
    for b in boxes:
        info = []
        for btn in b.buttons():
            role = b.buttonRole(btn)
            info.append(f"{btn.text()!r}[{role.name}]"
                        f"{'*DEFAULT' if btn.isDefault() else ''}")
        print("    buttonbox:", ", ".join(info))
    loose = [w for w in dlg.findChildren(QPushButton)
             if not isinstance(w.parent(), QDialogButtonBox)]
    if loose:
        print("    loose buttons:",
              ", ".join(f"{w.text()!r}{'*DEF' if w.isDefault() else ''}"
                        for w in loose))
    # Esc: a plain QDialog rejects on Esc unless keyPressEvent is
    # overridden.
    over = type(dlg).keyPressEvent is not QDialog.keyPressEvent
    print(f"    keyPressEvent overridden: {over}   "
          f"reject overridden: "
          f"{type(dlg).reject is not QDialog.reject}")
    focusable = [w for w in dlg.findChildren(
        (QAbstractSpinBox, QLineEdit, QComboBox, QCheckBox, QRadioButton))
        if w.isVisibleTo(dlg)]
    print(f"    focusable fields: {len(focusable)}")
    named = [w for w in dlg.findChildren(object)
             if hasattr(w, "accessibleName") and w.accessibleName()]
    print(f"    widgets with accessibleName: {len(named)}")
    texts = []
    for lab in dlg.findChildren(QLabel):
        t = lab.text()
        if t:
            texts.append(t)
    ang = [t for t in texts if "Å" in t]
    asc = [t for t in texts if "A^" in t or t.strip().endswith(" A")
           or "(A)" in t]
    if ang or asc:
        print(f"    units: angstrom-symbol {ang[:4]}  ascii {asc[:4]}")


for name, (dotted, build, size) in spec().items():
    try:
        C = imp(dotted)
        dlg = build(C)
        dlg.show()
        if size:
            dlg.resize(*size)
        settle(400)
        path = f"{out}/{name}.png"
        dlg.grab().save(path)
        describe(name, dlg)
        print(f"    -> {path}")
        dlg.close()
        dlg.deleteLater()
    except Exception as exc:
        print(f"--- {name}: FAILED {exc!r}")
        traceback.print_exc()
    settle(100)
