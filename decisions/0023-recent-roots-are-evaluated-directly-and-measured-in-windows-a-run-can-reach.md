# 0023. Recent roots are evaluated directly, and measured in windows a run can reach

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 19 asks how many admitted spends outlive their recent root
in pools, against the window's length, congestion and a builder that delays
them, and what each node re-checks when a root leaves the window. An earlier
account abstraction study records that a builder that delays inclusion can
force a spend to be proved again. An earlier design study records that
EIP-8272 declines to guarantee the root writes themselves, and that a set
whose writes stop keeps working for the window and then stops.

The model had no recent roots. EIP-8272 is Draft, and was read in full at
`258836f9` (`refs/refs.md`). It leaves `RECENT_ROOT_CODE` as `TBD`, and that
one constant is the consensus artefact, the mempool's admission predicate
and the oracle a direct evaluation must match.
Its window is 8191 slots, which at 12 s is about 27 hours; the simulator's
runs are 30 minutes.

## Decision

1. **The verifier frame is evaluated directly, never executed.** The EIP
   lets a client do this ("a client MAY evaluate this frame directly"), and
   there is no bytecode to execute. `recent_root_code` is a named string
   compared by equality, as every code in the model is (MD-2). The frame's
   `reverts` observation stands for a halt for want of gas, which the unset
   code would decide. So a conforming implementation here agrees with the
   EIP's predicates, not with its gas.
2. **Source ids, entries and storage keys are injective functions of the
   EIP's inputs, not keccak256.** The EIP's hashes exist so that two
   different `(source, slot, root)` never share an entry and two sources
   never share a key. `ref/python/emem/recentroots.py` keeps that property
   with sha256 over the same fields, and writes a source id as
   `address/salt` so that vectors can name one by hand.
3. **A head carries its slot, and a block is at the slot it is built
   for.** RR-2 takes the slot from EIP-7843's `slotNumber`. The simulator's
   chain gives a block its parent's slot plus one plus the slots missed
   since, so the pool's current slot, the head's plus one, stalls in an
   empty slot exactly as the EIP says it does.
4. **The margin refuses what RR-7 would evict within `root_margin` slot
   advances.** The EIP leaves the margin to the node. Reading it as a
   distance from eviction makes 0 the EIP's window exactly, so the
   `eip-8272` profile has 0. A pool applies the margin, and a block does not
   (RR-8).
5. **RR-6's recheck is FP-15 step 3's re-run.** The EIP asks for the age
   and storage predicates to be checked again when a dependency may have
   changed. The frame pool already re-runs a prefix whose dependencies
   changed, and the two evict the same transactions. In the model an entry
   a transaction depends on changes only when a head goes back, which the
   simulator never produces, so the re-runs the experiment counts are the
   other dependencies' and RR-6 adds none.
6. **Eviction for age is by index, without a re-run.** RR-7 removes a
   transaction once its root expiry, recorded at admission, is reached.
   That is the EIP's "evict it when any tuple reaches" with the index it
   asks clients to keep, and is why a slot advance re-runs nothing.
7. **The windows are scaled down, and the EIP's is run as well.** Section 1
   uses 8192. Sections 2 to 4 use 4 to 64 slots, so that a delay a run can
   produce reaches the window's end. Nothing else in the model depends on
   the window's absolute length, so what moves with it is the ratio of the
   delay to the window, in slots. That is the quantity the results report.
8. **Each slot's builder is drawn at random from ten.** `ChainConfig.draw`
   draws it with a stream of the scenario's own. With rotation a filtering
   share comes round at fixed intervals. With a draw, a run of filtering
   builders is as long as chance makes it, and those runs are what delay a
   spend past its window.
9. **Wallets are assumed, not sourced.** A user proves for 12 s against the
   latest root written at or before its node's head. It sends again after
   every block that leaves its spend out. When a node refuses the spend for
   its root (`ErrFrameRootExpired`, `ErrFrameRootUnknown`), it proves again
   against the latest root. The proving time is a parameter of the
   experiment, not a measurement. The verifier frame's limit is 10,000 gas,
   above the 7,588 an earlier design study measured for one tuple with
   storage cold.
10. **A root source writes from one account, every slot.** The account's
    writes queue on its nonce, so a write a builder leaves out holds back
    the writes after it until a builder that does not filter includes it.
    A source with several writers, which that design study's fallback for
    stopped writes asks for, is not measured.

## Consequences

- `docs/spec/08-recent-roots.md` version 1, clauses RR-1 to RR-8, and 34
  hand-written cases in `conformance/vectors/recent-roots/`.
- The `eip-8272` profile. `Head.slot`, `Tx.root_writes`,
  `FrameTx.root_writes` and `Frame.roots` in the reference. Every vector
  and experiment before this one leaves them at their defaults, which is
  why no earlier results file moves.
- `ChainConfig.draw`, `RootWriter` and `RootSpendLoad` in the simulator.
- Experiment 14.
- Not modelled: the contract's bytecode and gas, activation, reorgs, the
  write operation's failures, introspection, and a wallet that could see
  from a root's age that proving against it is futile.
