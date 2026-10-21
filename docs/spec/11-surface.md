# 11. The surface: real frame transactions in and out of the pool

Version 4, 2026-10-21. Version 1 did not decode a recent-root verifier frame's
tuples; version 2 did not read a claim; version 3 did not read whether a
claim is bound to its transaction; see the version notes at the end.

The model has no RLP, no signatures and no EVM (`00-model.md`). This document
specifies the layer around a frame pool that a node needs to take real
transactions: the bytes a type `0x06` transaction arrives as, the hash the
chain knows it by, the outcome of its validation prefix taken from an
execution client, the answer it gives over JSON-RPC, and what it relays to
peers and accepts from them. The pool's own clauses are unchanged; the
surface feeds them and carries their results out. It is the plan's item 42,
and decision record 0051 has the readings it rests on.

It was read from:

- EIP-8141 and EIP-8250 at ethereum/EIPs `258836f9`: "Payload Encoding",
  "Constraints", "Gas Accounting", "Mempool" ("Acceptance Algorithm",
  "Replacement and Eviction"), "Networking" and "Security Considerations"
  of EIP-8141, and "Transaction payload" of EIP-8250;
- go-ethereum at `93d78a01`: `internal/ethapi/api.go` (`SendRawTransaction`),
  `core/types/transaction.go` (`UnmarshalBinary`, `decodeTyped`),
  `core/txpool/validation.go` (`ValidateTransaction`),
  `core/txpool/legacypool/legacypool.go` (`txMaxSize`), `eth/handler.go`
  (`BroadcastTransactions`), `eth/handler_eth.go` and
  `eth/fetcher/tx_fetcher.go` (`Enqueue`);
- libp2p's gossipsub v1.1 specification at libp2p/specs `c750236d`,
  "Extended Validators";
- ethrex at `64b8fc09`, the commit the Hegota testnet runs since 2026-10-07:
  `crates/networking/rpc/ethrex.rs` (`ethrex_simulateFrameTransaction`),
  `crates/vm/levm/src/validation_observer.rs` (`FrameSimViolation`) and
  `crates/vm/backends/levm/mod.rs` (the verdict's text).

## Profiles

**SF-1. Parameters.** The surface's parameters, by the frame pool profile
of FP-1:

| Parameter | `eip-8141` | `hegota-testnet` | Note |
| --- | --- | --- | --- |
| `envelope` | `keyed` | `keyed` | `keyed` is EIP-8250's payload, `[chain_id, nonce_keys, nonce_seq, sender, frames, signatures, fees, blob_versioned_hashes]`; `plain` is EIP-8141's own, with one `nonce` where the two fields are, which ethpandaops' frames-devnet-0 carries (`exp-frames`, README, "Network") |
| `chain_id` | 1 | 8141 | *Interpretation*: the EIP fixes no chain; 1 is the chain of ethrex's golden vector; the testnet's is 8141 |
| `max_tx_size` | 131072 | 131072 | go-ethereum's `txMaxSize`, $4 \cdot 32768$ bytes; the testnet's own limit was not read, so this is *Interpretation* for it |
| `relay` | `eth` | `eth` | how a node relays (SF-6): `eth`, go-ethereum's broadcast and fetcher, or `gossipsub`, a libp2p topic; skandha relays between its own nodes over `gossipsub` (decision record 0051) |
| `handoff` | false | false | whether the node hands what it admits to an execution client's pool (SF-9); set per node |

## Errors

| Code | Raised by | Name from |
| --- | --- | --- |
| `ErrTxTypeNotSupported` | SF-2 | go-ethereum `core.ErrTxTypeNotSupported` |
| `ErrOversizedData` | SF-2 | go-ethereum `txpool.ErrOversizedData` |
| `ErrFrameDecode` | SF-2 | this repository |
| `ErrFrameBlobs` | SF-2 | this repository |
| `ErrFrameMalformed` | SF-2 | FP-3's code, for the EIP's "Constraints" |
| `ErrInvalidChainId` | SF-2 | go-ethereum `types.ErrInvalidChainId` |
| `ErrFrameClientRefused` | SF-4 | this repository |

The pool's own codes (FP-2 to FP-14) are returned as the pool gives them.

## Bytes in

**SF-2. Decoding.** A node MUST take a frame transaction as the bytes
$\mathtt{0x06} \Vert \mathit{rlp}(\mathit{payload})$ and MUST check, in
order, returning the first failure:

1. `ErrTxTypeNotSupported` if there are no bytes or the first is not `0x06`.
   A node with no account-nonce pool refuses types 0 to 4 this way, as
   go-ethereum refuses a type a subpool does not accept.
2. `ErrOversizedData` if there are more than `max_tx_size` bytes.
3. `ErrFrameDecode` unless the rest is exactly one RLP list in canonical
   form, with nothing after it, of the envelope's 8 items (`keyed`) or 7
   (`plain`), each of its field's kind: every integer a byte string with no
   leading zero byte, a single byte below `0x80` written as itself and zero
   as the empty string; every byte field a byte string; `frames` a list of
   6-item lists, each frame's `limits` a 2-item list of integers,
   `signatures` a list of 4-item lists, `fees` a 3-item list of integers,
   `nonce_keys` and `blob_versioned_hashes` lists. Canonical form also means
   every length in its shortest encoding.
4. `ErrFrameBlobs` if `blob_versioned_hashes` is not empty. *Not modelled*:
   a blob-carrying frame transaction travels with its EIP-7594 sidecar
   ("Networking"), and the surface carries no blobs.
5. `ErrFrameMalformed` if a decoded field breaks one of EIP-8141's
   "Constraints" or EIP-8250's payload rules that FP-3 does not check
   itself: `nonce_seq`, or the `plain` envelope's `nonce`, at least $2^{64}$;
   a nonce key, `chain_id`, a fee or a frame's `value` at least $2^{256}$;
   `sender` not 20 bytes; a `target` neither empty nor 20 bytes; a frame
   limit, or the sum of every frame's two limits, at least $2^{64}$; a
   `scheme` other than 0, 1 or 2; a `signer` neither empty nor 20 bytes, or
   not empty for scheme 0; a `msg` neither empty nor 32 bytes, or 32 zero
   bytes; `max_fee_per_blob_gas` not 0.
6. `ErrInvalidChainId` if `chain_id` is not the profile's.

*Interpretation*, decision record 0051: go-ethereum decodes before it checks
the size, and a transaction that fails both gets the decoding error there and
`ErrOversizedData` here. Splitting a failure to parse (step 3) from a parsed
field out of range (step 5) is this repository's: the first says the bytes
are not a frame transaction, the second that a frame transaction is invalid,
which SF-7 treats differently. **Source:** EIP-8141, "Payload Encoding" and
"Constraints"; EIP-8250, "Transaction payload" ("Each nonce key and
`nonce_seq` MUST be encoded as canonical minimal-length RLP integers");
go-ethereum `core/types/transaction.go`, `decodeTyped`, and
`core/txpool/validation.go`, `ValidateTransaction`.

**SF-3. The model transaction.** A transaction that passes SF-2 MUST be
handed to the pool as the MD-6 frame transaction below. Fields not listed
take their defaults.

| Model field | Taken from |
| --- | --- |
| `sender` | `sender`, written `0x` and 40 lowercase hexadecimal digits |
| `nonce_keys`, `nonce_seq` | the two fields; under `plain`, `(0,)` and `nonce` |
| `frames` | one frame for each: `mode`, `flags`, `value` as they are; `target` absent when empty and written as `sender` is otherwise; `exec_gas` and `state_gas` from `limits`; `data_size` the length of `data`; `deadline`, for a frame whose target is the profile's `expiry_verifier` and whose `data` is 8 bytes, those bytes as a big-endian integer; and `roots`, under a profile with `recent_roots` (RR-1), for a frame whose target is `recent_root_address` and whose `data` is a whole number of 72-byte tuples, one entry for each, `source_id(32) || uint64_be(slot) || root(32)`, with the source id and the root written `0x` and 64 lowercase hexadecimal digits and the slot as an integer |
| `signatures` | one for each: `scheme` 0 `arbitrary`, 1 `secp256k1`, 2 `p256`; `signer` absent when empty; `canonical_msg` true when `msg` is empty; for `arbitrary`, `length` the length of `signature`; `valid` false for a `secp256k1` signature that is not 65 bytes or a `p256` one that is not 128, which the acceptance algorithm's step 2 calls malformed, and true otherwise |
| `tip`, `max_fee` | `max_priority_fee_per_gas`, `max_fee_per_gas` |
| `size` | the number of bytes received |
| `zero_bytes` | the zero bytes among every frame's `data`, every signature's `signer`, `msg` and `signature`, and $\mathit{rlp}(\mathit{nonce\_keys}) \Vert \mathit{rlp}(\mathit{nonce\_seq})$, which are FEE-4's $D$ |
| `label` | the transaction's hash |
| `verdict` | SF-4 |
| `claim` | under a frame profile with `claims` (CG-1), CG-10's claim, with the code at the pool's head of each `VERIFY` frame's target as the execution client answers it (`eth_getCode`): its `sender` written as above, `nonce_keys` and `nonce_seq` the transaction's, `epoch` and `salt` (`0x` and 64 lowercase hexadecimal digits) from the ticket's frame, `binder` from a bound ticket paymaster's frame, written as `sender` is, `valid` by CG-9, and `bound` by CG-12 over the signature hash of the bytes received; a ticket's frame whose data is not of its paymaster's length, 168 or 188 bytes, gives `epoch` 0, an empty `salt`, no `binder` and `valid` and `bound` false; absent when no frame carries a ticket, and under any other profile |

The transaction's **hash** is $\mathit{keccak256}$ of the bytes received,
the hash the chain gives it, and it is the hash FP-2, MD-8's `verdicts` and
every answer of this document use. Two byte strings that differ anywhere,
in a signature's bytes for instance, are two transactions, as on chain.
**Source:** EIP-2718, "the transaction hash is `keccak256(TransactionType ||
TransactionPayload)`"; EIP-8141, "Field Definitions" and "Gas Accounting".

The `claim` is read with the code the execution client answers at the
pool's head because MD-2's `code` is compared by equality only, and a node
that does not execute the EVM has no other reader of a real account's code.
A node may keep, by address, each target whose code it found to be a ticket
paymaster's, and read every other target again at each head: outside the
transaction that created a contract, `SELFDESTRUCT` "does not delete any
data (including storage keys, code, or the account itself)" (EIP-6780), and
EIP-7702 sets code only where the code "is empty or already delegated", so
such code changes only in a reorganisation. A ticket paymaster then costs a
node one `eth_getCode` and one G2 decoding. *Interpretation*, decision
record 0058.

*Not modelled*: the cryptographic check of a signature, which reaches the
pool only through the verdict (SF-4); and a dependency frame's triples
(AG-2), which no profile of this document reads, so such a frame is an
ordinary frame of its mode and the verdict carries its outcome. A
recent-root verifier frame's tuples are decoded (above), and the verdict
stands for their check against the contract's entries (RR-6).

## The validation prefix

**SF-4. The client's verdict.** A node that does not execute the EVM MUST
take the outcome of a transaction's validation prefix from an execution
client that does, simulated against the pool's head, and MUST record it as
the transaction's `verdict` before `add`. It MUST NOT ask the client about a
transaction that SF-2 or FP-2 to FP-7 refuse, or, under a frame profile with
`claims`, that CG-2, with CG-12 under `binding`, CG-4 or CG-6 refuse after
FP-6: those checks read no
state except the sender's nonce sequences and the code SF-3's `claim` reads,
and the EIP asks a node to "perform all available structural and stateless
checks before sender-state access". Running CG-2, CG-4 and CG-6 before the
client is this repository's: a junk ticket then costs a node one signature
check and no simulation (*Interpretation*, decision record 0058). The
client's answer maps to a verdict as follows, matching an answer of the form
`Name(...)` by its name:

| Client's answer (ethrex `ethrex_simulateFrameTransaction`) | `verdict` |
| --- | --- |
| `valid` true | `ok` |
| `BannedOpcode(...)` | `ErrFrameBannedOpcode` |
| `StateWriteOutsideDeploy` | `ErrFrameStateWrite` |
| `StorageReadNonSender` | `ErrFrameStorageReadNonSender` |
| `CallToNonexistentOrDelegated(...)` | `ErrFrameCallTarget` |
| `DeployInstalledNoCode` | `ErrFrameDeployNoCode` |
| `validation prefix frame reverted` | `ErrFramePrefixReverted` |
| `validation prefix did not establish a payer` | `ErrFrameMissingApprove` |
| `frame signature list does not authenticate the sender` | `ErrInvalidSender` |
| anything else | `ErrFrameClientRefused` |

The node MUST keep the client's text with an `ErrFrameClientRefused`, and
SHOULD with every other refusal, so that a disagreement can be read later.
The client MUST be asked at the pool's head, named by its hash or number,
not at whatever it calls latest, so that the verdict and the state the pool
reads belong to one head. **Source:** EIP-8141, "Acceptance Algorithm", step
4, and "Explicit Sender State-Read Amplification"; ethrex `64b8fc09`, the
`FrameSimViolation` variants, written with Rust's `Debug` format, and the
three fixed strings of `crates/vm/backends/levm/mod.rs` and
`crates/networking/rpc/ethrex.rs`. *Interpretation*, decision record 0051:
the table is this repository's reading of one client's answers; ethrex's
simulation also runs gates FP-3 to FP-6 already ran, so an answer from those
gates means the client's parameters differ from the profile's, and it maps
to `ErrFrameClientRefused`.

## Answers out

**SF-5. `eth_sendRawTransaction`.** A node MUST take a frame transaction over
JSON-RPC's `eth_sendRawTransaction`, whose one parameter is the bytes as
`0x`-prefixed hexadecimal; a parameter that is not is an invalid-params error
(code -32602). The node applies SF-2, the checks of FP-2 to FP-7, SF-4 and
then `add`. On `ok` it MUST return the hash (SF-3) as `0x` and 64 lowercase
hexadecimal digits, and relay the transaction (SF-6). On a refusal it MUST
return an error with code -32000 whose message begins with the error code,
and MUST NOT relay. **Source:** go-ethereum `internal/ethapi/api.go`,
`SendRawTransaction`, which decodes, adds and returns `tx.Hash()`; -32000 is
go-ethereum's code for an error that carries none of its own.
*Not modelled*: go-ethereum's `RPCTxFeeCap` and its EIP-155 check, which have
no frame-transaction counterpart.

## Peers

**SF-6. Relay.** A node MUST relay to its peers every frame transaction that
`add` answers `ok`, whether it came over JSON-RPC or from a peer, as the bytes
it received, to every peer not known to have it, and never to the peer it came
from. It MUST NOT relay a transaction that SF-2, SF-4 or `add` refused, nor
one it already holds (`ErrAlreadyKnown`), and MUST NOT relay again a
transaction it replaced or evicted; one it admits again later, received
again, is relayed again. Under `relay` `eth`, a node pushes the transaction
to $\lceil \sqrt{n} \rceil$ of its $n$ peers and announces its hash to the
others, and only announces a transaction over 4096 bytes. Under `gossipsub`,
it publishes the bytes as one message on the topic
`/frame-transactions/<chain_id>/raw`, `<chain_id>` in decimal, and the
router's mesh does the pushing and its gossip the announcing. **Source:**
EIP-8141, "Acceptance Algorithm" step 8 ("accepted into the public mempool
and propagated to peers"), "Replacement and Eviction" ("Evicted and replaced
transactions must not be re-propagated. Re-admission requires receiving the
transaction again"), and "Mempool" ("Transactions outside these rules ...
must not be propagated through the public mempool"); go-ethereum
`eth/handler.go`, `BroadcastTransactions` and `txMaxBroadcastSize`.
*Interpretation*, decision record 0051: the topic name and its message.

**SF-7. A transaction from a peer.** A node MUST put a transaction a peer
sends through the same steps as one from JSON-RPC (SF-5), and then:

| Outcome | The peer | Relayed (SF-6) | Under `gossipsub` |
| --- | --- | --- | --- |
| `ok` | nothing | yes | accept |
| `ErrTxTypeNotSupported` or `ErrFrameDecode` | at fault: under `eth` disconnected | no | reject |
| any other refusal, `ErrAlreadyKnown` included | nothing | no | ignore |

A node MUST NOT count a well-formed transaction it refuses against the peer
that sent it: an honest peer that admitted it may have done so at another
head, or under another profile. **Source:** go-ethereum
`eth/handler_eth.go`, where a `Transactions` or `PooledTransactions` message
that does not decode ends the peer's session, and
`eth/fetcher/tx_fetcher.go`, `Enqueue`, where a pool's refusal disconnects
no one; gossipsub v1.1, "Extended Validators" ("Accept message ... delivered
and forwarded"; "Reject message ... trigger the P4 penalty"; "Ignore message
... neither delivered nor forwarded ... does not trigger the P4 penalty").
*Interpretation*, decision record 0051: `ErrFrameMalformed`,
`ErrInvalidChainId`, `ErrOversizedData` and `ErrFrameBlobs` are a pool's
refusals in go-ethereum and are treated as such here. *Not modelled*:
go-ethereum's 200 ms pause when more than a quarter of one delivery is
refused, and its memory of underpriced hashes (decision record 0004).

## Head changes

**SF-8. A new head.** When its client reports a new canonical head, a node
MUST, before the next `add`:

1. read at the new head its `slotNumber`, which is the head's `slot`
   (RR-2), and, for every pending transaction, its sender's sequence for
   each of its nonce keys, its sender's and its payer's balance and code,
   and the code at `expiry_verifier` if it has an expiry frame;
2. ask the client for a verdict at the new head for every pending
   transaction that step 1 does not show included, that is, none of whose
   nonce keys has a sequence above its `nonce_seq` (SF-4);
3. `reset` the pool with the head, a state holding what step 1 read, and
   the verdicts of step 2 (MD-8).

FP-15 then removes what was included or expired and re-runs FP-7 to FP-10
for every transaction whose verdict or read dependency changed.
*Interpretation*, decision record 0051: ethrex's simulation records the
sender slots a prefix touched (`touched_sender_slots` in its validation
observer) but `ethrex_simulateFrameTransaction` does not return them, so a
surface cannot index a transaction by the slots it read and asks the client
about every pending transaction still pending at every head. The pool's re-simulations are
still FP-15's; the client's work is one simulation per pending transaction
per head, the work FP-15 says a node should not spend, and the cost of
keeping the EVM outside the pool. *Not modelled*: a canonical paymaster's
`withdrawal`, which the surface does not read and which reaches the pool
only through the verdict.

## Handing on

**SF-9. Hand-off.** A node whose `handoff` is true MUST send every
transaction its pool admits, as the bytes it received, to its execution
client's `eth_sendRawTransaction`, and MUST record the client's answer with
the hash. A client's refusal of a transaction the pool admitted at the same
head is a disagreement between two pools and MUST be recorded as one; the
node keeps the transaction, because its own clauses admitted it. A node whose
`handoff` is false hands nothing on, and reaches a block only through peers.
*Interpretation*, decision record 0051: a node that does not build blocks
reaches a builder through a client's pool; the parameter exists so that a
run can show a transaction reaching the chain through a second node rather
than the one it was sent to.

## Run procedure

What cannot be stated offline, a client's verdict on a real prefix and a
transaction reaching a block, is checked by a run, recorded as the plan's
item 42 asks. A run passes or fails on these steps:

1. Two nodes, A and B, each with a pool under the `hegota-testnet` profile,
   peers of each other and of no one else, both asking the same execution
   client of the Hegota testnet for verdicts and state; A with `handoff`
   false, B with `handoff` true.
2. A transaction that the profile admits at the current head, signed with a
   key held in the environment and never written down, is sent to A alone
   over `eth_sendRawTransaction`.
3. Recorded with the implementation's commit and the command: A's answer;
   whether and when B received the transaction from A, and B's outcome; B's
   hand-off answer; the transaction's hash, block and receipt from the chain.
4. The run passes when A answers the hash of the bytes, B received the
   transaction from A and admitted it, the client answered B with the same
   hash, and the chain included it.
5. A and B answering differently at the same head is the result the plan's
   item 42 names as the one that would show its claim wrong, and is
   reported as such, whatever else the run shows.

## Version notes

- **Version 1.** First version: SF-1 to SF-9 and the run procedure.
- **Version 2.** SF-3 decodes a recent-root verifier frame's tuples into
  `roots` under a profile with recent roots, which `hegota-testnet` now is
  (`08-recent-roots.md` version 2), and SF-8 takes the head's slot from
  the header's `slotNumber`, which differs from the block number on the
  testnet. A transaction with no frame to `recent_root_address` decodes as
  under version 1 (decision record 0053).
- **Version 3.** SF-3's model transaction carries a `claim` under a frame
  profile with `claims` (`10-claim-gated-admission.md` version 4, CG-10),
  read with the code the execution client answers for each `VERIFY`
  frame's target; SF-4 runs CG-2, CG-4 and CG-6 before it asks the client,
  so a junk ticket is refused at the cost of a signature check. Under every
  profile without `claims` nothing changes, and every vector of version 2
  holds and now says version 3. *Interpretation*, decision records 0057
  and 0058.
- **Version 4.** SF-3's `claim` gains a `binder`, read from a bound ticket
  paymaster's frame, and `bound`, CG-12's verdict
  (`10-claim-gated-admission.md` version 6): the transaction's signature
  hash is computed from the bytes received, as EIP-8141's
  `compute_sig_hash` defines it, and the binder's `secp256k1` signature is
  checked over it before the client is asked. A claim read from a ticket
  paymaster's 168 bytes has no binder and is not bound. Every vector of
  version 3 holds and now says version 4, its claims with `bound` false
  where they come from a ticket; SF-3 and SF-5 gain a bound ticket and a
  copy of it with a higher priority fee, which SF-5 refuses before the
  client is asked (decision record 0067).
