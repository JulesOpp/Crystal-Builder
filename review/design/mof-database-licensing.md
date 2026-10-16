# Shipping a curated MOF library: what is safe to redistribute

> **Written 2026-09-19.** Licences, terms of service and dataset contents
> were checked on that date and **will drift** — re-verify before shipping.
> Sizes were measured, not estimated. **Not legal advice.**

Julius said of structure databases (idea 12): *"Depends on licensing and the
size of databases. A small database of curated MOFs could also be useful.
MOF-#, NU-#, HKUST-#, etc."* This answers both halves: what may be shipped,
and what it costs.

## The short answer

**Source from COD (CC0), regenerate anything COD lacks, ship a NOTICE
file.** ~30 curated structures costs **200–700 KB raw, 50–150 KB gzipped** —
noise beside any desktop binary. Avoid everything CSD-derived.

## What may be redistributed

| Source | Licence | Verdict |
|---|---|---|
| **COD** | **CC0** — *"dedicated to the public domain"* | **Use this.** Attribution is courtesy, not condition. ~535k entries. |
| **Regenerated from a paper** | yours | **Use this** for gaps. Facts are not copyrightable (*Feist* 1991; Moglen: *"If you extract only the actual coordinate data you have no copyright liability"*). |
| CoRE MOF **2025 SI subset** | CC BY 4.0 | Legitimate fallback — **99.8 % journal-SI-derived, not CSD**. Needs a NOTICE: cite *Matter* 8 (2025) 10.1016/j.matt.2025.102140, name the licence, state files were modified. |
| QMOF | CC BY 4.0 | Usable, but these are **DFT-relaxed**, not experimental — wrong if you want to show "the published structure". Rosen deliberately withholds the CSD input geometries. |
| CoRE MOF **2019** | CC BY 4.0 *(tagged)* | **Avoid.** 94.2 % of its 19,081 files are refcode-named (`ABAVIJ_clean_pacman.cif`) i.e. CSD-derived. The 2025 restructuring — which routes the CSD portion through CCDC instead — reads as a tacit acknowledgement that the tag over-reached. |
| **CSD MOF Collection** | CC BY-**NC**-**SA** | **Hard no.** NC kills commercial use; SA is copyleft over your data. |
| **CCDC Access Structures** | ToS | **Hard no.** *"These services must not be used to systematically download or redistribute these structures… Programmatic access is not permitted."* |
| ICSD | proprietary | No. (Also inorganic — MOFs go to the CSD.) |

**The nuance worth understanding:** CCDC nowhere asserts *copyright in the
raw coordinates*. Their basis is a **licence contract** plus, in the EU/UK,
**sui generis database right** over the curation. That is why the MOF
Collection can be CC BY-NC-SA at all — they are licensing their editorial
work, not the facts. It does not make breaching the ToS safe; it means the
bright line is contractual, and routes 1 and 2 sidestep it entirely.

## All six headline MOFs exist in COD — verified

Queried the COD API, downloaded each, parsed with gemmi:

| MOF | COD ID | Space group | *a* (Å) |
|---|---|---|---|
| MOF-5 / IRMOF-1 | **1516287** | *Fm*-3*m* | 25.8247 |
| HKUST-1 | **4002052** | *Fm*-3*m* | 26.2711 |
| ZIF-8 | **7249359** | *I*-43*m* | 16.902 |
| UiO-66 | **4512072** | *Fm*-3*m* | 20.7465 |
| MIL-101(Cr) | **4000663** | *Fd*-3*m*:2 | 88.869 |
| NU-1000 | **7230579** | *P*6/*mmm* | 39.2679 |

Nothing missing. MOF-5 expands to **424 atoms** — matching the app's own
`MOF-5.cif` exactly.

## The precedent: what RASPA2 does

**RASPA2** (MIT) ships **108 MOF CIFs** (3.99 MB), including exactly this
target list — `IRMOF-1..16`, `Cu-BTC`, `ZIF-8`, `UIO-66`, `MIL-47/53/88/100/101/140`,
`NU-100SP`, `NU-108`. And the method is the point. `IRMOF-1.cif` reads:

```
_audit_creation_method RASPA-1.0
_audit_author_name 'David Dubbeldam'
_citation_author_name  'M. Eddaoudi, J. Kim, N. Rosi, ... and O.M. Yaghi'
_citation_title 'Systematic design of pore size and functionality in ...'
```

**Regenerated files with a citation block crediting the original paper** —
not verbatim CCDC downloads. That is the community norm and the legally
right shape: reproduce the facts, credit the discovery.

Contrast **iRASPA**, which ships ~49 MB of **CoRE MOF 2019** inside an
MIT repo with no data licence, no CC BY attribution and no CSD notice — a
precedent for what people do, not a model to copy. pymatgen ships an
`ICSD59959.cif` test fixture. Avogadro2 is the good model: BSD data with
provenance stated in the README.

## Size — measured

Six COD entries, stripped to cell + symmetry + `atom_site` with gemmi:

| | asym. unit | gzipped | P1 atoms | P1 CIF | P1 gz |
|---|--:|--:|--:|--:|--:|
| MOF-5 | 580 B | 285 B | 424 | 16,409 B | 2,408 B |
| HKUST-1 | 537 B | 279 B | 624 | 23,901 B | 3,546 B |
| ZIF-8 | 646 B | 329 B | 348 | 13,459 B | 2,430 B |
| UiO-66 | 793 B | 348 B | 688 | 26,104 B | 3,851 B |
| NU-1000 | 1,244 B | 545 B | 510 | 19,864 B | 3,149 B |
| MIL-101 | 4,322 B | 1,628 B | **16,000** | 624,654 B | 112,683 B |

Three practical notes:

1. **Strip `_refln` loops unconditionally.** UiO-66's COD download is 286 KB
   and NU-1000's 301 KB *only* because of embedded reflection tables (13,836
   and 8,387 lines against 25 and 46 `atom_site` rows). Stripping removes
   ~99.7 % of the bytes.
2. **Ship primitive cells for MIL-100/101.** MIL-101 is 16,000 atoms in the
   conventional cell; RASPA2's primitive version is 75 % smaller.
3. **Ship asymmetric units + symmetry ops**, not P1 — a 28× saving, and this
   app expands on read anyway.

**Budget for 30 structures: ~200–700 KB raw, ~50–150 KB gzipped.** Gzip
ratio measured at **5–8×** on real CIF text (7.9× over 15 RASPA2 files).
For comparison `packaging/bundle.py` already ships nine samples, and VESTA
alone is 22–25 MB.

## Recommendation

1. **Source from COD.** CC0, verified to hold every headline MOF.
2. **Regenerate what COD lacks**, RASPA2-style, with `_audit_creation_method`
   and a `_citation_*` block.
3. **CoRE MOF 2025 SI** as a fallback, with the required NOTICE.
4. **Never** CSD MOF Collection, Access Structures, ICSD, or refcode-named
   CoRE MOF 2019 files.
5. **Ship a `DATA_LICENSES` file** naming each structure's source, COD ID,
   original citation and licence. This is the one thing almost every project
   surveyed got wrong, and it is cheap.

## Grey areas, flagged

Not resolved, and a short opinion from counsel would be cheap insurance if
this ever ships commercially:

- Whether EU/UK database right bites on ~30 structures extracted from a
  12,505-entry collection — untested for CIFs.
- Whether CCDC's contractual ban binds someone who never accepted the terms.
- CoRE MOF 2019's CC BY tag over CSD-derived files.

Routes 1 and 2 avoid all three.
