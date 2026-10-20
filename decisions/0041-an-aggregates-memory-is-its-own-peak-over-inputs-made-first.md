# 0041. An aggregate's memory is its own peak, over inputs made first

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 32 asks for the peak memory of proving an aggregate,
against what an interval's aggregate holds, on the benchmark machine.
go-ethereum's README at the commit `docs/spec/README.md` pins, `93d78a01`, lists under
Hardware Requirements a minimum of "8GB RAM" and a recommendation of
"16GB+ RAM".

`bench/results/2026-10-13-leanvm.md` has a peak for each of leanVM's CLI
benchmarks, but a recursion's peak "includes proving its children": the CLI
proves the leaves in the same process before the step it times. An
aggregate a node makes in the pool takes its recursive inputs from its
peers and proves only the step. leanVM at `1f9e4c4f` takes at most
`MAX_RECURSIONS`, 16, children in one aggregate
(`crates/rec_aggregation/src/aggregation.rs`).

## Decision

1. **The peak is the aggregate's, over what the process already held.**
   `bench/leanvm-memory/memory.rs` makes the inputs first, then resets the
   process's peak resident set (`/proc/self/clear_refs`, 5) and proves the
   aggregate, twice, the first a warmup whose peak is kept, since a node
   that proves every interval keeps leanVM's caches. It prints what the
   process held before and the peak, which includes it. One subject a
   process, so that nothing an earlier subject allocated is counted.
2. **A recursive input is a leaf aggregate of one signature.** It is the
   smallest aggregate, the input whose cost is least confounded by what it
   covers. Leaves of 16 signatures are run at 2, 4 and 8 children too, the
   CLI's own recursion benchmark, so the two benchmarks can be compared.
   Direct leanSPHINCS signatures are run at the counts `bench/leanvm/` ran.
3. **A cost is a joint fit, and a capacity is a measured peak.** Memory
   follows the VM's tables, each padded to a power of two, so it rises in
   steps: 6 and 7 recursive inputs peak alike, as do 9 and 10. A line
   through one kind of subject is a summary, and its intercept can be
   negative. What a clause needs is a cost it can add up, so `fit.py`
   fits the peak against recursive inputs and direct signatures together,
   $a + b r + c s$ in MiB, one base for both, and `cost()` returns it for
   experiments. What a machine holds is read from the peaks measured, not
   from any line: the most inputs whose peak was within the machine's
   memory, and the next count's peak where one was measured above it.
4. **The machine's memory is all the proving's.** The capacity table
   assumes nothing else resident. A node also runs its client; how much of
   a machine the client leaves is the experiment's assumption to state,
   not the benchmark's. The table is in GiB, and go-ethereum's figures are
   in GB, which is the smaller unit; a figure quoted against the README
   says which.

## Consequences

- `bench/leanvm-memory/` holds the harness, its runner and its derivation,
  `bench/results/2026-10-13-leanvm-memory.txt` the one run and
  `bench/results/2026-10-13-leanvm-memory.md` its table.
- Subjects above 10 recursive inputs ran out of the benchmark machine's
  memory limit, so the table says "at least" where nothing was measured
  above a machine's memory.
- What bounds an aggregate's memory in the pool, and what a node that cannot
  prove does, is a clause, not a benchmark; it is decided where the clause is
  written.
