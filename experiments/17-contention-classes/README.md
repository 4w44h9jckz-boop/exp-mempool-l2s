# 17. Width by contention class

**Question.** MATCHA gives a shared sender one pending transaction that spends
no width, its baseline, and charges every other, because one write to what a
sender's prefixes read can invalidate all of them. A reply on its thread asks
whether width should be indexed instead by the contention class of what a
prefix reads, so that a spend that reads nothing another can change is not
charged; an earlier design study asks the same of the EIP-8250 authors.
What does a shared sender land under each indexing, and how much work can a
malicious application make every node do for each unit of gas it spends,
against experiment 02?

**Clauses exercised.** MA-14 (`docs/spec/04-matcha.md`, version 3): a class,
with `contention` set to `sender`, the post's, `storage`, under which every
slot of an account is one element, or `slot`, under which each slot is one.
MA-5 to MA-7 take a baseline per class and MA-9 re-runs a baseline free;
MA-2 to MA-4 and MA-8 to MA-11 are experiment 02's, against FP-12's `one` and
`disjoint-keys`. Decision record 0026 has the readings.

## Setup

- Experiment 02's network, chain and spend: 20 nodes with 8 peers each, link
  latency 20 to 100 ms, a block every 12 s from a rotating proposer, finality
  on the beacon chain's happy path, gas limit 2,100,000; the voucher-pool spend,
  with a 256-bit nullifier as its EIP-8250 nonce key, and a relayer at n00
  that sends every spend at once and sends again what its node refused or
  dropped. MATCHA at a safety factor of 2, a cap of $2^{24}$, a lifetime of
  3 h and balance reuse on.
- The spend's `self_verify` frame reads nothing of the pool's storage
  (`none`, experiment 02's), a slot named by its nullifier, expecting 0
  (`own`: a pool that keeps its nullifiers in storage), or slot 0 accepting
  any value (`root`: a pool that reads a root every deposit rewrites), with
  a depositor at n00 that rewrites it in every block. A root read through
  EIP-8272 instead is in no class (MA-14, item 4), so it is `none` under
  every value of `contention`, and is not run.
- Section 2's application earns width for 45 minutes, then for 20 minutes
  sends up to 100 junk spends a block that no builder includes, and changes
  what they read in the next block. It reads one setting (experiment 02's),
  a setting for each junk spend, or, under `one`, one setting in each of 100
  applications of its own. The flip pays 21,000 gas, 5,000 for each slot it
  changes and 2,600 for each further application it calls (EIP-2929 and
  EIP-2200).
- Section 3's adversary holds vouchers for the honest pool and, for the last
  two hours, sends 20 junk spends a block from it to every node, read like
  the honest ones.
- Seed 1; four simulated hours a run in sections 1 and 3, and in section 2
  until two slots after the attack ends.

## Run

```
python3 experiments/17-contention-classes/run.py > experiments/17-contention-classes/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

**Honest throughput** (section 1), spends an hour and seconds from request
to inclusion; re-simulations and work are per node per block, width refusals
per spend asked at n00:

| policy | reads | demand | landed | delay p50 | p90 | first multi-spend block, min | re-simulations | work | width refusals | waiting at end |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| disjoint-keys | none | 1200 | 1198.00 | 6.16 | 10.86 | 0.20 | 0.16 | 118789.08 | 0.00 | 0 |
| matcha, sender | none | 1200 | 1198.00 | 9.90 | 1260.66 | 19.40 | 0.00 | 138623.43 | 0.48 | 0 |
| matcha, storage | none | 1200 | 1198.00 | 6.16 | 10.86 | 0.20 | 0.00 | 114332.55 | 0.00 | 0 |
| matcha, storage | own | 1200 | 1198.00 | 9.90 | 1260.66 | 19.40 | 0.00 | 138623.43 | 0.48 | 0 |
| matcha, slot | own | 1200 | 1198.00 | 6.16 | 10.86 | 0.20 | 0.00 | 114332.55 | 0.00 | 0 |
| disjoint-keys | root | 1200 | 1198.00 | 6.16 | 10.86 | 0.20 | 0.16 | 118892.83 | 0.00 | 0 |
| matcha, every class | root | 1200 | 365.25 | 5759.42 | 9498.25 | 19.40 | 0.31 | 65461.00 | 1.25 | 3331 |
| matcha, sender | none | 2400 | 2263.00 | 2041.47 | 2773.50 | 19.40 | 0.00 | 322395.29 | 1.13 | 499 |
| matcha, storage | none | 2400 | 2387.75 | 6.17 | 10.90 | 0.20 | 0.00 | 227904.25 | 0.00 | 0 |
| matcha, storage | own | 2400 | 2263.00 | 2041.47 | 2773.50 | 19.40 | 0.00 | 322395.29 | 1.13 | 499 |
| matcha, slot | own | 2400 | 2387.75 | 6.17 | 10.90 | 0.20 | 0.00 | 227904.25 | 0.00 | 0 |
| matcha, every class | root | 2400 | 365.25 | 6761.48 | 11472.64 | 19.40 | 0.31 | 71136.30 | 1.13 | 8090 |

`slot` with `none` is `storage` with `none` in every column, the three
classes with `root` are one row because they are the same in every column,
and `disjoint-keys` lands the same with every read.

**Mass invalidation** (section 2), per block of the attack; work is per
node, in gas, and the ratio is that work against the attacker's gas:

| policy | junk reads | junk admitted | re-simulations | work | attacker gas | work per attacker gas | width at end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| one | one setting | 0.99 | 0.55 | 81754.04 | 25742.57 | 3.18 | 0 |
| one | an application each | 99.01 | 98.59 | 6748477.58 | 770693.07 | 8.76 | 0 |
| disjoint-keys | one setting | 99.01 | 98.96 | 6833617.97 | 25742.57 | 265.46 | 0 |
| matcha, sender | one setting | 3.16 | 1.97 | 182862.69 | 25742.57 | 7.10 | 35108 |
| matcha, sender | a setting each | 3.16 | 1.97 | 182862.69 | 36584.16 | 5.00 | 35108 |
| matcha, storage | one setting | 2.93 | 1.97 | 177733.58 | 25742.57 | 6.90 | 30068 |
| matcha, storage | a setting each | 2.93 | 1.97 | 177733.58 | 35445.54 | 5.01 | 30068 |
| matcha, slot | one setting | 2.93 | 1.97 | 177733.58 | 25742.57 | 6.90 | 30068 |
| matcha, slot | a setting each | 99.01 | 98.96 | 6833617.97 | 515841.58 | 13.25 | 16777216 |

**Width draining** (section 3), honest spends landed in hours 3 and 4, the
adversary's; delays from hour 2; junk held and evicted are per node:

| policy | reads | adversary | hour 3 | hour 4 | delay p50 | p90 | junk admitted | junk held | evicted | width refusals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| matcha, sender | none | no | 1230 | 1164 | 6.08 | 10.89 | n/a | n/a | 0.00 | 0.48 |
| matcha, sender | none | yes | 1128 | 1214 | 288.24 | 515.80 | 1153 | 877.35 | 0.00 | 1.07 |
| matcha, storage | none | yes | 1230 | 1164 | 6.08 | 10.89 | 12000 | 4091.00 | 7909.00 | 0.00 |
| matcha, storage | own | yes | 1128 | 1214 | 288.24 | 515.80 | 1153 | 877.35 | 0.00 | 1.07 |
| matcha, slot | own | yes | 1230 | 1164 | 6.08 | 10.89 | 12000 | 4091.00 | 7909.00 | 0.00 |

`slot` with `none` is `storage` with `none`, and `sender` with `own` is
`sender` with `none`.

## What it shows

1. **Where a spend reads nothing a write can change, a class waives the
   charge and MATCHA's warm-up goes.**
   - The spend of experiment 02 keeps its nullifier in its nonce key and
     reads none of the pool's storage. Under `storage` and `slot` it shares
     no class with any other, so every one is a baseline.
   - At 1200 spends an hour its delays are `disjoint-keys`' (6.16 s and
     10.86 s), where under `sender` the 90th percentile is 1260.66 s and the
     first block with two spends comes at minute 19.40, after the first
     width.
   - The pool makes no re-simulation (0.00 against `disjoint-keys`' 0.16 a
     node and block) and the least work, 114332.55 gas a node and block
     against 118789.08.
   - At 2400 an hour `storage` lands 2387.75 an hour, as `disjoint-keys`
     does, where `sender` lands 2263.00 and leaves 499 waiting.
2. **A nullifier kept in storage needs `slot`.** A spend that reads its own
   nullifier's slot is `sender`'s row under `storage`, to the hundredth
   (1260.66 s at 1200 an hour, 2263.00 landed at 2400), and `none`'s under
   `slot`. `storage` cannot tell a slot that one spend reads from one that
   every spend reads.
3. **A live root takes every indexing down together.** When every spend
   reads a slot that a depositor rewrites in every block, every pending spend
   is re-run at every head (MA-9), and all of them share that slot under
   every value of `contention`.
   - MATCHA landed 365.25 spends an hour under all three, against demand of
     1200 and of 2400. The median delay was 5759.42 s and 6761.48 s, with
     3331 and 8090 spends waiting at the end, and 1.25 and 1.13 width
     refusals per spend asked.
   - `disjoint-keys` landed them all, at 0.16 and 0.34 re-simulations a
     node and block.
   - The class question for a root has its answer in EIP-8272: an entry of
     the recent root contract is in no class (MA-14, item 4), so a root read
     that way is `none`.
4. **`slot` lets an application buy re-runs at the price of a slot write.**
   - With a setting for each junk spend, every junk spend under `slot` is a
     baseline. 99.01 were admitted at n05 a block, every node re-ran 98.96
     a block, and the work was `disjoint-keys`' 6833617.97 gas a node and
     block. Width never moved from the cap, 16777216.
   - The flips cost 515841.58 gas a block, 5,000 for each slot, so the
     ratio was 13.25 work per attacker gas. Under `sender` and `storage` the
     same strategy gets 5.00 and 5.01, below their 7.10 and 6.90 with one
     setting: width still admits 3.16 and 2.93 junk spends a block, and the
     flip now writes a slot for each.
   - Under `one`, an application for each junk spend gets 8.76. `slot` gives
     one application what `one` gives a hundred, at a lower price: a further
     slot costs the flip 5,000 gas, a further application 2,600 more.
   - `disjoint-keys` with one setting stays far above all of them, at
     265.46.
5. **A waived class lets junk in for nothing, and only eviction stops it.**
   - Under `sender`, junk that reads like the honest spends drains the
     width: 1153 junk spends were admitted, and the honest median delay from
     hour 2 rose to 288.24 s.
   - Under `storage` and `slot` with `none`, and `slot` with `own`, every
     junk spend is a baseline that spends no width. All 12000 were admitted,
     every node held 4091.00 of them at the end and evicted 7909.00 for
     room, and nothing refused one for width.
   - Honest spends landed as with no adversary, 1230 and 1164 in hours 3
     and 4, at the same delays, because a junk spend at a tip of 1 wei loses
     every eviction (FP-14).
   - The width that a waiver saves an honest pool is also the bound on what
     one sender holds in every pool, and under a waiver that bound is the
     pool's size. Junk that bids as much as the honest spends is not run.

**Answer to the question.** Indexed by `storage`, a shared sender whose
spends read nothing of its storage gets `disjoint-keys`' throughput and
delays from MATCHA, and mass invalidation stays near `sender`'s ratio, 6.90
against 7.10 with one setting. The price is that junk from that sender is no
longer bounded by width, only by the pool's size and its eviction order.
`slot` extends the same throughput to a nullifier kept in storage, and buys
it with an attacker's ratio of 13.25, above `one`'s with a hundred
applications. A pool that reads a live root gets 365.25 spends an hour under
every indexing, and EIP-8272 is its way out.

## What it does not show

- A reduced charge. Reply #2 asks for the charge to be "waived or reduced";
  MA-14 waives it, by taking the baseline per class, or charges it in full.
- FOCIL, the deterrent the post relies on for junk, as in experiment 02:
  junk at a tip of 1 wei never lands here.
- What a client pays to know a class. In the model it is read off the run
  the pool already makes; a client that checks width before the run cannot
  know it (`docs/spec/04-matcha.md`, open questions).
- A deposit's own work: the depositor's transaction writes one slot and is
  26,000 gas.
- Storage repricing. A change to what a cold write costs changes every
  ratio in section 2 whose flip writes more than one slot.
