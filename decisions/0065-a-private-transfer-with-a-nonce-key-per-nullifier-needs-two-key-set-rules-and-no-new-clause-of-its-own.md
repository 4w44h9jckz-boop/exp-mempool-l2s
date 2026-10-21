# 0065. A private transfer with a nonce key per nullifier needs two key-set rules, and no clause of its own

Date: 2026-10-21. Status: accepted.

## Context

An Aztec-model private transfer, moved out of a rollup into frames, is a
transaction from a shared privacy contract: its `VERIFY` frame checks a
proof made on the user's device, approves execution and pays, and each note
it spends has a nullifier that becomes one EIP-8250 nonce key. A transfer
that spends two notes carries two keys at sequence 0. A node is to admit
it, gossip it, and refuse its double spend before inclusion. The question
asked first is whether the specification already says all of that.

Read against the clauses:

- **Admission and the double spend.** FP-7 requires every key to be at the
  transaction's sequence, so once a block consumes a nullifier any
  transaction that names it again is `ErrNonceTooLow`, and FP-15 step 1
  drops a pending one that names it. FP-12 under `disjoint-keys` admits
  transfers whose key sets share nothing, refuses one that shares a key with
  a pending transfer as `ErrFrameSenderBusy`, and lets a transfer with the
  very same key set replace the pending one only if it pays the bump. Under
  `one`, the shared sender holds one pending transfer. Decision record 0054
  already judged the single-key case on `exp-frames`' mined pair.
- **Gossip.** `11-surface.md`'s relay (SF-5) passes on what a node admits,
  whatever its nonce keys.
- **The fee.** The contract pays for itself: its payer class is `sender`,
  so FP-11's cap of one pending transaction for a non-canonical payer does
  not apply, and FP-11's reservation does: the contract's balance must cover
  the summed `max_cost` of its pending transfers.

What the clauses lack is in EIP-8250 at `258836f9`, "Transaction payload":
its decoders reject a transaction with more than `MAX_NONCE_KEYS`, 16, keys,
and one that holds key 0 beside another key. FP-3 checked neither.

EIP-8250 also charges `KEYED_NONCE_FIRST_USE_STATE_GAS`, 97,920 state gas,
for each key used for the first time, from the approving `VERIFY` frame's
state limit; "the existing `MAX_VERIFY_STATE_GAS` cap on the sum of state
limits in the validation prefix is unchanged". `00-model.md` lists this
charge as *Not modelled*.

## Decision

1. **FP-3 takes the two key-set rules**, read from the EIP, in
   `02-frame-pool.md` version 8: at most 16 keys, and key 0 only alone. They
   are constants, like FP-3's 64 frames, not profile parameters, so no
   descriptor changes.
2. **No clause is new for the transfer itself.** FP-7, FP-11, FP-12, FP-15
   and SF-5 say what a node does with it. The vectors that say so are
   `conformance/vectors/frame-pool/fp-12-nullifier-keys.json`: two-nullifier
   transfers admitted together, a double spend that shares one nullifier
   refused before inclusion and impossible after it, the same key set only
   replaced at the bump, one pending transfer under `one`, and the key-set
   limits.
3. **The first-use charge stays *Not modelled* in FP-8**, and the vectors of
   this record declare it. A real transfer's approving frame carries 97,920
   state gas a fresh nullifier, or its approval halts, so the vectors give
   their approving frames that state limit, and FP-6 then caps a transfer
   at $\lfloor 500000 / 97920 \rfloor = 5$ fresh nullifiers under `eip-8141`.
   Under `hegota-testnet` the cap on state gas is not enforced, and 16 is the
   limit. Making FP-8 compute the charge would re-read every vector
   transaction with a fresh non-zero key and the simulator's spends, about
   360 transactions in 20 files; that is left to a decision of its own.
4. **What a two-key cancellation means.** A double spend that names one
   spent and one fresh nullifier is `ErrFrameSenderBusy` while the first is
   pending and `ErrNonceTooLow` once it is mined: it can never land, and it
   cannot replace the first either, since replacement needs the same key
   set. A wallet that wants to change a pending transfer must keep its
   nullifiers and pay the bump.

## Not modelled

- A key at `MAX_NONCE_SEQ`, which EIP-8250 at `258836f9` calls exhausted:
  stateful validity requires `nonce_seq < MAX_NONCE_SEQ`, and no sequence in
  the model's vectors comes near it.
- EIP-8250 on master, read at `25b19523` on 2026-10-21, differs: an empty
  key set selects the legacy nonce, `nonce_seq == MAX_NONCE_SEQ` marks every
  key single-use and is the form it names for nullifiers, and each key adds
  12,100 gas, `KEYED_NONCE_ACCESS_COST`, to intrinsic gas and to the
  calldata floor. Neither profile reads master; a later reading moves both
  together, as decision record 0063 did for EIP-8288.

## Consequences

- An Aztec-model transfer spends at most 16 notes by nonce key under any
  profile, and at most 5 fresh ones under `eip-8141`'s state-gas cap.
  Aztec's own transactions may emit more nullifiers than that; such a
  transfer needs keys for the notes it spends only, or two transactions.
- A shared nullifier set across senders is outside what nonce keys give:
  a key belongs to one sender, so two privacy contracts can both accept the
  same nullifier. That is the contract's to prevent, and a frame cannot.
- The wallet's transaction bytes, when they come, are judged through the
  surface as decision record 0054 judged `exp-frames`' pair.
