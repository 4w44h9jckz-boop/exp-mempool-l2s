# 10. Claim-gated admission (proposal)

Version 3, 2026-10-20. Version 1, 2026-10-13, had every node verify;
version 2, the same day, added `verifies` and CG-7; version 3 adds CG-8 to
CG-10, the bytes a ticket signs, how a node verifies one and where a
transaction carries it, and changes nothing else.

**Status: proposal.** This document states, as clauses, an admission policy
that no client implements and no EIP specifies: claim-gated admission,
stated as six rules, R1 to R6, with a variant that remembers bad claims
rather than slots, and with nodes that need not verify. Decision record 0037
records the readings it rests on, and its vectors check the clauses. A
clause marked *Interpretation* is this repository's reading where the rules
leave a choice open, and names decision record 0037. The profile,
`claim-gated`, is the specification of nothing but this document.

The policy answers free work: the verification honest nodes spend on proofs
that never land and that nobody pays for. EIP-8288 has every pool node verify
the proof of every transaction with a dependency it is sent
(`05-aggregation.md`, AG-5), so an adversary who sends junk proofs costs every
node a verification each. Under claim-gated admission a transaction with a
dependency also carries an **admission claim**, bought in advance for one
sender, one sequence number and one epoch, and a node checks the sender's
signature and the claim before it verifies the proof. The claim intended is
a blind ticket: CG-8 gives the bytes a ticket signs, CG-9 how a node
verifies one and CG-10 where a transaction carries it; how one is issued,
priced and kept unlinkable is outside this document.

## What changes

A pool under the `claim-gated` profile is the frame pool of
`02-frame-pool.md` under the `eip-8288` profile of `05-aggregation.md`, with
these changes and no others:

- a frame transaction may carry a claim (`00-model.md`, MD-6, version 6),
  which CG-2 checks after FP-6;
- CG-3 checks every transaction of a mode 0 wrapper before AG-5 verifies the
  wrapper's proofs;
- CG-4 to CG-6 keep three records a node consults at admission: slots or
  claims under which a proof failed, claims under which a proof was
  verified, and claims of transactions the pool dropped;
- CG-7 lets a node relay mode 0 wrappers after those checks without
  verifying their proofs;
- CG-8 to CG-10 say when a real transaction carries a claim and when it is
  `valid`: an issuer's BLS12-381 signature over a fixed message that names
  the claim's chain, epoch and slot, carried to a ticket paymaster.

## Profile

**CG-1. Parameters.**

| Parameter | `claim-gated` | Note |
| --- | --- | --- |
| `claims` | true | whether CG-2 to CG-6 apply; false under every other profile |
| `claim_epoch` | 384 | seconds an epoch lasts; the epoch of a head is its `timestamp` divided by this, rounded down; *Interpretation*, decision record 0037 |
| `claim_memory` | `slot` | what CG-4 records after a proof fails: `slot`, rule R3; `claim`, the variant that remembers bad claims; or `none` |
| `signed_proofs` | false | whether a sender's signature covers the proofs a wrapper carries for its transaction; false is EIP-8288's wrapper; *Interpretation*, decision record 0037 |
| `verifies` | true | whether the node verifies proofs; a node with false is a relay (CG-7); a value of each node, not of the network; decision record 0038 |

Every AG-1 parameter is `eip-8288`'s. `claim_memory`, `signed_proofs` and
`verifies` exist to be varied: the experiments measure each value.

## Errors

| Code | Raised by |
| --- | --- |
| `ErrClaimMissing`, `ErrClaimInvalid`, `ErrClaimWrongSlot`, `ErrClaimEpoch` | CG-2 |
| `ErrProofUnsigned` | CG-3 |
| `ErrSlotRefused`, `ErrClaimRefused` | CG-4 |
| `ErrClaimUsed` | CG-5 |
| `ErrClaimExpired` | CG-6 |
| `ErrRelayAggregate` | CG-7 |

The rules name no errors; these codes are this repository's.

## Claims

**CG-2. A claim names one slot in one epoch (R2).** A transaction's *slot*
is its `sender`, `nonce_keys` and `nonce_seq`. A *claim* carries a `sender`,
`nonce_keys`, `nonce_seq` and `epoch`, `valid`, whether the issuer's
signature on it verifies, and a `salt` (MD-6); two claims with equal fields
are one claim. Under `claims`, after FP-6 and before AG-6, the pool MUST
reject:

1. with `ErrClaimMissing`, a transaction with a dependency (AG-4) that
   carries no claim;
2. with `ErrClaimInvalid`, one whose claim is not `valid`;
3. with `ErrClaimWrongSlot`, one whose claim names another slot than its
   own;
4. with `ErrClaimEpoch`, one whose claim's `epoch` is not the epoch of the
   pool's head.

A transaction without a dependency needs no claim, and one it carries is
checked all the same. **Source:** decision record 0037. Rule R2 accepts a claim $\tau$ of epoch $e$ only
during $e$, and only for a transaction that its sender $S$ signed at the
sequence number $n$ the claim names; the claim is a ticket, an issuer's
signature over a message that contains $(S, n)$ and $e$. The signature by
$S$ is FP-3's signatures and FP-8's simulation of the validation prefix,
which a node runs before any proof under CG-3. *Interpretation:* a claim is
checked when a transaction is admitted and not again, so one admitted in the
last head of its epoch stays pending after the epoch ends; R2 says when a
claim is accepted, not how long what it admitted stays; decision record 0037.

**CG-3. The signature and the claim before the proof (R1).** Under `claims`,
a node checking a mode 0 wrapper (AG-5) runs, after AG-5's step 4 and before
its step 5, these checks, and on the first failure refuses the whole wrapper
with the code, verifying no proof:

1. under `signed_proofs`, every proof is `signed`, the proof its
   transaction's sender signed, else `ErrProofUnsigned`;
2. for each transaction of the wrapper in order, the frame pool's admission
   checks FP-2 to FP-10 with CG-2, CG-4 and CG-6 in their places and without
   AG-6, each with its own code, and then CG-5.

These checks change nothing in the pool; AG-6 offers the transactions to it
afterwards, and it decides as it always does. **Source:** decision record
0037. Rule R1 has a node check the
sender's signature $\sigma$ and the claim $\tau$ first, and the proof $\pi$
only after both. *Interpretation:* EIP-8288 has a node verify a wrapper's
proof before its transactions reach the pool (AG-5, AG-6), so R1 moves the
transaction's checks ahead of the proof; R1's $\sigma$ is the validation
prefix and the signatures that FP-3 and FP-8
check, and the checks that depend on what else the pool holds, FP-11 to
FP-14, stay where they were, after the proof. A wrapper's proofs travel
beside its transactions (EIP-8288, Mempool Wrapper Object: a wrapper is
"[transactions, mode, content]" with "content = [deps, proofs]" in mode 0),
so the sender's signature does not cover them, and anyone who holds a
transaction can send it in a wrapper with a proof of their own;
`signed_proofs` is a variant in which it does; decision record 0037.

**CG-4. After a proof fails (R3, or its variant).** When AG-5's step 5
refuses a mode 0 wrapper that passed CG-3, the node records, for each of its
transactions that declares a triple whose proof does not verify, with its
claim's epoch $e$: under `claim_memory` `slot`, the transaction's slot; under
`claim`, its claim; under `none`, nothing. While the epoch of its head is at
most $e$, the pool MUST then reject, after CG-2: with `ErrSlotRefused`, a
transaction whose slot is recorded; with `ErrClaimRefused`, one whose claim
is recorded. **Source:** decision record 0037. Rule R3: once a proof $\pi$ fails under a signature and
claim $(\sigma, \tau)$ that both hold, the slot $(S, n)$ is refused for the
rest of epoch $e$. Its variant binds each ticket to one slot and remembers
the tickets under which a proof failed, rather than the slots.

**CG-5. One proof under each claim (R4).** When a mode 0 wrapper that passed
CG-3 reaches AG-5's step 5, the node records the slot and claim of each of
its transactions, whether its proofs verify or not. CG-3 MUST refuse with
`ErrClaimUsed` a transaction whose slot and claim are recorded. A
transaction the pool already holds is answered `ErrAlreadyKnown` by FP-2
first. **Source:** decision record 0037. Rule R4: a node verifies no more than one proof $\pi$ for each
$(S, n, \tau)$, so replacing a transaction takes a new claim.
*Interpretation:* the record does not expire with the epoch, since a claim
of a past epoch fails CG-2 anyway, and
it binds only proofs verified in a mode 0 wrapper; a transaction that
arrives in an aggregate has no proof of its own to verify (AG-5, mode 1).

**CG-6. No second admission (R6).** When the pool removes a transaction that
carries a claim for any reason but that its nonce was consumed (FP-15
step 1), the node records its slot and claim with the claim's epoch $e$.
While the epoch of its head is at most $e$, the pool MUST reject, after
CG-4, a transaction whose slot and claim are recorded, with
`ErrClaimExpired`. **Source:** decision record 0037. Rule R6: an
$(S, n, \tau)$ that has expired is not admitted again during $e$.
*Interpretation:* the clause counts every removal that leaves the slot open,
a replacement and an eviction included, decision record 0037.

## Relays

**CG-7. Relays.** Under `claims`, a node whose `verifies` is false is a
*relay*. A relay:

1. MUST refuse every mode 1 wrapper with `ErrRelayAggregate`, before AG-5's
   checks, verifying no recursive STARK;
2. checking a mode 0 wrapper, runs AG-5's steps 1 to 4 and CG-3, and then,
   in place of step 5, verifies no proof, records the wrapper's triples as
   *relayed*, and makes CG-5's record for each of its transactions;
3. offers the transactions to its pool as AG-6 does, a relayed triple
   counting as proven;
4. MUST send each mode 0 wrapper it accepted, unchanged and once, to every
   peer but the one it came from;
5. builds no aggregate (AG-7) and MUST NOT propose a block.

A relay keeps no record under CG-4, since no proof fails at it.
**Source:** decision record 0038. *Interpretation:* relays carry claimed
transactions, and an aggregate carries no claim: a relay that forwarded one
unchecked would carry recursive STARKs that cost every verifier a check with
no claim bought, so a relay takes none (item 1).
CG-5's record at a relay bounds what it forwards to one wrapper under each
claim, as R4 bounds what a verifier verifies (item 2). A builder aggregates
the proofs of the transactions it includes (EIP-8288, Recursive Mempool
Aggregation), which is a verifier's work, so a relay proposes nothing
(item 5). Decision record 0038.

## Tickets

The clauses above read a claim's `valid` flag. A real claim is a ticket: an
issuer's signature over a message naming one slot in one epoch on one
chain, which the buyer obtained blind, so that the issuer cannot link the
ticket it signed to the ticket it later sees. Blinding happens between the
buyer and the issuer and leaves an ordinary signature, so a node verifies a
ticket as it would any BLS signature. A transaction carries its ticket to a
*ticket paymaster*, a contract that pays its gas in a `VERIFY` frame after
checking the same signature on EIP-2537's precompiles, so that a node and
the chain check one ticket over the same bytes. CG-8 to CG-10 hold for
every profile that sets `claims`; the vectors of CG-2 to CG-7 give the flag
directly.

**CG-8. A ticket's message.** For a claim with `sender` $S$, `nonce_keys`
$K$, `nonce_seq` $s$, `epoch` $e$ and `salt` $t$, on the chain whose ID is
$c$, the message is

$$m = \mathrm{be}_{32}(c) \Vert S \Vert h(K) \Vert \mathrm{be}_{8}(s) \Vert \mathrm{be}_{8}(e) \Vert t$$

where $\mathrm{be}_{l}(x)$ is $x$ as $l$ bytes, most significant first, $S$
is the sender's 20 bytes, $h(K)$ is EIP-8250's `nonce_keys_hash` of $K$,
the 32 bytes `TXPARAM(0x0F)` returns, and $t$ is 32 bytes, so $m$ is 132
bytes long. A claim has no message when $c$ or a key is not below
$2^{256}$, when $s$ or $e$ is not below $2^{64}$, or when $S$ is not 20
bytes or $t$ not 32. **Source:** EIP-8250 at `258836f9`, "Transaction
introspection", for $h$: the keccak256 of the number of keys and the keys,
each as 32 bytes; decision record 0056. *Interpretation:* the fields are
CG-2's claim at fixed widths, so two claims that differ in any field have
different messages, and a ticket paymaster rebuilds $m$ from `CHAINID` and
`TXPARAM` with no loop over the keys. $K$ is the keys the transaction
carries. The chain ID binds a ticket to one chain. The salt is the buyer's,
so that two tickets for one slot in one epoch are two claims (CG-5);
decision record 0056.

**CG-9. A ticket's verification.** A ticket carries a `signature`, 128
bytes, and names an `issuer` key, 256 bytes (CG-10 says how), beside its
claim's fields, and a node holds for each epoch a set of issuer keys it
accepts. The claim is `valid` (MD-6) exactly when:

1. it has a message $m$ (CG-8);
2. `issuer` is in the node's set for the claim's `epoch`;
3. `issuer` decodes as a point $\mathit{pk}$ of G2 and `signature` as a
   point $\sigma$ of G1, each in EIP-2537's encoding (each coordinate in 64
   bytes whose first 16 are zero, below $p$; an element $c_0 + c_1 u$ of
   $\mathbb{F}_{p^2}$ as $c_0$ then $c_1$), on its curve, in its subgroup of
   order $r$, and not the point at infinity;
4. $e(\sigma, P_2) = e(H(u), \mathit{pk})$, where $P_2$ is G2's generator,
   $u$ is the byte 15, the 15 ASCII bytes `FRAME_TICKET_V1`, then $m$, and
   $H$ is hash_to_curve with the suite BLS12381G1_XMD:SHA-256_SSWU_RO_ and
   the domain separation tag `BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_`.

**Source:** RFC 9380, sections 5.3.1, 6.6.2, 6.6.3 and 8.8.1, and appendix
E.2, for $H$; draft-irtf-cfrg-bls-signature-05, sections 2.7 (CoreVerify)
and 4.2.3 (the ciphersuite BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_, the
minimal-signature-size variant), for step 4; EIP-2537 at `258836f9`
(Final), "Fine points and encoding of base elements" and "Subgroup
checks", for step 3's encoding and checks; Commonware
at `c18a6b9`, whose `ops::verify_message` for `MinSig` is steps 3 and 4
over its own encoding, with $u$ formed by `union_unique`, the namespace's
length as a varint, then the namespace, then the message. *Interpretation:*
signatures are in G1, so each transaction carries one point of G1, and keys
in G2, since an issuer has few. EIP-2537's encoding is the one a ticket
paymaster hands its precompiles; a node may hold the points in any form.
The namespace keeps a ticket's message apart from what the same key signs
through `sign_message` for other purposes, but an issuer that signs blind
signs whatever point it is sent, so an issuer's key signs tickets and
nothing else. The point at infinity is refused as a signature, as
Commonware's decoding refuses it; this changes no verdict, since such a
signature verifies only against a key at infinity, which step 3 refuses
already, or for a $u$ that hashes to infinity, which nobody can find.
Decision record 0056.

**CG-10. Where a ticket rides.** A node holds, for each epoch, a set of
ticket paymasters it accepts, each an address with its issuer key; the
issuer keys CG-9 accepts for an epoch are those of its ticket paymasters.
Under `claims`, a frame transaction carries a claim exactly when a frame of
its validation prefix is a `VERIFY` frame whose target is a ticket
paymaster the node accepts for the epoch of its head. The first such frame
is the ticket's. Its data is $\mathrm{be}_{8}(e) \Vert t \Vert \sigma$, 168
bytes: the claim's `epoch` $e$, its `salt` $t$, and the `signature`
$\sigma$ in EIP-2537's 128 bytes. The claim's `sender`, `nonce_keys` and
`nonce_seq` are the transaction's own, its `issuer` is that paymaster's
key, and it is `valid` by CG-9. Data of any other length makes a claim that
is not `valid`. **Source:** decision record 0056. *Interpretation:* the
frame names the key, so a ticket carries no key of its own and a node
checks one signature, not one for each key it accepts; a ticket paymaster
holds one key, so a set of issuers is a set of paymasters. The transaction
names the slot and the chain, so the frame carries only what it does not:
the epoch, the salt and the signature. A claim is taken only from a
paymaster the node accepts at its head, so a ticket to any other contract
is no claim at all and CG-2 judges the transaction without one; decision
record 0056.

## Not modelled

- R5: whatever admission reads is carried in the transaction or owned by
  it. The frame pool's rules on payers (FP-11) are kept as `eip-8288` has them; a transaction paid by a
  sponsor whose balance another transaction can drain is admitted. The
  experiments' honest transactions pay for themselves.
- How claims are issued and priced, and how a buyer blinds and unblinds a
  ticket. In CG-2 to CG-7 a claim is a record whose `valid` flag is CG-9's
  verdict; how many valid claims an adversary holds is a parameter of an
  experiment.
- How a node learns the ticket paymasters it accepts for an epoch. CG-10
  takes the set as given; a paymaster that holds its key in its code from
  deployment lets a node read the key from the chain, but which paymasters
  to trust is the node's to decide.
- What a ticket paymaster's `VERIFY` frame costs, and how many of its
  transactions a pool holds at once. A paymaster that checks a ticket on
  EIP-2537's precompiles spent 122,006 gas in its frame on the Hegota
  testnet (`exp-frames` experiment 36), above `eip-8141`'s `max_verify_gas`
  of 100,000 (FP-1); and under `claim-gated` a ticket paymaster is a payer
  like any other, so FP-11 lets it sponsor one pending transaction at a
  time. A profile that admits ticket-paid transactions at the EIP's limits
  needs a clause for both.
- What checking a signature, a claim, a proof or an aggregate costs. The
  pool decides; the simulator counts what each decision cost (decision
  record 0037).
- How a relay sends what it forwards. CG-7 has it send every wrapper to
  every peer, as AG-7 has a node send its aggregate; a relay that announced
  a wrapper and let each peer fetch it once would send less. Nor how a node
  learns which of its peers verify.
- A recursive STARK that does not verify, and the nodes that send one: the
  claims bind proofs a node verifies directly.

## Version notes

- **Version 2.** CG-1 gains `verifies`, and CG-7 says what a node does
  without it. `claim-gated` sets it to true, so the profile's behaviour does
  not change: every vector of version 1 holds unchanged and now says
  version 2.
- **Version 3.** CG-8 to CG-10 say where a real transaction's claim comes
  from and what its `valid` flag is: the bytes an issuer signs, a BLS12-381
  signature over them, and the frame that carries it to a ticket paymaster.
  Nothing in CG-1 to CG-7 changes: every vector of version 2 holds unchanged
  and now says version 3.
