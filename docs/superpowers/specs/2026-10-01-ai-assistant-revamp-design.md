# The AI assistant drives the window: design

Date: 2026-10-01. Branch: `feature/ai-assistant-revamp`. One PR.

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
  is the current tab; `open` is `window.open_path(path, report=False)`.

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
(`energy`, `optimize`, `run`) execute on the server thread over
`document.structure.copy()`, as the Force Field panel does; only
reading the structure for the copy and applying the result cross to the
GUI thread.

**Gates.** Every tool call is refused with `WINDOW_BUSY` (error) while
`document.is_playing` or `window.has_running_calculation()`. An agent
calculation registers itself so `has_running_calculation()` is true for
the person's gestures too (the same hazard the panel has: an edit
during a run would be overwritten by the apply). The structure's stack
position is read before an agent calculation; if it moved, the apply is
refused with `DOCUMENT_CHANGED` (error) and the run folder keeps the
result (`RESULT_NOT_APPLIED` names it).

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
| `WINDOW_BUSY` | error | a window tool refused while a trajectory is open or a calculation runs (§2) |
| `DOCUMENT_CHANGED` | error | the tab changed during an agent calculation; the result was not applied (§2) |

All five go into `CODES` and `references/diagnostics.md`; the existing
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
- `pyproject.toml`: `mcp = ["mcp>=1.2"]`, in `dev`.

### Tests, by commit

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

### Commit order

Each commit is green on its own, in this order: right-sizing; rules;
tool layer + headless `xtal mcp`; `WindowSession` + gates; server,
preferences, discovery, proxy; packaging; skill + docs; eval harness.

## Not in this PR

- A manual chapter *Working with an AI assistant* (waits for #25).
- Other clients' instruction formats (AGENTS.md); the MCP server is
  what reaches them.
- Headless render from the frozen launcher.
- Multiple windows: the discovery file holds one; a second window
  that finds a live one does not start a server and says so on its
  page.
