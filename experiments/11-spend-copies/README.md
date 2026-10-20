# 11. One spend, many copies

**Question.** When the holder of a spend hands it out as several copies to
different nodes, of which one can land, how many pools hold a copy that has
lost and for how long, and what do the copies cost the network, with the
spend's nullifier in a nonce key and in a storage slot, and with the pool's
static checks before the prefix?

**Clauses exercised.**

- FP-12: a pending frame transaction's identity, and the price bump a copy
  needs to replace the one a pool holds.
- FP-11 and FP-12 before FP-8 under `static_first` (Admission, version 5).
- FP-9: a prefix may read only `sender`'s storage.
- FP-15: what a pool removes and what it runs again at a new head.
- BB-3: what a builder tries and fails.

An earlier design study built a blind ticket that can be put into many
operations at once, of which one lands. It reads the copies as ERC-7562's
mass invalidation attack in its cheapest form, and proposes duplicate
suppression, one pending operation per paymaster and ticket. In the frame
pool the ticket is a spend from a shared sender, whose nullifier is either
an EIP-8250 nonce key or a slot of the sender's storage (decision record
0020).

## Setup

- **Network:** 50 nodes, 8 peers each, go-ethereum's gossip, a block every
  12 s from a proposer that rotates through every node, gas limit
  30,000,000, so that every spend fits in the next block. 480 s a run, and
  each row pools three runs, seeds 1 to 3.
- **Pools:** `hegota-testnet`, whose `disjoint-keys` lets a pool hold one
  spend per nullifier from the shared sender (decision record 0020). Under
  the nonce key, also with `static_first`.
- **Spends:** from 12 s to 420 s, users ask for spends from one shared
  sender at one a slot, each with a 1 gwei tip and a fee cap of twice the
  next base fee plus the tip. Each user hands the spend out at once as 1, 2,
  4 or 8 copies, or one to every node, each to a different random node, and
  never sends again. The copies differ only in their label.
- **Nullifier:**
  - *nonce*: the spend's nonce key, so that every copy has one identity;
  - *slot*: a slot of the shared sender's storage, which the prefix reads
    and approves only while it holds 0 and the execution sets to 1. Each
    copy has a nonce key of its own.

## Run

```
python3 experiments/11-spend-copies/run.py > experiments/11-spend-copies/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

Section 1, 50 nodes, selected columns. Every row pools three runs and 92
spends, all of which landed. Held after loss is in seconds, and delay is the
p50 from asking to the winning block, in seconds.

| nullifier | static first | copies | pools with a lost copy | held after loss p50 | max | runs per spend | refused per spend | re-runs of lost copies per spend | failed in block per spend | delay p50 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nonce | no | 1 | 0.00 | n/a | n/a | 50.00 | 0.00 | 0.00 | 0.00 | 5.95 |
| nonce | no | 2 | 22.21 | 0.54 | 1.00 | 119.80 | 70.15 | 0.00 | 0.00 | 5.95 |
| nonce | no | 8 | 41.99 | 0.54 | 1.00 | 285.99 | 238.77 | 0.00 | 0.00 | 5.80 |
| nonce | no | every node | 49.00 | 0.54 | 1.00 | 533.97 | 490.50 | 0.00 | 0.00 | 5.76 |
| nonce | yes | 8 | 41.99 | 0.54 | 1.00 | 49.99 | 238.77 | 0.00 | 0.00 | 5.80 |
| nonce | yes | every node | 49.00 | 0.54 | 1.00 | 50.00 | 490.50 | 0.00 | 0.00 | 5.76 |
| slot | no | 2 | 50.00 | 0.53 | 1.00 | 100.03 | 0.03 | 50.00 | 1.00 | 5.95 |
| slot | no | 8 | 49.99 | 0.53 | 1.00 | 400.26 | 0.43 | 349.85 | 6.93 | 5.80 |
| slot | no | every node | 49.99 | 0.53 | 1.00 | 2510.96 | 14.91 | 2446.25 | 48.08 | 5.76 |

Section 2, one copy for every node, per spend and node.

| nullifier | static first | nodes | runs | re-runs of lost copies | failed in block per spend |
| --- | --- | --- | --- | --- | --- |
| nonce | no | 25 | 10.50 | 0.00 | 0.00 |
| nonce | no | 200 | 10.88 | 0.00 | 0.00 |
| nonce | yes | 25 | 1.00 | 0.00 | 0.00 |
| nonce | yes | 200 | 1.00 | 0.00 | 0.00 |
| slot | no | 25 | 25.14 | 23.96 | 23.48 |
| slot | no | 50 | 50.22 | 48.92 | 48.08 |
| slot | no | 100 | 100.52 | 98.72 | 95.63 |
| slot | no | 200 | 201.11 | 198.51 | 194.59 |

The other rows and columns are in `results.md`.

## What it shows

- **Under a nonce key the pool merges the copies, as EIP-8141 says it
  should.** Every copy has the spend's identity, so a pool keeps the first
  it receives and refuses the others (FP-12, `ErrReplaceUnderpriced`). The
  network splits into one region per copy. With 8 copies, 41.99 of 50 pools
  hold a copy that loses, and with one copy for every node, 49.00.

  They hold it only until the winning block arrives, p50 0.54 s and at most
  1.00 s, which is the model's import delay. A pool then drops the lost
  copy at FP-15 step 1, because the spend's key has moved on, and runs
  nothing: re-runs of lost copies are 0 in every nonce row, and no builder
  fails one.
- **What the merge still costs is the refusals, because they come after
  the prefix.** Runs per spend rise from 50.00 with one copy to 285.99
  with eight and 533.97 with one copy for every node. Each pool runs the
  prefix of every copy its peers relay before FP-12 refuses it. Per node
  that is 10.50 runs per spend at 25 nodes and 10.88 at 200, which is about
  the number of peers a node has.
- **Checking FP-12 before the prefix makes the copies free.** Under
  `static_first`, runs per spend stay at the 50 a single copy costs, 49.99
  with 8 copies and 50.00 with one for every node, and section 2's runs
  per spend per node are 1.00 at every size. The refusals are the same,
  238.77 per spend with 8 copies, but no prefix stands behind them. Which
  copies pools hold, which lands and when are the same as under the EIP's
  order. This is the study's duplicate suppression, and the frame pool gets it
  by moving one comparison ahead of the simulation.
- **Under a storage slot, one spend invalidates every copy in every
  pool.** Each copy has an identity of its own, so every pool holds all of
  them, and 49.99 of 50 pools hold a copy that loses with 8 copies. The
  copy that lands writes the slot, which every other copy's prefix reads.
  So every pool re-runs every other copy at the next head (FP-15 step 3)
  and finds that it fails: 349.85 re-runs per spend with 8 copies. The
  builder of the winning block also tries and fails 6.93 of them (BB-3).

  With one copy for every node, the work grows as the square of the
  network. Runs per spend per node are 201.11 and re-runs 198.51 at 200
  nodes, against 25.14 and 23.96 at 25. The holder pays for one spend.
  This is the mass invalidation the study describes, in its cheapest form. The
  copies are distinct transactions and only the one that lands pays, which
  is the shape of ethresear.ch topic 25995's case 1, a rule that charges
  nothing per attempt.
- **It is not experiment 03's cost, and balance reuse does not remove it.**
  Experiment 03 needed transactions held at a fee cap no builder accepts
  and a separate touch, and `reuse_balance` removed every re-run it caused
  (`experiments/03-revalidation-cost/results.md`, section 1). Here the
  spend that lands is the touch. The dependency it changes is a storage
  slot, and FP-15 step 3 reuses a result only when every dependency that
  changed is a balance.
- **Copies buy the holder nothing in this model.** Delay p50 is between
  5.76 and 5.95 s in every row. One copy alone reaches every pool (pools
  reached is 50.00 in `results.md`), and every block takes whichever copy
  its builder holds.

## What it does not show

- **Copies at different fees.** A copy that pays the 10% bump replaces
  the others as it spreads. That is a fee race, and it costs a run at
  every pool it replaces in.
- **Congestion, and holders that resend.** Every block here has room, so
  every spend lands in the next block or the one after.
- **How many copies a slot nullifier allows.** `disjoint-keys` lets a pool
  hold as many copies as `max_pending`, 4096. The largest number measured
  is one per node.
- **The study's own case, copies from different senders.** A prefix cannot
  read a ticket's spent record outside `sender` (FP-9), so the frame pool
  cannot express it. Nor does the model have ERC-7562's reputation, which
  is what throttles a paymaster there.
- **The `eip-8141` profile.** It allows one pending transaction per
  sender, so every copy and every other spend from the shared sender
  compete for one place in each pool, which is experiment 01's ceiling.
- **$w$.** As in experiment 10, a run is counted and not timed.
