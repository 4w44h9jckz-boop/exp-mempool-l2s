# 0049. Commonware gives four measurements and a method, and its conformance commitments are fixtures

Date: 2026-10-14. Status: accepted.

## Context

The owner asked what this repository can take from Commonware. Until now it
had used one Commonware post, `/blogs/batch-pari`, for the cost of verifying
proofs in a batch (decision record 0025, experiment 16), and it cited two
others only through an earlier study's reading of them: a share from each
member for each ciphertext, and a reshare at every change of the set
(decision record 0032). A snapshot of 41 pages of commonware.xyz was taken
on 2026-09-15, and the posts that bear on a mempool were read in it on
2026-10-14 (`refs/refs.md`).
Deciding what to take is a choice: Commonware builds a library for chains
with a known, staked validator set of tens of members, and Ethereum's public
mempool has neither.

## Decision

1. **The posts are read in that snapshot, as primary text.** As for
   experiment 16, the snapshot's text is the post. Commonware's figures are
   quoted as its own: single-threaded on an M5 MacBook Pro unless a post
   says otherwise, over BLS12-381, none post-quantum, none reproduced here.
   Commonware's posts are design writing by their authors, read as their
   stated position, which is how the snapshot records them.
2. **Four measurements are taken, each as an item of the plan, because
   each needs a pool to answer and this repository has one.**
   - Item 37: the size of a batched share, 48 bytes, and of a ciphertext,
     replace experiment 23's assumption where a scheme names a size.
   - Item 38: "Pick Your Poisons" names the window $q$ that an
     epoch-restricted scheme needs and the position conflict that an indexed
     scheme suffers, and neither has the inclusion delays that decide them.
   - Item 39: Bonsai removes the shared sender at a price its authors state,
     the acting account, and the claim that counterparties stay hidden is
     one the ticket linker of decision record 0040 can test.
   - Item 40: blocking the peer that sent a bad proof is bounded by staked
     identity in Commonware and by nothing in a public mempool, where
     go-ethereum's precedent, dropping a peer that fails KZG verification,
     meets free node IDs and a 30 s inbound throttle.
3. **One method is taken: conclusions are checked on more than one seed**
   (item 41). Commonware runs its tests on about ten seeds each CI run; this
   repository checks that seed 1 reproduces, which says nothing about
   whether a README's comparison holds on seed 2.
4. **`conformance` is not taken, because its commitments are fixtures.** It
   commits to a hash of cases generated from seeds by the implementation,
   and a change that moves the hash is accepted by regenerating it under a
   "breaking-format" or "breaking-api" label. That is derived from the code
   and asks whether the code still does what it did. A vector here is
   written by hand from a clause and is never regenerated, and the
   simulator's regression record is already each experiment's committed
   `results.md`.
5. **Stability levels are not taken.** Commonware grades each primitive
   from ALPHA to EPSILON and lets nothing depend on a less stable one.
   Here each specification document carries a version, the two that are
   proposals say so, and no experiment needs a ladder.
6. **A key for a slot is not proposed as a committee variant.** Binding
   timelock encryption (`/blogs/only-time-will-tell`) decrypts with a
   threshold signature over a view, and "Phone a Friend" states what such a
   key costs an application whose ciphertexts may miss their time: "It's
   now entirely possible that a user's bid is not included on chain before
   T and therefore never included as part of the auction, but after time T
   their bid can be decrypted". LUCID releases a key for each committed
   ticket, so a slot-wide key would open sealed transactions that were
   never committed. Commonware's own precondition, a threshold key held by
   the validator set, rests on a DKG whose post reports a dealing at $n = 8$
   and gives "projections out to $n = 64$" (`/blogs/golden`).
7. **Helper-aided decryption is noted and not run.** "Phone a Friend"
   relies on its helper "only for liveness", which passes the placement
   test of decision record 0048, but at LUCID's 32 sealed
   transactions a block it saves nothing worth a run: 121.61 ms to decrypt
   against 7.274 ms to verify a batch of 32.
8. **Below the mempool is out of scope.** The consensus and dissemination
   posts (Minimmit, Multimmit, the Carnot bound, erasure-coded blocks,
   pipelined Simplex) are about blocks, not the pool. Constantinople's
   passkey signatures and Bajillion's clearing are not mempool behaviour
   either.
9. **Funding is disclosed, not weighed.** `/blogs/route-66` announces a
   strategic investment from Coinbase Ventures, and an earlier reading of
   the same corpus records Tempo's.
   Neither is a reason to doubt a measurement, and none is used as one.

## Consequences

- The plan's items 37 to 41, with the order: item 37 first, item 39 after
  the Bonsai paper is read.
- `refs/refs.md` lists the posts read, and records that the consensus post
  the entry for experiment 16 calls unread, `/blogs/buffered-signatures`,
  is now read.
- No clause, vector, code or result changes with this record.
