# 0083. A node names a real prover, and folds only the signatures it holds

Date: 2026-11-04. Status: accepted.

## Context

`05-aggregation.md` models proofs as flags (decision record 0012). A real
prover exists in a sibling repository: `exp-e2e-frames` experiment 19's
`prover/` at `47f5496`, over leanVM at `3cbac04`. It has two modes a mempool
node can use:
- **`aggregate <claims> <out>`** folds leanSPHINCS signatures, each a public
  key, a message and a signature, with leanVM's own aggregation. It passes
  no earlier aggregate as an input.
- **`verify-aggregate <proof> <claims>`** checks the bytes against the keys
  and messages.

Each prints one JSON line, and a refusal is `{"error": ...}` with exit
status 2. The same experiment records that leanVM at `3cbac04` recurses only
over proofs of its own bytecode (README, Amendment 3), so nothing it makes
covers a leanSTARK dependency, whose proof is another program's.

A node needs to run against that prover so that its aggregates carry real
proofs, and the clause must say what changes. This session cannot build the
prover, so it is tested against a stub of the same contract.

## Decision

1. **The prover is a node setting,** `prover`, not a profile's. Every profile
   leaves it unset, and the flags stand. A node that sets it names a command
   with the two modes above (AG-11).
2. **What it changes:**
   - a leanSPHINCS triple's key and message are 32 bytes each;
   - a mode 0 wrapper carries each signature as a witness;
   - a received aggregate is checked by `verify-aggregate`;
   - the node's own aggregate is `aggregate`'s output over the triples it
     lists.
3. **Only signatures the node holds are folded.**
   - A transaction is in the node's aggregate only if every dependency is a
     leanSPHINCS triple whose witness the node keeps.
   - The aggregate takes no recursive input, since the prover passes none.
   - So a transaction known only from a received aggregate, or with a
     leanSTARK dependency, is admitted (AG-6) and not folded.
4. **A mode 0 signature is the node's own check.** The prover has no mode for
   one signature, and a leanSPHINCS check is native and cheap. If the node
   took a witness wrongly, `aggregate` refuses, and the node sends nothing
   that interval.
5. **Measured, not decided by.** The prover reports its proving time and peak
   memory, and the node records them. AG-9 and AG-10 still decide by the
   profile's costs, so that what a node lists does not depend on the
   machine.
6. **The stub.** `conformance/prover-stub.py` follows the contract with
   stand-in cryptography:
   - a signature is the SHA-256 of a tag, the key and the message;
   - an aggregate is a tag and the SHA-256 of the sorted, deduplicated keys
     and messages;
   - its `sphincs <seed> <message>`, the prover's own mode for a key and a
     signature, gives a stand-in key and signature, so that a run that makes
     its signatures with the prover runs on the stub too.

   The vectors in `conformance/vectors/aggregation/ag-11-prover.json` run
   against it. It checks the files, the output and the exit codes the node
   reads, not leanVM's cryptography.

## Consequences

- **The bytes are real,** under a real prover, and a run against it measures
  proving time and memory instead of computing them.
- **Folding stops at what a node holds itself.** Two nodes that each hold
  half of the signatures cannot fold the other's half until the prover
  takes children. EIP-8288's merge of aggregates is then not exercised.
- **leanSTARK dependencies stay outside every aggregate** until leanVM
  recurses over other programs.
- **The vectors judge the contract, not the cryptography.** A real prover's
  own answers are its tests, run where it can be built.
- **The stub has to mirror the prover's output forms, not only its
  checks.** The first run on the real binary stopped because its `sphincs`
  mode prints bare hex and the stub printed `0x`, so no real key was of
  item 1's form (`exp-e2e-frames` experiment 22, `992094b`). The stub now
  prints bare hex there too, and AG-11 says the prover reads either form,
  while a triple's key and message keep item 1's `0x`.
- **A node keeps its prover resident to fold every interval.** Started for
  each fold, it took 2.7 to 3.4 s, over the 1,000 ms interval. The contract
  is one process for each call, so a resident prover is a different
  contract, not yet specified.

## Amendment, 2026-11-05

Item 4 is superseded by decision record 0084. The prover has a mode for one
signature since `exp-e2e-frames` `3209255`, `verify-sphincs`, and a client's
mode 0 proof is checked with it (`11-surface.md`, SF-10), so that a node has
no leanSPHINCS verifier of its own to keep. What item 4 says of `aggregate`
still holds: it refuses a witness that does not open at its message.
