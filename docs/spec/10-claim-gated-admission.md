# 10. Claim-gated admission (proposal)

Version 7, 2026-10-21. Version 1, 2026-10-13, had every node verify;
version 2, the same day, added `verifies` and CG-7; version 3, 2026-10-20,
added CG-8 to CG-10, the bytes a ticket signs, how a node verifies one and
where a transaction carries it; version 4, the same day, recognises a
ticket paymaster by its code rather than from a set a node holds; version
5, the same day, accepts a ticket paymaster only under a bond, ERC-8421's
stake and reputation (CG-11); version 6, 2026-10-21, binds a ticket to the
transaction it pays for, through a one-time key the buyer chose (CG-12);
version 7, the same day, names the bound template.

**Status: proposal.** This document states, as clauses, an admission policy
that no client implements and no EIP specifies: claim-gated admission,
stated as six rules, R1 to R6, with a variant that remembers bad claims
rather than slots, and with nodes that need not verify. Decision record 0037
records the readings it rests on, decision record 0064 those of the bond,
decision record 0067 those of the binding, decision record 0069 those of
the bound template, and its vectors check the clauses. A clause marked *Interpretation* is this
repository's reading where the rules leave a choice open, and names the
decision record. The profile,
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
  the claim's chain, epoch and slot, carried to a ticket paymaster;
- CG-11, under `bond`, accepts a ticket only if its paymaster is staked as
  ERC-8421 stakes an operator, keeps ERC-8421's reputation for each ticket
  paymaster, and refuses a banned one before the ticket is checked;
- CG-12, under `binding`, accepts a claim only if the ticket's message names
  a one-time key and that key signed the transaction's signature hash, so a
  copy of the transaction with any signed field changed is not paid by the
  same ticket.

## Profile

**CG-1. Parameters.**

| Parameter | `claim-gated` | Note |
| --- | --- | --- |
| `claims` | true | whether CG-2 to CG-6 apply; false under every other profile |
| `claim_epoch` | 384 | seconds an epoch lasts; the epoch of a head is its `timestamp` divided by this, rounded down; *Interpretation*, decision record 0037 |
| `claim_memory` | `slot` | what CG-4 records after a proof fails: `slot`, rule R3; `claim`, the variant that remembers bad claims; or `none` |
| `signed_proofs` | false | whether a sender's signature covers the proofs a wrapper carries for its transaction; false is EIP-8288's wrapper; *Interpretation*, decision record 0037 |
| `verifies` | true | whether the node verifies proofs; a node with false is a relay (CG-7); a value of each node, not of the network; decision record 0038 |
| `bond` | true | whether CG-11 applies; false under every other profile, and a profile with `claims` and without `bond` is version 4's admission; decision record 0064 |
| `binding` | true | whether CG-12 applies; false under every other profile, and a profile with `claims` and without `binding` is version 5's admission; decision record 0067 |
| `bound_template` | 1,185 bytes, keccak256 `0x52c656815e560bb189c3fb362c9628432ca1ed6b720e239857775236c18bc1d3` | the bound template of CG-10, as its length and keccak256; a profile that names none has no bound ticket paymaster; decision records 0067 and 0069 |

Every AG-1 parameter is `eip-8288`'s. Under `bond`, CG-11 reads seven of
AM-1's parameters (`14-erc-8421.md`), with the values
`docs/spec/descriptors/erc-8421.json` gives them: `min_stake_value`
$10^{18}$ wei, `min_unstake_delay` 86400 s,
`min_inclusion_rate_denominator` 10, `throttling_slack` 10, `ban_slack` 50,
`refresh_seconds` 3600 and `throttled_entity_mempool_count` 4.
`claim_memory`, `signed_proofs` and `verifies` exist to be varied: the
experiments measure each value.

## Errors

| Code | Raised by |
| --- | --- |
| `ErrClaimMissing`, `ErrClaimInvalid`, `ErrClaimWrongSlot`, `ErrClaimEpoch` | CG-2 |
| `ErrProofUnsigned` | CG-3 |
| `ErrSlotRefused`, `ErrClaimRefused` | CG-4 |
| `ErrClaimUsed` | CG-5 |
| `ErrClaimExpired` | CG-6 |
| `ErrRelayAggregate` | CG-7 |
| `ErrIssuerUnbonded`, `ErrEntityBanned`, `ErrEntityThrottled` | CG-11 |
| `ErrClaimUnbound` | CG-12 |

The rules name no errors; these codes are this repository's. CG-11's last
two are the codes `14-erc-8421.md` gives REPUTATION-010 and REPUTATION-020.

## Claims

**CG-2. A claim names one slot in one epoch (R2).** A transaction's *slot*
is its `sender`, `nonce_keys` and `nonce_seq`. A *claim* carries a `sender`,
`nonce_keys`, `nonce_seq` and `epoch`, `valid`, whether the issuer's
signature on it verifies, a `salt`, a `binder` and `bound`, whether it is
bound to its transaction (MD-6, CG-12); two claims with equal fields are
one claim. Under `claims`, after FP-6, after CG-11 under `bond`, and before
AG-6, the pool MUST reject, with CG-12's check between steps 1 and 2 under
`binding`:

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
   checks FP-2 to FP-10 with CG-11 under `bond`, CG-2, CG-4 and CG-6 in their
   places and without AG-6, each with its own code, and then CG-5.

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

The clauses above read a claim's `valid` and `bound` flags. A real claim is a ticket: an
issuer's signature over a message naming one slot in one epoch on one
chain, which the buyer obtained blind, so that the issuer cannot link the
ticket it signed to the ticket it later sees. Blinding happens between the
buyer and the issuer and leaves an ordinary signature, so a node verifies a
ticket as it would any BLS signature. A transaction carries its ticket to a
*ticket paymaster*, a contract that pays its gas in a `VERIFY` frame after
checking the same signature on EIP-2537's precompiles, so that a node and
the chain check one ticket over the same bytes. CG-8 to CG-10 hold for
every profile that sets `claims`; the vectors of CG-2 to CG-7 give the flags
directly.

**CG-8. A ticket's message.** For a claim with `sender` $S$, `nonce_keys`
$K$, `nonce_seq` $s$, `epoch` $e$, `salt` $t$ and no `binder`, on the chain
whose ID is $c$, the message is

$$m = \mathrm{be}_{32}(c) \Vert S \Vert h(K) \Vert \mathrm{be}_{8}(s) \Vert \mathrm{be}_{8}(e) \Vert t$$

where $\mathrm{be}_{l}(x)$ is $x$ as $l$ bytes, most significant first, $S$
is the sender's 20 bytes, $h(K)$ is EIP-8250's `nonce_keys_hash` of $K$,
the 32 bytes `TXPARAM(0x0F)` returns, and $t$ is 32 bytes, so $m$ is 132
bytes long. For a claim whose `binder` is $a$, the address of a one-time
key, the message is $m \Vert a$, 152 bytes. A claim has no message when $c$
or a key is not below $2^{256}$, when $s$ or $e$ is not below $2^{64}$, or
when $S$ is not 20 bytes, $t$ not 32, or a `binder` not 20. **Source:** EIP-8250 at `258836f9`, "Transaction
introspection", for $h$: the keccak256 of the number of keys and the keys,
each as 32 bytes; decision record 0056. *Interpretation:* the fields are
CG-2's claim at fixed widths, so two claims that differ in any field have
different messages, and a ticket paymaster rebuilds $m$ from `CHAINID` and
`TXPARAM` with no loop over the keys. $K$ is the keys the transaction
carries. The chain ID binds a ticket to one chain. The salt is the buyer's,
so that two tickets for one slot in one epoch are two claims (CG-5);
decision record 0056. The binder goes last, so that a message without one
is version 5's, and the issuer, which signs blind, learns it no more than
the salt; decision record 0067.

**CG-9. A ticket's verification.** A ticket carries a `signature`, 128
bytes, and names an `issuer` key, 256 bytes (CG-10 says how), beside its
claim's fields. The claim is `valid` (MD-6) exactly when:

1. it has a message $m$ (CG-8);
2. `issuer` decodes as a point $\mathit{pk}$ of G2 and `signature` as a
   point $\sigma$ of G1, each in EIP-2537's encoding (each coordinate in 64
   bytes whose first 16 are zero, below $p$; an element $c_0 + c_1 u$ of
   $\mathbb{F}_{p^2}$ as $c_0$ then $c_1$), on its curve, in its subgroup of
   order $r$, and not the point at infinity;
3. $e(\sigma, P_2) = e(H(u), \mathit{pk})$, where $P_2$ is G2's generator,
   $u$ is the byte 15, the 15 ASCII bytes `FRAME_TICKET_V1`, then $m$, and
   $H$ is hash_to_curve with the suite BLS12381G1_XMD:SHA-256_SSWU_RO_ and
   the domain separation tag `BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_`.

**Source:** RFC 9380, sections 5.3.1, 6.6.2, 6.6.3 and 8.8.1, and appendix
E.2, for $H$; draft-irtf-cfrg-bls-signature-05, sections 2.7 (CoreVerify)
and 4.2.3 (the ciphersuite BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_, the
minimal-signature-size variant), for step 3; EIP-2537 at `258836f9`
(Final), "Fine points and encoding of base elements" and "Subgroup
checks", for step 2's encoding and checks; Commonware
at `c18a6b9`, whose `ops::verify_message` for `MinSig` is steps 2 and 3
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
signature verifies only against a key at infinity, which step 2 refuses
already, or for a $u$ that hashes to infinity, which nobody can find.
Decision record 0056.

**CG-10. Where a ticket rides.** A *ticket paymaster* is an account whose
code at the node's head is $T \Vert K \Vert D$: $T$ the ticket-paymaster
template, 1,105 bytes whose keccak256 is
`0xec9f3f855524392a3891f2f2eb554781236d5565520d68388e455be74bdf3fe0`; $K$,
256 bytes that decode as a point of G2 as CG-9 step 2 decodes `issuer`, on
the twist, in the subgroup and not the point at infinity; and $D$, any 32
bytes. A *bound ticket paymaster* is an account whose code at the node's
head is $T_b \Vert K \Vert D$, with $K$ and $D$ as above and $T_b$ the bound
template that CG-1's `bound_template` names by its length and keccak256; a
profile that names none has no bound ticket paymaster. Under `claims`, a
frame transaction carries a claim exactly when one of its frames is a
`VERIFY` frame whose target is a ticket paymaster or a bound ticket
paymaster. The first such frame is the ticket's. To a ticket paymaster its
data is $\mathrm{be}_{8}(e) \Vert t \Vert \sigma$, 168 bytes: the claim's
`epoch` $e$, its `salt` $t$, and the `signature` $\sigma$ in EIP-2537's 128
bytes; the claim has no `binder`. To a bound ticket paymaster its data is
$\mathrm{be}_{8}(e) \Vert t \Vert a \Vert \sigma$, 188 bytes, and the
claim's `binder` is $a$. The claim's `sender`, `nonce_keys` and `nonce_seq`
are the transaction's own, its `issuer` is that paymaster's $K$, it is
`valid` by CG-9 and `bound` by CG-12. Data of any other length makes a
claim that is neither `valid` nor `bound`. **Source:** for
$T$, `kohaku-rs` at `eea02a3`, `crates/frame-ticket/contracts/TicketPaymaster.hex`
after its 25-byte constructor, whose `TicketPaymaster.yul` appends the key
and a 32-byte denomination to the code it deploys; the same bytes are the
code of `0x273795f6eb2730d50c3544cbef1e0c1adba4f541` on the Hegota testnet.
For $T_b$, `exp-frames` branch `exp/48-bound-ticket` at `9a6427f`,
`exp-frames/experiments/48-bound-ticket/BoundTicketPaymaster.yul`, which
appends the key and the denomination to the code it deploys; the same
1,185 bytes begin the code of `0xca7aa9eb83846186c1562abab968d1568ad55228`
on the Hegota testnet, read at block 493,609.
*Interpretation:* a node recognises a ticket paymaster by its code, with no
list and no registry, as the owner ruled; decision record 0057. The frame
names the key, so a ticket carries no key of its own and a node checks one
signature; a set of issuers is a set of paymasters. A node can keep a
paymaster's verdict by its code hash, since the code decides it. A
transaction names the slot and the chain, so the frame carries only the
epoch, the salt and the signature, and the binder when the ticket names
one. A ticket to any other account is no claim at all, and CG-2 judges the
transaction without one. The bound template rebuilds the 152-byte message,
checks CG-9's pairing, and then reads every entry of the transaction's
signature list with `SIGPARAM`, scheme first, for one whose scheme is
`secp256k1`, whose `msg` is empty and whose resolved signer is the binder:
CG-12's steps 1 and 2, with step 3 left to the protocol; decision records
0067 and 0069.

What a junk proof then costs its sender, read from these clauses: anyone
can deploy the template with a key of their own and sign their own
tickets. Under CG-3 a mode 0 wrapper's transactions run FP-2 to FP-10 and
CG-2 before its proofs and FP-11 after them, so a wrapper refused at its
proof leaves no transaction pending: it holds none of FP-11's pending
places for its paymaster and reserves none of its balance. FP-8 needs the
paymaster's balance to cover the transaction's `max_cost`, and spends none
of it. Each junk proof of a self-issuer therefore costs it a fresh slot and
a ticket it signs itself, and once, a paymaster's deployment and the float
for one transaction's `max_cost`; it costs a node CG-9's check, the
prefix's simulation, the paymaster's `VERIFY` frame included, and the
proof's verification. Decision record 0057.

## The bond

**CG-11. A bond on the ticket paymaster.** Under `bond`, a transaction that
carries a claim has a *ticket paymaster* when its payer, the resolved target
of the frame that carries `APPROVE_PAYMENT` (FP-4's last prefix frame, the
payer `14-erc-8421.md`'s AM-3 names), is not its sender; that payer is its
ticket paymaster. A ticket paymaster is *bonded* when it is staked as AM-3
stakes an entity, at the pool's head: its `code` is not empty, its `stake`
is at least `min_stake_value`, its `unstake_delay` at least
`min_unstake_delay`, and its `withdrawing` false (MD-2). For each ticket
paymaster the node keeps AM-13's two counters, `seen` and `included`, which
start as the node was given them, 0 unless said otherwise, and every
`refresh_seconds` of the pool's time, counted from 0, are multiplied by 23
and divided by 24, rounding down. With
$m = \lfloor \mathit{seen} / \mathit{min\_inclusion\_rate\_denominator} \rfloor$,
a ticket paymaster is `BANNED` if $m > \mathit{included} + \mathit{ban\_slack}$,
`THROTTLED` if $\mathit{included} + \mathit{throttling\_slack} < m$ and it
is not banned, and `ACTIVE` otherwise; the pool exposes its counters and its
state as it does an entity's (MD-9). Under `claims` and `bond`, after FP-6
and before CG-2's checks, the pool MUST reject a transaction with a ticket
paymaster:

1. with `ErrIssuerUnbonded`, if the paymaster is not bonded;
2. with `ErrEntityBanned`, if it is `BANNED`;
3. with `ErrEntityThrottled`, if it is `THROTTLED` and already the ticket
   paymaster of `throttled_entity_mempool_count` pending transactions.

The node adds 1 to a ticket paymaster's `seen` once for each transaction it
is the ticket paymaster of: when a proof of the transaction fails at AG-5's
step 5 after CG-3, as CG-4 records, or when the pool admits it, whichever
comes first. It adds 1 to its `included` when
FP-15's step 1 removes a pending transaction it is the ticket paymaster of,
which the model reads as its inclusion. A counter is each node's own.
**Source:** `14-erc-8421.md`, AM-3 [STAKING-010] for the stake and AM-13
[REPUTATION-010, REPUTATION-020] for the counters, the states and the
refusals, read for one entity, the ticket paymaster; decision record 0062,
which modelled them in the simulator, and experiment 26, which priced them.
*Interpretation*, decision record 0064:

- the ticket paymaster is the payer. The template's `VERIFY` frame accepts
  only the scope `PAYMENT` and approves payment (CG-10's $T$, kohaku-rs at
  `eea02a3`, `TicketPaymaster.yul`), so every transaction that carries a
  real ticket is paid by its ticket paymaster, and never by its sender,
  whose own frame must approve execution. A claim the model gives on a
  transaction that pays for itself (MD-6) stands for a ticket whose
  paymaster is not modelled, and CG-11 reads nothing for it;
- the stake is required. ERC-8421 lets an unstaked payer in under
  REPUTATION-220; a ticket paymaster without one would let a self-issuer
  replace a banned paymaster for the price of a deployment;
- the checks come before CG-2's, so a node refuses an unbonded or banned
  paymaster's ticket without checking its signature (CG-9);
- `seen` counts each transaction once, after it has passed the bond, the
  ticket and the prefix: a junk proof's when its proof fails, since it is
  never admitted, and any other at its admission, as AM-13 counts. A
  transaction whose count bans its paymaster is therefore admitted, and the
  next is refused. ERC-8421 counts a replacement against the payer it
  changes (REPUTATION-040); here a replacement is a new transaction and
  counts once, as any other;
- a banned paymaster's pending transactions stay pending. AM-13 removes
  them at `reset`; experiment 26 measured the bond without that removal,
  under which a holder of an honest issuer's tickets who has it banned
  would also drop the issuer's pending spends.

Under `claim-gated`, FP-11 already holds a ticket paymaster, which is not
canonical, to `max_pending_noncanonical` pending transactions, 1, fewer than
`throttled_entity_mempool_count`; step 3 refuses nothing until a profile
lets a paymaster pay for more, and the stake and the ban are what bind.

What a junk proof costs under the bond, read from these clauses and
measured in experiment 26 (`experiments/26-ticket-bond/README.md`, "What it
shows"), which ran the same rules in the simulator with the descriptor's
parameters:

- **A self-issuer stakes each paymaster.** A node that has counted none of
  a paymaster's transactions included bans it after
  $(50 + 1) \cdot 10 = 510$ junk proofs under its tickets. Against one
  staked paymaster, every node banned it at 1,584 s, after 510 failed
  proofs there, and the hourly refresh reopened it for 22 more. Over the run
  that is 15,960 junk proofs against 68,520 under version 4, for
  $10^{18}$ wei locked 1.08 ETH-days. With four staked paymasters the
  self-issuer kept 1,180 junk proofs a node in the first hour and 911 in
  the second: the bond prices junk at a stake per paymaster, and does not
  stop a self-issuer with capital.
- **An unstaked paymaster costs a node nothing.** Its tickets are refused
  before the signature, the prefix or the proof.
- **A busy honest issuer cannot be closed** by a holder of its tickets: at 8
  or 64 junk proofs an epoch, no node throttled or banned it, since its
  `included` grows with its traffic.
- **A small honest issuer can.** At 64 junk proofs an epoch every node
  throttled one selling 4 tickets an epoch at 1,541 s, and the same rate,
  sustained, bans it after 2.03 hours; 8 an epoch never throttles it.
- **The stake weighs on a small issuer.** $10^{18}$ wei is 1,000 tickets'
  face value in the experiment: 1.11 days of the small issuer's sales, and
  0.07 days of a busy one's, locked from its first ticket to the end of the
  unstake delay after its last.

No honest spend was refused, and no honest delay moved, in any of
experiment 26's rows.

## The binding

**CG-12. A ticket bound to its transaction.** A claim is **bound** when it
has a `binder` $a$ and its transaction carries a signature that:

1. has `scheme` `secp256k1` and an empty `msg`;
2. has $a$ as its resolved signer: its `signer`, or the transaction's
   `sender` when `signer` is empty;
3. verifies over the transaction's signature hash, `compute_sig_hash(tx)`:
   its 65 bytes are $v \Vert r \Vert s$ with $v \le 1$, $0 < r < n$ and
   $0 < s \le \lfloor n / 2 \rfloor$, $n$ the order of secp256k1, and the
   address they recover for that hash is $a$.

Under `claims` and `binding`, after CG-2's step 1 and before its step 2,
the pool MUST reject with `ErrClaimUnbound` a transaction whose claim is not
`bound`. A claim with no `binder` is not bound. The model's `bound` flag
(MD-6) stands for this verdict, as `valid` stands for CG-9's; a node that
reads a real transaction computes both (CG-10, `11-surface.md` SF-3).
**Source:** EIP-8141 at `258836f9`, "Signature Hash", where
`compute_sig_hash(tx)` empties the `signature` bytes of every signature
with an empty `msg` and hashes the rest of the transaction; "Signature
Validation", `validate_signature` for `SECP256K1`, which is step 3;
"Transaction Signatures" ("Every protocol-validated signature in this list
must validate successfully before any frame is executed"); and
"Introspection", `SIGPARAM`, which returns a signature's resolved signer,
scheme and `msg` to a `VERIFY` frame, so a bound ticket paymaster can check
steps 1 and 2 and leave step 3 to the protocol. *Interpretation*, decision
record 0067: the buyer chooses the one-time key and puts its address in the
message it has signed blind, so the issuer never sees it and is not needed
when the ticket is spent. The signature hash covers every field of the
transaction but the bytes of signatures over it, the ticket's frame
included, so a copy with any field changed is not signed by the binder,
and only the binder's holder can sign another. The signature is a
`secp256k1` entry of the transaction's list rather than bytes in a frame,
since a signature over the signature hash cannot sit in the frame data
that hash covers; `p256` is left out, since a one-time key gains nothing
from a passkey and its check costs 6,700 gas of FP-6's budget rather than
2,800. The check comes before `valid` so that a node can refuse an unbound
claim without CG-9's pairing.

## Not modelled

- R5: whatever admission reads is carried in the transaction or owned by
  it. The frame pool's rules on payers (FP-11) are kept as `eip-8288` has them; a transaction paid by a
  sponsor whose balance another transaction can drain is admitted. The
  experiments' honest transactions pay for themselves.
- How claims are issued and priced, and how a buyer blinds and unblinds a
  ticket. In CG-2 to CG-7 a claim is a record whose `valid` flag is CG-9's
  verdict; how many valid claims an adversary holds is a parameter of an
  experiment.
- How a node reads a target's code: from its execution client at its head,
  as it takes a verdict (`11-surface.md`, SF-4); the model's clauses take
  the claim as given (MD-6).
- A memory of the paymasters under whose tickets a proof failed, which would
  price a self-issuer's junk proofs in deployments (CG-10); `claim_memory`
  has no such value. Experiment 25 priced it as issuer memory, and a node's
  list of issuers beside it; the bond of CG-11 was chosen over both
  (decision record 0064).
- How a node reads a paymaster's stake on a chain: from ERC-8421's staking
  registry, `getDepositInfo` (AM-3). The model keeps the registry's answer
  on the account (MD-2), and `11-surface.md` reads no registry, so a node
  run against a chain checks claims without `bond`.
- Staking itself: the deposit, the unstake delay's unlock, the withdrawal
  and their gas. CG-11 reads only whether a paymaster is staked at the head.
- A reputation shared between nodes. Each node counts what it saw, so a
  self-issuer that reaches fewer nodes is banned at fewer, and so is an
  honest issuer whose tickets a griefer spends at only some.
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
- What the bound template's `VERIFY` frame costs: 122,233 and 122,350 gas
  on the Hegota testnet, against the version 5 template's 122,006
  (`exp-frames` experiment 48), so a bound ticket fits `eip-8141`'s
  `max_verify_gas` no better than an unbound one did. The binding's
  signature adds 2,800 gas to the transaction's verification cost (FEE-4),
  which FP-6 counts against `max_verify_gas`.
- What the bound template checks beyond CG-9 and CG-12: that its frame's
  scope is `PAYMENT`, that the transaction's `max_cost` is at most its
  denomination, and that the binder is not zero. A node takes these from
  the client's verdict on the prefix (`11-surface.md`, SF-4). The template
  reads no epoch and keeps no record: CG-2's step 4 and CG-4 to CG-6 are a
  node's alone (decision record 0069).
- How a buyer derives its one-time keys, and what a wallet must keep to
  spend a ticket it bought: CG-12 reads only the address in the message and
  the signature in the transaction.
- A signature with an empty `msg` whose scheme is `arbitrary`: its bytes,
  like the binder's, are outside the signature hash, so a copy that changes
  them keeps a bound claim bound. Whoever can change them is whoever its
  own verifier accepts; EIP-8141's "Arbitrary Signature Malleability"
  leaves that to the verifier.

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
- **Version 4.** A ticket paymaster is an account whose code is the
  template followed by a key and 32 bytes (CG-10), so CG-9 loses its step
  2, the node's set of keys for each epoch, and its steps 3 and 4 become 2
  and 3. CG-9's and CG-10's vectors change with it; the vectors of CG-2 to
  CG-8 hold unchanged and now say version 4.
- **Version 5.** CG-1 gains `bond`, true under `claim-gated`, and CG-11
  puts ERC-8421's stake and reputation on the ticket paymaster. Every
  transaction of the earlier vectors pays for itself, so CG-11 reads
  nothing for it: the vectors of CG-2 to CG-10 hold unchanged and now say
  version 5, and CG-11's are new.
- **Version 6.** CG-1 gains `binding`, true under `claim-gated`, and
  `bound_template`, none under it; a claim gains a `binder` and a `bound`
  flag (MD-6, `00-model.md` version 12); CG-8's message ends with the
  binder when a claim has one; CG-10 reads a bound ticket paymaster's 188
  bytes; and CG-12 refuses a claim its binder has not signed for. A model
  claim is `bound` unless a vector says otherwise, so the vectors of CG-2 to
  CG-7 and CG-11 hold unchanged and now say version 6; so do CG-8's, CG-9's
  and CG-10's, whose claims have no binder. CG-12's are new, and CG-8's,
  CG-9's and CG-10's gain cases with a binder.
- **Version 7.** CG-1's `bound_template` under `claim-gated` is no longer
  none: it names `exp-frames` experiment 48's template, 1,185 bytes, which
  CG-10 cites. No rule changes. The vectors of CG-2 to CG-12 set a template
  of their own where they read one, so they hold unchanged and now say
  version 7. CG-12's gain the transactions experiment 48 sent to the
  testnet, mined and refused, read under the profile's own template, and
  cases for the entries a bound template must skip; CG-12's pool vectors
  gain a holder's re-pricing and an epoch that ends while a ticket is
  pending (decision record 0069).
