# Experiments

Each experiment asks one question of the mempool and answers it with a
simulation built on `sim/emem_sim`, which runs the reference pools of
`ref/python` on a network of nodes. Some experiments will also measure a live
chain; those say so and record the endpoint and block height they read.

## Layout

```
experiments/NN-short-name/
  README.md    the question, the setup, how to run it, the results, what they mean
  run.py       the experiment; prints its result file on standard output
  results.md   what run.py printed, committed
```

- `NN` is the next free two-digit number. Numbers are never reused.
- `run.py` is deterministic: every random choice comes from the scenario's seed,
  so the same code prints the same `results.md`. `make experiments` re-runs every
  offline experiment and fails if any output differs from the committed file,
  which is how a number in a README is kept honest. It runs them in parallel,
  `scripts/check-experiments.sh experiments/NN-name` checks one, and CI checks
  each in a job of its own (decision record 0017). A change meant to move a
  number regenerates `results.md` in the same commit
  (`python3 experiments/NN-name/run.py > experiments/NN-name/results.md`), and
  the README's prose is updated to match.
- A `run.py` that reads a live endpoint declares `NETWORK = True` at the top
  and is skipped by `make experiments`; its `results.md` records where and when
  it was measured instead.
- The README follows the template below. "What it shows" says what the
  numbers mean for the question, and "What it does not show" names what the
  model leaves out that could change the answer (the spec's *Not modelled*
  notes are the starting list).
- Results are reproduced under the Python version CI uses (3.13); another
  version can draw different random numbers and print different figures.

## README template

```
# NN. Title

**Question.** One sentence.

**Clauses exercised.** The spec clauses whose behaviour decides the answer.

## Setup
Network, chain, pools, profile, load, duration, seed.

## Run
python3 experiments/NN-name/run.py > experiments/NN-name/results.md

## Results
The key table, copied from results.md.

## What it shows

## What it does not show
```

## Index

| # | Experiment | Question |
| --- | --- | --- |
| 00 | [Baseline](00-baseline/) | Does the base behave like a mempool: propagation in under a second, inclusion within a slot or two below target, a backlog and a rising base fee in a burst that drain afterwards? |
| 01 | [The one-pending-transaction ceiling](01-one-pending-ceiling/) | How many spends an hour does a shared sender land under FP-12's `one` and `disjoint-keys` as demand rises, and what does it cost its users in delay and exposure? |
| 02 | [MATCHA](02-matcha/) | Does MATCHA lift the one-pending-transaction ceiling for a shared sender, how soon and at what cost in delay, and how much revalidation work can an adversary make every node do under it? |
| 03 | [Revalidation cost](03-revalidation-cost/) | When many pending frame transactions rest on one payer, how many prefixes can one block make every node re-run, what does it cost whoever makes it happen, and what do the profiles' caps and balance reuse take away? |
| 04 | [Eviction order](04-eviction-order/) | When a pool is full, what can transactions that no builder includes push out of it, at what cost, and does EIP-8141's order, the nearest deadline before the lowest tip, make that worse than go-ethereum's order by price? |
| 05 | [The expiry timestamp](05-expiry-timestamp/) | How many transactions does a pool admit that no block can include, under the head's timestamp and the next slot's, and does the next slot's check, with or without a tip-first eviction order, close the pool to floods of them? |
| 06 | [In-mempool aggregation](06-in-mempool-aggregation/) | How long does a transaction with an EIP-8288 dependency take to reach a builder and a block, and how many such transactions do the aggregates carry, when the wrapper limits bind aggregates, when they do not, and when users' wrappers are relayed at once? |
| 07 | [Sealed admission](07-sealed-admission/) | How long does a cheap sealed payment wait as demand nears the 32 commitments a block takes, and what can a flood of sealed transactions that tolerate no commitment before them do to it under each reading of EIP-8184's open admission policy and each eviction order? |
| 08 | [The verification gas floor](08-verify-floor/) | Under EIPs pull request 12301's floor, how far does a private spend above 100,000 gas reach and how long does it wait, against the share of nodes with headroom and where they sit, and what does a budget carried in announcements save and let a liar do? |
| 09 | [Inclusion lists and builders that filter](09-focil/) | When a share of builders leaves some senders out, how long do their transactions wait without inclusion lists and with them, what does filtering cost a builder when blocks have room and when they are full, and what changes when includers filter too and for private spends? |
| 10 | [Wasted work against network size](10-wasted-work/) | How many validation prefixes does the network run for one adversary transaction whose sponsor will never pay, and how does that grow with the number of nodes, under both frame pool profiles? |
| 11 | [One spend, many copies](11-spend-copies/) | When the holder of a spend hands it out as several copies to different nodes, of which one can land, how many pools hold a copy that has lost and for how long, and what do the copies cost the network, with the spend's nullifier in a nonce key and in a storage slot, and with the pool's static checks before the prefix? |
| 12 | [Propagation as a timing channel](12-timing-channel/) | How well do observers in the gossip network find the node a spend was handed to, how soon do they hear of it, and how long do they hold it before a block includes it, against the share that observes, the peer count, the arrive timeout, the network's size, and builders that filter? |
| 13 | [MATCHA's load floor](13-load-floor/) | Under MATCHA's optional linear fees, what does a user of a busy shared sender pay over a user who sends the same spend alone, at the same demand, how often does the floor bind, and what does it cost a wallet that does not read it? |
| 14 | [Recent roots that expire in the pool](14-recent-roots/) | How many spends proved against an EIP-8272 recent root outlive their root in pools, against the window's length, congestion and builders that leave the spends or the root writes out, what does each node re-check when a root leaves the window, and what does the margin a node keeps change? |
| 15 | [Wallets that bump fees](15-fee-bumping/) | How fast does the backlog a burst leaves clear when wallets re-price a stuck transaction, what does it cost them, what changes when users stop sending above a price, and what does a shared sender under `one` do when only a spend's user can re-price it? |
| 16 | [Batched admission](16-batched-admission/) | How large a batch of proofs under one key does a node form in a window, what does it save, what delay does the window add to propagation and inclusion, and what does a sender of invalid proofs cost a node that batches? |
| 17 | [Width by contention class](17-contention-classes/) | What does a shared sender land when MATCHA takes its baseline per contention class of what a prefix reads rather than per sender, and how much work can a malicious application make every node do for each unit of gas it spends, against experiment 02? |
| 18 | [Withheld keys](18-withheld-keys/) | What do key publishers that withhold the keys they are named for do to cheap sealed payments, against their share, when senders send a withheld payment again sealed or in public, under each admission policy, and what does experiment 07's escalating flood cost when it withholds every key? |
| 19 | [A committee's settlement](19-committee-settlement/) | What delay from intent to settlement and what gas a transfer does an MPC committee's batching rule give against demand, what do its rounds between blocks add, and what does a burst do to a committee that sends from an account, from one frame transaction at a time or from a nonce key for each batch, with and without re-pricing? |
| 20 | [A committee that clears every block](20-per-block-clearing/) | With an MPC committee's members in the gossip network, how many batches are settled in the block they were meant for and how many orders make the batch they were sent for, against the round count and slots of 12, 8 and 4 s, with orders from the chain or from the pool at a cutoff, and how many rounds fit once the network is counted? |
| 21 | [Expiring nonces](21-expiring-nonces/) | With EIP-8266's expiring nonces composed with EIP-8250 as a reserved key and the nullifier in storage, how many spends an hour does a shared sender land, at what delay and exposure, and what do the deadline and the 13,000 gas cost, when nodes take the EIP's MAY and when they do not? |
| 22 | [Delegated accounts](22-delegated-accounts/) | What throughput does NP-6 leave a delegated hot wallet, sent at once, serially, across accounts or batched, and when a sponsor upgrades busy accounts, how often does NP-7 refuse the batch, the account's own traffic spend the authorization, or the authorization spend a transfer's nonce? |
| 23 | [A committee's keys](23-committee-keys/) | With a threshold committee as LUCID's key publisher, how often is a key in time and what do payments pay for it, against members that withhold or are late, at two thirds and a majority of 16, 64 and 423, when a slot's members fail every key at once, with senders that go public or release their own key; and what do the shares, a rotation, and builders that leave the committee out cost? |
| 24 | [Proving time in the aggregation interval](24-proving-budget/) | At proving costs fitted from leanVM's own benchmark on this machine, does one aggregation interval's work fit in the interval, and what do nodes that fill a budget in EIP-8288's order, nodes that prove everything and skip ticks, a share of nodes that cannot prove, and a flood of transactions with a dependency that never pay do to delay, reach and what aggregates carry? |
| 25 | [A self-issuer's junk proofs](25-ticket-defences/) | Under version 4 of claim-gated admission, what does a self-issuer's junk proof cost the nodes and the self-issuer, under version 4 as written, issuer memory and a node list, and what does each defence cost the honest senders it protects? |
