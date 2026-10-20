# 10. Wasted validation work against network size

**Question.** How many validation prefixes does the network run for one
adversary transaction whose sponsor will never pay, and how does that grow
with the number of nodes, under both frame pool profiles?

**Clauses exercised.**

- FP-8 to FP-11: a pool runs the prefix, then reads the payer's balance,
  what it reserves and, under `hegota-testnet`, how many transactions a
  default-code sponsor already pays for.
- FP-15: what a pool runs again when a block moves a payer's balance.
- BB-3: what a builder tries and fails.

ethresear.ch topic 25995 proves that a public-mempool rule which "charges
nothing" per attempt cannot keep wasted work in proportion to the attacker's
cost. Its argument is: "Each distinct s reaches and is checked by all N
nodes", so that $k$ transactions waste $W = N \cdot w \cdot k$, where $w$ is
one node's work to check one. EIP-8141 avoids that
by holding money: a pool reserves each pending transaction's cost against
its payer's balance (FP-11). The result bites for a private spend, whose
payer is a fresh account with no escrow, bond or trust to offer. This
experiment counts, in the model, the work the rule leaves.

## Setup

- **Network** (decision record 0019): 25, 50, 100 and 200 nodes, 8 peers
  each, go-ethereum's gossip, a block every 12 s from a proposer that
  rotates through every node, gas limit 30,000,000, 360 s a run. Each row
  pools three runs, seeds 1 to 3.
- **Honest load**, the yardstick: wallets sending self-paying frame
  transactions at 6 a slot, each from a sender of its own.
- **Empty sponsors** (section 1): from 36 s to 324 s, 12 sponsored frame
  transactions a slot. Each has a default-code sender and a default-code
  sponsor of its own that holds nothing, a fee cap of twice the next base
  fee plus a 1 gwei tip, and is handed to one random node or to every node.
- **A drained sponsor** (section 2): from 36 s to 324 s, 2 s after every
  block, k sponsored transactions (4 or 32) backed by one default-code
  sponsor that holds enough to pay for all of them at their fee cap, each
  handed to a random node. With them, every node is handed the sponsor's
  transfer of its whole balance to the next round's sponsor, at twice the
  tip. The next block includes the transfer first, so the transactions
  fail, and the same money backs every round.
- **Work** is counted in prefix runs (decision record 0019): every answer a
  pool gives at or after FP-8, and every re-run at a new head. The model
  has no client and gives no time per run.

## Run

```
python3 experiments/10-wasted-work/run.py > experiments/10-wasted-work/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

Section 1, sponsors that hold nothing, selected columns. Every row pools
three runs, and 871 transactions were sent in each.

| profile | handed to | nodes | handed | runs per transaction | work per hand-over | pools reached | landed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | 1 | 25 | 871 | 1.00 | 1.00 | 0.00 | 0 |
| eip-8141 | 1 | 200 | 871 | 1.00 | 1.00 | 0.00 | 0 |
| eip-8141 | every node | 25 | 21775 | 25.00 | 1.00 | 0.00 | 0 |
| eip-8141 | every node | 200 | 174200 | 200.00 | 1.00 | 0.00 | 0 |

The `hegota-testnet` rows are the same.

Section 2, a sponsor drained every block, selected columns, with the cost
table's last two columns beside them. Work per node a round is what every
node ran, admitting and re-running, per round the adversary sent.

| profile | k | nodes | pools reached | work per transaction per node | work per hand-over | failed in block | work per node a round | work per gwei paid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eip-8141 | 4 | 25 | 24.90 | 2.00 | 50.11 | 0.96 | 8.02 | 0.004254 |
| eip-8141 | 4 | 200 | 198.71 | 2.01 | 401.32 | 0.96 | 8.03 | 0.03407 |
| eip-8141 | 32 | 25 | 24.90 | 2.00 | 50.10 | 0.96 | 64.13 | 0.03403 |
| eip-8141 | 32 | 200 | 198.66 | 2.01 | 401.23 | 0.96 | 64.20 | 0.2725 |
| hegota-testnet | 4 | 25 | 6.23 | 1.37 | 34.24 | 0.24 | 5.48 | 0.002907 |
| hegota-testnet | 4 | 200 | 49.84 | 1.34 | 267.60 | 0.24 | 5.35 | 0.02272 |
| hegota-testnet | 32 | 25 | 0.78 | 0.34 | 8.54 | 0.03 | 10.93 | 0.005802 |
| hegota-testnet | 32 | 200 | 6.24 | 0.29 | 57.50 | 0.03 | 9.20 | 0.03905 |

Each run has 25 rounds. The adversary holds 0.00504 ETH at k = 4 and
0.0109 ETH at k = 32, and each round's transfer pays 4.711e+04 gwei. An
honest transaction costs each node 1.00 run in every row of both sections.

## What it shows

- **The frame pool has no case 1.** A transaction whose sponsor holds
  nothing is refused by the node it is handed to. FP-8 runs its prefix and
  ends in `ErrInsufficientFunds`, and a node relays only what it admits
  (EIP-8141, Acceptance Algorithm, step 8: "If all checks pass, the
  transaction may be accepted into the public mempool and propagated to
  peers"). So it goes no further: work per hand-over is 1.00 at every size
  under both profiles, and no such transaction reached a pool. The topic's
  "Each distinct s reaches and is checked by all N nodes" assumes a node
  that relays before it checks. Here the network does only the work the
  adversary delivers itself. A transaction handed to all 200 nodes costs
  200 runs because it was handed over 200 times.
- **What the rule still charges nothing for is the hand-over.** Each one
  costs the receiving node a prefix run, the topic's $w$, and costs the
  adversary only the connection. The amplification is 1, not $N$, but the
  price is still zero.
- **Holding money does not bound the work when the money can move.** Under
  `eip-8141` the drained sponsor's transactions reach nearly every pool:
  198.71 of 200 at k = 4. Every node runs each one twice, once to admit it
  and once at the next head, which removes it, so work per transaction per
  node is 2.01. An honest transaction costs 1.00. Work per hand-over then
  grows with the network, from 50.11 at 25 nodes to 401.32 at 200, which
  is case 1's proportion to $N$, reached with money held.

  Each node runs about two prefixes per transaction a round: work per node
  a round is 8.02 at k = 4 and 64.13 at k = 32 with 25 nodes, and the same
  to within 0.1 at every size. The adversary pays one transfer a round,
  4.711e+04 gwei, and keeps its capital. Work per gwei paid grows with both $N$ and k, from 0.004254 at
  k = 4 and 25 nodes to 0.2725 at k = 32 and 200 nodes. This is the topic's
  "checked-but-drainable balance", which it files under "hold money". FP-11
  bounds what a payer's pending transactions can cost, not how many
  transactions one balance moved once can invalidate. Only the capital and
  `max_pending` bound k.
- **The testnet's cap on codeless sponsors bounds a node's work per
  sponsor, and the EIP leaves it out.** Under `hegota-testnet` a pool holds
  one transaction per default-code sponsor (FP-11, `cap_codeless_payers`).
  It admits the first of the k it receives and refuses the rest with
  `ErrFramePaymasterBusy`, which stops them spreading. Pools reached per
  transaction falls to 6.23 of 25 at k = 4 and to 0.78 at k = 32. Work per
  node a round is 5.48 at k = 4 and 10.93 at k = 32 with 25 nodes, and
  9.20 at k = 32 with 200. Each node's share no longer grows with k as it
  does under `eip-8141`, but the network's work still grows with its size,
  from 8.54 a hand-over at 25 nodes to 57.50 at 200.

  The refusals come after the prefix has run (FP-11 follows FP-8), so each
  still costs a run. The EIP says the opposite of the cap: "a `pay` frame
  whose target has the empty code hash (a default-code sponsor) is not a
  paymaster and is governed by the per-payer exposure rule alone"
  (Mempool, Replacement and Eviction, at `258836f9`). The cap is what was
  measured on the testnet, not what the EIP specifies.

## What it does not show

- **$w$ itself.** The model counts prefix runs and gives no time for one.
  The topic asks for $w$ measured in a client, and so does the plan,
  under "Growing the base".
- **Work outside the prefix.** Every hand-over is fetched, decoded and has
  its signatures checked before FP-8. That is paid whatever the rule, and
  the model counts none of it, including FP-3's signature check.
- **Peer scoring.** A client may drop a peer that sends it transactions it
  refuses, which would limit a hand-over to every node. The gossip model
  never disconnects a peer.
- **A check before the prefix.** A pool that read the payer's balance and
  count before running the prefix would refuse both adversaries' extra
  transactions without a run. The EIP's acceptance algorithm simulates
  first (steps 4 to 7), and the model follows it.
- **Other adversaries.** Not measured here: many sponsors each backing one
  transaction under the cap, which costs a transfer per transaction a
  round; sponsors with code, which both profiles cap; a canonical paymaster
  instance draining through its withdrawal; and a shared sender, which
  experiments 02 and 03 measured.
