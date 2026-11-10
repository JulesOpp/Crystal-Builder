# From a synthesis

What a metal salt, linkers, solvents and a temperature are likely to
make, read off the published syntheses nearest to them. Modules ▸
From a synthesis…, `xtal run synthesis.forecast`. This is the design
record: what it is for, what was considered, what was chosen and why,
and how it is tested. What is still owed is in `docs/TODO.md`.

## What it is for

A chemist planning a synthesis wants to know which framework it will
probably give before going to the oven -- and a person building a
hypothetical one wants to start from a node and a net that real
syntheses of that metal and linker produce, rather than from the
2400 nets in the picker. The answer has to be honest about how much
it knows: a vote among strangers is a guess, and has to read as one.

Success is:

- the syntheses everybody knows come out right (UiO-66 is `fcu`,
  HKUST-1 is `tbo`);
- on syntheses held out of the table, the net that was made is in the
  first five more often than not, and the number is measured and
  quoted, never asserted;
- every answer names the precedents it stood on and says how far the
  query is from the nearest;
- nothing leaves the machine: no network, no third-party service;
- what it names can be built: the best of the voted nets and nodes
  that comes out as asked opens in a tab.

## Approaches considered

**A. Ask a web service** (structsub.com's `/frameworks/forward` does
exactly this). Widest coverage, least work. Rejected: it needs the
network, the terms of use are unknown, and a desktop application's
answer would change under it without a release. Not used anywhere.

**B. A nearest-neighbour vote over a bundled open table** -- chosen.
The precedents are two open tables joined by CSD refcode: what formed
(CoRE MOF 2024's MOFid: nodes, linkers, net; CC-BY 4.0) and how it
was made (SynMOF-ME's metal, counter-ion, solvents, temperature; MIT).
A query is scored against every precedent and the nearest vote,
weighted by similarity. Transparent (each vote is a refcode a person
can look up), offline, a few hundred lines, and the source is a seam
another table can fill.

**C. A trained classifier** over the same table. Rejected for now:
only 323 precedents carry conditions, too few to train anything that
would beat the vote, and a model's answer cannot be traced to the
syntheses behind it, which is the thing that makes this answer
usable.

## Design

Three units, each testable alone.

| Unit | Does | Depends on |
|---|---|---|
| `scripts/synthesis_precedents.py` | Joins the two downloads into `xtal/mof/data/precedents.json.gz`, then measures the held-out accuracy and prints it | RDKit, the two files named on the command line |
| `xtal/mof/precedent.py` | Reads a query, scores it against a `Source`, votes | numpy-free; RDKit only to read a typed linker |
| `xtal/mof/candidates.py` | The linker as a block, the candidates, the test builds | the forecast, the catalogue, the MOF builder |
| `xtal/modules/synthesis.py` | The registry entries: the vote, and the vote then the builds | the three above |

**The table.** One record per CSD refcode *family*: `WIZMAV02` to
`WIZMAV13` are re-determinations of one compound and were eleven
votes for one paper's `fcu` before they were folded. The kept
determination is one MOFid could name a net for. MOFid's own words for
"no net" (`UNKNOWN`, `ERROR`, `NA`, `MISMATCH`, `TIMEOUT`) are not
nets. Linkers are stored once each, uncharged and canonical, with
their Morgan bits (radius 2, 2048), so loading costs no RDKit. 7870
precedents, 323 with conditions, 4336 with a named net, 200 KB.

**The similarity**, 0 to 1, a weighted mean:

| Term | Weight | Score |
|---|---|---|
| metal | 0.40 | 1 the same, 0.5 an analogue (`ANALOGUES`: Zr/Hf/Ce, the lanthanides, ...), else 0 |
| linker | 0.40 | each query linker's best Tanimoto among the precedent's, averaged |
| solvent | 0.10 | Jaccard of the PubChem CIDs |
| temperature | 0.05 | exp(-ΔT / 40 C) |
| counter-ion | 0.05 | Jaccard |

A condition missing on either side scores 0.5. Most precedents have
no conditions; scored 0 they would never vote, scored 1 they would
outvote the syntheses done the same way.

**The vote.** The nearest 50 (`NEIGHBOURS`, measured below) vote with
their similarity as weight on the node, the net and interpenetration.
A precedent with no net does not vote on the net, so a net's share is
out of the weight that named one. Nodes are tallied by their metals
(`Zr6`), not by SMILES, which writes one cluster several ways. Ties
are broken by refcode, so an answer is the same every time.

**The answer** (`Forecast`): the shares, the precedents with their
similarities and conditions, and a `Novelty` -- the closest
similarity, and whether the metal, the linker and the two together
are in the table at all -- whose sentence is the run's first line.
The module's report adds whether the builder has each net.

**Errors are results.** A source with no metal, no linker, more than
three, a linker that is neither a name nor a SMILES, a temperature
that is not a number or is outside -80 to 400 C: each is a failed run
naming what was wrong. A solvent that is not recognised is not an
error; it is left out of the comparison and the answer says so in
the row a person reads (not a tooltip).

## Building what it names

Build the likely frameworks… (`synthesis.build`,
`xtal/mof/candidates.py`) votes and then builds. Approaches weighed:
matching MOFid's node SMILES to a catalogue block atom for atom
(exact, but two writers draw one cluster two ways, which is why the
vote counts nodes by their metals), against matching by metals and
connection count (chosen: the catalogue's carboxylate clusters are
few enough per metal that the first two tried are nearly always one
cluster drawn twice). Three steps:

- **The linker as a block.** The typed linker's carboxylic acids
  become connection points: the carboxyl carbon *becomes* the `X`
  and its two oxygens go, because in this catalogue the carboxylate
  is the node's (N16 is Zn4O(CO2)6, E14 the phenylene between).
  Turning the carbon rather than deleting it keeps a double bond's
  E or Z, which is stored against its neighbours -- deleting them
  made fumarate `*C=C*`, as happy to embed cis. Two carboxylates make
  an edge; three or more an organic node (BTC in tbo), joined to the
  metal directly. A linker with none is refused by name: a pyridyl or
  azolate meets its metal in a node the catalogue draws differently.
  Embedded arms-out as the isoreticular series is, written as
  `SYN-<hash>.xyz` into the workspace's `blocks/`, where the MOF
  builder reads the blocks a person draws.
- **The plan.** Each of the first five voted nets the builder has,
  with each of the first five voted nodes, filled with **plain**
  carboxylate clusters -- metals, oxygens and one carbon per
  connection, no nitrogen -- of exactly the voted metals and the
  slot's connection count, two per slot at most. Plain only: falling
  back on any cluster with the right metal put a zinc porphyrin on the
  first row of Zn + BDC. Ranked by net share times node share. What
  cannot be tried is said once each: a net the builder lacks, a net
  with no slot for the linker, a node with no cluster.
- **The trial.** Built in rank order for 30 s (a parameter), checked
  between builds; at least one is always built, and the rest are
  listed untried. Anything PORMAKE raises fails that row and the next
  is tried. A build counts when the builder reads back the net it
  asked for; the best is the highest-ranked such build with nothing
  overlapping, and it opens in a new tab with a warning that it is a
  starting geometry, not the phase that forms. Every row carries the
  `xtal run mof.build` parameters that build it again.

The vote alone stays its own action and never imports the builder,
so it still answers in a second.

## How well it does

Measured by the script, each synthesis with conditions and a named
net held out by refcode family in turn (146 of them): the net made
first / in the first five --

| voters | 5 | 10 | 25 | 50 |
|---|---|---|---|---|
| | 31 / 42 % | 25 / 47 % | 25 / 56 % | 24 / 62 % |

Fifty: one point of the first place for six of the list, and the list
is what a person reads. Generous, because a paper's series of related
structures stays in the table when one of them is held out (no DOI to
hold out a paper by). 146 is a small sample.

## Testing

`tests/test_synthesis.py`, headless:

- **Reading**: salts by name and by formula, hydrates, oxidation
  states, the counter-ions that contain each other (perchlorate and
  chloride, hydroxide and oxide); solvents read and unread; commas
  inside names; a linker the same as acid or anion.
- **Similarity and vote** on a small table written in the test,
  through the `Source` seam, so no RDKit and exact expectations:
  unknown conditions rank between agreeing and not, shares sum to
  one, a precedent with no net votes on the node only, one node
  written two ways is one node, ties broken the same every time.
- **The script** on a few source rows written in the test: the join,
  folding a refcode family, the words that are not nets, counter-ion
  aliases.
- **The shipped table**: its own invariants (indices in range, bits
  in range, nets lower case, one record per family, the attribution
  inside), and its linker bits are what `linker_key` gives today -- a
  new RDKit or a changed fingerprint would otherwise compare a typed
  linker against stale bits and every answer would quietly drift.
- **Known syntheses** come out first (UiO-66, HKUST-1), and a slow
  test re-measures the held-out accuracy against the number `BASIS`
  quotes.
- **The module and the CLI**: registered, greys out without RDKit,
  returns a report and no structure, each bad query a failed run by
  name, and `xtal run synthesis.forecast` end to end in a subprocess.
- **Building** (`tests/test_synthesis_build.py`, on forecasts written
  by hand): carboxylates to points (BDC, BTC, fumarate trans and
  maleate cis, NH2-BDC), the acid and anion one block, pyridyl,
  azolate and ester refused; only plain clusters offered; a ditopic
  linker in the edges, a tritopic one a node beside Cu2 on tbo; best
  first; each skip said once; a candidate's rebuild line parsed back
  to its request; a failed build (PORMAKE's own assertion included)
  one row and the next still tried; the time and Stop leave the rest
  untried; the best is confirmed and clean. UiO-66 and HKUST-1 from
  their syntheses end to end, and the window opens the UiO-66 build
  in a new tab with its BDC block kept (`tests/test_synthesis_ui.py`).
- **Mutations**: each rule above was broken on purpose once and a
  test failed for it -- the vote's seven, and the build's six
  (non-plain clusters, the deleted carboxyl, a zero budget building
  nothing, worst first, an overlapping best, a narrow `except`).
