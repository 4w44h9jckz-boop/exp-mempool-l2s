# 02. The frame transaction pool (EIP-8141 public mempool)

Version 7, 2026-10-20.

The public mempool policy for EIP-8141 frame transactions, with EIP-8250's
keyed nonces, written down as clauses. Both EIPs are Draft; the text was read
from ethereum/EIPs at commit `258836f9` (2026-10-07), EIP-8141 section
"Mempool" and EIP-8250 section "Mempool". Quotations below are from those
sections unless another is named.

The model does not run the EVM. A frame carries what a node simulating it
would observe (MD-6), and the clauses below are rules over those observations.
Decision record 0003 explains the choice and what it cannot express. The
mechanism itself is EIP-8141's and is not restated here.

## Profiles

**FP-1. Parameters.**

| Parameter | `eip-8141` | `hegota-testnet` | Note |
| --- | --- | --- | --- |
| `max_verify_gas` | 100000 | 500000 | `MAX_VERIFY_GAS`; testnet value measured by bisection on 2026-09-10 |
| `max_verify_state_gas` | 500000 | not enforced | `MAX_VERIFY_STATE_GAS`; testnet: the same measurement |
| `max_pending_noncanonical` | 1 | 1 | `MAX_PENDING_TXS_USING_NON_CANONICAL_PAYMASTER` |
| `cap_codeless_payers` | false | true | whether a default-code sponsor counts against the cap above; testnet: the same measurement |
| `per_sender` | `one` | `disjoint-keys` | FP-12; testnet: reported by `exp-frames` on 2026-10-07 (its `plan` branch, citing EIPs pull request 12039) and not re-measured here |
| `expiry_verifier` | `0x81413f0cF12e9b6a49B1D0439E081c577D57FfFf` | `0x0000000000000000000000000000000000008141` | `EXPIRY_VERIFIER` |
| `price_bump` | 10 | 10 | "10% is the conventional default" |
| `price_limit` | 1 | 1 | *Interpretation*: the EIP sets no minimum tip; this mirrors NP-1 |
| `max_pending` | 4096 | 4096 | *Interpretation*: the EIP says "local resource limits" without a number |
| `reuse_balance` | false | false | whether a change to balances alone re-runs a prefix (FP-15); not in the EIP, and true only in variants the experiments measure, decision record 0009 |
| `evict_first` | `expiry` | `expiry` | which criterion FP-14 applies first, the nearest deadline or the lowest effective tip; `tip` is not in the EIP and is set only in variants the experiments measure, decision record 0010 |
| `expiry_margin` | 0 | 0 | seconds added to the head's `timestamp` where FP-8 and FP-15 compare a deadline with it; 0 reads the EIP's "current block timestamp" as the head's, and only variants the experiments measure set it otherwise, to the slot time for the next block's, decision record 0011 |
| `static_first` | false | false | whether FP-11 and FP-12 run before FP-8 (Admission); not in the EIP, and true only in variants the experiments measure, decision record 0020 |

`hegota-testnet` also takes `08-recent-roots.md`'s recent roots, with the
parameters of its RR-1 column, because the testnet runs EIP-8272; no other
profile here does (decision record 0053).

Two code values are distinguished by profile: `canonical_paymaster_code`, the
runtime code of the canonical paymaster implementation, and
`expiry_verifier_code`, that of the expiry verifier. In the model both are
named strings (`canonical-paymaster`, `expiry-verifier`), compared by equality
like all code (MD-2). Precompiles are a set of addresses, by default
`0x01` to `0x11` and `0x100` written as 40-digit hexadecimal addresses.

## Errors

| Code | Raised by |
| --- | --- |
| `ErrAlreadyKnown` | FP-2 |
| `ErrFrameMalformed`, `ErrGasLimitTooHigh`, `ErrInvalidSender`, `ErrTipAboveFeeCap`, `ErrTxGasPriceTooLow`, `ErrGasLimit` | FP-3 |
| `ErrFrameExpiryNotFirst`, `ErrFrameNoPayer`, `ErrFrameAtomicInPrefix`, `ErrFrameUnrecognizedPrefix`, `ErrFrameVerifyAfterPrefix` | FP-5 |
| `ErrFrameVerifyGas`, `ErrFrameVerifyStateGas` | FP-6 |
| `ErrNonceTooLow`, `ErrNonceTooHigh` | FP-7 |
| `ErrFrameExpired`, `ErrFramePrefixReverted`, `ErrFrameMissingApprove`, `ErrFrameDeployNoCode`, `ErrInsufficientFunds` | FP-8 |
| `ErrFrameBannedOpcode`, `ErrFrameStateWrite`, `ErrFrameStorageReadNonSender`, `ErrFrameCallTarget` | FP-9 |
| `ErrFramePayerExposure`, `ErrFramePaymasterBusy` | FP-11 |
| `ErrReplaceUnderpriced`, `ErrFrameSenderBusy` | FP-12 |
| `ErrAlreadyReserved` | FP-13 |
| `ErrTxPoolOverflow` | FP-14 |

The EIP names no errors. The frame-specific codes are this repository's; the
others reuse go-ethereum's names where the meaning is the same.

## Admission

The checks run in the order of the clauses, and the first failure is the
result. The order follows the EIP's "Acceptance Algorithm" where it gives one.

With `static_first` true, which is read only when `per_sender` is `one` or
`disjoint-keys`, FP-11 and FP-12 run after FP-7 and before FP-8. They take
the payer and its class that FP-10 would give, read from the prefix's shape:
the payer is the resolved target of the prefix's last frame, the one that
carries `APPROVE_PAYMENT` (FP-4), and its class is `sender` if it is the
sender and otherwise follows from its code in the head state, which no
prefix frame changes, because only a `deploy` frame installs code and only
at `sender`. Neither clause reads anything FP-8 to FP-10 compute, so a pool
admits the same transactions in either order. What changes is that a
transaction FP-11 or FP-12 refuses is refused without its prefix being run,
and that one which FP-8 or FP-9 would also refuse gets FP-11's or FP-12's
answer; FP-11's exposure check implies FP-8's balance check, so
`ErrInsufficientFunds` is never the answer. *Not in the EIP:* its acceptance
algorithm simulates the prefix (step 4) before it checks solvency (step 6)
and the sender's pending transaction (step 7), and says a replacement "must
be valid under all rules in this section" ("Replacement and Eviction").
Decision record 0020.

**FP-2. Duplicates.** A transaction whose hash the pool holds MUST be answered
`ErrAlreadyKnown`.

**FP-3. Static validity.** The pool MUST reject with `ErrFrameMalformed` a
transaction that breaks a constraint of EIP-8141 "Constraints" or "Expiry
Verifier Frame" that the model can express: between 1 and 64 frames;
`nonce_keys` non-empty and strictly increasing; every `mode` below 3 and every
`flags` below 8; `value` only on `SENDER` frames; a frame whose flags include
`APPROVE_EXECUTION` (0x2) targets `sender` or nothing; a frame with
`ATOMIC_BATCH_FLAG` (0x4) is not `VERIFY`, is not last, and is followed by a
frame that is not `VERIFY`; frames in an atomic batch carry no approval scope;
at most one frame targets the expiry verifier and it has flags 0, value 0,
state limit 0 and 8 bytes of data. Then, in order: `ErrGasLimitTooHigh` if
$\max(g_{\text{intr}} + \sum_f e_f,\, g_{\text{floor}}) > 16777216$ (FEE-4);
`ErrInvalidSender` if any signature is not `valid` (step 2 of the acceptance
algorithm); `ErrTipAboveFeeCap` if `tip` > `max_fee`; `ErrTxGasPriceTooLow` if
`tip` < `price_limit`; `ErrGasLimit` if `max_gas` exceeds the head's
`gas_limit`. *Interpretation:* the last three are not in the EIP and mirror
NP-3.

**FP-4. The validation prefix.** The validation prefix is the frames up to and
including the first frame whose `flags` include `APPROVE_PAYMENT` (0x1).
*Derivation:* the EIP defines the prefix as "the shortest prefix of frames
whose successful execution sets `payer`", and only `APPROVE` with a payment
scope sets `payer`, which `APPROVE` refuses unless the scope is within
`frame.flags`. So no earlier frame can set `payer`, and if this one does not,
the transaction is invalid whatever the prefix is taken to be.

**FP-5. Structure.** Frames are classified as: `expiry_verify`, a `VERIFY`
frame targeting `expiry_verifier`; `deploy`, a `DEFAULT` frame with no approval
scope; `self_verify`, a `VERIFY` frame with flags `0x3` targeting `sender` or
nothing; `only_verify`, the same with flags `0x2`; `pay`, a `VERIFY` frame with
flags `0x1`. The pool MUST reject:

1. with `ErrFrameExpiryNotFirst`, an `expiry_verify` frame anywhere but first;
2. with `ErrFrameNoPayer`, a transaction with no frame carrying
   `APPROVE_PAYMENT`;
3. with `ErrFrameAtomicInPrefix`, a prefix frame with `ATOMIC_BATCH_FLAG`
   (structural rule 5);
4. with `ErrFrameUnrecognizedPrefix`, a prefix that, with a leading
   `expiry_verify` frame skipped, is not one of `[self_verify]`,
   `[deploy, self_verify]`, `[only_verify, pay]`,
   `[deploy, only_verify, pay]` (structural rules 1 to 4);
5. with `ErrFrameVerifyAfterPrefix`, any `VERIFY` frame after the prefix
   (structural rule 8).

*Interpretation:* structural rule 2 says `deploy` "must be the first frame"
while the expiry section skips a leading `expiry_verify` frame for shape
matching; this spec reads "first" after that skip, so
`[expiry_verify, deploy, self_verify]` is recognised. Decision record 0003.

**FP-6. Budgets.** The sum of `exec_gas` over the prefix plus the signature
verification cost of FEE-4 MUST NOT exceed `max_verify_gas`, else
`ErrFrameVerifyGas`. Where the profile enforces it, the sum of `state_gas`
over the prefix MUST NOT exceed `max_verify_state_gas`, else
`ErrFrameVerifyStateGas`. (Structural rule 6.)

**FP-7. Nonce.** For each key in `nonce_keys` the pool reads the sender's
current sequence (MD-3). If any is above `nonce_seq` the pool MUST return
`ErrNonceTooLow`; else if any is below it, `ErrNonceTooHigh`. **Source:**
EIP-8141 "Behavior", step 1 ("Ensure `tx.nonce == state[tx.sender].nonce`"),
as generalised by EIP-8250. A frame transaction is never queued.

**FP-8. Simulation.** The pool MUST evaluate the prefix frames in order
against the head state, with `sender_approved` false and no payer:

- `expiry_verify`: if the code at the target is not `expiry_verifier_code`,
  `ErrFramePrefixReverted`; if `deadline` is below the head's `timestamp`
  plus `expiry_margin`, `ErrFrameExpired`.
- `deploy`: the trace rules of FP-9 apply with the deploy exceptions. If the
  frame reverts, `ErrFramePrefixReverted`. If its target has empty code, or
  `installs_code` is absent, or `sender` already has code, nothing is
  installed and the result is `ErrFrameDeployNoCode` (trace rule "its
  execution does not result in non-empty code being installed"). Otherwise
  later frames see `sender` with the installed code.
- `self_verify`, `only_verify`, `pay`: let the resolved target be `target`, or
  `sender` if absent. If the resolved target has empty code the frame runs the
  default code: it approves the frame's scope if the signature at index 0
  (scope includes `APPROVE_EXECUTION`) or index 1 (otherwise) is `secp256k1`,
  `valid`, over the canonical message, and its resolved signer is the resolved
  target; otherwise it reverts, `ErrFramePrefixReverted`. Otherwise the frame's
  observations decide: first the trace rules of FP-9 (unless the canonical
  paymaster exception applies); then `ErrFramePrefixReverted` if the frame
  `reverts` or any of its `reads` with an `expected` value does not hold it in
  the head state; then `ErrFrameMissingApprove` if `approves` differs from the
  frame's approval scope.
- An approval that includes payment MUST fail with `ErrInsufficientFunds` if
  the payer's balance is below `max_cost` (`APPROVE`: "If `resolved_target` has
  insufficient balance, revert").

A transaction that carries a `verdict` (MD-6) is not evaluated frame by
frame. Its verdict is the outcome of the prefix frames under this clause and
FP-9: a value other than `ok` is the result, and `ok` passes every prefix
frame, after which the payment check of the last bullet still applies, with
the payer of FP-10. *Interpretation*, decision record 0051: the verdict is
the answer of a client that simulated the prefix at the pool's head
(`11-surface.md`, SF-4), so a pool that does not execute the EVM applies the
EIP's step 4 through it. A client folds some failures into one answer: a
payer whose balance cannot cover `max_cost` makes `APPROVE` revert, which a
client may report as a reverted prefix, so a pool with a verdict can answer
`ErrFramePrefixReverted` where one evaluating observations answers
`ErrInsufficientFunds`. Both refuse the transaction.

*Interpretation:* within a frame, the order of trace rules before outcome is
this spec's; a client finds a trace violation at the instruction that commits
it, which may be after a read that decides the outcome. Decision record 0003.

*Interpretation*, for the deadline: the expiry verifier "reverts unless
`block.timestamp <= expiry_timestamp`" (Expiry Verifier Frame), and the
mempool section drops a transaction whose deadline "is less than the node's
view of the current block timestamp at any point" (Mempool, Expiry Verifier
Frame) without saying which block is current. With `expiry_margin` 0 it is
the head, as in go-ethereum, whose pool takes its head from `CurrentBlock`,
"the current head of the chain", and checks fork rules at the head's time
(`core/txpool/txpool.go`, `core/txpool/validation.go`, at `93d78a01`). A
deadline at or above the head's timestamp and below the next block's then
passes, and no block can include the transaction. With `expiry_margin` equal
to the slot time the current block is the one being built, the first a
transaction can be in, and with no missed slot every deadline admitted can
be met. The profiles keep version 1's reading; decision record 0011.

**FP-9. Trace rules.** For a prefix frame whose behaviour is not protocol
defined, the pool MUST reject, checking in the order listed:

- with `ErrFrameBannedOpcode`, an observation of any of `GASPRICE`,
  `BLOCKHASH`, `COINBASE`, `TIMESTAMP`, `NUMBER`, `PREVRANDAO`, `GASLIMIT`,
  `BASEFEE`, `BLOBBASEFEE`, `SLOTNUM`, `GAS` (the model writes `GAS` only for a
  `GAS` not immediately followed by a call), `INVALID`, `SELFDESTRUCT`,
  `BALANCE`, `SELFBALANCE`, and, outside a `deploy` frame, `CREATE`, `CREATE2`,
  `SETDELEGATE` and `SSTORE`;
- with `ErrFrameStateWrite`, any write, except that a `deploy` frame may write
  `sender`'s storage;
- with `ErrFrameStorageReadNonSender`, a read of storage at any address other
  than `sender`, "including when reached transitively";
- with `ErrFrameCallTarget`, a call to an address that is neither a precompile
  nor holds code, or that holds an EIP-7702 delegation, except `sender`.

A transaction that carries a `verdict` is not checked against these rules
by the pool: its verdict already holds their result (FP-8).

Protocol-defined frames are exempt and are evaluated directly ("Direct
Evaluation of Protocol-Defined Frames"): default-code frames, the expiry
verifier, and a `pay` frame whose target code is `canonical_paymaster_code`
("Canonical Paymaster Exception"). The canonical paymaster's `reverts`,
`reads` and `approves` observations still decide its outcome, because it is
admitted by "code match, successful `APPROVE(APPROVE_PAYMENT)`".

**FP-10. Payer and dependencies.** The payer is `sender` for the
`self_verify` shapes and the `pay` frame's resolved target otherwise. Its
class is `sender` if it is the sender; else `canonical` if its code is
`canonical_paymaster_code`; else `default` if its code is empty; else
`noncanonical`. On admission the pool records the transaction's
**dependencies**: the sender's sequence for each of its nonce keys, code and
balance; every `sender` storage slot read in the prefix; the code of a deploy
frame's target (policy item 4, "the code of the factory"); the payer's code and
balance and, for a canonical payer, its `withdrawal`; and, with an expiry
frame, the code at `expiry_verifier`. **Source:** "Acceptance Algorithm"
step 5, and the dependency set of "Direct Evaluation of Protocol-Defined
Frames". For a transaction that carries a `verdict` the sender storage
slots its prefix read are not known to the pool; its dependencies are the
others above and its verdict, which FP-15 counts as changed when a `reset`
gives a different one (MD-8). *Interpretation*, decision record 0051.

**FP-11. Payer accounting.** Let $R(P)$ be the summed `max_cost` of the
pending transactions whose payer is $P$, leaving out a transaction this one
replaces, and $w(P)$ the payer's `withdrawal` if its class is `canonical` and
0 otherwise. The pool MUST reject with `ErrFramePayerExposure` if

$$
\mathit{balance}(P) - R(P) - w(P) < \mathit{max\_cost},
$$

which applies to every payer class ("Reservation accounting applies to every
payer, not only canonical paymasters"). For class `noncanonical`, and for
class `default` when `cap_codeless_payers` is true, the pool MUST reject with
`ErrFramePaymasterBusy` if $P$ already pays for `max_pending_noncanonical`
pending transactions, not counting one this one replaces.

**FP-12. One pending transaction per sender.** A pending transaction is
identified by `(sender, nonce_keys, nonce_seq)` (EIP-8250). If the pool holds
one with the new transaction's identity, the new one MUST replace it if and
only if the fee rule of NP-11 holds with `price_bump`, and MUST otherwise be
rejected with `ErrReplaceUnderpriced`. If the pool holds any other pending
transaction from the sender, the new one MUST be rejected with
`ErrFrameSenderBusy`, except under `per_sender = disjoint-keys` when neither
transaction uses key 0 and their `nonce_keys` share no key. A replacement may
name a different payer, and moves the reservation atomically.
**Source:** "Acceptance Algorithm" step 7, "Replacement and Eviction";
EIP-8250 "Mempool" and Rationale ("A future policy MAY admit multiple pending
frame transactions for the same sender on disjoint non-zero key sets").

**FP-13. Subpool reservation.** A sender's transactions live in at most one
subpool at a time, under the tracker of NP-8: a frame transaction from a
sender held by the account-nonce pool MUST be rejected with
`ErrAlreadyReserved`. *Interpretation:* the EIP does not say how frame
transactions share a sender with other types; this follows go-ethereum's
subpool exclusivity. Decision record 0003.

**FP-14. Capacity.** When the pool holds `max_pending` transactions and the new
one replaces none, the pool MUST choose a victim among the held transactions
and the new one. With `evict_first` set to `expiry` it is the one with the
nearest expiry deadline (none counts as infinitely far), then the lowest
effective tip at the pending base fee, then the latest received (MD-10); with
`tip`, the one with the lowest effective tip, then the nearest deadline, then
the latest received. If the victim is the new transaction the pool MUST
return `ErrTxPoolOverflow`; otherwise it MUST evict the victim, releasing its
reservation. **Source:** "Replacement and Eviction" ("first transactions
already invalid against the current head, then transactions with the nearest
expiry deadline, then transactions with the lowest effective priority fee").
The first criterion is empty in the model, because FP-15 evicts invalid
transactions at every reset; the EIP uses "invalid against the current head"
for a prefix that no longer approves, not for a fee cap below the base fee,
which FP-3 admits. `evict_first` `tip` is not in the EIP: it puts the price a
builder orders by (BB-2) ahead of the deadline, and exists so that experiment
04 can measure what the EIP's order protects and what it exposes (decision
record 0010).

*Open question, not settled here:* under the EIP's order any transaction
without a deadline outranks any with one, whatever either pays, so a full
pool can be emptied of every transaction with a deadline by transactions no
builder includes, which FP-3 admits at a fee cap of 1 wei. Under `tip` a
full pool can be emptied of every transaction by ones at a high tip whose
deadline the next block cannot meet, which FP-8 admits with `expiry_margin`
0 (FP-15's open question). Whether a deadline should rank before price is left open;
experiment 04 measures both orders.

## Head changes

**FP-15. Revalidation.** On `reset(head, state)` the pool MUST, in order:

1. remove every transaction for which some key of `nonce_keys` has a sequence
   above `nonce_seq` in `state` (included, or superseded on chain);
2. remove every transaction with an expiry deadline below the new head's
   `timestamp` plus `expiry_margin` ("at any point");
3. for each remaining transaction, in the order received, whose recorded
   dependencies (FP-10) changed between the old and new state, a verdict
   given in `reset` counting as changed when it differs from the one
   recorded, and any re-run using the transaction's newest verdict: if
   `reuse_balance` is true, every dependency that changed is a balance, and
   none of those balances changed from or to zero, record the new balances and
   re-run nothing; otherwise re-run FP-7 to FP-10 against the new head and
   state, and remove it if they fail;
4. recompute the reservations of FP-11 in the order received, removing every
   transaction that no longer passes FP-11.

The pool MUST NOT re-simulate a transaction whose dependencies did not change,
and MUST report which transactions the last reset re-simulated, so that the
revalidation work is observable. **Source:** "Revalidation"; "Nodes SHOULD
index pending transactions by this set so that head-of-chain changes are
revalidated without re-execution."

*Interpretation*, for `reuse_balance` only: a prefix cannot read a balance,
because FP-9 bans `BALANCE` and `SELFBALANCE`, so a balance enters its outcome
in two places. One is `APPROVE`'s check of the payer's balance against
`max_cost`, which step 4 makes at least as strictly. The other is the
sender-existence check that "decides the `APPROVE` account-creation state-gas
charge" ("Direct Evaluation of Protocol-Defined Frames"), which only a balance
moving from or to zero can change. The EIP asks for revalidation without
re-execution only for prefixes made of protocol-defined frames; the variant
extends it to every prefix, for balances only. Decision record 0009.

*Open question, not settled here:* the EIP drops a transaction "whose deadline
is less than the node's view of the current block timestamp". With
`expiry_margin` 0 a transaction whose deadline lies between the head's
timestamp and the next block's is admitted and can never be included.
Whether nodes should use the next slot's timestamp instead, which
`expiry_margin` set to the slot time does, is left open; experiment 05
measures both (FP-8, decision record 0011).

*Open question, not settled here:* the reservations of FP-11 and step 4
bound what a payer's pending transactions can cost, not how many there are.
Nothing in the mempool section keeps `max_fee` above the base fee, and
`max_cost` is `max_gas` times `max_fee`, so a payer can back up to
`max_pending` transactions with `max_gas` wei each, and step 3 re-simulates
all of them whenever its balance changes, by however little and by whomever.
Whether a node should require a fee cap near the base fee, or bound how many
transactions one payer backs, is left open; experiment 03 measures the cost
of neither.

## What builders see

**FP-16. The pending view.** The pool MUST offer its transactions to a builder
in descending order of effective tip at the builder's base fee, ties broken by
earlier receipt, omitting those whose effective tip is below the builder's
minimum. Each frame transaction stands alone: under FP-12 no two pending
transactions consume the same nonce sequence.

## Version notes

- **Version 2.** FP-1 gains `reuse_balance` and FP-15 step 3 its
  rule, with the reading behind it and a note on what the reservations
  bound. Both profiles set `reuse_balance` to false, so neither profile's
  behaviour changes: every vector of version 1 holds unchanged and now says
  version 2.
- **Version 3.** FP-1 gains `evict_first` and FP-14 the order it names.
  Both profiles set it to `expiry`, the EIP's order, so neither profile's
  behaviour changes: every vector of version 2 holds unchanged and now says
  version 3.
- **Version 4.** FP-1 gains `expiry_margin`, and FP-8 and FP-15 step 2 add it
  to the head's timestamp. Both profiles set it to 0, version 1's reading, so
  neither profile's behaviour changes: every vector of version 3 holds
  unchanged and now says version 4.
- **Version 5.** FP-1 gains `static_first`, and Admission the order it
  sets. Both profiles set it to false, so neither profile's behaviour
  changes: every vector of version 4 holds unchanged and now says
  version 5.
- **Version 6.** FP-8 and FP-9 take a transaction's `verdict` (MD-6,
  version 9) as the outcome of its prefix frames, FP-10 records the verdict
  in place of the sender slots the pool cannot see, and FP-15 step 3 counts
  a different verdict at the new head as a changed dependency (decision
  record 0051). A transaction without a verdict is judged as under version
  5, so neither profile's behaviour changes for one: every vector of version
  5 holds unchanged and now says version 6.
- **Version 7.** FP-1's `hegota-testnet` takes the recent roots of
  `08-recent-roots.md` version 2 (decision record 0053). `eip-8141`'s
  behaviour does not change, nor does `hegota-testnet`'s for a transaction
  with no frame that targets `0x0000000000000000000000000000000000008272`:
  every vector of version 6 holds unchanged and now says version 7.
