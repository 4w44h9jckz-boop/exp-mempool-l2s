# 0051. The surface takes real bytes and a client's verdict, and the model prices zero bytes

Date: 2026-10-20. Status: accepted.

## Context

The plan's item 42 asks for the clauses a pool needs to take real frame
transactions, so that skandha can admit a transaction over JSON-RPC, relay
it to a second node, and see it mined on the Hegota testnet (decision record
0050). Until now the model had no bytes, no hash but its own, and no EVM: a
frame carried what a node simulating it would observe (MD-6, decision record
0003), and every vector wrote those observations down.

A real node has the bytes and nothing else. skandha has no EVM. The testnet's
client, ethrex at `64b8fc09`, answers `ethrex_simulateFrameTransaction` with
whether the validation prefix passed and why not, and with the transaction's
`maxCost`. It does not serve `debug_traceTransaction` or any trace (the
endpoint answers "not available", probed 2026-10-20), so the observations
MD-6 lists cannot be read off a client. Its validation observer records the
sender slots a prefix touched, `touched_sender_slots`, but the RPC does not
return them.

Two measurements on 2026-10-20 bear on what the model must change
(`refs/refs.md`, "The Hegota testnet"):

- FEE-4 priced every calldata byte as non-zero. EIP-8141's `tokens_in` counts
  a zero byte as one token and any other as four. Across `exp-frames`' 182
  Hegota fixtures, FEE-4 with the zero-byte term matched ethrex's `maxCost` in
  all 182, and the term changed the answer in 159. A surface on version 8's
  FEE-4 would reserve more than the transaction can cost against nearly every
  payer, and refuse with `ErrFramePayerExposure` what the chain admits.
- At a block older than the client keeps state for, `ethrex_simulateFrameTransaction`
  refuses ("state root missing"), but `eth_getBalance`,
  `eth_getTransactionCount` and `eth_getCode` answer, with the latest state:
  nonce 12 at the parent of a block whose transaction from that sender used
  nonce 9.

## Decision

1. **A document of its own.** `docs/spec/11-surface.md`, prefix `SF`, specifies
   the layer around the pool: decoding (SF-2), the model transaction and its
   hash (SF-3), the client's verdict (SF-4), `eth_sendRawTransaction` (SF-5),
   relay (SF-6), what is taken from peers (SF-7), head changes (SF-8) and
   hand-off to a client (SF-9), with a run procedure for what cannot be stated
   offline. The pool's clauses keep what they read from the EIP; the model
   gains two fields and `reset` one argument.
2. **The client's verdict is an input.** MD-6 gains `verdict`, the client's
   answer for the prefix at the pool's head, and FP-8 and FP-9 take it as the
   outcome of the prefix frames. The pool still runs FP-2 to FP-7 first, then
   FP-8's payment check, FP-10 to FP-14 and FP-15 itself. MD-7 leaves the
   verdict out of the transaction's identity: a new answer at the next head is
   not a new transaction. The alternatives were observations read off a trace,
   which the client does not serve, and an EVM inside skandha, which would be a
   second client rather than a pool. The cost is stated in FP-8: a client folds
   some failures together, so a pool with a verdict can answer
   `ErrFramePrefixReverted` where one with observations answers
   `ErrInsufficientFunds`.
3. **SF-4's table is read from ethrex's source, not from its messages in
   experiments.** The `FrameSimViolation` variants, written with Rust's `Debug`
   format, match by name; three fixed texts match whole; anything else is
   `ErrFrameClientRefused`, with the text kept. A gate FP-3 to FP-7 already ran
   that the client refuses means the client's parameters differ from the
   profile's, and is reported as a refusal rather than guessed at.
4. **FEE-4 counts zero bytes.** MD-6 gains `zero_bytes`, $Z$, and the
   intrinsic gas becomes $16 D - 12 Z$ where it was $16 D$; the floor is
   unchanged, because EIP-7976's floor counts every byte the same. A
   transaction with $Z$ at its default of 0 costs what it cost under version 8.
5. **SF-2 separates bytes that are not a frame transaction from a frame
   transaction that is invalid.** A failure to parse (`ErrTxTypeNotSupported`,
   `ErrFrameDecode`) puts the peer that sent it at fault; a field out of range
   (`ErrFrameMalformed`), a wrong chain (`ErrInvalidChainId`) or any refusal of
   the pool does not. This is go-ethereum's line: a message that does not
   decode ends the session in `eth/handler_eth.go`, and nothing the pool refuses
   disconnects anyone in `eth/fetcher/tx_fetcher.go`. Size is checked before
   decoding, which go-ethereum does after; the vectors pin the order.
6. **skandha relays over gossipsub.** skandha's peers speak libp2p, not
   devp2p, so SF-1 has `relay` as `eth` or `gossipsub`, and SF-6 names the
   topic, `/frame-transactions/<chain_id>/raw`, whose message is the bytes.
   Gossipsub's validator outcomes map onto SF-7: accept, reject for a decoding
   failure, ignore for any other refusal, as skandha's own validator already
   does for user operations.
7. **At every head, every transaction still pending is asked about again.**
   The client does not return the slots a prefix read, so a surface cannot
   index by them. SF-8 asks the client about every pending transaction that
   the new state does not show included, and the pool re-runs only those
   whose verdict or readable dependency changed, so FP-15's observable
   re-simulations are unchanged. The client's work is one simulation per
   pending transaction per head, the work FP-15 exists to avoid, and it is the
   price of keeping the EVM outside the pool. A client that returned
   `touched_sender_slots` from its simulation would remove it; that is a
   request to ethrex, and filing it is the owner's act.
8. **Hand-off is a parameter.** SF-9's `handoff` lets a run show a transaction
   reaching the chain through a second node rather than the one it was sent
   to, which is what item 42's "done when" asks.
9. **The vectors' expected values come from outside this repository.** The
   decoding vectors use `exp-frames`' encoding of mined fixtures, kept only
   where keccak256 of the bytes is the chain's hash, so the bytes are the
   chain's; their expected fields are those of the transaction so encoded, and
   their `max_cost` is ethrex's `maxCost`. The malformed cases are ethrex's
   golden vector with pieces written in by hand, and their results come from
   the clauses. No expected value was produced by the reference. Six
   deliberate breaks of the reference were each caught by at least one case
   and then undone: zero bytes priced as non-zero, one verdict mapped to the
   wrong code, an included transaction asked about, a transaction relayed back
   to its source, a new verdict ignored at a head, and decoding before the
   size check.
10. **Historical state is not read.** Because the testnet's state reads at an
    old block answer with the latest state, without an error, the replay of
    item 43 must not read state at a fixture's block; it can judge only what
    the transaction, its block and its receipt fix. That is item 43's
    decision, recorded here because it was found here.

## Consequences

- `00-model.md` is version 9, `02-frame-pool.md` version 6; every vector of
  both says so, and none needed another change.
- `conformance/` gains the `surface` operation and `vectors/surface/`, seven
  files, and the reference gains `ref/python/emem/surface.py` and a keccak256
  of its own, standard library only. `scripts/check_vectors.py` covers `SF`.
- skandha's copy of the vectors moves to the commit that carries this, and
  its port gains the verdict, the zero-byte term and the surface. Its runner
  must skip a case by what it needs, including a profile it lacks, under
  decision record 0035.
- *Not modelled*, as SF-2 to SF-7 say: blob-carrying frame transactions,
  go-ethereum's RPC fee cap and EIP-155 check, its pause for a peer whose
  deliveries are mostly refused, a canonical paymaster's withdrawal read by
  the surface, and the cryptographic check of a signature, which reaches the
  pool through the verdict.
