# 0025. A node verifies proofs under one key in a batch it holds for a window

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 14 takes up an earlier problem record: the one measured
economy for verifying pairing proofs cheaply is a batch under one
verification key, and the tier that admits a transaction to the public
mempool decides one transaction at a time. It asks for the delay a node's
batching window adds against the verifications it saves. A second record
adds the case that decides whether a batch is safe to form in public: one
invalid proof fails the whole batch.

No source read here specifies a node that batches. EIP-8141 admits a frame
transaction on its own validation prefix, metered per operation. EIP-8288
aggregates hash-based signatures and STARKs by recursion into one STARK that
a node proves every interval, and has no pairing proofs to batch. The
measurement is Commonware's, `/blogs/batch-pari`, read in a snapshot taken
on 2026-09-15: Pari proofs, single-threaded on an M5 MacBook Pro, verified
one at a time and as one batch for 2, 32, 512, 8,192 and 65,536 proofs. Its
mechanism, a random linear combination of the proofs' pairing equations,
needs every proof in the batch to be under the same key. The same page
describes no defence against a bad proof; Commonware's consensus post
bisects a failed batch and then blocks the sender by its staking identity.

## Decision

1. **No clause changes.** Batched verification is what a node does before
   its pool sees a transaction, and the pool's answer is the one it gives
   without batching: a transaction whose proof fails never reaches it, and
   one whose proof passes meets the same rules. It is the simulator's,
   in `sim/emem_sim/batch.py` and `sim/emem_sim/network.py`.
2. **The proof is declared beside the transaction**, as an EIP-8288
   dependency is, and verified outside the validation prefix, whose gas is
   unchanged. In the simulator it is a flag, valid or not, kept by the
   network for the transaction's hash; nothing verifies anything.
3. **The costs are Commonware's.** A batch of a measured size costs what was
   measured; between two sizes the cost is interpolated on a log-log line; a
   proof alone costs the 65,536-proof run's individual rate, 0.5845 ms. Each
   node has one core for this, and a batch's verification time delays the
   admission of everything in it. The parallel measurement is not used.
4. **A window per node.** The first proof a node holds opens a batch, which
   closes `batch_window` seconds later, or when `batch_max` are held. A
   window of 0 verifies each proof on arrival, one at a time. A node relays
   a transaction only once its pool has admitted it, as go-ethereum relays
   only pending transactions, so each hop pays its own window. A transaction
   held or being verified counts as known, and one whose proof failed is
   remembered and refused again without a second verification.
5. **A failed batch is bisected**: split in halves, each checked, down to the
   proofs that fail. Blocking the sender is Not modelled: an invalid proof
   comes from a fresh sender, and a public mempool has no identity a node
   could block it by that the sender cannot replace.
6. **The adversary hands every invalid proof to every node itself.** An
   honest node relays no transaction whose proof failed, so this is what it
   takes to spoil a batch at every node; it pays nothing, since nothing it
   sends is admitted.
7. **Pricing a batch in gas is an interpretation.** Section 2 of experiment
   16 scales the gas of the pairing check in a one-nullifier private spend,
   181,000 of its 211,828 (ethresear.ch topic 25889), by the share of time
   the batch saves. Commonware measured Pari over BLS12-381, and the spend
   verifies Groth16 over BN254 by precompile; only the ratio is carried
   across, and no EIP prices a batch. The section says so in its text.
8. **Three seeds**, each with its own topology and arrivals, at rates of 1,
   10 and 100 proofs a second under the key.

## Consequences

- `sim/emem_sim/batch.py`; `batch_window` and `batch_max` in
  `NetworkConfig`, and a node's held batch, verifier and counts; `ProofLoad`
  and `InvalidProofLoad` in `sim/emem_sim/workload.py`.
- Experiment 16.
- Not modelled: blocking a peer that sent an invalid proof, a pool that
  admits before verifying and evicts on failure, proofs under several keys,
  parallel verification, and a node that batches what it relays rather than
  what it admits.
