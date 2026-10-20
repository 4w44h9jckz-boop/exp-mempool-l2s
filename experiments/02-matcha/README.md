# 02. MATCHA against one pending transaction per sender

**Question.** Does MATCHA lift the one-pending-transaction ceiling for a shared
sender, how soon and at what cost in delay, and how much revalidation work can
an adversary make every node do under it, against FP-12's `one` and
`disjoint-keys`?

**Clauses exercised.** MA-2 (the charge), MA-4 (width earned from finalized
gas), MA-5 to MA-7 (baseline and additional admissions), MA-9 (re-runs paid
from width, and balance reuse), MA-10 and MA-11 (reservations kept rather than
removed), against FP-12 and FP-15 as experiment 01 exercised them; FEE-4,
version 2, prices the spend. Finality is the simulator's
(`sim/emem_sim/chain.py`) and is not specified in `docs/spec/`.

MATCHA is a proposal on ethresear.ch (topic 25949, 2026-09-08), stated here as
clauses in `docs/spec/04-matcha.md`, with its open choices in decision record
0007. A sender keeps EIP-8141's one free pending transaction, its *baseline*,
and pays for each further one with *width*, earned from the gas its frame
transactions used in finalized blocks. An earlier design study priced the
charge for its voucher-pool spend: admission gas 26,601, a charge of 53,202 at
a safety factor of 2, and 1.27 further admissions paid for by one included
spend; it left out the cap, the lifetime and the charges for re-runs. The post
names two attacks: an application that makes nodes re-run many prefixes with
one write, and an adversary who drains an honest sender's width. This
experiment measures how fast width arrives, what bounds it, what the re-run
charges do to a pool that is the payer of every spend, and both attacks with
nothing deterring them.

## Setup

- The network and chain of experiment 01: 20 nodes with 8 peers each, link
  latency 20 to 100 ms, go-ethereum's gossip, a block every 12 s from a
  rotating proposer, imported by the others 0.1 to 1.0 s later. Gas limit
  2,100,000, genesis base fee 1 gwei, and no other traffic.
- Finality on the beacon chain's happy path (consensus-specs `c489a990`,
  phase 0): a node that imports block $s$ knows every block up to
  $32(\lfloor s/32 \rfloor - 2)$ is final. A block is final 64 to 95 slots
  after it is produced, and width arrives once an epoch, 32 blocks' worth at a
  time.
- Pools: `eip-8141` (`one`), the same with `per_sender = disjoint-keys`, and
  `matcha` (safety factor 2, cap $2^{24}$, lifetime 3 h, balance reuse on),
  also with balance reuse off. Section 2 varies the factor and the cap.
- The spend is that study's voucher-pool spend whole (decision record 0008): an
  expiry frame a day ahead, the pool's `self_verify` frame (5,000 gas, 260
  bytes), a `SENDER` frame calling a token (41,000 gas, 68 bytes), a 256-bit
  nullifier as its nonce key at sequence 0, and one signature entry by the
  user. Its admission gas is 28,621 and its included gas 69,621, against the
  study's 26,601 and 67,601: the difference is the expiry frame's execution and
  the bytes FEE-4 counts, the nonce fields among them (decision record 0006).
  The pool holds $10^{24}$ wei and pays for every spend.
- Demand is Poisson at 600, 1200 and 2400 spends an hour, twice to eight times
  experiment 01's ceiling, with tips uniform between 0.001 and 3 gwei and a fee
  cap of twice the next base fee plus the tip.
- The relayer sits at n00. Under `one` it is experiment 01's, serial.
  Otherwise it sends each spend at once and, after every block, sends again
  any spend its node refused or no longer holds (decision record 0008).
- Section 3's adversary is an application with its own relayer; section 4's
  holds vouchers for the honest pool. Both send junk: valid spends at a tip of
  1 wei, below every builder's minimum, from one node after every block it
  imports.
- Seed 1, four simulated hours a run, 23 runs, about four minutes of wall
  clock.

## Run

```
python3 experiments/02-matcha/run.py > experiments/02-matcha/results.md
```

## Results

From [results.md](results.md). The spend under MA-2:

| safety factor | charge | additional admissions one included spend pays for | spends a slot width sustains | charges in a cap of 2^24 | cap's ceiling, spends an hour |
| --- | --- | --- | --- | --- | --- |
| 1 | 28621 | 2.43 | no limit | 586 | 5793.75 |
| 2 | 57242 | 1.22 | no limit | 293 | 3046.88 |
| 3 | 85863 | 0.81 | 5.29 | 195 | 2128.12 |

Section 1, a subset of its columns. Landed and demand are spends an hour;
delays are seconds from request to inclusion; first width is when n00 was
first credited, in minutes; work is the admission gas of every prefix run for
the sender, per node per block.

| policy | demand | landed | last 2 h | delay p50 | p90 | first width | work | width refusals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| one | 1200 | 299.50 | 299.50 | 5431.90 | 9739.20 | n/a | 40793.27 | 0.00 |
| disjoint-keys | 600 | 599.50 | 604.50 | 6.02 | 10.80 | n/a | 59226.39 | 0.00 |
| disjoint-keys | 1200 | 1198.00 | 1197.00 | 6.16 | 10.86 | n/a | 118789.08 | 0.00 |
| disjoint-keys | 2400 | 2387.75 | 2380.00 | 6.17 | 10.90 | n/a | 237562.65 | 0.00 |
| matcha 2, cap 2^24 | 600 | 599.50 | 604.50 | 7.24 | 408.88 | 19.21 | 62855.29 | 0.27 |
| matcha 2, cap 2^24 | 1200 | 1198.00 | 1197.00 | 9.90 | 1260.66 | 19.21 | 138623.43 | 0.48 |
| matcha 2, cap 2^24 | 2400 | 2263.00 | 2997.00 | 2041.47 | 2773.50 | 19.21 | 322395.29 | 1.13 |
| matcha 2, cap 2^24, no reuse | 600 | 342.00 | 324.00 | 2702.82 | 5381.81 | 19.21 | 51521.38 | 1.50 |
| matcha 2, cap 2^24, no reuse | 1200 | 342.00 | 324.00 | 4782.85 | 8998.85 | 19.21 | 54376.32 | 1.25 |

Section 2, MATCHA at 1200 spends an hour:

| policy | landed | last 2 h | delay p50 | p90 | width at end | cap's ceiling |
| --- | --- | --- | --- | --- | --- | --- |
| matcha 1, cap 2^24 | 1198.00 | 1197.00 | 7.63 | 714.67 | 15575134 | 5793.75 |
| matcha 2, cap 2^24 | 1198.00 | 1197.00 | 9.90 | 1260.66 | 14373052 | 3046.88 |
| matcha 3, cap 2^24 | 1032.25 | 1284.00 | 2318.71 | 2514.31 | 38901 | 2128.12 |
| matcha 2, cap 2^22 | 896.00 | 974.00 | 2287.05 | 3408.55 | 15638 | 984.38 |
| matcha 1, cap 2^24, no reuse | 494.50 | 544.00 | 4592.65 | 7832.27 | 23578 | 5793.75 |

Section 3, mass invalidation: per block of a 20-minute attack, junk admitted
at the adversary's node, and per node the re-simulations and the work for the
adversary's sender, against the gas of the one write a block that invalidates
the junk.

| policy | junk admitted | re-simulations | work | attacker gas | work per attacker gas | width at start | width at end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| one | 0.99 | 0.55 | 81754.04 | 25742.57 | 3.18 | 0 | 0 |
| disjoint-keys | 99.01 | 98.96 | 6833617.97 | 25742.57 | 265.46 | 0 | 0 |
| matcha 2, cap 2^24 | 3.16 | 1.97 | 182862.69 | 25742.57 | 7.10 | 15662087 | 35108 |

Section 4, width draining: honest spends landed by hour, the adversary acting
in hours 3 and 4, and delays of the spends asked in those hours. Under `one`
none of them had landed by the end, because the queue was already hours long.

| policy | junk sent to | hour 1 | hour 2 | hour 3 | hour 4 | delay p50 from hour 2 | p90 | junk admitted | junk held |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| one | no adversary | 299 | 299 | 300 | 299 | n/a | n/a | n/a | n/a |
| one | n05 | 299 | 299 | 70 | 60 | n/a | n/a | 1 | 0.70 |
| one | every node | 299 | 299 | 16 | 15 | n/a | n/a | 2 | 0.95 |
| matcha 2, cap 2^24 | no adversary | 795 | 1598 | 1230 | 1164 | 6.08 | 10.89 | n/a | n/a |
| matcha 2, cap 2^24 | n05 | 795 | 1598 | 1128 | 1214 | 288.18 | 515.57 | 924 | 854.90 |
| matcha 2, cap 2^24 | every node | 795 | 1598 | 1128 | 1214 | 288.24 | 515.80 | 1153 | 877.35 |

## What it shows

- **MATCHA lifts the ceiling once the sender has width, and not before.** A
  new sender earns nothing until its first block is final: n00 is first
  credited at 19.21 minutes and the first block with two spends follows at
  19.40, against 0.20 under `disjoint-keys`. Until then the pool is under
  `one`, and the backlog it builds sets the delays. After it, MATCHA lands
  what `disjoint-keys` lands at 600 and 1200 spends an hour (599.50 and
  1198.00) where `one` lands 299.50, but its p90 delay over the run is 408.88
  and 1260.66 s against 10.80 and 10.86. A pool that has run for a while has
  width in hand; a new pool, or one whose width an adversary has spent, pays
  the cold start again.
- **The cap is a throughput ceiling, because width arrives an epoch at a
  time.** MA-4 credits a whole epoch of final blocks at once and clips the sum
  at the cap, so a sender can add at most one cap of width a epoch: a baseline
  a slot plus $\lfloor \mathit{width\_cap} / \mathit{charge} \rfloor$ spends
  an epoch. That is 3046.88 an hour at $2^{24}$ and a factor of 2, and at 2400
  an hour MATCHA drains its backlog at 2997.00 an hour over the last two hours
  and lands 2263.00 over the run. At $2^{22}$ the ceiling is 984.38, below the
  demand of 1200, and the pool lands 974.00 an hour over the last two hours,
  896.00 over the run. A cap has to hold an epoch of the busiest sender's
  gas, which the post, leaving the cap to clients, does not say.
- **Without balance reuse MATCHA is barely above `one`.** Every included spend
  changes the pool's balance, which every pending spend from it reads through
  `APPROVE`, so with `reuse_balance` off every additional spend pending at
  every node is charged again at every block, and most are removed for want of
  width without running. The pool lands 342.00 an hour at every demand tried,
  494.50 at a factor of 1, against `one`'s 299.50. The post's sentence that "a
  change to the payer balance does not by itself require rerunning validation"
  is what makes MATCHA work for a sender that pays for itself; in the model the
  reuse is exact (decision record 0007, item 7), and a client has to make it so.
- **The safety factor sets how long the cold start lasts.** At a factor of 1
  the p90 delay is 714.67 s, at 2 1260.66 s. At 3 one included spend pays for
  0.81 further admissions, so width compounds slowly from the free baselines
  and sustains at most 5.29 spends a slot; the pool lands 1032.25 an hour over
  the run, catches up at 1284.00 over the last two hours, and ends with 38,901
  of width, under one charge. The study puts the share of admitted additional
  spends that must land for width to keep up at 79 percent at a factor of 2
  and 118 percent at 3, so at 3 additional spends cannot pay for themselves;
  what lets the pool catch up at all is the free baseline in every slot.
- **Mass invalidation is bounded by width, and costs about twice `one`.** One
  write a block invalidates every junk spend the adversary has pending. Under
  `disjoint-keys` that is 99.01 junk spends admitted a block and 6,833,617.97
  gas of prefix work per node per block, 265.46 times the adversary's gas.
  Under `one` it is 81,754.04 and 3.18 times. Under MATCHA it is 182,862.69
  and 7.10 times: the adversary spent its width, from 15,662,087 at the start
  to 35,108 at the end, and was then a baseline a block. What a malicious
  application can buy is what it earned with honest gas earlier, at a factor
  of 2 half of it in admission work, and nothing past the cap.
- **Under `one` a single junk spend nearly halts the pool; under MATCHA
  draining costs delay.** Under `one` the adversary's first junk spend takes
  the pool's only slot at every node it reaches and never leaves, because no
  builder includes it and the `eip-8141` profile has no lifetime: honest spends
  in hours 3 and 4 fall from 300 and 299 to 70 and 60 when it sends to n05,
  and to 16 and 15 when it sends to every node, with one and two junk spends
  admitted in all. Under MATCHA the adversary gets 924 and 1153 junk spends
  admitted over two hours and leaves 854.90 and 877.35 pending at every node
  on average. Honest spends still land, 1128 and 1214 an hour against 1230 and
  1164 without it, but a spend asked in those hours waits 288.18 s at the
  median and 515.57 at p90, against 6.08 and 10.89. The junk takes width as it
  arrives, once an epoch, and the honest spends wait for the next epoch's.
  The deterrent the post relies on, FOCIL forcing junk on chain, is not
  modelled (decision record 0008).
- **A refusal for width costs a node a prefix run.** MA-6 runs the prefix
  before it checks width, so a resend refused for width is work no charge
  pays for. At 1200 an hour MATCHA does 138,623.43 gas of work per node per
  block where `disjoint-keys` does 118,789.08 for the same landed spends, with
  0.48 refusals per spend asked. The charge depends only on the static prefix,
  so a client could check width first; `docs/spec/04-matcha.md` carries this
  as an open question.

## What it does not show

- **FOCIL** (EIP-7805) and the post's deterrent, under which a sender's junk
  would be forced on chain and paid for. Section 4 is draining with nothing
  deterring it.
- **State gas.** The model credits `gas_used` in one dimension. If "the actual
  gas used" includes the 97,920 state gas EIP-8250 charges for a fresh nonce
  key, a pool that spends from fresh nullifiers earns about twice the width
  shown here (`docs/spec/04-matcha.md`, open questions).
- **Finality that stalls.** No slot is missed and finality never lags, so
  width always arrives 64 to 95 slots late. In a period without finality no
  sender earns width, and every shared sender is back under `one`.
- **A relayer that reads width.** The relayer resends blindly, so the width
  refusals are its own; holding spends until width covers them would refuse
  fewer and land the same.
- **The lifetime.** Section 4's junk is sent in the last two hours of the
  run, so MA-8 never removes it; a longer attack would meet the three-hour
  lifetime, after which the junk must be sent, and charged, again.
- **Several pools, payers other than the sender, and congestion.** One shared
  sender, which is its own payer, in blocks that always have room. The
  paymaster extension in reply #7 of the thread, under which a payer earns
  width, is not modelled.
