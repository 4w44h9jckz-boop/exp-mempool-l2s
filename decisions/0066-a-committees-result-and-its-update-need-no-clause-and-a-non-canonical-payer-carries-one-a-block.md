# 0066. A committee's result and its update need no clause, and a non-canonical payer carries one a block

Date: 2026-10-21. Status: accepted.

## Context

A threshold committee that answers requests on L1 sends two kinds of frame
transaction:

- **a result**: the sender is a result contract, whose `VERIFY` frame checks
  the committee's threshold signature over a request and its result and
  approves execution; the contract pays, or a paymaster's `VERIFY` frame
  does. Results for different requests do not depend on each other, so each
  request is a nonce key of its own.
- **an update of shared state**: the sender is the committee's own account,
  whose `VERIFY` frame checks the committee's signature and approves
  execution, and a payer's `VERIFY` frame approves payment, or the committee
  pays. An update is computed from the state the last one left, so updates
  follow one another.

The questions are what the specification already says a node does with each,
how FP-11's limit of one pending transaction for a non-canonical payer
applies to each, and what that limit costs a committee that posts often. As
for decision record 0065, the clauses were read first.

- **The signature check** is a prefix's verification cost, which FP-6 caps
  at `max_verify_gas`. A threshold signature verifies as one signature
  against the group's key, so the threshold does not change the check, and a
  signature from fewer members than the threshold does not verify: the
  frame reverts and the prefix never approves (FP-8). A BLS signature is
  checked with a pairing check of two pairs, which EIP-2537 prices at
  $32600 \cdot 2 + 37700 = 102900$ gas, before the message is hashed to the
  curve: above `eip-8141`'s `max_verify_gas` of 100,000 whatever else the
  frame does. A ticket paymaster's `VERIFY` frame, the same check over a
  132-byte message, spent 122,006 gas on the Hegota testnet (`exp-frames`
  experiment 36, `refs/refs.md`), under `hegota-testnet`'s 500,000.
- **FP-10 and FP-11** read the payer from the prefix's last frame. A result
  contract or a committee that pays for itself is class `sender`; a
  paymaster whose code is the canonical paymaster's is `canonical`; a payer
  with no code is `default`; any other is `noncanonical`, and FP-11 lets it
  pay for `max_pending_noncanonical`, 1, pending transaction, as it lets a
  `default` payer when `cap_codeless_payers` is true, as on
  `hegota-testnet`. The reservation applies to every class.
- **FP-12** holds a sender to one pending transaction under `one`,
  `eip-8141`'s value, and to one for each set of keys that shares none with
  another under `disjoint-keys`, `hegota-testnet`'s.
- **FP-7** queues no frame transaction: an update at the next sequence of a
  key is `ErrNonceTooHigh` until a block includes the one before it, and
  FP-15 step 1 then drops that one from the pool.

## Decision

1. **No clause is new.** FP-6, FP-7, FP-8, FP-10, FP-11, FP-12 and FP-15
   say what a node does with both transactions, and SF-6 relays what a node
   admits. The vectors that say so are
   `conformance/vectors/frame-pool/fp-11-committee.json`, ten cases; the
   reference passed them unchanged.
2. **How FP-11 applies to each.**
   - A result paid by its contract is never capped by FP-11: its contract
     is class `sender`, and its balance must cover the summed `max_cost` of
     its pending results. Under `disjoint-keys` results for different
     requests are pending together; under `one` the contract holds one.
   - A result or an update paid by a non-canonical paymaster is one pending
     transaction for that paymaster, whatever its keys: the second is
     `ErrFramePaymasterBusy` until a block includes the first.
   - An update paid by the canonical paymaster, or by the committee's own
     account, is held only by the payer's balance, less a canonical
     paymaster's pending withdrawal.
   - Under `one` FP-12 binds first: the committee's account holds one
     pending update whatever pays, and FP-11 adds nothing to it. Under
     `disjoint-keys` FP-11 is what binds.
3. **What it costs a committee that posts often.** A pool holds at most one
   transaction for each non-canonical paymaster, and keeps it until a block
   includes it or the pool drops it, so a builder that takes transactions from
   its pool puts at most one of that paymaster's in a block. A committee
   paid by one non-canonical paymaster therefore lands at most one
   transaction a block through the public pool, results and updates
   together. The vectors' case "results paid by a non-canonical paymaster"
   shows the step: the next is admitted only once the last is included.
   - Its updates lose nothing to this that FP-7 does not already take: one
     after another on one key, they land at most one a block anyway.
   - Its results do: results for different requests could be pending
     together, and a non-canonical paymaster serialises them. A committee
     that answers more than one request a block needs one non-canonical
     paymaster for each result it lands in a block, each with a float of its
     own, or the canonical paymaster, or a result contract that pays for
     itself, or several results in one transaction.
   - A transaction that a block leaves out holds up every later one through
     the same paymaster, and only a replacement at the price bump moves it:
     FP-11 counts a replacement in place of the transaction it replaces.
     Experiment 19 measured the same stall for a committee that sends from
     one key and never re-prices: after a burst, 467 of 627 intents were
     never settled.
4. **The vectors take 122,006 gas for the check**, the ticket paymaster's
   measured frame, as an ASSUMPTION for a committee's signature over a
   request and its result: the same pairing check, over a message of
   another length. Only the hashing changes with the length. The refusal
   under `eip-8141` does not rest on it, since the pairing check alone is
   above the cap.

## Not modelled

- The committee's computation, its rounds, its keys and its rotation:
  experiments 19 and 23 model them.
- A builder that takes a committee's transactions from somewhere other than
  its pool, which FP-11 does not bound.
- What hashing a message of a given length to the curve costs in a frame.

## Consequences

- Under `eip-8141`'s budget no transaction whose `VERIFY` frame checks a
  BLS signature is admitted, a committee's result or update as much as a
  ticket. A committee there needs a signature whose check costs less than
  a pairing check of two pairs, which nothing here has measured, or a
  profile with a larger `max_verify_gas`, as `10-claim-gated-admission.md`
  lists for the ticket paymaster under "Not modelled".
- The limit falls on the committee that posts results often through a
  non-canonical paymaster: one result a block for each such paymaster.
- The committee's own shapes, when they come, are judged against these
  vectors, as decision record 0054 judged `exp-frames`' mined pair.
