# 0033. A benchmark measures a machine once, and what is derived from it is checked

Date: 2026-10-13. Status: accepted.

## Context

The owner asked for "performance benchmarks, or simulations" to test an
earlier argument about in-mempool aggregation. Two of the outcomes that
would falsify it are about cost, not behaviour: that $w$, the work to reject
one transaction, is large, and that aggregation does not fit the interval:
if proving one aggregation interval on commodity hardware takes longer than
the interval, only builders can aggregate. An earlier problem record tested
the second against the figures leanVM's README publishes, from the
implementers' Mac M4 Max, and said itself that they are neither a
commodity-hardware figure nor an independent measurement. Nothing in this
repository could answer either: the simulator spends no proving time unless an
experiment sets a fixed delay (`docs/spec/05-aggregation.md`, version 1, Not
modelled).

leanVM is public (github.com/leanEthereum/leanVM, with Apache 2.0 and MIT
licence files), builds
with the Rust toolchain this machine has, and ships a benchmark CLI that
aggregates leanSPHINCS signatures and merges child proofs by recursion, the
two operations EIP-8288's aggregate is made of. Running it here measures a
4-core cloud machine with 15.7 GiB, of which a process may use 13.4 GiB
(its memory control group's limit), not the implementers' 16-core laptop
with 48 GB, and is a measurement of this repository's rather than a
quotation.

A benchmark is not an experiment. An experiment is deterministic from its
seed, and `make experiments` reruns it and fails if its committed result has
moved (decision record 0017). A benchmark measures a machine: rerun, it
prints other numbers, and on another machine, very different ones. Checking
it by rerunning would fail every time, and so would check nothing.

## Decision

1. **Benchmarks live in `bench/`**, one directory per tool, with a script
   that builds the tool at a pinned commit outside this repository and prints
   its raw output, and a result file per run in `bench/results/`, named by
   date, holding that output with the date, the tool's commit, this
   repository's commit, the processor, the core count, the memory, the
   memory a process may use and the compiler version. A run that fails, as
   one the out-of-memory killer stops, is recorded with its exit status and
   the rest go on: what does not fit is a measurement too. The script is shell and the tool is not Python, so the
   standard-library rule, which covers `ref/`, `sim/`, `conformance/` and
   `scripts/`, does not reach it; nothing in `make` builds or runs it.
2. **The raw output is measured once and never regenerated to check it.** A
   later run on any machine is a new file beside the old one, and a document
   that quotes a figure names the file it came from.
3. **What is derived from the raw output is deterministic, and checked.** A
   standard-library script beside the runner reads the raw file and prints a
   table and any constants fitted from it, as `bench/results/<name>.md`;
   `make checks` reruns it and fails if the committed table has moved, as
   `make experiments` does for an experiment. An experiment that uses the
   constants imports the same function, so the number it runs with is the
   number the table shows.
4. **Output is ASCII.** The runner transliterates the two non-ASCII
   characters leanVM prints, the plus-minus sign and the arrow, and drops
   anything else outside ASCII, so that `scripts/check-ascii.sh` covers the
   raw file too.
5. **The first tool is leanVM at `1f9e4c4f`**, the head of its main branch
   on 2026-10-13, built with its own release profile and
   `-C target-cpu=native`, on this session's machine. A first attempt
   stopped at the recursion over 16 children, which the kernel's
   out-of-memory killer ended at 13,965,404 KiB resident, the group's limit, and before the runner
   recorded failures; it was discarded and the whole benchmark run again,
   so the committed file is one invocation of the committed script. Its README's figures,
   from an M4 Max with 16 cores and 48 GB, are quoted beside ours in the
   table and are never mixed into a fit.

## Consequences

- `bench/README.md` says what lives there, and `make checks` gains the
  derivation check.
- A figure from a benchmark carries its machine wherever it is quoted. The
  ratio of this machine's time to the README's at the same benchmark is a
  measured ratio between two machines, not a property of either.
- The fit that turns a run into AG-9's constants is a model of leanVM's cost,
  linear in what an aggregate takes in; decision record 0034 says where that
  model is used and what it leaves out.
