# 03. Revalidation cost

**Question.** When many pending frame transactions rest on one payer, how many
prefixes can one block make every node re-run, what does it cost whoever
makes it happen, and what do the profiles' caps and a rule that reuses a
prefix's result on a balance change take away?

**Clauses exercised.** FP-10 (the payer's balance is a dependency of every
transaction it pays for), FP-11 (reservations, and the cap on non-canonical
and, under `hegota-testnet`, codeless payers), FP-12 (one pending transaction
per sender, or disjoint keys), FP-6 (`max_verify_gas`), FP-14
(`max_pending`), FP-3 (no floor on the fee cap), and FP-15, version 2, with
its `reuse_balance` variant (decision record 0009).

EIP-8141 sets its public mempool the goal "to avoid allowing an arbitrary
number of transactions to be invalidated by a single environmental change or
state modification", and says that per-payer reservations bound "aggregate
exposure so that a single balance change cannot invalidate an unbounded set of
pending transactions"; its Revalidation section then has a node re-simulate
every transaction "whose payer's balance or code changed" (Mempool, at
`258836f9`). Reservations limit what a balance change can invalidate. This
experiment measures what it makes a node re-run, which the plan's item 3 calls
the DoS bound the rules buy. Experiment 02 measured one case of it, an
application whose junk spends read a setting it flips every block, at 265.46
times the adversary's gas under `disjoint-keys`
(`experiments/02-matcha/results.md`, section 3).

## Setup

- The network and chain of experiments 01 and 02: nodes with 8 peers each,
  link latency 20 to 100 ms, go-ethereum's gossip, a block every 12 s from a
  rotating proposer, imported by the others 0.1 to 1.0 s later; gas limit
  2,100,000, genesis base fee 1 gwei. Sections 1 and 2 use 10 nodes, because
  every node there holds and re-runs the same transactions and a larger
  network only takes longer; section 3 uses 20.
- Pools: `eip-8141` and `hegota-testnet` (FP-1), and each with
  `reuse_balance` set, under which a change to non-zero balances alone re-runs
  no prefix and FP-15's reservation check stands in for `APPROVE`'s. The
  variant is a proposal, not the EIP (decision record 0009).
- The adversary (sections 1 and 2) sends its transactions to every node at
  30 s, at a fee cap and tip of 1 wei, which FP-3 admits and no builder
  includes, so each reserves only its `max_gas` in wei. They rest on one payer
  it controls, in one of five shapes: a default-code sponsor paying for
  default-code senders, or for senders with code; a canonical paymaster
  instance, which anyone may deploy; a non-canonical paymaster; or one
  shared sender on disjoint nonce keys. A sender with code runs 80,000 gas of
  verification, within `MAX_VERIFY_GAS` beside both signatures. From 60 s, an
  account it controls sends the payer 1 wei in a 21,000-gas transfer, the
  *touch*, which lands in each of the next five blocks.
- Work is counted twice (decision record 0009): re-simulations, which FP-15
  makes observable, and code gas, the declared limits of the prefix frames
  whose target holds code the protocol does not define. Default code and the
  canonical paymaster are evaluated directly ("Direct Evaluation of
  Protocol-Defined Frames") and count no code gas.
- Section 3 has no adversary: users of one paymaster service, each a sender
  with code verifying for 30,000 gas, at 1500 transactions an hour, with 7500
  more an hour for ten minutes, past the block's capacity. Each user resends
  after every block that leaves it out, and nobody raises a fee.
- Seed 1, 28 runs, about two minutes of wall clock.

## Run

```
python3 experiments/03-revalidation-cost/run.py > experiments/03-revalidation-cost/results.md
```

## Results

From [results.md](results.md). The bound, from the profiles' parameters:

| profile | max_pending | max_verify_gas | gas re-run per node per block, at most | adversary's gas per block | ratio |
| --- | --- | --- | --- | --- | --- |
| eip-8141 | 4096 | 100000 | 409600000 | 21000 | 19504.76 |
| hegota-testnet | 4096 | 500000 | 2048000000 | 21000 | 97523.81 |

Section 1, 1024 transactions sent, a subset of its columns and the rows
without `reuse_balance`; every row with it re-simulates nothing. Held is per
node; re-simulations and code gas are per node per block that carried a
touch; the ratio is code gas against the touch's 21,000.

| payer | profile | held | refused as | capital, wei | re-simulations per touch | code gas per touch | ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sponsor, default-code senders | eip-8141 | 1024.00 | none | 53732352 | 1024.00 | 0.00 | 0.00 |
| sponsor, default-code senders | hegota-testnet | 1.00 | ErrFramePaymasterBusy | 52473 | 1.00 | 0.00 | 0.00 |
| sponsor, senders with code | eip-8141 | 1024.00 | none | 130532352 | 1024.00 | 81920000.00 | 3900.95 |
| sponsor, senders with code | hegota-testnet | 1.00 | ErrFramePaymasterBusy | 127473 | 1.00 | 80000.00 | 3.81 |
| canonical paymaster, senders with code | eip-8141 | 1024.00 | none | 126272512 | 1024.00 | 81920000.00 | 3900.95 |
| canonical paymaster, senders with code | hegota-testnet | 1024.00 | none | 126272512 | 1024.00 | 81920000.00 | 3900.95 |
| non-canonical paymaster, senders with code | eip-8141 | 1.00 | ErrFramePaymasterBusy | 128313 | 1.00 | 90000.00 | 4.29 |
| non-canonical paymaster, senders with code | hegota-testnet | 1.00 | ErrFramePaymasterBusy | 128313 | 1.00 | 90000.00 | 4.29 |
| shared sender, disjoint keys | eip-8141 | 1.00 | ErrFrameSenderBusy | 117838 | 1.00 | 80000.00 | 3.81 |
| shared sender, disjoint keys | hegota-testnet | 1024.00 | none | 120692768 | 1024.00 | 81920000.00 | 3900.95 |

Section 2, the sponsor with senders that hold code under `eip-8141`:

| transactions sent | held | capital, wei | re-simulations per touch | code gas per touch | ratio |
| --- | --- | --- | --- | --- | --- |
| 1 | 1.00 | 127473 | 1.00 | 80000.00 | 3.81 |
| 16 | 16.00 | 2039568 | 16.00 | 1280000.00 | 60.95 |
| 256 | 256.00 | 32633088 | 256.00 | 20480000.00 | 975.24 |
| 1024 | 1024.00 | 130532352 | 1024.00 | 81920000.00 | 3900.95 |
| 4096 | 4096.00 | 522129408 | 4096.00 | 327680000.00 | 15603.81 |

Section 3, an honest paymaster service, a subset of its columns. Held and
re-simulations are per node per block, code gas likewise; a canonical
paymaster's transaction is 102,313 gas, so a block holds 6000.00 an hour and
its base fee targets 3078.79.

| profile | payer | asked | landed | delay p50 | p90 | held | held, most | re-simulations | code gas | busy | waiting at end |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | canonical paymaster | 2548 | 2548.00 | 7.43 | 628.34 | 102.74 | 364 | 102.37 | 3071055.01 | 0.00 | 0 |
| eip-8141, reuse | canonical paymaster | 2548 | 2548.00 | 7.43 | 628.34 | 102.74 | 364 | 0.00 | 0.00 | 0.00 | 0 |
| eip-8141 | default-code sponsor | 2552 | 2552.00 | 7.60 | 861.74 | 125.44 | 418 | 125.44 | 3763302.12 | 0.00 | 0 |
| hegota-testnet | default-code sponsor | 1958 | 300.00 | 702.25 | 2187.09 | 0.93 | 1 | 0.93 | 27943.49 | 279.48 | 1658 |

## What it shows

- **Reservations bound what a payer's transactions can cost, not how many
  there are.** Nothing in FP-3 or the EIP's mempool section keeps the fee cap
  near the base fee, so each of the adversary's transactions reserves its
  `max_gas` in wei: 1024 transactions from senders with code on one sponsor
  reserve 130,532,352 wei, and at a fee cap of the base fee they would reserve
  130,532,352,000,000,000, about 0.13 ether. Under `eip-8141` nothing else
  limits a default-code sponsor or a canonical paymaster, and every node held
  all 1024; section 2 fills `max_pending`, 4096, the same way.
- **One 21,000-gas transfer makes every node re-run all of them.** Each touch
  re-simulated 1024 prefixes per node, 81,920,000 gas of sender code, 3900.95
  times the touch's gas; at 4096 transactions it is 327,680,000 gas and
  15,603.81 times, under the bound of 409,600,000 because the signatures and
  the pay frame take part of each prefix's budget. Re-simulation is
  linear in the transactions sharing the payer (section 2), and blocks without
  a touch re-ran nothing. The touch invalidates nothing: every transaction
  stays valid, so the reservation rule holds exactly as the EIP says and does
  not limit this, because what costs is the re-run, not the eviction.
- **Each profile closes some paths and leaves another open.** Under
  `eip-8141`, FP-12's `one` holds a shared sender to one transaction and the
  non-canonical cap holds its paymaster to one, while a default-code sponsor
  and a canonical paymaster back all 1024. `hegota-testnet` caps the
  default-code sponsor too (`ErrFramePaymasterBusy`), but its
  `disjoint-keys` lets one shared sender back all 1024, and the canonical
  paymaster, which the EIP admits without a count because no ether leaves it
  except as payment or after a delay, is open under both. The testnet's
  `max_verify_gas` of 500,000 raises its bound to 2,048,000,000 gas a block,
  97,523.81 times the touch. A canonical paymaster is built so that ether
  cannot leave it, not so that ether cannot arrive, and an arrival is all the
  touch is.
- **Prefixes of protocol-defined frames re-run no code.** A default-code
  sponsor paying for default-code senders is re-simulated 1024 times per
  touch and runs 0 gas of code: a client that follows the EIP's SHOULD and
  evaluates such prefixes directly pays a lookup per transaction. The cost is
  in senders with code, which any adversary can deploy.
- **Reusing the result on a balance change removes all of it.** With
  `reuse_balance`, every row of section 1 re-simulates nothing, under both
  profiles, and the pool keeps exactly the transactions it keeps without it
  (`ref/python/tests/test_invariants.py`). What can still move every
  dependant of a payer at once is then its code, a canonical paymaster's
  delayed withdrawal, or a shared sender's storage (experiment 02,
  section 3), which only the payer or the sender can change.
- **Honest overload does the same work.** When a paymaster service's users
  outrun the block for ten minutes, every block that includes one of them
  moves the paymaster's balance, and every node re-runs everything it still
  holds for it: 102.37 re-simulations per node per block on average and 364 at
  most, 3,071,055.01 gas of code per node per block on average, more than the
  2,100,000 gas the block itself carries. A default-code sponsor under
  `eip-8141` does the same (125.44 and 3,763,302.12). With `reuse_balance` the
  same users land the same transactions at the same delays and nothing is
  re-run.
- **The testnet's cap trades the work for a ceiling.** Under
  `hegota-testnet` a default-code sponsor lands 300.00 transactions an hour,
  one a slot, as a shared sender does under `one` in experiment 01: the
  median delay is 702.25 s, each transaction is refused as busy 279.48 times,
  and 1658 are still waiting at the end. The cap ends the sponsor's fan-out by
  ending its concurrency, and the canonical paymaster it does not reach is
  where the fan-out goes instead.

## What it does not show

- **Time.** The model counts work and charges none: a node that would take
  seconds to re-run 327,680,000 gas of code imports the next block on time
  here. Whether that is a missed slot for a validator or only a slow mempool
  depends on the client, which runs mempool revalidation apart from block
  import or not.
- **Measured gas.** Code gas is the frames' declared limits, the most a
  prefix can spend; a client can also cache signature checks, and the model
  cannot price a direct evaluation at all.
- **Honest traffic beside the adversary.** With a full pool and no honest
  transaction carrying a deadline, FP-14 evicts the adversary's 1-wei
  transactions first, which caps what it keeps at what the honest load leaves
  free. Experiment 04 found the condition matters: FP-14 evicts any
  transaction with a deadline before any without one, so the same 1-wei
  transactions push out every honest transaction that carries a deadline
  (`experiments/04-eviction-order/README.md`).
- **Other shared dependencies:** a paymaster's code or delayed withdrawal,
  which only its owner moves, and the bandwidth of sending 1024 transactions
  to every node, which the model does not limit.
- **A fee floor or a count limit.** Whether a node should require a fee cap
  near the base fee, as MATCHA does for its additional transactions, or bound
  how many transactions one payer backs, is FP-15's open question; the first
  only multiplies the capital by the base fee, and section 1 of the results
  gives it at 1 gwei.
