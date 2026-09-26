#!/bin/bash
cd /Users/sam/Projects/Jules/Crystal-Builder
D=review/probes/perf
for case in none MOF-5 MFU4l Ni2Cl2BTDD CFA1; do
  rm -rf $D/scr_$case
  if [ "$case" = none ]; then OPEN=""; else OPEN="--open resources/samples/${case}.cif"; fi
  /usr/bin/time -l .venv/bin/python .claude/skills/run-app/drive.py \
      --scratch $D/scr_$case $OPEN --eval 'print("open")' \
      > $D/start_$case.out 2> $D/start_$case.err
  echo "--- $case --- swap: $(sysctl -n vm.swapusage | sed 's/total.*used = //;s/free.*//')"
  grep -E "sites" $D/start_$case.out | head -1
  grep -E "real|maximum resident" $D/start_$case.err | head -2
done
