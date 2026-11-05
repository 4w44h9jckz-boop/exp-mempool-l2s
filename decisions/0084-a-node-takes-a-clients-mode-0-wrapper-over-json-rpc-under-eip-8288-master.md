# 0084. A node takes a client's mode 0 wrapper over JSON-RPC, under EIP-8288 as master writes it

Date: 2026-11-05. Status: accepted.

## Context

A transaction authorized by a leanSPHINCS dependency, as EIP-8288 master
writes it, could not reach a node's pool through `11-surface.md`. The gap
was found by running one such transaction through skandha's node against a
local chain (`exp-e2e-frames` experiment 22: `c39af8e` for the chain id,
`70c8fc3` for the mode 4 frame). The same transaction went to the patched
client's own pool and was mined, with a valid block proof (`cc5d4c9`), so the
gap was the node's, not the chain's:
- **No surface profile had dependency frames.** SF-1 named `eip-8141` and
  `hegota-testnet` only. A node's pool profile must also be a surface
  profile, so AG-1's `eip-8288-master` could not be chosen, and FP-3
  refused a mode 4 frame.
- **The chain id was the profile's.** A local chain had to take 8141.
- **No proof reached the pool.** SF-5 takes a transaction alone. AG-6
  refuses a dependency no wrapper proved, and SF-3 did not even decode a
  dependency frame's triples.

EIP-8288 gives the wrapper, `[transactions, mode, content]`, with mode 0's
`[deps, proofs]` "intended to be used primarily by clients broadcasting
their transactions". It defines no JSON-RPC method.

## Decision

1. **A surface profile `eip-8288-master`.** It is beside the two earlier
   profiles, for AG-1's pool profile of that name, with chain id 1 by
   default. A node may set its own chain id.
2. **SF-3 decodes a dependency frame's triples into `deps`.** It does so
   under a profile with dependency frames: each whole 96 bytes is a scheme
   word, a data hash and a key. Under `sig_hash`, a zero data hash is
   written as EIP-8141's `compute_sig_hash` of the bytes received, which
   the surface already computes for CG-12. AG-4 then finds no zero to
   replace.
3. **`frames_sendWrapper` takes a mode 0 wrapper from a client** (SF-10):
   - the transactions' bytes, the `deps` and exactly one proof per triple,
     a different count being a parameter not of the method's shape;
   - each transaction through SF-2, then FP-2 to FP-7 and the client's
     verdict, as SF-5 does;
   - each leanSPHINCS proof checked by the node's prover's
     `verify-sphincs`;
   - the wrapper judged by AG-5 and AG-6, as the vectors judge one.
4. **A proof a node cannot check does not verify.** That covers a node with
   no prover, and a proof of another scheme. So such a node refuses every
   wrapper with a dependency rather than admit a transaction on an
   unchecked proof.
5. **No mode 1 from a client, and no wrapper between nodes.** A recursive
   STARK is a node's own (AG-7). A node does not relay a transaction with
   dependencies, since a peer could not admit it without the proofs. A
   client that wants several nodes to hold a transaction sends its wrapper
   to each. Under `gossipsub`, accepting a message forwards it, so a node
   that admits such a transaction from a peer ignores the message rather
   than accept it (SF-7).
6. **The mode 0 check goes through the prover, not natively.** Neither the
   reference nor skandha has a leanSPHINCS verifier. The prover's contract
   gains a mode, `verify-sphincs <publicKey> <message> <signature>`,
   printing `{"verified": true}` or `{"verified": false}` with exit status
   0, and a refusal with exit status 2, as its other modes do. The stubs
   (`conformance/prover-stub.py` and skandha's) mirror it. `exp-e2e-frames`
   experiment 19's prover has no such mode at `47f5496`, nor on its branch
   at `d3edeb9` (its `verify` mode checks a leanSTARK). Until it does, it
   takes an unknown mode's name for a program's path and stops with a
   non-zero exit status, which item 4 counts as not verified, so a node
   naming it refuses every wrapper with a dependency rather than admit one.

## Consequences

- **A node under `eip-8288-master` admits a leanSPHINCS-authorized
  transaction** that reaches it in a client's wrapper, and its own
  aggregates then fold that signature (AG-11).
- **Each node needs the wrapper from the client.** Two nodes do not pass
  dependency transactions to each other until wrappers travel between nodes,
  which this record leaves out.
- **A node with no prover takes no wrapper.** Under `eip-8288-master` it
  then admits no transaction with a dependency.
