#!/bin/sh
# Area 7: every CLI subcommand with bad arguments.
# Prints, per case: the exit status, how many lines went to stderr,
# and whether stderr contains a traceback.
set -u
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
XTAL="$ROOT/.venv/bin/xtal"
TMP=$(mktemp -d /tmp/xtalprobe.XXXXXX)
trap 'rm -rf "$TMP"' EXIT INT TERM

cp "$ROOT/resources/samples/ZIF-8.cif" "$TMP/good.cif"
mkdir -p "$TMP/adir"
printf 'not a cif at all\n' > "$TMP/junk.cif"
printf '' > "$TMP/empty.cif"
printf '2\nc\nNa 0 0 0\nCl 2 2 2\n' > "$TMP/xyzlike.cif"

run() {
  desc="$1"; shift
  out=$("$XTAL" "$@" 2>"$TMP/err" </dev/null)
  rc=$?
  errlines=$(wc -l < "$TMP/err" | tr -d ' ')
  if grep -q 'Traceback (most recent call last)' "$TMP/err"; then
    kind="TRACEBACK"
  elif [ "$errlines" -eq 0 ]; then
    kind="(no stderr)"
  elif [ "$errlines" -eq 1 ]; then
    kind="one line"
  else
    kind="$errlines lines"
  fi
  printf '%-52s rc=%-3s %-11s | %s\n' "$desc" "$rc" "$kind" \
    "$(head -c 200 "$TMP/err" | tr '\n' ' ')"
}

echo "=== missing file ==="
for c in info symmetry bonds types energy; do
  run "$c missing.cif" $c "$TMP/missing.cif"
done
run "convert missing.cif out.cif" convert "$TMP/missing.cif" "$TMP/o.cif"
run "optimize missing.cif" optimize "$TMP/missing.cif"
run "run zeopp missing.cif" run "$TMP/missing.cif" zeopp

echo
echo "=== a directory instead of a file ==="
for c in info symmetry bonds types energy; do
  run "$c <a directory>" $c "$TMP/adir"
done
run "convert <dir> out.cif" convert "$TMP/adir" "$TMP/o.cif"

echo
echo "=== a file that is not what its extension says ==="
run "info junk.cif"    info "$TMP/junk.cif"
run "info empty.cif"   info "$TMP/empty.cif"
run "info xyzlike.cif" info "$TMP/xyzlike.cif"
run "info good.cif (control)" info "$TMP/good.cif"

echo
echo "=== unknown / missing extension ==="
cp "$TMP/good.cif" "$TMP/noext"
run "info noext"             info "$TMP/noext"
cp "$TMP/good.cif" "$TMP/g.wat"
run "info g.wat"             info "$TMP/g.wat"
run "convert good.cif o.wat" convert "$TMP/good.cif" "$TMP/o.wat"

echo
echo "=== -p with a bad key=value ==="
run "run -p novalue"      run "$TMP/good.cif" zeopp -p novalue
run "run -p =noname"      run "$TMP/good.cif" zeopp -p =noname
run "run -p a=b (unknown param)" run "$TMP/good.cif" zeopp -p a=b
run "run unknown-module"  run "$TMP/good.cif" not-a-module

echo
echo "=== --supercell ==="
run "--supercell 0 0 0"   convert "$TMP/good.cif" "$TMP/s1.cif" --supercell 0 0 0
run "--supercell -1 1 1"  convert "$TMP/good.cif" "$TMP/s2.cif" --supercell -- -1 1 1
run "--supercell 1 1"     convert "$TMP/good.cif" "$TMP/s3.cif" --supercell 1 1
run "--supercell 1 1 x"   convert "$TMP/good.cif" "$TMP/s4.cif" --supercell 1 1 x
run "--supercell 50 50 50" convert "$TMP/good.cif" "$TMP/s5.cif" --supercell 50 50 50

echo
echo "=== output path == input path ==="
cp "$ROOT/resources/samples/quartz.cif" "$TMP/rt.cif" 2>/dev/null || \
  cp "$ROOT/resources/samples/ZIF-8.cif" "$TMP/rt.cif"
before=$(wc -c < "$TMP/rt.cif" | tr -d ' ')
run "convert rt.cif rt.cif" convert "$TMP/rt.cif" "$TMP/rt.cif"
after=$(wc -c < "$TMP/rt.cif" | tr -d ' ')
echo "    size before=$before after=$after"
run "convert rt.cif rt.cif --supercell 2 2 2" \
  convert "$TMP/rt.cif" "$TMP/rt.cif" --supercell 2 2 2
echo "    size now=$(wc -c < "$TMP/rt.cif" | tr -d ' ')"

echo
echo "=== output into a directory that does not exist / is read-only ==="
run "convert -> missing dir" convert "$TMP/good.cif" "$TMP/nope/o.cif"
mkdir -p "$TMP/ro" && chmod 500 "$TMP/ro"
run "convert -> read-only dir" convert "$TMP/good.cif" "$TMP/ro/o.cif"
chmod 700 "$TMP/ro"
run "convert -> a directory" convert "$TMP/good.cif" "$TMP/adir"

echo
echo "=== symmetry / energy / optimize flags ==="
run "symmetry --symprec 0"    symmetry "$TMP/good.cif" --symprec 0
run "symmetry --symprec -1"   symmetry "$TMP/good.cif" --symprec -1
run "symmetry --symprec 1e9"  symmetry "$TMP/good.cif" --symprec 1e9
run "energy --engine nope"    energy "$TMP/good.cif" --engine nope
run "optimize --max-steps 0"  optimize "$TMP/good.cif" --max-steps 0
run "optimize --max-steps -5" optimize "$TMP/good.cif" --max-steps -- -5
run "optimize --method nope"  optimize "$TMP/good.cif" --method nope

echo
echo "=== structures that break symmetry detection ==="
run "symmetry CFA1"        symmetry "$ROOT/resources/samples/CFA1.cif"
run "symmetry Ni2Cl2BTDD"  symmetry "$ROOT/resources/samples/Ni2Cl2BTDD.cif"
run "info CFA1"            info "$ROOT/resources/samples/CFA1.cif"
