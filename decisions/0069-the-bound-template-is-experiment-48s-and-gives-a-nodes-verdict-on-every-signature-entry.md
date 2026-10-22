# 0069. The bound template is experiment 48's, and gives a node's verdict on every signature entry

Date: 2026-10-21. Status: accepted; point 3's second re-pricing is changed
by decision record 0080.

## Context

Decision record 0067 left CG-1's `bound_template` empty under
`claim-gated` until a wallet fixed the code of a bound ticket paymaster.
Until then a node there reads every ticket as unbound and refuses it.

That code now exists. `exp-frames` experiment 48 (branch
`exp/48-bound-ticket` at `9a6427f`) holds `BoundTicketPaymaster.yul`. It
deployed the template on the Hegota testnet at
`0xca7aa9eb83846186c1562abab968d1568ad55228`, beside a version 5
paymaster for the same committee key at
`0x4687b01b7e3642144e1386a8c128bd16a8c722a9`, and spent bound tickets
through it:
- **A fresh sender's spend,** mined in block 491,574.
- **A shared pool's withdrawal** with no signer but the binder, mined in
  block 491,578.
- **Three copies of the withdrawal,** each refused before inclusion.
- **The version 5 control's copy** with raised fees, mined in its
  original's place in block 491,576.

Readers of the binding listed cases on which a node (CG-12) and the
template must give the same verdict:
- an entry with a 32-byte `msg`;
- an entry with scheme `p256`;
- an index that points at another entry;
- a signer other than the binder;
- two candidate entries;
- a ticket whose epoch ends before inclusion;
- the holder's re-pricing under the same ticket.

## Decision

1. **`claim-gated` names experiment 48's template.**
   - It is 1,185 bytes, with keccak256
     `0x52c656815e560bb189c3fb362c9628432ca1ed6b720e239857775236c18bc1d3`.
   - These are the deployed code before the 256-byte key and the 32-byte
     denomination, read by `eth_getCode` at block 493,609 and hashed with
     the reference's keccak.
   - They agree with the experiment's record. The version 5 paymaster's
     code begins with CG-10's $T$, which also agrees.
   - `10-claim-gated-admission.md` becomes version 7 and
     `13-descriptors.md` version 4. `claim-gated.json`'s identifier
     becomes `bafkreigdwjfslxd6hbroctviyyikp2kudifirzznwlbfxouqx56yinjqui`,
     computed three ways: the reference, skandha's encoder, and Python's
     SHA-256 and base32.
2. **The template checks what CG-12 checks.** Read from the Yul:
   - its frame data is 188 bytes, and it rebuilds CG-8's 152-byte message
     from `CHAINID`, `TXPARAM` and that data;
   - after CG-9's pairing it reads every entry of the signature list with
     `SIGPARAM`, scheme first, and counts one only if its scheme is 1, its
     `msg` is 0 and its resolved signer is the binder.

   That is CG-12's steps 1 and 2. Step 3 is the protocol's, which validates
   every entry before any frame runs. On each listed case:
   - **A 32-byte `msg`** is skipped by both. EIP-8141's static constraints,
     at `258836f9`, refuse an explicit `msg` of 32 zero bytes, so
     `SIGPARAM`'s 0 means an empty `msg` and nothing else.
   - **A `p256` entry** by the binder's address is skipped by both, though
     it verifies.
   - **An index** exists in neither: CG-12 asks whether the transaction
     carries such a signature, and the template scans every entry. The
     mined fresh-sender spend has the binder's entry at index 1.
   - **A signer other than the binder** is skipped by both. When the frame
     names that signer as the binder, the pairing fails at the template
     and CG-9 fails at the node.
   - **Two candidate entries** bind the claim at both, in either order, if
     one of them is over the signature hash.
3. **Where they differ, the difference is a node's rule, by design.** The
   template keeps no record and reads no epoch.
   - **An epoch that ends while a ticket is pending.** CG-2 checks the
     epoch at admission only, so the transaction stays pending, and the
     template pays for it. Both pay.
   - **A ticket of a past epoch sent anew.** A node refuses it
     (`ErrClaimEpoch`); the template would pay.
   - **The holder's re-pricing without a dependency.** The first, at the
     price bump, replaces the original (FP-12), and the template pays for
     it. CG-6 counts that replacement as a removal (decision record 0037),
     so a second re-pricing under the same ticket is `ErrClaimExpired` at
     a node, while the template would pay for it.
   - **The holder's re-pricing with a dependency.** It is refused at once
     (`ErrClaimUsed`, CG-5, rule R4), since a node verifies one proof
     under each claim.

   So a fee bump under one ticket works once, and only for a transaction
   with no proof of its own to check. That is the price of R4 and R6,
   which bound a node's free work; it is not the binding's.
4. **The template's other checks are the client's verdict.** It also
   requires the scope `PAYMENT`, a `max_cost` no more than its
   denomination, and a binder other than zero. A node takes these from the
   client's verdict on the prefix (SF-4), as it takes every revert.
5. **Vectors.**
   - `conformance/vectors/claim-gated/cg-12-experiment-48.json` holds the
     eight transactions the experiment sent, with each paymaster's code as
     the testnet serves it. It judges them under the profile's own
     template, with no stand-in.
   - `cg-12-binder-entries.json` holds seven new transactions under the
     same template, made by `exp-frames`' encoder and signers:
     - the `p256` entry;
     - two entries by the binder, in both orders;
     - two entries with an empty `msg`;
     - a `msg` of 32 zero bytes;
     - the original;
     - the holder's re-pricing.
   - `cg-12-binding.json` gains three pool cases:
     - a re-pricing with no dependency;
     - a re-pricing with a dependency;
     - an epoch that ends while a ticket is pending.
   - Each raw case's expectations were computed before the reference saw
     them: the ticket's verdict with Commonware at `c18a6b9`, the binding
     with viem's recovery, and the `p256` entry with noble's P256
     verification.

## Not modelled

- **The template's gas,** which experiment 48 measured as 122,233 and
  122,350 against the version 5 template's 122,006. The prefix stays
  above `eip-8141`'s `max_verify_gas`, as before.
- **A re-pricing that raises `max_cost` above the denomination.** The
  template reverts, and a node takes that from the client's verdict.
- **A copy that pays through a payer of its own,** dropping the ticket. It
  spends the slot, and so burns the ticket, without spending it. The
  binding cannot stop this; only a proof that commits to the binder, or to
  the payer, could. That is the sender's contract's choice, not a node's.

## Consequences

- **A node under `claim-gated` now admits bound tickets** to experiment
  48's template, and still reads every version 5 ticket as unbound. The
  testnet's mined version 5 copy is `ErrClaimUnbound` there, which is
  the copy the binding exists to refuse.
- **One template ties the node to the wallet.** A change to it changes
  `bound_template`, `claim-gated.json`'s identifier, and the profile's
  version.
- **The vectors pin the node's verdict on each entry the template skips.**
  An implementation that reads only the first entry resolved to the
  binder, or that trusts the protocol's validation and reads the signer
  and `msg` without the scheme, fails them.
