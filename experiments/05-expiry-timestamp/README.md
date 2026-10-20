# 05. The expiry timestamp

**Question.** How many transactions does a pool admit that no block can
include, when it checks a deadline against the head's timestamp and when it
checks against the next slot's? And does the next slot's check, with or
without a tip-first eviction order, close the pool to floods of such
transactions?

**Clauses exercised.**

- FP-8 and FP-15, step 2, in version 4, with the `expiry_margin` variant
  (decision record 0011).
- FP-14 and its `evict_first` variant (decision record 0010).
- FP-11, for a default-code sponsor, which `hegota-testnet` caps and
  `eip-8141` does not.
- FP-13: a sponsor that sends no frame transaction can use the account-nonce
  pool.
- BB-3 and BB-5: a builder skips a transaction that fails in its block.

EIP-8141's expiry verifier "reverts unless `block.timestamp <=
expiry_timestamp`" (Expiry Verifier Frame, at `258836f9`). Its mempool section
says a node drops a transaction whose deadline "is less than the node's view
of the current block timestamp at any point", and does not say which block is
current. FP-8 has read it as the head since version 1, as go-ethereum names
its head the current block. So a deadline at or above the head's timestamp
and below the next block's passes, and no block can include the transaction.

Experiment 04 found that such transactions push everything out of a full pool
under a tip-first eviction order. It concluded that closing both of its
floods needs the tip order and a check against the next slot's timestamp.
This experiment measures that check, `expiry_margin` set to the slot time,
and tests the conclusion with a third flood.

## Setup

- **Pools.** Four variants of `eip-8141`: the EIP's eviction order or tip
  first, each with `expiry_margin` 0 (the head) or 12 (the next slot). Section
  1 also runs `hegota-testnet` alone and with tip first and the next slot.
- **The adversary's transactions**, each from a default-code sender of its
  own:
  - *free*: a fee cap and tip of 1 wei, paid by a canonical paymaster
    instance (experiment 04);
  - *expiring*: the earliest deadline the pool admits, the head's timestamp
    plus `expiry_margin`, at a tip of 10 gwei, paid by the same paymaster;
  - *drained*: the same price without a deadline, paid by one default-code
    sponsor. The sponsor then sends its whole balance away in a 21,000-gas
    transfer at 20 gwei, through the account-nonce pool. The next block
    includes the transfer first, and every transaction the sponsor backs
    fails there.
- **Section 1: one pool and the next block.** As in experiment 04, a pool of
  4096 is filled with honest transactions in three classes: *pays*,
  *deadline* (600 s out) and *stranded*. Then 4096 of the adversary's
  transactions arrive, and the pool builds the next block.
- **Section 2: the network**, that of experiments 01 to 04:
  - 10 nodes, 8 peers each;
  - a block every 12 s from a rotating proposer;
  - gas limit 2,100,000.

  Wallets that pay for themselves send 1500 transactions an hour, half with a
  deadline 10 minutes out. They resend after every block that leaves their
  transaction out, and give it up at the deadline. From minute 10 to minute
  20 the adversary keeps every pool full with a fresh batch at every head.
  Every pool holds at most 256 here, so that a batch made fresh at every head
  fits in the model's run time (decision record 0011).
- **Section 3: honest deadlines.** Experiment 04's burst at the profiles'
  4096, with no adversary: 45,000 transactions an hour more from minute 10 to
  minute 25.
- **A transaction no block can include** is counted at admission: an
  admission, at any node, of a transaction whose deadline is below the
  timestamp of the next block built after it.
- Seed 1. 18 one-pool runs and 11 network runs take about five minutes.

## Run

```
python3 experiments/05-expiry-timestamp/run.py > experiments/05-expiry-timestamp/results.md
```

## Results

From [results.md](results.md).

**Section 1, at one pool**, a subset of the rows. "Next block" counts the
adversary's transactions and the honest ones it includes.

| pool | adversary | admitted | out: pays | out: deadline | out: stranded | next block: theirs | next block: honest | skipped | paid, wei |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | expiring | 0 | 0 | 0 | 0 | 0 | 29 | none | 0 |
| eip-8141 | drained | 4096 | 1366 | 1365 | 1365 | 1 | 0 | 4096 ErrInsufficientFunds | 441000000000000 |
| eip-8141, tip first | expiring | 4096 | 1366 | 1365 | 1365 | 0 | 0 | 4096 ErrFrameExpired | 0 |
| eip-8141, tip first, next slot | free | 0 | 0 | 0 | 0 | 0 | 29 | none | 0 |
| eip-8141, tip first, next slot | expiring | 4096 | 1366 | 1365 | 1365 | 42 | 0 | none | 22645392000000000 |
| eip-8141, tip first, next slot | drained | 4096 | 1366 | 1365 | 1365 | 1 | 0 | 4096 ErrInsufficientFunds | 441000000000000 |
| hegota-testnet | drained | 1 | 0 | 1 | 0 | 1 | 28 | 1 ErrInsufficientFunds | 441000000000000 |

**Section 2, on the network.** Rows are the honest transactions first sent
during the flood.

| profile | flood | class | asked | landed in the flood | landed | gave up | delay p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | none | deadline | 114 | 112 | 114 | 0 | 6.33 |
| eip-8141 | expiring | deadline | 114 | 112 | 114 | 0 | 6.33 |
| eip-8141, next slot | expiring | pays | 125 | 14 | 125 | 0 | 528.09 |
| eip-8141, next slot | expiring | deadline | 113 | 10 | 56 | 57 | 284.25 |
| eip-8141, tip first | expiring | deadline | 113 | 0 | 103 | 10 | 363.08 |
| eip-8141, tip first, next slot | expiring | deadline | 113 | 0 | 50 | 63 | 271.12 |
| eip-8141 | drained | pays | 125 | 0 | 125 | 0 | 348.07 |
| eip-8141 | drained | deadline | 113 | 0 | 103 | 10 | 363.08 |
| eip-8141, tip first, next slot | drained | deadline | 113 | 0 | 103 | 10 | 363.08 |

What the flood cost over its ten minutes:

| profile | flood | admitted | of them never includable | included | skipped | paid, wei | base fee, wei |
| --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | expiring | 130433 | 130433 | 0 | 12558 ErrFrameExpired | 0 | 199074 |
| eip-8141, next slot | expiring | 70804 | 2510 | 2104 | none | 1112058408773214584 | 4517201087 |
| eip-8141, tip first | expiring | 130560 | 130560 | 0 | 12801 ErrFrameExpired | 0 | 19598 |
| eip-8141, tip first, next slot | expiring | 130560 | 2560 | 2142 | none | 1136258765343761136 | 4509885775 |
| eip-8141 | drained | 131070 | 0 | 51 | 12800 ErrInsufficientFunds | 21422662215696000 | 22602 |
| eip-8141, tip first, next slot | drained | 131070 | 0 | 51 | 12800 ErrInsufficientFunds | 21422662215696000 | 22602 |

**Section 3, honest deadlines.**

| profile | landed | gave up | admitted, never includable | per one given up | skipped by builders | refused as expired |
| --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | 4718 | 3247 | 771 | 0.24 | 6 | 0 |
| eip-8141, next slot | 4718 | 3247 | 53 | 0.02 | 0 | 3247 |
| eip-8141, tip first | 4718 | 3247 | 699 | 0.22 | 6 | 0 |
| eip-8141, tip first, next slot | 4718 | 3247 | 49 | 0.02 | 0 | 3247 |

Under each order, both readings included the same transactions.

## What it shows

- **Under the EIP's order, the head's reading costs work, not inclusion.**
  - An expiring flood takes only the room honest transactions leave. Its
    transactions have the nearest deadline, so they are the first victims.
  - On the network, honest transactions land exactly as without a flood.
  - Even so, nodes admitted 130,433 of the flood's transactions, every one of
    them never includable, and builders skipped 12,558. Nobody paid for any
    of that work.
- **Under tip first, the head's reading is free exclusion.** No honest
  transaction first sent during the flood landed before it ended, and the
  flood paid nothing. This is experiment 04's one-pool finding, now on the
  network.
- **The next slot's check makes the expiring flood pay. It does not stop it.**
  - Every transaction the pool holds can now be in the next block. At one
    pool, the next block includes 42 of the adversary's, which pay
    22,645,392,000,000,000 wei.
  - On the network over ten minutes, blocks included 2104 to 2142 of them,
    which paid 1,112,058,408,773,214,584 to 1,136,258,765,343,761,136 wei.
    The pending base fee rose to about 4.5 gwei.
  - Under either order the flood's 10-gwei transactions outbid every honest
    one, in the block if not in the pool. Under the EIP's order only 14 of
    125 transactions without a deadline landed during the flood; under tip
    first, none.
  - So under the next slot's check, an expiring flood is a purchase of block
    space, at the price any mempool charges for it.
- **The next slot's check leaves the drained flood untouched, and that flood
  is cheaper.**
  - Under every `eip-8141` variant, 4096 transactions backed by one
    default-code sponsor push every honest transaction out of a full pool.
    In the next block, one 21,000-gas transfer of the sponsor's balance
    makes all 4096 fail.
  - On the network, no honest transaction first sent during the flood landed
    before it ended. Ten minutes cost the adversary 51 transfers, which paid
    21,422,662,215,696,000 wei. The capital the sponsors held, at most
    134,331,487,229,309,952 wei reserved at a node, comes back with every
    transfer.
  - Experiment 03 found that a balance touch invalidates nothing. This one
    invalidates everything, because the balance that moves is the payer's
    own.
  - The EIP says a default-code sponsor "is not a paymaster and is governed
    by the per-payer exposure rule alone" (Replacement and Eviction). That
    rule bounds the set by the sponsor's capital, which a drain recovers
    every block.
  - `hegota-testnet`'s cap on codeless payers refuses the flood at its
    second transaction (`ErrFramePaymasterBusy`).
  - Experiment 04's conclusion therefore holds for the two floods it named,
    and not for the pool. The tip order with the next slot's check still
    admits, for one transfer a block, transactions no block includes. What
    closes that is a count cap on default-code sponsors, which the EIP's
    text rules out.
- **For honest wallets, the next slot's check costs nothing measurable.**
  - Under the head's reading, the burst made nodes admit 771 transactions no
    block could include, 0.24 for every transaction given up. Builders
    skipped 6.
  - Under the next slot's reading those 3247 last resends were refused as
    `ErrFrameExpired`. Only 53 admissions remained, all at nodes that had
    not yet imported the latest block.
  - Under each order both readings included the same 4718 transactions.
  - The honest count is small for two reasons. A wallet's last resend before
    its deadline is the only one that falls in the window. And under the
    EIP's order a full pool refuses it, because it has the nearest deadline.

## What it does not show

- **Missed slots.** The next slot's check assumes the next block comes in the
  next slot. A missed slot makes the next block later, and the check then
  admits deadlines that block cannot meet. The model misses no slot.
- **A node that reads the clock.** The 53 admissions under the next slot's
  reading came from nodes behind the head. A node that took the next slot
  from its clock rather than from its head would admit none of them.
- **Another route for the drain.** The transfer goes through the public
  account-nonce pool here. Refusing it there, for instance by counting a
  sponsor's frame reservations against its own transactions, would not stop
  a transfer sent to a builder privately, which the model does not have.
- **Scale and bandwidth.** Section 2's pools hold 256, not 4096. The flood
  sent up to 137,716 transactions in ten minutes, and the model limits none
  of it.
- **The price of a block.** What the expiring flood paid under the next
  slot's check depends on the base fee before it began, which the light
  honest load keeps low: under the head's reading, where no block carried
  the flood, it was 199,074 wei when the flood ended.
