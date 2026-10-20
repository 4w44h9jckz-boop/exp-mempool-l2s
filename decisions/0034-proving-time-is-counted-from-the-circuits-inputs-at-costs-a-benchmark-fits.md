# 0034. Proving time is counted from the circuit's inputs, at costs a benchmark fits

Date: 2026-10-13. Status: accepted.

## Context

EIP-8288 (Draft; read at `258836f9`, the commit `docs/spec/README.md` pins,
and unchanged on master at `3db7d3f4` on 2026-10-13) has every mempool node
prove a recursive STARK over what it holds every `AGGREGATION_INTERVAL`, and
gives a node short of time an order to fill it in: "If a node anticipates
that it will not have enough proving time to aggregate in _all_ aggregates
that it saw, it should prioritize in the following order: 1. Its own
aggregate from the previous round 2. Removing anything that needs to be
removed 3. Other nodes' aggregates, in descending order of how many new
transactions they will add to the aggregate 4. Users' transactions, in
descending order of priority fee". AG-7 already takes that order, and
decision record 0012 read it as the order that fills the wrapper limits. It
gives no proving time, no hardware and no budget.

An earlier argument about in-mempool aggregation makes the interval a
falsifier: if proving one aggregation interval on commodity hardware takes
longer than the interval, only builders can aggregate, and the operator set
stops being dynamic. An earlier problem record names the fee-ordered fallback
as the cost, and a second the re-proving that a discard causes, which nothing
limits. Experiment 06 left the question open, since its nodes spent a fixed
delay or none (its README, "What it does not show"). Decision record 0033
supplies a measurement: leanVM's own benchmark, run on this machine.

## Decision

1. **The clause counts, and the simulator waits.** AG-9
   (`docs/spec/05-aggregation.md`, version 2) gives an aggregate a proving
   time, and with `proving_budget` set makes AG-7 list only what fits, going
   on past what does not, as it does for the wrapper limits. The simulator
   sends an aggregate its proving time after the tick, and a node proves one
   aggregate at a time, so without a budget a tick that comes while it is
   still proving is skipped. With the four costs at 0, their value in the
   profile, nothing changes: experiment 06's runs are the same.
2. **Proving time is linear in the circuit's inputs.** The EIP's circuit
   takes "[deps, witnesses, recursive_proofs, recursive_deps_list,
   discards]" and its logic is "verify inputs, merge and discard". So an
   aggregate costs a fixed `prove_base`, `prove_recursive` for each recursive
   STARK it takes in, and `prove_sig` or `prove_stark` for each triple it
   verifies from a direct witness. A discard costs nothing of its own. The
   linear form is a model; leanVM's prover pads its tables to powers of two,
   so its time moves in steps, and the fit smooths them.
3. **The costs are fitted from leanVM at `1f9e4c4f` on this machine**
   (`bench/leanvm/fit.py`, `bench/results/2026-10-13-leanvm.md`):
   `prove_base` and `prove_sig` are the intercept and slope of aggregates of
   1 to 245 leanSPHINCS signatures, and `prove_recursive` the slope of
   recursions over 2, 4 and 8 children of 16 signatures each, the most one
   wrapper may carry. The recursion over 16 children, leanVM's
   `MAX_RECURSIONS`, did not fit in the memory a process may use here and
   was killed; the 8 used 12.3 GiB. Only the recursion line's slope is
   used, since an aggregate's fixed cost is the signature line's intercept.
   leanVM has no leanSTARK of a user's own to verify, so `prove_stark` is
   taken as `prove_recursive`: a user's proof and a child aggregate are both
   STARKs the circuit verifies. The "laptop" in the experiment is this
   machine's costs scaled by the README's time over ours for the same kind
   of work: `prove_base` and `prove_sig` by the ratio for
   `aggregate --sphincs 245`, `prove_recursive` and `prove_stark` by the
   ratio for the README's 2-to-1 recursion. Each is a ratio between two
   machines on one benchmark, not a model of the laptop.
4. **Each triple is covered by the cheapest source the order offers.** As
   AG-7 lists a transaction, a triple not yet covered is covered by the
   node's own previous aggregate if that covers it, then in step 2 by the
   received aggregate it is listed from, then by its direct proof if the
   node verified one, and last by the first aggregate the node received that
   covers it. A recursive STARK taken in covers all its triples at once. The
   node therefore keeps every aggregate it receives; the EIP does not say
   how long a node keeps proofs (decision record 0012 kept proven triples
   for good), and an aggregate it never keeps is one a later round could not
   use.
5. **A budget is per aggregate, and is one interval in the experiment.** The
   EIP says "every `AGGREGATION_INTERVAL` milliseconds", so a node that sends
   one aggregate an interval proves at most an interval's worth into each. With
   that cadence a node proves once an interval whatever is discarded, so the
   second record's unbounded re-proving does not arise; what a discard costs is
   the share of an earlier budget spent on what was later discarded, which is
   what experiment 24's flood measures.
6. **A node that cannot prove aggregates nothing and builds nothing.** In
   the experiment's section 2, where the provers have the laptop's costs, a
   node without the means to prove has a budget of 0, so it admits wrappers and sends no aggregate, and the
   proposer rotates through the provers alone, since a block with
   dependencies needs its recursive STARK. A builder market that would let a
   non-prover sell its slot to a prover is not modelled.

## Consequences

- Experiment 24 measures delay, reach and what aggregates carry against
  demand for nodes with no proving time, and for this machine and the
  laptop with a budget of one interval and without one, against the share
  of nodes that can prove, and under a flood of transactions with
  dependencies that never pay.
- At this machine's costs a budget of one interval holds no recursive input
  and no leanSTARK triple, since `prove_base` and one of them come to more
  than 1000 ms; the experiment runs that case as measured rather than
  choosing a budget that fits.
- Memory is not in the count. The benchmark reports leanVM's peak memory, a
  floor on who can prove at all, and the post quotes it beside the times.
- Proof sizes are not in the simulator, as before; the benchmark reports
  them, and experiment 06's bytes a second can be priced at them.
- The FOCIL extension, whose includers prove a recursive STARK for their
  lists, stays Not modelled: an includer that already aggregates has one to
  reuse, and one that cannot prove is section 2's non-prover.
