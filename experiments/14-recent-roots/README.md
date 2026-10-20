# 14. Recent roots that expire in the pool

**Question.** A spend proved against an EIP-8272 recent root is valid only
while its root is in the window. How many admitted spends outlive their root
in pools, against the window's length, congestion and builders that delay
them? What does each node re-check when a root leaves the window? And what
happens to spends when builders leave the root writes out?

**Clauses exercised.**

- RR-2 to RR-8 (`docs/spec/08-recent-roots.md`, version 1): slots, root
  writes, the verifier frame's shape, admission, dependencies, eviction for
  age, and the block's own check.
- FP-15 (`docs/spec/02-frame-pool.md`): what a pool re-runs at a head change.
- IL-1 to IL-8 under `eip-8369` (`docs/spec/07-focil.md`), for one
  row.

A privacy protocol's spend proves membership against a root, and EIP-8272
lets the public mempool check that root without reading the protocol's
storage. A builder that delays inclusion can force a spend to be proved
again. EIP-8272 says "This EIP does not guarantee inclusion of root
writes", and a set whose writes stop keeps working for the window: a
fallback a privacy protocol can rely on.

## Setup

- **Network:** 50 nodes, 8 peers each, link latency 20 to 100 ms,
  go-ethereum's gossip, a slot every 12 s, gas limit 30,000,000, base fee
  from 1 gwei. Each slot's block is built by one of ten builders, drawn at
  random (decision record 0023). A builder that filters leaves out what the
  row says: the spends or the root writes. Each run lasts 1800 s, and each
  row pools five runs, seeds 1 to 5.
- **Pools:** `eip-8272`, with `recent_root_length` 8192 in section 1 and 4
  to 64 in sections 2 to 4, and `root_margin` 0 except in section 4.
- **A root source** writes a fresh root every slot from one account, from
  3 s.
- **Users** ask for one spend a slot on average, from 60 s to 1500 s, each
  from a sender of its own. A user reads the latest root written at or
  before the head of a random node, which it then watches. It proves for
  12 s and sends the spend to a random node, and sends it again after every
  block its node imports without it. When a node refuses the spend for its
  root, the user proves again against the latest root. The proving time is
  assumed, not measured (decision record 0023).
- **Congestion:** one row of section 1 adds 1,000,000-gas transfers at the
  gas target, and three a second more from 600 s to 900 s.

## Run

```
python3 experiments/14-recent-roots/run.py > experiments/14-recent-roots/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

Section 1, the EIP's window of 8191 usable slots, with 610 spends in every
row. Delays are in seconds, and the age of a spend's root is in slots, when
the spend lands.

| builders that filter | landed | delay p50 | p90 | max | age landed max | slots to spare | proofs | evictions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 610 | 17.52 | 22.64 | 24.17 | 3 | 8188 | 1.00 | 0.00 |
| none, congested | 610 | 17.75 | 23.18 | 66.58 | 7 | 8184 | 1.00 | 0.00 |
| 0.9, spends | 606 | 89.48 | 304.28 | 441.35 | 37 | 8154 | 1.00 | 0.00 |
| 0.9, spends, `eip-8369` | 610 | 18.91 | 24.83 | 28.04 | 3 | 8188 | 1.00 | 0.00 |
| 0.9, root writes | 610 | 17.93 | 24.07 | 452.34 | 37 | 8154 | 1.00 | 0.00 |
| every one, root writes from 600 s | 610 | 17.52 | 22.64 | 24.17 | 77 | 8114 | 1.00 | 0.00 |

Section 2, shorter windows with builders that leave the spends out. Proved
again is the share of spends that took more than one proof; evictions are
the pools that dropped a version for its root's age, per spend; largest
burst is the most spends one node dropped at one block.

| length | share | landed | delay p90 | max | proofs | max | proved again | evictions | largest burst | re-runs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 0.5 | 610 | 71.29 | 192.88 | 1.34 | 5 | 0.26 | 17.0 | 5 | 0 |
| 4 | 0.9 | 591 | 398.08 | 821.88 | 5.05 | 22 | 0.79 | 202.7 | 20 | 0 |
| 8 | 0.9 | 599 | 316.34 | 515.32 | 2.08 | 7 | 0.52 | 53.9 | 8 | 0 |
| 16 | 0.9 | 601 | 303.50 | 499.09 | 1.32 | 4 | 0.26 | 15.8 | 7 | 0 |
| 32 | 0.9 | 605 | 303.50 | 502.91 | 1.04 | 2 | 0.04 | 2.1 | 4 | 0 |
| 64 | 0.9 | 606 | 304.28 | 441.35 | 1.00 | 1 | 0.00 | 0.0 | 0 | 0 |

With no builder filtering, every length lands all 610 spends with one proof
each.

Section 3, builders that leave the root writes out and include the spends.
Slots with a root is the mean per run, out of 150.

| length | builders that leave writes out | slots with a root | spends landed | last landed (s) | proofs | max |
| --- | --- | --- | --- | --- | --- | --- |
| 16 | 0.9 | 15.2 | 610 | 1572.00 | 2.11 | 16 |
| 16 | every one from 600 s | 49.0 | 282 | 768.00 | 19.75 | 57 |
| 64 | every one from 600 s | 49.0 | 545 | 1344.00 | 3.11 | 27 |
| 8192 | every one from 600 s | 49.0 | 610 | 1512.00 | 1.00 | 1 |

Section 4, the margin, at length 64 with every builder leaving the root
writes out from 600 s.

| margin | landed | last landed (s) | age landed max | proofs | refused |
| --- | --- | --- | --- | --- | --- |
| 0 | 545 | 1344.00 | 63 | 3.11 | 4.3 |
| 8 | 501 | 1248.00 | 55 | 4.97 | 8.0 |
| 16 | 455 | 1152.00 | 47 | 7.41 | 12.9 |
| 32 | 357 | 960.00 | 31 | 13.79 | 25.7 |

## What it shows

- **Under the EIP's window, no spend outlived its root.** Not one spend was
  evicted for its root's age in section 1. No spend needed a second proof,
  even with 0.9 of the builders leaving the spends out. The oldest root a
  spend landed with was 37 slots, against a usable window of 8191. The
  same 37 slots came from 0.9 of the builders leaving the root writes out,
  and the largest age, 77 slots, from every builder doing so from 600 s.
  Congestion moved the oldest root from 3 slots to 7. A builder delay that
  forces re-proving has to last on the order of the window, which is 8191
  slots, about 27 hours at 12 s. With 0.9 of the builders leaving the spends
  out, the slowest spend waited 441.35 s.
- **A window must come down to the delay before spends outlive it.** With
  0.9 of the builders filtering, the oldest root that landed was 37 slots.
  At length 64 nothing was evicted. At 32, 0.04 of spends were proved
  again; at 16, 0.26; at 8, 0.52; at 4, 0.79, with 5.05 proofs a spend on
  average and at most 22. Re-proving also costs delay: at length 4 the p90
  rose to 398.08 s, against 304.28 s at 64.
- **A node re-checks nothing when a root leaves the window.** RR-7 evicts
  by the root expiry recorded at admission, so a slot advance drops spends
  without running any prefix. The re-runs column is 0 in every row: no
  dependency of a spend changed, because only a head that goes back
  changes a written entry (decision record 0023). What a node does at a
  root's expiry is drop a batch. The largest batch was 20 spends at one
  node at one block, at length 4 with 0.9 filtering. The EIP expects
  this: "A reorganization or synchronized expiry may evict many
  transactions that use one popular root, but dependency indexing lets
  clients identify affected transactions without rerunning unrelated
  validation prefixes" (Security Considerations).
- **Inclusion lists remove the delay, and with it the risk.** Under
  `eip-8369` the same 0.9 of filtering builders left delay p90 at
  24.83 s and the oldest root at 3 slots, against 22.64 s and 3 slots with
  no builder filtering.
- **When root writes stop, spends continue for exactly the usable window,
  then stop.** With every builder leaving the writes out from 600 s, the
  last root is the 49th slot's. At length 16 the last spend landed at
  768 s, slot 64, which is 49 plus the usable 15. At length 64 it landed at
  1344 s, slot 112, which is 49 plus 63. At 8192 every spend landed, since
  the window outlasts the run. That is the fallback, measured: degradation
  for $W$ slots after the last write, and then no spend at all. After that,
  each user's every proof is refused: 19.75 proofs a spend on average at
  length 16, and at most 57.
- **Filtering 0.9 of root writes ages roots, but does not stop them.** A
  run had a root in 15.2 of its 150 slots on average, and a spend was first
  sent with a root up to 37 slots old. At length 16 that cost 2.11 proofs a
  spend; at 64 and above, one.
- **A node's margin shortens that grace period slot for slot.** At length
  64 with the writes stopped, a margin of $m$ made the oldest root that
  landed $63 - m$ slots old, and moved the last spend $m$ slots earlier:
  1344 s at 0, 1248 s at 8, 1152 s at 16 and 960 s at 32. Spends landed
  fell from 545 to 357, and proofs rose from 3.11 a spend to 13.79. No
  spend was evicted at any margin, because nothing delayed the spends, so
  the margin saved no pool work here. A spend reaches every node within a
  second of being sent. So a margin acts only on a root that is already
  old when its spend is sent. Under the EIP's window that is a root more
  than $8191 - m$ slots old: a set whose writes stopped about 27 hours ago,
  less the margin.

## What it does not show

- **Reorganisations.** RR-6's dependencies are recorded, but no head here
  removes a written root, so their re-check is never exercised.
- **Wallets that read the window.** The users here prove again against the
  latest root even when that root is already too old to be admitted. A
  wallet that compares its root's age to the window would stop, and the
  proofs counted after the writes stop would fall to one.
- **Other proving times.** The 12 s is assumed. A wallet whose proof takes
  longer sends a root that is older by as many slots. Under the EIP's window
  that does not matter until it is on the order of the window.
- **Several root sources for one set.** A design that relies on the fallback
  would have more than one source per set. Here one account writes, and a write
  left out holds back the ones after it on its nonce.
- **The contract's gas.** `RECENT_ROOT_CODE` is unset, so the frame is
  evaluated directly and its gas is a limit the experiment gives it.
