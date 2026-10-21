# The specification: expected mempool behaviour

This directory is the normative half of the repository. It states what a
transaction pool does, clause by clause, and every clause names the primary
source it was read from. The reference implementation in `ref/python/` exists
to show the clauses are implementable and unambiguous, and the hand-written
vectors in `conformance/vectors/` bind the two together. When the code and a
clause disagree, the clause is what is wrong until a decision record says
otherwise.

| Document | Clause prefix | What it specifies | Read from |
| --- | --- | --- | --- |
| `00-model.md` | `MD`, `FEE` | The objects every other document talks about: accounts, heads, transactions with the state gas they use (version 7), the value they pull from accounts that signed for it (version 8), and their zero calldata bytes and a client's verdict on their prefix (version 9), an account's stake and a slot's association (version 10), a dependency frame's mode by profile (version 11), the pool interface, fee arithmetic | EIP-1559, EIP-8141, EIP-8037, ERC-3009, ERC-8421, go-ethereum |
| `01-nonce-pool.md` | `NP` | The account-nonce pool for transaction types 0, 1, 2 and 4: admission, replacement, promotion, limits, eviction, head changes | go-ethereum `core/txpool` at `93d78a01` |
| `02-frame-pool.md` | `FP` | The EIP-8141 public mempool for frame transactions, with EIP-8250 keyed nonces | ethereum/EIPs at `258836f9` |
| `03-block-building.md` | `BB` | How a builder takes transactions out of the pools, the minimal state transition the model needs, EIP-8037's two gas dimensions as the rule `two` (BB-6, version 3), and a transaction that reverts, included or dropped (BB-5 and BB-7, version 4) | go-ethereum `core/txpool/txorder`, `miner`, `core/gaspool.go`, `core/state_transition.go` at `93d78a01`; EIP-8037 and EIP-8141 at `258836f9` |
| `04-matcha.md` | `MA` | A proposal: MATCHA, several pending frame transactions per sender paid for with width earned from finalized gas, and a baseline per contention class | ethresear.ch topic 25949 (2026-09-08), read 2026-10-07 and 2026-10-09, with topic 25934 |
| `05-aggregation.md` | `AG` | EIP-8288 as a layer on the frame pool: dependency frames, wrappers, the proofs a node keeps, its aggregate every interval, the block's charge for declared dependencies, an aggregate's proving time under a budget (AG-9, version 2), its memory under a budget (AG-10, version 3), and the EIP on master as a second profile, `eip-8288-master`, with leanSTARK reserved (version 4) | ethereum/EIPs at `258836f9`; for `eip-8288-master`, master at `899bef0a` |
| `06-lucid.md` | `LU` | EIP-8184's sealed transactions as a third subpool: the ticket's fees, admission, the commitment order, what a builder commits, the key round between the two blocks (the commitment, the key message, its release, the committee's vote and its tally), and the next block's decrypted transactions, what they pull and pay, and refunds (version 3) | ethereum/EIPs at `258836f9` |
| `07-focil.md` | `IL` | EIP-7805's inclusion lists as a constraint on the builder, with EIP-8369's profiles for which transactions can be enforced, and the budget fill per list or per payload | ethereum/EIPs at `258836f9`; ethrex at `64b8fc09`; consensus-specs at `d9663f85`; execution-apis at `e4ba6c4f` |
| `08-recent-roots.md` | `RR` | EIP-8272's recent roots on the frame pool: slots, root writes, the verifier frame's shape and admission, its dependencies, eviction when a root leaves the window, and the block's own check; under `eip-8272` and, since version 2, `hegota-testnet` | ethereum/EIPs at `258836f9` |
| `09-expiring-nonces.md` | `EN` | EIP-8266's expiring nonces on the frame pool, composed with EIP-8250 as a reserved key: the consumed hashes, the mode, the deadline in place of the nonce, the charge at payment, several pending per sender, and the block's own check | ethereum/EIPs at `258836f9`, unchanged at `af80fc1c` |
| `10-claim-gated-admission.md` | `CG` | A proposal: claim-gated admission on the EIP-8288 frame pool, a claim per sender, sequence number and epoch checked with the signature before any proof, what a node remembers after a proof fails, relays that verify no proof, and the ticket behind a claim: the bytes an issuer signs, a BLS12-381 signature over them, and the frame that carries it to a ticket paymaster, recognised by its code (versions 3 and 4); a bond on the ticket paymaster, ERC-8421's stake and reputation (version 5); and a ticket bound to its transaction through a one-time key (version 6), with `exp-frames` experiment 48's bound template (version 7) and the holder's re-pricing under it (version 8) | a proposal of this repository (decision records 0037, 0038, 0056, 0057, 0064, 0067, 0069 and 0080); for the bond, ERC-8421 as `14-erc-8421.md` reads it; for the binding, EIP-8141 at `258836f9`; for tickets, EIP-8250 and EIP-2537 at `258836f9`, RFC 9380, draft-irtf-cfrg-bls-signature-05 and Commonware at `c18a6b9c` |
| `11-surface.md` | `SF` | The layer around a frame pool that takes real transactions: decoding a type `0x06` transaction, its hash, the claim its ticket carries (version 3), the validation prefix's outcome from an execution client, `eth_sendRawTransaction`, relay to peers and what is accepted from them, head changes and hand-off to a client | EIP-8141 and EIP-8250 at `258836f9`; go-ethereum at `93d78a01`; gossipsub v1.1 at libp2p/specs `c750236d`; ethrex at `64b8fc09` |
| `12-replay.md` | `RP` | A procedure, not pool behaviour: a profile's verdict on a transaction a chain mined, from its bytes, its receipt's payer and its parent header, the chain's outcome, and the differences between profile and chain named before any replay | `11-surface.md`, `02-frame-pool.md`; `exp-frames`' fixtures; ethrex's divergence ledger at `64b8fc09` |
| `13-descriptors.md` | `DS` | A proposal: a ruleset as a file a node loads, with a canonical encoding, a content identifier, rule modules named as their sources name them, inheritance from a parent, and refusals that name the descriptor and the rule; three descriptors in `descriptors/`; the bond's module since version 2, and the binding's since version 3 | ERC-8421 at ERCs pull request 2028, `493ba8ac`; RFC 8785; multiformats `cid`, `multicodec` and `multibase` (decision record 0060) |
| `14-erc-8421.md` | `AM` | ERC-8421's standard alternative mempool read into the model: entities and stake, per-entity budgets, `pre_verify` frames, storage association, keyed-nonce limits, solvency, reputation and blame, and what a fresh sender is asked for | ERC-8421 at ERCs pull request 2028, `493ba8ac` (Draft), read 2026-10-20 (decision record 0061) |

## How a clause is written

- A clause has an identifier (`NP-12`), a one-line title, a normative body
  using RFC 2119 keywords in capitals, and a **Source** line naming the file
  and function, or the EIP section, it was read from.
- A clause that this repository chose rather than read is marked
  **Interpretation**, says what the source leaves open, and names the decision
  record that settled it. An interpretation is a place a second implementation
  could reasonably differ, and the vectors for it say so.
- A clause marked **Not modelled** names behaviour of the source that the
  reference deliberately leaves out, so that nobody reads its absence as a
  claim that the behaviour does not exist.
- Clauses are numbered within a document and never renumbered. A clause that is
  withdrawn keeps its number with the word *Withdrawn* and the reason.

## Profiles

A pool's behaviour depends on parameters that differ between the
specification and the clients that implement it. A **profile** is a named set
of parameters. Each document lists its profiles in a table, and a vector names
the profile it was written against.

- `geth` (nonce pool): go-ethereum's `DefaultConfig`, as read at the pinned
  commit.
- `eip-8141` (frame pool): the constants and rules of the EIP text, as read at
  the pinned commit. This is the default for anything that claims to be "the
  frame transaction mempool".
- `hegota-testnet` (frame pool): what the ethrex Hegota testnet was observed
  to enforce, by `exp-frames` and by earlier measurements on the same
  testnet. It is a record of measurements with dates, not a specification,
  and decision record 0003 says why it is kept beside the specified profile
  rather than replacing it.
- `matcha` (frame pool): `eip-8141` with MATCHA's per-sender rule
  (`04-matcha.md`). It specifies a proposal, not a client and not an EIP,
  and decision record 0007 lists the readings it rests on. Its optional
  load floor, MA-13, is off in the profile and set by `load_price`
  (decision record 0022), and its classes, MA-14, are the post's, one a
  sender, until `contention` says `storage` or `slot` (decision record
  0026).
- `eip-8288` (frame pool): `eip-8141` with EIP-8288's dependency frames,
  wrappers and aggregation (`05-aggregation.md`). It specifies a Draft EIP,
  and decision record 0012 lists the readings it rests on; two of them,
  `cap_aggregates` and `forward_wrappers`, are kept as parameters so that an
  experiment can measure each.
- `eip-8184` (sealed pool): the constants and rules of EIP-8184's text, as
  read at the pinned commit, with a sealed pool beside the other two
  (`06-lucid.md`); the default sealed profile, `off`, refuses every sealed
  transaction. It specifies a Draft EIP that leaves the pool's admission
  policy open, and decision record 0014 lists the readings it rests on; the
  policy is kept as the parameter `policy`.
- `eip-7805` and `eip-8369` (inclusion lists): EIP-7805's constants and its
  check, which enforces the transaction types of the account-nonce pool
  only, and the same with EIP-8369's Profile 2, which enforces frame
  transactions whose prefix stays within its state surface
  (`07-focil.md`); the default, `off`, has no inclusion lists. EIP-8369 is
  Informational and asks a later Standards Track extension to restate its
  rules, so `eip-8369` specifies a proposal, and decision record 0018 lists
  the readings both rest on. `ethrex` is `eip-8369` with the budget fill
  ethrex runs, one budget for the payload in the order delivered (decision
  record 0055).
- `eip-8272` (frame pool): `eip-8141` with EIP-8272's recent roots
  (`08-recent-roots.md`). It specifies a Draft EIP that leaves
  `RECENT_ROOT_CODE` unset and the margin a node keeps to the node, and
  decision record 0023 lists the readings it rests on; the margin is the
  parameter `root_margin`, 0 in the profile.
- `eip-8266` (frame pool): `eip-8141` with EIP-8266's expiring nonces
  (`09-expiring-nonces.md`), composed with EIP-8250's keyed nonces as the
  reserved key the EIP's Rationale names, in a composition the EIP calls
  non-normative. It specifies a Draft EIP, and decision record 0030 lists the
  readings it rests on; whether a node takes the EIP's MAY and admits
  several pending transactions in the mode from one sender is the parameter
  `expiring_per_sender`, `many` in the profile.
- `claim-gated` (frame pool): `eip-8288` with the claim-gated admission of
  `10-claim-gated-admission.md`. It specifies a proposal of this
  repository, not a client and not an EIP, and decision record 0037 lists
  the readings it rests on; what a node remembers after a proof fails,
  whether a sender's signature covers its proofs, and whether a node
  verifies at all are the parameters `claim_memory`, `signed_proofs` and
  `verifies`, kept so that an experiment can measure each; decision record
  0038 has the readings behind a relay. Since version 5 it sets `bond`, a
  bond on the ticket paymaster with ERC-8421's stake and reputation at
  `erc-8421.json`'s values (decision record 0064); experiments that build
  their profile from `eip-8288` with `claims` alone run version 4's
  admission.
- Variants: an experiment may change one parameter of a profile and says so,
  as experiment 01 does with `per_sender`, experiment 03 with `reuse_balance`,
  experiment 04 with `evict_first`, experiment 05 with `expiry_margin`,
  experiment 06 with `cap_aggregates` and `forward_wrappers`, experiment 07
  with the sealed pool's `policy`, `evict_first` and `st_slots`, and
  experiment 08 with `max_verify_gas`, set per node, which is how
  ethereum/EIPs pull request 12301, open, reads it: a floor that every node
  admits, with headroom of each node's own above it (decision record 0016).
  Experiment 09 varies IL-1's `policy` (decision record 0018),
  experiment 11 FP-1's `static_first`, experiment 14 RR-1's
  `recent_root_length` and `root_margin` (decision record 0023), and
  experiment 21 EN-1's `expiring_per_sender` (decision record 0030).
  `reuse_balance`, `evict_first`, `expiry_margin` and `static_first` exist
  in `02-frame-pool.md` only to be varied: both FP-1 profiles set them to
  what the EIP says, or for `expiry_margin` to the reading version 1 took
  (decision records 0009, 0010, 0011 and 0020; MA-1 sets its own
  `reuse_balance`).
  LU-1's `evict_first` exists in `06-lucid.md` for the same reason
  (decision record 0015).

## Versioning

Every document carries a version number and the date it was last changed. A
vector names the version it was written against. Changing a clause's meaning
bumps the document version and is recorded in the log on the branch `plan`;
fixing a typo does not.

## Pinned sources

| Source | Commit | Read on |
| --- | --- | --- |
| ethereum/go-ethereum | `93d78a01abb7e04beed100b54cd84d2b3c0e859f` (2026-10-06) | 2026-10-07 |
| ethereum/EIPs | `258836f9185999e608aae534567a703079b14767` (2026-10-07) | 2026-10-07 |
| ethereum/ERCs | `c73cd77c8dc45b4774892d9501964d3203b6e566`, for ERC-3009 (Draft) | 2026-10-13 |
| libp2p/specs | `c750236de43cd8b246a824b377dfdb26bae686db`, gossipsub v1.1 | 2026-10-20 |
| lambdaclass/ethrex | `64b8fc09d47d7787eb1a4e3f082aa9e831dc5f8c`, the Hegota testnet's client since 2026-10-07 | 2026-10-20 |
| ethereum/consensus-specs | `d9663f85be248c4fd0ae95806da6070e17c2442b`, `specs/heze/inclusion-list.md` | 2026-10-20 |
| ethereum/execution-apis | `e4ba6c4fd2a6e5d770b262ca0fbfabfaee3b4e1f`, `src/engine/bogota.md` | 2026-10-20 |

`refs/refs.md` lists every other source, with what it was used for.
