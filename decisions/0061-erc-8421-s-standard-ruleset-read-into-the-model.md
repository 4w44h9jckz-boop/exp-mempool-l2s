# 0061. ERC-8421's standard ruleset, read into the model

Date: 2026-10-20. Status: accepted.

## Context

ERC-8421 (Draft, ERCs pull request 2028 at `493ba8ac`, read 2026-10-20)
defines a standard alternative mempool with per-entity budgets, stake,
storage association, reputation and keyed-nonce limits. The model runs no
EVM and has no chain, so each rule needs a reading in its terms, and some
of the ERC's text leaves choices open. `14-erc-8421.md` states the
readings as clauses; this record says why.

## Decision

1. **Stake is on the account.** MD-2 gains `stake`, `unstake_delay` and
   `withdrawing`, what `getDepositInfo` at the Staking Registry returns. The
   registry's storage layout is not the ERC's to fix, and a pool reads
   only its answer.
2. **Association is observed.** A read or write carries the address its
   slot is associated with, as a tracer finds it under ASSOC-010 and
   ASSOC-020. The model never computes keccak preimages, as it never runs
   code; the tracer's range parameter rides in the descriptor.
3. **Per-chain constants get model values.** `MIN_STAKE_VALUE` is one
   ether and `STAKING_REGISTRY_ADDRESS` the name `staking-registry`. A chain
   loads a child descriptor that sets its own.
4. **`pre_verify` by target, wherever it stands.** A `DEFAULT` frame whose
   resolved target is the next approving frame's is `pre_verify`; the
   ERC's distinction by created code needs a simulation the shape check
   comes before.
5. **The expiry frame's gas counts against no entity**, since the ERC
   attributes the frame to none.
6. **The nonce is checked in the Acceptance Algorithm's step 6**, with the
   limits, since LIFECYCLE-010 is a lifecycle rule and allows a nonce one
   above a pending transaction's.
7. **Reputation in integers, as written.** `opsAllowed` takes the
   product `inclusionRate * min(included, ...)` with the division last,
   rounding down. A pool starts with the counters it is given.
8. **Blame spares every entity but the blamed one**, except that a
   staked factory absorbs a sender's failure and a staked sender absorbs
   any. REPUTATION-310 says the payer is spared, and REPUTATION-320 and 330
   say who absorbs, which leaves the factory under an unstaked sender's
   failure to this reading.
9. **Propagation is a module the pool does not check.** PROPAGATION-010 to
   050 are transport rules the ERC leaves the wire for; the descriptor
   holds them and the pool does nothing with them.
10. **A limit counts what the pool would hold.** LIFECYCLE-030 keeps "at
    most" so many pending transactions, and REPUTATION-020, 210 and 220
    limit the "entries in the mempool", so every count leaves out the
    transactions a replacement removes; otherwise a payer at its limit
    could never have a transaction repriced.
11. **A replacement moves `seen` by address.** REPUTATION-040 names roles;
    the model counts each address of a transaction once, so a replacement
    moves `seen` only for addresses that join or leave, which is the role
    rule whenever the roles' addresses differ.
12. **Inclusion is FP-15's step 1.** The model's `reset` carries no
    receipts, so a transaction removed because a key's sequence passed it
    counts as included for each of its entities.
13. **Revalidation re-runs what reads state**, PREFIX-110, stake, budgets,
    simulation and trace, and blames the entity a re-run fails at: a
    frame's, or the one over its budget. A removal at `reset` evicts what
    it leaves with a nonce gap, as a replacement does under LIFECYCLE-020,
    since LIFECYCLE-010 allows no gap at all.

## Consequences

- The ruleset's descriptor replaces six frame-pool modules and adds the
  ERC's. A fresh sender is asked for nothing beyond the frame pool's own
  rules, which AM-16 derives and a vector checks.
- *Not modelled*: wall-clock refresh, `THROTTLED_ENTITY_BLOCK_COUNT` and
  `THROTTLED_ENTITY_LIVE_BLOCKS`, and propagation.
