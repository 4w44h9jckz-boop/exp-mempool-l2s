# 07. Inclusion lists (FOCIL, EIP-7805)

Version 2, 2026-10-20. Version 1 had one budget fill, a budget for each
list; see the version notes at the end.

What an inclusion list obliges a builder to do, and what an includer puts in
one. Two Drafts were read from ethereum/EIPs at commit `258836f9`
(2026-10-07), and both were unchanged on master on 2026-10-08:

- EIP-7805, *Fork-choice enforced Inclusion Lists (FOCIL)*, Standards Track,
  sections "Roles And Participants", "Execution Layer", "IL Building",
  "Beacon chain changes" (Preset), "Core Properties" and "Payload
  Construction";
- EIP-8369, *VOPS Profiles for FOCIL Eligibility*, Informational, sections
  "VOPS profiles", "Fee validity", "Constants", "Profile 1", "Profile 2",
  "Transactions outside FOCIL enforcement", "Includers", "Builders",
  "Attesters" and "Security Considerations".

Version 2 adds the fill an implementation runs, read from ethrex at
`64b8fc09`, the Hegota testnet's client: `crates/blockchain/focil_eligibility.rs`
(`fill_il_budget`, `is_profile_2_candidate`) and
`crates/networking/rpc/engine/inclusion_list.rs`, which hands it one array.
That array is the one consensus-specs at `d9663f85` builds in
`specs/heze/inclusion-list.md`, `get_inclusion_list_transactions`, and
execution-apis at `e4ba6c4f` carries in `src/engine/bogota.md`, as
`inclusionListTransactions: Array of DATA`.

Quotations below are from those sections. A clause marked *Interpretation*
is this repository's reading where the texts leave a choice open, and names
decision record 0018.

In each slot a committee of validators, the **includers**, each builds an
inclusion list (IL) from its own view of the public mempool and gossips it.
The next slot's block must contain every listed transaction that "could be
validly included" when appended to the end of the payload, unless the block
lacks the gas; attesters do not vote for a block that leaves one out. What
FOCIL is for, and why an IL is built by a committee rather than by the
proposer, is not restated here.

EIP-7805 states its check for "the nonce and balance of `T.origin`", which
does not decide whether a frame transaction is valid. EIP-8369 says which
transactions can be enforced: Profile 1, the transaction types of the
account-nonce pool, under EIP-7805's own check; and Profile 2, frame
transactions whose validation prefix stays within a fixed state surface,
checked by replaying the prefix. EIP-8369 is Informational and says "a
future Standards Track extension to EIP-7805 must restate every binding
rule". The profile `eip-8369` therefore specifies a proposal, as `matcha`
does (decision record 0007).

## What changes

Under a profile with `enabled` true, a builder that has filled its block by
BB-3 of `03-block-building.md` then appends what the slot's ILs oblige it
to (IL-7), and a block is canonical only if it satisfies them (IL-8). The
pools do not change: an IL is built from a pool (IL-2), and EIP-8369 is
explicit that "public mempool admission and FOCIL eligibility remain
separate".

## Profile

**IL-1. Parameters.**

| Parameter | `off` | `eip-7805` | `eip-8369` | Note |
| --- | --- | --- | --- | --- |
| `enabled` | false | true | true | |
| `committee_size` | 16 | 16 | 16 | `IL_COMMITTEE_SIZE` |
| `max_bytes` | 8192 | 8192 | 8192 | `MAX_BYTES_PER_INCLUSION_LIST`, "for all of the RLP encoded transactions" |
| `frames` | false | false | true | whether frame transactions can be enforced, EIP-8369's Profile 2 |
| `max_verify_gas_per_il` | 1048576 | 1048576 | 1048576 | `MAX_VERIFY_GAS_PER_IL`, "candidate value `2**20`, pending benchmarks" |
| `max_verify_gas_per_tx` | 1048576 | 1048576 | 1048576 | `MAX_VERIFY_GAS_PER_TX`, "up to `MAX_VERIFY_GAS_PER_IL`"; *Interpretation*, decision record 0018: equal to it |
| `policy` | `fee` | `fee` | `fee` | *Interpretation*, decision record 0018: how an includer orders what it lists (IL-2); `age` is a variant |
| `fill` | `per-list` | `per-list` | `per-list` | IL-4: a budget for each IL, or `per-payload`, one budget over the array the execution layer receives |

A fourth profile, `ethrex`, is `eip-8369` with `fill` set to `per-payload`:
what ethrex at `64b8fc09` runs, with `MAX_VERIFY_GAS_PER_IL` and
`MAX_VERIFY_GAS_PER_TX` both $2^{20}$, and every other parameter as in
`eip-8369`. It records an implementation, as `geth` does in `00-model.md`;
whether the Hegota testnet enforces inclusion lists was not measured.

**Source:** EIP-7805, Beacon chain changes, Preset, and IL Building;
EIP-8369, Constants; ethrex at `64b8fc09`, `focil_eligibility.rs`. EIP-8369's `AA_VOPS_SLOT_COUNT` has no value until "the
enforcing Standards Track EIP selects" one; IL-5 does not need it.

## Clauses

**IL-2. What an includer lists.** An includer builds its IL from the
transactions pending in its own pool that a block built on its head could
include: those the account-nonce pool's view of NP-20 and the frame pool's
view of FP-16 return at the next block's base fee with a minimum tip of
zero. Under `frames` false, it lists no frame transaction. Under `frames`
true, it lists a frame transaction only if it is a Profile 2 candidate
(IL-3) whose budget fits what remains of its IL's `max_verify_gas_per_il`,
which the transaction then uses up.

It takes each sender's transactions in nonce order and orders the senders
by `policy`: under `fee`, by the effective tip of each sender's next
transaction at the next block's base fee, highest first, ties by arrival;
under `age`, by the arrival of each sender's next transaction, earliest
first. A transaction that would take the IL's encoded size above
`max_bytes` is left out, with the rest of its sender's, and the includer
goes on with the next.

*Interpretation*, decision record 0018. EIP-7805 leaves IL building "to the
discretion of implementers. For instance, they may select transactions from
the public mempool in various ways such as at random, by priority fee, or
based on how long they have been pending". The two orders here are the
second and third of those. Listing only what it could enforce, and skipping
a frame transaction its IL's budget cannot hold, are this repository's: a
listed transaction that cannot be enforced costs the IL bytes and buys
nothing.

**Source:** EIP-7805, IL Committee Members, IL Building; EIP-8369, Includers.

**IL-3. Profile 2 candidates.** A frame transaction is a Profile 2
candidate if, from the transaction alone:

1. FP-3's static checks pass;
2. with a leading expiry verifier frame skipped and, under a frame profile
   with recent roots (`08-recent-roots.md`), a leading recent-root verifier
   frame skipped as RR-4 places it, the classes of its validation prefix
   (FP-4, FP-5) are one of `self_verify`, `deploy | self_verify`,
   `only_verify | pay` and `deploy | only_verify | pay`;
3. no frame of the prefix has `ATOMIC_BATCH_FLAG` set, and no frame after
   the prefix has mode `VERIFY`;
4. its budget, the signature verification gas plus the declared gas limits
   of every frame of the prefix, expiry verifier included, is at most
   `max_verify_gas_per_tx`.

These are FP-3's and FP-5's checks, and FP-6's sum with IL-3's bound in
place of the pool's `max_verify_gas`. EIP-8369: "EIP-8141's `100_000`
limit applies to public mempool admission and does not determine either
value". It names no bound on state gas and no minimum tip, so FP-6's
`max_verify_state_gas` and FP-3's `price_limit` do not apply.

*Interpretation*, decision record 0055: EIP-8369's condition 2 skips only
the expiry verifier, "Ignoring the optional EIP-8141 expiry verifier frame
for shape matching", and so leaves out every transaction with a recent-root
verifier frame, the privacy spends its own motivation names. EIP-8272 says
"clients MUST skip both optional leading protocol verifier frames" (RR-4),
and ethrex's candidacy does so. Under a frame profile without recent roots
the frame is not a verifier frame, and condition 2 reads as written.

**Source:** EIP-8369, Profile 2, Constants; ethrex at `64b8fc09`,
`is_profile_2_candidate` and `validation_prefix`.

**IL-4. The budget fill.** Each IL is read in order with a budget of
`max_verify_gas_per_il`. For a frame transaction listed in it: if its
signature cost and prefix cost together exceed `max_verify_gas_per_tx` or
the budget left, it is ignored; otherwise the signature cost is deducted;
if a signature is invalid, the occurrence is not admitted and keeps only
that debit; otherwise the prefix cost is deducted, and the occurrence is
admitted if it is a Profile 2 candidate (IL-3). A frame transaction can be
enforced only if at least one of its occurrences, across the ILs, was
admitted. A transaction of the account-nonce pool uses none of the budget.

Under `fill` = `per-payload` there is one budget of `max_verify_gas_per_il`
for the slot, and the fill reads, by the same steps, the slot's ILs'
transactions as the execution layer receives them: each once, in the order
delivered. A frame transaction can be enforced only if the fill admitted
it. The order is an input of the check. Where none is given, the model
takes the ILs in committee order with each transaction at its first
occurrence.

*Interpretation*, decision record 0055: no text fixes the order the
execution layer receives. consensus-specs' `get_inclusion_list_transactions`
ends `return list(set(transactions))`, under "Order does not need to be
preserved", and the Engine API carries an `Array of DATA` with nothing on
its order. The default order is the model's, so that the simulator has one.

**Source:** EIP-8369, Includers ("Profile 2 budget fill is static and
evaluated per IL occurrence before deduplication"); under `per-payload`,
ethrex at `64b8fc09`, where `fill_il_budget` runs once over the
`inclusionListTransactions` of `engine_newPayloadV6`.

**IL-5. Valid at the end of the payload.** Against the state after the
last transaction of a block, with the block's base fee:

- a transaction of the account-nonce pool is valid if its fee cap is at
  least the base fee and its tip at most its fee cap, its nonce is its
  sender's, and its sender's balance covers its gas limit times its fee
  cap plus its value;
- under `frames` true, a frame transaction is valid if it can be enforced
  (IL-4), its fee is valid as above, and FP-7 to FP-10's simulation of its
  prefix succeeds against that state;
- under `frames` false, no frame transaction is valid for this check.

*Interpretation*, decision record 0018:
- the fee check is EIP-8369's `fee_valid`, which EIP-7805's "could be
  validly included" implies but does not list;
- EIP-8369 checks Profile 2 "at a builder-claimed transaction index", which
  defaults to the end of the payload. For a transaction whose dependencies
  are "position-stable", "this is equivalent to EIP-7805's end of payload
  rule", and every frame transaction the experiments send is: a fresh keyed
  nonce, or a payer only it spends from. The model checks at the end;
- Profile 2 also lets the prefix read the first `AA_VOPS_SLOT_COUNT` slots
  of the payer. FP-9 lets it read only the sender's, so a transaction of the
  frame pool never needs more, and the model keeps FP-9;
- a node that does not execute the payload, as a mempool node at the
  surface (`11-surface.md`), takes a frame transaction's validity at the
  end of the payload as a client's verdict, which stands for the fee check,
  FP-7 and FP-8 to FP-10 against the post-state, as an FP-8 verdict stands
  for the simulation (MD-6). It computes IL-4 itself (decision record 0055).

**Source:** EIP-7805, Execution Layer, step 3; EIP-8369, Fee validity,
Profile 1, Profile 2, Security Considerations.

**IL-6. Whether a block satisfies its ILs.** Take every transaction of every
IL once, in the order the ILs and their transactions are given, or under
`fill` = `per-payload` in the order delivered (IL-4). For each:
if the block contains it, go on; if its gas limit exceeds the gas the block
left unused, go on; if it is not valid at the end of the payload (IL-5), go
on; otherwise the block does not satisfy its ILs, and that transaction is
the omission. A block satisfies its ILs if no transaction is the omission.

**Source:** EIP-7805, Execution Layer, steps 1 to 3 ("If `T` is valid,
terminate process and return an `INCLUSION_LIST_UNSATISFIED` status").

**IL-7. What a builder appends.** After BB-3 has filled the block, a builder
appends listed transactions to it: it walks the ILs' transactions as IL-6
does, appends each that is valid at the end of the payload and fits the gas
left, under the BB-5 state transition, and walks them again whenever it
appended one, until a walk appends none. The block then satisfies its ILs.

**Source:** EIP-7805, Payload Construction (the "naive way": "If one is
found, append it to the end of the payload and update the post-state. Go
back to step 1").

**IL-8. A block that does not satisfy its ILs.** Attesters "only vote for
the proposer's block if it includes transactions from all stored ILs", so a
block that does not satisfy IL-6 for the slot's ILs is not canonical: the
slot has no block, and the next proposer builds on the same parent.

*Interpretation*, decision record 0018: every attester stores the same ILs,
the ones the slot's includers built, and attesters are honest.

**Source:** EIP-7805, Attesters, Fork choice changes.

## The simulator

The committee and the clock are the simulator's, not a pool's, and are
decision record 0018's. Each slot, `committee_size` nodes are drawn without
replacement from the network, from a random stream of their own, and each
builds its IL from its own pool at a set time in the slot (EIP-7805: "`Slot
N`, `t=0 to 8s`"); the ILs reach the next slot's builder and every attester.

## Not modelled

- IL gossip, its validation rules and its deadlines: the view freeze at
  9 s, the builder's freeze at 11 s, and an IL that arrives late.
- IL equivocation and the rule that ignores an equivocator's ILs.
- The builder's claimed index for Profile 2 (IL-5), and VOPS state: the
  model's nodes hold all state.
- Blob transactions, which no profile covers.
- A listed transaction with EIP-8288 dependencies (`05-aggregation.md`).
  IL-6 compares a transaction's gas limit with the gas a block left, and
  AG-8 charges a block more than that for such a transaction. No text says
  which one IL-6 counts, and no experiment combines the two profiles.
- The Engine API, and how a builder outside the proposer learns the ILs.
- Enshrined proposer-builder separation (EIP-7732), under which EIP-8369
  says Profile 2's check must move or "leave Profile 2 disabled".
- Rewards: FOCIL "does not provide explicit rewards for IL committee
  members".
- ethrex's second budget, at most 16 distinct code bodies and their bytes
  loaded by Profile 2's replays (`MAX_VALIDATION_CODE_BODIES`).
- The changes to EIP-7805 and EIP-8369 that `exp-frames` experiment 25
  reports open on 2026-10-13, ethereum/EIPs pull requests 12394 and 12396,
  which fill in `(keccak256(envelope), envelope)` order; they were not read
  here, and neither is a profile.

## Version notes

- **Version 1.** First version: IL-1 to IL-8.
- **Version 2.** IL-1 gains `fill` and the `ethrex` profile, IL-4 the fill
  with one budget over the delivered array, and IL-6 its order. IL-3 says
  which leading verifier frames shape matching skips, which version 1 left
  to the frame profile, and IL-5 how a node without the post-state takes
  validity. Under `per-list` every version 1 vector holds unchanged
  (decision record 0055).
