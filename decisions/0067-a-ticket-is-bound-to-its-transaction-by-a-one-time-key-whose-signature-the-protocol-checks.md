# 0067. A ticket is bound to its transaction by a one-time key whose signature the protocol checks

Date: 2026-10-21. Status: accepted.

## Context

A ticket's message (CG-8, version 5) names one slot: the chain, the sender,
its nonce keys and sequence, the epoch and a salt. It names nothing the
transaction does or pays. A sender that signs its transaction covers the
rest. A sender that does not sign, such as a shared privacy contract paid
for by a ticket, leaves every field outside the slot to whoever forwards the
transaction: a copy with a higher priority fee, or other calldata, carries
the same ticket and is as valid as the original.

The binding asked for: the message also commits to a one-time key the buyer
chose, and a ticket counts only with that key's signature over the
transaction's signature hash. It must not need the issuer when the ticket
is spent, must not let the issuer link a ticket to its spend, and must fit
the validation budget a ticket paymaster has.

Read from EIP-8141 at `258836f9`:

- **The signature hash.** "Signature Hash": `compute_sig_hash(tx)` empties
  the `signature` bytes of every signature whose `msg` is empty, then hashes
  the whole transaction, frames, fees and nonces included.
- **The signature list.** "Transaction Signatures": "Every
  protocol-validated signature in this list must validate successfully
  before any frame is executed." A `SECP256K1` entry names any 20-byte
  `signer`, and "Signature Validation" checks it over the signature hash
  when its `msg` is empty, with low `s` and `v` 0 or 1. Its gas is 2,800.
- **Introspection.** `SIGPARAM` returns an entry's resolved signer, scheme
  and `msg` to EVM code; the raw bytes of a protocol-validated entry are not
  readable. `exp-frames` experiment 20 (at `85ee60d`) read entries this way
  from contracts on the Hegota testnet.
- **Where a signature over the hash can sit.** "Bespoke signature schemes
  must place their witness bytes in an `ARBITRARY` signature entry rather
  than in frame data when the witness signs the canonical transaction
  signature hash": frame data is inside the hash.

## Decision

1. **The binder is an address in the message.** A claim gains a `binder`,
   the 20-byte address of the one-time key, appended to CG-8's message,
   which becomes 152 bytes. The buyer chooses the key and blinds the whole
   message, so the issuer signs the binder without seeing it, as it signs
   the salt. A message without a binder is version 5's, byte for byte.
2. **The binder's signature is an entry of the transaction's list.** CG-12
   counts a claim as bound when the transaction carries a `secp256k1`
   signature with an empty `msg`, whose resolved signer is the binder, and
   which verifies over the signature hash. The protocol checks that
   signature before any frame runs, and a bound ticket paymaster needs only
   `SIGPARAM` to see that it is there. A node checks it too, at the surface,
   before it asks a client, so that an unbound copy costs it one recovery
   and no pairing.
3. **`secp256k1` only.** A one-time key gains nothing from a passkey, and a
   `p256` entry costs 6,700 gas of FP-6's budget rather than 2,800.
4. **The check sits between CG-2's steps 1 and 2.** It is cheaper than
   CG-9's pairing, and a node that refuses an unbound claim first never runs
   the pairing for it.
5. **`binding` is a parameter, true under `claim-gated`.** A profile with
   `claims` and without `binding` is version 5's admission, which is what an
   unbound control runs under.
6. **The bound template is a parameter, none for now.** A bound ticket
   paymaster rebuilds the 152-byte message, and checks the binding, in
   code a wallet session writes. Its length and keccak256 are CG-1's
   `bound_template`, and `null` in `claim-gated.json` until that code is
   fixed. Until then a node under `claim-gated` reads every ticket as
   unbound and refuses it. That is the price of the version:
   tickets issued under version 5 are not tickets under version 6. The
   vectors give a stand-in template in their configuration, as decision
   record 0054 used a stand-in for a spend it could not have.
7. **In the model, `bound` is a flag**, default true, as `valid` is: the
   pool's vectors give it, and CG-10's and the surface's compute it from
   bytes. Its default and an empty binder leave every claim's hash, and
   every earlier vector, as they were.

## Vectors and their sources

- The transactions, their signature hashes and their `secp256k1`
  signatures are made by `exp-frames`' own encoder and signer
  (`src/frametx/`, at `85ee60d`), whose transactions the testnet has mined.
  The reference shares no code with them.
- Each ticket's BLS signature is Commonware's `ops::sign_message` for
  `MinSig` at `c18a6b9`, as for decision record 0056, over the 152-byte
  message.
- One case per field of the transaction that a copy can change, each
  keeping the original's bytes for the binder's signature: the priority
  fee, the fee cap, a frame's mode, flags, target, gas limits, value and
  data, a frame added and a frame removed, and the slot's own fields, whose
  change also invalidates the ticket. Further cases cover the binder's
  signature removed, signed by another key, over an explicit digest, with
  a high `s`, or with `v` 27.

## Not modelled

- The bound template's code, and the gas its check of the binding costs in
  `VERIFY`.
- How a wallet derives one-time keys, and what it must keep to spend a
  ticket it bought.
- A signature with an empty `msg` and scheme `arbitrary`: its bytes are
  outside the hash, as the binder's are, and whoever its verifier lets
  change them can change a bound transaction's hash without unbinding it.

## Consequences

- A copy of a ticket-paid transaction with any signed field changed is
  refused at CG-12 by a node, and is invalid on chain, since the binder's
  signature no longer verifies; only the binder's holder can sign another.
- A ticket costs its spender one more signature, 2,800 gas of the
  transaction's verification cost, and its paymaster a few `SIGPARAM`
  reads.
- `claim-gated` admits no ticket until a bound template is fixed. When it
  is, `claim-gated.json` names it, and only the descriptor's identifier
  changes.
