# Plan

This is the plan of `exp-mempool-l2s`, on the branch `plan`, which is never
merged. Paths are on `main`. The log, one file a day, sits beside it in
`log/`.

Status at publication, 2026-10-20: the specification (thirteen documents),
the reference implementation, 653 hand-written conformance vectors, the
simulation base, twenty-five experiments and two benchmarks are in place and
checked by `make verify` and `make experiments` (decision records 0017 and
0033). A second implementation of the frame pool, in TypeScript, lives in a
fork of skandha and plays the vectors (decision record 0035). What comes
next is experiments, and the base grows when an experiment needs it.

New work follows the branches of the README: a change to the specification,
the reference or the simulator goes to `base`, in the order clause, vectors,
then code, and is merged before the experiment that needs it, which goes to
its own `exp/NN-name`.

## What exists

| Part | State |
| --- | --- |
| `docs/spec/00-model.md` | Version 11. Accounts, heads, transactions, pool interface with `finalize`, fee and gas formulas; FEE-4 prices EIP-8250's nonce fields (decision record 0006); MD-6 has EIP-8288's dependency frames and an admission claim; MD-11 holds a sender in one of three subpools; MD-5's authorizations may carry their nonce (decision record 0031); MD-5 and MD-6 carry the EIP-8037 state gas a transaction uses (decision record 0043); MD-5's transaction can pull value from accounts that signed for it and pay it on, as ERC-3009's `receiveWithAuthorization` does, and declares the gas it uses if it reverts (decision record 0045); MD-6's frame transaction counts its zero calldata bytes, which FEE-4 prices at one token, and may carry a client's verdict on its prefix, which `reset` renews (decision record 0051); since version 10 an account carries the stake ERC-8421's registry reports, and a frame's reads and writes the address a tracer finds a slot associated with (decision record 0061); since version 11 a dependency frame's mode is AG-1's (decision record 0063) |
| `docs/spec/01-nonce-pool.md` | Version 1. go-ethereum `legacypool` at `93d78a01`, 20 clauses |
| `docs/spec/02-frame-pool.md` | Version 7. EIP-8141 public mempool at `258836f9` with EIP-8250, 16 clauses, profiles `eip-8141` and `hegota-testnet`, a `reuse_balance` variant of FP-15 (decision record 0009), an `evict_first` variant of FP-14 (decision record 0010), an `expiry_margin` variant of FP-8 and FP-15 (decision record 0011) and a `static_first` variant that checks FP-11 and FP-12 before the prefix (decision record 0020); FP-8 and FP-9 take a client's verdict where a transaction carries one, and FP-15 counts a new verdict as a changed dependency (decision record 0051); `hegota-testnet` takes `08-recent-roots.md`'s recent roots (decision record 0053) |
| `docs/spec/03-block-building.md` | Version 4. go-ethereum miner ordering and the model's state transition, which checks each EIP-7702 authorization against its authority's code and nonce (decision record 0031), and BB-6, EIP-8037's two gas dimensions as the rule `two`, each envelope reserving as its EIP says (decision record 0043); a transaction whose execution reverts is included and pays for the gas it used, as go-ethereum does, and BB-7 adds builders that drop what would revert (decision record 0045) |
| `docs/spec/04-matcha.md` | Version 3, a proposal. MATCHA's width on top of the frame pool, 14 clauses, profile `matcha` (decision record 0007), the post's optional load floor, off in the profile (decision record 0022), and a baseline per contention class, one a sender in the profile, with `storage` and `slot` as the readings of reply #2's question (decision record 0026) |
| `docs/spec/05-aggregation.md` | Version 4. EIP-8288 at `258836f9` on top of the frame pool, 10 clauses, profile `eip-8288` with `cap_aggregates` and `forward_wrappers` for the readings the text leaves open (decision record 0012), AG-9's proving time of an aggregate under a budget, unset in the profile with its four costs at 0 (decision record 0034), and AG-10's memory of an aggregate under a budget, unset likewise (decision record 0042); since version 4 a second profile, `eip-8288-master`, the EIP at master `899bef0a` with leanSTARK reserved, a dependency frame of mode 4 outside an atomic batch, a zero `data_hash` for the signature hash and mode 1's union checked (decision record 0063) |
| `docs/spec/06-lucid.md` | Version 2. EIP-8184 at `258836f9` as a sealed subpool and two builder steps, 13 clauses, profile `eip-8184` with the admission `policy` left open (decision record 0014) and an `evict_first` variant (decision record 0015); a decrypted transaction executes its pulls and pays, and reverts, as BB-5 says (decision record 0045) |
| `docs/spec/07-focil.md` | Version 2. EIP-7805 at `258836f9` as a constraint on the builder, with EIP-8369's profiles for what can be enforced, 8 clauses, profiles `eip-7805` and `eip-8369` and a `policy` variant for what an includer lists first (decision record 0018); since version 2 the budget fill per list or per payload, with the profile `ethrex`, the order delivered as an input, and validity at a node without the post-state as a verdict (decision record 0055) |
| `docs/spec/08-recent-roots.md` | Version 2. EIP-8272 at `258836f9` on top of the frame pool, 8 clauses, profile `eip-8272`, with `RECENT_ROOT_CODE`, which the EIP leaves unset, a named string, and the margin a node keeps as `root_margin`, 0 in the profile (decision record 0023); since version 2 `hegota-testnet` too, at the testnet's constants, and a transaction with a client's verdict keeps its root expiry (decision record 0053) |
| `docs/spec/09-expiring-nonces.md` | Version 1. EIP-8266 at `258836f9`, unchanged at `af80fc1c`, on top of the frame pool, composed with EIP-8250 as the reserved key its Rationale names, 7 clauses, profile `eip-8266`, with whether a node admits several pending in the mode as `expiring_per_sender`, `many` in the profile (decision record 0030) |
| `docs/spec/10-claim-gated-admission.md` | Version 5. A proposal of this repository: claim-gated admission on the `eip-8288` profile, 10 clauses, profile `claim-gated`, with what a node remembers after a failed proof as `claim_memory` and whether a sender's signature covers a wrapper's proofs as `signed_proofs`, false in the profile as in EIP-8288 (decision record 0037), and relays, nodes that check claims and verify no proof, as `verifies` (decision record 0038); version 3 (on `base`) adds the ticket: the 132 bytes an issuer signs, a BLS12-381 signature in EIP-2537's encoding, and the frame to a ticket paymaster that carries it (decision record 0056); version 4 recognises a ticket paymaster by its code (decision record 0057), and version 5 accepts one only under a bond, ERC-8421's stake and reputation, CG-11 (decision record 0064) |
| `docs/spec/11-surface.md` | Version 2. The surface around a frame pool for the plan's item 42: a type `0x06` transaction decoded from its bytes and named by its keccak256, the validation prefix's outcome from an execution client's verdict, `eth_sendRawTransaction`, relay to peers over `eth` or `gossipsub` and what is taken from them, head changes and hand-off to a client, 9 clauses and a run procedure; read from EIP-8141 and EIP-8250 at `258836f9`, go-ethereum at `93d78a01`, gossipsub v1.1 and ethrex at `64b8fc09` (decision record 0051); version 2 decodes a recent-root verifier frame's tuples and takes a head's slot from its `slotNumber` (decision record 0053) |
| `docs/spec/12-replay.md` | Version 2. A procedure for the plan's item 43: a profile's verdict on a transaction a chain mined, from its bytes, its receipt's payer and its parent header, and the differences between profile and chain named before any replay (decision records 0052 and 0053) |
| `docs/spec/13-descriptors.md` | Version 2, a proposal. A ruleset as a file a node loads: strict JSON with RFC 8785's canonical form, a CIDv1 identifier of it, rule modules named as their sources name them, inheritance from a parent, completeness, and refusals that name the descriptor and the rule, 8 clauses; `docs/spec/descriptors/` holds EIP-8141's canonical mempool, claim-gated admission and ERC-8421's standard ruleset (decision record 0060); version 2 adds the bond's module, CG-11 (decision record 0064) |
| `docs/spec/14-erc-8421.md` | Version 1. ERC-8421's standard alternative mempool, ERCs pull request 2028 at `493ba8a` (Draft), read into the model as modules of a descriptor: entities and stake, per-entity budgets, `pre_verify` frames, trace and storage rules with association, keyed-nonce lifecycle and limits, local rules, solvency, reputation and blame, 16 clauses (decision record 0061) |
| `docs/aztec-as-not-a-rollup.md` | A reading, not normative: Aztec's node (aztec-node at `54e3383c`, aztec-packages at `5a63848e`) job by job against the clauses and experiments here, what fits, what fits with work and what does not; proposes items 35 and 36 (decision record 0047) |
| `ref/python/emem` | Implements all twelve, the surface's decoding, verdicts, relay and head changes in `surface.py` with a keccak256 of its own (decision record 0051), indexing pending frame transactions by the addresses they read and sealed ones in commitment order, and listing a state's changes from the edits it made since its parent; a builder may leave senders out and add transactions of its own, which no clause makes; 46 unit and randomised invariant tests; its aggregator counts the checks, proofs and folds it does (decision record 0037), and at a relay verifies nothing and builds no aggregate (decision record 0038); its builder counts a block's gas in one sum or, under BB-6's `two`, in two (decision record 0043), and includes a transaction that reverts, or under BB-7 drops it (decision record 0045); `descriptor.py` loads a descriptor and compiles it to a profile, and `framepool/erc8421.py` runs ERC-8421's ruleset as a pool (decision records 0060 and 0061) |
| `conformance/vectors` | 122 files, 868 cases on `base`; every FEE, NP, FP, BB, MA, AG, LU, IL, RR, EN, CG, SF, RP, DS and AM clause has one except the ten profile tables and LU-2, the object, and so do MD-6 to MD-8, MD-10 and MD-11; the `surface` set's bytes are mined transactions or ethrex's golden vector, its expected values the chain's, the client's or derived by hand (decision record 0051) |
| `bench` | leanVM's own benchmark at `1f9e4c4f`, run once on this machine, and the table and AG-9 costs derived from it, checked by `make checks` (decision record 0033); and the memory leanVM takes to prove one aggregate over inputs made first, with AG-10's costs and their envelope (decision records 0041 and 0042) |
| `sim/emem_sim` | Seeded event loop, go-ethereum's broadcast and fetcher, rotating proposers, finality on the beacon chain's happy path, Poisson wallets with their own random streams, shared-sender spends, sponsored users, wallets that resend and give up at a deadline, adversaries that send junk spends, rest many transactions on one payer, or keep every pool full of transactions no builder includes, that pay only for the block they fill, or that a default-code sponsor drains in the next block, EIP-8288 wrappers and each node's aggregate every interval (decision record 0013), EIP-8184 sealed senders that resend and may reseal and a flood of sealed transactions that tolerate no commitment before them (decision record 0015), a frame pool profile per node, blocks built by a subset of nodes, budget hints in announcements and nodes that lie in them (decision record 0016), an inclusion-list committee drawn each slot, missed slots, and builders and includers that filter with four strategies and what filtering cost them (decision record 0018), an adversary whose sponsors hold nothing or are drained every block (decision record 0019), spends handed out as copies with the nullifier in a nonce key or a storage slot (decision record 0020), when and from whom every node first heard of each transaction, and a spy connected to every node that relays nothing (decision record 0021), an aggregate sent after its proving time, a node proving one at a time (decision record 0034), wallets that meet MATCHA's load floor (decision record 0022), a slot for every block, builders drawn at random each slot, a root source that writes a recent root every slot and spends proved against one that are proved again when a node refuses their root (decision record 0023), wallets that re-price their oldest pending transaction or every one, users who stop at a price of their own and spend users who sign a re-priced version (decision record 0024), nodes that verify proofs under one key in batches they hold for a window (decision record 0025), spends that read a slot of their own or a root a depositor rewrites, and junk that reads a setting each or one in each of many applications (decision record 0026), sealed senders whose key publishers withhold (decision record 0027), a committee that settles a batch of intents and re-prices it (decision record 0028), a committee that clears a batch every block from a block or from the pool at a cutoff (decision record 0029), spends in EIP-8266's expiring-nonce mode with their nullifier in storage, signed again when a version can no longer make the next block (decision record 0030), hot wallets that send at once, serially or in batches, and a sponsor that upgrades their accounts with authorizations they sign at their next nonce (decision record 0031), transactions with admission claims and wallets that buy a fresh one, floods with claims, with junk proofs or from senders of each head's own, adversaries that put an honest claim on a transaction of their own or send an honest transaction again with a junk proof, and each node's checks, proofs and folds by who sent them (decision record 0037), relays that verify nothing and forward what they accept, and the proofs reaching each node by who made them (decision record 0038), an open-role updater that proves a pool's root from its chained outputs, racing or backing off (decision record 0039), blind tickets bought under a key at a Poisson rate and spent from a shared sender after a holding time from the block that carried them, through the node bought at or a random one (decision record 0040), blocks that count state gas apart under BB-6's `two`, and transfers and spends that carry EIP-8037 state gas (decision record 0043), transactions that revert and builders that drop them (decision record 0045), shuffle rounds in the public pool, sealed or locked at inclusion, with a griefer that holds one seat a round (decision record 0046), a node's defences against a self-issuer's junk proofs: issuer memory, a node list (decision record 0059) and a bond on the ticket paymaster with ERC-8421's reputation (decision record 0062), independent runs in parallel, recorder with what builders skipped, the route each transaction reached its proposer by, each block's sealed commitments and when each transaction was first listed |
| `experiments/00-baseline` | Propagation, inclusion and base fee through a burst; finds the stuck-nonce backlog |
| `experiments/01-one-pending-ceiling` | A shared sender under `one` and `disjoint-keys`: the ceiling is one spend a slot, the delay below it is $\frac{s/2}{1-\rho}$, and who submits decides how long a nullifier is public |
| `experiments/02-matcha` | The same sender under MATCHA: the ceiling lifts after a cold start of about 19 minutes, the cap becomes a ceiling of its own, balance reuse is what makes it work for a sender that pays, mass invalidation is bounded by width, and draining costs delay rather than throughput |
| `experiments/03-revalidation-cost` | One 21,000-gas transfer makes every node re-run every transaction resting on its payer, up to `max_pending`; reservations bound value, not count; each profile leaves a path open, the canonical paymaster under both; balance reuse removes it all, and honest overload does the same work |
| `experiments/04-eviction-order` | Under EIP-8141's order a free flood keeps every transaction with a deadline out of every pool for as long as it lasts and stays in them after; go-ethereum's order by price and a tip-first variant let it push out only what builders would not include now, but the variant opens the pool to transactions that expire before the next block; honest overload lands the same transactions under either order |
| `experiments/05-expiry-timestamp` | Checking a deadline against the next slot's timestamp instead of the head's turns an expiring flood into a purchase of every block it fills and costs honest wallets nothing measurable; it leaves open a cheaper flood, transactions a default-code sponsor backs and drains in the next block, which empties a full pool for one transfer a block under every `eip-8141` variant and which only `hegota-testnet`'s cap on codeless payers refuses |
| `experiments/06-in-mempool-aggregation` | Under EIP-8288's wrapper cap, read as binding aggregates, aggregation is a queue: nodes keep and copy one leanSTARK transaction each, the network carries fewer distinct transactions a slot than the reading of the cap as a limit on users' wrappers alone, inclusion slows as demand rises though gas never binds, and what lands mostly lands by the wallets' resend; without the cap aggregation costs about a tick a hop and little in inclusion, forwarding users' wrappers matches gossip and sends every proof in the clear, and a node sends one recursive STARK per peer per interval |
| `experiments/07-sealed-admission` | Below the 32 commitments a block takes the policy does not matter; near them a payment's hash decides how long it waits, which resealing turns into a lottery under `every-head`; the EIP's own low-ToB flood shuts payments out of every pool under `any` and not under the other two policies, a flood that comes first gets past all three and outlives itself under the EIP's only order, and dropping first what has no place in the next block keeps every payment |
| `experiments/08-verify-floor` | Under EIPs pull request 12301's floor a spend above it reaches the cluster of nodes with headroom it starts in, so the gradient the pull request describes is a cutoff once those nodes stop being connected; it lands only because every node here proposes, and none lands when the nodes that build lack headroom; a budget hint saves fetched copies and not pushed ones, and a lie in one that a node remembers suppresses an announced spend at the floor as well as above it |
| `experiments/09-focil` | Without inclusion lists a filtered transaction waits for a builder that does not filter; with them it waits about as long as anyone's where such a builder can take the slot, and filtering then costs the filtering builders a large share of their fees; when every builder filters the lists include nothing and the cost falls on burned gas or missed slots; at full blocks the excuse is free only for a transaction as large as those filling the block; EIP-8369's Profile 2, and not EIP-7805 alone, gets private spends listed, including the ones experiment 08 could not get into a block |
| `experiments/10-wasted-work` | A transaction whose sponsor holds nothing is refused by the node it is handed to and goes no further, so the network does the work the adversary hands it and no more; a sponsor drained every block gets each of its transactions run twice by nearly every node under the specification, so the work grows with the network's size and the number of transactions one balance backs, for one transfer a round; the testnet's cap on codeless sponsors, which the EIP leaves out, bounds each node's share |
| `experiments/11-spend-copies` | With a spend's nullifier in its nonce key, the pool merges its copies, each pool keeps one and drops it without a run once another lands, and checking FP-12 before the prefix makes the copies cost no more than one; with the nullifier in a storage slot every pool holds every copy and re-runs all of them when one lands, so one copy for every node costs work that grows as the square of the network |
| `experiments/12-timing-channel` | A spy connected to every node names the node a spend entered by four times in five, and ordinary nodes that log do as well from a fifth of the network; both hear of it within a tenth of a second, because a hash is announced at once and the arrive timeout delays only the fetch; inclusion lists cut how long a filtered spend is held to about a slot, and leave the join, so the channel is not closed by them |
| `experiments/13-load-floor` | MATCHA's optional load floor charges the users of a shared sender for each other's pending spends and never charges a user who sends alone; at 1 gwei it raises half the spends at three a slot, unequally by where a spend falls in the slot, and a wallet that does not read it waits minutes instead; at 0.01 gwei it almost never binds against tips up to 3 gwei, and its deterrent is as small |
| `experiments/14-recent-roots` | Under EIP-8272's window no spend outlived its root, with nine builders in ten leaving out the spends or the root writes, because a delay must last on the order of 8191 slots; a window has to come down to the delay before spends are proved again; a node drops spends by index when their root expires and re-runs nothing; when root writes stop, spends continue for exactly the usable window and then stop, and a node's margin shortens that slot for slot |
| `experiments/15-fee-bumping` | Wallets that re-price clear the backlog experiment 00 left, by NP-11's least bump only if it reaches every stranded transaction, and to the market even from the oldest alone; with demand that pays what the next block asks the base fee climbs while the queue lasts, and users with a price of their own stop the climb by leaving; a shared sender under `one` keeps landing spends once other wallets bump only if its users re-price to the market every block |
| `experiments/16-batched-admission` | Nodes that verify proofs under one key in a batch held for a window, at Commonware's measured cost: a batch is about the rate under the key times the window, each hop pays the window, and the delay to a block grows less than the delay to the network; read as gas, a batch of 6 brings a one-nullifier spend under `MAX_VERIFY_GAS`, a 0.06 s window at 100 proofs a second and 40 minutes at the busiest a privacy pool has been; one invalid proof for every ten valid ones costs a node that batches more than one that does not, and its sender nothing |
| `experiments/17-contention-classes` | MATCHA's baseline taken per contention class (MA-14): read off the storage a prefix reads, a pool whose spends read none of it gets `disjoint-keys`' delays at about `sender`'s attacker ratio, 6.90 against 7.10, and its junk is bounded only by pool size and eviction; read per slot, a nullifier kept in storage gets the same, and an application with a setting for each junk spend gets 13.25 work per gas, above `one`'s 8.76 with a hundred applications; a spend that reads a root rewritten every block lands 365.25 an hour under every indexing |
| `experiments/18-withheld-keys` | Key publishers that withhold every key they are named for, against experiment 07's sealed payments: a withheld key costs its sender a ticket and a block, and the chain nothing; sent again sealed at 16 payments a slot, every payment runs and the 99th percentile rises from 23.94 s to 256.42 s with half the publishers withholding; at 28 a slot withheld commitments take 13.38 of a block's 32 places and 1239 of 1498 payments run by the end; sent again in public, a payment keeps its delay and about the withholding share goes public; the policies matter less than the withholding; a flood that withholds pays 1010311606824866.75 wei a commitment rather than 18150406804575.83, for the same damage |
| `experiments/19-committee-settlement` | A committee's settlement of users' intents, at Merces's gas: settling every block meets the one-block floor, a median of 12.56 s, at 1562933.88 gas a transfer with an intent a slot, which a full-batch rule brings to at most 914659.64 at a median of 168.84 s; rounds longer than a slot cost an account one block and a frame transaction under one key more, since it cannot pipeline; a burst stops a committee that does not re-price, 467 of 627 intents unsettled, and one with a nonce key for each batch pays 38435320615574192.00 wei a transfer settled for 729 reverted settlements; re-pricing every block settles everything, at a 90th percentile of 216.51 s |
| `experiments/20-per-block-clearing` | A committee of three nodes that clears a batch every block: from the chain, the last member's import of the block and the settlement's way to the proposer leave 134 rounds at 80 ms in a 12 s slot and 34 in a 4 s one, against budgets of 150 and 50 rounds from an earlier survey of committees, so a tree tournament's 49 rounds settle a block late at 4 s and a collaborative proof's 63 fall behind without bound; from the pool at a cutoff the whole budget is usable, at a delay that grows with the rounds, from 7.30 s at 2 rounds to 19.07 s at 150 at 12 s; the margin before the block must cover the settlement's 0.32 s 99th percentile |
| `experiments/21-expiring-nonces` | A shared sender in EIP-8266's expiring-nonce mode, its nullifier in storage: where nodes take the EIP's MAY to admit several pending, the ceiling goes as under `disjoint-keys`, for 13,703 gas more a spend; where they do not, every spend has one identity, so a relayer misses 55 slots in 1200 to the fetcher's memory of `ErrReplaceUnderpriced` and users who send their own spends are served by tip |
| `experiments/22-delegated-accounts` | A hot wallet under NP-6 and a sponsor's upgrade of sixteen busy accounts under NP-7 and BB-5: a delegated account lands 299.00 transfers an hour, experiment 01's ceiling, and 3552.50 of 3600 when it batches, at a median of 17.46 s; an authorization races its account's own transfers, so of sixteen accounts sending four transfers a slot none was upgraded in batches of 16, and 416 skipped authorizations cost the sponsor 10,400,000 gas, while wallets that drain before signing were upgraded in 24.96 s in batches of 16, with nothing lost |
| `experiments/23-committee-keys` | A threshold committee as LUCID's key publisher: with a third of the members withholding, two thirds of 64 released 0.0350 of its keys at a lateness of 0.1 and a majority released all of them; keys that fail together in a slot lengthen the tail at the same share released; senders that go public or release their own key keep a failing committee to a ticket's loss; a rotation loses only what waits across it |
| `experiments/24-proving-budget` | Proving time at costs fitted from leanVM on this machine: a budget of one interval holds no recursive input, so nodes that keep to it aggregate nothing with a leanSTARK dependency and transactions land by their wallets' resends, at a median of 57.84 s; nodes that ignore it keep aggregating at their own cadence, at 13.97 s; at the laptop's costs aggregation fits the interval and a flood that never pays takes its slack; a share of provers is a share of proposers |
| `experiments/25-ticket-defences` | Under version 4 of claim-gated admission a self-issuer's junk proof costs every node a ticket check, a prefix and a proof, and the self-issuer nothing after one deployment; issuer memory caps what one paymaster buys a node an epoch but lets one honest ticket an epoch close an honest issuer at every node; a node list ends the junk and costs honest spends the nodes that do not list their issuer |
| `experiments/26-ticket-bond` | A bond on the ticket paymaster, ERC-8421's stake and reputation: one staked paymaster is banned at every node after 510 junk proofs there, and each hourly refresh reopens it for 22, for a stake locked 1.08 ETH-days; more paymasters buy more, a stake each; a holder of honest tickets cannot throttle a busy issuer at 64 tickets an epoch, and throttles a small one without refusing its spends; the bond is 1.11 days of a small issuer's sales (on `exp/26-ticket-bond`) |

## Items

Each item is a question an experiment answers, or a part of the base an
experiment needs. A finished item's result is in its experiment's
`results.md` and README on `main`, and "What exists" above gives it in one
line; the decision records hold the readings each rests on. Numbers are kept
from before publication. Items 27 to 34 list the clauses, loads and records
they added; their experiments are not part of this repository.

### Done

1. **The one-pending-transaction ceiling.** *Done, 2026-10-07:*
   `experiments/01-one-pending-ceiling/`, a shared sender under `one` and
   `disjoint-keys` (decision record 0005).
2. **MATCHA.** *Done, 2026-10-07:* `docs/spec/04-matcha.md` as a proposal
   (decision record 0007) and `experiments/02-matcha/` (decision record
   0008).
3. **Revalidation cost.** *Done, 2026-10-08:*
   `experiments/03-revalidation-cost/`, with the `reuse_balance` variant of
   FP-15 (decision record 0009).
4. **Eviction order as an attack surface.** *Done, 2026-10-08:*
   `experiments/04-eviction-order/`, with the `evict_first` variant of
   FP-14 (decision record 0010).
5. **The expiry timestamp question.** *Done, 2026-10-08:*
   `experiments/05-expiry-timestamp/`, with `expiry_margin` (decision record
   0011).
6. **Propagation as a timing channel.** *Done, 2026-10-09:*
   `experiments/12-timing-channel/` (decision record 0021).
7. **Delegated accounts.** *Done, 2026-10-09:* `00-model.md` version 5,
   `03-block-building.md` version 2 and `experiments/22-delegated-accounts/`
   (decision record 0031).
8. **Wallet behaviour.** *Done, 2026-10-09:* `experiments/15-fee-bumping/`
   (decision record 0024).
9. **In-mempool aggregation (EIP-8288).** *Done, 2026-10-08:*
   `docs/spec/05-aggregation.md` and `experiments/06-in-mempool-aggregation/`
   (decision records 0012 and 0013).
10. **LUCID (EIP-8184).** *Done, 2026-10-08:* `docs/spec/06-lucid.md` and
    `experiments/07-sealed-admission/` (decision records 0014 and 0015).
11. **A shared floor for the validation budget.** *Done, 2026-10-08:*
    `experiments/08-verify-floor/`, EIPs pull request 12301 read at
    `f3538f20` (decision record 0016).
12. **MATCHA's load floor.** *Done, 2026-10-09:* MA-13 in `04-matcha.md`
    version 2 and `experiments/13-load-floor/` (decision record 0022).
13. **Wasted work against network size.** *Done, 2026-10-09:*
    `experiments/10-wasted-work/` (decision record 0019).
14. **Batched admission.** *Done, 2026-10-09:*
    `experiments/16-batched-admission/` (decision record 0025).
15. **Expiring nonces for a shared sender.** *Done, 2026-10-09:*
    `docs/spec/09-expiring-nonces.md` and `experiments/21-expiring-nonces/`
    (decision record 0030).
16. **Width by contention class.** *Done, 2026-10-09:* MA-14 in
    `04-matcha.md` version 3 and `experiments/17-contention-classes/`
    (decision record 0026).
17. **FOCIL and builders that filter.** *Done, 2026-10-09:*
    `docs/spec/07-focil.md` and `experiments/09-focil/` (decision record
    0018).
18. **One spend, many copies.** *Done, 2026-10-09:* `static_first` in
    `02-frame-pool.md` version 5 and `experiments/11-spend-copies/`
    (decision record 0020).
19. **Recent roots that expire in the pool.** *Done, 2026-10-09:*
    `docs/spec/08-recent-roots.md` and `experiments/14-recent-roots/`
    (decision record 0023).
20. **Withheld LUCID keys.** *Done, 2026-10-09:*
    `experiments/18-withheld-keys/` (decision record 0027).
21. **Shuffle rounds in the pool: the clauses and the load.** *Done,
    2026-10-13:* `00-model.md` version 8 gives a transaction pulls from
    accounts that signed for it, `03-block-building.md` version 4 includes a
    transaction that reverts, or under BB-7 drops it, and the simulator's
    `ShuffleRounds` sends rounds with a griefer that holds one seat (decision
    records 0045 and 0046).
22. **A committee's settlement through the pool.** *Done, 2026-10-09:*
    `experiments/19-committee-settlement/`, at Merces's gas (decision record
    0028).
23. **A committee that clears every block.** *Done, 2026-10-09:*
    `experiments/20-per-block-clearing/` (decision record 0029).
24. **A threshold committee as LUCID's key publisher.** *Done, 2026-10-13:*
    `experiments/23-committee-keys/` (decision record 0032).
26. **Proving time in the aggregation interval.** *Done, 2026-10-13:*
    `bench/leanvm/` and `experiments/24-proving-budget/` (decision records
    0033 and 0034).
27. **A user's own proof, and how fast junk is rejected.** *Done,
    2026-10-13.*
28. **Claim-gated admission as a profile, and the framing attack.** *Done,
    2026-10-13:* `docs/spec/10-claim-gated-admission.md` and its vectors
    (decision record 0037).
29. **Who verifies sets the price.** *Done, 2026-10-13:* CG-7 in
    `10-claim-gated-admission.md` version 2 (decision record 0038).
30. **The timing linker in a real pool.** *Done, 2026-10-13:* the
    simulator's `Tickets` (decision record 0040).
31. **Chained outputs and an open-role updater.** *Done, 2026-10-13:* the
    simulator's `Updater` (decision record 0039).
32. **Memory as a constraint on who proves.** *Done, 2026-10-13:*
    `bench/leanvm-memory/` and AG-10 in `05-aggregation.md` version 3
    (decision records 0041 and 0042).
33. **Shuffle rounds in the pool.** *Done, 2026-10-13,* as item 21.
34. **The nullifier floor under state pricing.** *Done, 2026-10-13:* BB-6's
    two dimensions in `03-block-building.md` (decision records 0043 and
    0044).
42. **The surface a frame pool sits behind.** *Done, 2026-10-20:*
    `docs/spec/11-surface.md` and its vectors (decision record 0051). Two
    skandha nodes took a frame transaction over JSON-RPC and gossip and an
    ethrex node mined it, both nodes reaching the same verdict at every head
    (skandha, `docs/frames/runs/2026-10-20-two-nodes/README.md`).
43. **Replay of mined transactions.** *Done, 2026-10-20:*
    `docs/spec/12-replay.md` and its vectors (decision record 0052);
    skandha's `packages/framepool/replay/results.md` over all 188 of
    `exp-frames`' fixtures, none disagreeing.
45. **Shared-sender admission, both ways.** *Done, 2026-10-20:*
    `conformance/vectors/frame-pool/fp-12-shared-sender.json`, on
    `exp-frames` experiment 06's mined pair (decision record 0054); skandha
    plays them.
46. **An includer, with a budget per list.** *Done, 2026-10-20:*
    `07-focil.md` version 2 and its vectors on `exp-frames` experiment 25's
    transactions (decision record 0055); skandha's node answers
    `skandha_frameInclusionList`.

### Started

49. **Claim-gated admission in a second implementation.**
    `10-claim-gated-admission.md` and its vectors implemented in TypeScript,
    with a BLS12-381 library for the ticket. *Started, 2026-10-20:* version
    3 on `base` gives the ticket its bytes, its check and its frame, CG-8 to
    CG-10, in the format a wallet ran on the Hegota testnet (decision record
    0056); skandha plays all 61 ticket vectors on `@noble/curves`, and
    claim-gated admission with received wrappers. *Done on `base`,
    2026-10-20:* version 4 accepts as a ticket paymaster any account whose
    code is the template, a key and a denomination (decision record 0057),
    and `11-surface.md` version 3 reads the claim from a real transaction
    and checks it before the client is asked (decision record 0058); a
    skandha node does both against the testnet with no configuration.
    *Finished, 2026-10-20:* on `main` through
    [4w44h9jckz-boop/exp-mempool-l2s#2](https://github.com/4w44h9jckz-boop/exp-mempool-l2s/pull/2),
    at `10fd022`.
50. **A self-issuer's junk proofs, and two defences.** Version 4 accepts
    any ticket paymaster, so anyone can issue tickets to themselves, and a
    junk proof costs every node a ticket check, a prefix and a proof while
    costing its self-issuer nothing after one deployment. What do issuer
    memory, for two values of $k$, and a node list cost, in node work, in
    the attacker's spend and in honest senders' delay? Both are modelled in
    the simulator and neither is specified (decision record 0059); the
    choice between them stays open. *Done on `exp/25-ticket-defences`,
    2026-10-20:* `experiments/25-ticket-defences/`, in
    [4w44h9jckz-boop/exp-mempool-l2s#3](https://github.com/4w44h9jckz-boop/exp-mempool-l2s/pull/3).
    *Finished, 2026-10-20:* on `main` at `badebcc`, and on `base` since
    `3a80a7d`. A third defence, a bond, is item 52, and the one chosen.
51. **Rulesets as descriptor files.** A ruleset a node loads from a file:
    a canonical encoding and an identifier derived from it, rule modules
    named as their sources name them, inheritance from a parent, and
    refusals that name the descriptor and the rule. *Done on `base`,
    2026-10-20:* `docs/spec/13-descriptors.md` and three descriptors in
    `docs/spec/descriptors/`: EIP-8141's canonical mempool, claim-gated
    admission and ERC-8421's standard ruleset (decision record 0060), at
    `461702b`. skandha loads all three from files and plays every
    descriptor vector, each refusal checked for the rule it names; its node
    runs a descriptor with `--frames.descriptor`.
52. **A bond on the ticket paymaster.** Item 50's self-issuer and holder
    of honest tickets against a third defence: ERC-8421's stake and
    reputation for the ticket paymaster as an operator, with item 44's
    parameters. Modelled in the simulator, not specified (decision record
    0062). *Done on `exp/26-ticket-bond`, 2026-10-20:*
    `experiments/26-ticket-bond/`, at `b6a3157`. *Chosen, 2026-10-20:* the
    owner chose the bond, and it is a clause: `10-claim-gated-admission.md`
    version 5, CG-11, with `cg-11-bond.json` and the reference (decision
    record 0064), at `3518573` on the session branch, in its own pull
    request,
    [4w44h9jckz-boop/exp-mempool-l2s#6](https://github.com/4w44h9jckz-boop/exp-mempool-l2s/pull/6),
    after the `base` and experiment 26 pull requests. *Finished,
    2026-10-21:* #4, #5 and #6 merged; `main` at `ff529ef`, and `base`
    fast-forwarded to it.
53. **A private transfer with a nonce key per nullifier.** An Aztec-model
    transfer from a shared contract: its `VERIFY` frame checks the user's
    proof, and each note it spends is one EIP-8250 nonce key. Does the
    specification already say how a node admits it, relays it and refuses
    its double spend before inclusion? *Done on the session branch,
    2026-10-21:* yes, with two of EIP-8250's key-set rules FP-3 had missed,
    at most 16 keys and key 0 only alone: `02-frame-pool.md` version 8 and
    `fp-12-nullifier-keys.json` (decision record 0065), at `8710ba1`, in
    [4w44h9jckz-boop/exp-mempool-l2s#7](https://github.com/4w44h9jckz-boop/exp-mempool-l2s/pull/7).
    Under `eip-8141` a transfer spends at most 5 fresh nullifiers, since each
    costs 97,920 state gas. The wallet's real transfer is still to come.
54. **A committee's result and its shared-state update.** A result whose
    `VERIFY` frame checks a committee's threshold signature, and an update
    sent from the committee's account with a payer: how does FP-11's one
    pending transaction for a non-canonical payer apply to each, and what
    does it cost a committee that posts often? *Done on the session branch,
    2026-10-21:* no clause is new; `fp-11-committee.json` and decision
    record 0066, at `7385a0f`, in #7. A BLS check is above `eip-8141`'s
    verify budget; a non-canonical paymaster lands at most one of the
    committee's transactions a block. The committee's own shapes are still
    to come.
55. **A ticket bound to its transaction.** A ticket names one slot and
    nothing the transaction does or pays, so whoever forwards a transaction
    whose sender does not sign can change its fee or calldata and keep the
    ticket. Can the ticket's message commit to a one-time key the buyer
    chose, so that only that key's signature over the transaction's
    signature hash makes the claim count, with nothing asked of the issuer
    when it is spent? *Done on the session branch, 2026-10-21:*
    `10-claim-gated-admission.md` version 6, CG-12 (decision record 0067),
    at `fdc4bb3` and `cb18a37`, in #7. The binder's signature is a
    `secp256k1` entry of the transaction's own list, checked by the protocol
    over the signature hash, and every copy with a signed field changed is
    unbound. The bound template is still to come from the wallet session.

44. **An ERC-8421 profile.** Read from ERC-8421: stake and reputation for
    paymasters and other operators, and what a fresh sender is asked for.
    *Done on `base`, 2026-10-20:* `docs/spec/14-erc-8421.md` reads the
    standard ruleset of ERCs pull request 2028 at `493ba8a` into the model,
    as item 51's `erc-8421.json`, and the reference runs it as a pool
    (decision record 0061). A staked paymaster's 500,000-gas frame is
    admitted under it, and a fresh sender is asked for nothing the frame
    pool does not ask (AM-16); skandha plays every vector of it. Item 52
    prices its stake and reputation as a defence.
47. **The aggregator.** AG-5 and AG-7 to AG-9 as testable clauses for the
    schemes EIP-8288 defines, its hash-based signatures, with the STARK scheme
    reserved as the EIP marks it. *Done on `base`, 2026-10-20:*
    `docs/spec/05-aggregation.md` version 4 reads EIP-8288 again at master
    `899bef0a` as a second profile, `eip-8288-master`, beside the pinned
    one, with leanSTARK reserved (decision record 0063), at `2df1fa0`; five
    vector files under it. skandha's aggregator plays every AG-7, AG-9 and
    AG-10 vector, and two of its pools, each with an aggregator, fold the
    same leanSPHINCS dependencies and each accept the other's fold, also
    after a block drops two of them. Two running nodes cannot exchange a
    fold until the EIP chooses `AGGREGATED_VK` and `DEPS_HASH`.

### Not started

25. **Sealed inputs to a committee's computation.** Computing on sealed
    transactions takes its inputs from the chain; what delivering them as
    Merces delivers amounts costs, and whether bids that are transactions
    can be sealed until a cutoff.
35. **Aztec's pool as a profile.** From `docs/aztec-as-not-a-rollup.md`
    (decision record 0047): a pool that keeps no sender and knows a
    transaction by its nullifiers.
36. **Aztec's pool on L1.** A shared sender's private spends at 12-second
    slots with a proof check of 250 ms, under FP-12's `one`, `disjoint-keys`
    and item 35's profile.
37. **A committee's shares at sizes a scheme names.** Experiment 23 counts a
    share at an assumed 32 bytes; Commonware's Simple BTE gives sizes to
    count instead.
38. **A committee's batch: a window or a position.** Commonware's "Pick Your
    Poisons" (`/blogs/pick-your-poisons`, 2026-07-22) on the compromise every
    batched threshold encryption scheme makes.
39. **Private payments without a shared sender, as a profile.** Commonware's
    Bonsai (`/blogs/private-payments`, 2026-09-12): one commitment an
    account.
40. **A peer that sends an invalid proof.** Blocking the sender of a failed
    batch, which experiment 16 lists as not tested, after Commonware's
    buffered signatures (`/blogs/buffered-signatures`, 2025-05-28).
41. **Conclusions on more than one seed.** Every experiment runs one seed;
    Commonware's runtime runs about ten in each CI run (decision record
    0049).
48. **The sealed subpool and a key publisher.** `06-lucid.md` as it stands,
    and the key publisher's side: when it releases a key, and what a
    withheld key leaves behind. Taken on 2026-10-20 by a second session, on
    branch `m7-lucid`, merged into `base` when done; it takes decision
    records 0070 to 0079 and logs in `log/YYYY-MM-DD-m7.md`.

## Growing the base

To be added when an experiment needs it, not before:

- **A second implementation.** *Started, 2026-10-13* (decision record
  0035): a fork of etherspot/skandha, an ERC-4337 bundler, is the base for a
  second implementation of the frame pool's clauses, in TypeScript, judged
  by a byte-for-byte copy of `conformance/vectors/`, with `docs/spec/` still
  normative. Its `packages/framepool` is a port of `ref/python/emem/` and
  plays every case it has the parts for: 212 of 473 on 2026-10-13, and 303
  of 653 on 2026-10-20, none failing, the rest needing the account-nonce
  pool, the sealed pool, block building, claim-gated admission or the
  aggregator. Its node takes frame transactions over JSON-RPC and gossip
  (item 42), and runs a ruleset from a descriptor file (items 44 and 51). Next: the aggregator (item 47), and an implementation
  written from the clauses without reading the reference, which is what
  would test the clauses rather than the vectors' independence from Python
  (decision record 0050).
- **Differential checks against real clients.** Play the nonce-pool vectors
  against `geth --dev` over JSON-RPC, and the frame-pool vectors against the
  ethrex Hegota testnet through `exp-frames`' tooling, to measure the
  `hegota-testnet` profile instead of citing it. This needs signing and RLP, so
  it lives outside `make verify`. Two probes belong here:
  - a pay frame declared below the gas it uses, which an earlier study
    found admitted and never included, with no error, on one client;
  - `exp-frames`' planned mempool rule probing (branch `plan`, "After the
    examples"): banned opcodes in the prefix, storage reads outside the
    sender and prefix gas caps, with simulated verdicts compared against
    `eth_sendRawTransaction`.

  The work a node spends to reject an invalid spend, $w$, in wall time per
  core, also needs a client: the simulator counts gas.
- **More pools and channels:** the blob pool (EIP-4844, eth/72 cell gossip),
  private order flow to builders, an encrypted mempool. FOCIL inclusion
  lists (EIP-7805) as a constraint on the builder arrived with item 17
  (`docs/spec/07-focil.md`). ERC-4337's
  mempools under ERC-7562 are not modelled, so questions about them, such
  as whether mempool privacy is permissioned by capital and whether one
  design gets two admission verdicts, wait for an ERC-7562 pool.
- **Scale:** incremental counters in the reference if an experiment needs
  hundreds of nodes. The baseline runs 30 nodes for 30 simulated minutes in
  about 35 seconds. Since experiment 04 the frame pool indexes its
  transactions by the addresses they read, so a reset re-checks only those
  that read an account the block touched.

## Open questions in the simulation

- A relayer under `one` races the block it is waiting for (experiment 01).
  Whether real clients show the race depends on block import times, which this
  network draws uniformly between 0.1 and 1.0 s; a measured distribution would
  settle how often a slot is lost.
- A node never forgets which transactions a peer knows, so a resent sealed
  transaction with an unchanged hash does not spread again (experiment 07).
  A client's record is bounded, and how long it remembers decides how much
  resealing is worth.
- Under the capped reading of EIP-8288, a proving delay of a full interval
  shortened inclusion (experiment 06). The model is consistent with fewer
  nodes copying the first to choose after a block, and does not show it;
  counting, per tick, how many nodes list the same transaction would.

## Open questions in the specification

- `hegota-testnet` and EIP-8272: *settled 2026-10-20.* The profile takes
  `08-recent-roots.md`'s recent roots at the testnet's constants, and the
  surface decodes the verifier frame's tuples (decision record 0053), after
  the replay explained 10 Hegota fixtures only by `recent-roots` and a
  wallet's withdrawal was refused by skandha for the same reason.
- SF-8: whether a client should return the sender slots a prefix read, so
  that a pool without an EVM can index by them instead of asking about every
  pending transaction at every head (decision record 0051). A request to
  ethrex.

- FP-15: whether a node should require a fee cap near the base fee, or bound
  how many pending transactions one payer backs; reservations bound neither
  (experiment 03). And whether `reuse_balance` should be proposed for the
  EIP, which asks for revalidation without re-execution only for prefixes of
  protocol-defined frames.

- MA-6: whether the width check should come before the prefix runs, so that
  a refusal for width costs a node nothing (experiment 02).
- MA-4: whether width counts state gas, and what `width_cap` should be; the
  cap has to hold an epoch of a sender's gas or it caps throughput
  (experiment 02).

- FP-14: whether a deadline should rank before price. Under the EIP's order
  transactions no builder includes can empty a pool of every transaction with
  a deadline; under a tip-first order, transactions that expire before the
  next block can empty it of everything (experiment 04).
- FP-15: which timestamp the expiry check uses. The next slot's costs honest
  wallets nothing measurable and makes an expiring flood pay for every block
  it fills (experiment 05); missed slots are not measured.
- FP-11: whether a node should cap how many pending transactions a
  default-code sponsor backs, as `hegota-testnet` does. The EIP leaves it to
  the exposure rule, and a sponsor that drains itself in the next block
  empties a full pool for one transfer a block under every `eip-8141`
  variant (experiment 05).
- AG-5 and AG-7: whether the wrapper limits bind an aggregate. Read as
  checks, they make aggregation a queue that carries fewer distinct
  leanSTARK transactions a slot than one node's ticks, and inclusion rests
  on wallets resending; read as limits on a user's wrapper only, aggregation
  costs about a tick a hop (experiment 06). A question for the EIP's
  authors.
- AG-7: whether a node relays a user's wrapper at once. Doing so matches
  gossip's delay and sends every direct proof to every peer; the text sends
  only aggregates (experiment 06).
- AG-7: what a builder receives grows with its peers, one recursive STARK
  from each every interval, where the Rationale gives "a fixed ~256 kB per
  `AGGREGATION_INTERVAL`" (experiment 06).
- LU-8: which reading of "no chance of getting included" a pool should
  take. `any`, the profile's, admits the denial-of-service vector the EIP
  names; `next-block` and `every-head` refuse it, and `every-head` holds
  less for the same delays (experiment 07).
- LU-10: whether a full sealed pool should drop first what the next block
  would pass over. Under the commitment order, a flood whose transactions
  come first replaces every honest one under every policy and outlives
  itself; `unplaced` kept every payment (experiment 07). A question for the
  EIP's authors.
- FP-6, under EIPs pull request 12301: whether a floor with headroom above
  it can promise anything to a transaction above the floor. Every private
  spend measured is above it, and reaches only the cluster of nodes with
  headroom it starts in (experiment 08). And whether a budget hint, which
  the pull request leaves to the eth wire protocol, can be acted on at all:
  a node that remembers a lie in one stops fetching a transaction at the
  floor too, and a check on fetch never runs (experiment 08).
- LU-6: whether a tie in ToB fee and gas should be broken by hash, which
  makes a payment's wait near the commitment limit depend on its hash
  (experiment 07).
- FP-13: whether frame transactions share a sender reservation with the
  account-nonce pool in clients. This is decision record 0003's
  interpretation, not something the EIP says.
