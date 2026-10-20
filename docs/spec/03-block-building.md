# 03. Block building and the state transition the model needs

Version 4, 2026-10-13. Version 1 applied every authorization of a set code
transaction, version 2 counted a block's gas in one dimension only, and
version 3 had no transaction that reverts; see the version notes at the
end.

A pool is only half of a mempool experiment: transactions leave it by being
included, and a block changes the state the pool validates against. This
document specifies how a builder takes transactions from the pools, following
go-ethereum's miner, and the minimal, non-consensus state transition that
moves the fields of MD-2 the pools depend on. It is not an EVM and makes no
claim about consensus validity beyond those fields.

A block counts its gas under one of two rules: `one`, a single sum against
the gas limit, which is the default and what BB-3 and BB-4 state; and `two`,
EIP-8037's execution and state dimensions, which BB-6 states as a change to
both. A transaction whose execution reverts is included and pays for the gas
it used (BB-5), unless its builder drops what would revert (BB-7).

**BB-1. Candidates.** A builder with minimum tip $m$ (go-ethereum's miner
`GasPrice`, 1,000,000 wei by default) building on a head with pending base
fee $b$ takes the account-nonce pool's pending view (NP-20) and the frame
pool's pending view (FP-16) at $m$ and $b$. **Source:** go-ethereum
`miner/worker.go`, `fillTransactions`.

**BB-2. Order.** The builder MUST order candidates by price and nonce: it keeps
one head per account-nonce sender (its lowest-nonce candidate) and treats each
frame transaction as a head of its own, and repeatedly takes the head with the
highest effective tip at $b$, ties going to the one received earlier. A sender
whose head has `max_fee` below $b$ is left out entirely. **Source:**
go-ethereum `core/txpool/txorder/ordering.go`, `TransactionsByPriceAndNonce`.

**BB-3. The loop.** While at least 21,000 gas is left in the block, the
builder MUST look at the best head and:

- if its gas limit (`gas`, or `max_gas` for a frame transaction) exceeds the
  gas left, drop that head and the rest of its sender's candidates;
- otherwise apply it (BB-5): on success, or on `ErrNonceTooLow`, replace the
  head with the sender's next candidate; on any other error, drop the head and
  the rest of its sender's candidates.

It stops when no head is left. **Source:** `miner/worker.go`,
`commitTransactions`.

**BB-4. The header.** The new head has `number` one above its parent,
`timestamp` the parent's plus the slot time (12 seconds by default),
the parent's `gas_limit`, `base_fee` from FEE-1 and `gas_used` the sum of its
transactions' `gas_used`.

**BB-5. Applying a transaction.** At base fee $b$, with price
$p = b + \min(\mathit{tip}, \mathit{max\_fee} - b)$ and a coinbase:

- An account-nonce transaction fails with `ErrNonceTooLow` or
  `ErrNonceTooHigh` unless `nonce` equals the sender's nonce, with
  `ErrFeeCapTooLow` if $\mathit{max\_fee} < b$, and with
  `ErrInsufficientFunds` if the sender's balance is below its `cost` (MD-5).
  Otherwise the sender's nonce increases by one. Then, for type 4, each
  authorization in turn whose authority's code is empty or a delegation
  indicator (MD-2), and whose nonce, when it carries one (MD-5), equals its
  authority's nonce at that point, sets that code to the delegation
  indicator for `delegate` and increases that nonce by one; any other
  authorization is skipped, and the transaction still applies. Then it
  *executes*, against the state at that point: `value` moves from the
  sender to `to`; each pull (MD-5) in turn moves its amount from its account
  to `to` if that account's balance covers it, and is otherwise skipped if
  `atomic` is false; each pay in turn moves its amount from `to` to its
  account; and `writes` are applied, with RR-3's root writes of
  `08-recent-roots.md` after them. The execution *reverts* if a pull is
  not covered while `atomic` is true, or if `to`'s balance does not cover a
  pay: then none of it applies, and the state is as it was before the
  execution, the sender's nonce and the authorizations kept. With $u$ its
  `revert_gas_used` if it reverted and its `gas_used` otherwise, the
  transaction applies either way: the sender pays $u \cdot p$, the coinbase
  receives $u \cdot (p - b)$, and BB-4 and BB-6 count $u$ as its gas used.
  **Source** for the authorizations: EIP-7702 at
  `258836f9`, Behavior, which processes the list "after the sender's nonce
  is incremented", steps 5, 6, 8 and 9, and "If any step above fails,
  immediately stop processing the tuple and continue to the next tuple in
  the list". **Source** for a revert: go-ethereum at `93d78a01`,
  `core/state_transition.go`, `execute` ("vm errors do not effect
  consensus": the transaction pays for `gasUsed` and its coinbase fee
  whatever the error) and `core/state_processor.go`, `MakeReceipt` (a failed
  result is `ReceiptStatusFailed`, and the transaction is in the block).
- A frame transaction fails as FP-7 would, with `ErrFeeCapTooLow` if
  $\mathit{max\_fee} < b$, with `ErrFrameExpired` if its deadline is below the
  new block's timestamp, and as FP-8 would if its prefix no longer approves
  against the state at that point in the block. Otherwise every sequence in
  `nonce_keys` increases by one; the payer pays $\mathit{gas\_used} \cdot p$;
  the coinbase receives $\mathit{gas\_used} \cdot (p - b)$; a deploy frame
  installs its code; each `SENDER` frame's `value` moves from `sender` to its
  target if the sender can pay it; and `writes` are applied.

**BB-6. Two dimensions.** Under the rule `two`, a block MUST count its gas
in two sums against its gas limit $L$, execution gas $X$ and state gas $S$,
both 0 when it starts, and BB-3 and BB-4 read as follows.

- A transaction's *reservation* is a pair $(r_X, r_S)$:
  $(\min(\mathit{gas}, 2^{24}), \mathit{gas})$ for an account-nonce
  transaction, and
  $(\mathit{max\_gas} - \sum_f s_f, \sum_f s_f)$ for a frame transaction,
  with $s_f$ its frames' state limits (FEE-4) and AG-8's charge, if any,
  added to $r_X$. It *fits* if $r_X \leq L - X$ and $r_S \leq L - S$. BB-3
  drops a head that does not fit where it would drop one whose gas limit
  exceeds the gas left, and wherever another document appends what fits
  the gas left (IL-7 of `07-focil.md`), it appends what fits.
- BB-3's loop runs while at least 12,000 gas is left in each dimension.
- An included transaction adds its `state_gas_used` (MD-5, MD-6) to $S$
  and the rest of its `gas_used` to $X$; AG-8's charge, and the gas of
  each transaction LU-13 decrypts, count in $X$. A transaction that
  reverted (BB-5) adds its whole `revert_gas_used` to $X$ and nothing to
  $S$.
- BB-4's `gas_used` is $\max(X, S)$, which FEE-1 reads as it is.

BB-5 is unchanged: the sender, or a frame transaction's payer, pays for all
of its `gas_used` at one price, both dimensions alike. **Source:** EIP-8037
at `258836f9` (Last Call, deadline 2026-11-01), Transaction validation, item
3 (`min(TX_MAX_GAS_LIMIT, tx.gas) <= execution_gas_available` and
`tx.gas <= state_gas_available`), Block-level gas accounting (the header's
`gas_used` is the larger of `block_execution_gas_used` and
`block_state_gas_used`, and the base fee is "modified accordingly"), and Multidimensional metering ("the user pays for both
execution-gas and state-gas") and Gas accounting for halts and reverts ("A
call frame's state changes are rolled back on both reverts and exceptional
halts. In both cases the frame's state-gas is restored to its baseline",
and "The same rules apply when the top-level call frame reverts or halts");
EIP-8141 at the same commit, Block-level gas
accounting ("A frame transaction may be included in a block only if its
worst case fits the remaining capacity of **each** dimension", with
`execution_reservation` and `state_reservation`); go-ethereum at
`93d78a01`, `core/gaspool.go` (`CheckGasAmsterdam`, `Available`, `Used`)
and `miner/worker.go`, `commitTransactions`, which under Amsterdam stops
when `Available` is below `TxBaseCost2780`, 12,000.

*Interpretation*, decision record 0043: a transaction declares its state
gas, since the model runs no code to meter it, and the rest of its
`gas_used` is execution gas, so a declared `gas_used` is taken to include
the calldata floor that EIP-8037 applies to the execution dimension alone.
An account-nonce transaction reserves its whole `gas` in both dimensions up
to EIP-7825's $2^{24}$, as EIP-8037's reservoir does, which under the
`geth` profile's `max_tx_gas` (NP-3, item 4) is all of it. AG-8's charge is
execution, as the gas of a verification, and a sealed transaction's gas is
counted as execution because the model does not split it.

**BB-7. Builders that drop what reverts.** A builder with `drop_reverting`
set MUST treat an account-nonce transaction whose execution would revert
(BB-5) as failing with `ErrExecutionReverted`, leaving the state as it was:
BB-3 then drops it and the rest of its sender's candidates. The default is
unset, under which BB-5 includes it. A transaction LU-13 of `06-lucid.md`
decrypts is not dropped, since the block must execute it. *Interpretation*,
decision record 0045: go-ethereum's miner includes a transaction whose
execution fails, as BB-5 says; a builder that simulates and leaves such a
transaction out is the defence an earlier design study named for a shuffle
round's submitter, sending the round privately to a builder that drops
transactions that would revert, which that study did not measure, and no
source read here says which builders do so.

*Not modelled:* refunds, blobs, block size, EIP-8037's state-gas refills and
reservoir within a transaction, EIP-2780's other changes, and bounding the
unpaid validation work a producer spends on a frame transaction that stops
approving ("Replacement and Eviction", last paragraph). Of EIP-7702's steps,
an authorization's chain id and signature
(an authority is a recovered address already), the refund of step 7, and a
delegation to the zero address, which clears the code instead. Where in
its execution a transaction reverts, and so how much of its gas it used,
which the model declares as `revert_gas_used`.

## Version notes

- **Version 4.** BB-5 executes a transaction's pulls and pays (MD-5 of
  `00-model.md` version 8) and includes one whose execution reverts, at the
  gas it used; BB-6 counts a reverted transaction's gas as execution; and
  BB-7 adds builders that drop what would revert (decision record 0045). A
  transaction with no pulls and no pays never reverts and applies as under
  version 3, so every vector of this document was re-read against version
  4 and needed no change but its version; `bb-05-apply.json` gains the
  cases of a revert and `bb-07-drop-reverting.json` is new.
- **Version 3.** BB-6 adds EIP-8037's two dimensions as the rule `two`
  (decision record 0043). Under the default `one`, BB-3 and BB-4 are
  version 2's. Every vector of this document was re-read against version
  3 and needed no change but its version; `bb-06-two-dimensions.json` is
  new.
- **Version 2.** BB-5 checks each authorization of a set code transaction as
  EIP-7702 does, against its authority's code and, when the authorization
  carries one, its nonce, after the sender's nonce has increased, and skips
  one that fails (decision record 0031). Version 1 applied every one, after
  the rest of the transaction. Every vector of this document was re-read
  against version 2: `bb-05-apply.json` gained four cases, and the rest
  needed no change but their version.
