#!/bin/bash
# One line per configuration: how many of $REPEATS repeats survived.
cd /Users/sam/Projects/Jules/Crystal-Builder
PY=.venv/bin/python
REPEATS=${REPEATS:-5}
JOBS=${JOBS:-200}
run() {                       # run <label> <extra args...>
  local label="$1"; shift
  local ok=0 crash=0 hang=0 how=""
  for i in $(seq 1 "$REPEATS"); do
    out=$($PY review/probes/stress_workers.py --jobs "$JOBS" --timeout 20 "$@" 2>&1)
    rc=$?
    if   [ $rc -eq 3 ]; then hang=$((hang+1)); how="$how hang"
    elif [ $rc -ne 0 ]; then crash=$((crash+1))
      how="$how $(echo "$out" | grep -m1 -oE 'Segmentation fault|Fatal Python error: Aborted|Destroyed while thread' | tr ' ' '_')"
    else ok=$((ok+1)); fi
  done
  printf '%-44s ok=%d crash=%d hang=%d %s\n' "$label" "$ok" "$crash" "$hang" "$how"
}
