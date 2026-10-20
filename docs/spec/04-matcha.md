# 04. MATCHA: several pending frame transactions per sender (proposal)

Version 3, 2026-10-09.

**Status: proposal.** This document states, as clauses, a mempool policy that
no client implements and no EIP specifies. Its source is the post *Mempool
Account Transaction Capacity from Historical Activity (MATCHA)*, by Thomas
(soispoke on ethresear.ch), "based on ideas and discussions with" Vitalik
Buterin and Toni Wahrstaetter: ethresear.ch topic 25949, first post dated
2026-09-08, read with its replies up to #14 on 2026-10-07 and again on
2026-10-09 (`refs/refs.md`). Quotations below are from that first post unless
another is named. A clause
marked *Interpretation* is this repository's reading where the post leaves a
choice open, and names the decision record that made it. The policy exists so
that experiments can measure it; its profile, `matcha`, is the specification
of nothing but this document.

MATCHA keeps EIP-8141's one pending frame transaction per sender as a
*baseline* and admits further transactions from the same sender, on disjoint
EIP-8250 nonce keys, by spending a per-sender capacity called *width*. A
sender earns width only from the gas its frame transactions used in finalized
blocks, and spent width is never returned. The public mempool it relaxes is
EIP-8141's (`02-frame-pool.md`). An earlier design study worked out what
MATCHA means for a privacy pool that is the sender of every spend, and
priced its charge for that pool's spend on 2026-09-08.

## What changes

A pool under the `matcha` profile is the frame pool of `02-frame-pool.md`,
version 1, under the `eip-8141` profile, with these changes and no others:

- FP-12 is replaced by MA-5 to MA-7;
- FP-15 steps 3 and 4 are replaced by MA-9 and MA-10;
- FP-16 is amended by MA-11;
- MA-4 gives meaning to `finalize` (MD-8), and MA-8 adds a lifetime;
- MA-13 adds the post's optional linear fees using `load`, off unless
  `load_price` is above 0;
- MA-14 gives every transaction a class, which MA-5 shares a baseline
  across; under `contention` = `sender`, the post's, it changes nothing.

## Profile

**MA-1. Parameters.**

| Parameter | `matcha` | Note |
| --- | --- | --- |
| `per_sender` | `matcha` | FP-12's third value; every other FP-1 parameter is `eip-8141`'s |
| `width_cap` | 16777216 | the "local cap"; *Interpretation*: the post gives no value, decision record 0007 |
| `safety_factor` | 2 | *Interpretation*: the post gives no value; 2 is the factor an earlier design study of a voucher pool quotes for it, decision record 0007 |
| `lifetime` | 10800 s | the "maximum local lifetime"; *Interpretation*: the post gives no value, and this is NP-1's `lifetime`, decision record 0007 |
| `reuse_balance` | true | whether a change to a balance alone re-runs a prefix (MA-9): "A change to the payer balance does not by itself require rerunning validation" |
| `load_price` | 0 | MA-13's floor for the first additional transaction, the post's `base_price`, in wei; 0 turns the optional policy off |
| `contention` | `sender` | what a class is (MA-14): `sender`, the post's, or `storage` or `slot`, two readings of reply #2's question; *Interpretation*, decision record 0026 |

## Errors

| Code | Raised by |
| --- | --- |
| `ErrFrameSenderBusy`, `ErrFeeCapTooLow`, `ErrFrameExpired`, `ErrFrameInsufficientWidth`, `ErrFrameLoadUnderpriced` | MA-6 |
| `ErrReplaceUnderpriced`, and those of MA-6 but the first | MA-7 |

`ErrFrameInsufficientWidth` and `ErrFrameLoadUnderpriced` are this repository's; the others are named as in
`02-frame-pool.md`, and `ErrFeeCapTooLow` is go-ethereum's name for a fee cap
below the base fee.

## Width and charge

**MA-2. Charge.** A frame transaction's admission gas is

$$
a = 12000 + 475 \cdot \lvert \mathit{frames} \rvert + 16 \cdot D + \sum_{\sigma} c(\sigma) + \sum_{f \in \text{prefix}} e_f ,
$$

with $D$, $c(\sigma)$ and $e_f$ as in FEE-4 and the prefix as in FP-4, which
is FEE-4's $g_{\text{intr}}$ without its value-transfer term, plus the
declared execution limits of the validation prefix. Its charge is
$\lceil \mathit{safety\_factor} \cdot a \rceil$, computed exactly.
**Source:** "`admission_gas(tx)` covers transaction data, signatures,
EIP-8250 nonce checks, [EIP-8272 checks], and EIP-8141 execution through
payment approval. For frame execution, it uses the declared execution gas
limits [...] It excludes later application execution. State gas [...] is
excluded"; `charge(tx) = ceil(safety_factor * admission_gas(tx))`.
*Interpretation:* the per-transaction and per-frame costs are counted as
admission work and the value-transfer cost is not, which is how an earlier
design study priced the same charge; EIP-8250 nonce checks enter only
through the nonce bytes in $D$, because EIP-8250 charges them state gas and
no execution gas. Decision record 0007.

**MA-3. Width.** The pool keeps a `width` for every sender, an integer that
starts at 0, is local to the pool, and is kept while the sender has no pending
transaction. Only MA-4 increases it. MA-6, MA-7 and MA-9 decrease it, and
nothing returns what they spent: "Inclusion, invalidation, removal, expiry, or
reorg does not return that `width`."

**MA-4. Earning width.** On `finalize(blocks, now)` the pool MUST take the
blocks in increasing `number`, skip every block whose number is not above the
highest it has already credited, and for each sender $S$ with gas $g_S$ in the
block set

$$
\mathit{width}(S) \leftarrow \min(\mathit{width\_cap},\ \mathit{width}(S) + g_S).
$$

**Source:** "A `sender` starts with no `width` and earns it from the actual
gas used by its Frame Transactions in newly finalized blocks, up to a local
cap. Each finalized block is credited only once."

## Admission

**MA-5. Baseline and additional transactions.** A transaction admitted while
the pool holds no pending transaction from its sender that shares its class
(MA-14) is a *baseline*. Every other transaction admitted from the sender is
*additional*. Under `contention` = `sender` every two transactions from a
sender share a class, so a sender has at most one baseline, and when it leaves
the pool while other transactions from its sender remain, the sender has no
baseline until it has no pending transaction at all. **Source:** "The EIP-8141
baseline spends no `width`, but every additional transaction does. If the
baseline leaves while other transactions remain pending, none of them becomes
the baseline; it becomes available again only when the sender's pending set
is empty." *Interpretation:* under `storage` and `slot` the rule is read class
by class: a transaction that shares a class with a pending one is additional
whether or not that one is a baseline, so no transaction becomes a baseline
when another leaves. Decision record 0026.

**MA-6. Admitting an additional transaction.** A transaction that replaces
nothing, from a sender that has a pending transaction, MUST pass check 1 and,
when it is additional (MA-5), checks 2 to 5, in order, after FP-11 and in
place of FP-12's:

1. neither it nor any pending transaction from the sender uses nonce key 0,
   and its `nonce_keys` share no key with theirs, else `ErrFrameSenderBusy`;
2. `max_fee` is at least the pending base fee (FEE-1), else
   `ErrFeeCapTooLow`;
3. if it has an expiry frame, its deadline is above the head's `timestamp`,
   else `ErrFrameExpired`;
4. the sender's width is at least the transaction's charge (MA-2), else
   `ErrFrameInsufficientWidth`;
5. its effective tip at the pending base fee is at least MA-13's floor,
   else `ErrFrameLoadUnderpriced`. With `load_price` 0 this always holds.

FP-13 and FP-14 then apply as before, and when an additional transaction is
admitted the pool MUST deduct its charge from the sender's width. **Source:** "Before
spending `width`, an additional transaction must pass the ordinary admission
checks and be valid for a child of the current head, including
`max_fee_per_gas >= next_base_fee`. Its `sender` must then have enough
`width`, and the client deducts the transaction's `charge`"; "No two distinct
pending transactions may use the same `(sender, nonce_key)`"; "Frame
Transactions that do not satisfy MATCHA continue to follow the 'one
transaction per sender' policy."
*Interpretation:* key 0 is excluded on both sides, as under `disjoint-keys`,
because EIP-8250 permits a future policy to admit several transactions "on
disjoint non-zero key sets" (Rationale) and the post names no wider set.
"Valid for a child" is read as checks 2 and 3: a child's timestamp is above
its parent's, and the expiry verifier "reverts unless
`block.timestamp <= expiry_timestamp`" (EIP-8141, Expiry Verifier Frame).
Decision record 0007.

**MA-7. Duplicates and replacements.** A duplicate is refused by FP-2 and
spends nothing. A transaction with the identity of a pending one (FP-12)
replaces it only if the fee rule of NP-11 holds with `price_bump`, else
`ErrReplaceUnderpriced`. A replacement of a baseline is a baseline, and spends
nothing, when every element of its class (MA-14) is in the class of the
transaction it replaces or in that of no other pending transaction from its
sender; under `contention` = `sender` this always holds. Any other
replacement, and every replacement of an additional transaction, is
additional: it MUST pass checks 2 to 5 of MA-6, and when it is admitted the
pool MUST deduct its charge. **Source:** "Exact duplicates of a transaction already
pending share one pool record and spend no `width`. Replacing the baseline
also spends no `width`. Replacing an additional transaction with different
bytes spends another `charge`." *Interpretation:* the condition on a
replacement's class keeps the baselines' classes apart (MA-14) when a
replacement reads what another pending transaction reads. Decision record
0026.

**MA-8. Lifetime.** At every operation that carries `now`, before anything
else, the pool MUST remove every frame transaction admitted more than
`lifetime` seconds before `now`. **Source:** "Every pending transaction is
removed after a maximum local lifetime, without affecting its onchain
validity. A removed transaction must pass admission again [...] and spends
another `charge` if it is additional." *Interpretation:* the age is counted
from the transaction's own admission, so a replacement starts a new
lifetime, and "more than" follows NP-18. Decision record 0007.

## Head changes

**MA-9. Revalidation.** In place of FP-15 step 3, for each remaining
transaction, in the order received, whose recorded dependencies (FP-10)
changed:

1. if `reuse_balance` is true and the only dependencies that changed are
   balances, the pool MUST NOT re-run its prefix, and MA-10 stands in for
   the balance check of FP-8;
2. otherwise, if it is a baseline, the pool MUST re-run FP-7 to FP-10 and
   remove it if they fail, as FP-15 does;
3. otherwise, if the sender's width is at least the transaction's charge,
   the pool MUST deduct the charge, then re-run FP-7 to FP-10 and remove it if
   they fail;
4. otherwise the pool MUST remove it without re-running anything.

Only a re-run counts as a re-simulation (FP-15). **Source:** "Rerunning its
validation prefix spends its stored `charge` before the work begins. If the
`sender` cannot cover that charge, the client removes the transaction without
rerunning the prefix"; "A change to the payer balance does not by itself
require rerunning validation. The client can reuse its earlier result if it
confirms that validation would run with the same code and inputs."
*Interpretation:* a baseline's re-run spends nothing, because the post
charges the re-runs of additional transactions and says the baseline spends
no width. In the model no prefix can observe a balance except through
`APPROVE`'s check against `max_cost` (FP-9 bans `BALANCE` and `SELFBALANCE`),
so reusing the earlier result on a balance change is exact. Decision record
0007.

**MA-10. Reservations after a head change.** In place of FP-15 step 4, the
pool MUST recompute $R(P)$ (FP-11) over all its pending transactions and
remove none for it. A payer is *over-reserved* when
$\mathit{balance}(P) - R(P) - w(P) < 0$ at the current head.
**Source:** "After a new head, affected transactions remain unavailable for
block construction until their combined reservations fit the new balance."

**MA-11. Availability.** The pending view of FP-16 MUST leave out every
transaction whose payer is over-reserved. *Interpretation:* "their combined
reservations" is read as all of the payer's pending transactions together,
so an over-reserved payer's transactions are all unavailable until the sum
fits, rather than the newest ones until the rest fit. Decision record 0007.

## Observables

**MA-12. Width, baseline and load.** A pool under `matcha` also exposes
`width(sender)`, `baselines(sender)`, the hashes of the sender's pending
baselines in the order admitted, `baseline(sender)`, the first of them or
none, and `load(sender)` (MA-13).

## Linear fees using load

**MA-13. The load floor.** A sender's *load* is the sum of the charges
(MA-2) of its pending additional transactions (MA-5), whether available or
not (MA-11). An additional transaction with charge $c$, from a sender whose
load is $L$, has the floor

$$
\mathit{load\_price} \cdot \frac{c + L}{c} ,
$$

and MA-6's check 5 compares its effective tip (FEE-2) at the pending base fee
(FEE-1) with the floor exactly. For a replacement (MA-7), $L$ leaves out the
transaction it replaces. A transaction leaves the load when it leaves the
pool, for any reason; the width it spent stays spent (MA-3).
**Source:** "A client may also track `load`, the sum of the `charge` values of
the additional transactions that remain pending. Each new additional
transaction must offer a minimum effective priority fee that rises linearly
with this `load`. The client chooses `base_price`, the starting fee floor.
When all charges are equal, the floor is `base_price` for the first
additional transaction, twice `base_price` for the next, then three times,
and so on. When a transaction leaves the mempool, its `charge` is removed from
`load` even though its spent `width` is not returned." The post calls the
policy optional, because it "raises fees for honest users when their shared
`sender` is busy". *Interpretation:* the post gives the floor only when every
charge is equal. With unequal charges the new transaction's own charge is
read as the unit, which is the only reading that gives the post's sequence
for equal charges without a constant the post does not name. "Remain
pending" is read as held by the pool, so an unavailable transaction still
counts. The baseline has no floor, because the floor is asked only of "each
new additional transaction". `matcha` sets `load_price` to 0, because the
policy is optional. Decision record 0022.

## Contention classes

**MA-14. Classes.** When the pool admits a transaction it MUST give it a
*class*, a set computed from the dependencies FP-10 recorded at that run and
kept while the transaction is pending. Two transactions from one sender
*share* a class when their classes have an element in common. Under
`contention` = `sender` the class of every transaction is its sender alone.
Under `storage` and `slot` its elements are its dependencies other than

1. nonce sequences: a change makes the transaction stale, and FP-15 step 1
   removes it without a run;
2. balances, when `reuse_balance` is true: a change to them alone re-runs
   nothing (MA-9, step 1);
3. the code of an account whose code is neither empty nor a delegation
   (MD-2), which nothing changes on chain;
4. the entries of the recent root contract (RR-6), which in the model change
   only by a head that goes back, and which RR-7 evicts the transaction for
   before they are overwritten;

and under `storage` every storage slot of one account is the same element,
that account's storage, while under `slot` each slot is an element of its
own. What is left is what can make the pool re-run the prefix (MA-9), so
under every value a sender's baselines have classes that share nothing, and a
head change re-runs, without a charge, at most one of them for each element
it changes. **Source:** the post indexes `width` by `sender`. Reply #2 on the
thread, by AnkushinDaniil (2026-09-08), observes that one write can take down
a pending set only when the prefixes "read shared live-contended state", and
asks "whether width could be indexed by that: full charge when the prefix
reads shared live-contended state, waived or reduced when it's provably
single-writer or recent-root-bound", after the three classes of ethresear.ch
topic 25934 (single-writer, recent-root-bound, live-contended); it names the
counter, "can a client decide cheaply that a prefix reads no shared contended
state without running it?" The post's author replied, #4, that "lower risk of
repeated invalidation could justify a lower charge, even if the initial
verification costs the same", but that "'single-writer' is not enough: an app
can change its own validation setting and invalidate txns", and that a shared
payer balance remains. EIP-6780 keeps a contract's code after the transaction
that created it, and EIP-7702 delegates only an account whose code "is empty
or already delegated", so item 3 holds on chain; BB-5 delegates every
authority of a type 4 transaction without that check, and no vector or
experiment gives it an account with code. *Interpretation:* "indexed
by" is read as MA-5's baseline taken per class, which waives the charge for a
transaction that shares no class with a pending one; a reduced charge is not
modelled. Width is still earned and spent by the sender (MA-3, MA-4), since
finalized gas belongs to no class. `storage` is the reading a client can make
without knowing who may write a slot: a prefix that reads no storage of its
sender, only nonces, balances, permanent code and recent roots, is waived.
`slot` takes reply #4's objection at its unit: the slot one write changes. A
class is read off the run the pool already makes, so it costs no further
work; the prefix runs before the width check (MA-6, and the open question
below). Decision record 0026.

## Not modelled

- FOCIL (EIP-7805) and the frame-transaction eligibility of EIP-8369 (Draft,
  Informational, *VOPS Profiles for FOCIL Eligibility*), which the post calls
  "the proposed FOCIL extension for Frame Transactions", and the deterrent the
  post builds on them; the model has no consensus layer, so width draining is
  measured here without it.
- The optional minimum period before expiry. The other optional policy,
  linear fees using `load`, is MA-13.
- EIP-8272 recent roots, which the model does not have.
- Per-peer limits, and the client's total limits on verification, state
  access and cleanup other than `max_pending` (FP-14).
- Reorgs: finality in the model is never reverted, and a removed transaction
  is never re-injected.
- The extension to paymasters in reply #7 of the thread, under which a payer
  rather than a sender would earn and spend width.

## Open questions, not settled here

- Whether "the actual gas used" includes state gas. EIP-8250 charges a
  payment-scoped `APPROVE` 97920 state gas for each nonce key used for the
  first time, more than a privacy spend's execution gas, so the answer
  decides whether a pool that spends from fresh nullifiers earns about twice
  the width it uses. The model has one gas dimension (FEE-4, *Not modelled*)
  and credits `gas_used`.
- The values of `width_cap`, `safety_factor` and `lifetime`. Experiment 02
  varies the first two.
- Whether "valid for a child of the current head" should use the next slot's
  timestamp, which a client knows. FP-1's `expiry_margin` set to the slot
  time makes FP-8 check it for every frame transaction, which implies MA-6's
  check 3 (compare the open question under FP-15, and experiment 05).
- Whether the width check should come before the prefix runs. MA-6 orders it
  after FP-7 to FP-11, reading "the ordinary admission checks" as EIP-8141's,
  which run the validation prefix, so every `ErrFrameInsufficientWidth`
  refusal costs a node one prefix run that nothing pays for. The charge
  depends only on the static prefix (FP-4), so a client could check width
  first; the payer, and so FP-11, is known only after the run. Experiment 02
  counts these runs in its work column. `02-frame-pool.md` version 5's
  `static_first` reads the payer from the prefix's last frame instead, and
  experiment 11 measures that order for FP-11 and FP-12; MATCHA's checks
  are not part of it. Under `contention` = `storage` or `slot`, whether a
  transaction is additional, and so whether width is asked at all, is also
  known only after the run (MA-14).
- Which `contention`, if any. `sender` charges a pool whose spends read
  nothing another can change for every spend after the first; `storage` and
  `slot` waive it, and `slot` also waives it for an adversary whose junk
  reads a slot each, at the price of a write for every slot it invalidates.
  Experiment 17 measures both sides against experiment 02. It finds that a
  waived class also waives the bound width puts on what one sender holds in
  every pool, which then rests on the pool's size and its eviction order
  (FP-14), and that a prefix reading a slot written in every block gets the
  same throughput under all three values: EIP-8272's recent roots, which
  are in no class, are that pool's way out.

## Version notes

- **Version 2.** MA-13 adds the post's optional linear fees using `load`,
  with `load_price` in MA-1, check 5 in MA-6 and MA-7, and `load(sender)` in
  MA-12. `matcha` sets `load_price` to 0, so its behaviour does not change:
  every vector of version 1 holds unchanged and now says version 2.
- **Version 3.** MA-14 adds classes, with `contention` in MA-1, and MA-5 to
  MA-7, MA-9 and MA-12 read a baseline per class; MA-12 gains
  `baselines(sender)`. `matcha` sets `contention` to `sender`, under which
  every transaction from a sender shares its class, so its behaviour does not
  change: every vector of version 2 holds unchanged and now says version 3.
