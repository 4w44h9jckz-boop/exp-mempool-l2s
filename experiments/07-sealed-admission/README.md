# 07. Sealed admission

**Question.** How long does a cheap sealed payment wait as demand nears the
32 commitments a block takes? And what can a flood of sealed transactions
that tolerate no commitment before them do to it, under each reading of
EIP-8184's open admission policy and each eviction order?

**Clauses exercised.**

- LU-3: the ticket's fees, and the ToB fee as what is left of the fee cap.
- LU-5: the checks against the head and the state.
- LU-6 and LU-7: the commitment order, and a builder's greedy selection with
  `max_preceding_commitments`.
- LU-8: the admission policy, `any`, `next-block` or `every-head`
  (decision record 0014).
- LU-10: capacity, under the profile's `last` and the `unplaced` variant
  (decision record 0015).
- LU-11: a new head, which re-applies the policy under `every-head`.
- LU-12 and LU-13: commitments in one block, decrypted transactions and
  refunds in the next.
- MD-11: a sender held in one subpool at a time.

EIP-8184, LUCID (Draft, read at `258836f9`), lets a sender propagate a sealed
transaction: a ticket that pays, and a ciphertext. A builder commits up to 32
of them in block $n$, in an order the protocol fixes by the ToB fee each
pays. The keys are released after that, and the decrypted transactions run
at the top of block $n+1$.

The EIP leaves the pool's policy open. "The mempool must naturally protect
against spam and reject STs that have no chance of getting included"
(Rationale), and "there are no fixed settings that can be established at
this point for STs that should or should not be propagated" (Security
Considerations). The same section names the threat: "Denial-of-service
vectors for STs are instances with a low ToB fee and low
`max_preceding_commitments`".

One reading of LUCID has a private payment pay a minimal ToB fee and rely on
being uninteresting, competing for the 32 commitment slots of a block against
every other sealed transaction on the network. This experiment measures what
that costs the payment, and what the EIP's denial-of-service vector costs it
under each reading.

## Setup

- **Network** (decision record 0015):
  - 10 nodes, 8 peers each, go-ethereum's gossip as in every experiment.
  - A block every 12 s from a rotating proposer, gas limit 60,000,000, so
    the ToB segment is 7,500,000 gas and a block commits at most 32.
  - Transfers of 1,000,000 gas fill the rest of the gas target, so the base
    fee stays near 1 gwei.
  - Each run lasts 1200 s; rows count what was first sent from second 240
    to second 960.
- **Pools:** the `eip-8184` profile with the policy and eviction order each
  row names. Sections 1 to 3 use the profile's 4096 slots; section 4's
  pools have 256, as experiment 05's do.
- **Payments:**
  - Each bids no ToB fee and tolerates 31 commitments before it, with
    100,000 gas and 512 bytes.
  - Each comes from a sender of its own with one in flight, sent to a
    random node.
  - After every block that does not commit it, the sender sends it again
    to a random node. A row that says *resealed* re-encrypts it first,
    which gives it a new hash.
- **Trades:** 2 a slot, bidding a ToB fee drawn between $10^{12}$ and
  $10^{15}$ wei, tolerating 1 to 8 commitments, with 300,000 gas.
- **Floods** (`sim/emem_sim/workload.py`, `SealedFlood`):
  - The flood's sealed transactions tolerate no commitment before them, so
    a block commits at most one of them, and only first. Each has 256 bytes
    and 16,384 gas, the least LU-4 allows, and is revealed.
  - *Cheap* ones all bid 1 wei of ToB fee, above the payments and below
    every trade: the EIP's low ToB fee and low tolerance.
  - *Escalating* ones bid from $10^{15} + 1$ wei up, 1 wei more each, so
    each comes first when it is sent.
  - In section 4 the adversary sends each node, directly, at the start and
    after every block the node imports, enough to fill its pool and 16 more.
    It stops at the first refusal.
- **Seed** 1.

## Run

```
python3 experiments/07-sealed-admission/run.py > experiments/07-sealed-admission/results.md
```

About three minutes. Every figure below is from `results.md`.

## Results

**One pool and the next block** (section 1), at the profile's 4096 slots,
holding 16 payments and 2 trades before the flood:

| pool | flood | admitted | honest held | next payment | honest committed | flood committed | flood held after the head |
| --- | --- | --- | --- | --- | --- | --- | --- |
| any | cheap | 4142 | 2 | ErrUnderpriced | 2 | 0 | 4094 |
| next-block | cheap | 0 | 18 | ok | 19 | 0 | 0 |
| any, unplaced | cheap | 4142 | 18 | ok | 19 | 0 | 4077 |
| any | escalating | 4142 | 0 | ErrUnderpriced | 0 | 1 | 4095 |
| every-head | escalating | 4142 | 0 | ErrUnderpriced | 0 | 1 | 1 |
| any, unplaced | escalating | 4142 | 17 | ok | 18 | 1 | 4077 |

The escalating flood's commitment cost it 24212884000033 wei once revealed.
Its senders held 4296383037508157440 wei for the pool to admit them all; the
cheap flood's held 136383037508157440.

**Honest demand** (section 2), delays from first sending to commitment, in
seconds:

| policy | resealed | a slot | committed | delay p50 | p90 | p99 | max | held |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| any | no | 16 | 967 | 6.60 | 10.94 | 11.94 | 12.53 | 9.70 |
| any | no | 28 | 1717 | 6.60 | 11.97 | 47.63 | 142.44 | 20.49 |
| any | no | 31 | 1871 | 7.08 | 24.07 | 417.57 | 730.27 | 72.37 |
| every-head | no | 31 | 1871 | 7.09 | 24.76 | 441.57 | 766.27 | 46.05 |
| next-block | yes | 31 | 1853 | 7.83 | 22.51 | 391.09 | 729.52 | 60.62 |
| every-head | yes | 31 | 1858 | 10.72 | 65.92 | 188.62 | 459.34 | 49.15 |
| any | no | 34 | 2025 | 7.85 | 125.87 | 694.55 | 813.27 | 183.17 |
| every-head | no | 34 | 2025 | 7.85 | 125.87 | 691.79 | 807.49 | 50.44 |

**Who waits** (section 3), at 31 a slot, by the quartile of a payment's
first hash: the 90th percentile and the longest delay, in seconds:

| policy | resealed | q1 p90 | q1 max | q2 p90 | q2 max | q3 p90 | q3 max | q4 p90 | q4 max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| any | no | 11.13 | 12.15 | 11.01 | 12.10 | 11.38 | 23.66 | 259.82 | 730.27 |
| every-head | yes | 11.25 | 96.49 | 51.24 | 226.86 | 83.19 | 247.03 | 102.69 | 459.34 |

**A flood on the network** (section 4), 256-slot pools, payments at 16 a
slot. Committed is by the end of the run, 240 s after the flood stops:

| pool | flood | payments | committed | trades | committed | flood held | flood committed | paid, wei |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| any | none | 967 | 967 | 122 | 122 | 0.00 | | |
| any | cheap | 854 | 227 | 122 | 122 | 254.79 | 28 | 307340431015964 |
| next-block | cheap | 967 | 967 | 122 | 122 | 0.97 | 9 | 127095503634441 |
| every-head | cheap | 967 | 967 | 122 | 122 | 0.74 | 9 | 125855108186121 |
| any | escalating | 854 | 15 | 113 | 93 | 256.00 | 81 | 1470182951170642 |
| next-block | escalating | 854 | 69 | 113 | 95 | 256.00 | 81 | 1471381532504656 |
| every-head | escalating | 854 | 522 | 113 | 112 | 255.72 | 69 | 1272782451917007 |
| any, unplaced | escalating | 967 | 967 | 122 | 122 | 246.20 | 81 | 1799000904238057 |
| next-block, unplaced | escalating | 967 | 967 | 122 | 122 | 246.19 | 81 | 1798958479557573 |

## What it shows

1. **Below the ceiling, the policy does not matter.** At 16 payments a slot,
   every payment was committed within 12.53 s under all three policies, with
   the same delays to the hundredth of a second. Nothing was refused,
   because every payment had a place in the next block. The policies differ
   only in what a pool holds once demand exceeds a block.

2. **Near the ceiling, the hash decides who waits.** Payments that bid no
   ToB fee and use the same gas are committed in the order of their hashes
   (LU-6). Neither sender nor pool chooses that order, and a payment keeps
   its hash while it waits.
   - At 28 a slot the median stayed at 6.60 s, while p99 rose to 47.63 s and
     the longest wait to 142.44 s.
   - At 31 a slot, with 2 trades a slot, demand is above the 32 a block can
     commit. The median was still 7.08 s, but p99 was 417.57 s and the
     longest 730.27 s.
   - Section 3 shows who waits. At 31 a slot no payment in the lower three
     quartiles of hashes waited more than 23.66 s, while the top quartile's
     90th percentile was 259.82 s. That reading has a payment rely on
     being uninteresting; under load, a payment also relies on being lucky.

3. **Resealing turns a fixed rank into a lottery, under `every-head`
   only.** At 31 a slot, re-encrypting before each resend under
   `every-head` cut p99 from 441.57 s to 188.62 s, and the longest wait
   from 766.27 s to 459.34 s. It raised the median from 7.09 s to 10.72 s,
   and spread the waiting over every quartile. Under `next-block` a pool
   keeps the old version and refuses the new one as an underpriced
   replacement (LU-9), so resealing changed little (p99 391.09 s). `every-head`
   holds less than `any` at every load above the ceiling: 50.44 against
   183.17 at 34 a slot, for the same delays.

4. **The EIP's denial-of-service vector shuts payments out under `any`, the
   profile's policy.**
   - In one pool of 4096 slots, the cheap flood was admitted in full and
     pushed out every payment. The next payment was refused, though the
     flood's transactions can never be committed while a trade is there.
   - On the network, 227 of 854 payments sent during the flood were
     committed by the end of the run, against 967 of 967 without it. Trades
     were untouched.
   - The flood was committed 28 times, in blocks whose builder held no
     trade, and paid 307340431015964 wei in all.
   - `next-block` and `every-head` refuse it, since it has no place, and
     payments were committed as without a flood.

5. **A flood that comes first gets past every policy, under the EIP's only
   order.**
   - Each escalating transaction has a place when it arrives: first. So
     every policy admits it, and LU-10's `last` then drops the honest ones,
     payments and trades alike.
   - Under `any` and `next-block` the flood's transactions outlive the
     flood: each stays first until a block commits it, one a block. That is
     81 commitments though the flood stopped sending at second 960, and
     only 15 and 69 of 854 payments were committed by the end.
   - `every-head` prunes them at the next head, and 522 were.
   - The cost to the adversary is one ticket a block, mostly refunded on
     reveal: 1470182951170642 wei in all under `any`. It also has to hold
     capital: 327243961923010560 wei across its 320 senders on the network,
     4296383037508157440 for a pool of the profile's size.

6. **Dropping what has no place first closes both.** Under `unplaced`,
   every payment and every trade sent during either flood was committed.
   - Pools stayed nearly full of the flood's transactions: 246.20 of 256
     under the escalating one.
   - The flood still bought the first commitment of every block (81).
   - Trades that tolerate few predecessors were pushed out of their place
     by it and evicted (311 times across nodes), and committed after
     sending again. Their median delay was 6.35 s against 6.22.
   - Without a flood the order makes no difference, because no honest run
     here filled a pool.

## What it does not show

- **Inclusion lists.** FOCIL's committee lists sealed transactions too
  (EIP-8184, Inclusion lists with STs and bundles). A flood that occupies
  every public pool also occupies what the committee sees, so the lists
  are unlikely to be a remedy, but this is not modelled.
- **Bundles and sponsorship.** A key publisher can rank a bundle of
  payments with its own sponsor transaction (EIP-8184, Rationale). The
  Security Considerations suggest such publishers "may garner more
  permissive bounds during filtering". Neither is modelled.
- **Builders that maximise revenue.** LU-7 is the greedy rule attesters
  check. A builder keeps only priority fees, so it may choose otherwise.
- **Withheld keys.** Every key here is released. A flood that withholds pays
  the whole ToB fee of what is committed, which matters to the escalating
  flood and not to the cheap one.
- **Gossip that forgets.** A node here never forgets what a peer knows, so a
  resent payment with an unchanged hash does not spread again. A client
  whose record of known transactions is bounded would spread it, and
  resealing would matter less.
- **Payments that bid.** A payment bidding a few wei of ToB fee escapes a
  cheap flood at 1 wei, and the adversary can bid just below the lowest
  trade instead. The race is not run.
- **Scale.** Section 4's pools have 256 slots, so that a flood sent afresh
  every block fits the model. Section 1 shows the same outcome at the
  profile's 4096, with a sender for each slot.
