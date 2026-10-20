# Documents

`spec/` is the specification. Read `spec/README.md` first for how clauses are
written and which source commits they were read from.

Beside it are readings, which are not normative: they fit a system that is
not in the specification onto its clauses, say what has been measured about
it here, and propose what the specification should add.

- `aztec-as-not-a-rollup.md`: Aztec's node, job by job, as it would run on
  L1's mempool with no blocks of its own (decision record 0047).

Background is not repeated here. For someone new to mempools, the primary
sources are, read in this order:

1. go-ethereum's transaction pool (`core/txpool/`): the pool and its gossip.
2. EIP-8141, section "Mempool": the EIP-8141 public mempool.
3. ERC-7562 and RIP-7560, to set beside EIP-8141: the validation rules of
   the other account-abstraction mempools.
4. EIP-7805 (FOCIL) and EIP-8184 (LUCID), for what comes after the public
   mempool.

Then `spec/01-nonce-pool.md` and `spec/02-frame-pool.md` say exactly what the
pools in this repository do.
