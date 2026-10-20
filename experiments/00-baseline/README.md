# 00. Baseline

**Question.** Does the base behave like a mempool? Below the gas target a
transaction should reach every node in well under a second and be included in
the next block or the one after. In a burst above the block limit there should
be a backlog and a base fee rising by up to 12.5 percent a block, and both
should unwind afterwards. If the base gets these wrong, no later experiment
built on it can be trusted.

**Clauses exercised.** FEE-1 and FEE-2; NP-2 to NP-5, NP-11, NP-14, NP-19 and
NP-20; FP-7, FP-8, FP-11, FP-12, FP-15 and FP-16; BB-1 to BB-5. Gossip follows
the devp2p `eth` protocol as `sim/emem_sim/network.py` describes. It is not
specified in `docs/spec/`.

## Setup

- 30 nodes, each dialling random peers until it has 8 (inbound links count, so
  some have more), with one-way link latency uniform in 20 to 100 ms. A node
  pushes a transaction it has just accepted to a fixed $\lceil\sqrt{n}\rceil$
  of its $n$ peers, chosen per sender, and announces it to the rest; announced
  hashes are fetched after 500 ms, and a transaction a node refused is fetched
  again when another peer announces it, as go-ethereum's fetcher does
  (decision record 0004). A block reaches the other nodes 0.1 to 1.0 s after
  its proposer.
- One block every 12 s, proposed in turn by every node from its own pool with
  the go-ethereum miner's ordering and minimum tip (0.001 gwei). Gas limit
  2,100,000, which is 100 plain transfers; the target is half that. The genesis
  base fee is 1 gwei.
- Pools: `geth` for the account-nonce pool, `eip-8141` for frame transactions.
- Load, 400 funded transfer senders and a disjoint 100 frame senders:
  - 2.5 transfers a second for the first 600 s, 60 percent of the target;
  - 12 a second from 600 s to 900 s, 2.9 times the target and 1.4 times the
    block limit;
  - 2.5 a second again until 1800 s;
  - throughout, 0.2 self-paying frame transactions a second,
    `[self_verify, sender]` with default code. A frame wallet waits for its
    transaction to be included before sending another (FP-12).
- Wallets: tip uniform between 0.001 and 3 gwei, fee cap twice the next base
  fee plus the tip, next nonce one past their last. They never bump a stuck
  transaction.
- Seed 1, 1800 simulated seconds, about 35 s of wall clock.

## Run

```
python3 experiments/00-baseline/run.py > experiments/00-baseline/results.md
```

## Results

From [results.md](results.md):

| phase | seconds | submitted | included | delay p50 | delay p90 | delay p99 | block fullness | base fee | pool | pool at end |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| quiet | 0-600 | 1651 | 1651 | 6.06 | 11.01 | 12.07 | 0.40 | 0.29 | 33.01 | 32.97 |
| burst | 600-900 | 3737 | 2836 | 8.69 | 677.63 | 1024.80 | 1.00 | 5.43 | 826.35 | 1535.30 |
| after | 900-1800 | 2502 | 1940 | 6.83 | 100.47 | 614.89 | 0.43 | 1.24 | 1627.35 | 1493.60 |

Propagation: half the nodes hold a new transaction after 0.14 s (median), all
of them after 0.30 s (median) and 0.83 s (p99).

At the end, node n00 holds 1,494 pending transactions at a next base fee of
1.24 gwei. 123 have a fee cap below it, 1,340 sit behind one of those in their
sender's nonce order, 31 are includable, and 102 of the 400 transfer senders
are stuck.

## What it shows

- **Below the target the base behaves as expected.** Every transaction
  submitted in the quiet phase was included, at p99 within 12.07 s, so in the
  next block or, for one submitted too close to a slot to reach its proposer,
  the one after. The base fee fell from 1 gwei to 0.29 because blocks were 40
  percent full, under the 50 percent target. Every node pushes to at least
  three peers ($\lceil\sqrt{8}\rceil$), and the median transaction is
  everywhere in 0.30 s; the p99 of 0.83 s is above the 500 ms a node reached
  only by announcements waits before it fetches.
- **The burst does what EIP-1559 says it should.** Blocks are full for the
  whole burst (a mean fullness of 1.00, to two places) and the base fee climbs
  from 0.29 to 5.43 gwei in 25 blocks, a factor of 18.7 against the
  $1.125^{25} \approx 19$ ceiling of full blocks. The median transaction is
  still included within a block, because a wallet that prices at twice the
  base fee outbids the backlog.
- **The backlog does not unwind, and the reason is the wallets, not the
  pool.** A transaction priced at twice a base fee that then rises eighteenfold
  is stranded. Under NP-13 every later nonce of its sender waits behind it, so
  102 senders, a quarter of them, are stuck at the end, and a sender's new
  transfers join the queue behind the stranded one. With most of the pool
  unincludable, blocks are 43 percent full after the burst and the base fee
  settles near 1.2 gwei rather than returning to 0.3. In go-ethereum's pool nothing expires
  a *pending* transaction: lifetime eviction (NP-18) applies to the queue only.
  Such a transaction leaves when its fee cap clears again or when a full pool
  evicts it (NP-9). This is the "stuck nonce" every wallet's speed-up button
  exists for, and an experiment that wants the backlog to clear has to model
  fee bumping.
- **Frame transactions ride along unaffected.** Their senders are separate and
  send one at a time, so they see the quiet-phase delays throughout (median
  6 s, p90 11 s).

## What it does not show

- Wallets that bump fees, cancel, or stop sending when the price rises. Demand
  here is inelastic, which is what strands the backlog. Experiment 15 adds
  bumping and users who stop.
- Bandwidth, message sizes and the fetcher's batching and peer scoring; a
  network of 30 nodes rather than thousands; one region's latency.
- Private order flow. Every transaction here is public; on mainnet a share of
  the volume goes privately to builders, and how much is not measured here.
- A full pool: 5,120 + 1,024 slots per node were never reached, so the eviction
  rules of NP-9 and NP-16 did not act. The conformance vectors cover them.
