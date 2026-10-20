# 16. Batched admission

**Question.** Verified one at a time, a pairing proof costs about 0.6 ms;
verified in a batch of proofs under one key, the cost a proof falls by up to
59 times (Commonware's blog post on batching Pari proofs). A mempool node
decides one transaction at a time. If a node holds proof-carrying
transactions for a window and verifies them as one batch, how large are the
batches it forms, what does it save, and what delay does the window add to
propagation and inclusion, against the window and the rate of proofs under
the key? What does a sender of invalid proofs, each of which fails the batch
it lands in, cost a node that batches?

**Clauses exercised.**

- FP-2 to FP-12 (`docs/spec/02-frame-pool.md`): a node admits a frame
  transaction by its hash, its static validity and its validation prefix,
  all unchanged here, and holds one pending transaction a sender; the proof
  is verified before the pool sees the transaction.
- BB-1 to BB-5 (`docs/spec/03-block-building.md`): a proposer includes what
  its own pool holds.

No clause changes. A node that batches is the simulator's, with decision
record 0025 for the choices; no source read here specifies one. EIP-8288's
dependencies are the model's other proofs declared beside a transaction
(experiment 06).

## Setup

- 50 nodes, 8 peers each, links of 20 to 100 ms one way, go-ethereum's
  gossip with a 500 ms arrive timeout, a block every 12 s from a proposer
  that rotates through the nodes, a gas limit with room for every proof,
  profile `eip-8141`.
- From 12 s to 96 s users send self-paying frame transactions, each from a
  sender of its own, to random nodes, at 1, 10 or 100 a second. Each carries
  a valid proof under one key shared by all of them.
- A node verifies a proof before its pool sees the transaction, on one core,
  and the time delays the admission. With a window of 0 it verifies each on
  arrival. Otherwise the first proof it holds opens a batch, which closes
  0.05 to 1 s later and is verified as one. A node relays a transaction only
  once its pool admits it, so each hop pays its own window.
- A proof alone costs 0.5845 ms, Commonware's individual rate at 65,536
  proofs; a batch costs what Commonware measured for Pari proofs on one
  thread at 2, 32, 512, 8,192 and 65,536 proofs, interpolated on a log-log
  line between them (`sim/emem_sim/batch.py`).
- Section 3 adds a sender of invalid proofs at 100 proofs a second: each
  invalid proof, from a fresh sender, is handed to every node at once. A
  node verifies it, refuses it and never relays it; in a batch it fails the
  batch, which the node bisects down to the proofs that fail.
- Seeds 1 to 3; every row pools the three runs, each 120 simulated seconds.

## Run

```
python3 experiments/16-batched-admission/run.py > experiments/16-batched-admission/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

Section 1, at each rate of proofs under the key: the mean batch a node
verified, verification in microseconds a proof and as a share of verifying
each alone, the time until 45 of the 50 nodes hold a transaction, and the
delay until a block includes it, in seconds, at the median:

| rate a second | window (s) | batch | verification | share | reach p50 | delay p50 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 1.00 | 584.5 | 1.00 | 0.25 | 5.88 |
| 1 | 0.10 | 1.11 | 554.0 | 0.95 | 0.76 | 6.30 |
| 1 | 1.00 | 2.08 | 395.4 | 0.68 | 3.41 | 8.67 |
| 10 | 0 | 1.00 | 584.5 | 1.00 | 0.25 | 6.20 |
| 10 | 0.10 | 1.98 | 406.5 | 0.70 | 0.67 | 6.52 |
| 10 | 0.50 | 5.46 | 212.9 | 0.36 | 1.83 | 7.48 |
| 10 | 1.00 | 10.33 | 137.2 | 0.23 | 2.72 | 8.09 |
| 100 | 0 | 1.00 | 584.5 | 1.00 | 0.25 | 6.26 |
| 100 | 0.05 | 5.84 | 203.8 | 0.35 | 0.42 | 6.38 |
| 100 | 0.10 | 10.63 | 134.8 | 0.23 | 0.58 | 6.48 |
| 100 | 1.00 | 94.54 | 39.5 | 0.07 | 2.64 | 8.01 |

At 100 a second a node that verifies each proof alone spends 56.54 ms of
verification a second; with a 0.10 s window, 13.03.

Section 2, the same shares applied to the 181,000 gas of the pairing check
in a one-nullifier spend of 211,828, as if gas scaled with time (decision
record 0025): the spend comes within `MAX_VERIFY_GAS`, 100,000, at 10 a
second with a 0.50 s window (96,751) and at 100 a second with 0.05 s
(93,926). The smallest batch that does it is 6 proofs, and a node collects
6 proofs under one key in:

| proofs under the key | window for a batch of 6 |
| --- | --- |
| 8.96 an hour, the busiest quarter of the four Tornado Cash ETH pools, merged | 40 minutes |
| 1 a second | 6.00 s |
| 10 a second | 0.60 s |
| 100 a second | 0.06 s |

Section 3, at 100 proofs a second with invalid proofs handed to every node:
checks are batch verifications a batch, and verification is per valid proof
with the invalid ones' cost included, and its share against no attack and
no window:

| window (s) | invalid a second | batch | checks | verification | share | reach p50 | delay p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 1.00 | 1.00 | 584.5 | 1.00 | 0.25 | 6.26 |
| 0 | 1 | 1.00 | 1.00 | 590.0 | 1.01 | 0.25 | 6.26 |
| 0 | 10 | 1.00 | 1.00 | 646.7 | 1.11 | 0.25 | 6.26 |
| 0 | 50 | 1.00 | 1.00 | 883.0 | 1.51 | 0.25 | 6.26 |
| 0.10 | 0 | 10.63 | 1.00 | 134.8 | 0.23 | 0.58 | 6.48 |
| 0.10 | 1 | 10.77 | 1.70 | 194.2 | 0.33 | 0.59 | 6.49 |
| 0.10 | 10 | 11.86 | 7.51 | 673.7 | 1.15 | 0.61 | 6.51 |
| 0.10 | 50 | 15.70 | 21.17 | 1785.0 | 3.05 | 0.65 | 6.54 |

## What it shows

- **A window saves in proportion to the proofs it catches, and every hop
  pays for it.** A node's batch is about the rate under the key times the
  window, plus the proof that opened it: 10.63 at 100 a second and 0.10 s,
  1.11 at 1 a second and the same window. What the batch saves follows
  Commonware's curve, down to 0.07 of verifying each alone at 94.54 proofs.
  Because a node relays only what it has admitted, each hop holds a
  transaction for up to the window: at 1 a second, where nearly every proof
  opens a batch of its own, a 1 s window takes the time to reach 45 nodes
  from 0.25 s to 3.41 s. At 100 a second, where most proofs join a batch
  already open, the same window takes it to 2.64 s.
- **The delay to a block grows by less than the delay to the network.** A
  block comes every 12 s, so a transaction that reaches the proposer later
  waits for the next slot only if it missed the one it would have made: at
  100 a second a 1 s window moves the median from 6.26 s to 8.01 s, and a
  0.10 s window from 6.26 s to 6.48 s.
- **The time saved is small; the price it could justify is not.** Verifying
  every proof alone at 100 a second takes 56.54 ms a second of one core.
  What batching changes is what a proof costs relative to its batch, and
  read as gas it brings a one-nullifier spend under `MAX_VERIFY_GAS` from a
  batch of 6. At 100 proofs a second under one key that is a 0.06 s window;
  at the busiest a privacy pool has been, 8.96 spends an hour, it is 40
  minutes. A batch needs traffic under one key, so the economy of batching
  is available to a key that many applications share, and not to one
  pool's spends at today's demand.
- **One invalid proof for every ten valid ones undoes the batch, and its
  sender pays nothing.** With a 0.10 s window at 100 a second, 1 invalid proof a
  second raises a node's verification from 0.23 to 0.33 of verifying alone,
  10 a second to 1.15, above the 1.11 the same attack costs a node that
  does not batch, and 50 a second to 3.05 against 1.51: each failed batch
  is bisected, at 21.17 checks a batch. The invalid proofs are never
  relayed and never admitted, so they cost their sender nothing but the
  sending. The one deployment of this economy bounds the cost by blocking
  a staked identity, which is what a public mempool lacks.
  Propagation and inclusion barely move: the attack costs a node's
  processor, not its users' time, at these rates.

## What it does not show

- A node read from a client. No client batches proof verification at
  admission; the window, the one core and the bisection are assumed
  (decision record 0025).
- Proofs under several keys. Proofs under different keys do not batch with
  each other, so every key in use divides the rate a batch is formed from.
- Gas. Section 2 carries Commonware's time ratio, measured for Pari over
  BLS12-381, across to the gas of a Groth16 pairing check over BN254, and
  no EIP prices a batch.
- A node that blocks the peer that sent an invalid proof, and a node that
  admits first and evicts on failure.
- Verification in parallel, which Commonware also measured, and hash-based
  proofs, whose batch economy is on the proving side.
