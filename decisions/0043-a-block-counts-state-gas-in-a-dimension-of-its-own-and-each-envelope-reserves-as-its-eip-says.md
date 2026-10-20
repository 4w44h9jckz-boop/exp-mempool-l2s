# 0043. A block counts state gas in a dimension of its own, and each envelope reserves as its EIP says

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 34 is about a floor on what a private spend costs: its
nullifier is one new storage entry, 97,920 state gas under EIP-8037, and it
cannot be deferred. The item asks for experiment 21 again with state gas and
full blocks. Until now the model
had no state gas: `03-block-building.md` version 2 listed EIP-8037's
dimension as not modelled, and FEE-4 neither required nor charged
EIP-8250's first-use state gas.

EIP-8037, read at `258836f9`, is in Last Call with a deadline of
2026-11-01. It splits a transaction's gas into execution gas and state gas,
`STATE_BYTES_PER_STORAGE_SET` $\times$ `CPSB` $= 64 \times 1530 = 97920$ for
a new storage slot, and keeps two sums per block, each against the gas
limit. The header's `gas_used`, and with it the base fee, is the larger sum.
A transaction pays for both dimensions at one price. Its inclusion check
reserves `min(TX_MAX_GAS_LIMIT, tx.gas)` of execution and `tx.gas` of state,
because a transaction with one gas field cannot say in advance how its gas
will split. go-ethereum at `93d78a01` implements exactly that under
Amsterdam (`core/gaspool.go`, `CheckGasAmsterdam`), and its miner skips a
transaction whose gas exceeds `Available` and stops when `Available` is
below `TxBaseCost2780`, 12,000 (`miner/worker.go`, `commitTransactions`).

EIP-8141 at the same commit gives a frame transaction both budgets in its
frames' `limits` and reserves them exactly: `execution_reservation`, the
intrinsic gas plus the frames' execution limits or the floor, in the
execution dimension, and `state_reservation`, the frames' state limits, in
the state dimension. It says so: "no portion of the transaction's gas is
reserved in both dimensions at once, as it must be under EIP-8037's
reservoir model".

## Decision

1. **Two rules, `one` by default.** `03-block-building.md` version 3 adds
   BB-6, the rule `two`, as a change to how BB-3 and BB-4 read. Under `one`
   nothing a block does changes, so no earlier experiment's result moves;
   an experiment chooses `two`.
2. **A transaction declares its state gas.** The model runs no code, so a
   transaction carries `state_gas_used` beside `gas_used` (MD-5 and MD-6 of
   `00-model.md` version 7): 0 by default for an account-nonce transaction,
   and its frames' state limits for a frame transaction, as `gas_used`
   defaults to the whole limit. The rest of `gas_used` is execution gas.
   EIP-8037 counts the calldata floor against the execution dimension
   alone; a declared `gas_used` is taken to include it.
3. **Each envelope reserves as its EIP says.** An account-nonce transaction
   reserves $(\min(\mathit{gas}, 2^{24}), \mathit{gas})$, go-ethereum's and
   EIP-8037's reservoir check. A frame transaction reserves
   $(\mathit{max\_gas} - \sum_f s_f, \sum_f s_f)$, which is EIP-8141's pair,
   since FEE-4's `max_gas` is the frames' state limits plus the larger of
   the intrinsic gas with the execution limits and the floor. The
   difference is the subject of item 34: the same spend reserves its state
   gas in the execution dimension too when it is a type 2 transaction, and
   does not when it is a frame transaction.
4. **The loop stops at 12,000 in either dimension.** That is go-ethereum's
   `Available` against `TxBaseCost2780` under Amsterdam. Where the
   execution room is at least $2^{24}$, `Available` is the state room
   alone, which stops the loop at the same point, so the clause states the
   simpler condition. EIP-2780 is otherwise not modelled: FEE-3 keeps
   21,000 for an account-nonce transaction, so the lower threshold matters
   only to frame transactions.
5. **What another clause adds counts as execution.** AG-8's 30,000 gas a
   dependency is a verification, and a sealed transaction's gas (LU-13) is
   not split in the model. IL-7's "fits the gas left" reads as BB-6's fit,
   so a listed transaction is appended under the same test as any other.

## Consequences

- A spend's nullifier can now cost state gas in a block, and an experiment
  can put the same spend in a frame transaction and in a type 2
  transaction, against blocks full of execution or of state.
- The base fee follows whichever dimension a block filled more. A block
  full of execution leaves the state dimension's room unpriced, and a
  spend's 97,920 state gas is still paid at the base fee the execution
  dimension set.
- Refills, the reservoir within a transaction and refunds stay out: the
  model's transactions use what they declare.
