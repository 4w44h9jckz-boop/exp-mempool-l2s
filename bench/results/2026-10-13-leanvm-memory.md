# leanVM: the memory an aggregate takes to prove

From `bench/results/2026-10-13-leanvm-memory.txt`, printed by `bench/leanvm-memory/fit.py` (decision records 0033 and 0041).

- date: 2026-10-13T14:22:37Z
- leanvm commit: 1f9e4c4f478038a95a2619009cb9cf654ae0824e
- commit: fcee2b7c96c383b121f78b396674592fbc66a8bd
- harness sha256: 17838e77119e31fd02bf3986b84652304ada1c53f7fa9b1810f58c0f4a7ccf4e
- cpu: Intel(R) Xeon(R) Processor @ 2.10GHz
- cores: 4
- memory: 16874930176 bytes
- memory limit of this process group: 14343688192 bytes
- rustc: rustc 1.97.0 (2d8144b78 2026-07-07)
- log_inv_rate: 1

Each subject is a process of its own (`bench/leanvm-memory/memory.rs`). A recursive subject first makes
its inputs, leaf aggregates of the leanSPHINCS signatures per leaf shown; a signature subject verifies
its signatures directly. The process's peak is then reset, and one aggregate proved twice, the first
discarded: held is what the process had resident before, peak its highest resident set while proving,
which includes what it held, and time the second proof's.

## Runs

| kind | inputs | signatures per leaf | held MiB | peak MiB | peak GiB | prove ms | cycles | proof KiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recursive | 1 | 1 | 388.5 | 1321.9 | 1.29 | 738.3 | 450,560 | 265.9 |
| recursive | 2 | 1 | 385.4 | 2515.2 | 2.46 | 1481.8 | 901,120 | 279.7 |
| recursive | 3 | 1 | 384.9 | 3879.3 | 3.79 | 2279.4 | 1,277,952 | 278.8 |
| recursive | 4 | 1 | 394.1 | 4786.1 | 4.67 | 2934.6 | 1,802,240 | 290.7 |
| recursive | 5 | 1 | 396.6 | 6481.8 | 6.33 | 3852.5 | 2,555,904 | 323.6 |
| recursive | 6 | 1 | 402.0 | 7443.9 | 7.27 | 4784.2 | 2,555,904 | 290.3 |
| recursive | 7 | 1 | 397.5 | 7396.4 | 7.22 | 4476.7 | 2,555,904 | 292.2 |
| recursive | 8 | 1 | 408.3 | 9089.5 | 8.88 | 5512.6 | 3,604,480 | 304.7 |
| recursive | 9 | 1 | 397.6 | 12722.3 | 12.42 | 7500.4 | 5,111,808 | 336.0 |
| recursive | 10 | 1 | 386.3 | 12708.3 | 12.41 | 8087.2 | 5,111,808 | 337.4 |
| recursive | 11 | 1 | | exit status 137 | | | | |
| recursive | 12 | 1 | | exit status 137 | | | | |
| recursive | 2 | 16 | 1126.3 | 3819.5 | 3.73 | 1736.5 | 1,212,416 | 310.3 |
| recursive | 4 | 16 | 1130.2 | 6492.4 | 6.34 | 3761.2 | 2,424,832 | 325.1 |
| recursive | 8 | 16 | 1139.8 | 12630.2 | 12.33 | 7118.7 | 4,849,664 | 341.9 |
| sphincs | 1 |  | 166.8 | 400.7 | 0.39 | 161.0 | 146,432 | 219.4 |
| sphincs | 16 |  | 166.9 | 1139.4 | 1.11 | 590.6 | 221,184 | 249.5 |
| sphincs | 64 |  | 174.3 | 3307.1 | 3.23 | 2065.4 | 753,664 | 315.5 |
| sphincs | 128 |  | 173.3 | 6502.5 | 6.35 | 3587.8 | 1,507,328 | 332.6 |
| sphincs | 245 |  | 165.8 | 9667.9 | 9.44 | 4653.7 | 2,359,296 | 314.2 |

## Fitted

The peak against the number of inputs, by least squares, $m(n) = a + b n$ in MiB, over the subjects that
proved:

| aggregate over | a, MiB | b, MiB an input |
| --- | --- | --- |
| recursive inputs of 1 signature | -124.6 | 1265.3 |
| recursive inputs of 16 signatures | 750.6 | 1477.9 |
| leanSPHINCS signatures, directly | 706.4 | 38.5 |

Both kinds together, $m(r, s) = a + b r + c s$ for $r$ recursive inputs of one signature and $s$
signatures verified directly, which is AG-10's form (`docs/spec/05-aggregation.md`): `memory_base` 318.5, `memory_recursive` 1202.0 and `memory_sig` 40.7 MiB.
Each line is a summary: memory follows the VM's tables, each padded to a power of two, so it rises in
steps, and subjects whose tables pad alike peak alike.

| kind | inputs | peak GiB | by the joint fit, GiB | by the envelope, GiB |
| --- | --- | --- | --- | --- |
| recursive | 1 | 1.29 | 1.48 | 3.03 |
| recursive | 2 | 2.46 | 2.66 | 4.21 |
| recursive | 3 | 3.79 | 3.83 | 5.38 |
| recursive | 4 | 4.67 | 5.01 | 6.56 |
| recursive | 5 | 6.33 | 6.18 | 7.73 |
| recursive | 6 | 7.27 | 7.35 | 8.90 |
| recursive | 7 | 7.22 | 8.53 | 10.08 |
| recursive | 8 | 8.88 | 9.70 | 11.25 |
| recursive | 9 | 12.42 | 10.88 | 12.42 |
| recursive | 10 | 12.41 | 12.05 | 13.60 |
| sphincs | 1 | 0.39 | 0.35 | 1.90 |
| sphincs | 16 | 1.11 | 0.95 | 2.50 |
| sphincs | 64 | 3.23 | 2.85 | 4.40 |
| sphincs | 128 | 6.35 | 5.40 | 6.95 |
| sphincs | 245 | 9.44 | 10.05 | 11.60 |

The envelope, the last column, is the joint fit with `memory_base` raised to 1904.4 MiB, by the most any peak lay above the fit, so that no subject's peak exceeds it: the costs a node that must not run out of memory budgets against (decision record 0042).

## What a machine's memory holds

The most recursive inputs of one signature an aggregate took, among the subjects measured, with a peak
within a machine's memory and nothing else resident; and whether a subject with one more input was
measured to need more.

| machine GiB | inputs | one more |
| --- | --- | --- |
| 8 | 7 | 8 inputs peaked at 8.88 GiB |
| 16 | at least 10 | none measured above it |
| 32 | at least 10 | none measured above it |
| 64 | at least 10 | none measured above it |

Subjects of 11 and 12 inputs ran out of this machine's limit of 13.36 GiB, so
nothing above it was measured; leanVM takes at most `MAX_RECURSIONS`, 16, inputs in one aggregate.
