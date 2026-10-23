# The AI assistant drives the window

The design record for PR #47 (2026-10-01).

## Goal

An AI assistant can drive the running Crystal Builder window, from the
packaged app as much as from a source install, through any MCP client,
with every edit landing as an undo step in the tab the person has open.
On the way, the answers an assistant reads are cut to a size a model can
hold, three rules that lived only in the skill's prose move into the
API, and a harness measures whether an agent given the skill follows it.

## What is there today

`xtal/agent/` (shipped 2026-09-26): a `Session` of 35 verbs, each the
command the window pushes for the same gesture; `VerbResult` answers
with closed diagnostic codes; `inspect`, `render`, `capabilities`; the
skill in `xtal/agent/skill/`, held to the code by
`tests/test_agent_skill.py`; `xtal` CLI commands with `--json`.

Measured on this machine (MOF-5 sample, 424 atoms in P1): open 0.03 s,
`inspect()` 0.06 s, UFF optimise 0.26 s, grid porosity 0.74 s, render
1.44 s. `str(inspect())` is 3.3 kB; `inspect().to_json()` is 172 kB;
`capabilities().to_json()` is 127 kB.

What it cannot do: reach anyone who installed the DMG or EXE (no `xtal`
entry point is frozen in, and the skill tells the agent to use one);
touch the open window (a `Session` is its own process, and the window
does not watch files); answer in a size a model can read; enforce its
own protocol on an agent that did not load the skill.

## Design

### 1. One tool layer, two hosts

```
Claude Code / Desktop / Cursor / Codex
        | stdio                        | HTTP (Claude Code may go direct)
        v                              v
  `xtal mcp` (shim) --proxy-->  window: http://127.0.0.1:<port>/mcp
        | no window running                |
        v                                  v
  HeadlessHost(Session)             WindowHost(WindowSession)
        \------------- xtal/agent/tools.py -------------/
                (one tool per verb, over any Session)
```

**`xtal/agent/tools.py`** (core; imports `mcp` lazily, so the core
without the extra still imports). `register(server, host)` adds one MCP
tool per verb in `capabilities.VERBS`, with the verb's own keyword
parameters and docstring, plus:

| Tool | Does |
|---|---|
| `documents` | the host's open sessions: path, name, atoms, modified, current |
| `open(path, workspace)` | `host.open`: a new session (window: a new tab) |
| `new(...)`, `build(action, workspace, **params)` | as the classmethods |
| `switch(path)` | makes that session current (window: raises its tab) |
| `capabilities(verbose)` | compact by default (see §4) |
| `help_for(name)` | as now |

Every tool returns `VerbResult.to_dict()` as JSON text. `inspect`
returns `Inspection.to_dict(sites=...)`. `render` returns the answer
and, when it drew, the PNG as MCP image content as well.

A `Host` is three methods: `current() -> Session`, `open(path,
workspace) -> Session`, `sessions() -> list[Session]`. Two hosts:

- `HeadlessHost` (`xtal/agent/serve.py`): a dict of `Session`s keyed by
  path; `open` of a path already held returns it.
- `WindowHost` (`xtalapp/agent_host.py`): one `WindowSession` per open
  `Document`, made on demand and dropped when the tab closes; `current`
  is the agent's **own** current session, set by `open` and `switch`
  (and, before it has one, the tab in front when it first asks) -- it
  does not follow the person's clicks, which sent the next edit into
  whatever tab they had raised. Once that tab is closed, `current`
  raises `LookupError` ("the document you were working on was closed;
  open or switch to one"), which the tools answer as a refusal. Every
  `WindowSession` answer carries `data["document"]`, the tab's path
  (`inspect`'s, `document`); headless answers are unchanged. `open` is
  `window.open_path(path, report=False)`.

**`WindowSession(Session)`**: `structure` is a property reading
`document.structure`; `entry` is `document.entry`; `path` is the
document's. The plumbing it overrides, and nothing else:

| Session | WindowSession |
|---|---|
| `_push(verb, command, ...)` | `document.run(command)` on the GUI thread, then the same `VerbResult` |
| `_operate(verb, command, args)` | preview as now; push via `document.run` |
| `undo()` / `redo()` | `document.undo()` / `document.redo()` |
| `save(path)` | `document.save()` / `save_as(path)` |
| `history()` | the document's stack labels |

A test walks every verb in `VERBS` that changes the structure and shows
it lands as exactly one entry on `document.stack` with the same label
the window would give, and that `undo` takes it back in the tab.

**Transport**: the `mcp` SDK's streamable HTTP server, bound to
`127.0.0.1` only, with a bearer token generated per launch (DNS
rebinding and any other local browser page are refused). The port
defaults to 7781 and falls back to an OS-chosen port when busy. A
discovery file `mcp.json` beside the application log (`xtalapp.applog`
knows the folder) holds `{port, token, pid, version}`, is written with
mode 0600 when the server starts and removed when it stops or the
window quits.

**`xtal mcp`** (stdio, in `xtal/agent/serve.py`): reads the discovery
file; if its `pid` is alive and the port answers, proxies every tool
call to the window using the SDK's client (`list_tools` once, then
`call_tool` through); otherwise runs `HeadlessHost` in process.
`--window` fails when no window answers; `--headless` never proxies.
Without the `mcp` extra it exits 2 saying what to install
(`xtal.install.command("mcp")`).

### 2. The window side

**Threading.** The server runs in a `QThread` (`xtalapp/workers.py`
pattern: a `QObject` moved to a thread, stopped from
`MainWindow.closeEvent`). A `Bridge(QObject)` living on the GUI thread
has one slot `call(fn) -> result`; `WindowSession` invokes it with
`QMetaObject.invokeMethod(..., Qt.BlockingQueuedConnection)` and reads
the result (or re-raises the exception) from a holder. Calculations
(`energy`, `optimize`, `thermochemistry`, `run`) execute on the server thread over
`document.structure.copy()`, as the Force Field panel does; only
reading the structure for the copy and applying the result cross to the
GUI thread.

**Gates.** Every tool call is refused with `WINDOW_BUSY` (error) while
`document.is_playing` or `window.has_running_calculation()`. An agent
calculation registers itself so `has_running_calculation()` counts it
(quitting asks first, and another agent call is refused). The person's
edits are not refused meanwhile; they are protected at apply time: the
tab's revision is read before an agent calculation, and if it moved --
or the tab was closed -- the apply is refused with `DOCUMENT_CHANGED`
(error) and the run folder keeps the result (`RESULT_NOT_APPLIED`
names it).

**Switching on.** Preferences gets an **AI assistant** page
(`xtalapp/dialogs/preferences.py`, after Engines):

- "Let an AI assistant connect to this window" (`QCheckBox`, setting
  `agent/serve`, default off). On: start the server and write the
  discovery file. Off: stop it, remove the file.
- Port (`agent/port`, default 7781), applied on the next start.
- Status line: "Listening on 127.0.0.1:7781" / "Off" / the error if the
  port could not be bound.
- Two read-only lines with Copy buttons: the Claude Code command
  (`claude mcp add --transport http crystal-builder
  http://127.0.0.1:7781/mcp --header "Authorization: Bearer ..."`) and
  the stdio command (the full path of the `xtal` launcher, `mcp`), the
  one any client's config takes.

Help ▸ **Connect an AI assistant…** opens Preferences on that page.
Help ▸ *Set up an AI assistant* (the skill install) stays. While a
client is connected the status bar says so; each verb that lands shows
its message there for a few seconds, the way the window reports its own
operations.

**`render` in the window** grabs the current viewport on the GUI thread
(`viewport.save_image(path)`, the same call the manual's screenshot
script uses), honouring `view` by setting the camera first and
restoring it after. Headless `render` is unchanged.

### 3. The `xtal` CLI in the bundle

`packaging/macos.spec` and `packaging/windows.spec` gain a second `EXE`
named `xtal` from `xtal/cli.py:main` with `console=True`, sharing the
one `Analysis` and `COLLECT` (two `EXE`s in one `COLLECT` is
PyInstaller's documented multi-entry layout). On macOS it sits in
`Crystal Builder.app/Contents/MacOS/xtal`. `packaging/bundle.py` adds
`mcp` to `COLLECT` so its data and hidden imports are found; the
`mcp` extra is always in the bundle. `xtalapp/main.py --selftest`
checks the launcher exists beside the app and answers `capabilities`.

Headless `render` from the frozen launcher is `RENDER_UNAVAILABLE` with
a message to connect the window (a frozen app has no `-m`).

### 4. Right-sized answers

`Inspection` gains `site_groups`: sites grouped by `(element,
coordination, neighbour pattern)` where the pattern is the sorted
neighbour elements with distances rounded to 0.05 Å; each group has
`count`, `sites` (indices) and one example row. MOF-5's 424 sites
become about six groups.

`Inspection.to_dict(sites="problems")`: `"problems"` keeps only the
site rows a diagnostic's `where` names (plus any `OVERCOORDINATED` /
`UNBONDED_ATOM` site); `"all"` is today's output; `"none"` drops the
table. `to_json(sites=...)` the same. `str()` prints the groups, then
the problem rows, then the diagnostics; the 40-row table goes.
CLI: `xtal inspect --sites problems|all|none`. The MCP tool takes
`sites` with the same default.

`capabilities(verbose=False)`: engines and module actions with `name`,
`label`, `available`, `reason` only; `verbose=True` is today's. Actions
"performed by the window" are left out of both (the verbs cover them).
`help_for` is unchanged. CLI: `xtal capabilities --verbose`.

Asserted by tests on the MOF-5 sample: `inspect().to_json()` under
5 kB with the default, `capabilities().to_json()` under 4 kB.

### 5. Rules into the API

| Code | Level | Fires when |
|---|---|---|
| `BONDING_WOULD_CHANGE` | warning | after `optimize`, `bonding.perceive` of the result differs from `bonding.perceive` of the start; message counts bonds gained and lost. Nothing is recalculated. |
| `SCAN_SIZE` | info | `run` of a `scan.*` action with more than one point: the point count (axes' steps multiplied, times two when both directions are walked), and that each point is a relaxation written as it finishes |
| `WORKSPACE_IGNORED` | info | `Session.open(path, workspace=...)` where the file already sits inside another workspace, on `session.opened` |
| `IMAGINARY_MODES` | warning | `thermochemistry` (or the `forcefield.thermo` / `forcefield.infrared` runs) found modes below -50 cm-1, left out of H, S and G |
| `WINDOW_BUSY` | error | a window tool refused while a trajectory is open or a calculation runs (§2) |
| `DOCUMENT_CHANGED` | error | the tab changed during an agent calculation; the result was not applied (§2) |

All six go into `CODES` and `references/diagnostics.md`; the existing
test holds the two lists equal.

### 6. The eval harness

`tools/agent_eval/` (not in the wheel): `tasks/` with one folder per
task (`task.md` prompt, the input file, `expect.json`), `run.py`, and
a `README.md`. `run.py` installs the skill into a temporary project
(`xtal skill install --project`), runs `claude -p <prompt>
--output-format json` once per task in that project with Bash, Read
and Write allowed, then grades: every code in `expect.codes` must
appear in the final report; `expect.inspect` is a list of
`(diagnostic code, present|absent)` checked by `inspect()` of the
`.xtalproj` the agent saved; `expect.must_not_change` for the trimer
task checks the atom count. It prints a table and exits non-zero on a
failure. It uses the person's own Claude Code login; no key.

Tasks:

1. `copies-and-hydrogens`: a CIF with symmetry copies as sites and no
   H (the `Ni2Cl2BTDD`-style fixture from the tests). Expect
   `COINCIDENT_ATOMS` reported, then `PREPARE_STEP` lines; saved
   project free of `COINCIDENT_ATOMS` and `MISSING_HYDROGENS`.
2. `build-overlap`: a `mof.build` combination known to overlap. Expect
   `BUILD_OVERLAP` reported and no relaxation run on it.
3. `tied-scan`: a scan along a coordinate the group ties. Expect
   `MODULE_FAILED` reported as the answer, and no `reduce_to_p1` in
   the log unless the prompt asked.
4. `open-trimers`: a trimer framework (COD sample). Expect
   `OPEN_TRIMERS` and `CELL_NOT_NEUTRAL` reported, no `cap` in the log,
   and a question to the person in the report.
5. `short-relax`: "relax this" with `max_steps=3`. Expect
   `NOT_CONVERGED` reported in so many words.

### 7. Skill, docs, tests

- `SKILL.md`: a section *Connected to the window*: the tools are the
  verbs; `documents`/`switch`; `WINDOW_BUSY` means wait, not retry;
  the person is watching, so say what you are about to do in the tool
  call's message; `render` returns the picture. `references/api.md`
  gains the new parameters (`sites`, `verbose`) and `site_groups`;
  `references/diagnostics.md` the five codes.
  `tests/test_agent_skill.py` also holds every tool name the skill
  mentions to `tools.py`.
- README's agent section: connect the window (both commands), `xtal
  mcp`, the eval. `docs/RELEASE_NOTES.md`. `CLAUDE.md`: the map rows
  for `tools.py`, `serve.py`, `agent_host.py`; the invariant gains
  "and through the window's own `Document.run` when connected".
  `docs/TODO.md`: the owed MCP item closed; the manual chapter stays.
- `pyproject.toml`: `mcp = ["mcp>=1.30,<2"]` (the version tested), in `dev`.

### Tests, by part

1. Right-sizing: `site_groups` on rutile and MOF-5; `sites=` three
   ways; size bounds; CLI flags; `str()` shape.
2. Rules: each code fires on a fixture and not on its opposite;
   `BONDING_WOULD_CHANGE` on dry ice with a bond stretched by a
   crafted calculator; `SCAN_SIZE` count arithmetic; `WORKSPACE_IGNORED`.
3. Tool layer + headless: an in-process MCP client over the SDK's
   memory transport lists every verb as a tool, calls `open`,
   `inspect`, `add_atom`, `undo`; the headless host keys by path;
   `xtal mcp --headless` starts and answers `initialize` over stdio.
4. `WindowSession`: every structure verb is one undo step in the tab;
   `WINDOW_BUSY` during playback and during a running calculation;
   `DOCUMENT_CHANGED` when the stack moves mid-run; the log is written
   to the entry; `render` writes the viewport (with the stub viewport,
   `save_image` is patched and asserted).
5. Server in the window: toggling the preference starts and stops the
   thread and writes/removes the discovery file; a client on another
   thread calls `inspect` and the GUI thread served it
   (`qtbot.waitUntil`); a wrong token is refused; the Help action opens
   the page; the proxy forwards to a window and falls back headless.
6. Packaging: both specs name two `EXE`s; `bundle.COLLECT` has `mcp`;
   the selftest's launcher check is unit-tested with a fake folder.
7. Skill/docs: the name-holding tests pass; `ruff check` clean.
8. Eval: `run.py --dry-run` lists the tasks and their expectations
   without calling `claude`; the grader is unit-tested on canned
   transcripts.

## Not in this PR

- A manual chapter *Working with an AI assistant* (waits for #25).
- Other clients' instruction formats (AGENTS.md); the MCP server is
  what reaches them.
- Headless render from the frozen launcher.
- Multiple windows: the discovery file holds one; a second window
  that finds a live one does not start a server and says so on its
  page.

## Simplifications (2026-10-01)

- `Availability(ok, what, command)` (`xtal/params.py`) replaces two
  string hacks: `capabilities._short_reason`, which cut a reason at
  " -- ", ".  " or ": ", and `engine_note_html`, which searched the
  reason for the install command.  `reason` is now composed from the
  two halves, and the compact listing reads `what`.  So compact
  `capabilities()` now shows an installed ML engine's whole note, and
  a plugin's or an exception's reason is no longer cut short.
- The proxy (`xtal/agent/proxy.py`) reconnects instead of exiting.  A
  call that finds the window closed, switched off, or restarted with
  a new port or token is answered with an error ("window: ...") and
  the connection dropped; the next call reads the discovery file
  again and connects.  A session the window forgot (its 404) is made
  again and the call sent once more at once, and a call that fails on
  its own keeps the session the others share.  The proxy exits only
  when the client closes stdin, and `_Leaving`, `_Stdout`, `_Stdin`
  and the exit codes went with the exits.

## Served context and the parity eval (2026-10)

A chemist in a chat client reaches Crystal Builder through MCP alone;
Claude Code with the skill and a shell was the better experience,
because the playbook never reached an MCP client. This part measures
the gap (`tools/agent_eval/run.py --via both`) and serves the
playbook.

### What a client is served

- **Instructions** at the handshake: `xtal/agent/skill/mcp.md`, the
  protocol condensed for tool calls (order of work, what never to do,
  what to report, when to read which guide), at most 6 kB.
- **`guide(topic)`**, a tool: the skill's reference pages, the same
  ones Claude Code reads, fetched by the model when it needs one. The
  topics and when to read each are `mcp.md`'s own list. With no topic
  it gives the instructions again, for a client that never shows the
  model the server's.
- **Resources**: each guide (`crystal-builder://guide/<topic>`) and
  the current document's `inspect`
  (`crystal-builder://document/current`), for a client where the
  person attaches context.
- **Prompts**: `prepare-deposited-cif`, `build-mof`, `porosity-report`,
  from `xtal/agent/skill/prompts/`.
- **Every tool parameter has a JSON type**, which
  `tests/test_agent_tools.py` holds. The baseline found it: untyped,
  `set_cell`'s numbers arrived as strings and it failed every call.

`xtal/agent/context.py` is the one reader. `build_server` serves it to
both hosts. The proxy answers the instructions, the guide resources
and the prompts itself, so they arrive with no window behind it, and
forwards the current document and every tool, `guide` among them.

### Baseline, before the playbook was served

2026-10-15, `--via both`, Opus 5.5, both ways with
`--setting-sources project` and the host session's variables dropped:

```
task                 | raw | turns | $    | mcp | turns | $    | failed checks
---------------------+-----+-------+------+-----+-------+------+--------------
build-overlap        | yes | 6     | 0.25 | yes | 4     | 0.11 |
compare-two          | yes | 8     | 0.26 | yes | 5     | 0.11 |
copies-and-hydrogens | yes | 7     | 0.31 | yes | 7     | 0.17 |
open-trimers         | no  | 9     | 0.32 | no  | 7     | 0.16 | raw: asks the person; mcp: asks the person
short-relax          | yes | 6     | 0.21 | yes | 4     | 0.06 |
strain-sweep         | yes | 8     | 0.27 | yes | 340   | 2.13 |
tied-scan            | yes | 9     | 0.30 | no  | 10    | 0.12 | mcp: reports MODULE_FAILED; log has scan.run
---------------------+-----+-------+------+-----+-------+------+--------------
passed               | 6/7 |       |      | 5/7 |       |      |
```

What the runs show:

- **tied-scan** is the trap the skill warns of: over MCP, with no
  skill, the agent scanned the cell parameter (a = 2d) and reported a
  landscape, never meeting `MODULE_FAILED`. Through the skill it did.
- **strain-sweep** cost 340 turns over MCP because `set_cell` failed
  every time: its parameters had no JSON type, so the client sent
  strings and the lattice compared a string with a number. Seventeen
  tools had an untyped parameter; raw Python never noticed. The agent
  passed anyway by building each strained cell afresh with `new` and
  typing in all 104 atoms, having also found `scan.run` refuse
  `engine: "uff"` and take an optimiser step at `max_steps: 0`.
- **compare-two** passed over MCP by hand: the agent worked the
  distances out from `inspect`'s coordinates and cell.
- **open-trimers** failed both ways on the grader's question check:
  both reports asked the person, but as an instruction ("Tell me which
  you want") rather than a sentence ending in "?".

### After the playbook was served

2026-10-15, the same command on this branch (served context and typed
tool parameters):

```
task                 | raw | turns | $    | mcp | turns | $    | failed checks
---------------------+-----+-------+------+-----+-------+------+--------------
build-overlap        | yes | 7     | 0.28 | yes | 5     | 0.21 |
compare-two          | yes | 11    | 0.31 | yes | 16    | 0.21 |
copies-and-hydrogens | yes | 5     | 0.26 | yes | 9     | 0.21 |
open-trimers         | yes | 8     | 0.31 | yes | 8     | 0.17 |
short-relax          | yes | 4     | 0.18 | yes | 8     | 0.12 |
strain-sweep         | yes | 8     | 0.29 | yes | 14    | 0.18 |
tied-scan            | yes | 6     | 0.26 | yes | 10    | 0.15 |
---------------------+-----+-------+------+-----+-------+------+--------------
passed               | 7/7 |       |      | 7/7 |       |      |
```

MCP now passes what raw access passes: tied-scan meets
`MODULE_FAILED` instead of scanning the cell, and strain-sweep takes 14
turns instead of 340 with `set_cell` typed. It still takes more turns
than raw access on the composition tasks (compare-two 16 against 11,
strain-sweep 14 against 8), which is what sub-projects B (queries) and
D (composition) are scheduled to close. One run each way: open-trimers
passing on both sides here and failing on both in the baseline is the
run-to-run spread of the grader's question check, not a change.

## Guardrails: the assistant's changes, attributed and revertible (2026-10)

Every step an assistant's verb pushes carries an `Origin` (its burst,
its place in it, the verb, a `checkpoint` label, the time); a person's
carries none. A burst is one run of the assistant's edits on one
document, opened lazily by the session that pushes: it ends when the
assistant calls `checkpoint(label)`, opens or switches documents,
had been quiet for `BURST_GAP` (60 s) when a call began, or finds its
last step is no longer the newest applied one (the person edited,
undid or reverted). The gap is measured to where a call begins, not
to where its step lands, so a relaxation longer than the gap is still
the request it was part of (`Session._hear`; in the window the tab's
session hears a calculation that a copy's session runs). The
assistant's own `undo` and `redo` do not end it: taking back its own
misstep is still the same request -- unless the redo re-applies a
person's step over the burst, which ends it, so no burst ever holds a
person's step. `checkpoint` names the *next* burst, and opening or
switching documents forgets the name, so the assistant calls it once
a document is open (after `open` or `build`) and again whenever the
person asks for something new, as `mcp.md` says. `xtal/agent/changes.py` reads the bursts off the
history itself and plans Revert (undo back to just before the burst,
everything after it included, said beforehand) and Restore (redo the
burst and whatever Redo must pass on the way, never a later change),
so the strip cannot disagree with what Undo does.

The window shows the latest burst in the *Agent changes* strip under
the notice bar, while an assistant can be connected: Revert, Restore,
and History for every burst. Its line reads *Two oxygens · 2 steps by
the assistant · 14:05*, the request first so that a narrow column,
which elides from the right, keeps what matters; the whole of it is
the tooltip. The label is the assistant's own words and is shown as
plain text everywhere (line, tooltip, menu). Revert says beforehand
what else it takes: *Revert (also undoes 1 of yours)*, and History's
entries likewise, *Revert: First (and 1 later assistant change; also
undoes 1 of yours)*, with a greyed entry's reason as its tooltip. The
strip's own Restore redoes exactly the steps its Revert took, is kept
per tab (switching tabs and back keeps it), and is withdrawn once
Redo no longer holds exactly those (another undo, a redo, an edit).
History offers Restore for a burst only once all of it is undone,
and that Restore is the plan above. Revert greys, saying why, while a
calculation holds the tab or a trajectory plays. On its next call the
assistant is told what happened behind its back:
`AGENT_CHANGES_REVERTED` when steps of its own that it had seen
applied were undone, counted by those; `PERSON_EDITED` when the person
added steps, or undid only steps of their own; its own undo and redo
are never reported to it as the person's. Cost estimates for calculations moved to sub-project C.

## The view: how a tab looks (2026-10)

Asked by Julius: could an assistant change the style, the ring filling
and the like? Two verbs, after `render` in `VERBS`. `view()` answers
every `ViewSettings` field by name (`to_dict`) and `VIEW_CHOICES`, the
values of each field that takes one of a list. `set_view(settings)`
changes any of them. Both are logged, and neither is a step:
`summarise_log` does not count them.

**Validated, all or nothing.** `coerce_view`
(`xtal/view/settings.py`, Qt- and VTK-free, moved there from
`xtalapp/viewport/view_settings.py` so the core may import it) reads each field's type off the record:
a bool is a bool or "true"/"false" (1 is refused, so 2 is not true), an
int refuses 2.5, a colour is three integers 0-255, a range is low <=
high, element keys are real elements, and a choice field takes only its
choices. The first bad key or value refuses the whole request with
`VIEW_SETTING_REFUSED` and a sentence naming what it takes ("did you
mean show_rings" for a misspelt key); nothing is applied. A core-only
install, with no `xtalapp`, reads and sets the view as the window does.
An empty request is ok and changes nothing. A `background` given alone
turns `background_follows_theme` off, so a theme change does not paint
over it.

**Not an undo step.** A style draws the structure and never changes
it, so a view change is not on the stack, does not mark the document
modified, and the *Agent changes* strip does not list it; it cannot be
reverted there. The answer's `data["changed"]` and `data["was"]` hold
the new and old values of the same keys, so sending `was` back is the
way to put the view as it was.

**In the window** `WindowSession` reads and writes the tab's own
`Document.view`: `set_view` coerces first, then on the GUI thread calls
`Document.update_view`, whose `viewChanged` the scene and the Style
panel follow, so the panel shows what was set. It is refused with
`WINDOW_BUSY` only while the tab plays a trajectory back (playback is
redrawing it); a calculation holds the structure, not how it is drawn,
so it is answered then. The status bar announces it like any verb.

**Headless** the session merges the cleaned settings into its own view
(a copy of whatever it was opened with), which a saved project carries.
`render` writes that view into the scratch project it hands the
snapshot subprocess, and the snapshot now draws the project's view, so
rings, Colour by and display ranges reach the picture. `render`'s
`style` and `show_cell` default to `None`, the view's own; given, they
win for that picture only. A headless render is always orthographic.

`mcp.md` tells the assistant to change the view only when the person
asks, to read it with `view` first, and to say what it changed. Out of
scope: view changes as undo steps, reverting them per request, and the
camera (not in `ViewSettings`).
