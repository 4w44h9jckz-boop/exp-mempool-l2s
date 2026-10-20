# 20. A committee that clears every block

**Question.** Per-block order matching, a private market maker or a batch
auction that clears every block must finish inside one slot. An earlier MPC
study budgets such a committee at the slot divided by its round trip, 150
rounds for a 12 s slot at 80 ms and 50 for a 4 s slot, a budget that leaves
out the network on either side of the computation. With the committee's
members in the gossip network, how many batches are settled in the block
they were meant for, and how many orders make the batch they were sent for,
against the round count and slots of 12, 8 and 4 s, when the orders come
from the chain and when the committee takes them from the pool at a cutoff?
And how many rounds fit once the network is counted?

**Clauses exercised.**

- NP-12 (`docs/spec/01-nonce-pool.md`): orders and settlements are type 2
  transactions, and the committee's settlements wait in nonce order.
- BB-1 to BB-5 (`docs/spec/03-block-building.md`): the builder takes
  candidates by tip; from the pool, every builder leaves the orders out,
  as `ChainConfig.censored` does for experiment 09's filtering builders.
- FEE-1 and FEE-2 (`docs/spec/00-model.md`).

No clause changes. The committee is the simulator's `Clearing`, and
decision record 0029 has the readings. The requirement, its budget and the
round counts of its protocols are the MPC study's.

## Setup

- **Network and chain**: 20 nodes, 8 peers each, a hop of 20 to 100 ms, a
  block every 12, 8 or 4 s from a proposer in turn among the 17 nodes that
  are not the committee's, gas limit 60,000,000 at every slot time.
  Transfers of 1,000,000 gas fill the gas target beside the orders and one
  settlement a block. A node imports a block 0.1 to 1.0 s after it is built,
  whatever the slot time (decision record 0029).
- **Orders**: 0.5 a second, 100,000 gas each, from accounts of the users'
  own, at a tip of 3 gwei and a fee cap of 100 times the next base fee, to
  random nodes, until second 1080.
- **The committee**: three members, nodes n17 to n19. A batch takes the
  rounds in the table at a round trip of 80 ms between them, and starts
  only when the last batch has ended, since it clears the book the last one
  left. Its settlement, 1,125,950 gas, a proof the chain checks as in
  Merces, is sent by n17 from an account at a tip of 2 gwei, for every
  batch, empty or not.
- **Orders from the chain** (section 1): batch $b$ is the orders block
  $b - 1$ carried, and starts once all three members have imported it; its
  settlement is meant for block $b$.
- **Orders from the pool** (sections 3 and 4): orders travel the network as
  transactions and no builder includes them. Batch $b$ is the orders all
  three members have held since before its cutoff, the rounds and a margin
  of 1 s (or the margin in section 4) before block $b$ is due.
- **Round counts**, the MPC study's: 2 (a garbled tournament), 17 (PRAC's heap
  insert, for an order book), 49 (a tree tournament over secret shares), 63
  (with a collaborative proof the chain checks), 150 (the 12-second budget
  itself) and 4,096 (a running maximum).
- Seed 1, 1200 s a run; rows are the batches meant for a block from second
  120 to second 1080, and the orders sent in that time.

## Run

```
python3 experiments/20-per-block-clearing/run.py > experiments/20-per-block-clearing/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

**Orders from the chain** (section 1), at 80 ms; in time is the percentage
of batches settled in the block they were meant for, late the most blocks
after it, and delays are seconds from sending an order to the block that
settled it:

| slot, s | rounds | rounds, s | in time | late, blocks | unsettled | delay p50 | p90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 12 | 2 to 63 | 0.16 to 5.04 | 100.00 | 0 | 0 | 18.01 | 22.61 |
| 12 | 150 | 12.00 | 0.00 | 1 | 0 | 30.01 | 34.61 |
| 8 | 2 to 63 | 0.16 to 5.04 | 100.00 | 0 | 0 | 11.94 | 15.40 |
| 8 | 150 | 12.00 | 0.00 | 50 | 146 | 249.97 | 381.54 |
| 4 | 2 or 17 | 0.16 or 1.36 | 100.00 | 0 | 0 | 6.05 | 7.75 |
| 4 | 49 | 3.92 | 0.00 | 1 | 0 | 10.05 | 11.75 |
| 4 | 63 | 5.04 | 0.00 | 62 | 66 | 149.32 | 236.45 |
| 4 | 150 | 12.00 | 0.00 | 199 | 327 | 529.29 | 736.33 |

At 4,096 rounds no batch due in the window was settled, and none of the 457
orders sent in it. The orders included in the first block after they were
sent were 98.25, 96.72 and 95.84 percent at 12, 8 and 4 s.

**The network on either side** (section 2), in seconds; before is, from the
chain, a block to the last member's import of it, and from the pool, an
order's sending to the last member's holding it; after is a settlement's
sending to its arrival at the proposer it was meant for. Rounds that fit
would have left 99 percent of the batches from the chain in time; the slot
alone is the MPC study's budget:

| orders | slot, s | before p50 | p99 | after p50 | p99 | fit, 5 ms | 80 ms | 250 ms | slot alone, 5 ms | 80 ms | 250 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chain | 12 | 0.84 | 1.00 | 0.13 | 0.32 | 2149 | 134 | 42 | 2400 | 150 | 48 |
| chain | 8 | 0.83 | 1.00 | 0.13 | 0.32 | 1349 | 84 | 26 | 1600 | 100 | 32 |
| chain | 4 | 0.83 | 0.99 | 0.13 | 0.32 | 549 | 34 | 10 | 800 | 50 | 16 |
| pool | 12, 8 or 4 | 0.18 | 0.75 | 0.13 | 0.32 | | | | | | |

**Orders from the pool** (section 3), at 80 ms with a margin of 1 s; own
batch is the percentage of orders in the first batch cut after they were
sent:

| slot, s | rounds | in time | late, blocks | own batch | unsettled | delay p50 | p90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 12 | 2 | 100.00 | 0 | 97.37 | 0 | 7.30 | 12.26 |
| 12 | 49 | 100.00 | 0 | 98.25 | 0 | 11.29 | 16.03 |
| 12 | 150 | 100.00 | 0 | 99.12 | 0 | 19.07 | 24.06 |
| 8 | 63 | 100.00 | 0 | 97.16 | 0 | 10.18 | 13.32 |
| 8 | 150 | 0.00 | 49 | 97.81 | 150 | 249.41 | 374.17 |
| 4 | 2 | 100.00 | 0 | 91.90 | 0 | 3.51 | 5.08 |
| 4 | 17 | 100.00 | 0 | 96.06 | 0 | 4.57 | 6.15 |
| 4 | 49 | 100.00 | 0 | 95.19 | 0 | 7.19 | 8.72 |
| 4 | 63 | 0.00 | 62 | 93.87 | 67 | 148.47 | 235.07 |

**The pool's margin** (section 4), at 17 rounds: with a margin of 0.25 s,
82.50, 81.67 and 82.50 percent of the batches were in time at 12, 8 and
4 s, and the rest one block late; with 0.5 s, 1 s or 2 s, all of them.

## What it shows

1. **From the chain, the network takes about a second of every slot, and
   the budget shrinks by it.**
   - A batch cannot start until the last of three members has imported the
     block that carries its orders, 0.84 s at the median and 1.00 s at the
     99th percentile under the simulator's import delay, and its settlement
     then needs 0.13 s at the median and 0.32 s at the 99th percentile to
     reach the proposer.
   - At 80 ms, 134 rounds would have kept 99 percent of the batches in time
     at 12 s, against the MPC study's 150; 84 at 8 s, against 100; and 34 at
     4 s, against 50. The rounds lost are the same, 16, at every slot time,
     so they are a larger share of a shorter slot.
2. **The protocols that fit a 4-second budget do not all fit a 4-second
   slot.**
   - At 12 s every count up to 63 was in time. At 8 s, so was 63.
   - At 4 s, 17 rounds were in time and 49, which the MPC study's budget of 50
     admits, settled every batch one block late: 3.92 s of rounds after an
     import of up to a second.
3. **A committee whose rounds exceed the slot falls behind without
   bound.** It cannot run two batches at once, so each starts later than
   the last: at 4 s, 63 rounds left batches up to 62 blocks late by the end
   and 66 orders unsettled; at 8 s, 150 rounds left them 50 blocks late. A
   count that only just exceeds what is left of the slot, 150 at 12 s or 49
   at 4 s, stays one block late and keeps up.
4. **From the pool, the committee gets the MPC study's whole budget, and the
   users pay for it in waiting.**
   - With the cutoff moved earlier by the rounds, the computation no longer
     waits for a block: every count up to the slot was in time, 150 rounds
     at 12 s and 49 at 4 s.
   - The cost is the cutoff: the median delay from sending an order to its
     settlement rose with the rounds, from 7.30 s at 2 rounds to 19.07 s at
     150 at 12 s, and from 3.51 s to 7.19 s at 49 at 4 s.
   - At every count that fit, the pool was the faster channel, since an
     order does not wait for a block of its own: at 2 rounds, 7.30 s
     against 18.01 s at 12 s and 3.51 s against 6.05 s at 4 s; at 49
     rounds, 11.29 s against 18.01 s at 12 s.
5. **An order misses its batch when it reaches the third member after the
   cutoff, and the next batch takes it.**
   - An order took 0.18 s at the median and 0.75 s at the 99th percentile to
     reach all three members. At 12 s between 97.37 and 99.12 percent of
     orders made their own batch, and at 4 s between 91.90 and 96.06, as
     the same delay is a larger share of the slot; how many miss in a run
     depends on how many happen to be sent just before a cutoff.
   - No order was lost: every row whose rounds fit has none unsettled.
6. **The margin has to cover the settlement's way to the proposer.** With
   0.25 s, between a sixth and a fifth of the batches were a block late at
   every slot time; with 0.5 s, which is above the 0.32 s 99th percentile,
   none was.

**Answer to the question.** From the chain a committee that clears every
block has the slot less about a second: at 80 ms, 134 rounds at 12 s and 34
at 4 s rather than the MPC study's 150 and 50, so the tree tournament's 49
rounds fit 12 and 8 s and settle a block late at 4 s, PRAC's 17 fit
everywhere, and a collaborative proof's 63 does not fit 4 s at all. From the
pool at a cutoff, the whole budget is usable, at the price of a cutoff that
many rounds ahead of the block, which is what users wait for, and it was still
the faster channel at every count that fit.

## What it does not show

- **A real network's import delay.** The second that section 2 measures is
  the simulator's 0.1 to 1.0 s for a node to import a block, the same at
  every slot time; a shorter slot with smaller blocks may import faster,
  and a real network has tails this one does not.
- **Bytes.** The MPC study's budget counts rounds, and so does this; at a
  bandwidth limit a garbled protocol's megabytes would lengthen its two
  rounds.
- **The round to agree on a batch from the pool**, which would add one
  round trip, and what the contract checks that batch against.
- **An abort or a slow member.** Any one member can stop the computation; here
  each round takes exactly its round trip.
- **What the committee and the network learn from the orders.** Orders
  from the pool are visible to every node while they wait for a cutoff,
  which is what experiment 12 measures for spends; how they are encrypted
  to the members is the MPC study's question.
- **A proposer that delays its block or leaves the settlement out.**
