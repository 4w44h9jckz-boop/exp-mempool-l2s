# 0053. `hegota-testnet` models EIP-8272, and the surface reads its tuples

Date: 2026-10-20. Status: accepted.

## Context

Item 43's replay found 10 of the 182 Hegota fixtures refused by the
`hegota-testnet` profile with `ErrFrameUnrecognizedPrefix`, each explained
only by RP-5's `recent-roots`: their prefix opens with EIP-8272's recent-root
verifier frame, which the testnet runs and the profile did not model. It was
logged as an open question.

It then blocked the coordination project's end-to-end proof of concept.
The coordinator ran two skandha nodes at `eee680f` as skandha's `FRAMES.md`
says and sent node A the wallet session's withdrawal from kohaku-rs. A
refused it with `ErrFrameUnrecognizedPrefix` before asking the client. The
withdrawal's layout is that of `0x339af560...7119659`, mined in block
477,924 and kept as a fixture by `exp-frames` and kohaku-rs: a recent-root
verifier frame with one tuple, `self_verify` at 310,930 gas, a `SENDER`
frame and a `DEFAULT` frame. The `eip-8272` profile classifies the first
frame, but carries `eip-8141`'s `max_verify_gas` of 100,000 against this
prefix's 322,903.

Two facts were checked at the source before anything changed. ethrex at
`64b8fc09`, the client the testnet runs, places the verifier at
`0x0000000000000000000000000000000000008272`, keeps 8192 entries and at most
16 references, and packs a tuple as `source_id(32) || uint64_be(slot) ||
root(32)`, the values `08-recent-roots.md` already had for `eip-8272`. And the
testnet's headers carry a `slotNumber` that is not the block number (slot
507,761 at block 478,613), which EIP-8272's current slot reads.

## Decision

1. **`hegota-testnet` takes recent roots** (`08-recent-roots.md` version 2,
   RR-1's new column; `02-frame-pool.md` version 7, FP-1). The profile is a
   record of what the testnet runs, and the testnet runs EIP-8272 at the
   constants above. A transaction with no frame to the verifier's address is
   judged exactly as before; every vector of both documents holds and only
   says its new version.
2. **The surface decodes the tuples** (`11-surface.md` version 2, SF-3) into
   the `roots` RR-4 checks, and takes a head's slot from its `slotNumber`
   (SF-8). Without the second, RR-7 would compare a tuple's slot with a block
   number and evict every such transaction as from the future.
3. **A verdict stands for RR-5, not for RR-7** (RR-6). The client's verdict
   covers the contract's code and entries, which the pool cannot read, but
   the tuples' slots are in the transaction, so the pool still records the
   root expiry and evicts by it at a head without asking.
4. **The replay keeps its named difference** (`12-replay.md` version 2).
   `recent-roots` was named before any replay and stays a difference for
   `eip-8141`. For `hegota-testnet` it is no longer one: the profile now has
   the clause. The 10 fixtures it explained are judged again under the
   profile's own clauses, and the one vector that expected the old verdict
   was corrected by hand to the new one, with a case added for `eip-8141`,
   as `conformance/README.md`'s third case says when a clause moves.

## Consequences

- The vectors gain the withdrawal's decoding, with its tuple, and a surface
  case where it is admitted on a verdict, kept while its root is recent and
  evicted by RR-7 when the root leaves the window. Three deliberate breaks of
  the change were each caught and undone.
- The experiments that use `hegota-testnet` (03, 04, 05, 10, 11 and 12)
  are run again against this change.
- skandha's port and its node take the same change; the end-to-end proof
  of concept can be run again with the same commands.
