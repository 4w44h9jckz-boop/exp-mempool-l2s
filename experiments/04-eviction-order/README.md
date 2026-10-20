# 04. Eviction order

**Question.** When a pool is full, what can transactions that no builder will
ever include push out of it? What does that cost whoever sends them? And does
EIP-8141's order, the nearest deadline before the lowest tip, make this worse
than go-ethereum's order by price?

**Clauses exercised.**

- FP-14, version 3, with its `evict_first` variant (decision record 0010).
- FP-3: no floor on the fee cap.
- FP-8: a deadline is checked against the head's timestamp.
- FP-15: expired transactions leave at the next head.
- FP-16 and BB-1: builders skip tips below their minimum.
- NP-9 and NP-10: the account-nonce pool's full-pool rule and its price heaps.

EIP-8141 asks a node that has reached its limits to evict "first transactions
already invalid against the current head, then transactions with the nearest
expiry deadline, then transactions with the lowest effective priority fee"
(Replacement and Eviction, at `258836f9`). So any deadline ranks below any
price: a transaction with a deadline goes first, whatever it pays. The EIP
gives no reason for this order.

go-ethereum's pool works by price instead. A newcomer to a full pool is
refused unless it is priced above the cheapest transaction held (NP-9, NP-10).
The plan's item 4 asks what each order lets a flood displace, and at what cost.

## Setup

- **Section 1: one pool, no network.** A pool at a pending base fee of 1 gwei
  is filled to its capacity with honest transactions, one sender each. The
  capacity is 4096 frame transactions, or 6144 slots in the account-nonce
  pool. Three classes:
  - *pays*: priced as wallets price, with no deadline;
  - *deadline*: the same, with a deadline 600 s out (frame pool only);
  - *stranded*: a fee cap below the base fee.

  Then as many again of the adversary's transactions arrive, one at a time.
- **The adversary's transactions.** No builder includes any of them. They
  come in three kinds:
  - *free*: a fee cap and tip of 1 wei;
  - *sub-minimum*: a tip one wei below the builders' minimum of 0.001 gwei;
  - *expiring*: a deadline at the head's timestamp, which FP-8 admits and the
    next block cannot meet, at a tip of 10 gwei.

  Each has a default-code sender of its own, and a canonical paymaster
  instance pays for all of them. No profile caps that paymaster
  (experiment 03).
- **Pools.**
  - `geth` (NP-9);
  - `eip-8141` and `hegota-testnet` (FP-14), which order eviction alike;
  - `eip-8141` with `evict_first` set to `tip`. This puts the lowest effective
    tip first and uses the deadline only to break ties. It is a proposal, not
    the EIP (decision record 0010).
- **Sections 2 and 3: the network.** It is that of experiments 01 to 03:
  - 10 nodes with 8 peers each;
  - link latency 20 to 100 ms, and go-ethereum's gossip;
  - a block every 12 s from a rotating proposer, which the other nodes
    import 0.1 to 1.0 s later;
  - gas limit 2,100,000, genesis base fee 1 gwei;
  - builders' minimum tip 0.001 gwei (BB-1).
- **Honest wallets.** They pay for themselves with default code and send
  1500 frame transactions an hour. Half carry a deadline 10 minutes after
  first sending. Each wallet has one transaction in flight. It sends it again
  to a random node after every block that leaves it out, and gives it up once
  its deadline has passed.
- **Section 2: the free flood.** From minute 10 to minute 30, the adversary
  keeps every node's frame pool full of *free* transactions. It sends to each
  node directly at the start and in the same instant the node imports each
  block: enough to fill the pool and 16 more, so that anything that slipped
  in is evicted. This is the strongest adversary (decision record 0010).
- **Section 3: an honest burst.** There is no adversary. For fifteen
  minutes, 45,000 transactions an hour more arrive from 15,000 other wallets
  of the same kind, until the backlog fills every pool.
- Seed 1: 8 one-pool runs and 6 network runs, about three minutes of wall
  clock.

## Run

```
python3 experiments/04-eviction-order/run.py > experiments/04-eviction-order/results.md
```

## Results

From [results.md](results.md).

**Section 1, at one pool.** "Out" is how many of each honest class are no
longer held.

| pool | adversary | capacity | admitted | out: pays | out: deadline | out: stranded | refused as |
| --- | --- | --- | --- | --- | --- | --- | --- |
| account-nonce pool, `geth` (NP-9) | free | 6144 | 0 | 0 | n/a | 0 | ErrUnderpriced |
| account-nonce pool, `geth` (NP-9) | sub-minimum | 6144 | 3072 | 0 | n/a | 3072 | ErrUnderpriced |
| frame pool, `eip-8141` (FP-14, expiry first) | free | 4096 | 1365 | 0 | 1365 | 0 | ErrTxPoolOverflow |
| frame pool, `eip-8141` (FP-14, expiry first) | sub-minimum | 4096 | 2730 | 0 | 1365 | 1365 | ErrTxPoolOverflow |
| frame pool, `eip-8141` (FP-14, expiry first) | expiring | 4096 | 0 | 0 | 0 | 0 | ErrTxPoolOverflow |
| frame pool, `eip-8141` with `evict_first` `tip` | free | 4096 | 0 | 0 | 0 | 0 | ErrTxPoolOverflow |
| frame pool, `eip-8141` with `evict_first` `tip` | sub-minimum | 4096 | 1365 | 0 | 0 | 1365 | ErrTxPoolOverflow |
| frame pool, `eip-8141` with `evict_first` `tip` | expiring | 4096 | 4096 | 1366 | 1365 | 1365 | none |

**Section 2, the free flood on the network.** A subset of the columns. Rows
are the transactions first sent during the flood. "Overflow" is
`ErrTxPoolOverflow` answers per transaction; "evicted" is evictions per
transaction, across nodes.

| profile | flood | class | asked | landed in the flood | landed | gave up | delay p50 | overflow | evicted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | none | pays | 251 | 250 | 251 | 0 | 5.93 | 0.00 | 0.00 |
| eip-8141 | none | deadline | 255 | 250 | 255 | 0 | 6.05 | 0.00 | 0.00 |
| eip-8141 | free | pays | 245 | 240 | 245 | 0 | 5.52 | 0.00 | 0.00 |
| eip-8141 | free | deadline | 241 | 0 | 37 | 204 | 390.64 | 62.07 | 13.83 |
| hegota-testnet | free | deadline | 241 | 0 | 37 | 204 | 390.64 | 62.07 | 13.83 |
| eip-8141, tip first | free | pays | 251 | 250 | 251 | 0 | 5.93 | 0.00 | 0.00 |
| eip-8141, tip first | free | deadline | 255 | 250 | 255 | 0 | 6.05 | 0.00 | 0.00 |

What the flood cost under `eip-8141`, and `hegota-testnet` alike:

| transactions | sent | admitted | held per node | held at the end | reserved, wei | at 1 gwei | included |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4112 | 58550 | 43360 | 4092.00 | 4088.90 | 197696796 | 197696796000000000 | 0 |

**Section 3, the honest burst.** The burst is 5.34 times what blocks hold of
transactions without a deadline.
Rows are the transactions first sent during it. Most held is 4096 under both
orders.

| profile | class | asked | landed in the burst | landed | gave up | delay p50 | overflow | evicted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | pays | 4494 | 1069 | 2288 | 0 | 103.51 | 0.00 | 0.00 |
| eip-8141 | deadline | 4557 | 1077 | 1310 | 3247 | 8.19 | 11.05 | 12.05 |
| eip-8141, tip first | pays | 4494 | 1069 | 2288 | 0 | 103.51 | 6.05 | 8.13 |
| eip-8141, tip first | deadline | 4557 | 1077 | 1310 | 3247 | 8.19 | 2.28 | 4.33 |

What each order evicted over the burst run:

| profile | evicted | with a deadline | tip p50, gwei | highest tip, gwei | included later |
| --- | --- | --- | --- | --- | --- |
| eip-8141 | 2809 | 2809 | 1.07 | 2.39 | 0 |
| eip-8141, tip first | 2183 | 970 | 0.66 | 1.83 | 0 |

## What it shows

- **Under the EIP's order, a deadline is a liability in a full pool.**
  - 1365 *free* transactions, at a fee cap and tip of 1 wei, push all 1365
    transactions with a deadline out of a full frame pool, and nothing else.
  - The same flood is refused as `ErrUnderpriced` by the account-nonce pool.
  - A *sub-minimum* flood pushes out the deadline transactions and the
    stranded ones too.
  - In every case the honest transactions that leave tip up to 3 gwei,
    while the transactions that replace them pay nothing.
- **Ordering by price limits a flood to what builders would not include
  now.**
  - In the account-nonce pool, the sub-minimum flood pushes out all 3072
    stranded transactions and none that pay. The tip-first variant does the
    same with the frame pool's 1365 stranded ones.
  - A stranded transaction is includable once the base fee falls, so price
    order does not protect the backlog that experiment 00 found after a
    burst. It does protect every transaction a builder would include now.
- **On a network, a free flood keeps every transaction with a deadline out
  for as long as it lasts.**
  - Under `eip-8141`, none of the 241 deadline transactions first sent
    during the flood landed before it ended.
  - 204 gave up at their deadlines. The 37 that landed did so after the
    flood, at a median delay of 390.64 s.
  - On average each was refused 62.07 times as `ErrTxPoolOverflow`. It was
    also evicted 13.83 times, each time after getting into a pool in the
    instant after a block, before the flood refilled it.
  - Transactions without a deadline were untouched: 240 of 245 landed during
    the flood, at a median delay of 5.52 s against 5.93 s without one.
  - `hegota-testnet` gives the same figures.
- **The flood costs nothing, and outlives itself.**
  - No flood transaction was ever included, so it paid no gas. What it
    reserves against its paymaster, 197,696,796 wei at a node, comes back
    when the transactions leave.
  - At a fee cap of 1 gwei it would reserve 197,696,796,000,000,000 wei,
    about 0.2 ether. With a 1-wei tip it would still be below the builders'
    minimum, so a floor on the fee cap at the base fee would not stop it.
  - Half an hour after the flood stopped, every node still held 4,088.90 of
    its transactions on average. Nothing in FP-15 removes a valid transaction
    that is never included, and the frame pool has no lifetime (MATCHA's MA-8
    has one).
  - A pool left this full admits deadline transactions only through the slots
    that inclusions free.
- **Putting the tip first closes the free flood.** Under the variant, the
  same flood changes nothing: both classes land exactly as they do without
  it.
- **It also opens an expiring flood.**
  - Under the variant, 4096 *expiring* transactions push out every honest
    transaction in section 1: 1366, 1365 and 1365. Under the EIP's order the
    same transactions are refused, because their deadline is the nearest.
  - A deadline at the head's timestamp passes FP-8, and the next block
    cannot meet it. The transaction is never included, and the adversary
    sends a fresh one every block, again at no cost.
  - So the EIP's order guards against exactly this flood.
  - Closing both floods needs the tip order and an admission check against
    the next block's timestamp. That is FP-15's open question and
    the plan's item 5.
- **Honest overload does not care which order is used.**
  - The burst fills every pool to 4096. Both orders then include the same
    4,718 transactions.
  - The EIP's order evicts 2809 transactions, every one with a deadline, at a
    median tip of 1.07 gwei and at most 2.39. The tip-first order evicts 2183,
    970 of them with a deadline, at a median of 0.66 gwei and at most 1.83.
  - Under either order, no evicted transaction was ever included.
  - Why: honest deadlines are a fixed time after sending, so the nearest
    deadline belongs to the oldest transaction still waiting. In a backlog
    ordered by tip, that is a cheap one. And wallets that resend after every
    block bring back whatever was evicted.
  - The deadline transactions that did not land (3247 of 4557) gave up
    because the backlog outlasted their ten minutes. That happens under
    either order.

## What it does not show

- **A slower adversary.** Here the adversary refills each pool in the instant
  the pool imports a block. One that arrives a link's latency later leaves a
  window after each block in which deadline transactions get in, until its
  surplus evicts them.
- **Wallets that do not resend.** For them an eviction loses the transaction
  for good, and which class loses depends on the order. Section 3's identity
  between the orders rests on resending.
- **Deadlines of different lengths.** Every honest deadline here is ten
  minutes. A transaction with a short deadline and a high tip is where the
  two orders part under honest load. Section 1 shows the mechanism, not how
  often it happens.
- **The expiring flood on a network.** It is measured at one pool only,
  because it must be resent to every node at every block (decision record
  0010). It belongs with the expiry timestamp question.
- **A fee or tip floor.** A floor on the fee cap at the base fee only scales
  up the free flood's capital. A floor on the tip at the builders' minimum
  would make every admitted transaction includable whenever blocks have room.
  Neither is measured.
- **Bandwidth.** The flood sends 58,550 transactions in twenty minutes, to
  ten nodes, and the model limits none of it.
- **Time.** Within the hour, 2288 of section 3's 4494 burst transactions
  without a deadline landed. The rest are stranded behind a base fee that
  the burst raised, the backlog of experiment 00.
