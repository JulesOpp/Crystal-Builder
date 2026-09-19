"""Areas 6b + 8: run folders, workspace paths and workspace.json."""
import json
import shutil
import sys
import tempfile
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))

from fixtures import quartz  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtal.workspace import NotAWorkspace, Workspace  # noqa: E402


def last():
    return traceback.format_exc().strip().splitlines()[-1]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        print("### a workspace root with non-ASCII characters")
        for name in ("café crystals", "結晶",
                     "näive"):
            try:
                ws = Workspace.create(tmp / name)
                src = tmp / "q.cif"
                write_cif(quartz(), src)
                entry = ws.add_structure(src)
                run = entry.next_run("uff", "optimise")
                print(f"  {name!r:<22} ok entry={entry.name!r} "
                      f"run={run.path.name!r} "
                      f"found={Workspace.find(run.path) == ws}")
            except Exception:
                print(f"  {name!r:<22} RAISED {last()}")

        print()
        print("### Workspace.find walking up from /")
        for p in ("/", "/nonexistent-xyz", str(tmp),
                  str(tmp / "no" / "such" / "file.cif")):
            try:
                print(f"  find({p!r}) -> {Workspace.find(p)}")
            except Exception:
                print(f"  find({p!r}) RAISED {last()}")

        print()
        print("### malformed workspace.json")
        ws = Workspace.create(tmp / "broken")
        marker = ws.root / "workspace.json"
        for tag, text in (("not json", "{{{ nope"),
                          ("a list", "[1, 2, 3]"),
                          ("null", "null"),
                          ("empty", ""),
                          ("session not a dict",
                           json.dumps({"session": 7})),
                          ("session.open not a list",
                           json.dumps({"session": {"open": "a.cif"}})),
                          ("session.open has absolute paths",
                           json.dumps({"session":
                                       {"open": ["/etc/passwd"]}})),
                          ("session.open escapes the root",
                           json.dumps({"session":
                                       {"open": ["../../x.cif"]}})),
                          ("active is negative",
                           json.dumps({"session": {"open": [],
                                                   "active": -4}}))):
            marker.write_text(text, encoding="utf-8")
            try:
                print(f"  {tag:<32} version={ws.version} "
                      f"session={ws.session} "
                      f"paths={[str(p) for p in ws.session_paths()]}")
            except Exception:
                print(f"  {tag:<32} RAISED {last()}")
        try:
            ws.set_session([])
            print(f"  set_session on a broken marker -> "
                  f"{marker.read_text(encoding='utf-8')[:70]!r}")
        except Exception:
            print(f"  set_session RAISED {last()}")

        print()
        print("### session referencing files that moved")
        ws2 = Workspace.create(tmp / "moved")
        src = tmp / "q2.cif"
        write_cif(quartz(), src)
        e = ws2.add_structure(src)
        target = next(e.path.glob("*.cif"))
        ws2.set_session([target], 0)
        print(f"  before: {ws2.session} -> "
              f"{[p.name for p in ws2.session_paths()]}")
        target.unlink()
        print(f"  after deleting it: {ws2.session} -> "
              f"{[p.name for p in ws2.session_paths()]}")

        print()
        print("### two runs asked for at the same moment")
        ws3 = Workspace.create(tmp / "race")
        src = tmp / "q3.cif"
        write_cif(quartz(), src)
        entry = ws3.add_structure(src)
        made, errs = [], []
        barrier = threading.Barrier(6)

        def go():
            barrier.wait()
            try:
                made.append(entry.next_run("uff", "optimise").path.name)
            except Exception as exc:
                errs.append(f"{type(exc).__name__}: {exc}")

        ts = [threading.Thread(target=go) for _ in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        print(f"  folders made: {sorted(made)}")
        print(f"  failures:     {errs}")

        print()
        print("### add_structure de-duplication and odd names")
        ws4 = Workspace.create(tmp / "names")
        for label, stem in (("plain", "quartz"),
                            ("with a space", "my quartz"),
                            ("accent", "quartz café"),
                            ("slash-ish", "a:b"),
                            ("dots", "..")):
            p = tmp / f"{stem}.cif"
            try:
                write_cif(quartz(), p)
                ent = ws4.add_structure(p)
                print(f"  {label:<14} {stem!r:<16} -> "
                      f"entry={ent.name!r}")
            except Exception:
                print(f"  {label:<14} {stem!r:<16} RAISED {last()}")
        # the same content twice, and different content same name
        p = tmp / "quartz.cif"
        ent = ws4.add_structure(p)
        print(f"  same file again -> entry={ent.name!r} "
              f"(entries: {[e.name for e in ws4.entries()]})")

        print()
        print("### Workspace.open on a folder that is not one")
        try:
            Workspace.open(tmp)
        except NotAWorkspace as exc:
            print(f"  NotAWorkspace: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
