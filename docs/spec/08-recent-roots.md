# 08. Recent roots (EIP-8272)

Version 2, 2026-10-20. Version 1 gave recent roots to the `eip-8272` profile
only; see the version notes at the end.

EIP-8272, *Recent Roots for Frame Transactions*, written down as clauses on
top of the frame pool. The EIP is Draft (Standards Track, Core, created
2026-05-15, requiring EIP-7843 and EIP-8141). It was read in full from
ethereum/EIPs at commit `258836f9` (2026-10-07), sections "Constants",
"Current slot", "Root sources", "Entry and storage keys", "Recent root
contract", "Recent root verifier frame", "Public mempool handling",
"Rationale" and "Security Considerations". Quotations below are from those sections unless another is
named. A clause marked *Interpretation* is this repository's reading where
the EIP leaves a choice open, and names decision record 0023.

A **root source**, named by an address and a salt, writes one root per slot
into a ring buffer of `RECENT_ROOT_LENGTH` entries held by a contract at
`RECENT_ROOT_ADDRESS`. A frame transaction can declare one to sixteen
tuples `(source_id, slot, root)` in a `VERIFY` frame of fixed shape and
position, which checks that each is stored and recent. A privacy protocol's
spend proves membership against such a root rather than against the tip, so
the public mempool can check what the proof depends on without reading the
protocol's storage. The mechanism, and why EIP-8141's closed validation
grammar needs it, is not restated here.

The model does not run the contract. A root is an opaque name, a source id
and a storage key are functions of what they are derived from, and the
verifier frame is evaluated directly, as the EIP permits a client to do.

## What changes

A pool under the `eip-8272` profile is the frame pool of `02-frame-pool.md`
under the `eip-8141` profile, and a pool under `hegota-testnet` is the same
pool under its own FP-1 parameters, each with these changes and no others:

- a head carries a slot (RR-2), and a transaction may write roots (RR-3),
  which BB-5 of `03-block-building.md` applies;
- FP-5 classifies the verifier frame and checks its position (RR-4), and
  matches the prefix's shape with it skipped;
- FP-8 evaluates it (RR-5), FP-9 exempts it, and FP-10 records what it
  depends on (RR-6);
- FP-15 evicts a transaction whose root has left the window (RR-7);
- BB-5 checks it against the block's own slot (RR-8).

## Profile

**RR-1. Parameters.**

| Parameter | `eip-8272` | `hegota-testnet` | Note |
| --- | --- | --- | --- |
| `recent_roots` | true | true | false under every other profile of FP-1, MA-1 and AG-1 |
| `recent_root_address` | `0x0000000000000000000000000000000000008272` | the same | `RECENT_ROOT_ADDRESS` |
| `recent_root_code` | `recent-root` | `recent-root` | `RECENT_ROOT_CODE`, `TBD` in the EIP; a named string, compared by equality like all code (MD-2). *Interpretation*, decision record 0023; on the testnet the code is ethrex's own bytes, and a pool with a verdict (MD-6) does not compare it |
| `recent_root_length` | 8192 | 8192 | `RECENT_ROOT_LENGTH`; `RECENT_ROOT_USABLE_WINDOW` is one less, 8191, "because the current slot is not referenceable" |
| `max_recent_root_references` | 16 | 16 | `MAX_RECENT_ROOT_REFERENCES` |
| `root_margin` | 0 | 0 | slots before a reference expires within which RR-5 refuses it; "To avoid admitting a transaction that expires almost immediately, clients SHOULD NOT admit a transaction whose oldest reference is within a margin chosen by the node". 0 admits up to the window's end, and only variants the experiments measure set it otherwise |

Every FP-1 parameter is the base profile's: `eip-8141`'s under `eip-8272`,
and `hegota-testnet`'s own under `hegota-testnet`. The testnet's column was
read from ethrex at `64b8fc09`, the client the testnet runs, which pins
EIP-8272 at `824cbc0b0e` (its divergence ledger, section 1):
`crates/vm/system_contracts.rs` (`RECENT_ROOT_ADDRESS`) and
`crates/common/types/transaction.rs` (`FRAME_TX_RECENT_ROOT_LENGTH`,
`FRAME_TX_MAX_RECENT_ROOT_REFERENCES`, and a tuple packed as
`source_id(32) || uint64_be(slot) || root(32)`). Decision record 0053. `RECENT_ROOT_TUPLE_BYTES` is 72. Below,
$L$ is `recent_root_length` and $W = L - 1$ the usable window.

## Errors

| Code | Raised by |
| --- | --- |
| `ErrFrameRootPosition` | RR-4 |
| `ErrFrameRootFuture`, `ErrFrameRootExpired`, `ErrFrameRootUnknown` | RR-5, RR-8 |

The EIP names no errors; these codes are this repository's.

## Slots and writes

**RR-2. Slots.** A head (MD-4) carries `slot`, the consensus slot of the
beacon block that contains it, which a client MUST take from EIP-7843's
`slotNumber` and MUST NOT derive from its timestamp. A block built on a parent
(BB-4) is at the slot it is built for: the parent's plus one, plus the slots
since the parent that had no block. A pool's **current slot** is its head's
`slot` plus one, and does not advance in a slot without a block; a block's
current slot is its own `slot`. **Source:** Current slot: "During public
mempool validation, `current_slot` is one greater than the `slotNumber` in the
latest canonical execution header. [...] This value deliberately does not
advance during empty slots."

**RR-3. Writing a root.** A transaction's execution may call the write
operation, which the model carries as `root_writes`, a list of
`(source_address, salt, root)` with `source_address` the caller. Under a
profile with `recent_roots`, BB-5 MUST apply each, after the transaction's
`writes` and in list order, in a block at slot $S$: the root source is
$\mathit{source\_id}(\mathit{source\_address}, \mathit{salt})$, and the entry
at index $S \bmod L$ of that source becomes $(\mathit{source\_id}, S,
\mathit{root})$, replacing what was there. A later write in the same block to
the same source replaces an earlier one. Under a profile without
`recent_roots` they are not applied. **Source:** Write operation; "The final
write in canonical block execution order overwrites earlier writes, and only
that root is referenceable beginning in slot `S + 1`." *Interpretation:* the
EIP derives the source id, the entry and its storage key with keccak256 over
fixed-width encodings; the model uses injective functions of the same inputs,
which is the property those hashes are used for, and its source id is
written `address/salt`. A write's gas is in the transaction's `gas_used`.
Decision record 0023.

## The verifier frame

**RR-4. Shape and position.** Under a profile with `recent_roots`, a frame is
a `recent_root_verify` frame if its `mode` is `VERIFY`, its `target` is
`recent_root_address`, its `flags`, `value` and `state_gas` are 0, and its
`data_size` is $72 k$ with $1 \le k \le$ `max_recent_root_references`, where
$k$ is the number of tuples in its `roots`, which the model carries beside
`data_size` (MD-6). A frame that targets `recent_root_address` and is not
one is classified by FP-5 as before. The pool MUST reject with
`ErrFrameRootPosition` a transaction that has more than one
`recent_root_verify` frame, or one anywhere but first or second after an
`expiry_verify` frame. This check comes after FP-5's first, so a
`recent_root_verify` frame before an `expiry_verify` one is
`ErrFrameExpiryNotFirst`. FP-5's prefix shapes are then matched with the
leading `expiry_verify` and `recent_root_verify` frames skipped, and the
frame's `exec_gas` counts toward FP-6's `max_verify_gas` like any prefix
frame's. **Source:** Recent root verifier frame; Public mempool handling:
"A transaction eligible for the public mempool MUST contain no more than one
recent root verifier frame. If present, it MUST appear immediately after an
optional `expiry_verify` frame and before every other frame", "clients MUST
skip both optional leading protocol verifier frames", "Clients MUST count the
recent root verifier frame's `limits.execution` toward EIP-8141's
`MAX_VERIFY_GAS` limit", and "Clients MUST check this frame shape and data
encoding before reading sender state".

**RR-5. Admission.** When FP-8 reaches a `recent_root_verify` frame, at a
current slot $s_c$ (RR-2), the pool MUST evaluate it directly, in this order:

1. if the code at `recent_root_address` is not `recent_root_code`,
   `ErrFramePrefixReverted`;
2. for each tuple $(\mathit{source}, s, r)$ in order, with age
   $a = s_c - s$: if $s \ge s_c$, `ErrFrameRootFuture`; else if
   $a > W - m$, `ErrFrameRootExpired`; else if the entry at index
   $s \bmod L$ of `source` in the head state is not
   $(\mathit{source}, s, r)$, `ErrFrameRootUnknown`;
3. if the frame `reverts`, `ErrFramePrefixReverted`.

In the pool $m$ is `root_margin`; in a block (RR-8) it is 0. FP-9's trace
rules do not apply to the frame, which is protocol defined. **Source:**
Validation operation, "For each tuple, the contract MUST check: `slot <
current_slot`, `current_slot - slot <= RECENT_ROOT_USABLE_WINDOW`, [...]
`storage[storage_key] == entry_hash`"; Public mempool handling: "Clients MUST
reject the transaction from the public mempool if the code at
`RECENT_ROOT_ADDRESS` does not equal `RECENT_ROOT_CODE`", "a client MAY
evaluate this frame directly", "A client MUST reject the transaction if EVM
execution would revert or halt exceptionally, including when
`frame.limits.execution` is insufficient", and the margin quoted in RR-1.
*Interpretation:* the frame's `reverts` observation stands for a halt for
want of gas, because the gas the frame needs depends on `RECENT_ROOT_CODE`,
which is unset; the order of the three steps, and of the checks within a
tuple, is the contract's as the EIP lists them, which no admission result
depends on but the error reported; and the margin is read as refusing a
reference that would be evicted (RR-7) within $m$ slot advances, so 0 is the
EIP's window exactly. Decision record 0023.

**RR-6. Dependencies.** On admission the pool MUST record, beside FP-10's
dependencies, the code at `recent_root_address` and, for each distinct tuple,
the entry it was checked against, and the transaction's **root expiry**, the
first current slot at which RR-7 evicts it, $\min s + L$ over its tuples.
For a transaction that carries a `verdict` (MD-6), the verdict stands for
RR-5 and for the code and entries, which the pool does not read; the root
expiry and the newest tuple's slot are still recorded, because they are read
from the transaction's tuples rather than from execution, so RR-7 applies to
it as to any other. *Interpretation*, decision record 0053.
FP-15 step 3 re-runs the transaction when any of these changed, as for any
other dependency. **Source:** Public mempool handling: "On admission, clients
MUST record each distinct `(storage_key, entry_hash)` dependency and the
first `current_slot` at which it expires", "Clients MUST also track the code
and activation status of `RECENT_ROOT_ADDRESS` as dependencies", and "When
any recorded dependency may have changed, clients MUST recheck the complete
age and storage predicates for each affected transaction". *Interpretation:*
the EIP asks for the age and storage predicates to be checked again, and
FP-15 step 3 re-runs the whole prefix; the two differ in the work counted,
not in what is evicted, and in the model an entry a transaction depends on
changes only by a head that goes back, which the simulator never produces
(decision record 0023).

## Head changes and blocks

**RR-7. Eviction.** On `reset`, after FP-15 step 2 and before step 3, the
pool MUST remove every transaction with a tuple whose slot is at or above the
new current slot, and every transaction whose root expiry is at or below it,
without re-running anything. **Source:** Public mempool handling: "Clients
MUST evict a pending transaction if any tuple has `slot >= current_slot`.
Otherwise, they MUST evict it when any tuple reaches: `current_slot - slot >=
RECENT_ROOT_LENGTH`", and "Clients SHOULD index pending transactions by these
values so that a slot advance [...] does not require scanning unrelated
transactions". The margin of RR-5 does not apply here.

**RR-8. Building.** BB-5 MUST fail a frame transaction whose
`recent_root_verify` frame fails RR-5 against the state at that point in the
block, with the block's own slot as the current slot and no margin. A root
written in the block cannot be referenced in it, because its slot is the
current one. **Source:** Current slot: "Before including a transaction in a
payload, a client MUST revalidate it with `SLOTNUM` set to that payload's
`slotNumber`"; Rationale, Window choice: "A reference close to expiry may
become stale if slots are skipped, so builders revalidate it against the
exact payload slot before inclusion."

## Not modelled

- The contract's bytecode, its gas, warm and cold access, `SLOTNUM` and the
  frame's receipt. `RECENT_ROOT_CODE` is `TBD`, and the direct evaluation the
  EIP permits must match it to the gas; a frame's `exec_gas` and `reverts`
  say what the bytecode would.
- Activation, and a head that crosses it: a profile with `recent_roots` has
  the contract from genesis, with the code the scenario gives it.
- Reorganisations. RR-6's dependencies are recorded and re-checked, but the
  simulator never produces a head that removes a written root.
- The write operation's failures: a call with value, a static call, and
  `DELEGATECALL` or `CALLCODE`, which write in the caller's storage context.
- Introspection through `FRAMEPARAM`, `FRAMEDATALOAD` and `FRAMEDATACOPY`: a
  later frame's observations (MD-6) already say what its code concludes.
- Inclusion of root writes. The EIP "does not guarantee inclusion of root
  writes", and nothing here does either; the simulator's builders may leave
  them out.

## Version notes

- **Version 2.** RR-1 gains a `hegota-testnet` column: the testnet runs
  EIP-8272, and the profile now models it with the constants ethrex uses,
  which are `eip-8272`'s. RR-6 says what a transaction with a verdict
  records. Under `eip-8272` nothing changes, and every vector of version 1
  holds unchanged and now says version 2. Under `hegota-testnet` a
  `recent_root_verify` frame is now classified and skipped in FP-5's shapes
  where version 1 left it an unrecognised frame (decision record 0053).
