# 0054. Shared-sender admission is judged on the mined pair, with a stand-in for the refused spend

Date: 2026-10-20. Status: accepted.

## Context

Item 45 opened with phase 2 on 2026-10-20. The claim it tests is that owned
state can live inside a shared contract when the nullifier is the nonce
key. FP-12 already gives `per_sender` as `one` and `disjoint-keys`, so the
item asks for no clause: it asks for vectors from `exp-frames` experiment
06's concurrent pair and its refused same-note replacement, one for each
value, and the pair's replay through item 42's surface. Would show it
wrong: under `disjoint-keys` two spends of one note are both admitted, or
under `one` the concurrent pair is admitted together.

The pair is two withdrawals from the experiment's keyed privacy pool, sent
about 220 ms apart and mined together in block 304,240
(`0x5fb29fe1...0f6c` and `0x2719e945...5db8`, both in `exp-frames`'
`test/fixtures/chain/` at `85ee60d`). The pool is their sender and their
payer, and each note's nullifier hash is the only nonce key. The experiment
also sent the same note twice, to two recipients, and ethrex refused the
second as an underpriced replacement (`exp-frames`,
`experiments/06-privacy-pool/README.md`, "Two withdrawals at once").

Three things the vectors need are not in what the experiment kept:

- the refused spend's bytes: it was proven for another recipient, refused,
  and never mined, and the fixtures are mined transactions only;
- a profile that runs the pair and has `per_sender = one`: `eip-8141` has
  `one`, but without recent roots it refuses the pair's leading verifier
  frame with `ErrFrameUnrecognizedPrefix` at FP-5, and its `max_verify_gas`
  of 100,000 is under the pair's prefix of 410,000, so FP-12 would never be
  reached;
- the pool's balance when the pair was sent, which a replay may not read
  (RP-1, decision record 0052).

## Decision

1. **The vectors are surface vectors on the mined bytes**,
   `conformance/vectors/frame-pool/fp-12-shared-sender.json`, under FP-12.
   The surface names each transaction by the chain's hash, and the vectors
   are the replay through item 42's surface: admission depends on the bytes,
   the client's verdict and the state a case gives. A case's head is the
   parent block's header as the testnet serves it: block 304,239, slot
   323,056, base fee 7. There is no live run, because both nonce keys are
   spent and the testnet would answer `ErrNonceTooLow`.
2. **`one` is `hegota-testnet` with `per_sender` set to `one`**, in a case's
   `config`, not `eip-8141`. The two profiles' cases then differ in FP-12
   alone, which is the clause the claim's "would show it wrong" names.
3. **The refused spend is stood in for by the first withdrawal's bytes with
   the last byte of its withdraw frame's recipient changed**, from `0xed` to
   `0xee`. FP-12 reads only what the stand-in shares with the real refused
   spend: the first withdrawal's identity, (pool, its nullifier, 0), and its
   fees. Both bytes are non-zero, so its zero bytes and its gas are the
   first's. Its verdict is `valid`, as the experiment simulated the real one
   before sending it. The vector's derivation says it is a stand-in; it is
   not a fixture, and the hash it gets is no chain's.
4. **The pool's balance is chosen**, 10^18 wei, enough for FP-11 to pass
   both, and the derivation says so.

## Consequences

- Done when, on the reference: the pair is admitted together under
  `disjoint-keys` and one after the other under `one`, and the same-note
  spend is refused with `ErrReplaceUnderpriced` under both. Three deliberate
  breaks of the reference were each caught and undone: `per_sender`
  ignored, disjointness never holding, and the fee rule of a replacement
  dropped.
- No clause changes and no document's version moves.
- What the vectors do not show: that the testnet serializes under `one`,
  since it runs `disjoint-keys` and `one` is the specification's; and that a
  second spend proven for another recipient is valid, which is the
  experiment's report, not something checked here. A second spend that pays
  the price bump replaces the first, so one note is still never pending
  twice.
