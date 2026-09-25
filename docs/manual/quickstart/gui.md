# The GUI

Crystal Builder is one window: a toolbar across the top, structures
in tabs in the middle, and panels docked either side and below.  It
opens on a question -- which {term}`workspace` to work in -- and
everything you open, build or run lives in the folder you answer
with.

## The workspace chooser

```{index} single: workspace; chooser
```

Before the window is built, the application asks which workspace this
session is in ({numref}`fig-workspace-chooser`).  A workspace is a
folder: structures, calculations and everything they leave behind
are kept in it, and the *Workspace* panel shows it as a tree.

:::{figure} /figures/quickstart/workspace-chooser.png
:name: fig-workspace-chooser
:width: 85%

The workspace chooser.  Recent workspaces are listed with the last
one selected, so {kbd}`Return` is the whole answer for somebody who
has one.
:::

- **Continue** opens the selected workspace.  On a first run the list
  holds one entry, `Crystal Builder` in your home folder, which the
  application makes for you; *Preferences ▸ General* is where that
  default folder is changed.
- **New Workspace…** makes a folder and opens it; **Open Other…**
  opens a folder that is already one.
- **Open Sample** opens the selected workspace with one of the sample
  structures already in a tab.
- **Quit** leaves without opening a window.

A file double-clicked from the Finder or Explorer that is *already
inside* a workspace skips the question, because there is only one
sensible answer.

## The window

```{index} single: window; layout
```
```{index} single: toolbar
```

:::{figure} /figures/quickstart/window.png
:name: fig-window
:width: 100%

The window with the MOF-5 sample open: the toolbar, the *Structure*
and *Workspace* panels on the left, the tab and the 3D view in the
middle, the *Sites* table on the right, and the status bar.
:::

**The menu bar** runs *File, Edit, Select, Structure, Symmetry, Cell,
Measure, View, Modules, Window, Help*, and the chapter
{doc}`/essentials/index` takes them in that order.  Every command in
every menu is listed with its key and its description in the
{doc}`command reference </reference/commands>`, and *Help ▸ Crystal
Builder Help* ({kbd}`Ctrl+?`) shows the same list inside the
application.

**The toolbar** holds what is pressed most often, left to right:

- *Open* and *Save File*, *Undo* and *Redo*.
- The **mouse modes**: *Select*, *Box select*, *Add atom* with the
  element it places beside it, *Add bond*, *Draw net*, *Move* and
  *Measure*.  One is pressed at a time and it decides what a click in
  the 3D view does; each mode's own line in the status bar says what
  to click.
- *Recalculate bonds*.
- **cells** *a*, *b*, *c*: how many unit cells are drawn along each
  axis.  Fractions can be typed -- `1.5` is half a cell more of a
  framework -- and the arrows step whole cells.
- *Reset view*, and **along** *a*, *b*, *c*, which look down each
  axis.

**The 3D view** is the tab.  Left-drag orbits, the wheel zooms,
middle-drag pans.  In *Select* mode a click selects an atom or a
bond, shift-click adds to the selection, and a double-click takes the
whole molecule or framework; *Box select* drags a rectangle and takes
everything inside it, front to back.  With no tab open the middle of
the window is a start pane instead: *Open a structure, drop a file
here, or start from a sample*, with the samples laid out as buttons.

**The status bar** describes the crystal in front -- formula, *Z*,
space group, sites and atoms, volume and density -- and, on the
right, what is selected.  Anything a command has to say in passing
(*net edge drawn -- 6 in the cell*, *bond added*) appears here too.

## The panels

```{index} single: panels
```

Every panel is a dock: it can be dragged to another edge, tabbed
behind another, floated, or closed and reopened from the *Window*
menu.  {ref}`Reset layout <cmd-reset_layout>` puts them back where
they started.  These are the fourteen, with where each opens; the
{doc}`panels reference </reference/panels>` describes each one.

| Panel | Opens on the | What it is for |
|---|---|---|
| {ref}`Structure <panel-info_dock>` | left | A read-only summary of the active document: formula, cell, space group, hand, and the asymmetric unit |
| {ref}`Workspace <panel-file_dock>` | left | The workspace tree, with a filesystem browser beside it; double-click a file to open it |
| {ref}`Modules <panel-modules_dock>` | left | The calculations that can be run, and the Stop button for the one running |
| {ref}`Inspector <panel-inspector_dock>` | right | The properties of the selected site: element, label, coordinates, occupancy, U{sub}`iso`, charge |
| {ref}`Net <panel-net_dock>` | right | The name of the net drawn over the structure, looked up in the RCSR |
| {ref}`Sites <panel-sites_dock>` | right | The site table, kept in step with the selection in the 3D view |
| {ref}`Move <panel-move_dock>` | right | Numeric translations, rotations and mirrors of the selection |
| {ref}`Style <panel-style_dock>` | right | Draw style, sizes, colours, labels and the legend |
| {ref}`Measure <panel-measure_dock>` | right | Distances, angles and torsions, and planes fitted to the selection |
| {ref}`Force Field <panel-ff_dock>` | right | Atom types, a single point, and a geometry optimisation |
| {ref}`DFTB+ <panel-dftb_dock>` | right | The same, with DFTB+ as the engine |
| {ref}`Trajectory <panel-trajectory_dock>` | bottom | Play, scrub and adopt a frame of a trajectory |
| {ref}`Log <panel-log_dock>` | bottom | A run's log, tailed while it is still being written |
| {ref}`Results <panel-results_dock>` | bottom | The tables and plots the last module run came back with |

The *Structure*, *Workspace* and *Sites* panels are shown on a first
run; the rest open when something needs them -- the *Force Field*
panel from *Modules ▸ Forcefield ▸ Force Field panel*, the *Results*
panel when a run finishes -- or from the *Window* menu.

:::{note}
A panel never holds its column open: a dock area is as wide as the
widest minimum of any panel in it, so no panel asks for more than
200 px, and a tall form scrolls instead.  If a column looks
squeezed, drag its divider; if the layout is beyond rescue, *Window
▸ Reset layout*.
:::

## Workspaces

```{index} single: workspace; layout of
```

Every structure gets a folder of its own inside the workspace,
whichever way it arrived: opened from disk (it is copied in, and the
tab follows the copy), started empty from *File ▸ New*, opened from
*Open Sample*, or built by the MOF builder.  Every run then lands
underneath the structure it was run against:

```
MFU4l/
  MFU4l.cif                a copy, so the workspace is whole
  MFU4l.xtalproj           the session, saved beside it
  uff-optimise-001/
    final.cif              the relaxed structure
    trajectory.extxyz      every step
    run.log                what happened, in order
```

Nothing in it is hidden and nothing needs this application to read
it: the trajectory opens in OVITO, VMD and ASE, the log is a text
file, and deleting a folder in the Finder is a supported way to clean
up.  Clicking a node in the tree opens it as what it is -- a
structure in a tab, a trajectory in the transport bar, a log in the
*Log* panel.

Two things about workspaces are worth knowing before they surprise
you:

:::{note}
**Changing workspace closes every tab.**  A tab belongs to the
workspace it was opened in, because its runs are filed there.
*File ▸ Open Workspace…* asks once about unsaved work, then closes
everything and opens the new folder -- which brings back the tabs
*it* was left with, because a workspace remembers its own.
:::

:::{note}
**Save File converts.**  {ref}`Save File <cmd-save>` ({kbd}`Ctrl+S`)
writes the session over the file the tab is, without asking where.
A document opened as a CIF becomes the `.xtalproj` of the same name
beside it on its first save, and the CIF is left exactly where it
is: a CIF cannot hold a measurement, a plane or the view you were
looking at it in.  {ref}`Export… <cmd-export>` is the way to write a
file for something else to read, and it never becomes the document's
file.
:::

Work is not lost between saves either: every two minutes each edited
tab is autosaved to a side file under `.autosave/` in the workspace,
and a newer autosave is offered back when the file is opened.  The
interval is in *Preferences ▸ General*; 0 turns it off.
