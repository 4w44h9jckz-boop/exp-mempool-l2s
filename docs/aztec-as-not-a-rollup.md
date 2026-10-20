# Aztec as not a rollup

*A reading, not a specification. Nothing here is normative: it takes Aztec's
node apart job by job and says which clause of `spec/` would hold each job if
Aztec ran on L1's mempool rather than as a rollup, what an experiment here has
already measured about it, and what is left over. Decision record 0047 records
the choices. Read 2026-10-13.*

## The question

An earlier design study claims that private applications already work the
way a mempool rollup would. Its evidence for Aztec is the 2024
block-production RFC: a node verifies a transaction's proof and passes it
on, and executes nothing at that step. The same study lists its own blind
spot: it read only the 2024 RFC, not Aztec's current block production.

This document reads the current code, and asks the question that turns the
claim into something this repository can test: **if Aztec had no blocks of its
own, which of its node's jobs would L1's mempool and L1's block take over,
under which clause, and what would Aztec have to give up?**

## What was read

Two repositories, at commits that agree with each other:

- **aztec-packages**, AztecProtocol/aztec-packages at `5a63848e`
  (2026-10-13): the L1 contracts (`aztec-packages/l1-contracts/src/core/`:
  `ValidatorSelectionLib.sol`, `ProposeLib.sol`, `EscapeHatch.sol`, the
  message bridge), the protocol constants
  (`aztec-packages/noir-projects/fnd/noir-protocol-circuits/crates/types/src/constants.nr`),
  and the transaction base rollup's expiry check (`private_tail_validator.nr`
  in `rollup-lib`).
- **aztec-node**, aztec-labs-eng/aztec-node at `54e3383c` (2026-09-23), the
  commit aztec-packages pins as its `labs` submodule. The node, the client
  and the documentation moved there. Read: the transaction validators and
  their README (`aztec-node/yarn-project/p2p/src/msg_validators/tx_validator/`),
  the transaction pool and its README
  (`aztec-node/yarn-project/p2p/src/mem_pools/tx_pool_v2/`), the `Tx` class,
  the fee payer code, the default note nullifier in Aztec.nr
  (`aztec-node/noir-projects/aztec-nr/aztec/src/macros/notes.nr`), and the
  developer documentation on transactions, state, fees and circuits.

Not read: the AVM, the prover network, the 2024 RFC itself (the earlier
study read it), and any deployed network's parameters. Slot length, epoch
length, committee size and the escape hatch's schedule are constructor
arguments in the L1
contracts, so the code fixes none of them.

## Aztec in one paragraph

A user's device runs the private functions of a transaction and proves them:
a chain of private kernel circuits, about 427,000 gates for a single call
behind an account entrypoint in the documentation's example
(`private_kernel.md`). What leaves the device is a `Tx`: the kernel's public
outputs (note hashes, nullifiers, encrypted logs, queued public calls, gas
settings, a fee payer, an anchor block and an expiry timestamp), the proof,
and the calldata of the public calls. A node checks it and keeps it in a pool.
Each epoch a committee is sampled from staked validators with L1's
`prevrandao`, and each slot one member proposes. The proposer runs the public
calls in the AVM, inserts the note hashes and nullifiers into the state trees,
and posts a checkpoint to L1 with attestations from more than two thirds of
the committee (`ValidatorSelectionLib.sol`). Provers then prove the epoch
with a tree of rollup circuits, and L1 verifies one proof. Fees are paid in
Fee Juice, bridged one way from L1.

## The node already behaves like a mempool

The validators' README lists what a node runs on a gossiped transaction, and
in what order:

| Step | What runs | Cost the README benchmarks |
| --- | --- | --- |
| Stage 1, fast | permitted, data, metadata, timestamp, double spend, gas limits, gas and fee payer, phases, block header | microseconds to a millisecond each, the data check 4 to 18 ms |
| Pool pre-check | duplicates and capacity | |
| Stage 2, slow | the client proof | about 250 ms |
| Pool add | the pool's rules | |

The README gives no hardware for these figures. Then: "Transactions already
in the pool, about to be sequenced into a block" are checked again by the
builder, which "Does **not** run: Proof, Data -- already verified on entry".
For a transaction with no public calls, nothing of it is executed after
admission: the block only inserts its note hashes and nullifiers.
The 2024 RFC's reading, that a node verifies and passes on, holds in the
current code.

The order matters to this repository. Cheap checks run before the proof, a
pool pre-check sits between them so that a node does not verify a proof it
would then refuse, and a peer that sends a bad proof is penalised. That is
the order of rules R1 and R3 of claim-gated admission, which this
repository specified (CG-3 and CG-4 in `spec/10-claim-gated-admission.md`).

## Job by job

Every row says what Aztec does today, as read in the files above, the clause
here that would hold the job on L1, and the experiment here that measured
something about it.

| Job | Aztec today | On L1, without a rollup | Clause here | Measured here |
| --- | --- | --- | --- | --- |
| execute private functions and prove them | the user's device | unchanged | | |
| check before the proof | stage 1 validators | the frame pool's static checks and validation prefix, run before any proof | FP-3 to FP-10, CG-3 | |
| check the proof | stage 2, about 250 ms | every mempool node, on admission | AG-5, AG-6 | 24 |
| penalise a bad proof | peer scoring by severity | what a node remembers after a proof fails | CG-4 | |
| replay protection | the nullifiers; a transaction that emits none gets its request hash as one | a keyed nonce or an expiring nonce on a shared sender | FP-7, FP-12, EN-2 to EN-4 | 01, 21 |
| identity in the pool | the nullifier set; no sender | the sender and its nonce keys | FP-12 | 01, 02 |
| replace a pending transaction | any shared nullifier, higher priority wins; a 10 percent bump over RPC only | the same identity, a 10 percent bump | FP-12 | 11, 15 |
| anchor | any block in the archive; the expiry at most a day after it | a recent root, 8,191 slots back | RR-3 to RR-7 | 14 |
| expiry | the expiry timestamp against the next block's; evicted after a block | an expiry frame | FP-8 | 05 |
| pay | a fee payer with Fee Juice, often a fee-paying contract, in a non-revertible setup phase restricted to an allow list | the payer frame and its approval, in a validation prefix restricted by trace rules | FP-9 to FP-11 | 03, 10 |
| a payer's pending total | the sum of pending fee limits against the payer's balance | payer accounting | FP-11 | 03 |
| capacity | evict the lowest priority | capacity and eviction order | FP-14 | 04 |
| order and build | a proposer from an epoch committee, two thirds attest | L1's proposer and builder | BB-1 to BB-4 | 00 |
| resist censorship | an escape hatch: a bonded candidate proposes for `ACTIVE_DURATION` epochs out of every `FREQUENCY` | inclusion lists every slot | IL-1 to IL-8 | 09 |
| run public calls | the AVM, in setup, app and teardown phases | the EVM, in the transaction's later frames | BB-5 | |
| prove the block | tx base, merge, block, checkpoint and epoch rollup circuits | mempool nodes aggregate every 1,000 ms; validators verify one proof | AG-7, AG-8 | 06, 24 |
| append note hashes | the rollup circuits insert into the note hash tree | an open-role updater proves a tree update from chained outputs | | |
| record nullifiers | the rollup circuits insert into an indexed tree | a storage entry each, under EIP-8037 state pricing | BB-6 | |
| publish data | blobs, by the proposer | the transaction itself | | |
| hide order flow | not hidden: the queued public calls are visible | sealed transactions | LU-1 to LU-13 | 07, 18, 23 |
| move assets between layers | an inbox, an outbox and a Fee Juice portal | nothing: there is one layer | | |

Four rows need more than a line.

### Replay protection and identity: where the fit is closest

Aztec's pool has no notion of a sender beyond the fee payer it charges. A
transaction is known by its nullifiers, and two pending transactions
conflict only if they share one (`NullifierConflictRule`): the incoming one evicts every transaction it
conflicts with if its priority is strictly higher than each, and is ignored
otherwise. Priority is the smaller of its maximum fee and its maximum
priority fee per unit of L2 gas, with the transaction hash breaking ties.
Over RPC the incoming fee must be at least 10 percent higher; over gossip
there is no bump.

On L1 a frame transaction needs a sender, and a private application that
does not want its users linked uses one shared sender for all of them. Under
FP-12's `one`, the default, that sender holds one pending transaction at a
time, which is the ceiling experiment 01 measured and MATCHA (experiment 02)
and expiring nonces (experiment 21) were built to lift. Aztec's rule is the
same idea as FP-12's `disjoint-keys` variant, with nullifiers as the nonce
keys: transactions that touch disjoint keys wait side by side. Two
differences remain. FP-12 replaces only a transaction with the same identity
and refuses one that overlaps without matching, `ErrFrameSenderBusy`;
Aztec's rule replaces on any overlap and can evict several transactions at
once. And FP-12 asks the same bump of every replacement, where Aztec asks it
only of one that arrives over RPC.

### Whose nullifier is it

The earlier study gives the test a step must pass to belong in the
mempool: any single node can check it from data it holds, and nodes that
disagree can only stall a transaction, never split the chain. For
nullifiers it concludes that the check that a nullifier is unspent fits
only if the sender owns it.

In Aztec the default note's nullifier is a hash of the note hash and the
owner's nullifier hiding key for the application
(`compute_note_nullifier(note_hash_for_nullification, [secret])`, with the
secret from `request_nhk_app`). Only the owner can compute it, so only the
owner can make it spent, and two pending transactions that conflict on it are
both the owner's: a disagreement between nodes stalls the owner's own
transaction and nobody else's. Those nullifiers pass the test. Two kinds
do not: a `#[custom_note]` may compute its nullifier any way it likes, and
some nullifiers mark a public fact once (a contract's initialisation, a
consumed message). Anyone able to emit one of those can race for it, and the
pool can only drop the loser after a block decides. Aztec does exactly that
(`InvalidTxsAfterMiningRule` evicts a pending transaction whose nullifier a
block included). Experiment 11 measured what the losers cost a network.

### The anchor fits the recent-root window

A transaction proves its notes exist against an anchor block, and the node
checks only that the anchor is somewhere in the archive
(`BlockHeaderTxValidator`). The archive tree has height 30. What bounds the
anchor's age is the expiry: the base rollup's comment says the expiry "must
be at most `MAX_TX_LIFETIME` from the anchor block's timestamp", and
`MAX_TX_LIFETIME` is 86,400 seconds, one day. So at inclusion the anchor is
at most a day old.

On L1 the application's contract would write its note hash tree's root into
EIP-8272's recent roots every block (RR-3), and a spend would reference one
(RR-4, RR-5). The usable window is 8,191 slots (RR-1), which at 12-second
slots is $8191 \times 12 = 98{,}292$ seconds, more than Aztec's own day. Aztec's
lifetime fits EIP-8272's window with $98{,}292 - 86{,}400 = 11{,}892$ seconds
to spare, so the window costs Aztec's users nothing they have today. What
experiment 14 measured, spends that outlive their root while they wait, is
what the window adds.

The expiry does not fit EIP-8266 in the other direction. EIP-8266 caps a
deadline at 60 seconds ahead (EN-1, `max_expiry_secs`), and an Aztec expiry
is fixed in the proof's public outputs when the proof is made. A transaction
whose proving takes longer than its deadline allows cannot use an expiring
nonce for replay protection, and needs a keyed nonce instead.

### Proving the block: the schemes do not match

Aztec's rollup circuits verify each transaction's client proof and fold them
into one epoch proof. EIP-8288 has mempool nodes do the same every 1,000 ms
(AG-1, AG-7), but a dependency names one of two schemes, leanSPHINCS
(`0x10`) and leanSTARK (`0x11`), and Aztec's client proof is neither. Its
transaction carries a `chonkProof` from barretenberg. So either the user
wraps it in a leanSTARK, at a proving cost nobody here has measured
(what was measured on this machine is leanVM's aggregation, experiment 24,
and its tree updates and memory, not a wrapped proof), or EIP-8288 gains a
scheme.
This is the largest change Aztec would have to make, and it is a change to
proving, not to the pool.

## What fits and what does not

By the earlier study's test, job by job:

- **Fits.** Checking the proof, before and after the cheap checks; owned
  note nullifiers; the anchor, inside EIP-8272's window; the expiry, as an
  expiry frame; the payer, as EIP-8141's payer frame; capacity and
  replacement, with the differences above; ordering, building and
  censorship resistance, which L1 already does every slot rather than in
  Aztec's escape-hatch windows.
- **Fits with work.** The proof scheme, wrapped or added; note hashes,
  appended by an open-role updater rather than by a sequencer; nullifiers,
  as storage entries at 97,920 state gas each, a new slot's price under
  EIP-8037's current constants (`spec/00-model.md`), up to
  `MAX_NULLIFIERS_PER_TX`, 64, a transaction.
  At that cap a transaction's nullifiers cost $64 \times 97{,}920 = 6{,}266{,}880$
  state gas (derived from the two).
- **Does not fit.** Public calls on shared public state need an order, so
  they run in the EVM at L1's gas, as any public contract does. This is the
  row the earlier study calls the honest limit: a rollup scales execution, and
  the mempool rollup scales verification. Shared nullifiers stay a race
  that a block settles.
- **Goes away.** The committee, its stake, slashing and attestations; the
  escape hatch; the inbox, outbox and Fee Juice portal; Fee Juice itself,
  since fees are paid in ether, by a payer that a private user would reach
  through a paymaster or a blind ticket.

## What this repository would add

Two items, proposed in the plan as items 35 and 36:

- **Aztec's pool as a profile.** Read the transaction pool and the
  validators at `54e3383c` into a specification document of their own,
  clause by clause: identity by nullifier set, the conflict rule with
  priority and the RPC bump, a payer's pending total, the order of cheap
  checks, pre-check and proof, eviction after a block and after a reorg, and
  capacity. Then vectors, then the reference, in that order.
- **Aztec's pool on L1.** With that profile beside FP-12's `one` and
  `disjoint-keys`, a shared sender's private spends at L1's 12-second slots
  with a 250 ms proof check: how many land, how long they wait, and what an
  adversary able to emit shared nullifiers can evict, against one that holds
  only owned ones.
