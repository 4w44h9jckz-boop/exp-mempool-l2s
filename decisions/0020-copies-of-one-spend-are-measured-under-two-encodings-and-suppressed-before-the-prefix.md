# 0020. Copies of one spend are measured under two encodings of its nullifier, and suppressed before the prefix

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 18 starts from the blind ticket of an earlier account
abstraction study. Its holder can put the ticket into many operations at
once, and only one of them can land. That study reads the copies as
ERC-7562's mass invalidation attack in its cheapest form: one spend
invalidates every copy. It proposes duplicate suppression, one pending
operation per paymaster and $\kappa$. Both were read on 2026-10-09.

In the frame pool the spent record cannot be a paymaster's storage, because
FP-9 refuses a prefix that reads storage outside `sender`. So the ticket
becomes a spend from a shared sender, as in experiments 01 and 02, and the
nullifier can sit in one of two places:

- **an EIP-8250 nonce key**, which `SharedSenderLoad` already uses. Then
  every copy has the same identity `(sender, nonce_keys, nonce_seq)`, and
  EIP-8141 already merges them: "Different variants of the same transaction
  share that identity and are therefore replacement candidates, not
  distinct transactions" (Mempool, Replacement and Eviction, at
  `258836f9`). FP-12 keeps one per pool.
- **a slot in the shared sender's storage**, the way a contract keeps a
  nullifier set. The prefix reads the slot and approves only while it holds
  0, and the execution writes it. FP-9 allows the read, because the slot is
  `sender`'s. Each copy then needs a nonce key of its own, so the copies
  have different identities, and every pool can hold all of them.

FP-12's merge has a cost the EIP's order leaves in. FP-8 runs the prefix
before FP-12 compares the copy with the one the pool holds, so every copy a
pool refuses has already cost it a run.

## Decision

1. **Both encodings are measured.** The nonce key is what the frame pool
   merges. The storage slot is what that study's paymaster-storage path
   looks like on a shared sender, and it is where the mass invalidation
   lives.
2. **A copy differs from the others only in its label.** The label is the
   model's stand-in for a field that differs between copies, such as a
   relayer's fee recipient. Copies carry the same fees, and the holder
   hands each to a different random node. A copy that paid the 10% bump
   would replace the others as it spread, which is a fee race, not copies.
3. **The suppression variant is FP-11 and FP-12 before the prefix.**
   `02-frame-pool.md` version 5 adds `static_first`, false in both profiles.
   Under the nonce encoding FP-12 already is that study's rule, one pending
   transaction per identity, with $\kappa$ in the identity. What it lacks is
   that it refuses on a field it can read without running anything. Moving
   it ahead of FP-8 does that. FP-11 moves with it. Its cap on
   non-canonical payers is the same kind of rule, one pending transaction
   per paymaster, and it reads only the payer the prefix names, that
   payer's balance and code, and the pool.

   Neither clause reads what FP-8 to FP-10 compute, so the admitted set is
   the same under either order. Only the answer differs, for a transaction
   that both orders refuse. The vectors pin the order through those
   answers, and `ref/python/tests/test_invariants.py` checks that a pool
   with the variant admits exactly what a pool without it admits. The EIP
   orders it the other way: its acceptance algorithm simulates (step 4)
   before solvency (step 6) and the per-sender rule (step 7).
4. **The storage encoding gets no suppression variant.** A pool cannot tell
   which slot is a nullifier without running the prefix. A rule keyed on
   the slots a prefix reads would need the trace, which is the work it
   means to save.
5. **The profile is `hegota-testnet`.** Under `one` a shared sender has one
   pending transaction per pool, so copies of different spends compete for
   it and the measurement becomes experiment 01's ceiling. `disjoint-keys`
   lets a pool hold one spend per nullifier.

## Consequences

- `02-frame-pool.md` version 5, nine new cases in `fp-11-payers.json` and
  `fp-12-per-sender.json`, and `static_first` in
  `ref/python/emem/framepool/`.
- `CopiesLoad` in `sim/emem_sim/workload.py` sends each spend as copies
  under either encoding.
- Experiment 11 measures how many pools hold a copy that has lost, for how
  long, and the runs and re-runs one spend costs. It does so for one to
  eight copies and for a copy handed to every node, under both encodings,
  and under the nonce encoding with and without `static_first`.
- Experiment 10's refusals, `ErrInsufficientFunds` for a sponsor that holds
  nothing and `ErrFramePaymasterBusy` under the testnet's cap, are among
  those `static_first` makes free. That experiment keeps the EIP's order.
