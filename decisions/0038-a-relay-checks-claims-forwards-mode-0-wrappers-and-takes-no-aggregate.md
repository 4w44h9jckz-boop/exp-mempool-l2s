# 0038. A relay checks claims, forwards mode 0 wrappers, and takes no aggregate

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 29 asks what it costs and saves to let nodes relay without
verifying. A claim is checked before any proof, so a node could relay
claimed transactions without verifying their proofs.

EIP-8288 (Draft, at `258836f9`) has no such node: "When they see a wrapper,
they validate its proof (either direct proofs or a recursive STARK). If
valid, they accept it" (Recursive Mempool Aggregation). It also has no
mode 0 forwarding: mode 0 "is intended to be used primarily by clients
broadcasting their transactions" (Mempool Wrapper Object), and a node sends
its peers one aggregate each interval. `docs/spec/10-claim-gated-admission.md`
version 1 had every node verify.

## Decision

1. **A relay is a node, not a profile.** `verifies` (CG-1) is read under
   `claims` only, and a node with it false is a relay (CG-7). A network
   mixes the two by giving some nodes a pool of the profile with `verifies`
   false, which the simulator's per-node pools already do.
2. **A relay takes no aggregate.** A mode 1 wrapper carries no claim of its
   own. A relay that forwarded one unchecked would carry recursive STARKs
   that cost every verifier a check with no claim bought, which is the free
   work claims exist to price; one that checked it would be a verifier. So
   CG-7 refuses every mode 1 wrapper at a relay, before AG-5's checks.
3. **A relay runs CG-3 and stops before the proof.** It checks the
   signature, the claim and FP-2 to FP-10, as a verifier does, then records
   the wrapper's triples as *relayed* rather than proven, and admits the
   transactions, so that FP-2 deduplicates what it has passed on and FP-15
   drops what a block makes stale. A relayed triple is never aggregated,
   since a relay builds no aggregate.
4. **CG-5 binds forwarding.** A relay makes CG-5's record when it accepts a
   wrapper, so it passes on one wrapper under each claim, as R4 has a
   verifier verify one proof under each. CG-4 never fires at a relay, since
   no proof fails there, so R3 runs only at verifiers.
5. **A relay pushes what it accepts to every peer, once.** That is how AG-7
   sends an aggregate, and how `forward_wrappers` already forwarded mode 0
   wrappers (decision record 0013). A protocol that announced a wrapper and
   let each peer fetch it would deliver each once; that is not modelled, and
   the floor a relay would pay with it is one copy of each proof it
   forwards.
6. **A relay proposes nothing.** A builder aggregates the proofs of what it
   includes (EIP-8288, Recursive Mempool Aggregation), which is a
   verifier's work. The simulator's chain draws proposers from the
   verifiers.
7. **With relays, verifiers forward mode 0 wrappers too.** Otherwise a
   transaction handed to a verifier reaches the relays only in aggregates,
   which they refuse, and its reach is the verifiers the verifier is linked
   to. So `forward_wrappers` is set at every node, and a network in which
   every node verifies is run with and without it, so that what forwarding
   costs is apart from what relays cost.
8. **The verifiers are the first nodes by name.** The topology is drawn at
   random after the nodes are named, so the first names, as many as there
   are verifiers, are a random draw with respect to position in the graph,
   and the same draw at every share.

## Consequences

- `docs/spec/10-claim-gated-admission.md` goes to version 2, and every
  vector of version 1 holds unchanged; `conformance/vectors/claim-gated/`
  gains CG-7's.
- The reference's aggregator and frame pool implement CG-7; the simulator
  forwards at relays, and counts the proofs reaching each node by the
  wrapper's kind and maker, so that what relays receive of junk can be set
  against what they saved.
