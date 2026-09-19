# Sub-research: standards, desktop expectations, distribution (condensed by coordinator)

## Interchange — what is vendorable
- **mmCIF/PDBx**: gemmi (already a dependency) reads/writes it. Zero new deps.
- **POSCAR/CONTCAR**: ase.io.vasp (ase already an extra) or ~80 lines by hand.
- **LAMMPS data**: pymatgen LammpsData / ase lammps-data; lammps-interface is the MOF standard (UFF4MOF!). Bonded topology is the hard part — CB already has the graph and the UFF typer, which is exactly what lammps-interface reconstructs.
- **GROMACS**: explicit gap in literature (lmp2gro 2026 JCIM; OBGMX does UFF→GROMACS for MOFs).
- **RASPA**: raspa2.py wrapper; hydraspa prepares GCMC inputs. No GUI does it.
- **QE / CP2K / CASTEP**: ase calculators write inputs; pymatgen.io.cp2k.
- **OPTIMADE**: `optimade` PyPI package has adapters to/from pymatgen/ASE/**CIF** and a client that queries every provider (COD, MP, OQMD, AFLOW…) at once. One dependency = a "search every database" door.
- **Materials Project**: mp-api (June 2026 backend migration).
- **COD**: REST API, CIF native; OPTIMADE provider too.
- **CSD**: proprietary Python API; only as optional plugin against user's licensed install.
- **pymatgen Structure JSON** (MSONable as_dict) and **ASE .traj**: both trivial to emit from xtal.
- Notebook reproducibility is bad (4% identical results over 800k notebooks; 2/19 sci notebooks reproducible) — argues FOR the self-contained .xtalproj.

## 2026 expectations for a VESTA-class desktop app
- Embedded Python console (qtconsole/Jupyter-in-Qt pattern) — CB's Qt-free core makes this cheap.
- Plugin ecosystem: ParaView split server/client plugins; Blender Extensions platform. CB has entry-point plugins but no registry/marketplace.
- Dark mode: 80%+ prefer; TODO.md line 2.
- HiDPI in Qt+VTK: named bug class (device-pixel-ratio in GL surfaces).
- Autosave/crash recovery: "single most critical showstopper for trust". CB has none documented.
- Headless parity: ImageJ2/ilastik/mzmine precedent; caveat that GUI-coupled plugins break — CB's wall (test_core_is_headless) is the right defence.
- Command palette (Cmd-K) is now the expected power-user vocabulary.
- Vector export SVG/PDF/EPS for journals — CB has PXRD/bands via matplotlib; the 3D view has no vector path (VTK gl2ps exists).
- glTF export (ChimeraX does it, ~100k tri budget) → web/Three.js; MolecularNodes for Blender. CB has STL via Blender.
- 3Dmol.js: embeddable web viewer in two lines — "share as HTML" export.
- Auto-update: Sparkle for macOS; no Python bridge — custom appcast client needed.
- Signing/notarisation: $99/yr, few hours first time, 10 min per release once in CI. 3D Slicer documents their process.
- universal2 needs every wheel universal2 — VTK isn't; CB's two-build decision is correct.
- Linux: AppImage lowest friction; Flatpak/Flathub is the "app store".
- conda-forge: Qt6 default since Aug 2025; grayskull auto-recipes from PyPI; don't mix pip PySide into conda.
- Jupyter: anywidget is the modern way to get a viewer widget from the headless core.

## Distribution / community precedents
- VESTA: closed binary, one author, cited via 2008 J Appl Cryst paper.
- Avogadro: BSD, Kitware umbrella, plugins, PyPI package + app.
- OVITO: PhD project → Basic (free) + Pro (paid) → OVITO GmbH 2020 because unfunded development wasn't sustainable.
- Olex2: EPSRC grant-seeded, free forever, OlexSys Ltd.
- Norm: PyPI → conda-forge bot → GitHub Releases for binaries.
- JOSS: reviews functionality/docs/tests/CI/licence; pymatgen-analysis-defects (2024) is a template. CB's test suite and CLAUDE.md would review well.
- Zenodo: DOI per release via GitHub integration, CITATION.cff in repo.
- Docs: Sphinx (autodoc for xtal/) — matches Phase 3/4 plan; Read the Docs hosting free.
