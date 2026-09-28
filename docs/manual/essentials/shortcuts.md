# Keyboard shortcuts

Every command that has a key, grouped as the menu bar groups them.
After this page you can reach the commands you press most often
without opening a menu, and you know how the same key is written on
each platform.

```{index} single: keyboard shortcuts
```

The keys are written as the {doc}`command reference
</reference/commands>` records them, which is Qt's portable spelling.
On macOS the menus show {kbd}`Ctrl` as {kbd}`⌘`, {kbd}`Shift` as
{kbd}`⇧` and {kbd}`Del` as {kbd}`⌦`: {kbd}`Ctrl+S` below is
{kbd}`⌘S` in the *File* menu.  On Windows and Linux they are as
written.

The table is generated from the same inventory the reference is
written from, `docs/manual/reference/inventory.json`; 33 commands
carry a key.  Where a command has more than one key the inventory
records the first, and the second is noted in the table.

| Menu | Command | Key |
|---|---|---|
| File | {ref}`New <cmd-new>` | {kbd}`Ctrl+N` |
| File | {ref}`Open… <cmd-open>` | {kbd}`Ctrl+O` |
| File | {ref}`Save File <cmd-save>` | {kbd}`Ctrl+S` |
| File | {ref}`Save As… <cmd-save_as>` | {kbd}`Ctrl+Shift+S` |
| File | {ref}`Close <cmd-close_tab>` | {kbd}`Ctrl+W` |
| File | {ref}`Close All <cmd-close_all_tabs>` | {kbd}`Ctrl+Shift+W` |
| File | {ref}`Preferences… <cmd-preferences>` | {kbd}`Ctrl+,` |
| File | {ref}`Quit <cmd-quit>` | {kbd}`Ctrl+Q` |
| Edit | {ref}`Undo <cmd-undo>` | {kbd}`Ctrl+Z` |
| Edit | {ref}`Redo <cmd-redo>` | {kbd}`Ctrl+Shift+Z` |
| Edit | {ref}`Cut <cmd-cut>` | {kbd}`Ctrl+X` |
| Edit | {ref}`Copy <cmd-copy>` | {kbd}`Ctrl+C` |
| Edit | {ref}`Paste <cmd-paste>` | {kbd}`Ctrl+V` |
| Edit | {ref}`Duplicate <cmd-duplicate>` | {kbd}`Ctrl+D` |
| Edit | {ref}`Delete <cmd-delete_selection>` | {kbd}`Del`, also {kbd}`Backspace` |
| Select | {ref}`Select All <cmd-select_all>` | {kbd}`Ctrl+A` |
| Select | {ref}`Invert selection <cmd-invert_selection>` | {kbd}`Ctrl+I` |
| Select | {ref}`Grow ▸ Grow to bonded neighbours <cmd-expand_bonded>` | {kbd}`Ctrl+G` |
| Select | {ref}`Grow ▸ Grow to whole fragment <cmd-expand_fragment>` | {kbd}`Ctrl+Shift+G` |
| Structure | {ref}`Add atom… <cmd-add_atom_dialog>` | {kbd}`Ctrl+Shift+A` |
| Structure | {ref}`Reset bonds to automatic <cmd-reset_bonds>` | {kbd}`Ctrl+B` |
| Symmetry | {ref}`Find symmetry… <cmd-find_symmetry>` | {kbd}`Ctrl+Shift+F` |
| Measure | {ref}`Measure selection <cmd-measure_selection>` | {kbd}`Ctrl+M` |
| Measure | {ref}`Define plane from selection <cmd-define_plane>` | {kbd}`Ctrl+Shift+P` |
| View | {ref}`Display range… <cmd-display_range>` | {kbd}`Ctrl+R` |
| View | {ref}`Along a <cmd-view_a>` | {kbd}`1` |
| View | {ref}`Along b <cmd-view_b>` | {kbd}`2` |
| View | {ref}`Along c <cmd-view_c>` | {kbd}`3` |
| View | {ref}`Reset view <cmd-reset_view>` | {kbd}`Ctrl+0` |
| Modules | {ref}`Forcefield ▸ Single point energy <cmd-single_point>` | {kbd}`Ctrl+E` |
| Modules | {ref}`Forcefield ▸ Optimise geometry <cmd-optimize>` | {kbd}`Ctrl+Shift+E` |
| Help | {ref}`Crystal Builder Help <cmd-help_contents>` | {kbd}`Ctrl+?` |
| -- | {ref}`Cancel the current gesture <cmd-cancel_gesture>` | {kbd}`Esc` |

Three things about the table that are choices rather than accidents:

- {kbd}`Ctrl+B` is on *Reset bonds to automatic* and not on
  *Recalculate bonds*, because recalculating after moving atoms is
  rare -- bonds do not follow the geometry -- and the way back to a
  clean answer after an afternoon of editing is the one worth a
  reflex.  The toolbar button is *Recalculate*, because a button is
  pressed by aim rather than by memory and the destructive one of a
  pair is the wrong thing to leave under the cursor.
- *Select None* has no key: {kbd}`Esc` is one action, and clearing
  the selection is its last rung, after a half-finished gesture and a
  mode.  Two actions on one key is, in Qt, neither of them firing.
- The DFTB+ single point and optimisation have no key, because
  {kbd}`Ctrl+E` and {kbd}`Ctrl+Shift+E` already mean the force field
  and a DFTB+ run is launched from its panel or the *Modules* menu.

*Help ▸ Crystal Builder Help* lists the same keys inside the
application.
