# 13. MATCHA's load floor

**Question.** Under MATCHA's optional linear fees, what does a user of a busy
shared sender pay over a user who sends the same spend alone, at the same
demand? How often does the floor bind, and what does it cost a wallet that
does not read it?

**Clauses exercised.**

- MA-13, the load floor, with MA-6's check 5 (`docs/spec/04-matcha.md`,
  version 2).
- MA-2 to MA-7, the charge, width and baseline, as in experiment 02.
- MA-9 to MA-11, with balance reuse, as in experiment 02.
- FP-16 and BB-2: builders take the highest effective tips first.

MATCHA is a proposal on ethresear.ch (topic 25949), stated as clauses in
`docs/spec/04-matcha.md` and measured in experiment 02. One of its two
optional strengthenings asks each additional transaction from a sender for
an effective tip that rises with the charges of the sender's other pending
additional transactions. The post says the rule "raises fees for honest users
when their shared `sender` is busy". For a privacy pool that is pricing a
user by how busy their anonymity set is. One piece of evidence would retire
that concern: a `base_price` small enough relative to market priority fees
that the floor never binds.

## Setup

- **Network:** 50 nodes, 8 peers each, link latency 20 to 100 ms,
  go-ethereum's gossip, a block every 12 s from a proposer that rotates
  through every node, gas limit 30,000,000, base fee from 1 gwei. Each run
  lasts 1800 s, and each row pools three runs, seeds 1 to 3.
- **Pools:** `matcha` with `load_price` 0, which is the profile, or 0.01,
  0.1 or 1 gwei.
- **Two populations, at one, two or three spends a slot each,** from 12 s
  to 1680 s. Both send `SharedSenderLoad`'s spend, each to a random node:
  - users of one shared sender, which every node credits with the width cap
    before the run, as if it had been busy before (decision record 0022);
  - users who each have a sender of their own, so each is its sender's
    baseline and meets no floor.
- **Wallets:** each draws a tip uniform in 0.001 to 3 gwei and a fee cap of
  twice the next base fee plus the tip. In section 1 it offers the higher of
  its tip and the floor the node it sends to asks of it; in section 2 it
  offers its tip. A spend a block leaves out is sent again, at the same
  fees, to a random node.

## Run

```
python3 experiments/13-load-floor/run.py > experiments/13-load-floor/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

Section 1, users of the shared sender, who meet the floor. Tips are mean
gwei a gas per spend; premium is what a user offered over what it drew, and
raised the share of spends whose floor was above their tip. Refused for the
floor is per spend, summed over nodes. In every row users who send alone
offer what they drew, are never refused, and wait p50 6.42 to 6.47 s.

| load price, gwei | spends a slot | drawn | offered | premium | premium p90 | max | raised | refused for the floor | delay p50 | p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.010 | 3 | 1.520 | 1.520 | 0.000 | 0.000 | 0.046 | 0.01 | 0.11 | 6.06 | 11.09 |
| 0.100 | 1 | 1.546 | 1.548 | 0.001 | 0.000 | 0.133 | 0.02 | 0.24 | 6.02 | 10.88 |
| 0.100 | 3 | 1.520 | 1.531 | 0.011 | 0.000 | 0.569 | 0.06 | 0.91 | 6.18 | 11.23 |
| 1.000 | 1 | 1.546 | 1.675 | 0.128 | 0.477 | 2.157 | 0.17 | 0.81 | 6.15 | 10.99 |
| 1.000 | 2 | 1.540 | 2.072 | 0.532 | 1.894 | 7.427 | 0.39 | 2.48 | 6.46 | 11.40 |
| 1.000 | 3 | 1.520 | 2.425 | 0.906 | 2.750 | 8.572 | 0.53 | 5.82 | 6.66 | 11.76 |

Section 2, users of the shared sender who offer what they drew. Delays are
in seconds; the last column but one is section 1's p90 for the same users
meeting the floor.

| load price, gwei | spends a slot | spends | landed | delay p50 | p90 | max | p90 meeting the floor | refused for the floor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.100 | 3 | 1277 | 1277 | 6.75 | 11.66 | 122.81 | 11.23 | 1.18 |
| 1.000 | 1 | 397 | 397 | 8.90 | 29.16 | 78.27 | 10.99 | 3.37 |
| 1.000 | 2 | 831 | 831 | 13.79 | 95.78 | 447.69 | 11.40 | 24.73 |
| 1.000 | 3 | 1277 | 1089 | 55.14 | 402.18 | 1347.87 | 11.76 | 46.73 |

The other rows and columns are in `results.md`.

## What it shows

- **The floor is a fee on the anonymity set's traffic.**
  Users who send alone are each their sender's baseline and never meet it.
  Users of the shared sender meet it whenever another user's spend is
  pending at their node. At 1 gwei it raises 0.17 of spends at one spend a
  slot, 0.39 at two and 0.53 at three. The mean premium grows from 0.128
  to 0.532 to 0.906 gwei a gas, against a mean drawn tip of about 1.5. The
  same users at the same demand, sending alone, pay nothing extra.
- **What one user pays depends on where it lands in the slot.** The floor
  clears when a block includes the sender's pending spends. The first user
  after a block is the baseline and pays nothing; the $k$-th after it faces
  $k - 1$ times `load_price`. So the premium is unequal among the users of
  one sender. At 1 gwei and three a slot the p90 is 2.750 gwei and the
  largest 8.572.
- **At a `load_price` well below market tips the floor almost never binds.**
  At 0.01 gwei it raises at most 0.01 of spends, and the mean premium rounds
  to 0.000 gwei at every demand. At 0.1 gwei it raises at most 0.06. That is
  the retirement test above, met for these prices against tips drawn
  between 0.001 and 3 gwei. The same price makes the deterrent small too:
  under MA-13 the $n$-th additional spend of a junk batch faces $n$ times
  `load_price`, so at 0.01 gwei the hundredth faces 1 gwei. Experiment 13
  does not measure an attacker (decision record 0022).
- **A floor read at one node is not the floor at the next.** Nodes see
  spends in different orders, so a spend priced at its own node's floor is
  refused by nodes whose load is higher. That is 5.82 refusals a spend at
  1 gwei and three a slot. It still reaches a builder: every spend landed,
  and delay p50 rose from 6.06 s at 0 to 6.66 s.
- **A wallet that does not read the floor pays in delay.** At 1 gwei and
  three a slot, users who offer what they drew wait p50 55.14 s and p90
  402.18 s. Only 1089 of 1277 spends land in the run, against 11.76 s p90
  for those who meet the floor. Such a spend gets into a pool only as the
  baseline, or where the load is low enough for its tip.
- **The width the floor sits on held.** Refusals for width were at most
  0.23 a spend, all at three a slot, and every one of those spends landed.
  Three a slot is close to the most the width cap carries before finalized
  blocks earn more (decision record 0022).

## What it does not show

- **The attacker the floor is for.** A junk batch from a malicious
  application, or one that drains an honest sender, is experiment 02's
  subject. Here only its arithmetic is quoted.
- **Wallets that re-price.** No wallet here bumps a fee after a refusal, so
  a refusal at another node is never answered. A wallet that reads the
  highest floor among several nodes would pay more and be refused less.
- **Busier senders.** Above three spends a slot the width cap, not the
  floor, decides admission until finalized blocks earn more, which is
  experiment 02's ceiling.
- **Market tips other than a uniform draw.** Whether the floor binds
  depends on `load_price` against what users would tip anyway. That
  calibration needs publishing, and a client sets `load_price`.
