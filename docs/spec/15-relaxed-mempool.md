# 15. A relaxed alternative mempool: write-once reads, many pending, and node tiers

Version 1, 2026-11-04.

**Status: proposal.** This document states, as modules of
`13-descriptors.md`, an alternative frame mempool that admits some of what
EIP-8141's canonical rules refuse, without letting one state change
invalidate an unbounded number of pending transactions. It is a proposal of
this repository: no client implements it and no EIP specifies it. Its
descriptor is `docs/spec/descriptors/relaxed.json`, which inherits the
canonical `eip-8141.json`. A clause marked *Interpretation* is this
repository's reading where its sources leave a choice open, and names the
decision record: 0081 for the gate, the declarations and the tiers, 0082 for
the bounds on the second and third relaxations.

The goal it keeps is EIP-8141's own: the public mempool rules exist "to
avoid allowing an arbitrary number of transactions to be invalidated by a
single environmental change or state modification" (EIP-8141 at `258836f9`,
Mempool). Three canonical rules keep that bound for frame transactions, and
each binds a contract that sends or pays for transactions of its own:

- FP-9 refuses a validation prefix that reads storage of any account but
  its sender;
- FP-11 lets a payer that is not the canonical paymaster pay for one
  pending transaction (`max_pending_noncanonical`, 1);
- FP-12 under `per_sender` `one` lets a sender have one pending
  transaction.

So under the canonical rules a shared pool that sends its own withdrawals has
one pending at a time, and so does a ticket paymaster. This document relaxes
each of the three where a bound on invalidation can be kept, and states the
bound (RM-9). It also defines three node tiers, so that a node that checks
no proof can still carry transactions (RM-8).

## What changes

A pool under `relaxed.json` is the frame pool of `02-frame-pool.md` under
`eip-8141.json`, with the aggregation of `05-aggregation.md` and the
claim-gated admission of `10-claim-gated-admission.md`, and with these
modules:

- RM-2 judges every transaction first under the canonical modules alone,
  and runs everything else in the descriptor only for a transaction they
  refuse, as ERC-7562's alternative mempools do;
- RM-3 lets a prefix read storage at slots a contract's code declares
  write-once, one pending reader for a slot not yet written;
- RM-4 lets a declared contract have several pending transactions on
  disjoint non-zero nonce keys;
- RM-5 lifts FP-11's count for a payer whose code declares the most one
  transaction can take from its balance;
- RM-6 keeps a reputation for each declared code, read from each block's
  access list;
- RM-7 exports groups of pending transactions for builders;
- RM-8 defines relay, verifier and aggregator nodes.

## Profile

**RM-1. Parameters.**

| Parameter | `relaxed` | Note |
| --- | --- | --- |
| `relaxed` | true | whether RM-2 to RM-8 apply; false under every other profile |
| `declarations` | none | RM-3's declarations, a list; the descriptor names none, and a child descriptor that replaces `RM-3` names a contract's (DS-5) |
| `sender_bound` | true | whether RM-4 asks for a declared sender and declared sender reads; false is the relaxation alone, kept to be measured (RM-9) |
| `outflow_bound` | true | whether RM-4 and RM-5 ask the payer for an outflow bound and the transaction to reserve it; false is the relaxation alone, kept to be measured (RM-9) |
| `ban_violations` | 3 | RM-6: violations at which a declared code is banned |
| `throttled_count` | 4 | RM-6: relaxed pending transactions a throttled code may be relied on by; CG-11's `throttled_entity_mempool_count` |
| `declaration_refresh_seconds` | 3600 | RM-6: how often violations decay; CG-11's `refresh_seconds` |
| `tier` | `verifier` | RM-8: `relay`, `verifier` or `aggregator`; a value of each node, not of the descriptor |

Every parameter of FP-1, AG-1 and CG-1 is `claim-gated`'s. In particular
`per_sender` stays `one` and `max_pending_noncanonical` stays 1, as
`13-descriptors.md` DS-6 requires beside the `RM` modules: RM-4 and RM-5
relax them, and RM-2's first judgement is the canonical one.

**A declaration** is an object with exactly these members:

| Member | Holds |
| --- | --- |
| `code` | the code a declaration is for: in the model a code value (MD-2), on a chain the keccak256 of an account's runtime code, as `0x` and 64 hexadecimal digits |
| `write_once` | an array of ranges, each an array of two members: the first slot, as `0x` and 1 to 64 hexadecimal digits, and a count of slots from 1 to $2^{32}$, an integer; possibly empty |
| `max_outflow` | the most one transaction may take from the balance of an account with this code, an amount (DS-1), or `null` for no bound declared |

A slot $s$ is **declared write-once** by a code $c$ when a declaration for $c$
has a range $[f, n]$ with $f \le s < f + n$. Two declarations for one code
are refused with `ErrDescriptorParams` (DS-4). An account whose code is
empty, or is an EIP-7702 delegation (MD-2), has no declaration whatever the
list says. **Source:** none; the declaration is this document's.
*Interpretation*, decision record 0081: a declaration is a claim made for a
code, not proved from it. Each block's access list checks it after the fact
(RM-6). The descriptor's identifier commits to the list, so nodes that load
one descriptor agree on it.

## Errors

| Code | Raised by |
| --- | --- |
| `ErrWriteOnceBusy` | RM-3 |
| `ErrRelaxedReserve` | RM-5 |
| `ErrDeclarationThrottled`, `ErrDeclarationBanned` | RM-6 |
| `ErrRelayUnchecked` | RM-8 |

A transaction that no relaxation admits keeps the canonical module's code:
`ErrFrameStorageReadNonSender` (FP-9), `ErrFramePaymasterBusy` (FP-11) or
`ErrFrameSenderBusy` (FP-12).

## The gate

**RM-2. The canonical rules first (ALT-020).** Under `relaxed`, the pool
judges a transaction first under the canonical modules alone: the frame
pool's modules with `eip-8141.json`'s parameters, and no `AG`, `CG` or `RM`
module. If they admit it, the pool admits it as they do, and no other module
of the descriptor reads it, then or later: it needs no claim and is not
counted by RM-6. If they refuse a transaction without a dependency with any
code but `ErrFrameStorageReadNonSender` (FP-9), `ErrFramePaymasterBusy`
(FP-11) or `ErrFrameSenderBusy` (FP-12), that refusal stands, since no
relaxation answers it. Otherwise the pool judges it again under the whole
descriptor, and that judgement is its answer, where:

- a transaction that has a dependency (AG-4) is judged as
  `10-claim-gated-admission.md` judges it, with RM-3 to RM-5 in the places
  below;
- a transaction that has none is judged with RM-3 to RM-6 in their places,
  and by CG-2 to CG-12 as a transaction without a dependency is there: a
  claim it carries is checked, and is not required. RM-6's checks come after
  RM-3 to RM-5 have admitted it.

A transaction the second judgement admits is **relaxed**. The pool records
which relaxations admitted it: `reads` (RM-3), `sender` (RM-4) or `payer`
(RM-5), any of them. **Source:** ERC-7562 (Review, ethereum/ERCs at
`493ba8a`), ALT-020: "The alt-mempool rules MUST be checked only when a
canonical rule is violated. That is, if validation follows the canonical
rules above, it is not considered part of an alt-mempool"; and ALT-021,
under which such a transaction "is checked against all the alt-mempools".
*Interpretation*, decision record 0081: the dependency frames and claims of
`05-aggregation.md` and `10-claim-gated-admission.md` are alternative rules
too, so the gate holds them, and a transaction the canonical rules admit is
treated exactly as under `eip-8141.json`.

## The relaxations

**RM-3. Write-once reads.** Under `relaxed`, a read in a prefix frame that
FP-9 refuses with `ErrFrameStorageReadNonSender` is allowed when the account
read holds code that declares the slot write-once (RM-1). Every other read
outside the sender stays refused. For each
allowed read the pool records the slot's value at its head as a dependency
(FP-10), so that FP-15 re-runs the prefix when the slot changes. A slot whose
value at the head is not 0 is **set**, and any number of pending transactions
may read it. A slot whose value is 0 is **unset**: the pool MUST refuse with
`ErrWriteOnceBusy` a relaxed transaction that reads an unset declared slot
some other pending transaction reads, not counting one it replaces. The pool
keeps, for each declared slot, the pending transactions that read it.
**Source:** none; the rule is this document's. *Interpretation*, decision
record 0081:

- a set slot can change only by a write that breaks its declaration (RM-6),
  so its readers lose nothing to any other write;
- an unset slot can be written once, which changes it for every reader, so
  holding one reader keeps that write to one invalidation;
- a transaction the canonical rules admit may read a declared slot of its
  own sender, and is never refused for it (RM-2), so an unset slot may have
  one canonical reader beside one relaxed one.

**RM-4. Many pending per sender.** Under `relaxed`, a transaction FP-12
refuses with `ErrFrameSenderBusy` is admitted, if it passes every other
module, when:

1. it and every pending transaction from its sender use only non-zero nonce
   keys, and share none, as FP-12 under `disjoint-keys` asks;
2. under `sender_bound`, its sender's code has a declaration, and every
   sender storage slot its prefix reads is declared
   write-once by it; those reads are then RM-3's, with its unset-slot rule;
3. under `outflow_bound`, its payer passes RM-5's reserve, whether the payer
   is the sender or not, unless the payer is the canonical paymaster.

Otherwise `ErrFrameSenderBusy` stands. **Source:** EIP-8250 at `258836f9`,
Rationale: "A future policy MAY admit multiple pending frame transactions for
the same sender on disjoint non-zero key sets", which item 1 is.
*Interpretation*, decision record 0082: with several transactions pending
from one sender, three single writes could invalidate all of them: one to the
sender's code, one to a sender storage slot they read, and one to the balance
that pays for them. Items 2 and 3 close each:

- a declaration is for a code, and an account with empty code or an EIP-7702
  delegation has none, so a relaxed sender is a contract, whose code no
  transaction can change;
- its relaxed transactions read only write-once slots of its own storage;
- the balance is RM-5's.

**RM-5. The payer's count lifted.** Under `relaxed`, a transaction FP-11
refuses with `ErrFramePaymasterBusy` is admitted, if it passes every other
module and FP-11's exposure check holds, when, under `outflow_bound`, its
payer passes the **reserve**: the payer's code has a declaration, its
`max_outflow` $X$ is not `null`, and the transaction's
`max_cost` $m$ (MD-5) is at least $X$. The pool MUST refuse with
`ErrRelaxedReserve` a transaction whose payer has such a declaration and whose
$m$ is below $X$. Otherwise `ErrFramePaymasterBusy` stands. Without
`outflow_bound`, the exposure check alone is asked. FP-11's exposure check is
unchanged:

$$
\mathit{balance}(P) - R(P) - w(P) \ge m
$$

**Source:** EIP-8141 at `258836f9`, "Non-canonical paymaster" ("each
non-canonical paymaster can only be used with no more than
`MAX_PENDING_TXS_USING_NON_CANONICAL_PAYMASTER` pending transactions"), the
count this lifts, and "Replacement and Eviction" ("Reservation accounting
applies to every payer"), the sum it keeps. *Interpretation*, decision record
0082:

- FP-11's sum bounds what a payer's pending transactions reserve, not how
  many one write can invalidate. A single transaction the pool does not hold
  can lower the payer's balance by any amount, and FP-15 step 4 then drops
  every transaction the balance no longer covers;
- with every relaxed transaction reserving at least $X$, a write that takes
  at most $X$ leaves a shortfall below $X$. FP-15 step 4 removes
  transactions in the order received, and once it has removed one relaxed
  transaction the rest fit. So one write removes at most one relaxed
  transaction, beside at most one the canonical rules admitted (RM-9);
- the canonical paymaster keeps EIP-8141's own bound, its delayed
  withdrawal $w(P)$, and is not asked for a reserve;
- a bound ticket paymaster refuses a `max_cost` above its denomination
  (CG-10's $T_b$), so its declaration's $X$ is that denomination, and a
  ticket-paid transaction reserves the whole of it.

## Reputation

**RM-6. Reputation per declared code.** For each code with a declaration
the pool keeps a count of **violations**, which starts at 0 and every
`declaration_refresh_seconds` of the pool's time, counted from 0, is multiplied by 23
and divided by 24, rounding down. A code is `BANNED` when its count is at
least `ban_violations`, `THROTTLED` when it is at least 1 and it is not
banned, and `ACTIVE` otherwise. The pool exposes each declared code's count
and state (MD-9).

At each `reset` (MD-8), for each block the reset brings, the pool reads the
block's access list. For each account whose code at the old head has a
declaration, each of these is one violation of that code:

1. a storage change at a slot the code declares write-once, whose value
   before that change is not 0: a write to a set slot, or a second write in
   one block to a slot that was unset;
2. a balance change whose post-balance is below the balance before it by
   more than the declaration's `max_outflow`, when that is not `null`.

The value before a change is the slot's or balance's value after the
previous change in the list, or at the old head if there is none
(EIP-7928, "Recording Semantics by Change Type"). A violation is counted when
the reset that carries its block is applied.

At admission, for a relaxed transaction, each declared code it relies on is
checked once: the code of an account it reads under RM-3, its sender's code
under RM-4, and its payer's code under RM-5's reserve. The pool MUST refuse:

1. with `ErrDeclarationBanned`, a transaction that relies on a `BANNED`
   code;
2. with `ErrDeclarationThrottled`, one that relies on a `THROTTLED` code
   already relied on by `throttled_count` relaxed pending transactions, not
   counting one it replaces.

A transaction the canonical rules admit relies on nothing (RM-2).
**Source:** EIP-7928 at `258836f9` (Last Call), the block access list:
`storage_changes` and `balance_changes`, each change at a block access index
with its post-value, a write being "any value change" and "zeroing a slot";
ERC-7562 at `493ba8a`, ALT-040 ("`opsIncluded` and `opsSeen` of entities
are kept per alt-mempool") and its Reputation Calculation, for the decay.
*Interpretation*, decision record 0081:

- the count is of violations rather than of seen and included operations,
  since a declaration fails by one write, not by a rate of inclusions;
- one violation throttles the code at the reset that shows it, so no code
  keeps its rate after a block breaks its declaration;
- a set slot that is written also changes the dependency of every
  transaction that read it, and FP-15 re-runs each. Those whose prefixes no
  longer hold are dropped once: the violation's first loss, which no
  reputation prevents (RM-9).

## Builders

**RM-7. Groups.** The pool exposes `groups()`: its pending transactions
partitioned into **groups**, where two transactions are in one group if a
chain of pending transactions joins them, each sharing a key with the next.
The keys of a transaction are:

- each of its nonce keys, with its sender;
- its payer, which its execution debits;
- each declared slot it reads, with the account, whether RM-3 admitted the
  read or its sender read its own slot.

Groups are listed in the order of their earliest transaction received, and
each group's transactions in the order received. **Source:** none.
*Interpretation*, decision record 0081: transactions in different groups
share no key the pool knows, so a builder may run the groups apart. That is a
lower bound on their conflicts, not a proof of independence: the pool sees
the keys of the validation prefix and the payer, not every key a
transaction's execution writes.

## Node tiers

**RM-8. Relay, verifier and aggregator.** Under `relaxed`, `tier` is a
setting of each node:

- **`verifier`**: the pool of RM-2 to RM-7. It runs every prefix, checks
  every proof (AG-5), and holds the state the write-once reads need;
- **`aggregator`**: a verifier that also builds aggregates (AG-7) for the
  schemes `05-aggregation.md` defines;
- **`relay`**: a node that runs no prefix and checks no proof. It holds:
  - each sender's nonce sequences;
  - each payer's balance;
  - the code of senders and payers, and the ticket paymasters' keys
    (CG-10);
  - the claims it has forwarded.

  It admits a transaction only if one of these holds; otherwise it refuses
  with `ErrRelayUnchecked`:
  1. every frame of its prefix is protocol-defined, a frame the EIP
     evaluates directly (FP-9): default code, the expiry verifier, or the
     canonical paymaster. The relay evaluates it as FP-8 does;
  2. it carries a claim that CG-2, CG-9 and, under `binding`, CG-12 accept.
     The relay runs FP-2 to FP-7, FP-11's exposure check, FP-12 with RM-4's
     first item, and those checks, and not the prefix.

  It forwards each transaction it admits without the proofs of its
  dependencies, which a verifier fetches. Under item 2 it forwards one
  transaction under each claim, and a replacement of it at FP-12's price
  bump.

**Source:** CG-7, whose relay verifies no proof. *Interpretation*, decision
record 0081:

- **CG-7's relay** still runs each prefix and holds the state for it; this
  relay holds less;
- **What a relay forwards that a verifier refuses** is a claimed
  transaction whose prefix fails, whose proof fails, or whose write-once
  read is busy or undeclared.
- **What that costs its sender** is the claim:
  - at a verifier a failed proof records the slot or the claim for the
    epoch (CG-4), and a claim is used once (CG-5);
  - each relay forwards one transaction under it.

  So a sender pays for each transaction relays carry that verifiers refuse
  with a ticket, an issuer's price for one slot in one epoch. A transaction
  that carries no claim and runs code in its prefix is carried by verifiers
  alone.

## The bound

**RM-9. What one write invalidates.** A **write** is one change to one
item of state: a storage slot, a balance, a code, or a nonce sequence. Under
`relaxed` with `sender_bound` and `outflow_bound`, one write removes at most
one relaxed pending transaction, unless it is a violation (RM-6):

- **a nonce sequence:** the pending transactions that use one key, at most
  one under FP-12 and RM-4;
- **an unset declared slot:** its one relaxed reader (RM-3);
- **a set declared slot:** this is a violation. Every pending transaction
  that read it is re-run once, and the code is throttled;
- **a code:** no relaxed transaction depends on a code a transaction can
  change (RM-4 item 2, RM-1);
- **a balance:** one relaxed transaction of the account it pays for
  (RM-5).

Each write also removes at most what the canonical rules let it, beside the
relaxed one. Without `sender_bound` or `outflow_bound`, one write to a
sender's or payer's balance, code or storage removes every relaxed
transaction that depends on it. **Source:** RM-3 to RM-6, and FP-15.
*Interpretation*, decision record 0082. Experiment 27
(`experiments/27-relaxed-tiers/README.md`) measures this bound, with each
tier's needs, under the canonical rules, under `relaxed.json`, and with
every node verifying.

## Not modelled

- **How a node learns a prefix's reads.** RM-3 and RM-4 item 2 read the
  slots the prefix reads, and the model gives them (MD-6). A client that
  answers with a verdict (`11-surface.md`, SF-4) gives none, and the Hegota
  testnet's client refuses any read outside the sender itself. So a node
  run against a chain cannot load `relaxed.json`; decision record 0081 names
  what it needs from the client.
- **How a proof travels apart from its transaction:** how a verifier
  fetches the proofs a relay did not carry, and from whom.
- **Declarations made on chain,** through a registry, or proved from code.
  Here they are a descriptor's.
- **Slots in a mapping,** whose keys a declaration would have to name one by
  one. A range covers an array or a ring of slots.

## Version notes

- **Version 1.** RM-1 to RM-9, the fourth descriptor `relaxed.json`
  (`13-descriptors.md` version 5), and their vectors in
  `conformance/vectors/relaxed/`, every one new (decision records 0081 and
  0082).
