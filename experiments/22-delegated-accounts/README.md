# 22. Delegated accounts

**Question.** NP-6 gives an account whose code is an EIP-7702 delegation
indicator one transaction in flight. What throughput is left for a
delegated hot wallet, at what delay, and how much does sending its
transfers at once, one at a time, across several accounts or batched
change it? And what does a pending authorization do to its authority: when a
sponsor upgrades busy accounts, how often does NP-7 refuse the batch, how
often does the account's own traffic spend the authorization, or the
authorization spend a transfer's nonce, and what does a wallet have to do
to be upgraded?

**Clauses exercised.**

- NP-6 and NP-7 (`docs/spec/01-nonce-pool.md`): one transaction in flight
  for a sender with a delegation, or named by an authorization in the pool,
  and a set code transaction refused while an authority has more than one
  transaction in the pool.
- BB-2, BB-3 and BB-5 (`docs/spec/03-block-building.md`, version 2): a
  block takes transactions by tip, and an authorization whose nonce its
  authority has already used, or whose authority has contract code, is
  skipped without failing its transaction (decision record 0031).
- MD-5 (`docs/spec/00-model.md`, version 5), an authorization's nonce, and
  FEE-3, 25,000 gas an authorization.

The wallets, the sponsor and the batch's price are the simulator's
`HotWallet` and `Upgrade`, and decision record 0031 has the readings. What a
delegation is and how its tuples are processed are EIP-7702's, and how a
delegated account batches calls is ERC-7821's; the mempool recommendation
behind NP-6 is EIP-7702's "Transaction propagation" section.

## Setup

- **Network and chain**: 20 nodes, 8 peers each, a hop of 20 to 100 ms, a
  block every 12 s from a proposer in turn, which other nodes import 0.1 to
  1.0 s later. Gas limit 30,000,000, genesis base fee 1 gwei, and no other
  traffic, so a block always has room.
- **Pools**: `geth` (NP-1), whose NP-6 and NP-7 are go-ethereum's
  `checkDelegationLimit` and `validateAuth`.
- **Transfers**: plain transfers of 21,000 gas, at a tip drawn from 0.001
  to 3 gwei and a fee cap of twice the next base fee and the tip, set when
  the transaction is sent. Each account's wallet sends to one node and
  watches it; a transaction its node refuses waits for the node's next
  import, and a transfer whose nonce a block used for something else is
  sent again (decision record 0031, item 4).
- **Section 1**: one account, with code from genesis or not, at a demand
  of 60 to 3600 transfers an hour for two hours. EOA: no code, each
  transfer sent at once. Delegated: sent at once; serial, one in flight;
  serial across four accounts; or batch, one in flight carrying every
  transfer waiting, priced at 21,000 gas a transfer, as if each were sent
  alone.
- **Section 2**: 16 accounts without code, each at 60, 300 or 1200
  transfers an hour, sent at once, and batched once their wallet's node
  shows the delegation. From second 1800 a sponsor upgrades them in type 4
  transactions of 1, 4 or 16 authorizations at a tip of 2 gwei, each
  authorization signed at its account's next nonce by a wallet that keeps
  sending; that pauses until the delegation shows or the authorization is
  skipped; or that drains, pausing and signing only once nothing it sent
  is waiting for a block. Two hours a run.
- Seed 1.

## Run

```
python3 experiments/22-delegated-accounts/run.py > experiments/22-delegated-accounts/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

**A hot wallet** (section 1), landed transfers an hour and delays in
seconds from the request to inclusion:

| variant | demand | landed | delay p50 | p99 | waiting at end | transfers a transaction | NP-6 refusals a transfer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EOA | 150 | 140.00 | 6.44 | 12.04 | 0 | 1.00 | 0.00 |
| EOA | 3600 | 3559.00 | 6.09 | 12.04 | 0 | 1.00 | 0.00 |
| delegated, serial | 150 | 140.00 | 10.24 | 47.13 | 0 | 1.00 | 0.00 |
| delegated, serial | 300 | 285.00 | 61.64 | 279.45 | 11 | 1.00 | 0.00 |
| delegated, serial | 600 to 3600 | 299.00 | 1654.78 to 3275.18 | 3475.88 to 6528.00 | 543 to 6520 | 1.00 | 0.00 |
| delegated, at once | 300 | 285.00 | 61.64 | 279.45 | 11 | 1.00 | 1.69 |
| delegated, serial, 4 accounts | 1200 | 1131.00 | 74.37 | 403.23 | 47 | 1.00 | 0.00 |
| delegated, serial, 4 accounts | 3600 | 1197.00 | 2335.97 | 4718.15 | 4724 | 1.00 | 0.00 |
| delegated, batch | 300 | 290.50 | 12.55 | 26.24 | 0 | 1.25 | 0.00 |
| delegated, batch | 3600 | 3552.50 | 17.46 | 23.71 | 13 | 11.88 | 0.00 |

**Upgrading 16 accounts** (section 2); time is seconds from second 1800
to the last delegation, n/a when not every account was delegated by the
end; sends, the sponsor node's `ErrAuthorityReserved` and inclusions are
type 4 transactions; skipped and lost are authorizations and transfers:

| rate | batch | wallet | delegated | time | sends | reserved | included | skipped | lost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 60 | 1 | keeps sending | 16 | 192.77 | 16 | 0 | 16 | 0 | 3 |
| 60 | 16 | pauses | 16 | 12.24 | 2 | 1 | 1 | 0 | 0 |
| 60 | 16 | drains | 16 | 24.96 | 1 | 0 | 1 | 0 | 0 |
| 300 | 1 | keeps sending | 16 | 252.77 | 22 | 1 | 21 | 5 | 7 |
| 300 | 4 | keeps sending | 16 | 168.93 | 9 | 1 | 8 | 11 | 6 |
| 300 | 4 | pauses | 16 | 120.75 | 6 | 1 | 5 | 4 | 0 |
| 300 | 4 | drains | 16 | 72.12 | 4 | 0 | 4 | 0 | 0 |
| 1200 | 1 | keeps sending | 9 | n/a | 150 | 1 | 148 | 139 | 9 |
| 1200 | 1 | pauses | 16 | 444.36 | 36 | 1 | 35 | 19 | 0 |
| 1200 | 1 | drains | 16 | 324.16 | 16 | 0 | 16 | 0 | 0 |
| 1200 | 4 | keeps sending | 1 | n/a | 26 | 1 | 24 | 95 | 1 |
| 1200 | 16 | keeps sending | 0 | n/a | 28 | 1 | 26 | 416 | 0 |
| 1200 | 16 | pauses | 16 | 12.24 | 2 | 1 | 1 | 0 | 0 |
| 1200 | 16 | drains | 16 | 24.96 | 1 | 0 | 1 | 0 | 0 |

The 416 authorizations skipped at 1200 an hour with batches of 16 cost the
sponsor 10,400,000 gas. Other nodes refused a send as `ErrAuthorityReserved`
up to 15.17 times a send, as it spread. The median delay of transfers asked
from second 600 to the start was 6.06 to 6.82 s; of those asked in the 600 s
after it, for the draining wallet with batches of 16, 7.06, 14.49 and
17.51 s at 60, 300 and 1200 an hour.

## What it shows

1. **NP-6 is the frame pool's `one` for an account.**
   - A delegated account lands one transaction a block: 299.00 transfers an
     hour at every demand from 600 up, the ceiling experiment 01's shared
     sender met under FP-12's `one`, 299.50 an hour at 600
     (`experiments/01-one-pending-ceiling/results.md`).
   - Below the ceiling it costs delay: at 150 an hour the 99th percentile
     was 47.13 s against the EOA's 12.04 s, and at 300 the median was
     61.64 s, with 11 transfers still waiting at the end.
2. **Sending at once does not help; it adds refusals.** A delegated wallet
   that sends every transfer at once landed the same transfers at the same
   delays as one that sends serially, and was refused 1.69 times a
   transfer at 300 an hour.
3. **Throughput is per account.** Four delegated accounts sending serially
   landed 1197.00 an hour at 3600, four times one account's 299.00, and
   kept up at 1200 with 47 waiting at the end.
4. **Batching gives the throughput back, for about a slot.** NP-6 bounds
   transactions, not transfers: a delegated account that batches what is
   waiting landed 3552.50 of 3600 an hour, 11.88 transfers a transaction,
   at a median of 17.46 s and a 99th percentile of 23.71 s, against the
   EOA's 6.09 s and 12.04 s. Each transaction waits for the block that
   includes the last, so a transfer waits for up to two.
5. **An authorization signed for an account that keeps sending is a race,
   and a busy account wins it.**
   - The authorization is signed for the nonce after the account's last
     transfer. If the account sends another first, the block skips the
     authorization; if the authorization goes first, it takes the nonce of
     a transfer already sent, which has to be sent again.
   - At 300 an hour every account of a wallet that keeps sending was
     upgraded, with 5 to 11 authorizations skipped and 6 to 8 transfers
     lost a run. At 1200, 9 of
     16 accounts were upgraded in batches of 1 by the end, 1 in batches of
     4 and none in batches of 16, where 416 skipped authorizations cost the
     sponsor 10,400,000 gas.
6. **NP-7 bounds the race and does not remove it.**
   - The sponsor's node refused at most one send a run, and never one
     after its first, at second 1800 (later, 0 in every row): every later
     send followed the import of a block, which had just taken the
     accounts' pending transfers. Every send it admitted in a run that
     finished was included.
   - While an authorization is pending, NP-6 holds its authority to one
     transaction in flight, and that one can still take the nonce. Other
     nodes, where an authority still held more than one transaction,
     refused a send up to 15.17 times as it spread.
7. **A wallet has to stop, and stopping is not quite enough.**
   - A wallet that pauses once it has signed was upgraded at every rate. At
     1200 an hour with batches of 1, 19 of its authorizations were still
     skipped: it signed with a transfer in flight, and a block that took the
     authorization first skipped it.
   - A wallet that drains first lost nothing: no authorization skipped, no
     send refused by the sponsor's node, no transfer lost, at every rate
     and batch. It cost one
     more slot in batches of 16, 24.96 s against 12.24 s, and saved time in
     batches of 1 at 1200 an hour, 324.16 s against 444.36 s, because
     nothing had to be signed again.
8. **Batching after the upgrade costs a slot, and the pause a little more
   at the tail.** For the draining wallet at 1200 an hour in batches of 16,
   the median delay of transfers asked in the 600 s after the start was
   17.51 s against 6.06 s before it, about section 1's batched median at
   that rate, 17.15 s; the 99th percentile was 31.50 s, against section 1's
   23.67 s.

**Answer to the question.** NP-6 leaves a delegated account one
transaction a block, about 300 an hour, the same ceiling as a shared
sender under FP-12's `one`, and sending at once only adds refusals. A
wallet gets its throughput back by batching, which a delegated account's
code can do, at about one slot more delay, or by spreading its transfers
over accounts. A pending authorization makes its authority delegated in
every pool that holds it, and races the authority's own transactions:
NP-7 limits the authority to one transaction in the pool, which bounds the
race and does not remove it. Of 16 accounts that kept sending at four
transfers a slot, 9 were upgraded in 90 minutes one at a time and none in
batches of 16; accounts whose wallet stopped and waited for its last
transfer before signing were upgraded in two slots, with nothing lost.

## What it does not show

- **The gas of a batch.** A batch is priced at 21,000 gas a transfer, as
  if each were sent alone; a delegate's loop of calls costs something else,
  which is not read from a source here, and the saving would move only the
  gas, not the slots.
- **An account that authorizes itself**, which signs for the nonce after
  its own transaction's (`bb-05-apply.json` has the case), or a sponsor
  that sends from a frame transaction.
- **What NP-6 protects against.** EIP-7702's reason for it is that a
  delegated account's code can sweep its balance and make its pending
  transactions stale; the model has no sweeping, so this measures NP-6's
  cost and not its benefit.
- **Blocks full of other traffic.** Here every block had room, so a
  transaction in flight always made the next block.
- **Other clients' pools.** EIP-7702's limit is a recommendation; the pool
  here is go-ethereum's.
- **A wallet that sends to several nodes**, or one that watches more than
  its own node.
