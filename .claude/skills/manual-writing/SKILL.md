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
  <chapter>/index.md       quickstart essentials energy structure porosity
                           frameworks workflows utilities architecture
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

Toolchain: the `docs` extra (`pip install -e ".[docs]"`: Sphinx,
MyST, sphinxcontrib-bibtex, furo). Build the HTML with
`sphinx-build -n -W -b html docs/manual build/manual/html`; CI builds
it the same way, so a broken `{ref}` fails the job. The PDF is XeLaTeX:
`sphinx-build -M latexpdf docs/manual build/manual` in CI, but **not
on this Mac**: it runs `make`, which here is the stub that asks to
install Xcode's developer tools. Locally, `sphinx-build -b latex
docs/manual build/manual/latex`, then `latexmk -pdfxe` in that
folder. The
TeX is `/usr/local/texlive/2016/bin/x86_64-darwin` (put it on `PATH`),
which is why `conf.py` turns off admonition icons and xindy; CI uses a
current TeX Live and uploads the PDF as an artifact. `/build/` is
ignored. There is no PDF renderer here: to look at a page, split it
out with pypdf and `sips -s format png` it.

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
   gets a `references.bib` entry and ``{cite}`rappe1992uff` `` at first
   use. **Add entries only with `cite.py`** (`cite.py KEY DOI` or
   `cite.py KEY arXiv:ID`), which fetches the record and prints it: read
   the title against the paper you mean before citing it. Never type an
   entry, and never cite from memory; prefer the published version of
   a preprint (`cite.py --check` finds them). If a source cannot be
   found, leave `TODO-cite` and list it for the user.
7. **Every factual claim has a source** you could point to: the
   generated reference, a scripted run, a docstring, a cited paper. A
   claim about the science that none of them makes is not written; it
   is a question for Julius.
8. Figures: add the shot to `shots.py`, regenerate, and look at the
   PNG before referencing it.
9. Build the HTML, fix warnings (broken refs are warnings), and report
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
- **2 Essential elements**: one section per menu, in menu-bar order:
  task-oriented prose, then the menu's commands from
  `reference/commands.md`; plus mouse modes and shortcuts
- **3-9, by task, as the ORCA manual groups its methods**: 3 Energy
  models (UFF/UFF4MOF, charges, xTB, DFTB+, MACE, ORB-v3, MatterSim,
  dispersion, choosing one) · 4 Structure and optimisation
  (optimisers, the cell, scans, Prepare for simulation,
  interpenetration) · 5 Porosity and properties (Zeo++, the grid
  entries, the pore surface, PXRD) · 6 Frameworks and nets (MOF
  builder, blocks, layer nets, drawing a net, net search, molecule
  builder) · 7 Workflows and the command line · 8 Utilities and export
  · 9 Architecture
- **A method section has one shape**, the ORCA manual's: a short
  outline of the theory with its equations and numbered citations;
  practical advice as a few bullets; a worked example on a sample --
  an `xtal` command and the output it actually printed, or the steps
  in the window and what they showed; the settings (link the
  generated reference, never retype it); limitations. The theory and
  advice are chemistry, and Julius signs each one off before it ships.
- **Appendices**: A Reference (generated) · B Change log (the
  release notes, included) · C Glossary · D Bibliography · Index

## Keeping it current

After any change to menus, tips, Params or panels: regenerate the
reference, rebuild, and grep the prose for the old names
(`grep -rn 'Old label' docs/manual --include='*.md'`). A renamed
registry key breaks a `{ref}`, which the build reports; that is the
check.
