# Benchmarks

Measurements of a machine, kept apart from the experiments (decision record
0033). An experiment is deterministic from its seed, and `make experiments`
reruns it and fails if its result has moved. A benchmark is not: rerun, it
prints other numbers, and on another machine very different ones. So a
benchmark's raw output is committed once, with the machine it ran on, and
what is derived from it is checked instead.

| Tool | Runner | Derivation | Results |
| --- | --- | --- | --- |
| leanVM at `1f9e4c4f`, from the leanEthereum organization whose tooling EIP-8288 assumes | `bench/leanvm/run.sh` | `bench/leanvm/fit.py` | `bench/results/2026-10-13-leanvm.txt`, `bench/results/2026-10-13-leanvm.md` |
| leanVM at `1f9e4c4f`, the memory one aggregate takes to prove, and AG-10's costs and their envelope (decision records 0041 and 0042) | `bench/leanvm-memory/run.sh` | `bench/leanvm-memory/fit.py` | `bench/results/2026-10-13-leanvm-memory.txt`, `bench/results/2026-10-13-leanvm-memory.md` |

- **The runner** builds the tool at a pinned commit, in a clone outside this
  repository, and prints its output with the date, both commits, the
  processor, the core count, the memory, the memory a process may use and
  the compiler; a run that fails is recorded with its exit status. It is not run by
  `make`; run it on an otherwise idle machine and commit what it prints as a
  new file in `bench/results/`, named by date. A later run is a new file
  beside the old one, never a replacement.
- **The derivation** is Python's standard library alone. It reads a raw file
  and prints a table, and any constants fitted from it, as the `.md` beside
  it. `make checks` reruns it and fails if the committed table has moved.
- **A figure from a benchmark carries its machine** wherever it is quoted.
  The leanVM tables set this machine beside the figures leanVM's README
  gives for the implementers' laptop, which are quoted, never fitted.

Experiment 24 takes AG-9's proving costs from `bench/leanvm/fit.py`, so the
constants it runs with are the ones the table shows, and AG-10's memory
costs (`docs/spec/05-aggregation.md`) are the ones
`bench/leanvm-memory/fit.py` fits.

A result's `commit` line names the commit of this repository that ran it.
The results of 2026-10-13 were run before the repository was published, and
their commits are in a history that is not public.
