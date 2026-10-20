# 0012. EIP-8288 is specified as a layer on the frame pool, with its open readings explicit

Date: 2026-10-08. Status: accepted.

## Context

The plan's item 9 asks what EIP-8288's in-mempool aggregation does to the delay
and the capacity of transactions that carry signatures and proofs as
dependencies. The EIP is Draft, read from ethereum/EIPs at `258836f9`. It
specifies a frame mode, a wrapper object that carries proofs beside
transactions, a per-interval aggregation step, mempool limits and a
block-level gas charge, and leaves several choices a pool has to make
unstated. `docs/spec/05-aggregation.md` states them as clauses, and this
record is where it says which readings it took.

## Decision

1. **A layer, like MATCHA.** A profile `eip-8288` is the `eip-8141` frame pool
   of `02-frame-pool.md` version 4 with AG-1 to AG-8 on top. The frame pool
   document does not change: a mode 3 frame stays `ErrFrameMalformed` under
   every FP-1 profile, as the EIP-8141 text has it, and `05-aggregation.md`
   says which FP clauses it amends. MD-6 gains the `deps` field the layer
   needs (`00-model.md` version 3).
2. **Proofs are flags.** A proof verifies or does not; a recursive STARK is
   the list of dependencies its public input is the hash of, and a flag. A
   node can prove any subset of what it holds proofs for, because the EIP's
   circuit takes recursive proofs and witnesses and removes discards. This
   says nothing about proving cost, which the simulator treats as a delay an
   experiment sets.
3. **A dependency frame's `gas_limit` is its execution limit, and its state
   limit is 0** (AG-2). The EIP constrains a field EIP-8141 frames do not
   have; `limits` is `[execution, state]`, and the verification cost is
   execution.
4. **A dependency frame is outside the validation prefix's shape and its
   verification budget** (AG-3). The EIP never places the frame relative to
   the prefix. Its Test Case 1 puts one first, before the `VERIFY` frame that
   reads it, which FP-5's closed list of shapes would refuse. The frame is not
   executed, so its gas is no work for a node simulating the prefix.
5. **The per-transaction limits count the deduplicated list** (AG-4), as the
   EIP says, and are mempool rules only.
6. **Both readings of the wrapper limits are kept, as `cap_aggregates`**
   (AG-1, AG-5, AG-7). The EIP lists `MAX_LEANSIG_DEPS_PER_WRAPPER` and
   `MAX_LEANSTARK_DEPS_PER_WRAPPER` among the checks of a mode 1 wrapper and
   under "Mempool-Level Limits" as limits on "recursive STARK aggregation",
   and also says a node broadcasts "exactly one wrapper containing all
   currently active transactions, with exactly one STARK covering all their
   dependencies". Once a node holds two transactions with a leanSTARK
   dependency each, both cannot hold. The profile takes the limits, `true`,
   because they are stated as checks; `false` is the reading the second
   sentence and the Rationale's "fixed ~256 kB per `AGGREGATION_INTERVAL`"
   need. An earlier design study read the limit literally: one distinct
   dependency per 1,000 ms tick, so about 12 a slot.
7. **Under the cap, the EIP's order for short proving time fills the
   aggregate** (AG-7): the node's own previous aggregate, then other nodes'
   aggregates by how many transactions they add, then the rest by effective
   tip. It is the only order the EIP gives for choosing among transactions.
   Read with the cap, it keeps a node's aggregate on the same transactions
   until they leave the pool, which is a consequence to measure rather than a
   reason to read it otherwise.
8. **A hash a node cannot resolve** is dropped from a mode 1 wrapper, whose
   proof does not depend on the transactions, and refuses a mode 0 wrapper,
   whose first check needs them (AG-5).
9. **Proofs are kept** (AG-6). A node that has proven a dependency admits a
   transaction declaring it again, alone or in a wrapper. The EIP does not
   say when a node forgets a proof, and a pool that forgot them would refuse
   a transaction it had just evicted for capacity.
10. **The block's charge counts declarations and is paid by nobody** (AG-8).
    "The total number of dependency triples across all transactions in the
    block" reads as declarations; the charge counts against the gas limit,
    which is what a builder needs to know, and who pays it is left open, as
    in the EIP.
11. **`forward_wrappers` is a variant, not a reading** (AG-1, AG-7). The EIP
    sends only the aggregate. An earlier reading, on 2026-09-11, held that
    under EIP-8288 transactions are still gossiped individually, which is
    what a node relaying the users' wrappers at once would give; the variant is
    there to measure that reading against the text's.

## Consequences

- An experiment can set `cap_aggregates` and `forward_wrappers` and report
  what each reading implies, without either being called the EIP's.
- A transaction with dependencies is refused unless it arrives with proofs or
  its proofs arrived before (AG-6), so in the simulator such transactions
  travel in wrappers and ordinary gossip of them fails.
- The reference gains a `Dependency` triple and a `deps` field on `Frame`
  (`ref/python/emem/tx.py`), an aggregation module, a profile, and a block
  charge in the builder.
- If the EIP fixes any of these points, the clause that read it changes and
  `05-aggregation.md` bumps its version.
