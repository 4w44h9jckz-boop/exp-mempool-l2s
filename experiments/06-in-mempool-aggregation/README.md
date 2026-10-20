# 06. In-mempool aggregation

**Question.** How long does a transaction with an EIP-8288 dependency take to
reach a builder and a block, and how many such transactions do the network's
aggregates carry? Three cases: the wrapper limits bind aggregates, they do
not, and users' wrappers are relayed at once.

**Clauses exercised.**

- AG-2 to AG-4: a dependency frame, its place outside the prefix, and the
  per-transaction limits.
- AG-5 and AG-6: a wrapper's checks, and admission once its proofs verify.
- AG-7: the aggregate, its order, and the two readings kept as
  `cap_aggregates` and `forward_wrappers` (decision record 0012).
- AG-8: the block's charge for declared dependencies.
- BB-3: a builder's gas check, with AG-8's charge.

EIP-8288 (Draft, read at `258836f9`) lets a frame transaction declare a
leanSTARK proof or a leanSPHINCS signature as a dependency. The proof travels
beside the transaction in a wrapper, and every mempool node sends its peers
one aggregate every `AGGREGATION_INTERVAL` of 1000 ms, with one recursive
STARK over what it holds.

The text caps a wrapper at `MAX_LEANSTARK_DEPS_PER_WRAPPER` = 1 and
`MAX_LEANSIG_DEPS_PER_WRAPPER` = 16, and lists those caps among the checks
of a mode 1 wrapper, which is what an aggregate is. It also says a node's
aggregate contains "all currently active transactions" (Mempool Wrapper
Object). Once a node holds two transactions with a leanSTARK dependency each,
both cannot hold. Read literally, the cap allows one distinct dependency
per 1,000 ms tick, so about 12 a slot. A third reading has transactions
still gossiped individually: the text sends only aggregates, and that
reading needs a node to relay users' wrappers at once. This experiment runs
all three.

## Setup

- **Network** (decision record 0013):
  - 30 nodes with 8 peers each, plus 100-node rows for gossip and the
    uncapped reading;
  - a block every 12 s from a rotating proposer;
  - gas limit 6,300,000, so that a block holds 47 of the leanSTARK
    transactions and 58 of the leanSPHINCS ones, above any demand here;
  - a builder's minimum tip of 1,000,000 wei.
- **Pools.**
  - `eip-8288`, the text's reading: the cap binds aggregates.
  - `eip-8288, uncapped`: `cap_aggregates` false.
  - `eip-8288, forwarded`: `forward_wrappers` true, cap kept.
  - `gossip, no dependency`: `eip-8141` with the same transactions without
    the dependency frame, gossiped as usual.
- **Wallets.**
  - Each is its own default-code sender, sending to a random node for 25
    minutes of a 30-minute run.
  - A transaction is `[dependency, self_verify, sender]` with one triple of
    its own, sent as a mode 0 wrapper with its proof.
  - A wallet with one in flight waits. After every block that leaves the
    transaction out, it sends it again to a random node. Section 3 instead
    sends once and waits.
- **Aggregation.** Every node aggregates once a second at a phase of its own
  and sends the aggregate to every peer. Section 1 also runs a proving delay
  of a full interval, the most a node that aggregates every interval can
  take; otherwise the delay is 0.
- **What is counted.**
  - *Reached*: when a transaction became pending at half the nodes, and at
    all of them.
  - *Route*: how the block's proposer first admitted each transaction it
    included: from a user's wrapper sent to it, from a peer's aggregate, from
    a forwarded wrapper, or by ordinary gossip.
  - *Carried*: the distinct transactions listed in any node's aggregate
    during a slot, averaged over the slots of the demand.
  - *What nodes send*: wrappers, recursive STARKs, direct proofs and bytes,
    per node and per second.
- Seed 1. 22 runs take about five minutes.

## Run

```
python3 experiments/06-in-mempool-aggregation/run.py > experiments/06-in-mempool-aggregation/results.md
```

## Results

From [results.md](results.md).

**Section 1, at 2 transactions a slot**, a subset of the columns. Delays are
in seconds, from first sending.

| network | reached half | p50 | reached all | p50 | delay p50 | p90 | user | aggregate | forwarded | carried |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gossip, no dependency | 223 | 0.14 | 219 | 0.29 | 6.67 | 10.87 | 0 | 0 | 0 | n/a |
| eip-8288 | 195 | 14.55 | 145 | 15.09 | 25.96 | 46.71 | 44 | 179 | 0 | 3.14 |
| eip-8288, proving 1 s | 206 | 6.08 | 138 | 7.89 | 16.02 | 27.78 | 26 | 197 | 0 | 3.62 |
| eip-8288, uncapped | 223 | 0.66 | 221 | 1.02 | 6.79 | 11.16 | 7 | 216 | 0 | 3.58 |
| eip-8288, uncapped, proving 1 s | 213 | 2.67 | 209 | 3.45 | 8.06 | 12.99 | 11 | 212 | 0 | 3.79 |
| eip-8288, forwarded | 223 | 0.08 | 223 | 0.12 | 6.64 | 10.71 | 6 | 0 | 217 | 1.64 |
| gossip, no dependency, 100 nodes | 223 | 0.20 | 216 | 0.78 | 6.68 | 10.91 | 0 | 0 | 0 | n/a |
| eip-8288, uncapped, 100 nodes | 223 | 0.95 | 221 | 1.40 | 6.98 | 11.64 | 5 | 218 | 0 | 3.62 |

All 223 transactions landed in every row.

**Section 2, against demand.** Spread is the mean number of the 30 nodes a
transaction became pending at.

| network | dependency | a slot | landed | delay p50 | p90 | spread | user | aggregate | forwarded | carried |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8288 | stark | 8 | 956 | 45.07 | 88.32 | 14.47 | 674 | 282 | 0 | 5.90 |
| eip-8288, uncapped | stark | 8 | 952 | 6.61 | 11.35 | 29.96 | 37 | 915 | 0 | 15.30 |
| eip-8288, forwarded | stark | 8 | 952 | 6.04 | 10.92 | 30.00 | 31 | 0 | 921 | 2.15 |
| eip-8288 | stark | 32 | 3819 | 54.21 | 102.63 | 9.25 | 3501 | 318 | 0 | 6.22 |
| eip-8288, uncapped | stark | 32 | 3881 | 6.65 | 11.43 | 29.95 | 132 | 3749 | 0 | 62.46 |
| eip-8288, forwarded | stark | 32 | 3890 | 6.04 | 10.87 | 30.00 | 118 | 0 | 3772 | 2.52 |
| eip-8288 | sphincs | 32 | 3871 | 27.76 | 46.38 | 24.40 | 994 | 2877 | 0 | 54.52 |
| eip-8288, uncapped | sphincs | 32 | 3881 | 6.65 | 11.43 | 29.95 | 134 | 3747 | 0 | 62.46 |

Every transaction sent landed in every row.

**Section 3, wallets that send once**, leanSTARK at 8 a slot.

| network | sent | landed | delay p50 | p90 | spread |
| --- | --- | --- | --- | --- | --- |
| eip-8288 | 948 | 948 | 99.38 | 283.00 | 10.53 |
| eip-8288, uncapped | 952 | 952 | 6.63 | 11.36 | 29.96 |
| eip-8288, forwarded | 952 | 952 | 6.04 | 10.91 | 30.00 |

**Section 4, what nodes send each other**, per node and per second, a subset
of the columns. The last column prices each recursive STARK at the 128 kB
the EIP gives as the least a STARK takes, so it is a floor.

| network | dependency | a slot | STARKs | direct proofs | kB transactions | kB of STARKs, at least |
| --- | --- | --- | --- | --- | --- | --- |
| eip-8288 | stark | 8 | 8.31 | 0.00 | 0.24 | 1063.23 |
| eip-8288, uncapped | stark | 8 | 7.15 | 0.00 | 1.80 | 915.15 |
| eip-8288, forwarded | stark | 8 | 7.14 | 4.53 | 1.89 | 914.44 |
| eip-8288 | stark | 32 | 8.38 | 0.00 | 0.25 | 1072.98 |
| eip-8288, uncapped | stark | 32 | 7.85 | 0.00 | 7.35 | 1004.16 |
| eip-8288, forwarded | stark | 32 | 7.87 | 18.51 | 6.98 | 1007.73 |

## What it shows

- **Under the text's reading, aggregation is a queue, not a broadcast.**
  - An aggregate holds one leanSTARK transaction. The EIP's order lists the
    node's own previous aggregate first, so a node keeps sending the same
    transaction until a block includes it. Next come other nodes'
    aggregates, so after a block nodes take up what a peer chose.
  - Across the network, aggregates listed 3.14 distinct transactions a slot
    at 2 a slot, 5.90 at 8 and 6.22 at 32. That is under the about 12 a
    slot that a literal reading of the cap gives, one distinct dependency a
    tick. Nodes that copy each other carry fewer distinct transactions than
    one node rotating through its pool could.
  - Inclusion slows as demand rises, although gas never binds. The median
    delay is 25.96 s at 2 a slot, 45.07 at 8 and 54.21 at 32, against
    gossip's 6.67. At 2 a slot only 145 of 223 transactions ever became
    pending at every node. At 32, a transaction reached 9.25 of the 30
    nodes on average.
- **What lands under the cap mostly lands by the wallets' resend.**
  - At 32 a slot, the proposer had first admitted 3501 of the 3819 included
    transactions from a user's own wrapper sent to it, and 318 from an
    aggregate. At 8 a slot it was 674 and 282.
  - A wallet that resends to a random node after every missed block is a
    route of its own, which reaches the next proposer by chance.
  - Wallets that send once wait a median of 99.38 s, with a p90 of
    283.00 s. All 948 still landed within the run.
- **Without the cap, aggregation costs about an interval a hop to reach the
  nodes, and little in inclusion.**
  - The uncapped reading reached half the nodes in 0.66 s, against gossip's
    0.14, and all of them in 1.02 s, against 0.29.
  - Its median delay was 6.79 s against gossip's 6.67 at 2 a slot, and 6.65
    at 32 a slot. Inclusion waits for the next slot, and the 12-second slot
    hides a second or so of propagation.
  - At 100 nodes the delay was 6.98 s against gossip's 6.68. With a proving
    delay of a full interval at 30 nodes it was 8.06 s.
  - The aggregates carried 62.46 distinct transactions a slot at 32 a slot,
    against 6.22 under the cap.
- **A proving delay sped up the capped reading.**
  - With a full interval of proving, the median delay fell from 25.96 s to
    16.02 s. Carried rose from 3.14 to 3.62, and the aggregate route from
    179 to 197.
  - That is consistent with nodes choosing from their own pools before a
    peer's aggregate arrives, so fewer of them copy the first node to choose
    after a block. The model does not show the mechanism directly.
- **The signature cap binds less.**
  - With one leanSPHINCS dependency each, at 32 a slot, an aggregate holds
    16. The median delay was 27.76 s, and 2877 of 3871 transactions
    reached the proposer by an aggregate.
  - Without the cap, the same transactions waited a median of 6.65 s.
- **Forwarding users' wrappers matches gossip and sends every proof in the
  clear.**
  - Forwarded wrappers reached every node in a median of 0.12 s, against
    gossip's 0.29.
    A wrapper goes in full to every peer, where gossip pushes to a square
    root of them and announces to the rest.
  - The median delay was 6.04 s at 8 and 32 a slot.
  - At 32 a slot each node sent 18.51 direct proofs a second besides its
    7.87 recursive STARKs. Each direct proof is a STARK of its own.
  - This is the reading under which transactions are still gossiped
    individually. The text does not relay users' wrappers.
- **A node sends one recursive STARK per peer per interval, whatever the
  demand.**
  - Each node sent 7.14 to 8.38 recursive STARKs a second, the same at 8 a
    slot and at 32. At 128 kB each, that is at least 914.44 to 1072.98 kB a
    second.
  - The EIP says the overhead "is constant per peer, regardless of the
    number of transactions" (FOCIL Compatibility, Censorship Resistance),
    which the measurement agrees with. It also says that for the builder it is "a fixed ~256 kB
    per `AGGREGATION_INTERVAL`" (Rationale). A builder with peers like
    these nodes receives one STARK from each of them every interval, so the
    fixed figure is per peer, not per builder.

## What it does not show

- **Proving cost.** Proving takes a fixed delay. A real node's proving time
  grows with what it aggregates, and the EIP's order is for a node that
  cannot prove everything in time. A slow prover under the uncapped reading
  would behave in part like the capped one.
- **Bandwidth.** The model slows no message for its size. At 914.44 kB a
  second of STARKs per node or more, a link that cannot carry it would add
  delay to every reading, and to forwarding most of all.
- **Shared dependencies.** Every transaction has its own triple. Transactions
  that share one, for instance under one proof for a batch, fit more to an
  aggregate under the cap.
- **Adversaries.** No node lists junk, withholds an aggregate or sends a
  failing proof. The EIP's Denial of Service section and FOCIL extension are
  not modelled.
- **Privacy.** The experiment counts time and bytes, not who learns which
  node a wrapper came from first. Aggregation hides nothing about that.
- **Demand above capacity.** Gas never binds here. Above 47 leanSTARK
  transactions a slot, the queue the cap makes would add to the queue for
  block space.
