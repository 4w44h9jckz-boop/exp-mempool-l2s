# 0047. Aztec is fitted job by job from its current code

Date: 2026-10-13. Status: accepted.

## Context

The owner asked how Aztec would run as not a rollup, and for the answer to
fit this repository's framework. An earlier post uses Aztec as evidence
that private applications already work like a mempool rollup, from Aztec's
2024 block-production RFC, and lists the current code as unread. This
repository specifies pools from primary sources and measures them, so the
question to settle was what to read, what "not a rollup" means, and where
the answer lives before any clause does.

## Decision

1. **The current code, at commits that agree.** Aztec's node, client and
   documentation moved from AztecProtocol/aztec-packages to
   aztec-labs-eng/aztec-node, which aztec-packages pins as its `labs`
   submodule. Both are read at once: aztec-packages at `5a63848e`
   (2026-10-13) for the L1 contracts and protocol constants, and aztec-node
   at `54e3383c` (2026-09-23), the commit that pin names, for the
   validators, the pool, the transaction and the documentation. The 2024
   RFC is not used: where it and the code differ, the code is what runs.
   Deployed parameters (slot, epoch, committee size, the escape hatch's
   schedule) are constructor arguments and are not read.
2. **"Not a rollup" is the mempool rollup.** Aztec keeps its private
   execution on the user's device and its proofs, and has no blocks of its
   own: L1's mempool admits its transactions, L1's proposer and builder
   order them, mempool nodes aggregate their proofs under EIP-8288, and its
   state lives in an L1 contract. That is one reading of many (a based
   rollup or a native rollup would keep blocks), chosen because it is the
   one the earlier post claims and this repository's clauses describe.
3. **A reading first, in `docs/`, not in `docs/spec/`.** The fit is
   `docs/aztec-as-not-a-rollup.md`: a table of Aztec's jobs against the
   clauses and experiments here, and what is left over. It is not normative.
   A specification document needs vectors in the same or the next commit
   (`make verify`'s vector-set check covers every clause), and which of
   Aztec's rules deserve clauses is what the reading is for.
4. **Nullifiers are split by who can compute them.** The default note's
   nullifier hashes the owner's application nullifier key
   (`aztec-node/noir-projects/aztec-nr/aztec/src/macros/notes.nr`), so it
   passes the test that a nullifier the mempool checks is one only the
   sender can spend. Custom notes and the nullifiers that mark a public fact
   once are counted as shared, since anyone able to emit them can race for
   them.
5. **Two items, in the usual order.** The plan's item 35 reads Aztec's pool
   into a specification document with vectors and the reference; item 36 is
   the experiment that puts it on L1 beside FP-12. Item 36 waits for 35.

## Consequences

- The earlier post's blind spot is answered from the code: the node runs cheap
  checks, a pool pre-check and then the proof, and the builder does not
  verify proofs again or execute anything for a transaction without public
  calls.
- The fit names one change to proving, not to the pool, as the largest:
  Aztec's client proof is neither of EIP-8288's two schemes.
- Two numbers in the fit are derived rather than read: the 11,892 seconds by
  which EIP-8272's window outlasts Aztec's transaction lifetime at 12-second
  slots, and the 6,266,880 state gas of 64 nullifiers at 97,920 each. Each
  says what it is derived from.
- Nothing here is measured yet. The 250 ms proof check is the README's
  benchmark, on hardware it does not state.
