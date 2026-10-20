# 0028. A committee settles a chain of batches from one node, at the costs Merces measured

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 22 takes an earlier study's reading of Merces, an MPC
confidential token (ePrint 2026/850, with its implementation at
TaceoLabs/merces1-paper `23ee451`, both read by that study and not here),
as two transactions:

- the user's *intent*, 873,716 gas with the implementation's two-hash
  compression, posted from the user's own account, which the contract
  verifies and queues;
- the committee's *settlement* of a batch, posted by `mpcAddress`, one
  address, with new commitments and one collaborative proof that the
  contract checks against the queued commitments. For a batch of 50 the
  authors measured 22,519 gas a transfer. A short batch is padded with
  entries that write no storage, so below 50 the per-transfer figure is an
  upper bound: that study's table gives a transfer at most 986,310 gas in a
  batch of 10, 1,155,200 in a batch of 4 and 1,999,651 alone.

That study concludes that a transfer settles at the earliest one block after
the block that carried its intent, that the committee, which decides when to
post, decides between the users' latency and the users' gas, and, from its
survey of EIPs and ERCs, that a committee's submission address has the same
shared-sender problem as a relayer's. Its round floor for a batch is 63 rounds,
with modelled times of 315 ms at a 5 ms round trip, 5,040 ms at 80 ms and
15,750 ms at 250 ms. The plan's item asks for the delay from intent to
settlement and the gas a transfer pays, against the batching rule, congestion
and the settlement sender, and needs no clause.

## Decision

1. **No clause changes.** An intent is a type 2 transaction and a settlement
   a type 2 or a frame transaction, which the pools already specify. The
   committee is a load of the simulator's, `Committee`.
2. **A settlement costs 1,125,950 gas whatever it holds**: 50 times 22,519.
   This is that study's upper bound for a short batch, whose padding writes
   no storage and so costs less, by an amount neither Merces's paper nor
   that study states. Its figures are this bound within 15 gas, since each
   is the intent plus the full settlement shared out:
   $b \cdot (g_b - 873{,}716)$ is 1,125,940 for $b = 10$, 1,125,936 for
   $b = 4$ and 1,125,935 for $b = 1$. The gas a transfer saves by waiting
   for a fuller batch is therefore at most what experiment 19 reports.
3. **The settlements are a chain.** Each is proved against the queue
   position where the last one ends, since the contract checks it against
   the queued commitments. One that a block includes before that position
   is reached reverts, pays its gas, and settles nothing; the committee cuts
   its intents again, and every settlement it had proved after it reverts
   too.
4. **Three ways to send.**
   - *account*: `mpcAddress` is one address, so the plain reading is an
     account whose settlements take successive nonces, which the
     account-nonce pool holds in order (NP-12).
   - *frame*: an account with code, for a committee that can rotate its key,
     whose settlements take successive sequences of one nonce key. FP-7
     queues no frame transaction, so the committee sends one only when the
     last has landed, under `one` and `disjoint-keys` alike.
   - *keys*: a nonce key for each settlement, which `disjoint-keys` admits
     side by side. Nothing then keeps them in order.
   A committee that signs with a threshold BLS signature is above EIP-8141's
   verification cap: that study puts its verification at no less than 114,275
   gas, over the cap. The frame variants verify one key, as `mpcAddress` is one
   address.
5. **The committee watches one node and computes between blocks.** After
   each block its node imports it queues the block's intents and cuts a
   batch: every block, or only at 50 or once the oldest has waited a number
   of blocks. The batch is ready after 63 rounds at that study's round
   trips. Bytes are not modelled, as its floor does not state them.
6. **A burst** is experiment 00's shape at this scale: transfers at twice
   the gas limit for five minutes. Intents bid a tip of 3 gwei and a fee cap
   of 100 times the base fee, so that the users' own delay does not hide the
   committee's; the committee bids 0.1 gwei, a committee that keeps its
   users' gas low. Unlike a relayer's spends (experiment 15), the committee
   signs its own settlements, so it can re-price them; it does so by
   `BumpLoad`'s rule to the market.
7. **Not modelled**: an abort or a slow party, which is the third question
   that study asks of every design, who can stop the computation; intents
   sent through a relayer; deposits and withdrawals; and a builder that
   censors the committee.

## Consequences

- `Committee` and `Settlement` in `sim/emem_sim/workload.py`, with tests.
- Experiment 19.
