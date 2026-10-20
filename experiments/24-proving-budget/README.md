# 24. Proving time in the aggregation interval

**Question.** EIP-8288 has every mempool node prove one recursive STARK over
what it holds every `AGGREGATION_INTERVAL` of 1000 ms. Does that fit in the
interval at the prover's measured cost, and what happens to the delay and
the reach of transactions with a dependency when it does not? What happens
when only some nodes can prove, and when an adversary floods the nodes with
transactions that carry a dependency and a high tip and never pay?

**Clauses exercised.** AG-9 (`docs/spec/05-aggregation.md`, version 2): an
aggregate's proving time, and the budget that bounds what AG-7 lists. AG-5
to AG-8 as in experiment 06. Decision record 0034 has the readings, and
decision record 0033 the benchmark the costs come from.

EIP-8288 (Draft, read at `258836f9`, and unchanged on master at `3db7d3f4`
on 2026-10-13) gives no proving time, no hardware and no budget. It gives
the order for a node that "will not have enough proving time to aggregate
in _all_ aggregates that it saw": its own previous aggregate, removals,
other nodes' aggregates by how many new transactions they add, and users'
transactions by priority fee. Whether an interval's proving fits in the
interval on commodity hardware decides who can aggregate: if it does not,
only builders can, and the set of nodes that aggregate is no longer open.
Experiment 06 spent a fixed delay or none, and left this open.

On EIPs master `LEANSTARK_SCHEME` is now reserved: "a frame that uses it is
invalid until get_deps_hash is defined for it". The leanSTARK rows below
read the pinned text, at which a user's own STARK is a dependency; the
leanSPHINCS rows hold under both.

## Setup

- **Costs** (decision record 0034), fitted from leanVM's own benchmark at
  `1f9e4c4f` run on this repository's machine
  (`bench/results/2026-10-13-leanvm.md`):
  `prove_base` 468.0 ms, `prove_sig` 19.9 ms a leanSPHINCS triple, and
  `prove_recursive` and `prove_stark` 951.7 ms a recursive input or a
  leanSTARK triple. The laptop's are 79.1, 3.4 and 178.0 ms: this
  machine's scaled by the README's time over ours, 0.169 for its
  aggregation of 245 signatures and 0.187 for its 2-to-1 recursion. So a
  budget of one interval holds 26 leanSPHINCS triples and no recursive
  input on this machine, since `prove_base` and one input alone pass
  1000 ms, and 270 triples or 5 inputs on the laptop.
- **Network**: experiment 06's, 30 nodes with 8 peers each, a block every
  12 s from a rotating proposer, but a gas limit of 30,000,000, so that gas
  never binds: a leanSTARK transaction takes 133,849 gas with AG-8's
  charge and a leanSPHINCS one 106,849. Wallets, each its own
  default-code sender, send transactions with one dependency of their own
  as mode 0 wrappers to random nodes for 15 minutes of a 20-minute run, and
  resend after every block that leaves them out.
- **Nodes**, all with `cap_aggregates` false except one row:
  - `no proving time`: experiment 06's uncapped reading, the four costs 0.
  - `this machine, budget`: this machine's costs and a budget of one
    interval, so a node lists in AG-7's order what it can prove in 1000 ms.
  - `this machine, no budget`: the same costs and no budget, so a node
    lists everything and skips the ticks that come while it is proving.
  - `laptop, budget` and `laptop, no budget`: the costs scaled to the
    README's machine.
  - `capped, laptop, budget`: the text's reading, the wrapper limits
    binding aggregates, with the laptop's costs and the budget.
- **Section 2**: a share of the nodes can prove, at the laptop's costs
  with the budget. The others have a budget of 0, so they send no
  aggregate, and build no block.
- **Section 3**: experiment 05's `drained` flood: after every block a node
  imports, k transactions with a leanSTARK dependency handed to that node,
  at a tip above every honest one, whose sponsor empties itself
  in the next block so that none is ever included. Under `no proving
  time`, `laptop, budget` and `this machine, no budget`.
- Seed 1. 32 runs take about two minutes on four cores.

## Run

```
python3 experiments/24-proving-budget/run.py > experiments/24-proving-budget/results.md
```

## Results

From [results.md](results.md).

**Section 1, against demand**, leanSTARK dependencies, a subset of the
columns. Delays are in seconds from first sending; time is an aggregate's
mean proving time in ms; busy is the share of ticks a node skipped while
proving. Every transaction sent landed in every row.

| nodes | a slot | delay p50 | p90 | spread | time ms | inputs | busy | a s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| no proving time | 2 | 7.00 | 11.03 | 29.98 | 0.00 | 1.13 | 0.00 | 0.52 |
| this machine, budget | 2 | 62.77 | 104.06 | 7.65 | n/a | n/a | 0.00 | 0.00 |
| this machine, no budget | 2 | 9.56 | 16.67 | 28.07 | 1607.66 | 1.18 | 0.36 | 0.30 |
| laptop, budget | 2 | 7.12 | 11.45 | 29.83 | 283.08 | 1.14 | 0.00 | 0.52 |
| no proving time | 8 | 6.90 | 11.58 | 29.98 | 0.00 | 1.42 | 0.00 | 0.90 |
| this machine, budget | 8 | 57.84 | 105.83 | 7.40 | n/a | n/a | 0.00 | 0.00 |
| this machine, no budget | 8 | 13.97 | 20.14 | 27.44 | 2752.90 | 2.27 | 0.69 | 0.29 |
| laptop, budget | 8 | 7.90 | 12.46 | 29.67 | 350.09 | 1.50 | 0.00 | 0.92 |
| capped, laptop, budget | 8 | 41.91 | 79.56 | 15.84 | 257.10 | 0.99 | 0.00 | 1.00 |
| no proving time | 32 | 6.80 | 11.48 | 29.96 | 0.00 | 1.96 | 0.00 | 0.99 |
| this machine, budget | 32 | 58.71 | 105.47 | 7.44 | n/a | n/a | 0.00 | 0.00 |
| this machine, no budget | 32 | 23.48 | 32.89 | 23.36 | 7507.76 | 5.59 | 0.88 | 0.12 |
| laptop, budget | 32 | 8.13 | 12.82 | 29.64 | 573.09 | 2.68 | 0.00 | 0.99 |
| laptop, no budget | 32 | 8.02 | 12.75 | 29.62 | 575.91 | 2.69 | 0.01 | 0.99 |

`laptop, no budget` is `laptop, budget` to the hundredth at 2 and 8 a
slot. With leanSPHINCS dependencies, where this machine's budget holds 26
triples verified directly:

| nodes | a slot | delay p50 | p90 | spread | time ms | inputs | direct | busy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| no proving time | 128 | 6.54 | 11.45 | 29.94 | 0.00 | 2.60 | 0.36 | 0.00 |
| this machine, budget | 32 | 15.81 | 31.02 | 18.18 | 513.41 | 0.00 | 2.28 | 0.00 |
| this machine, budget | 128 | 15.99 | 31.78 | 18.34 | 611.61 | 0.00 | 7.22 | 0.00 |
| this machine, no budget | 128 | 22.29 | 31.83 | 23.09 | 7565.32 | 7.32 | 6.71 | 0.88 |
| laptop, budget | 128 | 8.22 | 13.21 | 29.30 | 918.67 | 4.71 | 0.42 | 0.00 |

A node that aggregates every interval sent its 8 peers 2,300.15 KiB a
second at 8 a slot and 2,529.72 at 32, at the benchmark's 319.9 KiB a
proof.

**Section 2, when only some nodes can prove**, at 8 a slot.

| provers | nodes | landed | delay p50 | p90 | spread |
| --- | --- | --- | --- | --- | --- |
| 100% | 30 | 580 of 580 | 7.90 | 12.46 | 29.67 |
| 50% | 15 | 580 of 580 | 12.96 | 31.52 | 29.70 |
| 20% | 6 | 569 of 569 | 27.52 | 85.43 | 29.81 |

**Section 3, a flood that never pays**, at 8 a slot. None of the flood was
included.

| nodes | k | delay p50 | p90 | spread | time ms | junk share | junk sent |
| --- | --- | --- | --- | --- | --- | --- | --- |
| no proving time | 0 | 6.90 | 11.58 | 29.98 | 0.00 | n/a | 0 |
| no proving time | 32 | 6.90 | 11.58 | 29.98 | 0.00 | 0.84 | 68160 |
| laptop, budget | 0 | 7.90 | 12.46 | 29.67 | 350.09 | n/a | 0 |
| laptop, budget | 8 | 7.90 | 12.46 | 29.67 | 440.81 | 0.64 | 17040 |
| laptop, budget | 32 | 8.05 | 12.74 | 29.69 | 759.48 | 0.84 | 68160 |
| this machine, no budget | 0 | 13.97 | 20.14 | 27.44 | 2752.90 | n/a | 0 |
| this machine, no budget | 8 | 26.19 | 37.13 | 21.14 | 8251.31 | 0.49 | 17040 |
| this machine, no budget | 32 | 49.37 | 71.77 | 14.55 | 19853.91 | 0.44 | 68160 |

## What it shows

- **On this machine one interval does not hold one recursive input.**
  leanVM proved a recursion over 2 children of 16 signatures in 1.798 s and
  an aggregate of 16 signatures in 0.594 s (`bench/results/2026-10-13-leanvm.md`).
  At the fitted costs an aggregate with one recursive input or one
  leanSTARK triple takes 468.0 and 951.7 ms, more than the interval. So
  nodes that keep to the interval list
  nothing with a leanSTARK dependency and send no aggregate: a transaction
  reaches a block only when its wallet's resend reaches the proposer, at a
  median of 57.84 s at 8 a slot against 6.90 s with no proving time, and
  becomes pending at 7.40 of 30 nodes. Everything sent still landed. This
  is the failing case of the test above, proving that takes longer than
  the interval, on one 4-core cloud machine.
- **A node that ignores the interval keeps the network aggregating, at its
  own pace.** Without a budget the same nodes skipped 0.69 of their ticks
  at 8 a slot and 0.88 at 32, made 0.29 and 0.12 aggregates a second, and
  took 2752.90 and 7507.76 ms to prove one. The median delay was 13.97 s
  and 23.48 s, against 6.90 and 6.80. Slow proving lengthens the cadence;
  it does not stop aggregation, but the cadence is no longer the EIP's.
- **With signatures alone, a slow node keeps its own users and loses
  everyone else's.** At this machine's budget a node verifies its own
  users' leanSPHINCS signatures directly, 7.22 an aggregate at 128 a slot,
  and takes no peer's aggregate, since that is a recursive input. A
  transaction reaches its entry node's peers and no further, 18.34 nodes,
  and waits a median of 15.99 s.
- **At the laptop's costs the interval is not the constraint.** Its
  aggregates took 350.09 ms at 8 a slot and 573.09 at 32, the budget never
  bound at 2 and 8 a slot, and the median delay was 7.12, 7.90 and 8.13 s
  at 2, 8 and 32 a slot, against 7.00, 6.90 and 6.80 with no proving
  time. At 128 leanSPHINCS transactions a slot an aggregate took 918.67 ms,
  close to the interval.
- **The text's cap still makes a queue.** `capped, laptop, budget` waited a
  median of 41.91 s at 8 a slot against 7.90 s uncapped, as experiment 06
  found without proving time.
- **A share of provers is a share of proposers.** With 6 of 30 nodes able
  to prove, at the laptop's costs, every transaction still landed, at a
  median of 27.52 s and a p90 of 85.43 s, against 7.90 and 12.46 with all
  30. A transaction handed to a node that cannot prove waits for its
  wallet to resend it to one that can.
- **Junk that never pays takes a budget's slack, and a slow prover's
  cadence.**
  - At the laptop's costs the flood made up 0.64 of what aggregates listed
    at k = 8 and 0.84 at k = 32, and raised an aggregate's proving time
    from 350.09 to 759.48 ms; the honest median delay went from 7.90 to
  8.05 s and the p90 from 12.46 to 12.74 s.
    AG-7 takes other nodes' aggregates in step 2, before users'
    transactions by tip in step 3, and a peer's aggregate costs one input
    whatever it carries, so the junk's high tip bought it the budget left
    after the peers; the run is consistent with that and does not isolate
    it.
  - Without a budget on this machine the flood is proven like everything
    else: an aggregate took 8251.31 ms at k = 8 and 19853.91 at k = 32, and
    the honest median delay rose from 13.97 s to 26.19 and 49.37 s.
  - None of the 68,160 junk transactions at k = 32 was included, so none
    paid. EIP-8288's cadence bounds re-proving to one aggregate an interval
    (decision record 0034), so the unbounded re-proving that spoiled batches
    could cause did not arise; what the junk took was proving time.
- **Aggregation costs bandwidth that the model does not charge.** A node
  sending one 319.9 KiB proof to each of 8 peers every second sent
  2,529.72 KiB a second at 32 a slot, the benchmark's size against
  experiment 06's floor of 128 kB.

## What it does not show

- **Memory.** The benchmark's recursion over 8 children peaked at
  12.333 GiB, and the one over 16, leanVM's `MAX_RECURSIONS`, was killed at
  the limit this machine sets a process, 14,343,688,192 bytes. Nothing here charges for
  memory, and a node with less cannot prove those recursions at all.
- **Bandwidth.** As in experiment 06, no message is slowed for its size.
  KiB/s prices each aggregate at the benchmark's proof size.
- **The step function.** leanVM pads its tables to powers of two, so its
  proving time moves in steps; AG-9 is the fitted line through them.
- **One machine, one run.** The costs are this machine's on one day. The
  laptop rows scale them by one ratio, at one benchmark, which is not a
  model of the laptop.
- **A builder market.** A node that cannot prove builds no block; a market
  in which it sells its slot to a prover is not modelled.
- **FOCIL's includers**, whose lists carry a recursive STARK under the
  EIP's FOCIL extension, stay Not modelled.
