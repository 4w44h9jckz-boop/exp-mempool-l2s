# 0026. MATCHA's baseline is taken per contention class, read off what can re-run a prefix

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 16 takes up a question an earlier account abstraction study put
to the EIP-8250 authors and the MATCHA thread: whether `width` should be
indexed by the contention class of what a prefix reads rather than by the
account alone. The question is first asked on the thread itself. Reply #2, by
AnkushinDaniil (2026-09-08), observes that the work width prices, "the cheap
repeated invalidation loop, only shows up when the validation prefix reads
shared live-contended state", and asks "whether width could be indexed by that:
full charge when the prefix reads shared live-contended state, waived or
reduced when it's provably single-writer or recent-root-bound". Its classes are
those of ethresear.ch topic 25934, by the same author (2026-09-07):
single-writer, recent-root-bound, and live-contended. It names the counter
itself: "can a client decide cheaply that a prefix reads no shared contended
state without running it?" The post's author answered, reply #4 (2026-09-09),
that "lower risk of repeated invalidation could justify a lower charge, even if
the initial verification costs the same", but that "'single-writer' is not
enough: an app can change its own validation setting and invalidate txns, and
even if you have independent nullifiers and recent roots, you still have the
shared payer balance". Both were read from the topics' raw text on 2026-10-09
(`refs/refs.md`).

Nothing in the thread says what a class is in terms a client can compute.
`04-matcha.md` version 2 has no classes: MA-5 gives a sender one free
pending transaction, its baseline, and charges every other.

## Decision

1. **"Indexed by" is read as the baseline taken per class.** A transaction
   that shares a class with no pending transaction from its sender is a
   baseline and spends no width; one that shares a class with a pending one
   is additional and is charged as before. This is reply #2's waiver; the
   reduced charge it also names is not modelled. Width is still earned and
   spent by the sender (MA-3, MA-4): finalized gas belongs to a sender, not to
   a class.
2. **A class is what can make the pool re-run the prefix**, read off the
   dependencies FP-10 records: all of them but nonce sequences (a change makes
   the transaction stale, and FP-15 step 1 removes it without a run),
   balances when `reuse_balance` is on (MA-9 step 1), the code of an account
   whose code is neither empty nor a delegation, and recent root entries.
   Two transactions share a class when their classes meet. With that
   definition a sender's baselines have classes that share nothing, and a
   head change re-runs, free, at most one baseline of a sender for each
   element it changes. That is the bound MA-5 gives a sender, one free re-run
   a head change, carried to the class. The empty code of an account with no
   code, and a delegation, stay in the class: EIP-7702 can change either, so
   every transaction from an externally owned sender shares one class, as
   under the post. Contract code is left out because EIP-6780 keeps it after
   the transaction that created it and EIP-7702 delegates only an account
   whose code "is empty or already delegated" (both read at the pinned
   commit); the model's BB-5 does not check the second, and nothing here
   uses it on an account with code. A recent root entry changes, in the
   model, only by a head that goes back, and RR-7 evicts a transaction before
   its entry is overwritten.
3. **Three values of `contention`.** `sender` is the post's: every
   transaction from a sender is in one class. `storage` makes every slot of
   an account one element, so a prefix that reads no storage of its sender is
   waived and any two that read some share: this is the reading a client can
   make without knowing who may write a slot, and it answers reply #4 by not
   waiving the case it objects to. `slot` makes every slot an element, so the
   unit is what one write changes: an application that changes its own
   setting re-runs, free, one baseline for each slot it writes, and pays
   for each. `matcha` keeps `sender`, and every vector of version 2 holds.
4. **The class is fixed at admission.** In the model a prefix's reads and its
   payer are fixed by its frames, and the only element whose presence depends
   on state, an account's code, can only leave the class (from empty to
   deployed), so a class computed again at a re-run is never larger.
5. **A replacement of a baseline stays a baseline only if its class adds
   nothing another pending transaction from the sender has.** MA-7 says a
   replacement of the baseline is the baseline. Read per class without a
   condition, a sender could replace each of several waived baselines with
   one that reads the same slot, and a write to that slot would then re-run
   all of them free. Under `sender` the condition always holds.
6. **No transaction is promoted.** MA-5's rule that a sender has no baseline
   until its pending set is empty is read per class: a transaction that
   shares a class with any pending one is additional, baseline or not.
7. **Experiment 17 measures both sides against experiment 02**, on its
   network, spend and adversaries. A spend reads nothing (experiment 02's,
   whose nullifier is its nonce key), a slot of its own (a nullifier kept in
   storage), or that and a slot every deposit rewrites (a live root, any
   value accepted). The depositor writes it once a block. The mass
   invalidation adversary reads one setting (experiment 02's), a setting
   for each junk spend, or, under `one`, one setting in each of 100
   applications; its flip pays EIP-2929 and EIP-2200's 5,000 gas for a cold
   write to a non-zero slot and 2,600 for each further account it calls, on
   top of 21,000. That is the least a change costs block after block: a
   write that clears a slot earns EIP-3529's refund of 4,800, but the slot
   then costs 20,000 to set again.
8. **Not modelled**: a reduced charge, and FOCIL, the deterrent the post
   relies on for junk, as in experiment 02 (decision record 0008).

## Consequences

- `docs/spec/04-matcha.md` version 3: MA-14, `contention` in MA-1, MA-5 to
  MA-7, MA-9 and MA-12 read per class, and `baselines(sender)`.
- Vectors for MA-14 in `conformance/vectors/matcha/`.
- `contention` in `FramePoolConfig`; classes in the frame pool.
- In the simulator, a spend's reads in `SharedSenderLoad`, a `SlotWriter`
  load, and `JunkLoad` reading several settings and flipping those it holds.
- Experiment 17.
