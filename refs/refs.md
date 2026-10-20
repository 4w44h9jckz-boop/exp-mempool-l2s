# Sources

Every source a clause or a document relies on, with the commit or date read
and what it was used for. A sibling repository is listed as a pointer: what it
says is checked against the primary source before it is relied on.

## Primary sources

- **go-ethereum**, ethereum/go-ethereum at commit
  `93d78a01abb7e04beed100b54cd84d2b3c0e859f` (2026-10-06), read 2026-10-07 from
  a sparse clone. Files: `core/txpool/validation.go` (`ValidateTransaction`,
  `ValidateTransactionWithState`), `core/txpool/errors.go`,
  `core/txpool/reserver.go`, `core/txpool/legacypool/legacypool.go` (`Config`,
  `DefaultConfig`, `add`, `validateTx`, `checkDelegationLimit`,
  `validateAuth`, `isGapped`, `enqueueTx`, `promoteTx`, `removeTx`,
  `runReorg`, `reset`, `promoteExecutables`, `truncatePending`,
  `demoteUnexecutables`, `Pending`, `loop`), `core/txpool/legacypool/list.go`
  (`list`, `SortedMap`, `priceHeap`, `pricedList`),
  `core/txpool/legacypool/queue.go`, `core/txpool/legacypool/noncer.go`,
  `core/txpool/txorder/ordering.go`, `miner/worker.go` (`commitTransactions`,
  `fillTransactions`), `miner/miner.go` (`DefaultConfig`),
  `consensus/misc/eip1559/eip1559.go` (`CalcBaseFee`). Used for
  `docs/spec/01-nonce-pool.md`, `docs/spec/03-block-building.md`, FEE-1 to
  FEE-3. Read again at the same commit on 2026-10-07 for the simulator's
  gossip: `eth/handler.go` (`BroadcastTransactions`, `choosePeers`,
  `txMaxBroadcastSize`, the fetcher's `validateMeta`) and
  `eth/fetcher/tx_fetcher.go` (`Notify`, `Enqueue`, `handleAddErrors`,
  `isKnownUnderpriced`, the `txOnChainCache` update, `txArriveTimeout`,
  `maxTxUnderpricedTimeout`). Used for `sim/emem_sim/network.py` and decision
  record 0004. `validateAuth` read again at the same commit on 2026-10-09 for
  experiment 22: it counts an authority's pending and queued transactions
  and asks the reservation tracker, and reads no authorization's nonce.
  Read again at the same commit on 2026-10-08 for experiment 05:
  `core/txpool/txpool.go` (the `BlockChain` interface, whose `CurrentBlock`
  "returns the current head of the chain", and `New`) and
  `core/txpool/validation.go` (`ValidateTransaction` takes its fork rules at
  the head's number and time). Used for FP-8's reading of "the current block"
  and decision record 0011. Its `README.md` at the same commit, read
  2026-10-13, lists under Hardware Requirements a minimum of "CPU with 4+
  cores" and "8GB RAM", and a recommendation of "Fast CPU with 8+ cores"
  and "16GB+ RAM". Used for decision record 0041 and
  `bench/leanvm-memory/fit.py`.
- **EIP-8141, Frame Transaction**, Draft, ethereum/EIPs at commit
  `258836f9185999e608aae534567a703079b14767` (2026-10-07), read 2026-10-07.
  Sections: Constants, Frame Transaction, Constraints, Signature Validation,
  Expiry Verifier Frame, Behavior, Gas Accounting, Default code, `APPROVE`,
  Mempool (all subsections). Used for `docs/spec/02-frame-pool.md`, MD-6, FEE-4.
- **EIP-8250, Keyed Nonces for Frame Transactions**, Draft, same commit, read
  2026-10-07. Sections: Mempool, Rationale. Used for FP-7 and FP-12. Read
  again the same day for experiment 02: Constants
  (`KEYED_NONCE_FIRST_USE_STATE_GAS`, 97920 under EIP-8037's current
  constants), Transaction payload (the nonce fields priced as data, which
  FEE-4 version 2 now does) and the payment-scoped `APPROVE` transition (state
  gas only). Used for FEE-4 and decision records 0006 and 0007. EIP-8141 at
  the same commit was read again for `calldata_cost`, `floor_tokens_in` and
  the floor (section Gas Accounting) and the expiry verifier's runtime code.
  EIP-8141 at the same commit was read again on 2026-10-08 for experiment 03:
  Mempool (its opening goal, Policy Summary, Canonical Paymaster Exception,
  Direct Evaluation of Protocol-Defined Frames, Paymasters, Acceptance
  Algorithm, Replacement and Eviction, Revalidation), `TXPARAM` 0x06 (the max
  cost), and Rationale, "Non-canonical paymasters in the mempool". Used for
  FP-15 version 2 and decision record 0009. Read again the same day for
  experiment 04: Mempool, Policy Summary, Expiry Verifier Frame (the drop
  "at any point"), Replacement and Eviction (the eviction order and the
  paragraph on block producers, which is where the EIP uses "invalid against
  the current head"), and Revalidation; the EIP states no reason for its
  eviction order. Used for FP-14 version 3 and decision record 0010. Read
  again the same day for experiment 05: Expiry Verifier Frame (the verifier
  "reverts unless `block.timestamp <= expiry_timestamp`" and its runtime
  code), Policy Summary (item 2, "the block timestamp as read by an expiry
  verifier frame"), the mempool's Expiry Verifier Frame and Direct
  Evaluation of Protocol-Defined Frames (the dependency set ends with "the
  current block timestamp"), and Replacement and Eviction (a default-code
  sponsor "is not a paymaster and is governed by the per-payer exposure rule
  alone"). Used for FP-8 and FP-15 version 4 and decision record 0011.
- **EIP-8037, State Creation Gas Cost Increase**, Last Call with a
  deadline of 2026-11-01, ethereum/EIPs at commit `258836f9`, read
  2026-10-13 for the plan's item 34. Sections: New parameters (`CPSB` 1530,
  `STATE_BYTES_PER_STORAGE_SET` 64, `STATE_BYTES_PER_NEW_ACCOUNT` 120),
  Parameter changes, Multidimensional metering for state creation costs
  (the two block sums, each against the gas limit, the header's `gas_used`
  their maximum, the reservoir and its inclusion check), Multidimensional
  metering in the Rationale, and Estimated price impacts (97,920 for a new
  slot, 183,600 for a new account). Used for BB-6 in
  `docs/spec/03-block-building.md` version 3, MD-5 and MD-6 in
  `docs/spec/00-model.md` version 7, and decision records 0043 and 0044.
  EIP-8141 at the same commit was read again on the same day for its
  block-level accounting under EIP-8037: `execution_reservation`,
  `state_reservation`, and "no portion of the transaction's gas is reserved
  in both dimensions at once, as it must be under EIP-8037's reservoir
  model". go-ethereum at `93d78a01` was read again the same day:
  `core/gaspool.go` (`CheckGasAmsterdam`, `Available`, `Used`),
  `miner/worker.go` (`commitTransactions` under Amsterdam, its stop below
  `TxBaseCost2780` and its skip of a transaction above `Available`) and
  `params/protocol_params.go` (`MaxTxGas`, $2^{24}$, and `TxBaseCost2780`,
  12,000). Read again 2026-10-13, at the same commit, for the plan's item
  21: Gas accounting for halts and reverts ("A call frame's state changes
  are rolled back on both reverts and exceptional halts. In both cases the
  frame's state-gas is restored to its baseline", and "The same rules apply
  when the top-level call frame reverts or halts"). Used for BB-6 in
  `docs/spec/03-block-building.md` version 4 and decision record 0045.
- **ERC-3009, Transfer With Authorization**, Draft, created 2020-09-28,
  ethereum/ERCs at `c73cd77c` (`ERCS/erc-3009.md`), read 2026-10-13:
  `receiveWithAuthorization`, which "has an additional check to ensure that
  the payee's address matches the caller of this function to prevent
  front-running attacks", and its Security Considerations (use it "instead
  of `transferWithAuthorization` when calling from other smart contracts").
  A shuffle round pulls each input's unit with it. Used for MD-5's
  `pulls` in `docs/spec/00-model.md` version 8 and decision record 0045.
- **go-ethereum, a transaction that reverts**, at `93d78a01`, read
  2026-10-13 for the plan's item 21: `core/state_transition.go` (`execute`:
  "vm errors do not effect consensus", the fee on `gasUsed` paid to the
  coinbase whatever the error) and `core/state_processor.go`
  (`applyTransactionWithEVM`, which returns an error only when
  `ApplyMessage` does, and `MakeReceipt`, which marks a failed result
  `ReceiptStatusFailed`). Used for BB-5 in `docs/spec/03-block-building.md`
  version 4 and decision record 0045.
- **go-ethereum, peers that deliver bad transactions**, at `93d78a01`, read
  2026-10-14 for the plan's item 40: `eth/fetcher/tx_fetcher.go`, which
  disconnects a peer whose delivery fails KZG verification ("Since KZG
  verification is computationally expensive, this acts as a defensive
  measure against potential DoS attacks"), drops a peer whose announced
  type or size disagrees with what it serves, and otherwise sleeps 200 ms
  when more than a quarter of a delivery is refused; `node/defaults.go`
  (`MaxPeers`, 50); and `p2p/server.go` (`MaxDialedConns`, `MaxPeers`
  divided by `defaultDialRatio`, 3, and `checkInboundConn`, which refuses
  an Internet address that connected within `inboundThrottleTime`, 30 s).
  Decision record 0049.
- **EIP-8369, VOPS Profiles for FOCIL Eligibility**, Draft, Informational,
  same commit: its abstract read 2026-10-07, to confirm what MATCHA calls "the
  proposed FOCIL extension for Frame Transactions" (its Profile 2 covers frame
  transactions whose validation stays within a fixed state surface). Read in
  full 2026-10-08, and unchanged on master that day: VOPS profiles, Fee
  validity, Constants (`MAX_VERIFY_GAS_PER_IL`, "candidate value `2**20`,
  pending benchmarks"; `MAX_VERIFY_GAS_PER_TX`, "up to" it), Profile 1,
  Profile 2, Transactions outside FOCIL enforcement, Includers (the budget
  fill "evaluated per IL occurrence before deduplication"), Builders,
  Attesters and Security Considerations (under EIP-7732 the check "must move"
  or Profile 2 stays disabled). VOPS state and the builder-claimed index are
  Not modelled. Used for `docs/spec/07-focil.md`, decision record 0018 and
  experiment 09.
- **EIP-8272, Recent Roots for Frame Transactions**, Draft, Standards Track,
  Core, by Thiery, Buterin, Wahrstaetter and lightclient, created
  2026-05-15, requiring EIP-7843 and EIP-8141; same commit, read in full
  2026-10-09. Sections: Abstract, Motivation, Constants
  (`RECENT_ROOT_LENGTH` 8192, `RECENT_ROOT_USABLE_WINDOW` 8191,
  `MAX_RECENT_ROOT_REFERENCES` 16, `RECENT_ROOT_TUPLE_BYTES` 72,
  `RECENT_ROOT_CODE` "TBD"), Current slot, Root sources, Entry and storage
  keys, Recent root contract (the write and validation operations), Recent
  root verifier frame, Public mempool handling, Rationale (Window choice)
  and Security Considerations (root writes are not guaranteed, and a
  "synchronized expiry may evict many transactions that use one popular
  root"). Activation, the contract's bytecode and
  introspection are Not modelled. EIP-7843 was not read: `slotNumber` is
  taken as EIP-8272 uses it. Used for `docs/spec/08-recent-roots.md`,
  decision record 0023 and experiment 14.
- **EIP-8266, Expiring Nonces for Frame Transactions**, Draft, Standards
  Track, Core, by Wahrstaetter and lightclient, created 2026-05-15, requires
  EIP-8141; ethereum/EIPs at `258836f9`, read in full 2026-10-09, and again
  at `af80fc1c` the same day, unchanged. Sections: Abstract (the scheme
  "adds no permanent state growth"), Constants, Mode selection, Storage
  layout, Stateful validity, Nonce consumption, Gas, Mempool ("Nodes MAY
  admit multiple pending expiring-nonce transactions per sender"), Rationale
  ("Composition with EIP-8250", which is "non-normative", and the
  `MAX_EXPIRY_SECS` bound, "~4369 sustained expiring-nonce TPS") and
  Security Considerations. The file's history was not reachable from here,
  since the proxy refuses the GitHub API, so whether the composition
  paragraph is newer than a reading of 2026-09-14 is not established.
  Used for `docs/spec/09-expiring-nonces.md`, decision record 0030 and
  experiment 21.
- **EIP-8288, In-mempool signature and proof aggregation**, Draft, by
  Buterin and Coratger, same commit, read in full 2026-10-08. Sections:
  Motivation (STARKs "all take over 128 kB"), Constants, New Frame Mode,
  Transaction Dependencies, Transaction Execution Visibility, Block Validity
  (the recursive STARK's header entry, its proof structure and the
  verification pseudocode, for what a recursive STARK covers), Mempool
  Wrapper Object, Recursive Mempool Aggregation (the order for short proving
  time), Mempool-Level Limits, Gas Accounting, Rationale ("a fixed ~256 kB
  per `AGGREGATION_INTERVAL`"), Backwards Compatibility, Test Cases 1 to 11,
  Security Considerations. FOCIL Compatibility and Lean Ethereum Integration
  were read and are Not modelled. Two things the text does not settle are in
  decision record 0012: the dependency frame's `gas_limit` is a field
  EIP-8141 frames at this commit do not have (they carry `limits`), and the
  wrapper limits and "all currently active transactions" cannot both hold.
  Used for `docs/spec/05-aggregation.md`, decision records 0012 and 0013 and
  experiment 06.
- **EIP-8209, Commit-Reveal Transaction Frames**, Draft, by Forshtat and
  Nacson, same commit, read 2026-10-08 only for its frame modes: its COMMIT
  frame is "Mode 0x03", the value EIP-8288 gives `DEP_VERIFY_FRAME_MODE`, and
  it too writes a frame's `gas_limit`. The collision was found in an earlier
  reading of the two EIPs and checked here; the model has no COMMIT frame, so mode 3 is EIP-8288's under
  the `eip-8288` profile alone.
- **EIP-8184, LUCID encrypted mempool**, Draft, by Elowsson, Florentine and
  Ma, created 2026-03-04, same commit, read 2026-10-08. Sections: Constants
  and parameters, Overview, Sealed transactions (ST ticket, Ciphertext
  envelope), Extended payload bid with ST-commitments, Execution payload
  expansion, Key message validity and decryption, Key release, Inclusion
  lists with STs and bundles (the attesters' check), Block processing (the
  charge, the ST-commitment ordering rule, the refund on decryption),
  Rationale (Competition for the ToB, Protocol welfare, Key publisher
  liability for non-reveal: "The mempool must naturally protect against spam
  and reject STs that have no chance of getting included") and Security
  Considerations ("Denial-of-service vectors for STs are instances with a
  low ToB fee and low `max_preceding_commitments`", and "no fixed settings").
  Bundles, key messages, key timeliness and the PTC, recovery, and the
  alternative specifications were read and are Not modelled. Used for
  `docs/spec/06-lucid.md`, decision records 0014 and 0015 and experiment 07.
  Read again 2026-10-09, unchanged on master `af80fc1c`, for what happens to
  a key that never arrives: Block processing (every ticket is charged, the
  refund and the key fee are paid "Upon successful decryption", and "STs not
  decrypted left out from the `decrypted_transactions` list"), Key release
  ("In the case of a single ST, the sender may itself also release the
  `LucidKeyMessage`, even if it specified a key publisher other than
  itself"), and Rationale, Exogenous MEV ("withheld transactions can be
  replaced by regular transactions in block $n+1$"). Used for decision
  record 0027 and experiment 18. Read again 2026-10-13, at the same master
  commit, for the plan's items 24 and 25: Overview ("following the key
  publisher's off-protocol instructions (and if applicable, using its public
  key)", and the timeline $T_1$ to $T_5$, which gives no seconds), Bundles
  (one `key_publisher` for every ticket, and its ECDSA signature over
  `(chain_id, bundle_root)` that "recovers `key_publisher`"), Key message
  (unsigned) and its validity, Key release, Key timeliness (the PTC's
  `keys_observed`), Block processing ("byte-identical transactions they
  derived via decryption"), and Rationale, Censorship resistance without
  FOCIL ("some builder may decide to censor based on key publisher
  identities") and Additional bundle and key options (threshold decryption
  for single-key and multi-key bundles, and "TODO: expand upon various ideas
  under consideration"). For experiment 23, also Rationale, PTC influence
  and state observation (the key vote "can realistically be positioned
  slightly earlier than the vote on the payload"). Used for decision record
  0032 and experiment 23.
  Read again 2026-10-13, at `258836f9`, for the plan's item 21: Block
  processing ("The PT is then executed as a regular transaction, except
  that it bypasses the ordinary EIP-1559 fee-cap validation and no gas fee
  is charged", and "executed against the header of the block in which their
  ST ticket was committed") and Rationale, User welfare ("Trusted
  intermediaries can offer, e.g., offchain revert protection, that the
  public path cannot replicate"). Used for LU-13 in `docs/spec/06-lucid.md`
  version 2 and decision record 0045.
  Read again 2026-10-20, at `258836f9` and byte-identical on master
  `ed9b712690ba810f652d2ec76293ec5c299e2069`, for the key round: Extended
  payload bid with ST-commitments ("For a non-bundle commitment,
  `executable` is empty and `gas_obligation = ticket.gas_limit`"), Key
  message and its validity (the five conditions, the fifth "successfully
  decrypts the transaction(s)"), Key release (the publisher's checks before
  release, and "When the key publisher is confident that the beacon block
  will become canonical (for example after observing attestations for
  it)"), Key timeliness (`keys_observed`, `timely_1`, `timely_0`, `late_1`,
  `late_0`, `equivocated_votes`, the two conditions, and "If this test
  fails for any key, the PTC of the next slot votes against the payload
  timeliness"; the deadlines are named, with no values), and Rationale, Key
  publisher liability for non-reveal. Used for LU-14 to LU-19 in
  `docs/spec/06-lucid.md` version 3 and decision record 0070.
- **EIP-7805, Fork-choice enforced Inclusion Lists (FOCIL)**, Draft, same
  commit, read 2026-10-08 first only for `IL_COMMITTEE_SIZE`, 16, from which
  EIP-8184 derives `MAX_ST_COMMITS`. Read in full the same day, and unchanged
  on master: Roles And Participants, Execution Layer (the three-step check,
  "If `T` is valid, terminate process and return an
  `INCLUSION_LIST_UNSATISFIED` status"), IL Building ("left to the discretion
  of implementers ... at random, by priority fee, or based on how long they
  have been pending"), the Preset (`MAX_BYTES_PER_INCLUSION_LIST`, 8192),
  Core Properties ("FOCIL does not provide explicit rewards for IL committee
  members") and Payload Construction (the "naive way"). IL gossip, its
  deadlines and equivocation are Not modelled. Used for
  `docs/spec/07-focil.md`, decision record 0018 and experiment 09.
- **EIP-7805, EIP-8141, EIP-8184, EIP-8250, EIP-8272, EIP-8288 and
  EIP-8369 on master**, ethereum/EIPs at commit
  `af80fc1c4122c4990b8c84bfd10be60c6e343bb2`, read 2026-10-09 and diffed
  against the pinned commit, for a write-up of the experiments, not
  published here. EIP-8288 reserves
  `LEANSTARK_SCHEME` ("a frame that uses it is invalid until
  `get_deps_hash` is defined for it") and moves the recursive STARK's charge
  into each transaction's intrinsic gas; EIP-8250 charges each non-zero
  nonce key `KEYED_NONCE_ACCESS_COST`, 12100 execution gas under EIP-8038's
  current constants, and deploys keylessly; EIP-8272 defines
  `RECENT_ROOT_CODE` and deploys keylessly; EIP-8141 journals the approval
  context with the frame that set it and restates the valid frame modes.
  EIP-7805, EIP-8184 and EIP-8369 are unchanged. None of this is in the
  specification yet: every clause still cites the pinned commit.
- **MATCHA**: *Mempool Account Transaction Capacity from Historical Activity
  (MATCHA)*, by Thomas (soispoke), "based on ideas and discussions with"
  Vitalik Buterin and Toni Wahrstaetter, ethresear.ch topic 25949, first post
  2026-09-08 13:51 UTC, read 2026-10-07 from the topic's raw text and JSON
  with replies #1 to #14 (no #10 was served). A forum post, not an EIP. Used
  for `docs/spec/04-matcha.md`, decision record 0007 and experiment 02. Read
  again 2026-10-09, the same thirteen posts, for reply #2 by AnkushinDaniil
  (2026-09-08), which asks whether width could be indexed by contention, and
  reply #4 by the author (2026-09-09), which answers it: used for MA-14,
  decision record 0026 and experiment 17.
- **ethresear.ch topic 25934**, "Order-dependence as the classifying
  dimension for frame-transaction mempool admission", by AnkushinDaniil,
  2026-09-07, one post, read 2026-10-09 from the topic's raw text and JSON.
  A forum post, not an EIP. Its three contention classes, single-writer,
  recent-root-bound and live-contended, are the ones MATCHA's reply #2 asks
  width to be indexed by. Used for MA-14 and decision record 0026.
- **ethereum/EIPs pull request 12301**, "Update EIP-8141: define
  `MAX_VERIFY_GAS` as a shared mempool floor", by AnkushinDaniil, open on
  2026-10-08: its head `f3538f209a23bd39ca83dd69d9d4aa16a78380ea`
  (2026-09-29) and a merge ref existed, and EIP-8141 at `master`
  (`17669e96`) does not carry its text. Read 2026-10-08 as the six commits'
  patch from `patch-diff.githubusercontent.com`, and as `EIPS/eip-8141.md`
  at the head. The GitHub API refused the request, so the pull request's
  description and review comments were not read. Commits 4 to 6
  (2026-09-19 to 2026-09-29) came after an earlier reading of it: they turn the
  floor into "MUST NOT reject ... solely because of its validation work",
  measure it over declared rule 6 budgets, keep `MAX_VERIFY_STATE_GAS` a
  hard maximum, say that a node dropping a transaction above the floor
  does not penalise its peer, drop the inclusion-list wording, and move a
  budget carried in announcements out of the EIP, to "a future version of
  the eth wire protocol". Used for decision record 0016 and experiment 08.
- **ethresear.ch topic 25889**, "EIP-8141 and minimum required validation
  budget for privacy applications", first post by mmjahanara (2026-09-02),
  posts 2 and 3 by AnkushinDaniil (2026-09-04, 2026-09-05), read
  2026-10-08 in full from the topic's JSON. A forum post, not an EIP; its
  numbers are its author's measurement, with method, and are cited, not
  reproduced. Section 3's budgets, 211,828, 231,828, 351,828 and 511,828
  for 1, 2, 8 and 16 nullifiers, and section 4's recommended values,
  250,000, 300,000, 400,000 and 525,000. Used for experiment 08. Read again
  2026-10-09 for experiment 16, from the same JSON: what remains of the
  one-nullifier spend once every compression is applied is "a BN254
  pairing check at 181,000, and the protocol's own 20,000 per nullifier".
- **ethresear.ch topic 24666**, "Frame Transactions and the Three Gates
  to Privacy", by Toni Wahrstaetter (Nero_eth), one post (2026-04-16, its
  second version), read 2026-10-14 in full from the topic's JSON. A forum
  post, not an EIP. Its withdrawal's frames, the three gates (public mempool
  admission, FOCIL eligibility, node capability), the validation-index
  enforcement with `MAX_VERIFY_GAS_PER_INCLUSION_LIST` at 2^20, the
  canonical pool ("every slot VERIFY reads only ever transitions" from false
  to true; a nullifier write is "per-tx and individually targeted, never
  mass"), the "1-of-16 capability assumption", the five proposed changes
  and the appendix on alternative mempools. Used for a reply to it from
  this repository's experiments, not published here; nothing in `docs/spec/`
  rests on it. EIP-8369 was read again for that post on 2026-10-14, from
  the copy taken at `af80fc1c` above (unchanged since the pinned commit):
  Profile 2's surface table and its exclusions ("nullifier mappings,
  commitment trees, and arbitrary external storage"), its motivating
  example ("a privacy spend that checks recent roots and consumes each
  nullifier as a single-use EIP-8250 keyed nonce"), the builder-claimed
  index, and `AA_VOPS_SLOT_COUNT`'s "candidate range 2 to 4".
- **ethresear.ch topic 25995**, "Public-mempool gas sponsorship needs
  escrow, a bond, or trust", by AnkushinDaniil, one post (2026-09-14),
  read 2026-10-09 in full from the topic's JSON. A forum post, not an EIP:
  the definitions (SwE, A1 to A3), the lemma, the theorem's four cases ("R
  charges nothing. ... Each distinct s reaches and is checked by all N
  nodes"), the three categories (EIP-8141 under "Hold money") and the
  snapshot corollary. Used for decision record 0019 and experiment 10.
- **consensus-specs**, ethereum/consensus-specs at commit
  `c489a99077c16bad7d75053257c50633d12d314d` (2026-10-06), read 2026-10-07:
  `specs/phase0/beacon-chain.md`, `SLOTS_PER_EPOCH`, `process_slots`,
  `weigh_justification_and_finalization`. Only phase0 was read; later forks
  change how participation is counted, not the finalization rule. Used for the
  simulator's finality (`sim/emem_sim/chain.py`).
  Read again 2026-10-13, at the same commit, for the seconds EIP-8184 does
  not give: `configs/mainnet.yaml` (`SLOT_DURATION_MS` 12000,
  `ATTESTATION_DUE_BPS_GLOAS` 2500, `PAYLOAD_ATTESTATION_DUE_BPS` 7500) and
  where `specs/gloas/validator.md` and `specs/gloas/fork-choice.md` use the
  last two, so attestations are due 3 s into a slot and the PTC's vote 9 s.
  The same file sets `SLOT_DURATION_MS_EIP8198` to 10000 for EIP-8198, which
  was not read. Used for decision record 0032.
- **ethresear.ch topic 19982**, ProbeLab (yiannisbot and cortze) on
  Gossipsub's message propagation latency in Ethereum's network, first post
  (2024-07-05), read 2026-10-13 from the topic's raw text: from three days
  of traces, "98% of messages arrive prior to the 4-second mark" of the
  slot, for beacon blocks. A measurement of 2024's network, not of Gloas.
  Used for decision record 0032's reading of the window between $T_3$ and
  $T_4$.
- **EIP-1559**, same commit. Section "Transaction Ordering", for MD-10.
- **EIP-7623** and **EIP-7976** (calldata floors), **EIP-7702** (set code
  transactions), **EIP-7825** (transaction gas cap), **EIP-3860** (initcode
  limit), **EIP-5793** (eth/68 announcements): cited through the go-ethereum
  code and the EIP-8141 text that apply them. Not read separately for this
  version, except EIP-7702, below.
- **EIP-6780**, **EIP-7702**, **EIP-2929**, **EIP-2200** and **EIP-3529**,
  ethereum/EIPs at `258836f9`, read 2026-10-09; each file is the same at
  master `af80fc1c`. EIP-6780: outside the transaction that created a
  contract, `SELFDESTRUCT` "does not delete any data (including storage
  keys, code, or the account itself)". EIP-7702, behavior step 5: "Verify the
  code of `authority` is empty or already delegated". EIP-2929:
  `COLD_SLOAD_COST` 2100, `COLD_ACCOUNT_ACCESS_COST` 2600, and
  `SSTORE_RESET_GAS` reduced to `5000 - COLD_SLOAD_COST`; EIP-2200:
  `SSTORE_SET_GAS` 20000; EIP-3529: a refund of 4,800 for clearing a slot.
  Used for MA-14, decision record 0026 and experiment 17's flips, and, both
  read again at `258836f9` on 2026-10-20, for SF-3's `claim` and decision
  record 0058. EIP-7702
  read again, at `258836f9`, on 2026-10-09 for experiment 22: Behavior (the
  list is processed "after the sender's nonce is incremented", steps 5, 6, 8
  and 9, and "If any step above fails, immediately stop processing the tuple
  and continue to the next tuple in the list"), Security Considerations,
  "Sponsored transaction relayers" and "Transaction propagation" (the
  recommendation that "clients do not accept more than one pending
  transaction for any EOA with a non-zero delegation indicator"). Used for
  BB-5 version 2, MD-5 version 5 and decision record 0031.
- **EIP-7805, EIP-8184 and EIP-8288 on master again**, ethereum/EIPs at
  commit `3db7d3f4`, read 2026-10-13 and byte-identical to their text at
  `af80fc1c`, so EIP-8288 still reserves `LEANSTARK_SCHEME`. Read for
  Recursive Mempool Aggregation's order for a node short of proving time
  and its private inputs, "[deps, witnesses, recursive_proofs,
  recursive_deps_list, discards]", with "verify inputs, merge and discard".
  Used for AG-9 (`docs/spec/05-aggregation.md`, version 2), decision record
  0034 and experiment 24.
- **leanVM**, github.com/leanEthereum/leanVM at commit
  `1f9e4c4f478038a95a2619009cb9cf654ae0824e` (2026-10-10), the head of its
  main branch on 2026-10-13, with Apache 2.0 and MIT licence files, from
  the organization EIP-8288 points to ("This EIP assumes the use of Lean
  Ethereum tooling for generating and verifying the recursive STARKs. This
  tooling can be found at the leanEthereum GitHub organization", Lean
  Ethereum Integration): a hash-based zkVM whose benchmark CLI (`bins/leanvm`) aggregates leanSPHINCS
  and XMSS signatures and merges child proofs by recursion, reporting
  proving time with a confidence interval, peak memory, proof size and
  verifying time; `MAX_RECURSIONS` is 16
  (`crates/rec_aggregation/src/aggregation.rs`). Its README's figures, from "M4 Max MacBook Pro (12
  performance cores, 4 efficiency cores, 48GB RAM)", are quoted in
  `bench/leanvm/fit.py`. Built and run on this repository's machine by
  `bench/leanvm/run.sh`; used for decision records 0033 and 0034,
  `bench/results/2026-10-13-leanvm.md` and experiment 24. `aggregate` and
  `aggregate_with_stats`
  (`crates/rec_aggregation/src/aggregation.rs`), which take child proofs and
  signatures together, read again on 2026-10-13 for
  `bench/leanvm-memory/memory.rs` and decision record 0041.
- **leanVM's `sha3` branch**, github.com/leanEthereum/leanVM at
  `bf7b6b29b3d5225dd0a27c0b64e7346058cefd98` (2026-10-12, "Merge main into
  sha3", a merge of `1f9e4c4f`), read 2026-10-13: the VM with its one hash
  instruction SHA3-256 in place of BLAKE2s, "SHA3-256 (FIPS 202), the repo's
  one hash function", over "the Keccak-f\[1600\] permutation" at a rate of
  136 bytes and a domain byte of 0x06 (`crates/primitives/src/hash.rs`), and
  a guest builtin `sha3(a, b, out)` of the same shape as main's `blake2s`
  (`crates/lean_compiler/src/lower/builtins.rs`). The main branch's README
  calls BLAKE2s "a placeholder. SHA2, SHA3, BLAKE3 are actively considered".
  Built and run for decision record 0039.
- **Go's SHA-3 package**, `crypto/internal/fips140/sha3/hashes.go` in Go
  1.25.1, read on this machine 2026-10-13: `New256` is "rate: rateK512,
  outputLen: 32, dsbyte: dsbyteSHA3" and `NewLegacyKeccak256`, "the legacy,
  non-standard Keccak-256 hash", is "rate: rateK512, outputLen: 32, dsbyte:
  dsbyteKeccak", with `dsbyteSHA3` 0b00000110 and `dsbyteKeccak`
  0b00000001. Read for decision record 0039's reading that keccak256 and
  SHA3-256 differ in one padding byte. That the EVM's keccak256 is this
  legacy Keccak-256 is not read here from a primary source.
- **ERC-8421, Frame Transaction Alternative Mempools**, Draft,
  ethereum/ERCs pull request 2028 at `493ba8ac`, read 2026-10-13: pools for
  EIP-8141 frame transactions alongside the public one, under ERC-7562's
  stake and reputation, with up to 64 pending transactions for an unstaked
  sender under keyed nonces. Read and reported on in the session; no clause
  rests on it yet. Named in decision record 0035 as the reason a bundler is
  the host for a second implementation, and as the profile that comes here
  first. Read again on 2026-10-20 at the same head, `493ba8ac`, whole, for
  `13-descriptors.md` (Alternative Mempools: "the IPFS hash of a document
  that describes its rules") and `14-erc-8421.md`, every rule of its
  Specification; decision records 0060 and 0061.
- **RFC 8785, JSON Canonicalization Scheme (JCS)**, read 2026-10-20:
  section 3.2.2.3 (numbers serialized as ECMAScript does) and 3.2.3
  (members sorted by UTF-16 code units). Used for DS-2, decision record
  0060.
- **multiformats** `cid` at `9eca1c5b`, `multicodec` at `8d9e9b3b` and
  `multibase` at `d7406cde`, read 2026-10-20: the CIDv1 grammar
  `<multibase-prefix><multicodec-cidv1><multicodec-content-type><multihash-content-address>`;
  `cidv1` `0x01`, `raw` `0x55`, `sha2-256` `0x12`; multibase `b`, "base32",
  "RFC4648 case-insensitive - no padding". Used for DS-3, decision record
  0060.
- **skandha**, etherspot/skandha at `acba0d8`, read 2026-10-13: an ERC-4337
  bundler in TypeScript (Bun and Lerna, vitest). The owner's fork,
  4w44h9jckz-boop/skandha, holds this repository's second implementation in
  `packages/framepool` on its branch `claude/laughing-turing-jj6c9m`, first
  at `3ca50e9`, with a copy of `conformance/vectors/` at `6932e756`.
  Decision record 0035.

- **aztec-packages**, AztecProtocol/aztec-packages at
  `5a63848e571dbb6a99c7c58f7c6077ee60ce93bd` (2026-10-13), read 2026-10-13
  from a sparse clone. Files: `l1-contracts/src/core/EscapeHatch.sol` (a
  bonded candidate proposes for `ACTIVE_DURATION` epochs every `FREQUENCY`,
  both constructor arguments), `l1-contracts/src/core/libraries/rollup/ValidatorSelectionLib.sol`
  (a committee sampled each epoch with `prevrandao`, one proposer a slot,
  more than two thirds of the committee to attest a checkpoint),
  `l1-contracts/src/core/libraries/rollup/ProposeLib.sol`, the message bridge
  (`Inbox.sol`, `Outbox.sol`, `FeeJuicePortal.sol`), the protocol constants
  in `noir-projects/fnd/noir-protocol-circuits/crates/types/src/constants.nr`
  (`MAX_NULLIFIERS_PER_TX` and `MAX_NOTE_HASHES_PER_TX` 64, `ARCHIVE_HEIGHT`
  30, `MAX_TX_LIFETIME` 86400, "1 day. Arbitrarily chosen.") and
  `validate_expiration_timestamp` in
  `noir-projects/fnd/noir-protocol-circuits/crates/rollup-lib/src/tx_base/components/private_tail_validator.nr`,
  whose comment says an expiry "must be at most `MAX_TX_LIFETIME` from the
  anchor block's timestamp". The node, client and documentation are no
  longer in this repository; its README points to the `labs` submodule.
  Used for `docs/aztec-as-not-a-rollup.md` and decision record 0047.
- **aztec-node**, aztec-labs-eng/aztec-node at
  `54e3383c4baa491a83ce129709023d0b6dcf8bc3` (2026-09-23), the commit
  aztec-packages pins as `labs`, read 2026-10-13 from a sparse clone. Files:
  `yarn-project/p2p/src/msg_validators/tx_validator/README.md` (the entry
  points, the stage order, and each validator's benchmarked duration, the
  client proof "~250ms", with no hardware stated), with
  `double_spend_validator.ts`, `timestamp_validator.ts`,
  `block_header_validator.ts`, `tx_proof_validator.ts` and
  `fee_payer_balance.ts` beside it;
  `yarn-project/p2p/src/mem_pools/tx_pool_v2/README.md` (the states, the
  pre-add and post-event rules, the RPC price bump of 10 percent by default)
  with `tx_metadata.ts` (`checkNullifierConflict`, `comparePriority`,
  `getTxPriorityFee`) and `eviction/nullifier_conflict_rule.ts`;
  `yarn-project/stdlib/src/tx/tx.ts` (the `Tx` carries a `chonkProof`);
  `noir-projects/aztec-nr/aztec/src/macros/notes.nr` (the default note's
  `compute_nullifier`, from `request_nhk_app`); and the developer
  documentation, under its `docs` directory in
  `docs-developers/docs/foundational-topics/`
  (`transactions.md`, `state_management.md`, `fees.md`, and
  `advanced/circuits/` `index.md`, `private_kernel.md`,
  `public_execution.md`, `rollup_circuits.md`). Used for
  `docs/aztec-as-not-a-rollup.md` and decision record 0047. Not read: the
  AVM, the prover network, any deployed network's parameters.

- **go-ethereum, for the surface**, at the same commit `93d78a01`, read
  2026-10-20 from raw files: `internal/ethapi/api.go` (`SendRawTransaction`,
  `SubmitTransaction`), `core/types/transaction.go` (`UnmarshalBinary`,
  `decodeTyped`), `core/types/transaction_signing.go` (`ErrInvalidChainId`),
  `core/txpool/validation.go` (`ValidateTransaction`, its type and size
  checks), `core/txpool/errors.go` (`ErrOversizedData`),
  `core/txpool/legacypool/legacypool.go` (`txMaxSize`), `eth/handler_eth.go`
  (a `Transactions` or `PooledTransactions` message that does not decode ends
  the session) and `eth/fetcher/tx_fetcher.go` (`Enqueue`: a pool's refusal
  disconnects no one, the 200 ms pause). Used for `docs/spec/11-surface.md`.
- **EIP-8141 and EIP-8250 for the surface**, at ethereum/EIPs `258836f9`, read
  2026-10-20: EIP-8141's "Payload Encoding", "Constraints", "Signature Hash",
  "Gas Accounting" (`tokens_in`, `floor_tokens_in`, `calldata_cost`),
  "Acceptance Algorithm", "Replacement and Eviction", "Networking" and
  "Security Considerations"; EIP-8250's "Transaction payload". EIP-8141 was
  also read at `b75cbe6115`, the testnet's pin, whose payload section is the
  same. Used for `docs/spec/11-surface.md` and FEE-4 version 9.
- **gossipsub v1.1**, libp2p/specs at `c750236de43cd8b246a824b377dfdb26bae686db`,
  read 2026-10-20: `pubsub/gossipsub/gossipsub-v1.1.md`, "Extended
  Validators". Used for SF-7.
- **ethrex**, lambdaclass/ethrex at `64b8fc09d47d7787eb1a4e3f082aa9e831dc5f8c`
  (branch `hegota-testnet-hotfix`), the client the Hegota testnet reports in
  `web3_clientVersion` since 2026-10-07, read 2026-10-20 from a partial clone:
  `crates/networking/rpc/ethrex.rs` (`ethrex_simulateFrameTransaction`: its
  parameters, the order of its gates, its result's fields),
  `crates/vm/levm/src/validation_observer.rs` (`FrameSimViolation`, and
  `touched_sender_slots`, which the observer records and the RPC does not
  return), `crates/vm/backends/levm/mod.rs` (the verdict's text: `Debug` of
  the violation, "validation prefix frame reverted", "validation prefix did
  not establish a payer") and `crates/blockchain/blockchain.rs`
  (`prospective_header`). Used for SF-4 and SF-8.
  Read again the same day for item 46: `crates/blockchain/focil_eligibility.rs`
  (`MAX_VERIFY_GAS_PER_IL`, `MAX_VERIFY_GAS_PER_TX`, `fill_il_budget`,
  `is_profile_2_candidate`), `crates/blockchain/inclusion_list_validator.rs`
  (`check_with_profile_2`, which runs the fill once),
  `crates/networking/rpc/engine/inclusion_list.rs` (the one array it is
  handed) and `crates/common/types/transaction.rs` (`validation_prefix`,
  which skips a leading recent-root verifier frame). Used for IL-1, IL-3 and
  IL-4's `per-payload`, `07-focil.md` version 2.
- **consensus-specs, inclusion lists**, ethereum/consensus-specs at
  `d9663f85be248c4fd0ae95806da6070e17c2442b` (master), read 2026-10-20:
  `specs/heze/inclusion-list.md`, `get_inclusion_list_transactions`, which
  ends `return list(set(transactions))` under "Order does not need to be
  preserved". Used for IL-4's delivered order.
- **execution-apis**, ethereum/execution-apis at
  `e4ba6c4fd2a6e5d770b262ca0fbfabfaee3b4e1f` (main), read 2026-10-20:
  `src/engine/bogota.md`, `inclusionListTransactions: Array of DATA` in
  `PayloadAttributesV5` and `engine_newPayloadV6`. Used for IL-4.
- **The Hegota testnet**, `https://rpc1.privacy.ethrex.xyz`, chain 8141,
  queried 2026-10-20: `ethrex_simulateFrameTransaction` at `latest` for each
  of `exp-frames`' 182 Hegota fixtures, whose `maxCost` FEE-4 version 9
  matched in all 182, the zero-byte term changing it in 159; the same call
  for ethrex's golden vector, `maxCost` `0x84f821926c800`; and, at block
  304884, the call refused ("state root missing"), while `eth_getBalance`,
  `eth_getTransactionCount` and `eth_getCode` at that block answered with the
  latest state, nonce 12 for a sender whose transaction in the next block
  used 9. Used for `sf-02-decoding.json`, `sf-03-model-transaction.json` and
  decision record 0051.
- **RFC 9380**, "Hashing to Elliptic Curves", read 2026-10-20 from
  `https://www.rfc-editor.org/rfc/rfc9380.txt`: sections 5.3.1
  (`expand_message_xmd`), 6.6.2 and 6.6.3 (simplified SWU, and its use
  through an isogeny), 8.8.1 (the suite BLS12381G1_XMD:SHA-256_SSWU_RO_),
  appendix E.2 (the 11-isogeny's constants, copied from the text into
  `ref/python/emem/bls.py` by a parser, all 53 present) and appendix J.9.1
  (the five test vectors in `ref/python/tests/test_bls.py`). Used for CG-9.
- **draft-irtf-cfrg-bls-signature-05**, an Internet-Draft of June 2022,
  expired as a draft, read 2026-10-20 from
  `https://www.ietf.org/archive/id/draft-irtf-cfrg-bls-signature-05.txt`:
  sections 2.5 (KeyValidate), 2.7 (CoreVerify), 4.2.3 (the ciphersuite
  BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_) and appendix A (the curve,
  the optimal ate pairing, and the compressed serialization it cites from
  zkcrypto). Used for CG-9.
- **Commonware**, commonwarexyz/monorepo at
  `c18a6b9c47b8e55d0a6f2fdef3fa10a75d6641da` (2026-10-19), read 2026-10-20
  from a clone: `cryptography/src/bls12381/primitives/ops/mod.rs`
  (`sign_message`, `verify_message`, `hash_with_namespace`),
  `cryptography/src/bls12381/primitives/group.rs` (G1 and G2 `Read`, which
  refuse a bad encoding, a point off the curve, the point at infinity and a
  point outside the subgroup), `cryptography/src/bls12381/primitives/variant.rs`
  (`MinSig`, `G1_MESSAGE`) and `utils/src/lib.rs` (`union_unique`). Run the
  same day, outside this repository, to sign every ticket in
  `conformance/vectors/claim-gated/`. Used for CG-9 and decision record 0056.
- **EIP-2537, Precompile for BLS12-381 curve operations**, Final, at
  `258836f9`, read 2026-10-20: "Fine points and encoding of base elements"
  (each field element in 64 bytes, its top 16 zero and below the modulus;
  an element of the extension field as `c0` then `c1`; the point at
  infinity as zeros), "ABI for pairing check" and "Subgroup checks". Used
  for CG-9 and CG-10.
- **EIP-8250**, at `258836f9` and again on master at
  `0ce679f4654ba4d120c97113626f320475e22fa9` (2026-10-19), read
  2026-10-20: "Transaction introspection", `TXPARAM(0x0F)` and the
  definition of `nonce_keys_hash`, the same at both. Used for CG-8. Master
  also allows `nonce_keys == []`, which FP-3, read at `258836f9`, refuses;
  not yet carried into `02-frame-pool.md`.
- **The Hegota testnet's EIP-2537 pairing precompile**, `eth_call` to
  `0x0f` at `https://rpc1.privacy.ethrex.xyz`, 2026-10-20: the verdict on
  every well-formed and malformed ticket in `cg-09-ticket-verification.json`
  and on every well-formed one in `cg-10-ticket-carriage.json`. Used for
  their expected values.

## Other repositories and public sources

- **exp-frames** (4w44h9jckz-boop/exp-frames, branches `plan` and `tooling`,
  read 2026-10-07): `PLAN.md` on `plan`, table "What differs from EIP-8141
  master", for the testnet's keyed-nonce concurrency (citing EIPs pull request
  12039) and its expiry verifier address. Not re-measured here.
- **exp-frames**, branch `plan` at `a58c327`, re-read 2026-10-07: the
  divergence table's "Mempool concurrency" row, for decision record 0005.
- **exp-frames**, branch `plan` at `a58c327`, re-read 2026-10-08: "After the
  examples", the mempool rule probing idea, for "Growing the base".
- **Ethereum Foundation, Mandate**, https://ethereum.org/foundation/mandate/,
  read 2026-10-13: "Our closest collaborators include those working
  directly on privacy, verifiability, and programmable cryptography."
  Used for decision record 0048. 0xPARC's essays on the term were tried at
  https://0xparc.org/blog/programmable-cryptography-1 the same day and
  returned only a script-rendered shell, so they are not cited.
  Read again 2026-10-14, fetched directly (sha256 of the page beginning
  `b941a70c`): the four CROPS properties as the
  mandate lists them, its definition of censorship resistance ("No actor
  can selectively exclude valid use or break functionality, including by
  gaining durable, non-competitive control of any critical mechanisms"),
  "The north star is disintermediation" with "keeping intermediary roles
  open, plural, bounded, and verifiable", and the "zero option". The
  mandate uses "capture" throughout and lists four properties, not five.
- **0xPARC, Programmable Cryptography (Part 1)**, by gubsheep, 2024-07-30,
  https://0xparc.org/blog/programmable-cryptography-1, read 2026-10-14 in
  full. The page renders in a script; its text is the first of 39
  base64-encoded markdown posts embedded in the site's bundle
  (`index.d05e47c4.js`), decoded and read as written. Used for the
  definition of programmable cryptography, its list (FHE, MPC, zkSNARKs,
  witness encryption, obfuscation), footnote 2's state of each, the
  sentence on what SNARKs, FHE and MPC, and obfuscation each give a
  system, and its example "rollups and validiums".
- **ethresear.ch topic 3675**, "Roll_up / roll_back snark side chain ~17000
  tps", BarryWhitehat, Alex Gluchowski, HarryR, Yondon Fu and Philippe
  Castonguay, first post 2018-10-03, read 2026-10-14 from the topic's
  JSON: its two roles, users and an operator who "uses snarks to aggregate
  these transactions into single on-chain updates", and "A malicious
  operator cannot steal funds".
- **Vitalik Buterin**, fetched directly from vitalik.eth.limo on
  2026-10-14 and read for the passages quoted: "Obfuscation: building the
  final boss of cryptography (Part I)" (2026-06-29; what ZK proofs and
  obfuscation each replace, "no M-of-N threshold committee required", and
  a run time that is "literally galactic" for iO "under reasonable
  security assumptions"), "Obfuscation (Part II): Diamond iO" (2026-07-28;
  "merely 'planetary', rather than galactic runtime - still infeasible
  today") and "The cryptographic world computer" (2026-09-27; "Even weak
  versions of obfuscation have many applications in eg. encrypted
  mempools", and that its conclusions "will apply long before any of that
  becomes available").
- **EIP-2938, Account Abstraction**, Withdrawn, created 2020-09-04, at the
  pinned commit `258836f9`, read 2026-10-14: its Tornado Cash example,
  where "a third-party relayer verifies the ZK-SNARK and unspent status of
  the nullifier, publishes the transaction using their own ETH to pay for
  gas", and AA "avoiding the need for relayers". With EIP-8141's
  Motivation ("without centralized, third party relayers"), EIP-8288's
  abstract and Specification ("allowing mempool nodes to combine proofs",
  one recursive STARK in the block) and EIP-7805's "1-out-of-N honesty
  assumption", all at the same commit.
- **L2BEAT scaling summary**, a snapshot retrieved 2026-10-01 from
  https://l2beat.com/api/scaling/summary (100 projects, 50.93 billion USD),
  read 2026-10-14; the snapshot is not kept in this repository. Shares
  recomputed from its per-project rows, weighted by value secured: a
  decentralised sequencer set 8.6%, no sequencer-failure mechanism 20.8%, no
  exit window 100.0%, Stage 2 under 0.01% (four projects, Aztec Network at
  2,223 USD). L2BEAT's classification and valuation are taken as given.
- **exp-frames** (4w44h9jckz-boop/exp-frames, main at `85ee60d`, read
  2026-10-20): `test/fixtures/chain/`, 188 mined frame transactions, 182 from
  the Hegota testnet and 6 from frames-devnet-0 in EIP-8141's own envelope;
  `src/frametx/` (`serializeFrameTx`, `frameTxFromJson`, `frameTxHash`), whose
  encoding of each fixture used in `conformance/vectors/surface/` hashes to
  the chain's hash; `test/encode.test.ts` (ethrex's golden vector);
  `exp-frames/experiments/19-mempool-rules/README.md` (ethrex's refusal texts). Used for
  `docs/spec/11-surface.md` and its vectors.
- **exp-frames** (branch `claude/nifty-einstein-llp9cd` at `f0749cb`, read
  2026-10-20): `exp-frames/experiments/36-blind-tickets/`, blind tickets issued by a
  threshold committee and paid for in a paymaster's `VERIFY` frame on the
  Hegota testnet: the ticket's message and the 168 bytes its frame carries,
  the paymaster's 122,006 gas of execution, the one pending transaction a
  payer other than the canonical paymaster may sponsor, and `record.json`,
  whose four mined tickets are cases in `cg-08-ticket-message.json`,
  `cg-09-ticket-verification.json` and `cg-10-ticket-carriage.json`. Its
  issuers and paymaster are `kohaku-rs` (4w44h9jckz-boop/kohaku-rs, `b6a63b1`),
  `crates/frame-ticket/`, `TicketPaymaster.yul` and `src/ticket.rs`. Used for
  CG-8 to CG-10 and decision record 0056.
- **kohaku-rs** (4w44h9jckz-boop/kohaku-rs, branch
  `claude/nifty-einstein-llp9cd` at `eea02a3`, read 2026-10-20):
  `crates/frame-ticket/contracts/TicketPaymaster.hex`, the paymaster's
  creation code, whose bytes after its 25-byte constructor are the
  ticket-paymaster template of CG-10, and `TicketPaymaster.yul`, which
  deploys that runtime followed by the key and a 32-byte denomination;
  `tests/fixtures/record.json`, experiment 36's re-run under
  `FRAME_TICKET_V1`, whose four mined tickets verify. The template's code
  was also read from the testnet: `eth_getCode` of
  `0x273795f6eb2730d50c3544cbef1e0c1adba4f541` (1,393 bytes) and of the first
  run's paymaster `0xaac74de2ec4dd90656b7f029610dc9fe2f19ceb4` (1,394 bytes,
  another runtime), 2026-10-20. Used for CG-10, its vectors and decision
  record 0057. The record's mined spend, its three refusals and its two
  spends sent at once are also the claim cases of `sf-03-model-transaction.json`
  and `sf-05-send-raw.json`, at the head the spend was built on: block
  `0x75728` (`eth_getBlockByNumber`: timestamp 1792484503, base fee 7, slot
  510342) and the paymaster's balance there (`eth_getBalance`,
  4016411986114884 wei), read 2026-10-20. Used for SF-3 and SF-4 version 3
  and decision record 0058. For experiment 25 and decision record 0059:
  `TicketPaymaster.yul`'s header ("There is no withdrawal: the float leaves
  only as gas this contract approves"; a call with value buys value over
  the denomination tickets, so a ticket costs the denomination, $10^{15}$
  wei in the run); the record's `payVerify.gasUsed`, 122,006, the
  paymaster's `VERIFY` frame; and `eth_estimateGas` of the record's
  deployment, its 1,418 bytes of creation code and key through the
  deterministic deployment proxy `0x4e59b44847b379578588920ca78fbf26c0b4956c`
  under a fresh salt, at block 482,799 of the testnet: 2,443,085 gas, read
  2026-10-20.

Before this repository was published on 2026-10-20, some readings and
measurements it uses came from research notes and benchmarks that are not
public. Where a decision record or a clause rests on one, it states the
reading or the measurement with its date and machine where known, and gives
no link.
