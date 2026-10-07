# Window and Help

The *Window* menu shows and hides the fourteen panels and puts the
layout back; the *Help* menu opens the application's own command
reference, reveals its log, sends feedback and says which version this
is.  After this page you can find a panel you have closed, recover a
layout you have broken, and read the same list of commands this
manual's appendix holds without leaving the application.

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

A panel never holds its column open -- a tall form scrolls, and a dock
area is only as wide as the widest minimum of the panels in it -- so a
squeezed column is a divider to drag, and a layout beyond rescue is
*Reset layout* ({doc}`the GUI </quickstart/gui>` explains the rule).

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
3. {ref}`Send Feedback <cmd-send_feedback>` writes a bug report, a
   feature request or a UI suggestion as an email in your own mail
   client, with the version, the system and -- for a bug -- the end
   of the log already in it.  You see the whole email before it
   opens, and nothing is sent until you send it.  The crash box has
   the same button, with the error in it.
4. {ref}`About Crystal Builder <cmd-about>` gives the version and the
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
