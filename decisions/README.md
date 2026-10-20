# Decision records

Every non-obvious choice gets a numbered record: the context, the decision,
and its consequences. A record is never rewritten; a later record supersedes it
and says so.

| # | Decision |
| --- | --- |
| [0001](0001-charter.md) | Charter: a specification, a reference implementation, and a simulation base |
| [0002](0002-the-nonce-pool-is-go-ethereums.md) | The account-nonce pool is go-ethereum's, transcribed |
| [0003](0003-the-frame-pool-models-what-simulation-observes.md) | The frame pool models what simulation observes, under two profiles |
| [0004](0004-gossip-follows-go-ethereums-fetcher.md) | Gossip follows go-ethereum's broadcast and fetcher, and loads roll their own dice |
| [0005](0005-a-shared-sender-is-measured-with-a-relayer-and-without.md) | A shared sender is measured with a relayer and without, against a one-knob variant |
| [0006](0006-fee-4-prices-the-nonce-fields.md) | FEE-4 prices the EIP-8250 nonce fields, and the floor counts them as tokens |
| [0007](0007-matcha-is-specified-as-a-proposal.md) | MATCHA is specified as a proposal, with its open choices made explicit |
| [0008](0008-experiment-02-resends-counts-gas-and-attacks-without-focil.md) | Experiment 02 resends, counts work in gas, and attacks without FOCIL |
| [0009](0009-revalidation-is-measured-against-a-balance-reuse-variant.md) | Revalidation is measured with a capital-free adversary, against a balance-reuse variant |
| [0010](0010-eviction-order-is-measured-against-transactions-no-builder-includes.md) | Eviction order is measured against transactions no builder includes, and against a tip-first variant |
| [0011](0011-the-expiry-check-is-measured-at-the-head-and-at-the-next-slot.md) | The expiry check is measured at the head and at the next slot, against three adversaries |
| [0012](0012-eip-8288-is-specified-as-a-layer-on-the-frame-pool.md) | EIP-8288 is specified as a layer on the frame pool, with its open readings explicit |
| [0013](0013-aggregation-is-measured-on-a-larger-network-with-proofs-only-in-wrappers.md) | Aggregation is measured on a larger network, with proofs only in wrappers |
| [0014](0014-lucid-is-specified-as-a-sealed-subpool-with-its-policy-open.md) | LUCID is specified as a sealed subpool, with its admission policy left open as a parameter |
| [0015](0015-sealed-floods-are-measured-against-an-eviction-that-keeps-what-has-a-place.md) | Sealed floods are measured against an eviction order that keeps what has a place |
| [0016](0016-the-verification-gas-floor-is-measured-as-per-node-budgets.md) | The verification gas floor is measured as per-node budgets, with hints the wire protocol does not have |
| [0017](0017-experiments-are-checked-in-parallel-outside-make-verify.md) | Experiments are checked in parallel, outside `make verify` |
| [0018](0018-inclusion-lists-are-read-from-eip-7805-and-filtering-builders-are-the-simulators.md) | Inclusion lists are read from EIP-7805 with EIP-8369's profiles, and builders that filter are the simulator's |
| [0019](0019-wasted-work-is-counted-in-prefix-runs-against-two-adversaries.md) | Wasted work is counted in prefix runs, against sponsors that hold nothing and a sponsor drained every block |
| [0020](0020-copies-of-one-spend-are-measured-under-two-encodings-and-suppressed-before-the-prefix.md) | Copies of one spend are measured with the nullifier in a nonce key and in a storage slot, and suppressed by checking FP-11 and FP-12 before the prefix |
| [0021](0021-the-timing-channel-is-measured-with-a-spy-at-every-node-and-observers-that-guess-the-first-peer.md) | The timing channel is measured with a spy connected to every node and with ordinary nodes that log, both guessing the first peer they heard from |
| [0022](0022-matchas-load-floor-is-specified-with-the-new-charge-as-its-unit-and-measured-against-users-who-send-alone.md) | MATCHA's load floor is specified with the new transaction's charge as its unit, and measured against users who send alone |
| [0023](0023-recent-roots-are-evaluated-directly-and-measured-in-windows-a-run-can-reach.md) | Recent roots are evaluated directly, with injective names for keccak256's, and measured in windows scaled down to what a run can reach as well as in the EIP's |
| [0024](0024-wallets-re-price-the-transaction-that-holds-up-the-others-and-users-stop-at-a-price-of-their-own.md) | Wallets re-price the transaction that holds up the others, and users stop at a price of their own |
| [0025](0025-a-node-verifies-proofs-under-one-key-in-a-batch-it-holds-for-a-window.md) | A node verifies proofs under one key in a batch it holds for a window |
| [0026](0026-matchas-baseline-is-taken-per-contention-class-read-off-what-can-re-run-a-prefix.md) | MATCHA's baseline is taken per contention class, read off what can re-run a prefix |
| [0027](0027-a-withheld-key-costs-its-sender-the-ticket-and-the-sender-sends-again.md) | A withheld key costs its sender the ticket, and the sender sends again |
| [0028](0028-a-committee-settles-a-chain-of-batches-from-one-node-at-the-costs-merces-measured.md) | A committee settles a chain of batches from one node, at the costs Merces measured |
| [0029](0029-a-committee-that-clears-every-block-takes-its-orders-from-a-block-or-from-the-pool-at-a-cutoff.md) | A committee that clears every block takes its orders from a block, or from the pool at a cutoff |
| [0030](0030-expiring-nonces-compose-with-keyed-nonces-as-a-reserved-key-and-a-shared-sender-keeps-its-nullifier-in-storage.md) | Expiring nonces compose with keyed nonces as a reserved key, and a shared sender keeps its nullifier in storage |
| [0031](0031-an-authorization-carries-its-nonce-and-a-hot-wallet-signs-one-at-its-next-nonce.md) | An authorization carries its nonce, and a hot wallet signs one at its next nonce |
| [0032](0032-a-committee-releases-a-key-when-enough-shares-are-in-time-and-a-key-sealed-to-a-committee-that-no-longer-serves-is-withheld.md) | A committee releases a key when enough shares are in time, and a key sealed to a committee that no longer serves is withheld |
| [0033](0033-a-benchmark-measures-a-machine-once-and-what-is-derived-from-it-is-checked.md) | A benchmark measures a machine once, and what is derived from it is checked |
| [0034](0034-proving-time-is-counted-from-the-circuits-inputs-at-costs-a-benchmark-fits.md) | Proving time is counted from the circuit's inputs, at costs a benchmark fits |
| [0035](0035-a-second-implementation-lives-in-the-owners-skandha-fork-and-is-judged-by-the-vectors-here.md) | A second implementation lives in the owner's skandha fork, and is judged by the vectors here |
| [0037](0037-claim-gated-admission-is-a-proposal-on-eip-8288-and-a-wrappers-proofs-are-not-under-the-senders-signature.md) | Claim-gated admission is a proposal on EIP-8288, and a wrapper's proofs are not under the sender's signature |
| [0038](0038-a-relay-checks-claims-forwards-mode-0-wrappers-and-takes-no-aggregate.md) | A relay checks claims, forwards mode 0 wrappers, and takes no aggregate |
| [0039](0039-an-update-is-a-program-leanvm-proves-with-its-own-hash-and-the-updater-is-a-load.md) | An update is a program leanVM proves with its own hash, and the updater is a load |
| [0040](0040-a-ticket-is-held-from-its-block-and-the-linker-ranks-gaps-by-a-model-of-the-pool.md) | A ticket is held from its block, and the linker ranks gaps by a model of the pool |
| [0041](0041-an-aggregates-memory-is-its-own-peak-over-inputs-made-first.md) | An aggregate's memory is its own peak, over inputs made first |
| [0042](0042-an-aggregates-memory-is-counted-as-its-time-is-and-a-node-budgets-against-an-envelope.md) | An aggregate's memory is counted as its time is, and a node budgets against an envelope |
| [0043](0043-a-block-counts-state-gas-in-a-dimension-of-its-own-and-each-envelope-reserves-as-its-eip-says.md) | A block counts state gas in a dimension of its own, and each envelope reserves as its EIP says |
| [0044](0044-a-spend-goes-out-three-ways-at-one-tip-and-the-burst-fills-the-sum-it-binds.md) | A spend goes out three ways at one tip, and the burst fills the sum it binds |
| [0045](0045-a-transaction-can-pull-from-accounts-that-signed-and-one-that-cannot-is-included-and-reverts.md) | A transaction can pull from accounts that signed for it, and one that cannot is included and reverts |
| [0046](0046-a-griefer-holds-one-seat-a-round-and-spends-as-the-round-is-sent.md) | A griefer holds one seat a round and spends as the round is sent |
| [0047](0047-aztec-is-fitted-job-by-job-from-its-current-code.md) | Aztec is fitted job by job from its current code |
| [0048](0048-programmable-cryptography-moves-to-the-mempool-job-by-job-and-capture-is-read-in-the-mandates-words.md) | Programmable cryptography moves to the mempool job by job, and capture is read in the mandate's words |
| [0049](0049-commonware-gives-four-measurements-and-a-method-and-its-conformance-commitments-are-fixtures.md) | Commonware gives four measurements and a method, and its conformance commitments are fixtures |
| [0050](0050-the-proof-of-concept-requests-are-items-42-to-49-and-phase-1-opens-the-surface-and-the-replay.md) | The proof-of-concept requests are items 42 to 49, and phase 1 opens the surface and the replay |
| [0051](0051-the-surface-takes-real-bytes-and-a-clients-verdict-and-the-model-prices-zero-bytes.md) | The surface takes real bytes and a client's verdict, and the model prices zero bytes |
| [0052](0052-a-replay-judges-what-a-chain-keeps-and-names-its-differences-before-it-runs.md) | A replay judges what a chain keeps, and names its differences before it runs |
| [0053](0053-hegota-testnet-models-eip-8272-and-the-surface-reads-its-tuples.md) | `hegota-testnet` models EIP-8272, and the surface reads its tuples |
| [0054](0054-shared-sender-admission-is-judged-on-the-mined-pair-with-a-stand-in-for-the-refused-spend.md) | Shared-sender admission is judged on the mined pair, with a stand-in for the refused spend |
| [0055](0055-the-budget-fill-per-payload-is-a-profile-and-the-order-delivered-is-an-input.md) | The budget fill per payload is a profile, and the order delivered is an input |
| [0056](0056-a-ticket-is-a-bls12-381-signature-in-g1-over-a-fixed-message-verified-as-commonware-verifies.md) | A ticket is a BLS12-381 signature in G1 over a fixed message, verified as Commonware verifies |
| [0057](0057-a-ticket-paymaster-is-recognised-by-its-code-and-a-self-issuer-pays-for-junk-proofs-only-once.md) | A ticket paymaster is recognised by its code, and a self-issuer pays for junk proofs only once |
| [0058](0058-the-surface-reads-a-paymasters-code-from-the-client-and-checks-a-claim-before-asking-about-the-prefix.md) | The surface reads a paymaster's code from the client, and checks a claim before asking about the prefix |
