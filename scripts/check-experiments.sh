#!/usr/bin/env bash
# Every offline experiment still prints its committed results.md.
#
#   scripts/check-experiments.sh                      every experiment
#   scripts/check-experiments.sh experiments/08-...   the ones named
#
# Experiments run in parallel, JOBS at a time (default: the number of
# processors). Each is a process of its own that takes its randomness from its
# own seeds, so running them together moves no number (decision record 0017).
# Results are printed in the order the experiments were named.
#
# An experiment whose run.py sets NETWORK = True reads a live endpoint and is
# skipped; its results.md records where and when it was measured instead.

set -uo pipefail
cd "$(dirname "$0")/.."

dirs=()
if [ $# -gt 0 ]; then
  for d in "$@"; do dirs+=("${d%/}"); done
else
  for script in experiments/*/run.py; do
    [ -e "$script" ] && dirs+=("$(dirname "$script")")
  done
fi
jobs=${JOBS:-$(nproc 2>/dev/null || echo 1)}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

check() {  # check DIR OUT: write a verdict to OUT, and 0 or 1 to OUT.status
  local dir=$1 out=$2
  if [ ! -e "$dir/run.py" ]; then
    echo "FAIL $dir: no run.py" > "$out"; echo 1 > "$out.status"; return
  fi
  if grep -q '^NETWORK = True' "$dir/run.py"; then
    echo "skip $dir (network)" > "$out"; echo 0 > "$out.status"; return
  fi
  if python3 "$dir/run.py" | diff -u "$dir/results.md" - > "$out.diff"; then
    echo "ok   $dir" > "$out"; echo 0 > "$out.status"
  else
    { echo "FAIL $dir: run.py no longer prints results.md"; head -40 "$out.diff"; } > "$out"
    echo 1 > "$out.status"
  fi
}

i=0
for dir in "${dirs[@]}"; do
  while [ "$(jobs -rp | wc -l)" -ge "$jobs" ]; do wait -n; done
  check "$dir" "$tmp/$i" &
  i=$((i + 1))
done
wait

status=0
for ((n = 0; n < i; n++)); do
  cat "$tmp/$n"
  [ "$(cat "$tmp/$n.status")" = 0 ] || status=1
done
exit "$status"
