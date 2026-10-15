(workflows-assistant)=
# Working with an AI assistant

An AI assistant such as Claude Code can work on your structures in
Crystal Builder, either in the window you have open, where every
change is a step you can undo and watch, or on files of its own with no
window at all.  After this section you can switch the window's side on,
point an assistant at it, install the skill that tells the assistant
how to work here, know what each side can and cannot do, and read the
record an assistant leaves behind.

```{index} single: AI assistant
```
```{index} single: MCP
```
```{index} single: xtal mcp
```
```{index} single: skill (AI assistant)
```

:::{note}
**An assistant edits through the same commands as a person.**  Every
verb it has pushes the command the window pushes for that gesture: one
undo step, bonds changed only by *Recalculate bonds*, markers held back
by the engine registry, no force field changing the atoms or the bonds,
and nothing that adds what a file never located unless it is named.
Nothing it does is a side door.
:::

## Two parts: a skill and a connection

The assistant needs to be told two different things, and they are
separate on purpose.

**The skill** is a document, `SKILL.md` with a handful of references,
that tells the assistant the protocol for crystal structures: what to
do in what order, what to check before it believes a structure, and
where the program will say its answer is wrong though it looks right
(three copies of every atom stacked in one place, a linker with half
its hydrogens, a cluster with the wrong charge).  Install it with
*Help ▸* {ref}`Set up an AI assistant <cmd-install_ai_skill>`, which puts
it where Claude Code reads it (`~/.claude/skills`); a copy you have
edited is replaced only if you say so.  The same from a terminal:

```console
$ xtal skill install              # for every project: ~/.claude/skills
$ xtal skill install --project .  # for one project: ./.claude/skills
$ xtal skill path                 # where the shipped copy is
```

**The connection** is an MCP (Model Context Protocol) server: the verbs
as tools an assistant can call.  Two sides can answer it, and which one
is in use decides what the assistant works on.

## Connecting to the window

*Help ▸* {ref}`Connect an AI assistant… <cmd-connect_ai_assistant>`
opens *Preferences ▸ AI assistant*, which has the switch and the lines
to paste.

1. Tick **Let an AI assistant connect to this window**.  The page says
   *Listening on 127.0.0.1:7781*, or why it could not.  The switch is
   greyed, naming the install command, when the `mcp` extra is missing.
2. **Port**: 7781 by default, applied the next time the server starts.
   If another program has it, a free one is used instead, and the lines
   below say which.
3. Copy the line for your assistant.  For Claude Code, straight to the
   window:

   ```text
   claude mcp add --transport http crystal-builder http://127.0.0.1:7781/mcp --header "Authorization: Bearer <key>"
   ```

   The key is made afresh every time the application starts, so paste
   the line again after a restart.  For any assistant that starts a
   command itself (Claude Desktop, Cursor, Codex), the second line is
   the full path of the `xtal` launcher followed by `mcp`.  From the
   Linux AppImage it is
   `/path/to/Crystal_Builder-….AppImage xtal mcp`, which the page
   shows.

While the window serves, the **tabs open in it are the assistant's
documents**.  Each thing it does is one step that Ctrl+Z takes back, and
the status bar says what it did.

:::{warning}
**The connection is a key to your window.**  The server listens on
`127.0.0.1` only, so nothing outside your computer can reach it, and it
answers only a client holding the key, because any web page in your
browser can reach loopback.  The key is in the first line on the page and
in the discovery file below; do not paste it where others can read it.
:::

### How the assistant finds the window

Starting the server writes `mcp.json` into the application-data folder
-- the port, the key, the process id and the version -- readable by its
owner alone, and removes it when the server stops or the window quits.
`XTAL_APP_DATA` moves the folder, for a second install or a test.  This
is how the second line works: `xtal mcp` reads the file and forwards to
the window **when the process in it is alive and the port answers**; a
window that crashed leaves its file behind, and a port can be taken by
somebody else once its owner has gone, so the file alone is not trusted.

## `xtal mcp`

```console
$ xtal mcp --help
usage: xtal mcp [-h] [--headless | --window]

options:
  -h, --help  show this help message and exit
  --headless  serve sessions in this process, even when a window is serving
  --window    drive the running Crystal Builder window, or fail (the default
              is the window when one answers, else headless)
```

Over standard input and output it offers one tool for each verb --
`open`, `new`, `build`, `inspect`, `render`, `select`, `add_atom`,
`delete_sites`, `set_element`, `move_sites`, `set_cell`, `supercell`,
`slab`, `reduce_to_p1`, `find_symmetry`, `standardize`,
`set_space_group`, `merge_duplicates`, `recalculate_bonds`, `add_bond`,
`remove_bond`, `set_bond_type`, `add_hydrogens`, `substitute`,
`fill_pores`, `place_molecule`, `prepare`, `interpenetrate`, `energy`,
`optimize`, `run`, `undo`, `redo`, `save` and `export` -- plus
`documents`, `switch`, `capabilities` and `help_for`.  Each has its own
keywords and returns a structured answer.  Without the `mcp` extra it
exits saying what to install.

**A proxy, or a host of its own.**  By default it is a proxy to the
window when one is serving, and otherwise **works on files of its own**
in its own process, one session per file, as a script would.
`--window` insists on the window and fails when none answers, rather than
quietly handing the assistant a structure nobody can see; `--headless`
never looks for one.  The proxy reconnects: a window that is closed,
switched off or restarted with a new port is answered with an error and
the connection dropped, and the next call reads the discovery file
again.

**The packaged application carries `xtal`** beside it (on macOS inside
the app bundle's `Contents/MacOS`), and the page's second line names its
real path.  A frozen application has no `python -m`, so a headless
`render` from that launcher is refused with `RENDER_UNAVAILABLE`; connect
the window and it draws the picture its own viewport draws.

## The window side and the headless side

| | Window | Headless |
|---|---|---|
| Documents | the open tabs | one session per file |
| Edits | `Document.run`, in front of you | its own undo stack |
| Undo | Ctrl+Z, in the tab | the `undo` verb |
| `render` | the viewport's own picture | a subprocess, with no GL needed in the session |
| Tab it works on | its own current one (`open`, `switch`) | its own current one |

The assistant's current tab is **its own**: it is set by `open` and
`switch` and does not follow your clicks, which would send the next edit
into whichever tab you had raised.  Every answer from the window names
the tab it came from.  If that tab is closed the next call is refused,
saying to open or switch to one.

## What it will not do

**`WINDOW_BUSY`.**  A call to the window is refused while a trajectory
plays or a calculation runs, and once the window is closing or has
stopped serving.  Nothing was changed.  Wait for the run to end and
call again; retrying at once is refused the same way.  A calculation the
assistant starts counts as a running calculation too, so quitting asks
about it as it would about yours.

**`DOCUMENT_CHANGED`.**  You are not locked out while an assistant's
calculation runs.  But a result is applied to the structure it was
computed from, so if the tab was edited or closed in the meantime the
result is **not applied**, the run folder keeps it, and `RESULT_NOT_APPLIED`
names it.

**Size.**  The Large structures limits apply to an assistant's
supercell too, and the refusal is `SIZE_LIMIT`, naming the largest that
fits ({ref}`the setting <preferences-large-structures>`).

## What it records

Each verb appends a line to `agent-session.jsonl` in the structure's
entry -- one JSON object per verb -- which is how you learn, on opening
the entry, that an assistant worked on it, and how.  The record is
beside the structure, in the {doc}`workspace <workspaces>`, and is the
assistant's own account; the undo history in the tab is the window's.

Every answer is a `VerbResult`: whether it worked, a message, the undo
label, the atom counts before and after, and **coded diagnostics**.  A
refusal is `ok=False` with a code, never an exception and never a no-op
left on the stack.  The codes are a closed list -- nothing else is ever
raised -- each with a level and a remedy:

- **error**: the numbers are not to be believed until it is fixed
  (`COINCIDENT_ATOMS`, `ENGINE_UNAVAILABLE`, `MODULE_FAILED`,
  `WINDOW_BUSY`, `DOCUMENT_CHANGED`);
- **warning**: something to fix or to tell you (`DISORDER`,
  `OPEN_TRIMERS`, `CLOSE_CONTACT`, `NOT_CONVERGED`, `BUILD_OVERLAP`,
  `BONDING_WOULD_CHANGE`, `CHEMISTRY_CHANGED`);
- **info**: context, reported where it matters (`PREPARE_STEP`,
  `BONDS_NOT_RECALCULATED`, `SCAN_SIZE`, `WORKSPACE_IGNORED`).

`xtal inspect FILE` is the first thing an assistant reads, and you can
read it too: a structure's composition, symmetry and coordination in a
few kilobytes, with its diagnostics last.  Sites are grouped (an
element, its coordination and its neighbour pattern), and `--sites
problems|all|none` chooses how many rows come with them.

## Practical notes

- **One change per call.**  You are watching the tab, so the skill
  tells the assistant to keep each call's purpose clear, to make one
  change per call in the order it would explain it, and to say before a
  long calculation that it is starting.  Ctrl+Z is always the way back.
  `inspect` still answers while the window is busy.
- **Chemistry is yours.**  The skill tells the assistant never to run the
  step that adds what a file never located (the trimers' terminal
  ligands) on its own judgement, and to say in so many words when a result
  contains something the file never had.
- `capabilities` tells the assistant what this install can run -- which
  engines are present, which modules and whether it can render -- so it
  does not guess; the same is `xtal capabilities` in a terminal.

## Limitations

- **One window at a time.**  The discovery file holds one; a second
  window that finds a live one does not start a server, and says so on
  its page.
- The window's side needs the `mcp` extra in a source install; the
  packaged application carries it.
- The assistant sees what the verbs answer, not the screen: `render`
  and `inspect` are how it looks.  An assistant's judgement of a
  structure is a first pass for you to check.
- A headless `render` from the packaged launcher is unavailable, as
  above.
