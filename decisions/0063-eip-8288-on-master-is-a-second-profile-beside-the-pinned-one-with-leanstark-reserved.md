# 0063. EIP-8288 on master is a second profile beside the pinned one, with leanSTARK reserved

Date: 2026-10-20. Status: accepted.

## Context

`05-aggregation.md` reads EIP-8288 at `258836f9`, where both of its schemes,
leanSPHINCS and leanSTARK, are defined. On ethereum/EIPs master at
`899bef0a` (read 2026-10-20) the EIP has moved:

- `DEP_VERIFY_FRAME_MODE` is 4, not 3;
- `LEANSTARK_SCHEME` is reserved: "a frame that uses it is invalid until
  `get_deps_hash` is defined for it", and `get_deps_hash` is defined for
  lists of leanSPHINCS dependencies only;
- a dependency frame may not be part of an atomic batch, so the frame before
  it carries no `ATOMIC_BATCH_FLAG`, and its `limits.state` is 0;
- a `data_hash` of 32 zero bytes stands for the containing transaction's
  signature hash in `dependencies(tx)`;
- a mode 1 wrapper, like a mode 0 one, must have `deps` equal to the sorted,
  deduplicated union of its transactions' dependencies (its check 5);
- the recursive STARK's gas, $30000$ a declared triple, is added to each
  transaction's intrinsic gas instead of being charged to the block;
- a dependency frame gets a frame receipt.

The aggregator is asked for "the schemes EIP-8288 defines today, its
hash-based signatures, with the STARK scheme marked as reserved, as the EIP
marks it". Experiments 06 and 24 to 26 rest on the pinned reading and use
leanSTARK dependencies throughout.

## Decision

1. **A second profile, `eip-8288-master`, beside `eip-8288`.** The pinned
   profile and every vector and experiment on it stay as they are. The new
   profile is the EIP at master `899bef0a`; a later reading of master
   changes its column and bumps the document's version. `05-aggregation.md`
   goes to version 4.
2. **Five parameters carry the difference** (AG-1): `dep_frame_mode`, 3 or
   4; `leanstark`, `defined` or `reserved`; `dep_in_batch`, whether a
   dependency frame may follow a frame with `ATOMIC_BATCH_FLAG`;
   `zero_data_hash`, `literal` or `sig_hash`; and `mode_1_union`, whether
   AG-5 checks a mode 1 wrapper's `deps` against its transactions. The state
   limit of 0 was already AG-2's reading of the pinned text (decision record
   0012) and is now the EIP's.
3. **The signature hash is the transaction's hash.** The model has no
   signature hash apart from MD-7's hash of the whole transaction, which no
   other transaction shares; a zero `data_hash` stands for it, so two
   transactions that each declare one never share that dependency.
4. **Mode 1's union is checked as far as a node can.** A mode 1 wrapper may
   name a transaction by a hash the node cannot resolve. AG-5 then checks
   that `deps` holds every dependency of every transaction the wrapper
   carries or the node resolves, and holds nothing else when it resolves
   them all. The EIP asks for equality; a node that cannot see a
   transaction cannot check its part of it.
5. **Not modelled.** The per-transaction charge of the recursive STARK's
   gas: FEE-4 is the model's and does not depend on a profile, so under
   `eip-8288-master` a payer's `max_cost` is understated by $30000$ a
   declared triple, and AG-8 still charges the block. The frame receipt, which
   the model has no place for. `DEPS_HASH` itself, which is still to be
   chosen: the model's recursive STARK is the list it covers.

## Consequences

- Vectors under `eip-8288-master` hold only leanSPHINCS triples, with a
  leanSTARK one refused. The existing aggregation vectors are re-read
  against version 4 and keep their meaning under `eip-8288`.
- The aggregator's clauses, AG-5 and AG-7 to AG-9, are unchanged; their
  vectors under the new profile are what a second implementation's
  aggregator is checked against.
- An experiment on `eip-8288-master` understates a sponsor's exposure by the
  STARK's gas, which matters only where the payer's balance binds.
