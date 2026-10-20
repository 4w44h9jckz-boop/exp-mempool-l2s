# 15. Wallets that bump fees

**Question.** Experiment 00 found that the backlog a burst leaves does not
unwind, because its wallets never re-price a transaction the base fee has
passed. How fast does the backlog clear when wallets do re-price, and what
does it cost them? What changes when users stop sending above a price of
their own? And what does a shared sender under FP-12's `one` do when its
pending spend is stranded and only that spend's user can re-price it
(experiment 01, "What it does not show")?

**Clauses exercised.**

- FEE-1 and FEE-2 (`docs/spec/00-model.md`): the base fee and the
  effective tip.
- NP-11 to NP-13 (`docs/spec/01-nonce-pool.md`): a replacement must raise
  both fee fields by `price_bump`, 10 percent under `geth`; later nonces
  wait behind a stranded one.
- FP-12 (`docs/spec/02-frame-pool.md`): under `one` a shared sender has one
  pending spend, and a replacement keeps its nonce key.
- BB-1 to BB-5 (`docs/spec/03-block-building.md`): the miner takes a
  sender's consecutive nonces in one block when their tips win.

No clause changes. Wallets that re-price and users who stop are the
simulator's (decision record 0024); neither is a pool's behaviour, and no
source read here specifies either.

## Setup

- Experiment 00's network, chain and demand: 30 nodes, 8 peers each, a
  block every 12 s, gas limit 2,100,000 (100 transfers, a target of 50), a
  base fee from 1 gwei, 400 senders of plain transfers at 2.5 a second, 12 a
  second from 600 s to 900 s and 2.5 a second after, and 100 senders of
  frame transactions at 0.2 a second.
- Each sender's wallet sends to one node, drawn when it first sends, and
  sends its replacements there. Experiment 00 sent each transfer to a random
  node, so its run and this one's seed 1 with wallets that never bump are
  close but not the same.
- Wallets price a new transfer with a tip uniform in 0.001 to 3 gwei and a
  fee cap of twice the next base fee plus the tip, as in experiment 00. A
  wallet that bumps waits until its node has imported 1 or 3 blocks without
  the transaction, and then replaces either its oldest pending transaction
  or every one:
  - by 10 percent, raising tip and fee cap each by NP-11's least, rounded up;
  - or to the market, which raises the fee cap further, to twice the next
    base fee plus the new tip.
- Section 2 gives each user a most it pays a gas, base fee and tip together,
  uniform in 1 to 10 gwei or in 0.5 to 3 gwei. A user does not send while
  the next base fee plus its tip is above it, and that demand leaves rather
  than waits. Neither range is from a source.
- Section 3 adds a shared sender under `eip-8141`, whose users ask for a
  spend every 36 s on average until 1500 s, a third of `one`'s ceiling of a
  spend a slot (experiment 01). Its relayer sends one spend at a time. A
  spend's fees are committed by its user's signature entry, so only its
  user can re-price it, and the relayer sends the new version in its
  place.
- Seeds 1 to 5; every row pools the five runs, each 1800 simulated seconds.

## Run

```
python3 experiments/15-fee-bumping/run.py > experiments/15-fee-bumping/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

Section 1, delays in seconds from asking to inclusion; price paid in gwei a
gas over the burst's transfers that landed; stuck senders, pool and base fee
at the end of the run, as a mean and the range over runs; cleared is the
runs in which the pool fell back to its quiet level, and the latest, in
seconds after the burst.

| wallets | burst landed, of 18,211 | burst p50 | burst p99 | replacements | price paid | stuck senders | pool at end | base fee at end | cleared |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| never | 13,990 | 8.98 | 1034.21 | 0.00 | 3.25 | 91 | 1380 | 1.27 | 0 of 5 |
| oldest, 10% after 1 block | 17,338 | 40.01 | 943.11 | 3.33 | 5.62 | 34 | 417 | 10.88 | 0 of 5 |
| oldest, 10% after 3 blocks | 15,986 | 10.85 | 1024.09 | 1.18 | 3.92 | 60 | 826 | 4.70 | 0 of 5 |
| every one, 10% after 1 block | 18,211 | 63.08 | 484.54 | 8.16 | 13.60 | 0 | 48 | 18.14 | 5 of 5, 612 s |
| oldest, to the market after 1 block | 18,211 | 58.73 | 405.10 | 2.20 | 11.07 | 0 | 44 | 22.53 | 5 of 5, 492 s |
| oldest, to the market after 3 blocks | 18,211 | 44.39 | 445.00 | 0.87 | 12.13 | 0 | 39 | 27.28 | 5 of 5, 420 s |
| every one, to the market after 1 block | 18,211 | 63.08 | 405.54 | 8.02 | 12.67 | 0 | 48 | 17.51 | 5 of 5, 612 s |

No node refused a replacement in any run of section 1.

Section 2, the burst's share priced out and the highest base fee of any
block, in gwei:

| most a gas | wallets | priced out | burst landed | burst p90 | peak base fee | stuck senders | cleared |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | never | 0.00 | 13,990 | 705.31 | 5.67 | 91 | 0 of 5 |
| none | oldest, to the market after 1 block | 0.00 | 18,211 | 281.52 | 76.21 | 0 | 5 of 5, 492 s |
| 1 to 10 gwei | never | 0.18 | 13,718 | 728.66 | 2.88 | 34 | 0 of 5 |
| 1 to 10 gwei | oldest, to the market after 1 block | 0.19 | 14,818 | 433.64 | 4.55 | 0 | 4 of 5, 888 s |
| 0.5 to 3 gwei | never | 0.47 | 9,566 | 11.17 | 1.00 | 0 | 5 of 5, 24 s |
| 0.5 to 3 gwei | oldest, to the market after 1 block | 0.47 | 9,566 | 11.18 | 1.00 | 0 | 5 of 5, 24 s |

Section 3, 197 spends in every row; the longest hold is the longest time
between two of the sender's spends landing, or from the last to the end of
the run when a spend never landed, which includes stretches when no spend
was asked for:

| transfer wallets | spend users | landed | delay p90 | max | longest hold |
| --- | --- | --- | --- | --- | --- |
| never | never | 197 | 18.49 | 75.88 | 127 |
| never | 10% after 3 blocks | 197 | 18.49 | 75.88 | 127 |
| never | to the market after 1 block | 197 | 17.87 | 42.36 | 127 |
| oldest, to the market after 1 block | never | 116 | 70.33 | 396.42 | 941 |
| oldest, to the market after 1 block | 10% after 3 blocks | 146 | 867.62 | 1107.88 | 782 |
| oldest, to the market after 1 block | to the market after 1 block | 197 | 98.27 | 245.18 | 166 |

## What it shows

- **Re-pricing clears the backlog, and NP-11's least bump is enough if it
  reaches every stranded transaction.** Wallets that re-price only their
  oldest transaction by 10 percent clear it in no run: under NP-13 a
  sender's later transfers wait behind the oldest, each needs bumps of its
  own, and they get them one at a time. The same 10 percent applied to every
  pending transaction clears all five runs, within 612 s of the burst's end.
  A bump to the market clears all five even on the oldest alone, within
  492 s, because one bump puts a transaction above the base fee and the
  miner then takes the sender's later nonces in the same block or the next.
- **Once every fee cap is above the base fee, the tips decide, and a larger
  bump buys nothing.** The two "every one" rows have the same burst median,
  63.08 s, because they raise the tips alike and differ only in caps that no
  longer bind. Waiting 3 blocks before bumping to the market cleared no later
  than waiting 1 (420 s against 492 s at most) for 0.87 replacements a
  transfer instead of 2.20.
- **The bound on NP-11's least bump is arithmetic.** A cap raised 10 percent
  a block falls behind a base fee that FEE-1 raises by up to an eighth a
  block, so a transfer priced at twice the base fee stays includable for
  $n$ full blocks while $2 \cdot 1.1^n \geq 1.125^n$, that is
  $n \leq \ln 2 / \ln(1.125/1.1) \approx 30.8$. A burst that fills blocks for
  longer than that strands even wallets that bump every transaction every
  block, unless they bump by more than the least.
- **Clearing moves the wait from the stranded to everyone, and raises the
  price.** Without bumping, the 4,221 transfers of the burst, over five
  runs, that have not landed by the end are what lets the rest through
  quickly: a burst median of 8.98 s, against 44.39 to 63.08 s when
  everything lands. The tail shrinks instead, from 1034.21 s at p99 to
  405.10 s. With demand that pays whatever the next
  block asks, every transaction re-priced back into the queue keeps blocks
  full, and the base fee climbs for as long as the queue lasts: a peak of
  76.21 gwei against 5.67, and 11.07 gwei a gas paid against 3.25.
- **Users with a price of their own stop that climb, and leave instead.**
  With most a gas drawn from 1 to 10 gwei, 0.18 to 0.19 of the burst never
  sends, the peak base fee falls from 76.21 to 4.55 gwei, and wallets that
  bump to the market clear the backlog in 4 of 5 runs. Without bumping it
  still strands 34 senders. With 0.5 to 3 gwei, 0.47 of the burst never
  sends, the base fee never rises above the 1 gwei it starts at, no backlog
  forms, and whether wallets bump makes no measurable difference. Elastic
  demand is what experiment 00's backlog lacked as much as bumping was; the
  cost of the remedy is the demand that leaves.
- **A shared sender under `one` survives only if its users re-price to the
  market, every block.** While other wallets never bump, the base fee stays
  low enough that every spend lands, at most 75.88 s after it was asked
  for, and whether its users re-price hardly matters. Once other wallets
  bump to the market, a spend whose user does not re-price is stranded, and
  under `one` every later user waits behind it: 116 of 197 spends land, and
  the sender is held for 941 s on average. A user who bumps 10 percent every
  3 blocks loses to the base fee and lands 146. A user who bumps to the
  market every block lands all 197, at most 245.18 s after asking. The
  relayer cannot do this for them, because the fees are in the user's
  signature entry, so a spend's user has to stay online until it lands.

## What it does not show

- Cancellation, fee estimators, wallets that read the pool rather than the
  head, users who come back once the price falls, and a relayer that
  re-prices by sponsoring out of its own pocket (decision record 0024).
- A wallet read from source. Both bump sizes, the patience and the choice
  between the oldest and every transaction are assumed; only the 10 percent
  is go-ethereum's `PriceBump` default (NP-1).
- The shared sender under MATCHA or `disjoint-keys`, where one stranded
  spend does not hold up the others (experiments 01 and 02).
- Private order flow, and a burst longer than the bound above.
