---
name: manual-writing
description: Write or update the Crystal Builder user manual (docs/manual, Sphinx + MyST) - set up the manual, draft a chapter, regenerate the command/module/engine reference from the app, script and refresh screenshots, verify the tutorial works, and keep the glossary, bibliography and index consistent - without reading source code wholesale. Use when asked to write, plan, extend, fix or rebuild the manual or any chapter of it, to add a figure, or when a UI change makes the manual out of date.
---

# The user manual

The manual is written **one chapter per session**, from sources that
already exist, with the reference half generated rather than typed.
That is what keeps it affordable and keeps it true: a page generated
from the registry cannot drift from the application, and a chapter
written in its own session does not carry the others' context.

**Do not start writing chapters before the user asks.** The outline
below is agreed; the UI text pass (`ui-text`) and panel redesigns are
meant to land first, because screenshots and names depend on them. If
asked to write a chapter while those are pending, say what will need
redoing.

## Layout

```
docs/manual/
  conf.py                  Sphinx: myst_parser, sphinxcontrib.bibtex, sphinx.ext.intersphinx
  index.md                 master toctree
  front/                   foreword.md  highlights.md  cite.md  using-this-manual.md
  quickstart/              about.md  installation.md  gui.md  first-build.md
                           recommendations.md  troubleshooting.md
  essentials/              file.md edit.md select.md structure.md symmetry.md
                           cell.md measure.md view.md window.md mouse-modes.md shortcuts.md
  modules/                 forcefield.md dftb.md zeopp.md mof-builder.md
                           molecule-builder.md net-builder.md pxrd.md blender.md
  back/                    glossary.md  bibliography.md  genindex (generated)
  reference/               GENERATED: commands.md modules.md engines.md panels.md inventory.json
  figures/                 GENERATED PNGs, one folder per chapter
  shots.py                 the screenshot script
  references.bib           every citation
```

Toolchain, installed only with the user's agreement:
`pip install sphinx myst-parser sphinxcontrib-bibtex furo`; PDF needs
a LaTeX install (`make latexpdf`). Build with
`sphinx-build -b html docs/manual build/manual` (`/build/` is ignored).

## The sources, in the order to trust them

1. **Generated reference**:
   `python .claude/skills/manual-writing/reference.py`, which writes
   `docs/manual/reference/`. Every command (menu path, key, tip,
   registry key), every module entry and setting (kind, range,
   default, help), every engine option, every panel. Anchors:
   `(cmd-<key>)`, `(mod-<module>-<action>)`, `(engine-<name>)`,
   `(panel-<dock attr>)`. **Never hand-edit these files.** A wrong or
   missing sentence is fixed in the source (the `tip=`, the
   `Param.help`, the dock's docstring) and regenerated. The script
   prints which commands and settings still have no text; hand that
   list to the user rather than inventing tips.
2. **The app itself**, driven with `run-app --scratch`: what a dialog
   actually shows, what a status bar says, what a run produces.
3. **Docstrings, by outline** (`code-map`): the first sentence of a
   class or method is usually the user-level explanation; read a body
   only to answer a specific question.
4. `CLAUDE.md` § Invariants: the *why* behind behaviour a user will
   notice (bonds only on Recalculate, dummy atoms, Save converts to a
   project). These become **Notes** in the essentials chapters.
5. `docs/PLAN.md`, `docs/TODO.md` (known limitations for
   Troubleshooting), `docs/RELEASE_NOTES.md` (installation, known
   issues), `docs/PACKAGING.md` (what a packaged copy contains).

Not a source: memory of how things used to be, other programs'
manuals (paraphrase an idea, never copy), guesses about defaults.

## Writing a chapter

1. Read the outline entry below and the generated reference sections
   it covers. Read nothing else yet.
2. List the facts the chapter needs that the reference does not give,
   and get each from the app (a scripted run) or a docstring outline.
3. Draft in MyST. Per page: a two-sentence lead saying what the
   reader can do after it; tasks as numbered steps; each command named
   the way the menu shows it, linked to its reference entry
   (`{ref}`Recalculate bonds <cmd-recompute_bonds>``); `:::{note}` for an
   invariant, `:::{warning}` for data loss or wrong science; one figure
   per task at most.
4. **Index** every concept on first substantive use:
   ```` ```{index} single: symmetry; reduce to P1 ```` ````.
5. **Glossary**: a term defined in `back/glossary.md` is linked with
   ``{term}`Wyckoff position` ``; add the term there if it is new.
6. **Citations**: every method, program, force field and database used
   gets a `references.bib` entry and ``{cite}`rappe1992` `` at first use.
   Verify the entry (DOI) and do not cite from memory; if it cannot be
   checked, leave `TODO-cite` and list it for the user.
7. Figures: add the shot to `shots.py`, regenerate, and look at the
   PNG before referencing it.
8. Build the HTML, fix warnings (broken refs are warnings), and report
   the chapter's word count and the open TODO-cites.

Style: second person, present tense, British spelling as the
application uses (*optimise*, *colour*), units as the app shows them
(Å, kcal/mol/Å, GPa). Say what a control does and why a user would
choose it; the reference already says what values it takes.

## Screenshots: `docs/manual/shots.py`

A `run-app --script` file, run with a scratch profile so every figure
is a first-run window at a fixed size:

```bash
python .claude/skills/run-app/drive.py --scratch build/manual-shots \
  --script docs/manual/shots.py
```

Inside, one function per figure writes
`docs/manual/figures/<chapter>/<name>.png`, using `win.resize(1600,
1000)`, the `--grab` technique for panels and dialogs (`widget.grab()`)
and `viewport.save_image()` for the crystal. Name figures after what
they show, not their order. Regenerating all figures is one command;
never take a figure by hand.

## The first-build tutorial must be proven first

Before `quickstart/first-build.md` is written, script the whole
exercise in `docs/manual/tutorial_check.py` (a `--script` for
run-app) and run it:

1. MOF builder: topology **acs**, node **N134**, edge a drawn
   `*c1ccc(*)cc1` (saved to the workspace's `blocks/`); build.
2. Force field: UFF4MOF, **Relax the cell as well**, optimiser
   **Smart**; run to convergence.
3. **Find Symmetry**: expect **P6₃/mmc**.
4. Draw topology bonds on the µ3-oxo centres; the Net panel says
   **acs**.
5. Delete a topology bond; **Add centroid** at the benzene ring;
   draw a topology bond centroid to nearest metal centre; the Net
   panel says **ssa**.

It must print the space group and both net names, and write the
figures the chapter uses. If a step does not give the expected answer,
**stop and report it**: the tutorial, or the app, is wrong, and the
user decides which. Keep the script; it is the tutorial's regression
check.

## The agreed outline

- **Front**: Foreword · Highlights · How to cite · How to use this
  manual (conventions: menu paths `File ▸ Open`, keys, notes and
  warnings, how the reference chapters are generated)
- **1 Quickstart**: About Crystal Builder · Installation (packaged
  app, source install and extras, external programs and where
  Preferences points at them) · The GUI (window, toolbar, panels from
  `panels.md`, workspaces, the chooser) · Your first crystal build (the
  tutorial above; the closing point is that a net is a choice of
  vertices, not a property of the crystal) · General recommendations ·
  Troubleshooting (from TODO.md limitations, RELEASE_NOTES known
  issues, and the app's own error sentences)
- **2 Essential calculation elements**: one page per menu, in
  menu-bar order: task-oriented prose, then an include of that
  section of `reference/commands.md`; plus mouse modes and shortcuts
- **3 Modules**: one page per module: what it is for, when to use it
  over the alternatives, a worked example on a sample, reading the
  results, its settings (include from `reference/modules.md` /
  `engines.md`), limitations, citations
- **Back**: Glossary · Bibliography (`{bibliography}`) · Index
  (generated)

## Keeping it current

After any change to menus, tips, Params or panels: regenerate the
reference, rebuild, and grep the prose for the old names
(`grep -rn 'Old label' docs/manual --include='*.md'`). A renamed
registry key breaks a `{ref}`, which the build reports; that is the
check.
