# The workspace, and handing work to the person

Everything lives in a **workspace**: a folder the Crystal Builder window
opens, with one folder (an *entry*) per structure. The person's default
is `~/Crystal Builder`, and the window asks for one at startup. Use the
workspace the person names. If they have not named one, ask, or use
their default rather than inventing a new folder somewhere else.

```
Crystal Builder/                 the workspace
  workspace.json                 its marker, and the window's open tabs
  MOF-5/                         an entry
    MOF-5.cif                    the copy of the file that was opened
    MOF-5.xtalproj               the project: what save() writes
    agent-session.jsonl          every verb you ran, one JSON per line
    uff-optimise-001/            a run: log, trajectory, final.cif
    zeopp-volume-grid-002/       another run, with its report
  blocks/                        building blocks drawn in the builder
```

## How files arrive

- `Session.open(file, workspace=ws)` **copies** the file into its own
  entry and works on the copy. The person's original is never touched.
  Opening the same bytes again finds the same entry. Two different
  files with one name get `MOF-5` and `MOF-5-2`.
- `Session.build(...)` files a build as one entry named after what was
  built, one CIF written from it, and the run folder moved underneath.
- `Session.new(..., workspace=ws)` makes an entry for a structure with
  no file yet.
- A file already inside a workspace is opened where it is.

## What save() writes

`save()` writes `<name>.xtalproj` beside the file the session is: the
structure, the bonds (hand-drawn and perceived), and the person's view,
unchanged. The CIF is left exactly as it was. A project is what the
person should open: it holds your bonds, and a CIF re-read later would
not. `export("x.cif")` writes a clean CIF for another program (no
markers, no net).

## Handing it over

The person opens the project from the window's Workspace panel,
double-clicking the entry, or with File ▸ Open. A run's `report.json`
double-clicked puts its tables back in the Results panel. Tell them:

- the project path `save()` returned;
- that `agent-session.jsonl` in the same folder lists every step;
- anything a warning said.

If the window already has that structure open in a tab, the person must
reopen it to see your changes: the window does not watch files.
