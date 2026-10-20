# 0030. Expiring nonces compose with keyed nonces as a reserved key, and a shared sender keeps its nullifier in storage

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 15 runs only if EIP-8266's expiring nonces compose with
EIP-8250's keyed nonces. An earlier account abstraction study asked the
authors whether they do: EIP-8266 selects its mode on
`tx.nonce == EXPIRING_NONCE_SENTINEL`, EIP-8250 replaces `nonce` with
`nonce_keys, nonce_seq` outright, and, as that study read them on
2026-09-14, neither EIP mentions the other. Without an answer that study
priced its shared-sender design with a nullifier and without concurrency.

EIP-8266 at `258836f9` and at `af80fc1c`, identical, does mention the other.
Its Rationale, "Composition with EIP-8250": "If both this EIP and EIP-8250
ship, the sentinel collapses into EIP-8250's keyed-nonce framing as a
reserved key `nonce_key == 2**256 - 1`; `NONCE_RING`'s storage can live in
`NONCE_MANAGER` under a distinct slot prefix; and the mechanism in this EIP
is otherwise unchanged. This composition is non-normative." The EIP's
history was not reachable from here, so whether the paragraph was added
after that study's reading is not established; `refs/refs.md` says so.

So they compose, as alternatives: a transaction is in expiring-nonce mode
or it uses keys. A shared sender cannot put a nullifier in a nonce key and
have the mode at once. It can have the mode and keep its nullifiers in its
own storage, which a validation prefix may read (FP-9); that study's note
that the ring cannot be a nullifier, since a freed slot is a re-spendable
note, is about the ring, not about that storage.

## Decision

1. **The composition is read as written**, in a new document,
   `docs/spec/09-expiring-nonces.md`, version 1, with clauses EN-1 to EN-7
   on top of the frame pool, and a profile `eip-8266`.
2. **The mode is the reserved key alone** (EN-3): `nonce_keys` exactly
   `[2**256 - 1]`, with `nonce_seq` 0. A key set that mixes it with ordinary
   keys is malformed, since it would both consume sequences and not.
3. **The pool's "now" is FP-8's** (EN-4), the head's timestamp under
   `expiry_margin` 0, as decision record 0011 read EIP-8141's deadline.
4. **The 13,000 gas is validation gas** (EN-5): it is deducted from the
   paying frame, so in the model it is part of that frame's `exec_gas`, and
   counts toward `max_verify_gas`. A paying frame with less is refused, as
   its `APPROVE` would halt out of gas.
5. **Several pending, beside a keyed one** (EN-6). The profile takes the
   EIP's MAY and exempts the mode from FP-12; FP-11's reservation applies,
   as the EIP requires. A transaction in the mode does not count against a
   keyed one from the same sender, nor the reverse, since on chain neither
   touches the other's replay protection.
6. **The ring is not modelled** (EN-2, EN-7): only the consumed hashes and
   their deadlines. `BufferFull` needs more than $2^{18}$ live deadlines,
   about 4369 transactions a second by the EIP's arithmetic, which no
   experiment here approaches.
7. **A shared sender in the mode keeps its nullifier in storage.** In the
   simulator a spend in the mode reads its own nullifier slot in the
   sender's storage, and writes it, as experiment 11's spends with
   `record` `storage` do, and carries a deadline at most 60 seconds
   after the timestamp of the head of the node it is made for, since a node
   with an older head refuses a later one as too far. A version that can no
   longer make the next block has to be signed again by its user with a new
   deadline, since the deadline is under the signature.

## Consequences

- `docs/spec/09-expiring-nonces.md`, its vectors in
  `conformance/vectors/expiring/`, and the reference frame pool's mode.
- The simulator's shared-sender spends gain the mode.
- Experiment 21 measures experiment 01's ceiling under it.
- The question to the authors has a partial answer in the EIP itself: they
  compose as alternatives, so a pool can have concurrency and a nullifier,
  if the nullifier lives in storage.
