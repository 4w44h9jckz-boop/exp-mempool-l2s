# 18. Withheld keys

**Question.** A key publisher that does not release a key leaves its sealed
transaction committed and charged, and nothing runs. What does that do to
cheap sealed payments, against the share of publishers that withhold, when
their senders send them again sealed or in public, under each admission
policy? And what does experiment 07's escalating flood cost its adversary
when it withholds every key?

**Clauses exercised.** LU-12 and LU-13 (`docs/spec/06-lucid.md`): every
committed ticket is charged, and only a commitment whose key is released runs
and is refunded. LU-8's policies and the rest of experiment 07's clauses.
Decision record 0027 has the readings; no clause changes.

An encrypted mempool which waits for a key keeps the chain live by turning
encryption off: a threshold design's circuit breaker invalidates every
pending ciphertext after too many slots without keys.
EIP-8184 (Draft, read at `258836f9` and unchanged at `af80fc1c`) needs no
breaker. A withheld key leaves its commitment out of the next block's
decrypted transactions, and the block runs the rest. The sender has paid for
its ticket and its nonce has moved on. The EIP gives it two ways on: "In the
case of a single ST, the sender may itself also release the
`LucidKeyMessage`, even if it specified a key publisher other than itself"
(Key release), and "withheld transactions can be replaced by regular
transactions in block $n+1$" (Rationale).

## Setup

- **Experiment 07's network, payments and trades**:
  - 10 nodes, 8 peers each, a block every 12 s, gas limit 60,000,000, so a
    block commits at most 32 sealed transactions.
  - Payments bid no ToB fee, tolerate 31 commitments before them, and use
    100,000 gas. Each comes from a sender of its own, and is sent again to a
    random node after every block that does not commit it.
  - Trades arrive at 2 a slot.
- **Publishers**: each attempt at a payment names one of 10 key publishers
  at random, among those that have not withheld from its sender before. A
  share of them withhold every key they are named for.
- **Responses**: when the block that committed a withheld ticket reaches
  the node its sender sent it to, the sender sends the payment again to
  that node at its next nonce:
  - *sealed*, re-encrypted to another publisher;
  - *public*, as a regular transaction with the same gas and tip.
- **Self-release is not run.** A sender that releases its own key is a run
  in which nothing is withheld (decision record 0027).
- **Section 2**: experiment 07's section 4, 256-slot pools and the
  escalating flood, with its keys released or all withheld.
- Seed 1, 1200 s a run; rows are the payments first sent from second 240 to
  second 960.

## Run

```
python3 experiments/18-withheld-keys/run.py > experiments/18-withheld-keys/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

**Payments against withholding publishers** (section 1), under `any`;
delays from first sending to the block that runs the payment, in seconds;
lost is the mean wei a payment paid for tickets whose key was withheld, and
withheld is how many of a block's commitments ran nothing:

| a slot | withholding | response | sent | executed | public | delay p50 | p90 | p99 | max | attempts | lost, wei | commitments | withheld |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 0 of 10 | | 967 | 967 | 0 | 18.60 | 22.94 | 23.94 | 24.53 | 1.00 | 0.00 | 18.15 | 0.00 |
| 16 | 1 of 10 | sealed | 967 | 967 | 0 | 19.12 | 23.91 | 34.67 | 36.00 | 1.09 | 21177404597931.75 | 19.60 | 1.43 |
| 16 | 1 of 10 | public | 967 | 967 | 93 | 18.62 | 22.95 | 23.95 | 27.90 | 1.00 | 21433994026680.45 | 18.15 | 1.55 |
| 16 | 3 of 10 | sealed | 960 | 960 | 0 | 20.81 | 34.04 | 48.77 | 58.90 | 1.37 | 87343573367916.67 | 24.08 | 5.98 |
| 16 | 3 of 10 | public | 960 | 960 | 290 | 18.49 | 22.93 | 23.97 | 27.90 | 1.00 | 70550607603750.00 | 18.03 | 4.83 |
| 16 | 5 of 10 | sealed | 956 | 956 | 0 | 24.77 | 58.72 | 256.42 | 439.34 | 1.80 | 189898715160878.66 | 30.67 | 12.70 |
| 16 | 5 of 10 | public | 960 | 960 | 473 | 18.49 | 22.93 | 23.98 | 35.12 | 1.00 | 114956045551458.33 | 18.03 | 7.88 |
| 28 | 0 of 10 | | 1715 | 1715 | 0 | 18.53 | 23.89 | 81.47 | 152.69 | 1.00 | 0.00 | 30.52 | 0.00 |
| 28 | 1 of 10 | sealed | 1689 | 1689 | 0 | 19.79 | 41.34 | 331.89 | 678.48 | 1.09 | 21350133622261.69 | 32.00 | 2.57 |
| 28 | 1 of 10 | public | 1710 | 1710 | 157 | 18.80 | 23.98 | 86.04 | 155.25 | 1.00 | 21360980844210.53 | 30.42 | 2.58 |
| 28 | 3 of 10 | sealed | 1593 | 1593 | 0 | 23.16 | 437.45 | 812.96 | 918.56 | 1.37 | 79584592567357.19 | 32.00 | 8.07 |
| 28 | 3 of 10 | public | 1707 | 1707 | 498 | 18.82 | 23.66 | 84.05 | 141.90 | 1.00 | 67771443852138.26 | 30.37 | 8.23 |
| 28 | 5 of 10 | sealed | 1498 | 1239 | 0 | 28.75 | 489.00 | 854.56 | 920.86 | 1.48 | 137726638633778.38 | 32.00 | 13.38 |
| 28 | 5 of 10 | public | 1708 | 1708 | 813 | 18.62 | 23.86 | 70.74 | 174.80 | 1.00 | 109842100439812.64 | 30.50 | 13.57 |

Under `any`, the largest loss of one payment was 1471320394500000 wei at 16
a slot and 1709625582300000 at 28, both sealed with 5 of 10 withholding.

**The policies** (section 1), the 99th percentile of the delay, in seconds,
where they differ; every other row of `results.md` is the same under all
three to the hundredth, or within a second at the median:

| a slot | withholding | response | any | next-block | every-head |
| --- | --- | --- | --- | --- | --- |
| 16 | 3 of 10 | sealed | 48.77 | 47.14 | 47.14 |
| 28 | 1 of 10 | sealed | 331.89 | 561.32 | 561.32 |
| 28 | 3 of 10 | sealed | 812.96 | 790.66 | 801.33 |
| 28 | 5 of 10 | sealed | 854.56 | 837.36 | 828.93 |
| 28 | 1 of 10 | public | 86.04 | 72.44 | 72.44 |

At 28 a slot with 5 of 10 withholding and the sealed response, 1239 of 1498
payments ran by the end under `any`, 1212 of 1502 under `next-block` and
1213 of 1521 under `every-head`.

**A flood that withholds** (section 2), payments at 16 a slot:

| pool | flood keys | payments | executed | delay p90 | flood committed | paid, wei | per commitment, wei |
| --- | --- | --- | --- | --- | --- | --- | --- |
| any | released | 854 | 11 | 838.49 | 81 | 1470182951170642 | 18150406804575.83 |
| any | withheld | 854 | 11 | 875.97 | 81 | 81835240152814205 | 1010311606824866.75 |
| every-head | released | 854 | 493 | 807.96 | 69 | 1272782451917007 | 18446122491550.82 |
| every-head | withheld | 854 | 494 | 803.36 | 69 | 69732112505853321 | 1010610326171787.25 |
| any, unplaced | released | 967 | 967 | 22.94 | 81 | 1799000904238057 | 22209887706642.68 |
| any, unplaced | withheld | 967 | 967 | 22.94 | 81 | 82162927560203803 | 1014357130372886.50 |

## What it shows

1. **A withheld key stops one payment, not the chain.** Every block ran the
   commitments whose keys were released. At 16 payments a slot, below the
   ceiling, every payment was executed by the end of the run, under both
   responses and at every share of withholding publishers. Nothing in the
   protocol waited for a key, and nothing published a ciphertext's contents
   to keep going, which is what the threshold design's circuit breaker does.
2. **What the sender pays is the ticket.** A withheld ticket is charged in
   full and refunds nothing (LU-12, LU-13). Under `any` at 16 a slot, a
   payment lost a mean of 21177404597931.75 wei with 1 of 10 publishers
   withholding and 189898715160878.66 with 5 of 10, when it was sent again
   sealed. The most one payment lost there was 1471320394500000 wei. A payment
   bids no ToB fee, so what it loses is its gas at the base fee and its
   priority fee; a trade would lose its ToB fee as well.
3. **Sealed again, each withheld key costs a block, and its commitment.**
   - At 16 a slot the 99th percentile rose from 23.94 s with no withholding
     to 34.67 s, 48.77 s and 256.42 s with 1, 3 and 5 of 10, and a payment
     needed 1.09, 1.37 and 1.80 tickets.
   - Commitments a block rose with them, from 18.15 to 30.67 at 5 of 10,
     of which 12.70 ran nothing: a withheld commitment takes a place among
     the 32 that a block makes.
4. **Near the ceiling the wasted places are what hurts.**
   - At 28 a slot every block made 32.00 commitments under the sealed
     response whenever a publisher withheld, against 30.52 with none.
   - With 1 of 10 withholding every payment ran, but the 99th percentile
     rose from 81.47 s to 331.89 s.
   - With 5 of 10, under `any`, 13.38 of a block's 32 commitments ran
     nothing, the 90th percentile was 489.00 s, and 1239 of 1498 payments
     had run by the end.
5. **Sent again in public, a payment keeps its delay and loses its
   encryption.**
   - At 16 a slot the public rows' 99th percentile stayed between 23.95 s
     and 23.98 s, and at 28 a slot between 70.74 s and 86.04 s, where no
     withholding gave 81.47 s.
   - The payments that went public were about the withholding share: 93,
     290 and 473 of about 960 at 16 a slot, and 813 of 1708 at 28 a slot
     with 5 of 10.
   - It also loses less, one ticket at most: 114956045551458.33 wei a
     payment against 189898715160878.66 sealed, at 16 a slot with 5 of 10.
   - This is the circuit breaker's trade, encryption given up to stay live,
     made by each sender for its own payment rather than by the protocol for
     every pending one.
6. **The policy matters less than the withholding.**
   - At 16 a slot, of the rows with withholding, the three policies differ
     only in the sealed rows at 3 and 5 of 10: the 99th percentile was
     48.77 s under `any` against 47.14 s under the others at 3 of 10, and
     the same 256.42 s at 5 of 10.
   - At 28 a slot no policy was best at every share. With 1 of 10, `any`
     gave 331.89 s at the 99th percentile and the other two 561.32 s; with
     5 of 10, `every-head` gave 828.93 s and `any` 854.56 s.
   - None of them can tell a ticket whose key will be withheld from one
     whose key will come, so none of them can save the place it takes.
7. **A flood that withholds pays the whole ToB fee and does the same
   damage.**
   - Under `any`, experiment 07's escalating flood cost 18150406804575.83
     wei a commitment with its keys released and 1010311606824866.75 with
     them withheld, since the reveal refunds 127/128 of the ToB fee.
   - Payments fared the same either way: 11 of 854 ran under `any`, 493
     and 494 under `every-head`, and all 967 under `unplaced`.
   - The flood's harm comes from its place in the commitment order, which a
     withheld key does not take back, so withholding prices the flood and
     does not stop it.

**Answer to the question.** LUCID needs no circuit breaker: a withheld key
costs its sender a ticket and a block, and costs every sealed sender a
commitment place. Below the ceiling the sealed response pays for withholding
in delay alone. Near it, the wasted places leave payments unexecuted, and the
public response is the way through that keeps the delay, for the share that
was withheld.

## What it does not show

- **Self-release.** It removes the publisher from a single payment's path
  at the price of being online in the slot of the commitment, which the
  model cannot price. A bundle's keys are the publisher's alone.
- **Selective withholding.** The EIP prices a publisher, or a sender, that
  releases a trade's key only when the trade pays (Rationale, "Probabilistic
  front-running"). A payment is never worth that, and it is not modelled.
- **Bundles and sponsorship.** A key publisher can carry the penalty for
  its own non-reveal with a sponsor transaction in a bundle (Rationale, "Key
  publisher liability for non-reveal"). Not modelled, as in experiment 07.
- **A publisher that withholds from some senders only.** Here a publisher
  that withholds withholds everything, so a sender that avoids it is
  safe; one that withholds only some senders' keys looks honest to the rest.
- **What the public response gives away.** A payment sent in public is
  exposed to the ordering and filtering the sealed path exists to avoid;
  the model counts it, and prices none of that.
