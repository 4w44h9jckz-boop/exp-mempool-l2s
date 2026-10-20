# 0037. Claim-gated admission is a proposal on EIP-8288, and a wrapper's proofs are not under the sender's signature

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 28 asks for claim-gated admission as a profile on the frame
pool and the aggregation layer. Claim-gated admission has six rules. R1 checks the signature $\sigma$ and
the claim $\tau$ before the proof $\pi$. R2 accepts $\tau$ only in its epoch
$e$, for a transaction from the sender $S$ at sequence number $n$ that $S$
signed. R3, once an invalid $\pi$ arrives under a valid $(\sigma, \tau)$,
refuses $(S, n)$ until $e$ ends. R4 verifies at most one $\pi$ for each
$(S, n, \tau)$, so that a replacement needs a new claim. R5 requires every
read made at admission to be carried or owned. R6 never admits an expired
$(S, n, \tau)$ again within $e$. In the rules' model the sender's signature
$\sigma$ covers the transaction together with its proof.

EIP-8288 (Draft, at `258836f9`) does not put the proof in the signed
transaction. A wrapper is "[transactions, mode, content]", with "content =
[deps, proofs]" in mode 0 (Mempool Wrapper Object), and a transaction only
declares its dependencies' triples. Anyone who holds a transaction can send
it in a wrapper of their own with a proof that does not verify, and the
sender's signature still verifies. `05-aggregation.md` follows the EIP: AG-5
verifies a wrapper's proofs, and only then does AG-6 offer its transactions
to the pool, so the signature is checked after the proof.

## Decision

1. **A proposal document on the `eip-8288` profile.**
   `docs/spec/10-claim-gated-admission.md`, clause prefix CG, profile
   `claim-gated`, stated as MATCHA's is: the specification of nothing but
   that document, with its rules stated, not adopted.
2. **A claim is a field of the transaction**, so that it is under the
   sender's signature and in its hash (MD-6 and MD-7, `00-model.md`
   version 6), as the rules' tuple has it. It names a *slot*, the sender,
   `nonce_keys` and `nonce_seq`, which is what FP-12 already treats as one
   place only one transaction fills, and an epoch. Whether its issuer's
   signature verifies is a flag, as a proof's is; a `salt` makes two claims
   for one slot two claims.
3. **An epoch lasts 384 s**, the beacon chain's 32 slots of 12 s; the rules
   leave its length open. A claim is checked at admission and not again.
4. **R1's $\sigma$ is the validation prefix.** CG-3 runs FP-2 to FP-10 and
   the claim's checks before AG-5 verifies a proof. The checks that depend
   on what else the pool holds, FP-11 to FP-14, stay after it, since they
   are not the signature.
5. **`signed_proofs` false is the EIP, and true is the rules' model.** With
   it false, CG-3 cannot tell an honest wrapper from the same transaction
   wrapped with a junk proof, and R3 refuses the honest sender's slot for
   the rest of the epoch at every node the junk reaches first. With it true,
   a wrapper carries for each proof whether it is the one the sender signed,
   and CG-3 refuses one that is not before any proof. How a sender would sign its proofs and still let nodes fold
   them is not designed here.
6. **R3 and a variant that remembers claims are one parameter.**
   `claim_memory` is `slot` for R3, `claim` for the variant, which refuses
   the claim rather than the slot, and `none` for neither, so that an
   experiment can tell what R3 adds to R4: R4 alone already lets a node
   verify at most one proof per claim.
7. **R4 binds proofs a node verifies directly.** The record is kept for
   good, and a transaction in an aggregate is not checked against it, since
   a recursive STARK covers it.
8. **R6 counts every removal that leaves the slot open.** Besides expiry,
   the frame pool drops a transaction for capacity, for a payer that can no
   longer pay, and for a replacement, each of which leaves the slot to be
   filled again under the same claim.
9. **R5 is not a rule here.** Under it the flood of experiment 24, paid by
   sponsors it drains, would be refused outright; without it the flood can
   be rerun with claims. The honest transactions of the experiments pay for
   themselves, so R5 holds of them.
10. **The simulator counts work by event.** A node counts a check of a
    transaction's signature and claim; a proof verified directly; and a
    triple listed in one of its aggregates for the first time, as a *fold* when the aggregate verified it
    directly and a *cover* when a recursive input it took covers it, which
    costs a share of that input (AG-9). An experiment states the costs it
    multiplies the counts by, and where it took them. The reference's
    aggregator counts the events, and the simulator files them by the
    message's origin and the transaction's maker, so that an adversary who
    re-sends someone else's transaction is charged for it.

## Consequences

- `docs/spec/README.md` lists the document and the profile, and
  `scripts/check_vectors.py` requires a vector for every CG clause but
  CG-1.
- `signed_proofs` is a profile parameter, so that EIP-8288's wrapper and
  one whose proofs are under the sender's signature can be set side by
  side.
