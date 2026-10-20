# 21. Expiring nonces for a shared sender

**Question.** EIP-8266 gives a frame transaction replay protection from a
deadline of at most a minute instead of a nonce, and lets a node admit
several such transactions from one sender. Composed with EIP-8250 as the
reserved nonce key its Rationale names, it is an alternative to a nonce key,
so a shared sender that uses it keeps its nullifier in its own storage. What
is experiment 01's ceiling then: how many spends an hour does the sender
land as its demand rises, at what delay and exposure, and what do the
deadline and the 13,000 gas cost, when nodes take the EIP's MAY and when
they do not?

**Clauses exercised.** EN-3 to EN-7 (`docs/spec/09-expiring-nonces.md`):
the reserved key, the deadline in place of FP-7, the charge in the paying
frame, several pending per sender under `many` and FP-12 under `one`, and
the hash a block consumes. FP-10 to FP-12, FP-15 and FP-16 as in experiment
01. Gossip follows `sim/emem_sim/network.py` (decision record 0004).

An earlier design study asked the two EIPs' authors whether expiring and
keyed nonces compose, because the keyed nonce is a shared sender's nullifier
and expiring nonces are the only proposal that would let it have several
transactions in flight. EIP-8266's Rationale answers part of it: the two
compose as a reserved key, so a transaction uses one or the other. Decision
record 0030 reads the composition and puts the nullifier in storage.

## Setup

- Experiment 01's network and chain: 20 nodes, 8 peers each, one-way link
  latency uniform in 20 to 100 ms, a block every 12 s from every node in
  turn, reaching the others 0.1 to 1.0 s after its proposer. Gas limit
  2,100,000; genesis base fee 1 gwei; no other traffic.
- Four variants:
  - `one`: the `eip-8141` profile; the spend's nullifier is its EIP-8250
    nonce key, a 256-bit hash at sequence 0, as the design study has it.
  - `disjoint-keys`: the same with FP-12's `disjoint-keys`, EIP-8250's
    "future policy" (decision record 0005).
  - `expiring, many`: the `eip-8266` profile. The spend uses the reserved
    key, carries an expiry frame and the 13,000 gas in its `self_verify`
    frame, reads its nullifier's slot of the pool's storage in that frame,
    expecting 0, and writes it.
  - `expiring, one`: the same, with `expiring_per_sender` `one`: a node that
    does not take the EIP's MAY and keeps FP-12 for the mode.
- The spend is otherwise experiment 01's, the voucher-pool spend.
- A version's deadline is 48 s after the timestamp of the head of the node
  it is made for (section 3 varies this lead). A version that can no longer
  make the next block, its deadline below that node's head timestamp plus
  the slot time, is signed again by its user with a new deadline, and sent
  in place of the old; nobody re-prices otherwise.
- Who submits, as in experiment 01: a relayer at a fixed node, which under
  `one` and `expiring, one` sends the next spend when its node imports the
  block that included the last, and otherwise sends each at once and takes
  back what its node dropped; or `direct` users, who send to a random node
  and again after every block their node imports without the spend.
- Demand is Poisson at 60 to 3600 spends an hour, from the load's own random
  streams, so every variant is offered the same spends at the same times;
  tips uniform between 0.001 and 3 gwei; fee cap twice the next base fee
  plus the tip, set when a version is signed.
- Seed 1, four simulated hours a run.

## Run

```
python3 experiments/21-expiring-nonces/run.py > experiments/21-expiring-nonces/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

The spend:

| variant | frames | data bytes | max gas | prefix gas | spends per block at the limit |
| --- | --- | --- | --- | --- | --- |
| `one`, `disjoint-keys` | 2 | 572 | 69902 | 15000 | 30 |
| `expiring, many`, `expiring, one` | 3 | 580 | 83605 | 28000 | 25 |

Section 1, a relayer; spends an hour, delays in seconds from the request to
the block that included the spend:

| variant | demand | landed | most in a block | delay mean | p99 | waiting at end |
| --- | --- | --- | --- | --- | --- | --- |
| one | 300 | 295.50 | 1 | 154.56 | 339.65 | 9 |
| one | 3600 | 299.00 | 1 | 6602.94 | 13075.81 | 13206 |
| disjoint-keys | 300 | 297.75 | 5 | 5.92 | 12.03 | 0 |
| disjoint-keys | 3600 | 3600.50 | 23 | 6.11 | 12.00 | 0 |
| expiring, many | 300 | 297.75 | 5 | 5.96 | 12.07 | 0 |
| expiring, many | 3600 | 3600.50 | 25 | 6.14 | 12.02 | 0 |
| expiring, one | 300 | 286.00 | 1 | 413.12 | 678.77 | 47 |
| expiring, one | 3600 | 286.00 | 1 | 6661.26 | 13131.18 | 13258 |

Section 2, at 300 spends an hour; exposure is seconds from a spend's first
submission to any node until its inclusion, upper and lower tips the median
delay of the spends tipping above and below the median, and submissions,
refusals, replacements and versions are per spend asked:

| variant | rule | landed | delay p50 | p90 | upper tips | lower tips | exposure p90 | submissions | refused | replaced | versions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| one | relayer | 295.50 | 159.88 | 260.16 | 161.42 | 159.82 | 11.85 | 0.99 | 0.00 | 0.00 | 1.00 |
| one | direct | 295.00 | 143.51 | 397.20 | 146.26 | 140.52 | 397.20 | 16.18 | 14.64 | 0.00 | 1.00 |
| disjoint-keys | direct | 297.75 | 5.92 | 10.81 | 5.71 | 6.02 | 10.81 | 1.04 | 0.03 | 0.00 | 1.00 |
| expiring, many | direct | 297.75 | 5.93 | 10.84 | 5.75 | 6.02 | 10.84 | 1.05 | 0.04 | 0.00 | 1.00 |
| expiring, one | relayer | 286.00 | 461.66 | 612.15 | 461.90 | 461.66 | 11.89 | 0.97 | 0.00 | 3.00 | 1.00 |
| expiring, one | direct | 293.25 | 13.44 | 444.58 | 8.24 | 72.01 | 444.58 | 20.97 | 14.68 | 30.70 | 5.03 |

Section 3, `expiring, many` with a relayer, against the lead of the deadline
over the head's timestamp: at 300 and 3600 spends an hour every lead landed
the same, 297.75 and 3600.50, at mean delays of 5.96 and 6.14 s. With a lead
of 12 s the landed spends averaged 1.05 versions (at most 2 and 3); with 24
to 48 s every spend at 300 an hour had one, and at 3600 at least one spend
needed a second at 24 s. With 60 s nodes refused 0.19 and 0.23 versions per spend as
`ErrFrameExpiryTooFar`.

Section 4, the two variants under which a node holds one spend from the
sender, with a relayer, against how long the fetcher remembers a refusal as
underpriced; a slot is missed when no spend was included though one had
waited since before the previous slot:

| variant | demand | memory, s | landed | slots missed |
| --- | --- | --- | --- | --- |
| one | 300 | 300 | 295.50 | 4 |
| one | 3600 | 300 | 299.00 | 4 |
| one | 3600 | 0 | 299.00 | 4 |
| expiring, one | 300 | 300 | 286.00 | 55 |
| expiring, one | 300 | 0 | 295.75 | 3 |
| expiring, one | 3600 | 300 | 286.00 | 55 |
| expiring, one | 3600 | 0 | 299.25 | 2 |

## What it shows

1. **Where nodes take the MAY, the ceiling goes, as under
   `disjoint-keys`.** `expiring, many` landed what was asked up to 3600 an
   hour (3600.50), at a mean delay of 5.91 to 6.14 s against
   `disjoint-keys`' 5.85 to 6.11, while `one` stopped at 299.00 from 600 an
   hour up. At a 48 s lead no spend at 300 or 3600 an hour needed a second
   signature (section 3).
2. **It costs 13,703 gas a spend**, 83,605 against 69,902, a fifth more:
   EN-5's 13,000 and the expiry frame's 703 (a frame's 475, 8 bytes of
   data at 16 gas each, and 100 of execution). At this gas limit a block
   holds 25 spends rather than 30, and at 3600 an hour one block held 25.
3. **Where nodes do not, the mode is worse than a nonce key.** Under
   `expiring, one` every spend from the sender has the same identity, the
   sender, the reserved key and sequence 0 (FP-12). A node that still holds
   the spend just included takes the relayer's next as its replacement,
   admitting it if it bids 10 percent more and otherwise refusing it as
   `ErrReplaceUnderpriced`, which go-ethereum's fetcher remembers for 300 s
   and does not fetch again (`sim/emem_sim/network.py`). Under `one` the
   same race is answered `ErrFrameSenderBusy`, which is fetched again on
   the next announcement. So `expiring, one` missed 55 slots in four hours
   against `one`'s 4, and landed 286.00 an hour against 299.00; with a
   fetcher that forgets, it missed 2 and landed 299.25. At $\rho = 1$ its
   mean delay was 413.12 s against 154.56.
4. **Users who submit their own spends under `expiring, one` bid for the
   one place a node has.** Each better-paid spend replaces the one a node
   holds, so the order of service follows the tip: at 300 an hour the
   spends tipping above the median waited 8.24 s at the median and those
   below 72.01 s, against 146.26 and 140.52 under `one`, where a node holds
   whichever spend reached it first. Each spend was replaced 30.70 times
   across the nodes and signed 5.03 times, because a replaced version that
   can no longer make the next block is signed again, and 14.68 of its
   20.97 submissions were refused. The 90th percentile stayed long, 444.58 s
   against 397.20.
5. **Exposure follows the queue, as in experiment 01.** Under
   `expiring, many` a user who submits their own spend is public for
   10.84 s at the 90th percentile at 300 an hour, as with a relayer and as
   under `disjoint-keys` (10.81 s). Under `one` and `expiring, one` such a
   user is public for the whole wait, 397.20 and 444.58 s.
6. **The deadline costs little while blocks have room.** At leads of 24 to
   48 s no spend at 300 an hour needed a second signature. At 12 s a spend
   sent too late for the next block was signed again, 1.05 versions a
   spend. At 60 s nodes whose head was older than the relayer's node's
   refused versions as too far, 0.19 a spend, and no spend lost time by it:
   a refusal for any reason but price is fetched again on a later
   announcement (decision record 0004), and the mean delay was 5.96 s at
   every lead.
7. **A queue outlives a deadline.** Under `expiring, one`, at $\rho = 1$
   and above, 99.39 to 99.65 percent of landed spends waited in the
   relayer's queue longer than the 48 s lead before it sent them. Their
   versions were made when the relayer sent them, so their users signed
   then and not when they asked: a relayer can hold a signed spend for at
   most a minute, where under `one` it holds a signed spend for as long as
   the queue is.

**Answer to the question.** The two EIPs compose as alternatives, so a
shared sender has concurrency and a nullifier at once only if the nullifier
lives in its storage and nodes take EIP-8266's MAY. Then it gets what
`disjoint-keys` gives a nonce key, no ceiling and the same delay and
exposure, for 13,703 gas more a spend. Without the MAY it is worse off than
with a nonce key under `one`: its spends share one identity, so a relayer
lost 55 slots in 1200 to the fetcher's memory of a refusal as
underpriced, and users who send their own spends outbid each other. Either
way the sender rests on a node's MAY: EIP-8266's is in its Mempool
section, and `disjoint-keys` is EIP-8250's "future policy" (FP-12).

## What it does not show

- **State gas.** The model has none (`docs/spec/00-model.md`, FEE-4). The
  mode does not save the nullifier's permanent state: EIP-8266's Abstract
  says the scheme "adds no permanent state growth", and that holds for the
  ring, but a shared sender's nullifier must outlive any deadline, so it
  moves from a nonce key to a storage slot. The design study prices both the
  same, one 64-byte item at 97,920 state gas at `CPSB` 1,530, so the
  difference per spend is the 13,703 gas measured here plus whatever the slot's
  regular gas is, and the ring's own slots, which the EIP does not charge.
- **The ring.** `BufferFull` and the ring's wrap are not modelled (EN-7).
  3600 spends an hour is one a second, against the "~4369 sustained
  expiring-nonce TPS" the EIP's Rationale says the ring tolerates.
- **Congestion.** No block here was full of other traffic, so no spend
  under `expiring, many` waited long enough to need more than one signature
  at a 24 s lead or more. When blocks are full, every minute a spend waits
  is another signature from its user, or from whoever holds versions it
  signed in advance.
- **Users who are not online.** A version is made when it is sent, which
  assumes its user signs then: at once for a relayer that sends at once, and
  whenever the relayer gets to it for one that queues.
- **Other per-sender rules.** MATCHA's width (experiment 02) and FOCIL
  (experiment 09) are not combined with the mode.
