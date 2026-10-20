#!/usr/bin/env bash
# How much memory leanVM takes to prove one aggregate, against how many recursive
# inputs or leanSPHINCS signatures it holds (the plan's item 32, decision record 0041).
# Not run by `make`: a benchmark measures a machine, so its output is committed
# once and the tables are derived from it (`bench/leanvm-memory/fit.py`), never
# rerun to check them (decision record 0033).
#
#   bench/leanvm-memory/run.sh DIR > bench/results/YYYY-MM-DD-leanvm-memory.txt
#
# DIR is a clone of https://github.com/leanEthereum/leanVM outside this
# repository. The script checks out COMMIT there, copies `memory.rs` in as an
# example of the CLI's package, builds it in release mode with the repository's
# own settings (`-C target-cpu=native`), runs it once for each subject, each in a
# process of its own, and removes the copy. A subject that runs out of memory is
# printed with its exit status. Run it on an otherwise idle machine.

set -uo pipefail

COMMIT=1f9e4c4f478038a95a2619009cb9cf654ae0824e
RECURSIVE="1 2 3 4 5 6 7 8 9 10 11 12"  # children of one signature each
WIDE="2 4 8"  # children of sixteen, as `bench/leanvm/` ran the CLI's recursion
SPHINCS="1 16 64 128 245"
dir=$1
here=$(cd "$(dirname "$0")/../.." && pwd)
src="$here/bench/leanvm-memory/memory.rs"
examples="$dir/bins/leanvm/examples"

git -C "$dir" checkout -q "$COMMIT" || exit 1
made_dir=0
[ -d "$examples" ] || { mkdir "$examples"; made_dir=1; }
cp "$src" "$examples/memory.rs"
cleanup() {
  rm -f "$examples/memory.rs"
  if [ "$made_dir" -eq 1 ]; then rmdir "$examples"; fi
}
trap cleanup EXIT
(cd "$dir" && cargo build -q --release --example memory -p leanvm-cli) || exit 1

echo "# leanVM aggregate memory"
echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "leanvm commit: $(git -C "$dir" rev-parse HEAD)"
echo "commit: $(git -C "$here" rev-parse HEAD)"
echo "harness sha256: $(sha256sum "$src" | cut -d' ' -f1)"
echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
echo "cores: $(nproc)"
echo "memory: $(free -b | awk '/^Mem:/ {print $2}') bytes"
memcg=$(awk -F: '$2 == "memory" {print $3}' /proc/self/cgroup)
limit=$(cat "/sys/fs/cgroup/memory$memcg/memory.limit_in_bytes" 2>/dev/null \
  || cat "/sys/fs/cgroup$(awk -F: '$1 == "0" {print $3}' /proc/self/cgroup)/memory.max" 2>/dev/null || echo unknown)
echo "memory limit of this process group: $limit bytes"
echo "rustc: $(rustc --version)"
echo "log_inv_rate: 1"
run() {
  "$dir/target/release/examples/memory" "$@" 2>/dev/null | LC_ALL=C tr -cd '\11\12\40-\176'
  local status=${PIPESTATUS[0]}
  if [ "$status" -ne 0 ]; then
    echo
    echo "subject: $1 n=$2 per_leaf=${3:-0}"
    echo "  exit status: $status"
  fi
}
for n in $RECURSIVE; do run recursive "$n" 1; done
for n in $WIDE; do run recursive "$n" 16; done
for n in $SPHINCS; do run sphincs "$n"; done
