# 10. Claim-gated admission (proposal)

Version 2, 2026-10-13. Version 1, the same day, had every node verify;
version 2 adds `verifies` and CG-7, and changes nothing else.

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
a blind ticket; how one is issued, priced and kept unlinkable is outside
this document, and is not modelled here.

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
  verifying their proofs.

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

## Not modelled

- R5: whatever admission reads is carried in the transaction or owned by
  it. The frame pool's rules on payers (FP-11) are kept as `eip-8288` has them; a transaction paid by a
  sponsor whose balance another transaction can drain is admitted. The
  experiments' honest transactions pay for themselves.
- How claims are issued and priced, and that they are blind. A claim is a
  record whose `valid` flag says whether its issuer's signature verifies;
  how many valid claims an adversary holds is a parameter of an experiment.
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
