# Where the sample structures came from

Every file in this folder is named here, with its source and what may
be done with it; `tests/test_samples.py` fails when one is not.  File
▸ Open Sample reads the catalogue in `xtalapp/samples.py`, which lists
twenty-three of the twenty-six.

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
