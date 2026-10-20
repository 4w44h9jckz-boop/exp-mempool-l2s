#!/usr/bin/env bash
# leanVM's own benchmark CLI, run on this machine, its output printed ASCII only
# beside what it ran on (decision record 0033). Not run by `make`: a benchmark
# measures a machine, so its output is committed once and the tables are
# derived from it (`bench/leanvm/fit.py`), never rerun to check them.
#
#   bench/leanvm/run.sh DIR > bench/results/YYYY-MM-DD-leanvm.txt
#
# DIR is a clone of https://github.com/leanEthereum/leanVM outside this
# repository. The script checks out COMMIT there, builds the CLI in release
# mode with the repository's own settings (`-C target-cpu=native`), and runs
# each benchmark with one warmup pass and REPEAT measured passes, each after
# COOLDOWN idle seconds. Run it on an otherwise idle machine. A run that
# fails, as one the out-of-memory killer stops, is recorded with its exit
# status and the rest go on.

set -euo pipefail

COMMIT=1f9e4c4f478038a95a2619009cb9cf654ae0824e
REPEAT=${REPEAT:-3}
COOLDOWN=${COOLDOWN:-2}
dir=$1
here=$(cd "$(dirname "$0")/../.." && pwd)

git -C "$dir" checkout -q "$COMMIT"
(cd "$dir" && cargo build -q --release -p leanvm-cli)
bin="$dir/target/release/leanvm"

ascii() {  # the CLI prints a plus-minus sign and an arrow; nothing else is kept outside ASCII
  sed -e 's/\xc2\xb1/+-/g' -e 's/\xe2\x86\x92/->/g' | LC_ALL=C tr -cd '\11\12\40-\176'
}

echo "# leanVM benchmarks"
echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "leanvm commit: $(git -C "$dir" rev-parse HEAD)"
echo "commit: $(git -C "$here" rev-parse HEAD)"
echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
echo "cores: $(nproc)"
echo "memory: $(free -b | awk '/^Mem:/ {print $2}') bytes"
memcg=$(awk -F: '$2 == "memory" {print $3}' /proc/self/cgroup)
limit=$(cat "/sys/fs/cgroup/memory$memcg/memory.limit_in_bytes" 2>/dev/null \
  || cat "/sys/fs/cgroup$(awk -F: '$1 == "0" {print $3}' /proc/self/cgroup)/memory.max" 2>/dev/null || echo unknown)
echo "memory limit of this process group: $limit bytes"
echo "rustc: $(rustc --version)"
echo "repeat: $REPEAT, cooldown: $COOLDOWN s"

run() {
  echo
  echo "\$ leanvm $*"
  set +e
  "$bin" --repeat "$REPEAT" --cooldown "$COOLDOWN" "$@" 2>/dev/null | ascii
  status=${PIPESTATUS[0]}
  set -e
  if [ "$status" -ne 0 ]; then
    echo "  exit status                 : $status"
  fi
}

# Direct leanSPHINCS signatures in one aggregate: the cost of each, and of none.
for n in 1 16 64 128 245; do
  run aggregate --sphincs "$n" --log-inv-rate 1
done
# Recursive inputs: k child aggregates of 16 leanSPHINCS signatures each, the
# most one wrapper may carry (`MAX_LEANSIG_DEPS_PER_WRAPPER`), and one larger child.
for k in 2 4 8 16; do
  run recursion --n "$k" --xmss-per-leaf 0 --sphincs-per-leaf 16 --log-inv-rate 1
done
run recursion --n 2 --xmss-per-leaf 0 --sphincs-per-leaf 128 --log-inv-rate 1
# The README's own runs, to set this machine beside the one it reports.
run aggregate --xmss 900 --log-inv-rate 1
run recursion --n 2 --xmss-per-leaf 900 --log-inv-rate 2
