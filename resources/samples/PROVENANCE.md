# Where the sample structures came from

Every file in this folder is named here, with its source and what may
be done with it; `tests/test_samples.py` fails when one is not.  File
▸ Open Sample reads the catalogue in `xtalapp/samples.py`, which lists
thirty-nine of the forty-two.

## From the COD (`cod/`)

The Crystallography Open Database's data are CC0: no licence travels
with them, and these may be shipped, changed and passed on freely.
Each file is the COD's own CIF with the experiment taken out -- the
`_refln` and `_diffrn` items and loops, a powder refinement's profile,
and the SHELX `.res`/`.hkl` files and PLATON SQUEEZE report some
depositions embed -- and every other byte as downloaded.
`scripts/fetch_cod_samples.py` writes them; `--check` says whether the
COD still agrees.  Fetched 2026-09-23.

| File | COD | Publication |
|---|---|---|
| `cod/MOF-5.cif` | [1516287](https://www.crystallography.net/cod/1516287.html) | Lock et al., *J. Phys. Chem. C* **114**, 16181 (2010), [10.1021/jp103212z](https://doi.org/10.1021/jp103212z) |
| `cod/HKUST-1.cif` | [4002052](https://www.crystallography.net/cod/4002052.html) | Peterson et al., *Chem. Mater.* **26**, 4712 (2014), [10.1021/cm501138g](https://doi.org/10.1021/cm501138g) |
| `cod/ZIF-8.cif` | [7249359](https://www.crystallography.net/cod/7249359.html) | De Zitter et al., *CrystEngComm* **26**, 5644 (2024), [10.1039/D4CE00735B](https://doi.org/10.1039/D4CE00735B) |
| `cod/UiO-66.cif` | [4512072](https://www.crystallography.net/cod/4512072.html) | Øien et al., *Cryst. Growth Des.* **14**, 5370 (2014), [10.1021/cg501386j](https://doi.org/10.1021/cg501386j) |
| `cod/MIL-101.cif` | [4000663](https://www.crystallography.net/cod/4000663.html) | Lebedev et al., *Chem. Mater.* (2005), [10.1021/cm051870o](https://doi.org/10.1021/cm051870o) |
| `cod/NU-1000.cif` | [7230579](https://www.crystallography.net/cod/7230579.html) | Islamoglu et al., *CrystEngComm* **20**, 5913 (2018), [10.1039/C8CE00455B](https://doi.org/10.1039/C8CE00455B) |
| `cod/MIL-100.cif` | [7102029](https://www.crystallography.net/cod/7102029.html) | Horcajada et al., *Chem. Commun.* 2820 (2007), [10.1039/b704325b](https://doi.org/10.1039/b704325b) |
| `cod/MOF-74.cif` | [1517474](https://www.crystallography.net/cod/1517474.html) | Queen et al., *Chem. Sci.* **5**, 4569 (2014), [10.1039/C4SC02064B](https://doi.org/10.1039/C4SC02064B) |
| `cod/PCN-222.cif` | [4329555](https://www.crystallography.net/cod/4329555.html) | Morris et al., *Inorg. Chem.* **51**, 6443 (2012), as MOF-545(Fe), [10.1021/ic300825s](https://doi.org/10.1021/ic300825s) |
| `cod/MOF-808.cif` | [4121463](https://www.crystallography.net/cod/4121463.html) | Furukawa et al., *J. Am. Chem. Soc.* **136**, 4369 (2014), [10.1021/ja500330a](https://doi.org/10.1021/ja500330a) |
| `cod/MIL-53.cif` | [1502688](https://www.crystallography.net/cod/1502688.html) | Mulder et al., *J. Phys. Chem. C* **114**, 10648 (2010), [10.1021/jp102463p](https://doi.org/10.1021/jp102463p) |
| `cod/MIL-88B.cif` | [7100637](https://www.crystallography.net/cod/7100637.html) | Serre et al., *Chem. Commun.* (2006), [10.1039/b512169h](https://doi.org/10.1039/b512169h) |
| `cod/Mn-BTT.cif` | [4111257](https://www.crystallography.net/cod/4111257.html) | Dincă et al., *J. Am. Chem. Soc.* **128**, 16876 (2006), [10.1021/ja0656853](https://doi.org/10.1021/ja0656853) |
| `cod/cubic-EuHOTP.cif` | [4134597](https://www.crystallography.net/cod/4134597.html) | Skorupskii et al., *J. Am. Chem. Soc.* (2020); the COD calls it EuHHTP, [10.1021/jacs.0c01713](https://doi.org/10.1021/jacs.0c01713) |
| `cod/pbz-MOF-1.cif` | [4130966](https://www.crystallography.net/cod/4130966.html) | Alezi et al., *J. Am. Chem. Soc.* **138**, 12767 (2016), [10.1021/jacs.6b08176](https://doi.org/10.1021/jacs.6b08176) |
| `cod/Al-soc-MOF-1.cif` | [4129499](https://www.crystallography.net/cod/4129499.html) | Alezi et al., *J. Am. Chem. Soc.* **137**, 13308 (2015), [10.1021/jacs.5b07053](https://doi.org/10.1021/jacs.5b07053) |

Not in the COD when looked for on 2026-09-23: MOF-303, Cu3(HHTP)2 and
Cr-red-MOF-1 ([10.1021/jacs.5c16581](https://doi.org/10.1021/jacs.5c16581)).

## Prepared for simulation (`prepared/`)

Models made from the COD files above, which are left exactly as
deposited.  Each is its COD file through every step of
`xtal/core/prepare.py` -- deuterium as hydrogen, the declared
centring's primitive cell, disorder ordered into whole components,
solvent out of the pores, M3O trimers completed, hydrogens -- written
by `scripts/prepare_samples.py`, whose `--check` says whether the
code still makes them.  Being made from CC0 data, they carry no
licence either; they are this project's models, and citing one means
citing the structure it was made from as well.

What each needed, checked against the textbook formula of the
framework rather than only for clashes:

| File | Made from the COD file by |
|---|---|
| `prepared/MOF-5.cif` | the primitive cell |
| `prepared/HKUST-1.cif` | the primitive cell; copper sites left open |
| `prepared/ZIF-8.cif` | each methyl's hydrogens in one of two orientations |
| `prepared/UiO-66.cif` | Zr6O4(OH)4(bdc)6, the ideal framework: the refinement's ~27 % missing linkers are an average the ordering does not keep |
| `prepared/MIL-101.cif` | the primitive cell (4080 atoms), one OH and two waters per Cr3O trimer, arene hydrogens by ring; relaxed |
| `prepared/NU-1000.cif` | Zr6O4(OH)4(OH)4(H2O)4 -- the valence planner's eight terminal hydroxides left each node -4 |
| `prepared/MIL-100.cif` | as MIL-101, on Fe; relaxed |
| `prepared/MOF-74.cif` | the primitive cell |
| `prepared/PCN-222.cif` | the chloride ordered; the CIF's riding hydrogens on the node's terminal oxygens replaced by four OH and four waters |
| `prepared/MOF-808.cif` | Zr6O4(OH)4(btc)2(HCOO)6 exactly |
| `prepared/MIL-53.cif` | Cr(OH)(bdc): the mu2-OH the neutron structure never located; relaxed |
| `prepared/MIL-88B.cif` | pyridine and water out of the pores, one OH and two waters per trimer; relaxed |
| `prepared/Mn-BTT.cif` | each framework Mn's methanol made CH3OH; not relaxed (below).  One extra-framework Mn per cell, where the charge wants 1.5 -- this cell cannot hold half an ion |
| `prepared/cubic-EuHOTP.cif` | one whole chelating nitrate per Eu (the CIF shares a distal oxygen between two across a two-fold axis) and the cluster nitrate ordered.  **Its charge is not settled**: HOTP is redox-active and any cations in the pores were never located, so the oxygen on each Eu is a water, the neutral reading of an oxygen whose hydrogens were not located, and not a claim about the charge |
| `prepared/pbz-MOF-1.cif` | one acetate in six missing, as refined, each gap a hydroxide and a water; relaxed |
| `prepared/Al-soc-MOF-1.cif` | one tilt of each terphenyl ring -- the CIF gives both at full occupancy, and its formula counts both -- a chloride per trimer and three waters on it; relaxed |

**Relaxed** means positions only, at the experimental cell, with
ORB-v3 (`conservative-inf-omat`, float64) and D3(BJ) through
torch-dftd at MOFSimBench's settings (xc pbe, 40 Bohr cutoff, BJ
damping), L-BFGS to a largest force of 0.03 eV/A, and only where the
refined linker geometry was out of line.  UFF was tried first and made
MIL-88B worse; MACE-MP-MOF0 knows no Cr, Mn or Eu.  The bonding was
checked unchanged by every relaxation.

| File | Precision | Steps | Heavy atoms moved (rms) | What it fixed |
|---|---|---|---|---|
| `prepared/MIL-100.cif` | float32-high | 217 | 0.30 A | ring C-C 1.45-1.58 to 1.39-1.40 A; C-O 1.23-1.36 to 1.26-1.29; O-C-O 116-123 to 124-128 degrees; ring-carboxylate C-C to 1.61 to 1.47-1.50 |
| `prepared/MIL-101.cif` | float32-high | 225 | 0.33 A | ring C-C to 1.46 to 1.38-1.41 A; C-O 1.21-1.36 to 1.26-1.29; O-C-O 115-126 to 125-128 degrees |
| `prepared/MIL-88B.cif` | float64 | 59 | 0.19 A | O-C-O 118 to 126-128 degrees; C-O to 1.32 to 1.26-1.29 A |
| `prepared/MIL-53.cif` | float64 | 16 | 0.11 A | carboxylate C-O 1.17 to 1.28 A; ring angles 116-122 to 120-121 degrees |
| `prepared/Al-soc-MOF-1.cif` | float64 | 302 | 0.26 A | the ordered ring's 88 degree angle and 1.33 A bond to 118-122 degrees and 1.39-1.41 A |
| `prepared/pbz-MOF-1.cif` | float64 | 327 | 0.33 A | acetate C-O to 1.47 to 1.26-1.29 A; O-C-O to 132 to 126 degrees |

float32-high above 2000 atoms, because float64 needs 4.4 GB for
MIL-100 on an 8 GB laptop; measured on MIL-88B relaxed both ways, the
two give the same structure to 0.001 A on every heavy atom.
**MIL-100's file states 24 of its bonds**: a quarter of its trimers'
waters relax to 2.28-2.31 A from their iron, the trans effect of the
mu3-oxo, and the Fe-O distance rule stops at 2.28 -- still on the
iron, but perceived as loose water without the bond written down.
**Mn-BTT was relaxed and not kept**: its extra-framework Mn slid
1.42 A and changed four bonds, a cell one half-charge short, while the
framework's own geometry had needed nothing.

## Shipped since the early phases

### From the CCDC

Three files carry the Cambridge Crystallographic Data Centre's header.
`CFA1.cif`'s says it is for bona fide research and may not be copied
or passed on; `MFU4l.cif`'s refers to the CCDC's access policy, and
`Ni2Cl2BTDD.cif`'s says neither.  **That is a risk this folder
carries knowingly**: Julius chose on 2026-09-23 to keep them as they
are and to add the COD set beside them rather than in their place.  MFU-4l is the project's stress
case, and nothing in the COD replaces it.

| File | Source |
|---|---|
| `MFU4l.cif` | CSD download, CCDC 776578 ([10.5517/ccv22xw](https://doi.org/10.5517/ccv22xw)); Denysenko et al., *Chem. Eur. J.* (2011), [10.1002/chem.201001872](https://doi.org/10.1002/chem.201001872).  Downloaded 2025-02-04 |
| `Ni2Cl2BTDD.cif` | CSD refcode POSWUS, CCDC 1951829, exported by ConQuest; *J. Am. Chem. Soc.* **141**, 13858 (2019) |
| `CFA1.cif` | CFA-1, the CCDC copy of the electronic supplementary material to a *Dalton Transactions* paper (2013) |

### From RASPA

Both written by RASPA 1.0, as their `_audit_creation_method` says, and
carrying the citation of the structure they model.

| File | Source |
|---|---|
| `HKUST1.cif` | Chui et al., *Science* **283**, 1148 (1999) |
| `UIO66.cif` | Cavka et al., *J. Am. Chem. Soc.* **130**, 13850 (2008).  Written in P1 |

### Models, and exports of unrecorded origin

| File | Source |
|---|---|
| `MOF-5.cif` | A VESTA export in P1.  Where the model came from is not recorded |
| `ZIF-8.cif` | A Materials Studio export in P1, dated 2008-03-16.  Origin not recorded |
| `zn_oac.cif` | CFA-1 modelled ordered and written in P1 from Materials Studio, dated 2022-12-12 |
| `MIL53.cif` | Written by Crystal Builder on 2026-09-16: a PORMAKE build on `acs` with node N134 and a benzene linker (block `acs-N134-c1ccc_cc1`) |
| `NiHITP.cif` | Written by Crystal Builder on 2026-09-20 from a Pawley-refined Ni3(HITP)2 model (block `NiHATP_CmCm_Pawleyconstant_go`) |
