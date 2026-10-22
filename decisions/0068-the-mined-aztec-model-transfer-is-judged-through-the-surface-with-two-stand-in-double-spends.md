# 0068. The mined Aztec-model transfer is judged through the surface, with two stand-in double spends

Date: 2026-10-21. Status: accepted.

## Context

Decision record 0065 read an Aztec-model private transfer against the
clauses before any existed: one EIP-8250 nonce key for each nullifier, a
`VERIFY` frame that checks the proof, and its double spend refused before
inclusion. Its vectors were model transactions. The transaction itself now
exists: `exp-frames` experiment 42, on branch `exp/42-noir-transfer` at
`32586cc`, records a transfer proved in Noir and checked by gnark's Groth16
verifier, which the Hegota testnet mined in block 491,278
(`0x10d33e62...`).

Its shape, as the bytes say:
- **Frame 0:** EIP-8272's root frame (10,000).
- **Frame 1:** the pool's `VERIFY`, scope 3 (490,000, and state 195,840).
- **Frame 2:** a `SENDER` frame that inserts two notes.
- **Nonce keys:** the two nullifiers, ascending, at sequence 0.
- **No signature.**

The validation prefix used 362,119 gas. The same bytes sent again after
the block were refused: "Nonce mismatch: expected 1, got 0". The record
also keeps a pool whose `VERIFY` frame runs Barretenberg's zero-knowledge
verifier. Its transaction was refused twice:
- at a limit of 3,600,000, by the budget;
- at 490,000, because the frame reverted.

Two things the vectors need are not in the record:
- **A double spend in other bytes.** The only re-spend sent was the same
  bytes.
- **The pool's code**, which the model compares only by equality (MD-2).

## Decision

1. **Surface vectors on the mined bytes.** They are
   `conformance/vectors/frame-pool/fp-07-mined-transfer.json`, under
   `hegota-testnet`:
   - the head is block 491,277, the one the testnet built on, as the
     testnet serves it;
   - the pool's balance is read there;
   - the client's verdict is the testnet's simulation before the transfer
     was sent;
   - block 491,278 moves both nullifiers to sequence 1.
2. **The re-spend is the same bytes,** as the record has it:
   - `ErrAlreadyKnown` while the transfer is pending (FP-2);
   - `ErrNonceTooLow` after the block, refused before the client is asked,
     as the testnet refused it.
3. **Two stand-in double spends**, made from the mined bytes with
   `exp-frames`' own codec, with one field changed each:
   - **Other outputs:** the last byte of the `SENDER` frame's data
     changed. Same notes and same fees, so `ErrReplaceUnderpriced`.
   - **One shared note:** the second nullifier raised by one, so the first
     note is spent beside another. `ErrFrameSenderBusy` while the transfer
     is pending, and `ErrNonceTooLow` after the block.

   The first stand-in also comes with both fees raised by the bump, the tip
   from 1 to 2 and `max_fee` from 100 to 110. That one replaces the
   transfer (FP-12), and block 491,278 then drops it. Added 2026-10-22.

   Their verdict is `valid`, as decision record 0054's stand-in was. FP-12
   and FP-7 read only the identity, the keys and the fees. A real double
   spend would carry a proof of its own, which the client would judge.
4. **The pool's code is the string `note-pool`.** Nothing in these cases
   reads it but FP-10's class, which is `sender` whatever the code is.
5. **The zero-knowledge pool's two attempts are cases too.**
   - At a 3,600,000 limit the prefix sums to 3,610,000. That is
     `ErrFrameVerifyGas` before the client is asked, as the testnet
     answered.
   - At 490,000 the testnet's answer, "validation prefix frame reverted",
     maps to `ErrFramePrefixReverted` (SF-4).

## Not modelled

- **The proof's check itself.** The pool takes it from the client's
  verdict (SF-4, MD-8). The vectors say what a node does with that verdict.
- **Whether the root the transfer names is in the recent-root window.**
  The root frame is skipped as RR-4 says, and the client's verdict covers
  the rest.

## Consequences

- **The transfer, through the reference and skandha.**
  - Admitted at the head it was mined on.
  - Dropped when its block spends its nullifiers.
  - Refused before inclusion when a pending transaction shares one of its
    notes.
  - Refused after inclusion whenever it names a spent nullifier.

  This is the node's half of the transfer's end-to-end run.
- **Decision record 0065's reading is borne out by a mined transaction.**
  The approving frame carries 97,920 state gas for each fresh nullifier,
  195,840 for two. The prefix fits the testnet's 500,000 with Groth16 and
  not with Barretenberg's verifier.
- **Nonce keys are per sender: the record shows it.** The same two
  nullifier values were spent by two pools, the layout pool in block
  491,124 and the Groth16 pool in block 491,278. Each had deposited the
  same notes, and both spends were mined. So a nullifier set shared across
  senders is a contract's to keep, as decision record 0065 says.
