# Conformance vectors

Hand-written expected behaviour, one file per clause of `docs/spec/`, and a
runner (`run.py`) that plays every vector against the reference implementation
in `ref/python/`. The vectors were written from the clauses before the
implementation existed. A vector written after the code it checks has read the
answer.

## The direction

Vectors are **clause-first**. A vector is written by hand from a clause as an
expected value and committed with the clause it binds. The implementation must
match the vector. **A vector is never regenerated from the implementation**, and
there is no target that does so: a vector derived from the code agrees with the
code by construction, including wherever the code is wrong. Decision record
0001 adopts the rule.

When a vector and the implementation disagree, exactly one of three things is
true, and which one has to be worked out before anything changes:

1. **The implementation is wrong.** Fix the implementation.
2. **The vector is wrong.** Fix the vector by hand, against the clause, never by
   running anything.
3. **The clause is ambiguous.** Two careful readers would write different
   vectors. Fix the clause in `docs/spec/`, bump its document version, and say
   in the commit which clause moved. If deciding between 1 and 2 needs a look
   at the implementation to see what the answer "should" be, it is case 3.

A vector may also be checked against a real client: the inputs are
transactions and states that a client can be driven with, and the error codes
are go-ethereum's names where one exists. Doing so is on the plan's roadmap.

A second implementation plays them too: a TypeScript frame pool in the
owner's fork of skandha, which holds a byte-for-byte copy of this directory
at a named commit and never edits it. A case it disagrees with is settled
here by the three cases above, and a vector that turns out to depend on the
reference rather than the clause is case 3 (decision record 0035).

## File format

One JSON object per file, named after the clause (`np-11-replacement.json`):

| Key | Holds |
| --- | --- |
| `clause` | the clause identifier, such as `NP-11` |
| `also` | optional: other clauses the cases also bind, from any document |
| `document` | the file under `docs/spec/` |
| `version` | the document version the vector was written against |
| `operation` | `pool`, `next_base_fee`, `intrinsic_gas`, `frame_gas`, `ticket_fee`, `surface` or `replay` |
| `distinguishes` | one sentence: what a failure here would mean |
| `cases` | a list of cases |

`scripts/check_vectors.py` checks that every vector names a clause that exists
in its document, and every clause marked normative has at least one vector.

### Operations other than `pool`

- `next_base_fee`: each case has `head` and `expect` (an integer), FEE-1.
- `intrinsic_gas`: each case has `tx` and `expect` with `intrinsic` and
  `floor`, FEE-3.
- `frame_gas`: each case has `tx` and `expect` with `intrinsic`, `floor`,
  `max_gas` and `max_cost`, FEE-4.
- `ticket_fee`: each case has `st`, `base_fee` and `expect` with `can_pay` and
  `cost`, and, if it can pay, `priority`, `tob` and `ticket_fee`, LU-3.

### The `surface` operation

A case drives one node's surface (`docs/spec/11-surface.md`) over a pool set
up as for `pool`, under the frame profile's surface parameters (SF-1). Case
keys: `profile`, `config` (with a `surface` part for SF-1's parameters),
`head`, `state` and `peers`, the node's peer names. Addresses are written as
the surface writes them, `0x` and 40 lowercase hexadecimal digits, and so is
the profile's `expiry_verifier`. Transactions are their bytes, as
`0x`-prefixed hexadecimal. For the inclusion-list steps, `focil` names the
IL-1 profile (`config` takes a `focil` part) and `txs` maps labels to bytes.

| Step | Does |
| --- | --- |
| `{"decode": bytes, "expect": {"result": r, "hash": h, "tx": {...}, "gas": {"max_gas": g, "max_cost": c}}}` | SF-2 and SF-3 alone: `ok` or the first failure; for `ok`, the chain's hash, the model transaction's fields (any subset; frames and signatures index by index; `null` expects the field absent) and FEE-4's gas |
| `{"verdict": answer, "expect": v}` | SF-4 alone: a client answer, `{"valid": true}` or `{"valid": false, "violation": text}`, and its verdict |
| `{"rpc": param, "client": answer, "as": name, "expect": {...}}` | SF-5: `param` sent over `eth_sendRawTransaction`; `client` is what the client answers if asked; the expectation names any of `result`, `hash`, `error_code`, `asked_client`, `relay_to` (sorted peer names) and `handed` (SF-9); `as` names the transaction for later steps |
| `{"peer": bytes, "from": p, "client": answer, "as": name, "expect": {...}}` | SF-7: the same from peer `p`, with `gossip` (`accept`, `ignore` or `reject`) and `disconnect` |
| `{"head": {...}, "state": {...}, "client": {name: answer, ...}, "expect_asked": [...], "expect_resimulated": [...], "expect_pending": [...]}` | SF-8: a new head, the state its step 1 reads merged over the last, and the client's answers by name; what was asked about, what FP-15 re-ran and what is pending, by name, in the order admitted |
| `{"il": {"base_fee": b}, "expect": [name, ...]}` | IL-2: the list the node builds from its pool for a block at `b`, by default the head's next base fee, by name |
| `{"inclusion": {"ils": [[label, ...], ...], "delivered": [...], "block": [...], "gas_left": g, "valid": [...]}, "expect_admitted": [...], "expect_omission": label}` | IL-4 and IL-6 at the node: the slot's ILs by `txs` label, the order delivered under `per-payload`, the labels a payload contains, the gas it left, and the labels a client finds valid at its end (IL-5); what the fill admitted, in the order first admitted, and the omission, `null` when the payload satisfies the ILs |

A case whose node would ask the client about a transaction for which the
step gives no answer fails: the vector did not expect the question.

A vector of this operation may carry `provenance`, saying where its bytes and
expected values come from when they are not written out by hand.

### The `replay` operation

Each case is one fixture under one profile (`docs/spec/12-replay.md`):
`profile` and `config` as for `surface`, and `fixture` with `raw`, the
bytes; `hash`, the chain's; `payer`, the receipt's; and `parent`, the
parent header's `number`, `timestamp`, `gas_limit`, `gas_used` and
`base_fee`, or `null` when it could not be read. `expect` names any of
`verdict`, `payer` (the pool's), `comparison` (`agree`, `explained`,
`disagree` or `not replayed`), `differences` (RP-5's names, in its order)
and `header` (`read` or `missing`).

### The `pool` operation

A case drives one pool, which is the account-nonce pool, the frame pool and
the sealed pool behind one shared reservation tracker, through a list of
`steps`:

| Case key | Default | Holds |
| --- | --- | --- |
| `profile` | `eip-8141` | the frame pool profile (FP-1, `matcha` of MA-1, `eip-8288` of AG-1, or `eip-8272` of RR-1); the nonce pool always uses `geth` |
| `sealed` | `off` | the sealed pool profile (LU-1): `off`, which refuses every sealed transaction, or `eip-8184` |
| `focil` | `off` | the inclusion-list profile (IL-1): `off`, `eip-7805` or `eip-8369` |
| `config` | `{}` | overrides, as `{"nonce": {...}, "frame": {...}, "sealed": {...}, "focil": {...}}` with the parameter names of NP-1, FP-1, MA-1, AG-1, LU-1, IL-1 and RR-1 |
| `head` | see below | the initial head |
| `state` | `{}` | the initial state, address to account fields (MD-2) |
| `roots` | `[]` | recent-root entries in the initial state, each `[source_address, salt, slot, root]` as a write of `root` at `slot` would leave it (RR-3); `root` `null` empties the entry |
| `steps` | | the steps |

| Step | Does |
| --- | --- |
| `{"add": [tx, ...], "now": t, "expect": [result, ...]}` | `add` at time `t` (default 0); each result is `ok` or an error code |
| `{"reset": {"head": {...}, "state": {...}, "roots": [...], "verdicts": {...}}, "now": t}` | `reset`; both objects are merged field by field over the previous head and state, `roots`, optional, is written over the state as the case key is, and `verdicts`, optional, maps a pending transaction's label to its verdict at the new head (MD-8) |
| `{"tick": t}` | `tick(t)` |
| `{"expect_pool": {"pending": {...}, "queued": {...}}}` | the pool's content, sender to labels in nonce order; senders not listed hold nothing |
| `{"expect_view": {"min_tip": m, "base_fee": b}, "expect": [label, ...]}` | the builder's view, flattened in BB-2 order |
| `{"expect_resimulated": [label, ...]}` | the frame transactions re-simulated by the last reset (FP-15) |
| `{"build": {"min_tip": m, "coinbase": c, "dimensions": d, "drop_reverting": r}, "expect": [label, ...], "expect_gas_used": g, "expect_commitments": [label, ...], "expect_decrypted": [label, ...]}` | build a block (BB-1 to BB-4), apply it, and reset the pool to it; `dimensions`, optional, is BB-6's rule, `one` or `two`, `one` by default; `drop_reverting`, optional, is BB-7's variant, false by default; `expect_gas_used`, optional, is the block's gas used with AG-8's charge, under `two` the larger of its two sums; `expect_commitments` and `expect_decrypted`, optional, are the sealed transactions it commits (LU-12) and the previous build's commitments it executes (LU-13), in order |
| `{"il": {"base_fee": b}, "expect": [label, ...]}` | the IL an includer holding this pool lists (IL-2), in order; `base_fee` defaults to the pending one |
| `{"build": {..., "slot": s}, "expect_failed": [[label, error], ...]}` | a build at slot `s`, which defaults to the head's plus one (RR-2); `expect_failed` lists the transactions BB-5 failed, in order, each with its error (RR-8) |
| `{"build": {..., "ils": [[tx, ...], ...], "skip": [sender, ...]}, "expect_omission": label or null, "expect_canonical": c}` | a build with the slot's ILs (IL-7), by a builder that leaves the named senders' transactions out of its block and does not append them; `expect_omission` is IL-6's omission, and a block with one is not canonical (IL-8): the head, the state and the pool stay as they were |
| `{"expect_selection": {"base_fee": b, "min_tip": m}, "expect": [label, ...]}` | the selection over the sealed pool (LU-7), in commitment order; `base_fee` defaults to the pending one and `min_tip` to 0 |
| `{"expect_state": {...}}` | account fields of the current state |
| `{"finalize": [{"number": n, "gas": {sender: g, ...}}, ...], "now": t}` | `finalize` (MD-8): the blocks that became final, each with its frame gas by sender |
| `{"expect_width": {sender: w, ...}}` | the width of each listed sender (`04-matcha.md`, MA-12) |
| `{"expect_baseline": {sender: label or null, ...}}` | the baseline of each listed sender, or none (MA-12) |
| `{"expect_baselines": {sender: [label, ...], ...}}` | the pending baselines of each listed sender, in the order admitted (MA-12) |
| `{"expect_load": {sender: l, ...}}` | the load of each listed sender, the charges of its pending additional transactions (MA-12, MA-13) |
| `{"wrapper": {...}, "now": t, "expect": code or [result, ...]}` | a wrapper received at time `t` (AG-5, AG-6): a code refusing the whole wrapper, or one result per transaction |
| `{"aggregate": {}, "expect": [label, ...] or null, "expect_hashed": [label, ...], "expect_deps": [triple, ...], "expect_time": ms, "expect_memory": MiB}` | the node's aggregate for this interval (AG-7): its transactions in order, or `null` for none; those sent as hashes; its sorted deps; its proving time (AG-9); its memory (AG-10) |

A wrapper is `{"mode": m, "txs": [...], "deps": [...], "proofs": [...],
"stark": {"covers": [...], "valid": v}}`. An entry of `txs` is a transaction,
or `{"hash": tx}` for a transaction sent by hash, whose hash is that of the
transaction written out. A triple, in a frame's `deps` or a wrapper's, is
`[scheme, data_hash, vk_hash]`, with scheme 16 for leanSPHINCS and 17 for
leanSTARK (EIP-8288, Constants).

Transactions are referred to by `label`, which is part of their identity (MD-7).
Several frame transactions from one sender, which only `disjoint-keys` and
`matcha` admit, have no nonce order between them; `expect_pool` lists them in
the order the pool admitted them, and vectors avoid depending on it otherwise.

### Defaults

So that a vector shows only what it is about, every field has a default:

- head: `number` 0, `timestamp` 1000, `gas_limit` 30000000, `gas_used`
  15000000, `base_fee` 10, `slot` 0, so the pending base fee is 10;
- account-nonce transaction: `type` 2, `nonce` 0, `gas` 21000, `max_fee` 100,
  `tip` 10, `value` 0, `to` `sink`, `data_size` 0, `size` $110 + \mathit{data\_size}$,
  `authorities` empty, `valid_signature` true, `gas_used` equal to `gas`,
  `state_gas_used` 0, `writes` and `root_writes` empty, `pulls` and
  `pays` empty, `atomic` true and `revert_gas_used` equal to `gas_used`;
  its cost is 2100000;
- frame transaction (`type` 6): `nonce_keys` `[0]`, `nonce_seq` 0, `max_fee`
  100, `tip` 10, `signatures` `[{"scheme": "secp256k1"}]`, `state_gas_used`
  the sum of its frames' `state_gas` (MD-6), `writes` and `root_writes`
  empty, `zero_bytes` 0 and no `verdict`;
- sealed transaction (`type` `st`, LU-2): `sender` `alice`, `nonce` 0,
  `max_fee` 100, `tip` 10, `gas_limit` 100000, `max_tob_fee` 0,
  `max_preceding` 31, `key_publisher` and `fee_recipient` `kp`, `key_fee` 0,
  `size` 512, `signature_id` 1, `valid_signature`, `ciphertext_ok` and
  `revealed` true, `used` equal to `gas_limit`, no `to`, `pulls` and `pays`
  empty, `atomic` true and `revert_used` equal to `used`; its cost is
  10000000;
- frame: `flags` 0, no `target`, `exec_gas` 0, `state_gas` 0, `value` 0,
  `data_size` 0, no `approves`, `reverts` false, empty `opcodes`, `reads`,
  `writes` and `calls`, no `installs_code`, no `deadline`, empty `deps`,
  empty `roots`, whose entries are `[source_id, slot, root]` with a source
  id written `address/salt` (RR-3, RR-4);
- signature: no `signer`, `canonical_msg` true, `valid` true, `length` 0;
- wrapper: `deps` the sorted union of its transactions' dependencies,
  `proofs` all true (mode 0), and a `stark` that covers `deps` and is valid
  (mode 1), so that a vector writes only the part of a wrapper that is
  wrong.

`reads` entries are `[address, slot, expected]` with `expected` possibly `null`;
`writes` entries are `[address, slot, value]`, `pulls` and `pays` entries
`[account, amount]` (MD-5), and `root_writes` entries
`[source_address, salt, root]`, the address the transaction's execution
writes the root from (RR-3).
