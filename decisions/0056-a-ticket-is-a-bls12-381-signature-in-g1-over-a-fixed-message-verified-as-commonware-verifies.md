# 0056. A ticket is a BLS12-381 signature in G1 over a fixed message, verified as Commonware verifies

Date: 2026-10-20. Status: accepted.

## Context

Item 49 implements `10-claim-gated-admission.md` in a second implementation
"with a BLS12-381 library for the ticket". Version 2 of that document reads
a claim's `valid` flag and says nothing of the bytes behind it, so two
implementations could agree on every vector and still disagree on every
real ticket. Three things had to be fixed: the bytes an issuer signs, where
a transaction carries the ticket, and what a node accepts as an issuer.

A wallet had already run blind tickets on the Hegota testnet when this was
decided (`exp-frames` experiment 36 at `f0749cb`, its issuers and buyers in
`kohaku-rs` at `b6a63b1`): a committee of issuers holding a threshold key
signs blinded messages, and a paymaster pays a fresh sender's gas in a
`VERIFY` frame after checking the ticket on EIP-2537's precompiles. Four of
its tickets were mined. A first draft of these clauses, with a message that
listed the nonce keys one by one, was written before that run was known
here, and was withdrawn unpublished.

## Decision

1. **The message is the run's** (CG-8): chain ID, sender, EIP-8250's
   `nonce_keys_hash`, sequence number, epoch and a 32-byte salt, 132 bytes
   at fixed widths. A paymaster rebuilds it from `CHAINID` and `TXPARAM`,
   `0x0F` returning the keys' hash, with no loop, and a node computes the
   same hash once. A node and a paymaster must check one ticket over the
   same bytes, or a ticket one accepts the other refuses.
2. **The namespace is `FRAME_TICKET_V1`,** not the run's own: a
   specification names no wallet. The run is repeated with it; nothing else
   in the run changes.
3. **Signatures in G1, keys in G2,** the IETF draft's minimal-signature-size
   variant, and **verification is Commonware's `ops::verify_message` for
   `MinSig`** at `c18a6b9`, which the run's issuers use: its domain
   separation tag is the draft's proof-of-possession ciphersuite's, and its
   message is the namespace's length as a varint, the namespace and the
   message, `union_unique`. Tickets are never aggregated, so a rogue key,
   which proofs of possession exist to stop, has nothing to attack here.
4. **Points are in EIP-2537's encoding** (CG-9), 128 bytes for the
   signature and 256 for a key, as the paymaster hands them to its
   precompiles; a node may hold them in any form. EIP-2537's own rules
   decide what decodes: padding zero, coordinates below $p$, on the curve,
   in the subgroup. The point at infinity, which EIP-2537 encodes as zeros,
   is refused, as Commonware's decoding refuses it.
5. **The ticket rides in a `VERIFY` frame to a ticket paymaster** (CG-10):
   epoch, salt and signature, 168 bytes of frame data, as the run carries
   it. The paymaster the frame targets names the key, so a ticket carries no
   key and a node checks one signature. A paymaster holds one key, so a set
   of issuers is a set of paymasters, and a node accepts a set of them for
   each epoch.
6. **The reference verifies with the standard library**
   (`ref/python/emem/bls.py`): RFC 9380's hash to G1 with the isogeny's
   constants as the RFC prints them, both encodings, and the optimal ate
   pairing. It is slow, about a second for each verification, and nothing
   but conformance calls it.
7. **The vectors are not the reference's output.** Signatures come from
   Commonware at `c18a6b9`, each valid one also issued blind there (the
   hash times a factor, signed, times the factor's inverse) and found equal
   to the plain one. Every verdict on decoding and on the pairing is the
   Hegota testnet's EIP-2537 pairing precompile, called with `eth_call`.
   `nonce_keys_hash` is computed with another library's keccak. The run's
   mined tickets are cases of their own: they verify under the run's
   namespace, which shows the message is the one the chain rebuilt, and
   not under this one.
8. **The second implementation verifies with another library.** skandha's
   `packages/framepool` uses `@noble/curves` rather than Commonware compiled
   to WebAssembly, so that the vectors judge a verifier that shares no code
   with the program that signed them. A key from threshold issuance is the
   group's key in G2, and is checked as any other.

## Consequences

- A claim's `valid` flag has one meaning on the wire, and the clauses that
  read it do not change; the vectors of CG-2 to CG-7 hold as they are.
- An issuer that signs blind signs whatever point it is sent, so its key
  must sign tickets and nothing else (CG-9).
- A library's decoding is not CG-9's: `@noble/curves` 1.8.1 decodes a
  compressed point by reducing its coordinate modulo $p$ rather than
  refusing one of $p$ or more, so a signature written with its $x$ plus $p$
  verifies there and not in Commonware. EIP-2537's encoding is decoded by
  hand in skandha, and the padding rule is its own check.
- The run's paymaster spends 122,006 gas in its `VERIFY` frame, which fits
  the testnet's validation budget of 500,000 and not EIP-8141's
  `MAX_VERIFY_GAS` of 100,000, and the frame pool lets a payer that is not
  the canonical paymaster sponsor one pending transaction at a time (FP-11).
  Both are listed under "Not modelled" in
  `docs/spec/10-claim-gated-admission.md`, with how a node learns which
  paymasters to accept.
