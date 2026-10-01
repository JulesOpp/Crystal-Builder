# AI assistant revamp: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task is one commit, written test-first by its implementer; this plan fixes files, interfaces, tests and acceptance, not code bodies.

**Goal:** An AI assistant drives the running Crystal Builder window through any MCP client, from the packaged app or a source install, with right-sized answers and the skill's rules enforced in the API.

**Architecture:** One MCP tool layer (`xtal/agent/tools.py`) over any `Session`, served by a headless host (`xtal mcp`, stdio) or by the window (streamable HTTP on loopback) through `WindowSession`, a `Session` subclass whose plumbing goes through `Document.run` on the GUI thread. A stdio shim proxies to the window when one is running. See the spec: `docs/superpowers/specs/2026-10-01-ai-assistant-revamp-design.md`.

**Tech Stack:** Python 3.11+, PySide6, the `mcp` Python SDK (`FastMCP`, streamable HTTP, memory transport for tests), pytest + pytest-qt, PyInstaller.

## Global Constraints

- Read `CLAUDE.md` first. Line length 79; `ruff check` only, never `ruff format`; test names are sentences; deprecation warnings are errors; `xtal/` imports no Qt.
- The core's dependencies stay numpy, scipy, gemmi, spglib. `mcp` is an **extra** (`mcp = ["mcp>=1.30,<2"]`, the version the suite was run against), imported lazily.
- Every verb is one undo step; a refusal is a `VerbResult` with `ok=False` and a code from `CODES`; no new code without its `diagnostics.md` row (the equality test enforces it).
- Chemistry defaults are Julius's: nothing here changes a default of any engine, step or module.
- git here is 1.8.4: no `git worktree`, no `git -C`, no `stash push <path>`. Work in the checkout on `feature/ai-assistant-revamp`, serially.
- No `make`, `g++`, `cc`, `clang`, `sphinx-build -M` (they trigger the Xcode dialog).
- Run tests with plain `pytest tests/<file>` (xdist is on by default); the whole suite before each commit: `pytest` (about 7 min here).
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Right-sized answers

**Files:**
- Modify: `xtal/agent/answers.py` (`Inspection`), `xtal/agent/inspect.py`, `xtal/agent/capabilities.py`, `xtal/cli.py` (`cmd_inspect`, `cmd_capabilities` and their parsers)
- Test: `tests/test_agent_inspect.py` (extend), `tests/test_agent_answer_size.py` (new)

**Interfaces:**
- Produces: `Inspection.site_groups: list[dict]` with keys `element`, `coordination`, `pattern` (str, e.g. `"O 1.95 x4"`), `count`, `sites` (list[int]), `example` (one site row). `Inspection.to_dict(sites="problems")`, `to_json(sites=...)`; `sites in {"problems","all","none"}`, `ValueError` otherwise. `inspect(structure, symprec)` unchanged. `capabilities(verbose=False)`; `help_for` unchanged. CLI flags `xtal inspect --sites`, `xtal capabilities --verbose`.
- "Problem" sites: every site index named by a diagnostic's `where` (`site N`, `atoms i, j` resolved through `cell.site_idx`), in index order.
- `str(Inspection)`: header as now, then one line per group (`Zn   CN 4  x32  O 1.94 x4`), then the problem rows in the existing table format, then diagnostics. The 40-row table and `MAX_ROWS` go.

**Tests (names are the sentences):**
- `test_sites_of_one_kind_are_one_group_with_a_count` (rutile: Ti x2 CN 6, O x4 CN 3).
- `test_a_problem_site_is_listed_and_a_clean_one_is_not` (quartz with an atom dropped on another: the CLOSE_CONTACT pair's sites in `to_dict()["sites"]`, nothing else).
- `test_sites_all_and_none_give_every_row_and_no_row`.
- `test_an_unknown_sites_choice_is_refused`.
- `test_mof5_inspection_json_is_under_five_kilobytes` and `test_capabilities_json_is_under_four_kilobytes` (open `resources/samples/MOF-5.cif`; `len(to_json()) < 5000`, `len(capabilities().to_json()) < 4000`).
- `test_verbose_capabilities_still_carry_every_parameter`.
- `test_actions_the_window_performs_are_not_listed`.
- `test_json_output_round_trips_for_every_cli_command_that_offers_it` still passes; add `--sites all` to the inspect case.

**Acceptance:** `pytest tests/test_agent_inspect.py tests/test_agent_answer_size.py tests/test_agent_skill.py tests/test_agent_session.py`; `ruff check`; `xtal inspect resources/samples/MOF-5.cif` prints groups, no 40-row table.

- [ ] Commit: `Agent answers sized for a model: site groups, problem sites, compact capabilities`

---

### Task 2: Rules into the API

**Files:**
- Modify: `xtal/agent/diagnostics.py` (`CODES`), `xtal/agent/session.py` (`open`, `optimize`, `run`), `xtal/agent/skill/references/diagnostics.md`
- Test: `tests/test_agent_session.py` (extend)

**Interfaces (codes, exact names, levels):**
- `BONDING_WOULD_CHANGE` warning: in `optimize`, after the apply, `bonding.perceive(result)` keys vs `bonding.perceive(start)` keys differ; message `"a recalculation would add N and remove M bond(s); bonds were left as they were"`. Suggestion: inspect; a bond now spans an unphysical length, or one is missing; recalculate only if the person wants perception to replace the drawn graph.
- `SCAN_SIZE` info: in `run` when `action` starts with `scan.` and the point count > 1. Count = product of every `axisN_steps` present (as coerced), times 2 when the action's parameters say both directions are walked (read the coerced param whose name contains `direction`/`both`; if there is none, times 1). Message: `"N points, each a relaxation, written as it finishes"`. Fires before the run (append to the answer either way).
- `WORKSPACE_IGNORED` info: in `Session.open` when `workspace is not None` and `Workspace.find(path)` found a different workspace. Message names both folders. On `session.opened`.
- `WINDOW_BUSY` error and `DOCUMENT_CHANGED` error: added to `CODES` and `diagnostics.md` now (raised in Task 4).
- `diagnostics.md` rows for all five, in the table's existing style.

**Tests:**
- `test_a_relaxation_that_would_change_the_bonding_says_so` (dry ice; a fake calculator that pulls one C–O apart beyond 1.3× the reference; `BONDING_WOULD_CHANGE` present, bond count unchanged) and `test_a_relaxation_that_keeps_the_bonding_says_nothing`.
- `test_a_scan_of_many_points_says_how_many` (monkeypatch `MODULES.find` to a stub action that records nothing and returns an ok result with `axis1_steps=5`; assert the info says 5, or 10 with both directions) and `test_a_single_point_scan_says_nothing`.
- `test_opening_into_another_workspace_says_the_file_stayed_where_it_was` (two workspaces in `tmp_path`).
- `test_every_diagnostic_code_is_documented_and_no_other_is` (existing) passes with the five new rows.

**Acceptance:** `pytest tests/test_agent_session.py tests/test_agent_skill.py`; `ruff check`.

- [ ] Commit: `Agent: three skill rules the API now keeps (bonding after a relaxation, scan size, ignored workspace)`

---

### Task 3: The tool layer and `xtal mcp` headless

**Files:**
- Create: `xtal/agent/tools.py`, `xtal/agent/serve.py`
- Modify: `pyproject.toml` (extra `mcp = ["mcp>=1.30,<2"]`, add to `dev`), `xtal/install.py` if extras are enumerated there, `xtal/cli.py` (`mcp` subcommand: `--headless`, `--window`), `xtal/agent/__init__.py` (`__all__` unchanged; no eager import of tools)
- Test: `tests/test_agent_tools.py`, `tests/test_agent_serve.py`
- Install into `.venv` first: `uv pip install --python .venv/bin/python -e ".[mcp]"` (uv is at `~/.local/bin/uv`).

**Interfaces:**
- `class Host(Protocol)`: `current() -> Session`, `open(path, workspace=None) -> Session`, `sessions() -> list[Session]`, `switch(path) -> Session`.
- `class HeadlessHost(Host)` in `serve.py`: sessions keyed by resolved path; `open` of a held path returns it; `current` is the last opened/switched; `current()` with none raises `LookupError("open a structure first")`, which `tools.py` turns into `VerbResult(ok=False, OPERATION_REFUSED)`.
- `tools.build_server(host, name="crystal-builder") -> FastMCP`: registers one tool per name in `capabilities.VERBS` except `open`, `new`, `build` (registered as host tools), with the verb's keyword parameters (from `inspect.signature`), its docstring as description, returning `json.dumps(result.to_dict())`; `inspect` takes `sites="problems"` and returns `Inspection.to_dict(sites)`; `render` returns `[TextContent(json), ImageContent(png base64)]` when it drew; plus `documents`, `switch`, `capabilities(verbose=False)`, `help_for(name)`. Tool names equal verb names.
- `serve.main(argv) -> int`: `xtal mcp [--headless|--window]`; headless runs `build_server(HeadlessHost()).run(transport="stdio")`. `--window` and proxying are Task 5 (here `--window` exits 2 "no window is listening"). Without `mcp` installed: exit 2 with `install.command("mcp")`.
- A `Diagnostic` for a tool refused because no session is current: `OPERATION_REFUSED` with that message (no new code).

**Tests:**
- `test_every_verb_is_a_tool_with_the_verbs_own_parameters` (memory transport: `mcp.shared.memory.create_connected_server_and_client_session`; `list_tools` names ⊇ VERBS minus the three classmethods, plus `documents`, `switch`, `capabilities`, `help_for`; `add_atom`'s schema has `element`, `frac`, `cart`, `bonded_to`).
- `test_a_tool_before_any_open_is_refused_not_raised`.
- `test_open_inspect_add_atom_and_undo_through_the_client` (rutile CIF in `tmp_path`; the undo answer says `undid add atom`).
- `test_inspect_tool_defaults_to_problem_sites_only`.
- `test_render_tool_returns_the_picture_as_image_content` (skip without VTK/GL as `test_agent_render.py` does).
- `test_two_opens_of_one_file_are_one_session`.
- `test_xtal_mcp_headless_answers_initialize_over_stdio` (subprocess `python -m xtal.cli mcp --headless`, send an `initialize` JSON-RPC line, read the reply, close).
- `test_without_the_extra_the_command_says_what_to_install` (monkeypatch `importlib.util.find_spec` for `mcp`).

**Acceptance:** `pytest tests/test_agent_tools.py tests/test_agent_serve.py`; `ruff check`; `xtal mcp --headless < /dev/null` exits cleanly.

- [ ] Commit: `MCP: one tool per agent verb, served headless by xtal mcp`

---

### Task 4: `WindowSession` and the gates

**Files:**
- Create: `xtalapp/agent_host.py` (`Bridge`, `WindowSession`, `WindowHost`, `AgentCalculation`)
- Modify: `xtalapp/mainwindow.py` (`has_running_calculation` counts an agent calculation; `agent_host` property), `xtal/agent/session.py` only if a verb bypasses `_push`/`_operate` (make it go through them; note it in the commit)
- Test: `tests/test_window_session.py`

**Interfaces:**
- `class Bridge(QObject)`: `call(fn: Callable[[], T]) -> T`: when on the GUI thread, calls directly; otherwise `QMetaObject.invokeMethod` with `Qt.BlockingQueuedConnection` into a slot that stores result or exception; re-raises the exception on the caller's thread.
- `class WindowSession(Session)`: `__init__(document, window)`; `structure` property → `document.structure`; `entry` → `document.entry`; `path` → `document.path`; overrides `_push`, `_operate`, `undo`, `redo`, `save`, `history`, `render` (viewport grab through `bridge.call`, `view` applied via the viewport's camera presets and restored after), `energy`/`optimize`/`run` (copy on the GUI thread via `bridge.call(lambda: document.structure.copy())`, compute on the calling thread, apply via `_push`), `_record` unchanged (writes the entry's log). Every tool entry point first checks `_gate()`: `document.is_playing or window.has_running_calculation()` → `WINDOW_BUSY` refusal. A `revision` read before a calculation (`len(document.stack._done)` or the document's own counter if it has one) that differs at apply time → `DOCUMENT_CHANGED` refusal with `RESULT_NOT_APPLIED` naming the run folder.
- `class AgentCalculation`: a context manager registered on the window so `has_running_calculation()` is true inside it; the status bar shows `"AI assistant: <verb> running"` while inside.
- `class WindowHost(Host)`: `current()` → `WindowSession` for `window.current_document()` (`LookupError` when no tab); `open(path, workspace)` → `bridge.call(lambda: window.open_path(path, report=False))` then its session; `sessions()`, `switch(path)` (raises the tab). Sessions cached per document, dropped on the document's close.

**Tests (window fixture as `tests/test_agent_skill_ui.py`, stub viewport):**
- `test_every_structure_verb_lands_as_one_undo_step_in_the_tab` (for each verb in a fixed list of structure-changing verbs with known-good arguments on rutile: `len(document.stack._done)` grows by one, and `document.undo()` restores the atom count).
- `test_a_verb_from_another_thread_is_served_on_the_gui_thread` (`threading.Thread` calls `session.add_atom`; `qtbot.waitUntil(lambda: done)`; assert the thread id recorded inside `Document.run`, patched, is the GUI thread's).
- `test_the_window_refuses_while_a_trajectory_is_open` (`document.open_trajectory(...)` or set `document.playback`; `WINDOW_BUSY`).
- `test_the_window_refuses_while_a_calculation_runs` (patch `window.has_running_calculation` → True).
- `test_a_relaxation_is_not_applied_if_the_tab_changed_meanwhile` (fake calculator whose `compute` pushes an `add_atom` on the GUI thread via the bridge before returning; `DOCUMENT_CHANGED` and `RESULT_NOT_APPLIED`; atom count = original + 1).
- `test_the_persons_edits_are_gated_while_the_agent_calculates` (inside `AgentCalculation`, `window.has_running_calculation()` is True).
- `test_the_log_is_written_to_the_entry`.
- `test_render_in_the_window_grabs_the_viewport` (stub viewport with `save_image` recorded).
- `test_the_host_follows_the_current_tab_and_opens_a_new_one`.

**Acceptance:** `pytest tests/test_window_session.py tests/test_agent_session.py`; `ruff check`.

- [ ] Commit: `The window as a Session: every agent verb lands in the open tab as one undo step`

---

### Task 5: The server in the window, Preferences, discovery, proxy

**Files:**
- Create: `xtalapp/agent_server.py` (`AgentServer(QObject)` on a `QThread`; `discovery_path()`, `write_discovery`, `remove_discovery`), `xtalapp/dialogs/preferences.py` (new `AgentPage`), `xtal/agent/discovery.py` (core: `read(path) -> dict | None`, `alive(entry) -> bool` by pid and a `GET` of `/mcp`), `xtal/agent/proxy.py` (stdio ↔ streamable HTTP forwarder using the SDK client)
- Modify: `xtalapp/settings.py` (`agent/serve` bool, `agent/port` int), `xtalapp/menus.py` (`connect_ai_assistant` → Help, next to `install_ai_skill`), `xtalapp/mainwindow.py` (`closeEvent` stops the server; `connect_ai_assistant()` opens Preferences on the page; status-bar messages on connect and per verb), `xtalapp/applog.py` only for `app_data()` reuse, `xtal/agent/serve.py` (proxy when discovery is alive; `--window`/`--headless`), `packaging/bundle.py` (`dialog_imports` if the page is lazily imported)
- Test: `tests/test_agent_server.py`, `tests/test_agent_discovery.py`, `tests/test_agent_proxy.py`, `tests/test_preferences_agent_page.py`

**Interfaces:**
- `AgentServer(window, port=7781, token=None)`: `start() -> (host, port)` (binds `127.0.0.1`, falls back to port 0 → OS-chosen when busy), `stop()`, `token` (32 hex from `secrets.token_hex(16)`), `url` (`http://127.0.0.1:<port>/mcp`), signals `started(int)`, `stopped()`, `failed(str)`, `clientConnected()`, `verbLanded(str)`. The ASGI app is `FastMCP.streamable_http_app()` wrapped by a Starlette middleware that requires `Authorization: Bearer <token>` (401 otherwise) and runs under `uvicorn.Server` in the thread (`uvicorn` arrives with `mcp`).
- Discovery file: `applog.app_data() / "mcp.json"` with `{"port", "token", "pid", "version", "url"}`, mode 0600; removed on `stop()` and in `closeEvent`.
- `AppSettings.agent_serve: bool` (default False), `agent_port: int` (default 7781).
- `AgentPage(QWidget)`: `TITLE = "AI assistant"`; checkbox, port `QSpinBox` (1024–65535), status `QLabel`, two `QLineEdit` read-only + Copy buttons (Claude Code HTTP line with the token; stdio line = `<launcher path> mcp` where the launcher is `shutil.which("xtal")` in a source install and `Path(sys.executable).with_name("xtal")` (+`.exe`) when frozen); signal `serveChanged(bool)`, `portChanged(int)`; forwarded by `PreferencesDialog` like `followGeometryChanged`.
- `MainWindow.connect_ai_assistant()`; Help action `connect_ai_assistant` labelled `"Connect an AI assistant..."`, tip in the existing voice; placed in the help menu list right after `install_ai_skill`.
- `proxy.run(url, token) -> int`: a stdio `FastMCP`-less server built from `mcp.server.lowlevel.Server` whose `list_tools`/`call_tool` forward to a `streamablehttp_client` session with the bearer header.
- `serve.main`: default = proxy when `discovery.read()` is alive, else headless; `--window` errors (exit 2) when nothing is alive; `--headless` never proxies.

**Tests:**
- `test_turning_the_preference_on_starts_the_server_and_writes_the_discovery_file` and `..._off_stops_it_and_removes_the_file` (`qtbot.waitSignal(server.started)`; file mode `0o600` on POSIX).
- `test_a_client_on_another_thread_is_served_by_the_gui_thread` (SDK `streamablehttp_client` to `server.url` with the header in a thread; `inspect` of an open rutile tab returns its formula).
- `test_a_wrong_token_is_refused` (HTTP 401 via `httpx`).
- `test_a_busy_port_falls_back_to_a_free_one` (occupy 7781 with a socket first).
- `test_the_help_action_opens_preferences_on_the_assistant_page`.
- `test_the_page_shows_both_connection_lines_with_the_live_port_and_token`.
- `test_discovery_of_a_dead_pid_is_not_alive`.
- `test_xtal_mcp_proxies_to_a_live_window_and_falls_back_headless` (server in the test process; `serve.main([])` with discovery patched to the test's file, run in a subprocess for the stdio side; then with the file removed, headless).
- `test_closing_the_window_stops_the_server`.

**Acceptance:** `pytest tests/test_agent_server.py tests/test_agent_discovery.py tests/test_agent_proxy.py tests/test_preferences_agent_page.py tests/test_window_session.py`; `ruff check`; manual: run the app (`python .claude/skills/run-app/drive.py --scratch build/mcp-try` or `crystal-builder`), switch the page on, `claude mcp add --transport http crystal-builder <url> --header "Authorization: Bearer <token>"`, and ask Claude Code to `inspect` the open tab.

- [ ] Commit: `Connect an AI assistant: an MCP server in the window, a Preferences page, and xtal mcp as its stdio door`

---

### Task 6: Packaging: the `xtal` launcher and the `mcp` extra in the bundle

**Files:**
- Modify: `packaging/macos.spec`, `packaging/windows.spec` (second `EXE` named `xtal`, `console=True`, same `Analysis` via a second `Analysis` over `xtal/cli.py` merged with `MERGE`, or one `Analysis` with both scripts; both `EXE`s into the one `COLLECT`), `packaging/bundle.py` (`COLLECT += ["mcp"]`; a `LAUNCHER = "xtal"` constant; `launcher_path(app_dir)`), `xtalapp/main.py` (`--selftest`: the launcher exists beside the executable and `subprocess.run([launcher, "capabilities", "--json"])` answers JSON with `version`), `xtalapp/selftest.py` if that is where checks live, `.github/workflows/*.yml` bundle step (install `.[mcp]`), `docs/PACKAGING.md`
- Test: `tests/test_packaging_launcher.py`

**Interfaces:**
- `bundle.LAUNCHER = "xtal"`; `bundle.launcher_path(executable: Path) -> Path` (`.exe` on Windows).
- `selftest.check_launcher(executable) -> str` in the existing check style; skipped (not failed) when not frozen.

**Tests:**
- `test_both_specs_build_an_xtal_launcher_beside_the_app` (parse the spec text: two `EXE(` with `name="xtal"` and `name="Crystal Builder"`, both referenced by `COLLECT(`).
- `test_the_bundle_collects_the_mcp_package`.
- `test_the_selftest_launcher_check_runs_the_launcher` (a fake `xtal` script in `tmp_path` printing `{"version": "x"}`).
- `test_the_launcher_check_is_skipped_when_not_frozen`.

**Acceptance:** `pytest tests/test_packaging_launcher.py tests/test_selftest*.py`; `ruff check`. A real bundle build is CI's (the workflow's bundle job); note in the commit that the spec change is verified by CI's draft-release run.

- [ ] Commit: `Bundle: an xtal launcher beside the app, with the mcp extra, so a packaged install can be driven too`

---

### Task 7: Skill and docs

**Files:**
- Modify: `xtal/agent/skill/SKILL.md` (section *Connected to the window* after §1; the shell section mentions `xtal mcp`), `xtal/agent/skill/references/api.md` (`inspect(sites)`, `site_groups`, `capabilities(verbose)`, the five codes where verbs mention them, `documents`/`switch`/`open` as tools), `xtal/agent/skill/references/diagnostics.md` (done in Task 2; re-check), `README.md` (agent section: connect the window, `xtal mcp`, the eval), `docs/RELEASE_NOTES.md`, `CLAUDE.md` (map rows for `tools.py`, `serve.py`, `discovery.py`, `proxy.py`, `agent_host.py`, `agent_server.py`; the invariant sentence), `docs/TODO.md` (close the owed MCP item; keep the manual chapter)
- Test: `tests/test_agent_skill.py` (extend: every tool name the skill mentions in backticks after "tool" exists in `tools.build_server`'s registry; every CLI command shown exists, now including `xtal mcp`)

**Tests:**
- `test_every_tool_the_skill_names_is_registered`.
- The existing name-holding tests pass unchanged.

**Acceptance:** `pytest tests/test_agent_skill.py tests/test_agent_skill_ui.py`; `ruff check`; `grep -n "performed by the window" xtal/agent/skill -r` finds nothing stale.

- [ ] Commit: `Skill and docs: driving the window, the tools, the new codes`

---

### Task 8: The eval harness

**Files:**
- Create: `tools/agent_eval/README.md`, `tools/agent_eval/run.py`, `tools/agent_eval/grade.py`, `tools/agent_eval/tasks/<name>/{task.md,expect.json,<input file>}` for the five tasks in the spec §6
- Test: `tests/test_agent_eval_grader.py`

**Interfaces:**
- `grade.grade(task_dir: Path, transcript: str, project: Path | None) -> Verdict` with `Verdict(passed: bool, checks: list[tuple[str, bool, str]])`. `expect.json`: `{"codes": [...], "inspect": {"CODE": "present"|"absent"}, "log_must_not_contain": ["cap"], "report_must_ask": true|false, "atoms_unchanged": true|false}`.
- `run.py [--claude PATH] [--only NAME] [--dry-run]`: finds `claude` with `shutil.which`, else `~/.claude/local/claude`, else errors with the path flag; per task: temp project dir, `xtal skill install --project <dir>`, copy the input, `claude -p "<task.md>" --output-format json --allowedTools "Bash,Read,Write,Edit"` with `cwd=<dir>`, then `grade`. Prints a table, exits 1 on any failure. `--dry-run` prints tasks and expectations only.
- Inputs: reuse fixtures that exist (`tests/` fixture CIFs for copies; a COD trimer sample from `resources/samples`; a `mof.build` combination that overlaps found by trying `catalog` pairs in the task's own setup script rather than hard-coding a guess, recorded in `task.md`).

**Tests:**
- `test_the_grader_passes_a_report_that_names_every_code_and_fails_one_that_does_not` (canned transcripts).
- `test_the_grader_checks_the_saved_project_with_inspect` (a saved rutile project; `COINCIDENT_ATOMS: absent` passes).
- `test_a_dry_run_lists_the_five_tasks_without_calling_claude`.

**Acceptance:** `pytest tests/test_agent_eval_grader.py`; `ruff check tools`; `python tools/agent_eval/run.py --dry-run` lists five tasks. A live run is for the person to trigger (it costs tokens): report the command in the PR.

- [ ] Commit: `An eval for the skill: five scripted tasks a real agent is graded on`

---

### After Task 8

- Full suite green; `ruff check` clean.
- Open the PR against `main` with a description per section of the spec, the measurements (sizes before/after), what CI must show (the bundle job builds two executables), and the manual-run instructions for the eval. End with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
