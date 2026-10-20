# 0007. MATCHA is specified as a proposal, with its open choices made explicit

Date: 2026-10-07. Status: accepted.

## Context

The plan's item 2 asks for a third `per_sender` policy, stated as a proposal in
a clause, so that experiment 02 can compare it with experiment 01's `one` and
`disjoint-keys`. The policy is MATCHA (ethresear.ch topic 25949, 2026-09-08),
a forum post rather than an EIP. It is written as a mechanism with rationale,
not as an algorithm, so turning it into clauses that two people would
implement the same way needs a reading at every point where the post leaves a
choice. Each choice below is an *Interpretation* in
`docs/spec/04-matcha.md`.

## Decision

1. **A separate document, a separate profile.** `04-matcha.md` states MATCHA
   as changes to the frame pool of `02-frame-pool.md`, which is unchanged.
   The `matcha` profile is the `eip-8141` profile with `per_sender = matcha`
   and four parameters of its own. The document says *proposal* in its
   status line, so that nobody reads the profile as what a client does.
2. **Parameter values the post does not give.** `width_cap` is $2^{24}$,
   EIP-7825's per-transaction gas cap, chosen only as a protocol constant of
   the right order: at the default safety factor it holds about 290 charges
   for the spend of experiment 02. `safety_factor` is 2, the factor an
   earlier design study of a voucher pool quotes for it, from its cost
   measurement of 2026-09-08.
   `lifetime` is three hours, go-ethereum's `Lifetime` for queued
   transactions (NP-1). None of the three is a finding; experiment 02 varies
   the first two.
3. **Admission gas** is FEE-4's intrinsic gas without its value-transfer
   term, plus the declared execution limits of the validation prefix. The
   post lists what it covers: data, signatures, nonce checks, recent-root
   checks and execution through payment approval. The per-transaction and
   per-frame costs are kept because that study keeps them when it prices the
   same charge, so the two sets of numbers can be compared; the value term
   is dropped because a value transfer happens after validation. EIP-8250's
   nonce checks cost state gas and no execution gas, so they enter only as
   the nonce bytes FEE-4 now prices (decision record 0006).
4. **Key 0 is excluded on both sides** of an additional admission, as under
   `disjoint-keys`. The post says an additional transaction uses "EIP-8250
   nonce keys"; EIP-8250's Rationale permits a future policy "on disjoint
   non-zero key sets". A baseline may use key 0, and while it is pending its
   sender gets no additional transaction.
5. **"Valid for a child of the current head"** is read as two checks the
   model can make: the fee cap covers the pending base fee, which the post
   names, and an expiry deadline lies above the head's timestamp, because a
   child's timestamp exceeds its parent's and the expiry verifier accepts
   `block.timestamp <= deadline`. A client knows the next slot's timestamp
   and could check against it; the model does not.
6. **A baseline's re-run is free.** The post charges the re-run of "its
   validation prefix" in a sentence about additional transactions and says
   the baseline spends no width. Charging the baseline would make MATCHA
   stricter than EIP-8141 for a sender with one pending transaction, which
   the post does not suggest.
7. **Balance reuse is exact in the model.** A prefix in the model observes a
   balance only through `APPROVE`'s comparison with `max_cost`, because FP-9
   bans `BALANCE` and `SELFBALANCE`, so a re-run after a balance-only change
   always returns the earlier result. MA-10's reservation check stands in
   for that comparison. The parameter `reuse_balance` exists so that the
   experiment can measure what the reuse saves, which is the honest
   throughput question the post leaves open.
8. **Unavailability is all or nothing per payer.** "Affected transactions
   remain unavailable for block construction until their combined
   reservations fit the new balance" is read as: while the sum of a payer's
   reservations exceeds its balance, none of its transactions is offered to a
   builder. A pool that offered the oldest ones that fit would be a
   different, also defensible, reading.
9. **Lifetime counts from each transaction's own admission**, checked at
   every operation that carries a time, with "more than" as NP-18 has it.
10. **Width is credited from `finalize`**, a fourth pool operation (MD-8,
    version 2), which hands the pool each newly final block's frame gas by
    sender. The pool cannot derive it from `reset`, which carries only the
    post-state, and finality is a consensus-layer fact the pool is told.
    `gas_used` is credited whole; whether the state-gas part of it should be
    is listed as an open question.

## Consequences

- The vectors in `conformance/vectors/matcha/` bind every one of these
  readings, and a vector for an interpretation says so in its
  `distinguishes` sentence.
- The simulator needs finality, so `sim/` gains a model of it (experiment
  02's README states the rule and its source).
- If the post's authors or a client settle any of these differently, the
  clause changes, `04-matcha.md` takes a new version, and this record is
  superseded rather than edited.
