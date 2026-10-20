# 01. The one-pending-transaction ceiling

**Question.** How many spends an hour does a shared sender, such as a privacy
pool, land through the public mempool as its demand rises, under FP-12's `one`
and `disjoint-keys`, and what does the answer cost its users in delay and in
how long their nullifiers are public?

**Clauses exercised.** FP-7 (each nonce key at its exact sequence), FP-10 and
FP-11 (the sender pays for itself), FP-12 (one pending transaction per sender,
or disjoint key sets), FP-15 (revalidation when the sender's balance moves),
FP-16 and BB-2 (each frame transaction stands alone in the builder's order).
Gossip follows `sim/emem_sim/network.py`, which is go-ethereum's broadcast and
fetcher (decision record 0004) and is not specified in `docs/spec/`.

On the testnet on 2026-09-10 a client was measured refusing a second frame
transaction from one sender even on fresh disjoint keys, which leaves a pool
that is its own sender one spend per block network-wide, about 300 an hour.
An earlier analysis of shared senders argues that the ceiling makes
fragmenting an anonymity set pay, because $m$ pools get $m$ ceilings, and
names two numbers it does not have: what the ceiling costs at a realistic
demand and how long a queued spend's nullifier is exposed (its amendment on
exposure). This experiment measures the ceiling, the delay below it, the
exposure and the multiplier.

## Setup

- 20 nodes, each dialling random peers until it has 8, one-way link latency
  uniform in 20 to 100 ms, gossip as in experiment 00. A block reaches the
  other nodes 0.1 to 1.0 s after its proposer, which imports it at once.
- One block every 12 s (2 to 12 s in section 4), proposed in turn by every
  node. Gas limit 2,100,000, so a block holds 30 spends; genesis base fee
  1 gwei. There is no other traffic, so a block always has room for every
  spend its proposer holds.
- Pools: `geth`, and for frame transactions `eip-8141`, whose `per_sender` is
  `one`, against the same profile with `per_sender = disjoint-keys` and nothing
  else changed (decision record 0005).
- The shared sender is a contract holding $10^{24}$ wei. A spend is the
  voucher-pool spend of an earlier design study without its expiry frame: a
  `self_verify` frame in which the pool's code checks the spend and approves
  execution and payment (15,000 gas, 160 bytes), a `SENDER` frame calling a
  token (30,000 gas, 292 bytes), a fresh nonce key as its nullifier at
  sequence 0, and one signature entry by the user. The first spend is 69,390
  gas, near the 67,601 that study gives for such a spend when included;
  later ones are up to 32 gas more, because a larger
  nonce key takes more bytes to encode (FEE-4).
- Demand is Poisson at 60 to 3600 spends an hour, $\rho$ being demand over the
  300 slots an hour. Tips are uniform between 0.001 and 3 gwei, and the fee
  cap is twice the next base fee plus the tip, set when the spend is first
  sent. Nobody bumps a fee. The demand is drawn from the load's own random
  streams, so every row with the same demand is offered the same spends at the
  same times (decision record 0004).
- Who submits (decision record 0005):
  - `relayer`: one party per sender, at a fixed node, sends spends in the order
    they were asked for. Under `one` it sends the next when its node imports
    the block that included the last, which is `FrameLoad`'s waiting rule; in
    section 4, optionally a fixed time after. Under `disjoint-keys` it sends
    each spend at once.
  - `direct`: each user submits their own spend to a random node and, after
    every block that node imports without including it, again to a random
    node.
- Seed 1, four simulated hours a run (two in section 4), about 85 s of wall
  clock for all 36 runs.

## Run

```
python3 experiments/01-one-pending-ceiling/run.py > experiments/01-one-pending-ceiling/results.md
```

## Results

From [results.md](results.md), section 1, a subset of its columns. Demand and
landed spends are per hour, delays in seconds from the user's request to the
block that included the spend.

| per sender | demand | rho | landed | slots missed | delay mean | formula | p99 | waiting at end | busy answers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| one | 60 | 0.20 | 65.25 | 0 | 7.39 | 7.50 | 22.67 | 0 | 0.90 |
| one | 150 | 0.50 | 153.25 | 1 | 13.58 | 12.00 | 62.59 | 0 | 3.40 |
| one | 240 | 0.80 | 236.50 | 1 | 34.92 | 30.00 | 196.56 | 2 | 5.92 |
| one | 270 | 0.90 | 269.25 | 2 | 60.93 | 60.00 | 252.90 | 2 | 7.22 |
| one | 300 | 1.00 | 295.75 | 2 | 155.12 | n/a | 351.65 | 8 | 8.38 |
| one | 600 | 2.00 | 299.50 | 2 | 3630.04 | n/a | 7096.70 | 1200 | 8.59 |
| one | 1200 | 4.00 | 299.50 | 2 | 5416.27 | n/a | 10682.21 | 3594 | 8.59 |
| disjoint-keys | 60 | 0.20 | 65.25 | 0 | 5.87 | 6.00 | 11.91 | 0 | 0.00 |
| disjoint-keys | 300 | 1.00 | 297.75 | 0 | 5.87 | 6.00 | 12.01 | 0 | 0.00 |
| disjoint-keys | 1200 | 4.00 | 1198.00 | 0 | 6.10 | 6.00 | 11.98 | 0 | 0.00 |

Section 2, exposure: seconds from a spend's first submission to any node until
its inclusion.

| rule | demand | landed | delay p90 | exposure p90 | submissions | refused busy | spends held, mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| one, relayer | 300 | 295.75 | 267.93 | 11.85 | 0.99 | 0.00 | 0.99 |
| one, direct | 300 | 294.50 | 414.88 | 414.88 | 17.38 | 15.12 | 7.06 |
| disjoint-keys, relayer | 300 | 297.75 | 10.79 | 10.79 | 1.00 | 0.00 | 1.00 |

Section 3, 1200 spends an hour over $m$ senders under `one`: 299.50, 599.25,
1176.75 and 1198.00 landed an hour for $m$ = 1, 2, 4 and 8, with median delays
of 5431.90, 3583.49, 157.18 and 9.79 s. Section 4, at saturation under `one`:
599.00 an hour at 6 s slots, 899.00 at 4 s and 1795.50 at 2 s; a relayer that
waits 1 s after its import lands 300.00, 600.00, 900.00 and 1614.50 at 12, 6, 4
and 2 s.

## The formula

Under `one` with a relayer, each slot boundary includes exactly one waiting
spend if there is one, in the order asked, provided the spend has reached the
proposer. Let $X$ be the number waiting just after a boundary and
$A \sim \mathrm{Poisson}(\rho)$ the spends asked for during the next slot; then
$X' = \max(X + A - 1, 0)$. Squaring the recursion and taking expectations in
the steady state, with $P(X + A = 0) = 1 - \rho$, gives

$$
E[X] = \frac{\rho^2}{2(1-\rho)}.
$$

A spend asked for at a uniformly random point of a slot waits on average $s/2$
for the boundary and then one slot for each spend ahead of it: the $E[X]$ left
at the last boundary and the $\rho/2$ asked for earlier in the same slot. So

$$
E[D] = \frac{s}{2} + s \left( \frac{\rho^2}{2(1-\rho)} + \frac{\rho}{2} \right) = \frac{s/2}{1-\rho}.
$$

Under `disjoint-keys` every waiting spend is included at the next boundary, and
$E[D] = s/2$. Both ignore propagation, which can only make a spend miss a
boundary it would otherwise have caught, so the simulation should lie at or
above the formula apart from sampling noise.

## What it shows

- **The ceiling is exact: one spend per slot, $3600/s$ an hour.** Under `one`,
  landed spends stop at 299.50 an hour from twice the ceiling up, 2 of 1200
  slots missed in four hours. At 6, 4 and 2 s slots the same sender lands 599,
  899 and 1795.5 an hour. So the testnet's 300 an hour is a twelve-second
  figure, as the analysis's amendment of 2026-09-28 already says, and it is
  reached rather than approached. Under `disjoint-keys` landed spends follow
  demand to the highest tried, 1198 an hour at four times the `one` ceiling;
  what bounds it is block space, 30 spends a block here.
- **Below the ceiling the price is delay, and it follows the formula.** The
  simulated mean is within 17 percent of $\frac{s/2}{1-\rho}$ at every $\rho$
  from 0.2 to 0.9 (7.39 against 7.50 s at 0.2, 34.92 against 30.00 at 0.8),
  and above it at three of the four. Under `disjoint-keys` the mean stays
  between 5.85 and 6.11 s at every demand. By the formula the delay under
  `one` is twice `disjoint-keys`' at $\rho = 1/2$ (13.58 s simulated against
  5.85), so a pool that wants its spends in the next slot on average has half
  the ceiling, 150 an hour. At $\rho = 1$ there is no
  steady state (a p99 of 352 s after four hours), and above it the backlog
  grows by demand minus 300 an hour: 1200 waiting after four hours at 600 an
  hour.
- **At today's demand the ceiling costs almost nothing.** The analysis's test
  of realistic demand takes the busiest quarter of the four Tornado Cash ETH
  pools merged, 8.96 spends an hour. That is
  $\rho = 8.96 \cdot 12 / 3600 = 0.0299$, and the formula gives
  $6/(1-0.0299) = 6.18$ s against 6.00 s without the ceiling. What the ceiling costs in a busy hour is the formula at
  that hour's $\rho$, and an hour above 300 leaves a backlog that drains only
  as fast as demand falls below 300.
- **Who holds the queue decides who sees each nullifier, and for how long.**
  With a relayer, a spend is public for at most a slot: exposure p90 is
  between 11.75 and 11.85 s at every demand in section 2, because the queue is
  the relayer's. The relayer learns every spend when it is asked for, and that
  trust is not in the number. Users who submit their own spends are public for
  their whole wait: exposure p90 is 414.88 s at 300 an hour, against 10.79 s
  under `disjoint-keys`. This is the analysis's amendment on exposure measured:
  under `one` a spend its user submits is public for its whole wait, which
  grows with the queue, and only a trusted relayer shortens that.
- **FP-12 limits a node to one spend, not the network.** Users who submit
  directly at 300 an hour leave 7.06 distinct spends from the one sender
  pending across the network just before a slot on average (15 at most), one
  per node, and make 17.38 submissions per spend, 15.12 of them refused as
  busy. The rate is unchanged, 294.50 an hour, because 98 percent of nodes
  hold some spend when a slot comes; the cost falls on the nodes and on the order of service, whose
  p99 is 784.78 s against the relayer's 351.65.
- **$m$ pools have $m$ ceilings.** At 1200 spends an hour, $m$ = 1, 2, 4 and 8
  senders land 299.50, 599.25, 1176.75 and 1198.00 an hour, and the median
  delay falls from 5431.90 s to 9.79 s. The analysis's multiplier holds, and
  splitting the set buys delay as well as rate: at $m = 4$ each pool is at
  $\rho = 1$ and its median is still 157.18 s.
- **Under `one` the next spend races the block.** A relayer that sends the
  next spend when its node imports a block reaches nodes that have not imported
  it yet; they still hold the spend just included and refuse the next as
  `ErrFrameSenderBusy`, 8.4 to 8.6 times per spend at saturation, against none
  under `disjoint-keys`. Fetching a refused transaction again on a later
  announcement (decision record 0004) recovers most of them; the rest are the
  missed slots, 2 of 1200 at 12 s and 9 of 3600 at 2 s. The race is worst when
  the relayer's own node proposes, because it imports at once: in the smaller
  and sparser network of `sim/tests/test_sim.py` every peer refuses the
  successor and the sender misses seven slots, until the relayer's node
  proposes again. Waiting 1 s, the latest any node here imports a block,
  removes every refusal and every missed slot at 4 s slots and longer, and at
  2 s slots costs a tenth of them instead (1614.50 against 1795.50 an hour). So
  under `one` a relayer has to know the network's import delay and the slot
  time; under `disjoint-keys` it needs neither.
- **Revalidation stays small here.** Every included spend changes the shared
  sender's balance, which every pending spend from it depends on (FP-10), so
  under `disjoint-keys` each is re-simulated at the next block (FP-15): 0.16
  re-simulations per node per block at 1200 spends an hour. Few are pending at
  a reset, because each is included within a slot. Experiment 3 is where this
  is pushed.

## What it does not show

- **Congestion.** Blocks always had room, so spends never competed on tip.
  Under `one` a spend that cannot win block space holds up every user of its
  sender, and only its user can re-price it: the fee fields are committed by
  the user's signature entry, and a replacement must keep the spend's nonce key
  (FP-12). Experiment 15 measures it.
- **Peaks.** Demand is Poisson at a constant rate. The analysis asks whether an
  hour with hundreds of spends happens, which a quarterly mean cannot see; the
  formula prices such an hour, but nothing here says how often one comes.
- **MATCHA's width and EIP-8266**, the two proposals that would move the
  ceiling (experiment 2).
- **Censorship.** Under `one` a whole set is delayed by suppressing one
  transaction at a time, which is the analysis's censorship-resistance point; no
  adversary is modelled.
- **A wallet between the two rules**, one that reads the public mempool and
  waits while its sender has a spend pending, and private order flow, which is
  not bound by FP-12 at all.
- **What the testnet runs.** `exp-frames` reports `disjoint-keys` on
  2026-10-07; `one` was measured on 2026-09-10 and on the relaunched chain on
  2026-09-18. This experiment needs neither.
- **Scale and proving.** 20 nodes in one latency band, no bandwidth limits, and
  spends that are ready the moment they are asked for.
