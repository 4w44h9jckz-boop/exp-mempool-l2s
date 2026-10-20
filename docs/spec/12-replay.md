# 12. Replay: a pool's verdict on transactions a chain mined

Version 2, 2026-10-20. Version 1 named `recent-roots` as a difference
`hegota-testnet` did not model; see the version notes at the end.

The plan's item 43: for each frame transaction a chain mined, the verdict a
profile gives it, the chain's outcome, and the named differences between the
profile and the chain that may explain a mismatch. It is the differential
check "Growing the base" planned, with any implementation of
`11-surface.md` as the implementation under test, and its input is
`exp-frames`' mined fixtures. The named differences of RP-5 were written on
2026-10-20 before any fixture was replayed, so a mismatch they do not name is
reported as a disagreement, not answered by adding a name. Decision record
0052 has the readings this rests on.

## Clauses

**RP-1. A fixture.** A fixture is a frame transaction a chain mined, given
as: its bytes (SF-2); the chain it was mined on; its receipt's `payer`; and
the header of its parent block, `number`, `timestamp`, `gas_limit`,
`gas_used` and `base_fee`, or the statement that the header could not be
read. Its bytes MUST hash, by SF-3, to the hash the chain gives the
transaction; a fixture whose bytes do not is not replayed, and is reported as
not replayed. No state is read at the fixture's block or before it.
*Interpretation*, decision record 0052: on the Hegota testnet a state read at
a block older than the client keeps answers with the latest state and no
error (decision record 0051), so a replay that read state could not tell a
historical value from a current one. A header read is not a state read, and
the client serves old headers.

**RP-2. The chain's outcome.** Every fixture's outcome is `mined`, with its
receipt's payer. *Interpretation*, decision record 0052: the fixtures were
sent through a client's `eth_sendRawTransaction`, so a mined fixture is one
that client's pool admitted; a transaction a builder included without its
pool would not be, and none of the fixtures is said to be one.

**RP-3. The verdict.** Under a profile, a fixture's verdict is the first
refusal among SF-2 and SF-3, with the profile's `chain_id`, and then FP-3 to
FP-6 against the parent header, and `ok` if there is none. Where the header
could not be read, FP-3's comparison of `max_gas` with the head's `gas_limit`
is left out, and the result says so. The pool's payer is the one FP-10 reads
from the prefix's shape, the resolved target of its last frame. Not judged,
because nothing a chain keeps fixes them: FP-2; FP-7, since inclusion fixes
the sequence a transaction used; FP-8 and FP-9, since a receipt records no
trace, and its payer stands for a prefix that approved payment; and FP-11 to
FP-14, since the pool's contents when the fixture was sent are not kept.

**RP-4. The comparison.** A fixture whose verdict is `ok` *agrees* with the
chain if the pool's payer is the receipt's, and *disagrees* otherwise. A
fixture whose verdict is a refusal is *explained* if a named difference of
RP-5, or two of them together, turns the verdict into `ok`, and the result
names the fewest that do, one before two; and it *disagrees* otherwise.

**RP-5. Named differences.** Written before any replay:

| Name | What differs | Applied as |
| --- | --- | --- |
| `max_verify_gas` | FP-1: `eip-8141` 100000, `hegota-testnet` 500000, the testnet's nodes' flag | `max_verify_gas` set to 500000 |
| `max_verify_state_gas` | FP-1: enforced by `eip-8141`, not by the testnet | the check of FP-6's state gas left out |
| `expiry_verifier` | FP-1: `eip-8141` `0x81413f0cF12e9b6a49B1D0439E081c577D57FfFf`, the testnet and frames-devnet-0 `0x0000000000000000000000000000000000008141`, at the EIP-8141 commit both pin | `expiry_verifier` set to `0x0000000000000000000000000000000000008141` |
| `recent-roots` | the testnet runs EIP-8272, whose verifier frame targets `0x0000000000000000000000000000000000008272` (ethrex's divergence ledger, section 1); `eip-8141` does not model it, and `hegota-testnet` has since `08-recent-roots.md` version 2 | the transaction judged without every frame that targets that address |

**RP-6. Profiles by chain.** A fixture from the Hegota testnet, chain 8141,
is judged under `hegota-testnet`, and also under `eip-8141` with `chain_id`
8141, so that the replay records what the EIP's own profile would refuse. A
fixture from ethpandaops' frames-devnet-0, chain 7034189865, is judged under
`eip-8141` with `envelope` `plain` and `chain_id` 7034189865: that devnet ran
EIP-8141 at the testnet's pin without EIP-8250 (`exp-frames`, README,
"ethpandaops frames-devnet-0").

## Not modelled

- A fixture's admission at the moment it was sent: the client's pool, the
  other transactions in it and the head it was sent at are not kept.
- The trace rules ethrex was measured to apply differently from the EIP
  (`exp-frames` experiment 19: a call to an account with no code but a
  nonce or balance, and a call to the expiry verifier from a VERIFY frame,
  both admitted): no receipt records a trace, so the replay cannot see them.

## Version notes

- **Version 1.** First version: RP-1 to RP-6.
- **Version 2.** `hegota-testnet` models EIP-8272 (`08-recent-roots.md`
  version 2), so `recent-roots` remains a named difference for `eip-8141`
  only. Version 1's replay explained 10 Hegota fixtures by it; they are now
  judged under the profile's own clauses. The differences themselves are
  unchanged (decision record 0053).
