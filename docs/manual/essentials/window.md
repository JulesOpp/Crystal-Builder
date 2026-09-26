# Window and Help

The *Window* menu shows and hides the fourteen panels and puts the
layout back; the *Help* menu opens the application's own command
reference, reveals its log and says which version this is.  After
this page you can find a panel you have closed, recover a layout you
have broken, and read the same list of commands this manual's
appendix holds without leaving the application.

## Window

```{index} single: panels; showing and hiding
```
```{index} single: layout; resetting
```

1. The *Window* menu lists every panel by name -- *Structure,
   Workspace, Modules, Inspector, Net, Sites, Move, Style, Measure,
   Force Field, DFTB+, Trajectory, Log, Results* -- with a tick beside
   each one that is shown.  Choose one to show or hide it.  A first
   run shows *Structure*, *Workspace* and *Sites*; the others open
   when something needs them (the *Results* panel when a run finishes)
   or from here.  What each panel is for is in the {doc}`panels
   reference </reference/panels>` and in {doc}`the GUI
   </quickstart/gui>`.
2. Every panel is a dock: drag its title bar to another edge, drop it
   on another panel to tab behind it, or drag it out to float.  Dock
   tab bars scroll rather than widen when there are more tabs than
   fit.
3. {ref}`Reset layout <cmd-reset_layout>` forgets the saved layout and
   puts every panel back where it started.  *Preferences ▸ General*
   has the same button.

:::{note}
**A panel never holds its column open.**  A dock area is as wide as
the widest minimum of any panel in it, tabbed behind or not, and no
panel asks for more than 200 px; a tall form scrolls instead.  If a
column looks squeezed, drag its divider; if the layout is beyond
rescue, *Reset layout*.
:::

## Help

```{index} single: help; in the application
```

1. {ref}`Crystal Builder Help <cmd-help_contents>` ({kbd}`Ctrl+?`)
   opens a window with two pages, *Commands* and *Modules*, generated
   from the application itself: every command grouped as the menu bar
   groups them, with its key and its description, and every module
   entry with every value it asks for.  It is the same information as
   the {ref}`reference appendix <reference-appendix>` of this manual,
   read from the running copy.
2. {ref}`Show Log <cmd-show_log>` reveals the file the application
   writes its warnings and crashes to, in the desktop's file browser.
   Attach it to a bug report.
3. {ref}`About Crystal Builder <cmd-about>` gives the version and the
   libraries underneath -- gemmi {cite}`wojdyr2022gemmi` and spglib
   {cite}`togo2024spglib` for the structure model and symmetry, VTK
   for the rendering.  On macOS it is in the application menu.

The *Workspace* panel has a context menu of its own -- {ref}`Open
<cmd-workspace_open>`, {ref}`Reveal in Finder <cmd-workspace_reveal>`,
{ref}`Copy Path <cmd-workspace_copy_path>` and {ref}`Move to Trash
<cmd-workspace_trash>` -- listed under *Elsewhere* in the command
reference because no menu-bar menu holds them.  *Move to Trash* takes
only a run's folder, never the structure it was run on, and nothing
in the workspace is ever deleted outright.
