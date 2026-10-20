# 05. In-mempool aggregation (EIP-8288)

Version 3, 2026-10-13. Version 1, 2026-10-08, had no proving time; version 2
added AG-9 and its five parameters. Version 3 adds AG-10 and its five
parameters, and changes nothing else.

The mempool section of EIP-8288, *In-mempool signature and proof
aggregation*, written down as clauses on top of the frame pool. The EIP is
Draft; it was read from ethereum/EIPs at commit `258836f9` (2026-10-07),
sections "Constants", "New Frame Mode", "Transaction Dependencies", "Mempool
Wrapper Object", "Recursive Mempool Aggregation", "Mempool-Level Limits" and
"Gas Accounting". Quotations below are from those sections unless another is
named. A clause marked *Interpretation* is this repository's reading where the
EIP leaves a choice open, and names decision record 0012, or 0034 for AG-9
and 0042 for AG-10.

EIP-8288 lets a frame transaction declare **dependencies**, triples
`(scheme, data_hash, verification_key_hash)` naming a leanSPHINCS signature or
a leanSTARK proof, in a frame that is never executed. The proofs travel beside
the transaction in a **wrapper**, mempool nodes merge what they hold into one
recursive STARK every `AGGREGATION_INTERVAL`, and a block carries one
recursive STARK for all its dependencies. What it is for, and why a privacy
protocol's spend needs it, is not restated here.

The model does not prove anything. A proof is a flag that says whether it
verifies, and a recursive STARK is the list of dependencies whose hash is its
public input, with the same flag. A node that holds proofs for a set of
dependencies can produce a recursive STARK for any subset of it, because the
EIP's circuit takes recursive proofs and direct witnesses as inputs and
removes `discards` (Block Validity, Recursive STARK Proof Structure).

## What changes

A pool under the `eip-8288` profile is the frame pool of `02-frame-pool.md`,
version 4, under the `eip-8141` profile, with these changes and no others:

- FP-3 admits frames of mode 3, which AG-2 checks;
- FP-4 to FP-6 do not see dependency frames (AG-3);
- AG-4 is added to admission after FP-3, and AG-6 after FP-6;
- AG-5 and AG-7 add wrappers, which the frame pool alone does not have, and
  AG-9 and AG-10 bound what AG-7 lists by the time and the memory it takes
  to prove;
- BB-3 counts AG-8's gas.

## Profile

**AG-1. Parameters.**

| Parameter | `eip-8288` | Note |
| --- | --- | --- |
| `dependency_frames` | true | FP-3 admits `DEP_VERIFY_FRAME_MODE`, 3; false under every profile of FP-1 |
| `max_dependencies_per_frame` | 256 | `MAX_DEPENDENCIES_PER_FRAME` |
| `max_sigs_per_tx` | 16 | `MAX_SIGS_PER_TX` |
| `max_starks_per_tx` | 1 | `MAX_STARKS_PER_TX` |
| `max_sig_deps_per_wrapper` | 16 | `MAX_LEANSIG_DEPS_PER_WRAPPER` |
| `max_stark_deps_per_wrapper` | 1 | `MAX_LEANSTARK_DEPS_PER_WRAPPER` |
| `aggregation_interval` | 1000 ms | `AGGREGATION_INTERVAL`, read by the network (AG-7), not by the pool |
| `cap_aggregates` | true | whether the two wrapper limits above bind the mode 1 wrappers nodes make (AG-5, AG-7); *Interpretation*, decision record 0012 |
| `forward_wrappers` | false | whether a node also relays the mode 0 wrappers it accepts, at once (AG-7); not in the EIP, and true only in variants the experiments measure, decision record 0012 |
| `proving_budget` | none | the most proving time, in ms, a node spends on one aggregate (AG-9); none means AG-9 bounds nothing; *Interpretation*, decision record 0034 |
| `prove_base` | 0 | ms an aggregate takes to prove before any input (AG-9) |
| `prove_recursive` | 0 | ms for each recursive STARK an aggregate takes as an input (AG-9) |
| `prove_sig` | 0 | ms for each leanSPHINCS triple an aggregate verifies directly (AG-9) |
| `prove_stark` | 0 | ms for each leanSTARK triple an aggregate verifies directly (AG-9) |
| `memory_budget` | none | the most memory, in MiB, a node spends on proving one aggregate (AG-10); none means AG-10 bounds nothing; *Interpretation*, decision record 0042 |
| `memory_base` | 0 | MiB an aggregate takes to prove before any input (AG-10) |
| `memory_recursive` | 0 | MiB for each recursive STARK an aggregate takes as an input (AG-10) |
| `memory_sig` | 0 | MiB for each leanSPHINCS triple an aggregate verifies directly (AG-10) |
| `memory_stark` | 0 | MiB for each leanSTARK triple an aggregate verifies directly (AG-10) |

Every FP-1 parameter is `eip-8141`'s. The schemes are `LEANSPHINCS_SCHEME`,
`0x10`, at `LEANSPHINCS_VERIFICATION_GAS` 3000, and `LEANSTARK_SCHEME`,
`0x11`, at `LEANSTARK_VERIFICATION_GAS` 30000.
The EIP gives no proving time, no memory and no hardware, so the profile
leaves both budgets unset and the eight costs at 0; an experiment that sets
them says where it took them.

## Errors

| Code | Raised by |
| --- | --- |
| `ErrDepFrameMalformed` | AG-2 |
| `ErrFrameTooManyDeps` | AG-4 |
| `ErrWrapperMalformed`, `ErrWrapperUnknownTx`, `ErrWrapperDeps`, `ErrWrapperTooManyDeps`, `ErrWrapperProof` | AG-5 |
| `ErrFrameDepsUnproven` | AG-6 |

The EIP names no errors; these codes are this repository's.

## Transactions

**AG-2. Dependency frames.** A frame of mode 3 is a *dependency frame*. Its
`data` is $k$ triples of 96 bytes, which the model carries as `deps`, a list of
`(scheme, data_hash, vk_hash)` beside the frame's `data_size` (MD-6). This
clause takes the place of FP-3's constraints on a single frame for a
dependency frame, and FP-3's constraints on the transaction still apply. The
pool MUST reject with `ErrDepFrameMalformed` a transaction with a dependency frame
that breaks any of: $1 \le k \le$ `max_dependencies_per_frame`; every `scheme`
is `0x10` or `0x11`; `data_size` is $96 k$; no `target`; `value` 0; `flags` 0;
`exec_gas` equal to the sum over its triples of 3000 for a leanSPHINCS triple
and 30000 for a leanSTARK one; `state_gas` 0. A frame of mode 3 under a profile
without `dependency_frames` is `ErrFrameMalformed` (FP-3).
**Source:** New Frame Mode, "Validity constraints". A scheme byte other than
the two, or a non-zero byte among the 31 before it, is one case in the model:
a `scheme` value that is neither. *Interpretation:* the EIP constrains "the
frame's `gas_limit`", and an EIP-8141 frame has no such field but `limits`, an
execution and a state limit; the clause reads it as the execution limit and
requires the state limit to be 0, decision record 0012.

**AG-3. Dependency frames and the prefix.** FP-4's validation prefix, FP-5's
structure and FP-6's budgets MUST be computed over the transaction's frames
with its dependency frames removed. A dependency frame's `exec_gas` still
counts in FEE-4's `max_gas`, as the EIP's gas formula charges it, but not in
FP-6's `max_verify_gas`. *Interpretation:* the EIP never says where a
dependency frame may sit relative to the validation prefix, and its Test Case 1
puts one before the `VERIFY` frame that reads it, a shape FP-5 would reject;
the frame is never executed, so its gas is no verification work, decision
record 0012.

**AG-4. Limits per transaction.** A transaction's *dependencies* are the
sorted, deduplicated list of the triples of all its dependency frames. The pool
MUST reject with `ErrFrameTooManyDeps` a transaction whose dependencies hold
more than `max_sigs_per_tx` leanSPHINCS triples or more than
`max_starks_per_tx` leanSTARK triples. Declarations of one triple more than
once count once here, and are charged for each in gas (AG-2).
**Source:** Transaction Dependencies, `dependencies(tx)`; Mempool-Level
Limits: "a transaction can have `<= MAX_SIGS_PER_TX` leanSPHINCS dependencies
and `<= MAX_STARKS_PER_TX` leanSTARK dependencies", and "These limits in all
cases apply to the length of the sorted, deduplicated dependency list". The
limits are a mempool rule, not a validity rule: a block may include a
transaction that breaks them.

## Wrappers

**AG-5. Checking a wrapper.** A wrapper carries `transactions`, each a frame
transaction or the hash of one, `mode`, `deps`, and for mode 0 one proof per
entry of `deps` or for mode 1 one recursive STARK. A node *holds* a
transaction that is pending in its frame pool. It checks a wrapper in this
order, and on the first failure refuses the whole wrapper with the code given:

1. `mode` is 0 or 1, and in mode 0 there are as many proofs as `deps`, else
   `ErrWrapperMalformed`;
2. in mode 0, every hash names a transaction the node holds, else
   `ErrWrapperUnknownTx`;
3. in mode 0, `deps` is the sorted, deduplicated union of the dependencies of
   all `transactions`, and in mode 1, the recursive STARK's public input is
   the hash of `deps`, else `ErrWrapperDeps`;
4. in mode 0, and in mode 1 when `cap_aggregates` is true, `deps` holds at
   most `max_sig_deps_per_wrapper` leanSPHINCS triples and at most
   `max_stark_deps_per_wrapper` leanSTARK triples, else
   `ErrWrapperTooManyDeps`;
5. in mode 0, every proof verifies, and in mode 1, the recursive STARK does,
   else `ErrWrapperProof`.

A mode 1 wrapper's transactions are not checked against its `deps`, and a
hash in it that names no transaction the node holds is answered
`ErrWrapperUnknownTx` on its own, without refusing the rest. Triples are
ordered by `scheme`, then `data_hash`, then `vk_hash`. **Source:** Mempool
Wrapper Object, the wrapper encoding and the two lists of checks. The order is
mode 0's, which checks the limits before the proofs; mode 1's list checks its
STARK first, and the order decides only which code a wrapper that fails twice
is refused with. *Interpretation:* the EIP lists the limits among the checks
of mode 1 and also says a node broadcasts "exactly one wrapper containing all
currently active transactions"; under the limit that wrapper holds at most
one leanSTARK dependency, so the two cannot both hold once a node has two
transactions with one each. `cap_aggregates` takes the first sentence when
true and the second when false, decision record 0012. The EIP lists no check
for a hash a node cannot resolve; mode 1 does not need the transactions to
check its proof, and mode 0 does, decision record 0012.

**AG-6. Admission needs proofs.** When a wrapper passes AG-5, the node records
as *proven* every triple in its `deps`, and then offers its transactions to
the frame pool in order; the answer for each is the pool's, `ErrAlreadyKnown`
(FP-2) for one it holds. The pool MUST reject with `ErrFrameDepsUnproven`,
after FP-6 and before FP-7, a transaction with a dependency the node has not
proven, whether it arrives in a wrapper or alone. **Source:** Recursive
Mempool Aggregation, "When they see a wrapper, they validate its proof (either
direct proofs or a recursive STARK). If valid, they accept it"; Rationale, "if
it sees a dependency appear [...] and it has no valid proof for it, then it
must be able to reject that transaction". *Interpretation:* the triples are
proven once the wrapper's proofs verify, whatever the pool then answers its
transactions, and they stay proven after the transactions leave the pool, so
a transaction resent alone is admitted; the EIP does not say how long a node
keeps proofs, decision record 0012.

**AG-7. The aggregate.** Every `aggregation_interval` a node MUST build one
mode 1 wrapper, its *aggregate*, over the transactions with dependencies that
it holds, with `deps` the sorted, deduplicated union of theirs, and send it to
each of its peers with every transaction it sent in an earlier aggregate
replaced by its hash; a node that lists none sends nothing. A transaction that
leaves the pool, for any reason, is not in the next aggregate, and neither are
its dependencies unless a transaction still there has them. The node lists
the transactions in this order, and when `cap_aggregates` is true it adds one
only if AG-5's limits still hold with it, going on past one that does not fit:

1. the transactions of its own previous aggregate that it still holds, in that
   aggregate's order;
2. the transactions of the aggregates it received since then, one aggregate at
   a time, the one with the most transactions not yet listed first, ties to
   the one received first;
3. the others, by effective tip at the pending base fee from highest, ties to
   the earliest admitted.

When `forward_wrappers` is true, a node also sends every mode 0 wrapper that
passes AG-5 to each of its peers at once. **Source:** Recursive Mempool
Aggregation: "Every `AGGREGATION_INTERVAL` milliseconds, they generate a new
mode 1 wrapper object containing all still-valid transactions [...] replacing
any transaction that they already sent previously with its hash"; "When a
transaction becomes unincludable [...] they keep note that its dependencies
need to be pruned"; and the order for a node that "will not have enough
proving time to aggregate in _all_ aggregates that it saw": "1. Its own
aggregate from the previous round 2. Removing anything that needs to be
removed 3. Other nodes' aggregates, in descending order of how many new
transactions they will add to the aggregate 4. Users' transactions, in
descending order of priority fee". *Interpretation:* the order is given for
proving time, and is read as the order that fills the limits as well; removal
is not a step, because only transactions the node holds are candidates;
"users' transactions" are all those not yet listed; and a priority fee is an
effective tip, decision record 0012. `forward_wrappers` is an earlier
reading, under which transactions are still gossiped individually; the
EIP's text sends only the aggregate.

## Building a block

**AG-8. Gas of the recursive STARK.** A block MUST count against its gas
limit, besides its transactions' gas, $30000 \cdot n$, where $n$ is the number
of dependency triples its transactions declare, duplicates included. A builder
applying BB-3 MUST treat a transaction with dependencies as needing that much
more gas left than its `gas_limit`, and adds it to the gas used when the
transaction is included. **Source:** Gas Accounting, "`recursive_stark_gas =
LEANSTARK_VERIFICATION_GAS * total_deps_in_block` where `total_deps_in_block`
is the total number of dependency triples across all transactions in the
block", "charged as part of the block's base fee". *Interpretation:* the EIP
does not say whether $n$ counts declarations or the deduplicated
`dependencies(block)`, nor who pays; the clause counts declarations, as the
sentence reads, and charges nobody, decision record 0012.

## Proving time

**AG-9. Proving time.** An aggregate's *proving time* is `prove_base`, plus
`prove_recursive` for each recursive STARK it takes as an input, plus
`prove_sig` for each leanSPHINCS triple and `prove_stark` for each leanSTARK
triple it verifies directly. A recursive STARK taken as an input covers every
triple of its `deps` and costs `prove_recursive` once, however many of them
the aggregate keeps. As AG-7 lists a transaction, each of its triples that
nothing already taken covers is covered by the first of these that applies:

1. the node's own previous aggregate, if it covers the triple;
2. in AG-7's step 2, the received aggregate the transaction is listed from;
3. the triple's proof, verified directly, if the node verified it in a mode 0
   wrapper;
4. the first aggregate the node received that covers the triple.

When `proving_budget` is set, AG-7's node adds a transaction only if the
aggregate's proving time with it is at most `proving_budget`, going on past
one that does not fit, as it does for AG-5's limits; an aggregate that lists
nothing has no proving time. When it is not set, proving time bounds nothing.
**Source:** Recursive Mempool Aggregation: "If a node anticipates that it
will not have enough proving time to aggregate in _all_ aggregates that it
saw, it should prioritize in the following order", the order AG-7 takes;
Block Validity, Recursive STARK Proof Structure: the circuit's private inputs
are "[deps, witnesses, recursive_proofs, recursive_deps_list, discards]", and
its logic is "verify inputs, merge and discard". *Interpretation:* the EIP
gives no proving time, no budget and no hardware. The clause counts proving
time as linear in the circuit's inputs, a recursive STARK or a direct
witness, with constants a profile leaves unset and an experiment takes from
a benchmark; it reads "enough proving time" as a budget for each aggregate;
it has the node keep every aggregate it receives, so that it can take one as
an input later; and it prefers a direct proof to an aggregate it was not
listed from, decision record 0034.

## Memory

**AG-10. Memory.** An aggregate's *memory* is `memory_base`, plus
`memory_recursive` for each recursive STARK it takes as an input, plus
`memory_sig` for each leanSPHINCS triple and `memory_stark` for each
leanSTARK triple it verifies directly, over the inputs and the triples AG-9
counts, which AG-9's order of cover chooses. When `memory_budget` is set,
AG-7's node adds a transaction only if the aggregate's memory with it is at
most `memory_budget`, going on past one that does not fit, as it does for
AG-5's limits and AG-9's budget; a transaction is added only if every bound
that is set holds with it. An aggregate that lists nothing has no memory.
When `memory_budget` is not set, memory bounds nothing.
**Source:** Block Validity, Recursive STARK Proof Structure: the circuit's
private inputs are "[deps, witnesses, recursive_proofs, recursive_deps_list,
discards]"; the EIP says nothing of memory. *Interpretation:* the clause
counts the memory proving one aggregate takes at its peak as linear in the
circuit's inputs, AG-9's form, with constants a profile leaves unset and an
experiment takes from a benchmark; it reads what a node can give proving,
its memory less what it keeps for everything else, as a budget for each
aggregate, since what must fit is the peak of the one aggregate being
proven, not a sum over aggregates; and it leaves the cover to AG-9, so that
memory never changes which input covers a triple, decision record 0042.

## Not modelled

- Block validity rules 1 and 2, the header field and the recursive STARK's
  public input: a block in the model is valid if its transactions are.
- The size of a recursive STARK, and the sizes of leanSPHINCS signatures and
  leanSTARK proofs; the simulator counts bytes of transactions and numbers
  of proofs, not bytes of proofs. Proving time is AG-9's count and memory
  AG-10's, and nothing else in a node waits for the one or holds the other.
- The FOCIL extension, its `recursive_stark` field and what attesters check.
- A node's choice to rebroadcast a mode 0 wrapper of concatenated leanSPHINCS
  signatures in place of an aggregate.
- `FRAMEPARAM` and `FRAMEDATACOPY` over a dependency frame: a frame's
  observations (MD-6) already say what its code concludes.
- Proofs that expire, and proofs a node holds for a transaction it never
  admitted.
