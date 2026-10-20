# 09. Expiring nonces (EIP-8266)

Version 1, 2026-10-09.

EIP-8266, *Expiring Nonces for Frame Transactions*, written down as clauses
on top of the frame pool. The EIP is Draft (Standards Track, Core, created
2026-05-15, requiring EIP-8141). It was read in full from ethereum/EIPs at
commit `258836f9` (2026-10-07), and again at `af80fc1c` (2026-10-09), where it
is unchanged: sections "Constants", "Mode selection", "Storage layout",
"Stateful validity", "Nonce consumption", "Mempool", "Rationale" and
"Security Considerations". Quotations below are from those sections unless
another is named. A clause marked *Interpretation* is this repository's
reading where the EIP leaves a choice open, and names decision record 0030.

A transaction in **expiring-nonce mode** is protected from replay by a
deadline of at most 60 seconds and by its signature hash, kept in a ring
buffer until the deadline passes, rather than by a nonce that advances. A
sender can have many such transactions pending, in any order, and none of
them leaves permanent state. The EIP is written against EIP-8141's single
nonce, where the mode is a sentinel value of `nonce`; its Rationale says how
it composes with EIP-8250's keyed nonces, which this repository's frame pool
models, and the clauses below take that composition. Why a shared sender
wants several transactions in flight, and why it cannot simply use one, is
not restated here.

The model does not run the ring buffer. A transaction's signature hash is
its hash (MD-7), and the state records, for each hash consumed, the deadline
it was consumed with.

## What changes

A pool under the `eip-8266` profile is the frame pool of `02-frame-pool.md`,
version 5, under the `eip-8141` profile, with these changes and no others:

- the state records consumed signature hashes (EN-2), which BB-5 of
  `03-block-building.md` writes (EN-7);
- FP-3 refuses the reserved key beside another key (EN-3);
- FP-7 is replaced for a transaction in the mode (EN-4), and FP-8 charges
  its paying frame (EN-5);
- FP-12 does not apply to it (EN-6);
- FP-15 evicts it when its hash is consumed (EN-6).

## Profile

**EN-1. Parameters.**

| Parameter | `eip-8266` | Note |
| --- | --- | --- |
| `expiring` | true | false under every profile of FP-1, MA-1, AG-1 and RR-1 |
| `expiring_key` | $2^{256} - 1$ | the key that selects the mode. *Interpretation*: the EIP's sentinel is `EXPIRING_NONCE_SENTINEL`, $2^{64} - 1$ in `nonce`, and "If both this EIP and EIP-8250 ship, the sentinel collapses into EIP-8250's keyed-nonce framing as a reserved key `nonce_key == 2**256 - 1`" (Rationale, "Composition with EIP-8250", which is "non-normative"). Decision record 0030 |
| `nonce_ring` | `nonce-ring` | the account whose storage holds $\mathit{seen}$ (EN-2); the EIP's `NONCE_RING`, whose address is "`0xTBD`" |
| `max_expiry_secs` | 60 | `MAX_EXPIRY_SECS` |
| `expiring_nonce_gas` | 13000 | `EXPIRING_NONCE_GAS` |
| `expiring_per_sender` | `many` | `many` admits several pending transactions in the mode from one sender ("Nodes MAY admit multiple pending expiring-nonce transactions per sender"); `one` keeps FP-12 for them, and is set only in variants the experiments measure |

Every FP-1 parameter is `eip-8141`'s. `RING_CAPACITY` is $2^{18}$ and is not
a parameter: see EN-7.

## Errors

| Code | Raised by |
| --- | --- |
| `ErrFrameExpiryMissing`, `ErrFrameExpiryTooFar` | EN-4 |

The EIP names no errors; these codes are this repository's. EN-3 raises
FP-3's `ErrFrameMalformed`, EN-4 FP-7's `ErrNonceTooLow` and FP-8's
`ErrFrameExpired`, and EN-5 FP-8's `ErrFramePrefixReverted`.

## State and mode

**EN-2. Consumed hashes.** The state (MD-3) records, for each consumed
signature hash $h$, the deadline $\mathit{seen}(h)$ it was consumed with,
and $\mathit{seen}(h) = 0$ for a hash never consumed. It is held as the
storage of the account `nonce_ring` at the slot that is $h$ read as an
integer, so FP-15 sees it change as it sees any account change. **Source:**
Storage layout, `slot_seen(h)`, "uint64 deadline, 0 means absent", in
"State in `NONCE_RING`". *Not modelled:* the slot's derivation,
`keccak256(h || left_pad_32(0))`; the ring itself, `slot_ring` and
`slot_ring_ptr`, and the clearing of an entry when the ring wraps; see
EN-7.

**EN-3. Mode.** With `expiring` true, a frame transaction is in
**expiring-nonce mode** if and only if `nonce_keys` is exactly
`[expiring_key]`. The pool MUST reject with `ErrFrameMalformed` (FP-3) a
transaction whose `nonce_keys` holds `expiring_key` beside another key, and
one in the mode whose `nonce_seq` is not 0. With `expiring` false the key is
an ordinary key. **Source:** Mode selection: "A frame transaction is in
**expiring-nonce mode** if `tx.nonce == EXPIRING_NONCE_SENTINEL`. Otherwise
the transaction follows EIP-8141 unchanged." *Interpretation:* the
composition names one reserved key and says the mechanism is "otherwise
unchanged", so a key set that mixes it with ordinary keys would both consume
sequences and not, and `nonce_seq` would carry a value nothing reads.
Decision record 0030.

## Admission

**EN-4. Validity in place of the nonce.** For a transaction in the mode, the
pool MUST NOT apply FP-7 and MUST instead, at FP-7's place, with
$t$ the head's `timestamp` plus `expiry_margin` (FP-8's reading of "now")
and $d$ the deadline of its `expiry_verify` frame, reject:

1. with `ErrFrameExpiryMissing`, a transaction with no `expiry_verify` frame;
2. with `ErrFrameExpired`, one with $d < t$;
3. with `ErrFrameExpiryTooFar`, one with $d > t + \mathit{max\_expiry\_secs}$;
4. with `ErrNonceTooLow`, one with $\mathit{seen}(h) \ge t$, its hash
   consumed by a transaction whose deadline has not passed.

**Source:** Stateful validity: `assert len(expiry_frames) == 1`,
`assert now <= d <= now + MAX_EXPIRY_SECS`,
`assert uint64(state[NONCE_RING].storage[slot_seen(h)]) < now`; "The
sender-nonce check from EIP-8141 (`tx.nonce == state[tx.sender].nonce`) is
skipped"; Mempool: "reject an expiring-nonce transaction if any
stateful-validity assertion above fails". FP-3 already refuses a second
`expiry_verify` frame, so only its absence is new. *Interpretation:* the
pool's "now" is FP-8's, the head's timestamp under `expiry_margin` 0
(decision record 0011).

**EN-5. The charge at payment.** In the mode, the frame that carries
`APPROVE_PAYMENT` MUST be refused with `ErrFramePrefixReverted` if its
`exec_gas` is below `expiring_nonce_gas`, since its `APPROVE` would halt out
of gas. Its `exec_gas` counts toward `max_verify_gas` in FP-6 as it is.
**Source:** Nonce consumption: "A payment-scoped `APPROVE` in
expiring-nonce mode additionally deducts `EXPIRING_NONCE_GAS` from the
executing frame [...] If the frame has less gas remaining than
`EXPIRING_NONCE_GAS`, the `APPROVE` halts out-of-gas and no approval effects
occur." *Interpretation:* in the model a frame's `exec_gas` is the gas it
uses (MD-6), so a sender in the mode writes the charge into it, and the
charge is validation gas like the rest of the frame's. Decision record 0030.

**EN-6. Several pending, and eviction.** With `expiring_per_sender` `many`,
FP-12 MUST NOT apply to a transaction in the mode: it is identified by its
hash, replaces nothing and is never replaced, and does not count as the
sender's pending transaction for one that is not in the mode. FP-11 applies
to it as to any other. On `reset`, FP-15's step 1 does not apply to a
transaction in the mode; instead, at that step, the pool MUST remove one whose
$\mathit{seen}(h)$ in the new state is at or above the new head's
`timestamp` plus `expiry_margin`. FP-15's step 2 removes one whose deadline
has passed. **Source:** Mempool: "Nodes MAY admit multiple pending
expiring-nonce transactions per sender; EIP-8141's
one-pending-frame-transaction-per-sender guidance does not apply. Instead,
the node MUST reserve each pending transaction's maximum cost
(`TXPARAM(0x06)`) against its gas payer's available balance"; "re-evaluate
those assertions on every new head and evict failures". *Interpretation:*
whether a transaction in the mode and one that is not, from the same sender,
may be pending together is not said; the Security Considerations allow "many
pending expiring-nonce transactions plus an unrelated legacy-nonce
transaction outstanding at the same time" on chain, and this spec admits
both in the pool. Decision record 0030.

## In a block

**EN-7. Applying it.** BB-5 applies a transaction in the mode as it applies
any frame transaction, except that it checks EN-4 in place of FP-7 with $t$
the block's timestamp $T$, and fails with the code EN-4 would reject it
with; and on success no sequence changes and $\mathit{seen}(h)$ becomes
$d$. BB-3 treats its `ErrNonceTooLow` as any other's: it moves on without
recording a failure. **Source:** Stateful
validity; Nonce consumption, `consume_expiring_nonce`, "storage[slot_seen(h)]
= d". *Not modelled:* `BufferFull`, which needs more than `RING_CAPACITY`
transactions in the mode with live deadlines, about 4369 a second
sustained by the EIP's own arithmetic (Rationale, "`MAX_EXPIRY_SECS`
bound"), and the bootstrap of the ring; the state gas of what the
transaction's own frames write; and activation.
