# 0057. A ticket paymaster is recognised by its code, and a self-issuer pays for junk proofs only once

Date: 2026-10-20. Status: accepted, the owner's ruling.

## Context

Version 3 of `10-claim-gated-admission.md` had a node hold, for each
epoch, a set of ticket paymasters with their keys, and took the set as
given. A node needs to know where the set comes from before it can check a
real ticket. The options were a list each node keeps, a registry contract,
or the paymaster's own code. The owner chose the code: a node accepts as a
ticket paymaster any account whose code is the ticket-paymaster template
followed by one issuer key, with no list and no registry.

The template is the runtime code of the paymaster a wallet ran on the
Hegota testnet (`exp-frames` experiment 36, re-run under `FRAME_TICKET_V1`;
`kohaku-rs` at `eea02a3`). Its `TicketPaymaster.yul` deploys its runtime
followed by the issuer key, 256 bytes in EIP-2537's G2 form, and a 32-byte
denomination, the largest `max_cost` it pays. The deployed code of
`0x273795f6eb2730d50c3544cbef1e0c1adba4f541` on the testnet is 1,393 bytes:
the 1,105-byte runtime, which is `TicketPaymaster.hex` after its 25-byte
constructor, then the key, then the denomination.

## Decision

1. **A ticket paymaster is an account whose code is $T \Vert K \Vert D$**
   (CG-10): $T$ pinned by its length, 1,105 bytes, and its keccak256; $K$ a
   key that decodes as a point of G2, in the subgroup and not the point at
   infinity; $D$ any 32 bytes. The denomination is not read: the paymaster
   enforces it itself, and a node has no reason to prefer one.
2. **CG-9 loses the node's set of keys.** The issuer is the key in the code
   of the paymaster the ticket's frame targets. The epoch stays in the
   ticket's message, and CG-2 still refuses a claim of another epoch.
3. **A change to the template is a format change.** It is made by a new
   decision record that pins the new hash, between the wallet that builds
   the code and this specification.
4. **The vectors of CG-9 and CG-10 are written again for version 4.** Their
   signatures still come from Commonware and their verdicts from the
   testnet's pairing precompile (decision record 0056). CG-9 loses the cases
   of a key outside the node's set. CG-10 takes each target's code instead
   of a set, and two runs on the testnet give it real cases: a mined
   ticket of the re-run, valid, and a spend of the first run, whose
   paymaster's runtime differs and is not a ticket paymaster.

## Consequences

- **A self-issuer's junk proofs cost it almost nothing after the first.**
  Anyone can deploy the template with their own key and sign their own
  tickets. Under CG-3 a refused wrapper leaves no pending transaction, so
  FP-11's pending places and reservations are not reached, and FP-8 checks
  the paymaster's balance without spending it. Each junk proof costs the
  self-issuer a fresh slot and a ticket it signs; the deployment and one
  transaction's float are paid once. Each costs a node CG-9's check, the
  prefix's simulation with the paymaster's `VERIFY` frame, and the proof's
  verification. A ticket still stops a junk proof from anyone who must buy
  one, and still stops a junk ticket at the cost of one signature check.
- **What would price a self-issuer's junk proofs**, not built: a memory of
  the paymasters under whose tickets a proof failed, refusing their tickets
  for the rest of the epoch, as `claim_memory` does for slots and claims.
  Each junk proof would then cost a deployment and a float that the run's
  paymaster cannot withdraw.
- **Crowds can fragment.** Any key is accepted, so senders may spread over
  many small issuers, and a node cannot tell which key has the larger
  crowd.
- A node keeps a paymaster's verdict by its code hash: one comparison and
  one G2 decoding for each new paymaster it sees.
