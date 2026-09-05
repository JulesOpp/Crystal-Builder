#!/usr/bin/env bash
#
# Build, prove and ship the macOS bundle in one go.
#
#     packaging/release-macos.sh
#     packaging/release-macos.sh --skip-tests --no-push
#
# The eight steps below are the ones CI's build job runs, in the same
# order, against a local .venv-build instead of a fresh runner.  Order
# is load-bearing in two places and neither is obvious:
#
#   * postbuild.py runs BEFORE the selftest, not after.  `strip -x` is
#     most of the download and it is also the step most likely to
#     break VTK; running the selftest against the unstripped bundle
#     proves nothing about what actually ships.
#   * makedmg.py runs after the selftest, so a bundle that cannot draw
#     never reaches a .dmg.
#
# Step 5 greps the selftest's output as well as trusting its exit
# code, and the difference is narrower than it looks: the selftest
# fails a database of fewer than 2000 nets or 800 blocks, this fails
# anything that is not exactly the 2403 and 867 that ship.  A bundle
# carrying most of the database is the failure that a threshold lets
# through, and it is the one PyInstaller actually produces.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VENV=.venv-build
PY="$VENV/bin/python"
APP="dist/Crystal Builder.app"
LOG="${TMPDIR:-/tmp}/crystal-builder-selftest.log"
SHOT="${TMPDIR:-/tmp}/selftest.png"

skip_tests=0
no_push=0
for arg in "$@"; do
    case "$arg" in
        --skip-tests) skip_tests=1 ;;
        --no-push)    no_push=1 ;;
        -h|--help)    sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

[ -x "$PY" ] || fail "no $PY -- create it with: python3 -m venv $VENV"
[ "$(uname)" = Darwin ] || fail "macOS only; this builds a .app"

started=$SECONDS

# 1. The ase extra is what the vendored PORMAKE imports, and the MOF
#    tests skip rather than fail without it -- so a venv missing it
#    produces a green suite and a bundle with no MOF builder.
step "1/8  Dependencies (mirrors the CI build job)"
"$VENV/bin/pip" install -q -e ".[gui,build,sketch,ase,test]"
"$VENV/bin/pip" install -q "pyinstaller>=6"

# 2. Serial, because -n auto wedges roughly one run in four; see the
#    deadlock note in CLAUDE.md.
step "2/8  Test suite (~155 s, serial)"
if [ "$skip_tests" = 1 ]; then
    echo "skipped (--skip-tests)"
else
    "$PY" -m pytest -q
fi

step "3/8  PyInstaller bundle"
QT_API=pyside6 "$PY" -m PyInstaller --noconfirm packaging/macos.spec
[ -d "$APP" ] || fail "PyInstaller produced no $APP"

# 4. ~175 MB of the download, and it invalidates any earlier
#    signature, which is why signing lives inside this script and not
#    in the spec.
step "4/8  Strip and ad-hoc sign"
"$PY" packaging/postbuild.py "$APP"

# 5. The one that matters: PORMAKE's data files are the thing most
#    likely to be missing from a frozen build, and missing data is
#    silent.
step "5/8  Selftest in the frozen bundle"
set +e
XTAL_NO_CONFIRM_CLOSE=1 "$APP/Contents/MacOS/Crystal Builder" \
    --selftest --selftest-image "$SHOT" 2>&1 | tee "$LOG"
status=${PIPESTATUS[0]}
set -e
[ "$status" = 0 ] || fail "selftest exited $status -- see $LOG"

grep -q "PORMAKE database: 2403 nets, 867 blocks" "$LOG" \
    || fail "selftest ran but the PORMAKE database is not in the bundle
         (expected: PORMAKE database: 2403 nets, 867 blocks)
         see $LOG"
grep -q "net identified as pcu" "$LOG" \
    || fail "selftest ran but the MOF builder did not build pcu
         (expected: MOF builder: pcu-N59-E32, 98 atoms, ...)
         see $LOG"
echo "vendoring proven in a frozen build"

step "6/8  Installed size"
du -sh "$APP"

step "7/8  DMG"
"$PY" packaging/makedmg.py "$APP" dist
ls -lh dist/*.dmg | tail -5

step "8/8  Push"
if [ "$no_push" = 1 ]; then
    echo "skipped (--no-push)"
elif [ -n "$(git status --porcelain)" ]; then
    fail "working tree is dirty -- commit or stash, then: git push"
elif [ "$(git rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0)" \
      = 0 ]; then
    echo "nothing to push; already up to date with the upstream branch"
else
    git push
fi

printf '\n\033[32mdone in %d min %d s\033[0m\n' \
    $(( (SECONDS - started) / 60 )) $(( (SECONDS - started) % 60 ))
echo "  app:  $APP"
echo "  shot: $SHOT"
