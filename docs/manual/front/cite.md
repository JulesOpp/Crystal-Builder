# How to cite

:::{note}
Crystal Builder has no publication or DOI of its own yet.  Until it
does, cite the release you used by its version number and repository,
<https://github.com/JulesOpp/Crystal-Builder>.
:::

Crystal Builder runs other people's methods and programs, and each
calculation should cite the work behind it.  Cite what you used:

| If you used | Cite |
|---|---|
| Symmetry detection, standardisation, Wyckoff positions | spglib {cite}`togo2024spglib` |
| Reading and writing CIF, space-group tables | gemmi {cite}`wojdyr2022gemmi` |
| The COD samples | the Crystallography Open Database {cite}`grazulis2012cod`, and the structure's own publication, named in the file |
| UFF | {cite}`rappe1992uff` |
| UFF4MOF parameters | {cite}`addicoat2014uff4mof`, {cite}`coupry2016uff4mof2` |
| QEq charges | {cite}`rappe1991qeq` |
| EQeq charges | {cite}`wilmer2012eqeq` |
| xTB: GFN1-xTB, GFN2-xTB, GFN-FF | {cite}`grimme2017gfn1`, {cite}`bannwarth2019gfn2`, {cite}`spicher2020gfnff`; the xtb program {cite}`bannwarth2021xtb` |
| DFTB+ | {cite}`hourahine2020dftbplus`, and the method: {cite}`porezag1995dftb`, {cite}`elstner1998scc`, {cite}`gaus2011dftb3` |
| MACE, MACE-MP-0, MACE-MP-MOF0 | {cite}`batatia2022mace`, {cite}`batatia2025macemp0`, {cite}`elena2025macemof0` |
| ORB-v3 | {cite}`rhodes2025orbv3` |
| MatterSim | {cite}`yang2024mattersim` |
| The machine-learned engines, through ASE | {cite}`larsen2017ase` |
| D3 dispersion | {cite}`grimme2010d3`, with Becke--Johnson damping {cite}`grimme2011bj` |
| The optimisers: L-BFGS, FIRE, ABNR | {cite}`liu1989lbfgs`, {cite}`bitzek2006fire`, {cite}`brooks1983charmm` |
| A relaxed scan's held coordinate | the projection-and-restore constraint of SHAKE {cite}`ryckaert1977shake` |
| Interpenetration, Class Ia and Class II | {cite}`blatov2004interpenetration` |
| Porosity with Zeo++ | {cite}`willems2012zeopp` |
| Porosity from the grid entries | SciPy's KD-tree {cite}`virtanen2020scipy` |
| A powder pattern | the pseudo-Voigt profile {cite}`wertheim1974pseudovoigt` and the Caglioti width relation {cite}`caglioti1958width`; structure factors through gemmi {cite}`wojdyr2022gemmi` |
| The MOF builder (PORMAKE) | {cite}`lee2021pormake`; the block fit is Kabsch's {cite}`kabsch1976` |
| The molecule builder | SMILES {cite}`weininger1988smiles`, the ETKDG embedding {cite}`riniker2015etkdg` and MMFF {cite}`halgren1996mmff`, through RDKit |
| Net names, transitivity and layer nets from the RCSR | {cite}`okeeffe2008rcsr`; coordination sequences and point symbols as defined in {cite}`blatov2010symbols` |
| Net identification by Systre | {cite}`delgadofriedrichs2003systre` |

The {doc}`bibliography </back/bibliography>` gives every reference in
full.
