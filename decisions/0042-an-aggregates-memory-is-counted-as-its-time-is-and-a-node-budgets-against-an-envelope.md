# 0042. An aggregate's memory is counted as its time is, and a node budgets against an envelope

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 32 asks for a network in which a node proves only when its
memory allows. EIP-8288 says nothing of memory, as it says nothing of proving time; AG-9
(`docs/spec/05-aggregation.md`, version 2, decision record 0034) counts an
aggregate's proving time from the circuit's inputs, a recursive STARK or a
direct witness, and bounds what AG-7 lists by a budget.

`bench/results/2026-10-13-leanvm-memory.md` (decision record 0041) measured
the peak of proving one aggregate. It rises in steps as leanVM's tables pad
to powers of two: 6 and 7 recursive inputs peak alike, and so do 9 and 10.
The joint fit, $a + b r + c s$ for $r$ recursive inputs and $s$ signatures
verified directly, lies below the peak at 9 inputs by the most, and above it
at 7.

## Decision

1. **AG-10 counts memory over AG-9's inputs, at constants of its own.**
   `memory_base`, `memory_recursive`, `memory_sig` and `memory_stark`, in
   MiB, over the recursive STARKs an aggregate takes and the triples it
   verifies directly. A line is what a clause can add up as AG-7 lists one
   transaction after another; the steps are the padding of one VM's traces,
   which moves with any change to the VM, so the clause takes the form and
   an experiment the constants.
2. **The budget bounds each aggregate's peak.** A node proves one aggregate
   at a time, as the simulator has it (decision record 0034), so what must
   fit is the peak of that one, not a sum. `memory_budget` is what a node
   can give proving: its memory less what it keeps for everything else.
   How much that is is an experiment's assumption to state.
3. **Memory leaves the cover to AG-9.** Each triple is covered as AG-9's
   order says, and the one count of inputs feeds both bounds; a cover chosen
   for each bound would be two different aggregates. A transaction passed
   over for memory in AG-7's step 2 can still be listed later by its direct
   proof, as AG-9 already allows for time.
4. **A transaction is added only if every bound that is set holds.** Time
   and memory are both properties of the one aggregate.
5. **`memory_stark` is `memory_recursive`**, as decision record 0034 took
   `prove_stark` as `prove_recursive`: a leanSTARK triple verified directly
   is a STARK the circuit verifies, as a recursive input is. leanVM has no
   leanSTARK of a user's own to measure.
6. **An experiment budgets against the envelope.** A node that runs out of
   memory loses the aggregate, and perhaps more, so it budgets against what
   an aggregate may take rather than what it takes on average.
   `bench/leanvm-memory/fit.py`'s `envelope()` keeps the joint fit's slopes
   and raises its base until no peak measured lies above the line, to
   1904.4 MiB. It overstates small aggregates, 3.03 GiB for one recursive
   input against a measured 1.29 GiB, which is adverse to the claim item
   32 tests: a node the envelope lets prove could prove at the measured peak.

## Consequences

- `docs/spec/05-aggregation.md` version 3 adds AG-10 and five parameters to
  AG-1, with the budget unset and the costs at 0 under `eip-8288`;
  `conformance/vectors/aggregation/ag-10-memory.json` has its cases, and
  `emem.aggregation.Aggregator` counts and bounds memory.
- An experiment can now give each node a memory and a share its client
  keeps, and let only nodes that can prove propose, as experiment 24's
  section 2 did.
- Not modelled: memory a node holds between aggregates (its proofs, its
  pool), which `memory_budget` leaves to what the node keeps; memory that
  depends on anything but the circuit's inputs.
