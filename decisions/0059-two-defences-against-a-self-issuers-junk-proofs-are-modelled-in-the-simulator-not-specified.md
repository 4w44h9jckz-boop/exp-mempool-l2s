# 0059. Two defences against a self-issuer's junk proofs are modelled in the simulator, not specified

Date: 2026-10-20. Status: accepted.

## Context

Version 4 of `10-claim-gated-admission.md` accepts as a ticket paymaster
any account whose code is the template, a key and a denomination (CG-10,
decision record 0057). Anyone can deploy one and sign tickets for
themselves. Under CG-3 a wrapper refused at its proof leaves no pending
transaction, so each junk proof costs such a self-issuer a fresh slot and a
ticket it signs, and costs every node it reaches a ticket check, a prefix
simulation and a proof verification.

Two defences are on the table, and the owner has asked for both to be
priced before either is chosen:

- **Issuer memory.** After $k$ proofs have failed under one issuer's
  tickets in an epoch, a node refuses that issuer's tickets for the rest of
  the epoch.
- **A node list.** A node accepts only the tickets of the issuers it lists.

Each censors someone. Issuer memory lets a holder of honest tickets close
an honest issuer. A node list leaves out every sender whose issuer a node
does not list. A clause would choose between them; an experiment can show
what each costs first.

## Decision

1. **No clause.** `10-claim-gated-admission.md` stays at version 4, and
   neither defence is in the reference's pool or in the vectors.
2. **The simulator models both, around the clauses** (`sim/emem_sim/issuers.py`).
   A guard on each node's frame pool runs, in CG-2's place and before the
   claim's own checks, the node list's refusal (`ErrIssuerUnlisted`) and
   issuer memory's (`ErrIssuerRefused`). It counts failed proofs by issuer
   and epoch where CG-4 records them, and closes an issuer at the $k$-th.
   Both refuse before the ticket's signature is checked, since a node reads
   the issuer from the paymaster's code first (CG-10).
3. **A claim's issuer is the simulator's, not the model's.** MD-6's claim
   has no issuer. The loads that make claims name it in a registry, and the
   guard reads it there.
4. **What a guard counts.** By load: the ticket checks it ran, the prefix
   simulations, and its refusals. Proofs verified stay in the aggregator's
   count (decision record 0037).
5. **The adversary.** `JunkProofs` hands every node wrappers whose proofs
   fail, each from a fresh sender with a valid ticket. A self-issuer moves
   to its next paymaster at a node that refuses the current one. A holder
   of honest tickets keeps to the honest issuer.

## Consequences

- Experiment 25 prices both defences against version 4 as written. The
  choice between them, or neither, stays open.
- The guard wraps three methods of the reference's frame pool
  (`_check_claim`, `proof_verified`, `_simulate`). A change to them changes
  what it counts, and `sim/tests/test_sim.py`'s `TestIssuers` checks the
  counts.
- *Not modelled*: a node that learns of another node's failed proofs, so
  closure spreads only to the nodes an adversary reaches itself; and a
  ticket paymaster's FP-11 cap of one pending transaction, which the
  experiment sets aside by having honest spends pay for themselves.
