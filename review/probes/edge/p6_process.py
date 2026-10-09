"""Area 6: the external process runner."""
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))

from xtal.modules.job import Cancellation  # noqa: E402
from xtal.modules.process import (  # noqa: E402
    ExternalProcess,
    MissingProgram,
)


def last():
    return traceback.format_exc().strip().splitlines()[-1]


def show(tag, result):
    print(f"  {tag:<38} ok={result.ok} rc={result.returncode} "
          f"cancelled={result.cancelled} "
          f"seconds={result.seconds:.2f}")
    print(f"      message: {result.message()}")
    if result.lines:
        print(f"      tail:    {list(result.lines)[-3:]}")


def script(tmp, name, body):
    p = tmp / name
    p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP
            | stat.S_IXOTH)
    return p


def main():
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        runs = tmp / "runs"
        runs.mkdir()

        print("### binary not on PATH")
        try:
            ExternalProcess(["definitely-not-a-program-xyz"],
                            cwd=runs).run()
        except MissingProgram as exc:
            print(f"  MissingProgram: {exc}")
        except Exception:
            print(f"  {last()}")

        print()
        print("### exits non-zero")
        bad = script(tmp, "bad.sh", "echo hello\nexit 3\n")
        show("exit 3", ExternalProcess([str(bad)], cwd=runs).run())

        print()
        print("### writes only to stderr")
        err = script(tmp, "err.sh",
                     "echo 'a real error' 1>&2\nexit 1\n")
        show("stderr only, exit 1",
             ExternalProcess([str(err)], cwd=runs).run())
        errok = script(tmp, "errok.sh",
                       "echo 'a warning' 1>&2\nexit 0\n")
        show("stderr only, exit 0",
             ExternalProcess([str(errok)], cwd=runs).run())

        print()
        print("### no output at all")
        quiet = script(tmp, "quiet.sh", "exit 0\n")
        show("silent, exit 0",
             ExternalProcess([str(quiet)], cwd=runs).run())

        print()
        print("### cancellation mid-run")
        slow = script(tmp, "slow.sh",
                      "i=0\nwhile [ $i -lt 100 ]; do echo tick $i; "
                      "sleep 0.1; i=$((i+1)); done\n")
        cancel = Cancellation()
        proc = ExternalProcess([str(slow)], cwd=runs)
        threading.Timer(0.6, cancel.cancel).start()
        show("cancelled after 0.6 s", proc.run(cancel=cancel))

        print()
        print("### cancel requested before launch")
        c2 = Cancellation()
        c2.cancel()
        show("pre-cancelled",
             ExternalProcess([str(slow)], cwd=runs).run(cancel=c2))

        print()
        print("### a child that ignores SIGTERM")
        stubborn = script(
            tmp, "stubborn.sh",
            "trap '' TERM\ni=0\nwhile [ $i -lt 200 ]; do echo t $i; "
            "sleep 0.1; i=$((i+1)); done\n")
        c3 = Cancellation()
        p3 = ExternalProcess([str(stubborn)], cwd=runs, grace=1.0)
        threading.Timer(0.6, c3.cancel).start()
        t0 = time.monotonic()
        show("SIGTERM ignored (grace=1 s)", p3.run(cancel=c3))
        print(f"      wall clock: {time.monotonic() - t0:.2f} s")

        print()
        print("### awkward run folders")
        pwd = script(tmp, "pwd.sh", "pwd\necho '#done'\n")
        for label, folder in (
                ("a space", runs / "with space"),
                ("an accent", runs / "café"),
                ("a newline", runs / "two\nlines"),
                ("quotes", runs / "it's \"here\"")):
            try:
                show(label, ExternalProcess([str(pwd)],
                                            cwd=folder).run())
            except Exception:
                print(f"  {label:<38} RAISED {last()}")

        print()
        print("### read-only location")
        ro = tmp / "readonly"
        ro.mkdir()
        os.chmod(ro, 0o500)
        try:
            show("under a read-only parent",
                 ExternalProcess([str(pwd)], cwd=ro / "run").run())
        except Exception:
            print(f"  read-only RAISED {last()}")
        os.chmod(ro, 0o700)

        print()
        print("### two runs, same folder, at once")
        writer = script(tmp, "writer.sh",
                        "for i in 1 2 3 4 5; do echo $1 line $i "
                        ">> out.txt; sleep 0.05; done\n")
        shared = runs / "shared"
        outs = []

        def go(tag):
            outs.append(ExternalProcess([str(writer), tag],
                                        cwd=shared).run())

        ts = [threading.Thread(target=go, args=(f"run{n}",))
              for n in (1, 2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        for r in outs:
            show("concurrent run", r)
        print(f"      out.txt: "
              f"{(shared / 'out.txt').read_text(encoding='utf-8')!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
