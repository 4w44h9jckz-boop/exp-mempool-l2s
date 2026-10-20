# 0058. The surface reads a paymaster's code from the client, and checks a claim before asking about the prefix

Date: 2026-10-20. Status: accepted.

## Context

Version 4 of `10-claim-gated-admission.md` recognises a ticket paymaster by
its code (CG-10, decision record 0057), and the pool checks a claim after
FP-6 (CG-2, CG-4 and CG-6). The pool's model has no real code: MD-2's
`code` is a string compared by equality. A node that takes real
transactions (`11-surface.md`) does not execute the EVM and asks an
execution client for the validation prefix's outcome (SF-4). Two things
were open: where the surface gets the code of a frame's target, and
whether the claim is checked before or after the client is asked.

On the Hegota testnet the client, asked about a transaction carrying a
ticket that does not verify, simulates the prefix, runs the paymaster's
`VERIFY` frame and its pairing, and answers `validation prefix frame
reverted` (`kohaku-rs` at `eea02a3`,
`crates/frame-ticket/tests/fixtures/record.json`, three such refusals).
That is the whole of the prefix's work, spent on a junk ticket.

## Decision

1. **The code is the client's.** SF-3's `claim` reads CG-10 with the code
   the execution client answers (`eth_getCode`) at the pool's head for each
   `VERIFY` frame's target. A node may keep, by address, each target whose
   code it found to be a ticket paymaster's, and read every other target
   again at each head. Code does not change outside the transaction that
   created it (EIP-6780) and EIP-7702 sets code only where it is empty or a
   delegation, so a paymaster's code changes only in a reorganisation; an
   address without code may gain some at any head. A ticket paymaster then
   costs a node one `eth_getCode` and one G2 decoding.
2. **The claim is checked before the client is asked.** Under a frame
   profile with `claims`, SF-4 runs CG-2, CG-4 and CG-6 after FP-6 and
   before it asks the client, in the order the pool runs them. A junk
   ticket then costs a node one signature check (CG-9) and no simulation,
   which is what a ticket is for.
3. **Nothing changes for a transaction without a ticket.** CG-2 asks a
   claim only of a transaction with dependencies, so a transaction no frame
   of which targets a ticket paymaster is asked about as before; under a
   profile without `claims` the surface reads no code.
4. **The vectors are real transactions.** `sf-03-model-transaction.json`
   and `sf-05-send-raw.json` take a spend the testnet mined, the three it
   refused and the two sent at once from the record above, with the
   paymaster's code and balance read from the testnet at the head the
   spend was built on. Each claim's verdict is the testnet's EIP-2537
   pairing precompile, not this repository's reference.

## Consequences

- **A ticket paymaster sponsors one pending transaction.** It is not the
  canonical paymaster, so FP-11 lets it sponsor one pending transaction at
  a time, and the testnet's client refused the second of two valid spends
  sent at once ("Non-canonical paymaster already sponsors the maximum
  number of pending frame transactions"); the pool does the same, after
  the client is asked. Every sender behind one ticket paymaster shares one
  pending place per node. A crowd that wants more than one spend pending at once
  needs more than one paymaster, or a rule for ticket paymasters in FP-11,
  which neither the EIP nor this repository has.
- The check before the client reads one more thing than FP-2 to FP-7 do:
  the code of each `VERIFY` frame's target, once per paymaster and once per
  head for every other target.
- *Not modelled*: a paymaster deployed after the pool's head, whose spend
  carries no claim until the head moves (the client's simulation would
  refuse it too), and a reorganisation that removes a paymaster's
  deployment.
