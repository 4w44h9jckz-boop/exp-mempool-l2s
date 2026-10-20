# 01. The account-nonce pool

Version 1, 2026-10-07.

The pool every Ethereum node runs for transaction types 0, 1, 2 and 4, written
down as clauses. The reference is go-ethereum's `legacypool` at commit
`93d78a01` (2026-10-06): `core/txpool/validation.go`,
`core/txpool/legacypool/legacypool.go`, `list.go`, `queue.go`, `noncer.go` and
`core/txpool/reserver.go`. Function names below are that code's. The pool
holds two sets per sender: **pending**, transactions executable now in an
unbroken nonce run from the account nonce, and **queued**, transactions that
are not, because of a nonce gap or because they have not been promoted yet.

Background on why the rules exist is not restated here.

## Profile

**NP-1. Parameters.** The `geth` profile is go-ethereum's `DefaultConfig` with
the Prague and Osaka rules active and Amsterdam not:

| Parameter | `geth` | Meaning |
| --- | --- | --- |
| `price_limit` | 1 | minimum `tip` admitted, in wei |
| `price_bump` | 10 | percent a replacement must raise both fee fields |
| `account_slots` | 16 | pending transactions per sender that truncation never touches |
| `global_slots` | 5120 | pending transactions across all senders before truncation ($4096 + 1024$) |
| `account_queue` | 64 | queued transactions per sender |
| `global_queue` | 1024 | queued transactions across all senders |
| `lifetime` | 10800 s | how long a sender may sit in the queue without a heartbeat |
| `eviction_interval` | 60 s | how often lifetime eviction runs |
| `max_size` | 131072 | `txMaxSize`, four slots of 32 KiB |
| `slot_size` | 32768 | `txSlotSize` |
| `max_tx_gas` | 16777216 | the EIP-7825 cap, active from Osaka until Amsterdam |
| `max_initcode_size` | 49152 | EIP-3860 |
| `floor_cost_per_token` | 10 | EIP-7623 |

A transaction occupies $\lceil \mathit{size} / \mathit{slot\_size} \rceil$
slots (`numSlots`).

## Errors

The codes are go-ethereum's error variable names, so a result can be compared
with a client's answer.

| Code | Raised by |
| --- | --- |
| `ErrAlreadyKnown` | NP-2 |
| `ErrTxTypeNotSupported`, `ErrOversizedData`, `ErrMaxInitCodeSizeExceeded`, `ErrGasLimitTooHigh`, `ErrNegativeValue`, `ErrGasLimit`, `ErrTipAboveFeeCap`, `ErrInvalidSender`, `ErrNonceMax`, `ErrIntrinsicGas`, `ErrFloorDataGas`, `ErrTxGasPriceTooLow`, `ErrEmptyAuthList` | NP-3 |
| `ErrNonceTooLow`, `ErrInsufficientFunds` | NP-4, NP-5 |
| `ErrOutOfOrderTxFromDelegated`, `ErrInflightTxLimitReached` | NP-6 |
| `ErrAuthorityReserved` | NP-7 |
| `ErrAlreadyReserved` | NP-8 |
| `ErrUnderpriced`, `ErrTxPoolOverflow`, `ErrFutureReplacePending` | NP-9 |
| `ErrReplaceUnderpriced` | NP-11, NP-12 |

`ErrEmptyAuthList` names an error go-ethereum raises without a variable
("set code tx must have at least one authorization tuple").

## Admission

**NP-2. Batches and duplicates.** `add` processes its list in order. A
transaction whose hash the pool already holds MUST be answered
`ErrAlreadyKnown` without further checks, including when the copy it
duplicates arrived earlier in the same batch. After the whole batch has been
processed the pool MUST run promotion (NP-14) for every sender that had a
transaction admitted without replacing another; a sender whose only admitted
transaction replaced one is not promoted by this batch. **Source:** `Add`,
`addTxsLocked`, `add`; promotion runs in `runReorg`.

**NP-3. Stateless checks.** Before reading any state the pool MUST apply these
checks in this order and return the first that fails:

1. the type is 0, 1, 2 or 4, else `ErrTxTypeNotSupported` (blob transactions
   belong to a different pool, which the model does not have);
2. `size` $\leq$ `max_size`, else `ErrOversizedData`;
3. if `to` is absent, `data_size` $\leq$ `max_initcode_size`, else
   `ErrMaxInitCodeSizeExceeded`;
4. `gas` $\leq$ `max_tx_gas`, else `ErrGasLimitTooHigh`;
5. `value` $\geq 0$, else `ErrNegativeValue`;
6. `gas` $\leq$ the head's `gas_limit`, else `ErrGasLimit`;
7. `max_fee` $\geq$ `tip`, else `ErrTipAboveFeeCap`;
8. a sender is recoverable (`valid_signature`), else `ErrInvalidSender`;
9. `nonce` $< 2^{64} - 1$, else `ErrNonceMax`;
10. `gas` $\geq g_{\text{intr}}$ (FEE-3), else `ErrIntrinsicGas`;
11. `gas` $\geq g_{\text{floor}}$ (FEE-3), else `ErrFloorDataGas`;
12. `tip` $\geq$ `price_limit`, else `ErrTxGasPriceTooLow`;
13. a type 4 transaction has at least one authority, else `ErrEmptyAuthList`.

**Source:** `ValidateTxBasics`, `txpool.ValidateTransaction`.

**NP-4. Nonce.** If `nonce` is below the sender's account nonce in the head
state, the pool MUST return `ErrNonceTooLow`. A nonce above it is admitted:
gaps go to the queue. **Source:** `txpool.ValidateTransactionWithState`.

**NP-5. Balance.** Let $B$ be the sender's balance in the head state and $S$
the summed cost of the sender's **pending** transactions (queued ones do not
count). The pool MUST return `ErrInsufficientFunds` if $B < \mathit{cost}$;
or, when a pending transaction $p$ with the same nonce exists, if
$B < S + \mathit{cost} - \mathit{cost}(p)$; or, otherwise, if
$B < S + \mathit{cost}$. **Source:** `txpool.ValidateTransactionWithState`
with `ExistingExpenditure` and `ExistingCost` from `validateTx`.

**NP-6. Delegated senders.** A sender is *delegated* when its code in the head
state is non-empty, or when any transaction in the pool lists it among its
`authorities`. For a delegated sender the pool MUST:

- if the sender has no pending transactions, return
  `ErrOutOfOrderTxFromDelegated` unless `nonce` equals the sender's pending
  nonce (NP-15);
- if it has pending transactions, return `ErrInflightTxLimitReached` unless a
  pending transaction with the same nonce exists, in which case the new
  transaction is a replacement candidate.

**Source:** `checkDelegationLimit`.

**NP-7. Authorities.** For a type 4 transaction the pool MUST return
`ErrAuthorityReserved` if any authority has more than one transaction in this
pool (pending and queued together), or is held by a different subpool
(NP-8). **Source:** `validateAuth`.

**NP-8. Subpool reservation.** A sender's transactions live in at most one
subpool at a time. When a transaction from a sender with no pending or queued
transaction passes NP-3 to NP-7, the pool MUST take the sender in the shared
reservation tracker and return `ErrAlreadyReserved` if another subpool holds
it. The pool MUST release the sender when its last transaction leaves, and
when the transaction that took the reservation is then rejected. **Source:**
`add`, `removeTx`, `ReservationHandle`.

**NP-9. A full pool.** The pool is full for a transaction when its occupied
slots plus the transaction's exceed `global_slots` + `global_queue`. For a
full pool the pool MUST, in order:

1. return `ErrUnderpriced` if the transaction is underpriced (NP-10);
2. return `ErrTxPoolOverflow` if more than $\lfloor \mathit{global\_slots} / 4 \rfloor$
   transactions have been dropped by this rule since the last promotion run;
3. choose transactions to drop with `Discard` (NP-10) for the missing slots,
   returning `ErrTxPoolOverflow` if it cannot free enough;
4. if the transaction is *gapped* (below) and any chosen transaction is
   pending, put the chosen ones back and return `ErrFutureReplacePending`;
5. otherwise remove the chosen transactions (NP-17). Towards the limit of
   step 2, a removed pending transaction counts one plus the transactions it
   demotes, and a removed queued transaction counts zero. The count restarts
   at zero after every promotion run (NP-2, NP-19).

A transaction is gapped when its nonce exceeds the sender's pending nonce
$n$ and the queue does not hold every nonce from $n$ up to it. **Source:**
`add`, `isGapped`.

**NP-10. The price list.** The pool keeps two heaps over its transactions:
**urgent**, ordered by effective tip at the pending base fee, then `max_fee`,
then `tip`; and **floating**, ordered by `max_fee`, then `tip`. In both, among
equal prices the higher nonce is cheaper. A new or replacing transaction goes
into urgent. Removed transactions are left in place as stale entries until
they reach the top of a heap; when the number of stale entries exceeds a
quarter of the entries in both heaps, and whenever the pending base fee
changes, the pool rebuilds: every transaction goes into urgent and the
cheapest $\lfloor n / 5 \rfloor$ by urgent order move to floating.

- A transaction is **underpriced** when at least one heap is non-empty and,
  for each non-empty heap, the cheapest live entry is not cheaper than it
  (equal counts as underpriced).
- **Discard** of $k$ slots repeats: if
  $\lvert \mathit{urgent} \rvert > 4 \lvert \mathit{floating} \rvert$, move the
  cheapest live urgent entry to floating; otherwise drop the cheapest live
  floating entry and count its slots; until $k$ slots are counted or both heaps
  are empty. If fewer than $k$ were found, the dropped entries go back into
  urgent and Discard fails.

**Source:** `list.go`, `priceHeap`, `pricedList`.

**NP-11. Replacing a pending transaction.** If the sender has a pending
transaction $p$ with the same nonce, the new transaction $t$ MUST replace it
if and only if

$$
t.\mathit{max\_fee} > p.\mathit{max\_fee},\;
t.\mathit{tip} > p.\mathit{tip},\;
t.\mathit{max\_fee} \geq \left\lfloor \tfrac{(100 + \beta)\, p.\mathit{max\_fee}}{100} \right\rfloor,\;
t.\mathit{tip} \geq \left\lfloor \tfrac{(100 + \beta)\, p.\mathit{tip}}{100} \right\rfloor
$$

with $\beta$ = `price_bump`, and MUST return `ErrReplaceUnderpriced`
otherwise. A replacement takes $p$'s place in pending directly and refreshes
the sender's queue heartbeat if one exists (NP-18). **Source:** `add`,
`list.Add`.

**NP-12. Queueing.** Any other admitted transaction MUST go to the sender's
queue. A queued transaction with the same nonce is replaced under the rule of
NP-11, else `ErrReplaceUnderpriced`. The sender's heartbeat is set to `now` if
the sender has none. **Source:** `enqueueTx`, `queue.add`.

## Promotion and limits

**NP-13. Ordering inside a sender.** Pending is *strict*: removing a pending
transaction moves every pending transaction of the same sender with a higher
nonce back to the queue. The queue is not strict. **Source:** `newList`,
`list.Remove`, `list.Filter`.

**NP-14. Promotion.** For each sender to promote, the pool MUST, in order:
drop queued transactions whose nonce is below the account nonce; drop queued
transactions whose cost exceeds the sender's balance or whose gas exceeds the
head's gas limit (each compared on its own: the cumulative rule of NP-5 is an
admission rule only); move to pending the queued run of consecutive nonces
that starts at or below the sender's pending nonce, each move replacing a
pending transaction of the same nonce only under NP-11 and setting the pending
nonce to one past it; drop the highest-nonce queued transactions beyond
`account_queue`. After promotion the pool MUST apply NP-16's truncations.
**Source:** `promoteExecutables`, `queue.promoteExecutables`, `promoteTx`.

**NP-15. The pending nonce.** The pool tracks a pending nonce per sender: the
next nonce after the sender's pending run. It defaults to the account nonce in
the head state, is set by promotion, is lowered (never raised) when a pending
transaction is removed, and is rebuilt on every reset as one past each
sender's highest pending nonce, falling back to the account nonce for senders
with nothing pending. **Source:** `noncer`, `runReorg`.

**NP-16. Truncation.** After every promotion run:

- **Pending.** If the pending transactions outnumber `global_slots`, the pool
  takes the senders with more than `account_slots` pending, largest first, and
  adds them one at a time to an offender list. Each time one is added, while
  the total is above `global_slots` and the previous offender has more pending
  than the newest, it removes the highest-nonce pending transaction from every
  offender except the newest, one round at a time. If the total is still above
  `global_slots` once the list is complete, it removes the highest-nonce
  pending transaction from every offender, round by round, while the total is
  above `global_slots` and the last offender holds more than `account_slots`.
  Each removal lowers the sender's pending nonce to the removed nonce. The
  totals count transactions, not slots.
- **Queue.** If the queued transactions outnumber `global_queue`, the pool
  takes senders in order of oldest heartbeat first and drops all of a sender's
  queued transactions when they do not exceed the overflow, or else its
  highest-nonce ones until the overflow is gone.

**Source:** `truncatePending`, `queue.truncate`.

**NP-17. Removal.** Removing a transaction (eviction, `Discard`, lifetime)
MUST remove it from pending or queue; removing a pending one demotes the
sender's higher pending nonces to the queue (NP-13) and lowers the pending
nonce. A sender whose queue empties loses its heartbeat. **Source:**
`removeTx`, `queue.remove`.

**NP-18. Lifetime.** Every `eviction_interval` seconds the pool MUST remove all
queued transactions of every sender whose heartbeat is more than `lifetime`
seconds old. A heartbeat is set when a sender's queue is created, and is
refreshed (only if it exists) when one of its transactions is promoted or a
pending transaction is replaced. **Source:** `loop`, `queue.evictList`,
`queue.bump`.

*Interpretation:* passes fall due at every multiple of `eviction_interval`
after the time the pool was created. Every operation, `add`, `reset` and
`tick` alike, first runs the passes that fell due at or before its `now`, in
order, each evaluated at its own time; `tick(now)` does only that. This is
go-ethereum's ticker with the clock made explicit. Decision record 0002.

## Head changes

**NP-19. Reset.** On `reset(head, state)` the pool MUST, in order:

1. adopt `head` and `state`, and reset every pending nonce to the account
   nonce;
2. run promotion (NP-14) for every sender with queued transactions;
3. for every sender with pending transactions: drop those whose nonce is below
   the account nonce; drop those whose cost exceeds the balance or whose gas
   exceeds the gas limit, demoting to the queue every pending transaction with
   a higher nonce than the lowest dropped (NP-13); and if the lowest remaining
   pending nonce is not the account nonce, demote them all;
4. set the pending base fee from FEE-1 and rebuild the price list;
5. rebuild the pending nonces (NP-15);
6. apply the truncations of NP-16.

**Source:** `runReorg`, `reset`, `demoteUnexecutables`.

*Not modelled:* reinjection of transactions from blocks dropped by a reorg
(the model only moves forward), dropping transactions above `max_tx_gas` at the
Osaka boundary, local transactions and the journal.

## What builders see

**NP-20. The pending view.** For a builder with minimum tip $m$ at base fee $b$
the pool MUST offer, per sender, the pending transactions in nonce order cut
before the first one whose effective tip at $b$ is below $m$. **Source:**
`Pending`.
