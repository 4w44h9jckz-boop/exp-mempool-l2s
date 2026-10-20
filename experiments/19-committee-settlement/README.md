# 19. A committee's settlement

**Question.** An MPC confidential token such as Merces settles a transfer in
two transactions: the user's intent, and the committee's settlement of a
batch of intents. The committee decides when to post. What delay from intent
to settlement, and what gas a transfer, does each batching rule give against
demand? What do the committee's rounds between blocks add? And what does a
burst of demand do to a committee that sends its settlements from an
account, from one frame transaction at a time, or from a nonce key for each
batch, with and without re-pricing them?

**Clauses exercised.**

- FEE-1 and FEE-2 (`docs/spec/00-model.md`): the base fee and the effective
  tip.
- NP-11 and NP-12 (`docs/spec/01-nonce-pool.md`): an account's settlements
  wait in nonce order behind the oldest, and a re-priced one replaces it.
- FP-7 and FP-12 (`docs/spec/02-frame-pool.md`): a frame transaction is
  never queued; under `one` a sender has one pending, and under
  `disjoint-keys` one for each nonce key.
- BB-1 to BB-5 (`docs/spec/03-block-building.md`): the builder takes
  candidates by tip.

No clause changes. The committee is the simulator's `Committee`, and
decision record 0028 has the readings. Merces's paper (ePrint 2026/850) and
its implementation are not read here: its two transactions, their gas and
the committee's choice between latency and gas are taken as an earlier study
of MPC systems reads them. That MPC study's conclusion is the one measured
here: a transfer settles at the earliest one block after the block that
carried its intent, and the committee decides between the users' latency and
the users' gas.

## Setup

- **Network and chain**: 10 nodes, 8 peers each, a block every 12 s from a
  rotating proposer, gas limit 60,000,000, a base fee from 1 gwei.
  Transfers of 1,000,000 gas fill the gas target beside the intents and one
  settlement a block.
- **Intents**: 873,716 gas each, Merces's figure with its implementation's
  compression, from accounts of the users' own, at the rate in the table, to
  random nodes, until second 1800. They bid a tip of 3 gwei and a fee cap of
  100 times the next base fee, so that their own delay does not hide the
  committee's.
- **The committee** watches node n00. After every block it imports, it
  queues the block's intents and cuts batches of at most 50 from the queue's
  head: every block, or only a full 50 or once the oldest has waited 5 or 25
  blocks. A batch is ready 63 rounds after its cut, at the MPC study's round
  trips: 5 ms in the same region, 80 ms cross-continent, 250 ms
  intercontinental. Its settlement costs 1,125,950 gas whatever it holds,
  Merces's measured batch of 50, which the MPC study takes as the upper bound
  for a padded short one (decision record 0028). It bids a tip of 2 gwei and a
  fee cap of twice the next base fee plus the tip.
- **Senders**: an account at its next nonce; a frame transaction at the next
  sequence of one nonce key, sent only once the last has landed, since FP-7
  queues none; or a frame transaction under a nonce key of its own for each
  settlement, which `disjoint-keys` admits side by side. A settlement is
  proved against the queue position the last one ends at, so one that a
  block includes before that one reverts, and every settlement proved after
  it reverts too.
- **Section 3** adds a burst of 1,000,000-gas transfers at twice the gas
  limit from second 600 to second 900, experiment 00's shape at this scale,
  and a committee that bids 0.1 gwei. A committee that re-prices replaces a
  settlement after every block its node imports without it, by 10 percent
  and to the market, as experiment 15's wallets do.
- Seed 1, 2400 s a run; rows are the intents first sent from second 240.

## Run

```
python3 experiments/19-committee-settlement/run.py > experiments/19-committee-settlement/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

**The batching rule against demand** (section 1), from an account in the
same region; delays in seconds from the block that included an intent to
the block that settled it, gas a transfer's intent and its share of the
settlements:

| a slot | rule | delay p50 | p90 | max | settlements | batch | gas a transfer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | every block | 12.56 | 12.89 | 12.99 | 101 | 1.63 | 1562933.88 |
| 1 | full, or 5 blocks | 36.96 | 72.62 | 72.98 | 24 | 6.88 | 1037490.55 |
| 1 | full, or 25 blocks | 168.84 | 288.90 | 312.90 | 6 | 27.50 | 914659.64 |
| 5 | every block | 12.56 | 12.91 | 12.99 | 148 | 4.94 | 1101678.52 |
| 5 | full, or 5 blocks | 48.00 | 72.22 | 72.96 | 25 | 29.24 | 912223.18 |
| 5 | full, or 25 blocks | 72.72 | 132.56 | 312.78 | 15 | 48.73 | 896820.31 |
| 20 | every block | 12.50 | 12.90 | 12.99 | 150 | 19.31 | 932015.10 |
| 20 | full, or 5 blocks | 24.75 | 36.99 | 72.91 | 58 | 49.95 | 896258.32 |
| 20 | full, or 25 blocks | 24.75 | 36.99 | 312.26 | 58 | 49.95 | 896258.32 |

Every intent sent in the window was settled in every row of section 1 and
section 2.

**The committee's rounds** (section 2), at 5 intents a slot, every block:

| network | rounds, s | sender | delay p50 | p90 | max | settlements | batch | gas a transfer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| same region | 0.315 | account or frame | 12.56 | 12.91 | 12.99 | 148 | 4.94 | 1101678.52 |
| cross-continent | 5.040 | account or frame | 12.56 | 12.91 | 12.99 | 148 | 4.94 | 1101678.52 |
| intercontinental | 15.750 | account | 24.56 | 24.89 | 24.99 | 148 | 4.94 | 1101678.52 |
| intercontinental | 15.750 | frame | 24.95 | 36.76 | 36.99 | 76 | 9.62 | 990777.83 |

**A burst** (section 3), at 5 intents a slot, every block, in the same
region, with a committee that bids 0.1 gwei; of 627 intents measured, wei is
what the settlements cost a transfer settled, reverted ones included:

| sender | re-prices | unsettled | delay p50 | p90 | max | settlements | batch | reverted | versions | settlement wei a transfer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| account | no | 467 | 12.58 | 12.93 | 12.98 | 49 | 5.39 | 0 | 148 | 202737506087743.56 |
| frame | no | 467 | 12.58 | 12.93 | 12.98 | 49 | 5.39 | 0 | 50 | 202737506087743.56 |
| keys | no | 467 | 12.58 | 12.93 | 12.98 | 49 | 5.39 | 729 | 801 | 38435320615574192.00 |
| account | every block | 0 | 12.72 | 216.51 | 312.20 | 148 | 4.94 | 0 | 548 | 2548436099100288.50 |
| frame | every block | 0 | 12.73 | 228.11 | 336.51 | 121 | 6.04 | 0 | 148 | 1611456233423642.25 |
| keys | every block | 0 | 12.72 | 216.51 | 312.20 | 148 | 4.94 | 0 | 548 | 2548436099100288.50 |

The base fee in section 3, in wei: in the last block before the burst, the
highest in the run, and the least from the burst's end to the end of the
run:

| sender | re-prices | before the burst | highest | least after the burst |
| --- | --- | --- | --- | --- |
| account or frame | no | 804004163 | 23318224680 | 5176640985 |
| keys | no | 804004163 | 23334153341 | 9280142425 |
| account or keys | every block | 804004163 | 24586086075 | 5361621037 |
| frame | every block | 804004163 | 23340025595 | 5287394692 |

## What it shows

1. **The floor is one block, and a committee that posts every block meets
   it.**
   - Settling every block, the median delay from the block that carried an
     intent to the block that settled it was 12.56 s at 1 and 5 a slot and
     12.50 s at 20, and the longest 12.99 s: the next block, as the MPC
     study says.
   - From sending, the 90th percentile was 23.08 s to 23.58 s: a block for
     the intent and a block for its settlement.
2. **What the committee buys with delay is the settlement's share.**
   - A settlement costs the same whatever it holds here, so the gas a
     transfer falls with the batch, by at most these amounts (decision
     record 0028). At 1 intent a slot, settling every block gave batches of
     1.63 and 1562933.88 gas a transfer; waiting for 50 or 25 blocks gave
     batches of 27.50 and 914659.64 gas, for a median delay of 168.84 s
     rather than 12.56 s.
   - At 20 a slot the batch fills before either wait runs out, so the two
     full rules gave the same 896258.32 gas a transfer, with batches of
     49.95, at a median of 24.75 s. Only their maximum differs, 72.91 s and
     312.26 s: the last intents, after the users stop, make a short batch
     that waits the rule out.
   - The busier the token, the less the choice costs: settling every block
     at 20 a slot gave 932015.10 gas a transfer at 12.50 s.
3. **The rounds cost a block once they are longer than the slot left.**
   - At 0.315 s and 5.040 s the batch was ready in time for the next block,
     and both senders gave the same figures as the same region's.
   - At 15.750 s, longer than a slot, a settlement missed the next block.
     From an account the committee pipelines, a batch cut every block and
     each settled one block late: the median was 24.56 s and the gas
     unchanged.
   - As a frame transaction under one key it cannot pipeline, since FP-7
     queues nothing: it cuts again only once the last settlement has
     landed, so it settled 76 times rather than 148, in batches of 9.62. Its
     90th percentile was 36.76 s, and a transfer paid 990777.83 gas rather
     than 1101678.52.
4. **A committee that never re-prices is stopped by one burst.**
   - The settlement sent as the burst began bid a fee cap of twice the next
     base fee plus its tip, under 2 gwei with the base fee at 804004163 wei
     before the burst (FEE-1 lets the base fee rise by at most an eighth a
     block). The burst took
     the base fee to 23318224680 wei, and it stayed above 5176640985 for the
     rest of the run, so that settlement was never included, and nothing
     after it settled: 467 of 627 intents were unsettled at the end, under
     every sender.
   - This is experiment 00's backlog, for a sender whose every later
     transaction waits on the stuck one.
   - From an account the later settlements waited in the queue behind it
     (148 sent, 49 included). As one frame transaction the committee sent 50
     and stopped, since the pool holds no second (FP-7, FP-12).
5. **A nonce key for each batch pays for the burst many times over.**
   - With a key for each settlement nothing keeps them in order. The later
     settlements, priced at a higher base fee, landed before the stuck one
     and reverted, and the committee cut and proved them again: 729
     reverted, and the settlements cost 38435320615574192.00 wei a transfer
     settled, against 202737506087743.56 from an account, for the same 49
     good settlements.
   - The reverted settlements' gas held the base fee up for everyone: its
     least after the burst was 9280142425 wei, against 5176640985 under the
     other two senders.
   - Re-pricing every block, the older settlement had always been raised
     more often, so a block that took two took them in order, and the keys
     committee's figures were the account's to the hundredth, with none
     reverted.
6. **Re-pricing settles everything, at the burst's price.**
   - Re-pricing every block, every intent settled, with a 90th percentile of
     216.51 s from an account and 228.11 s as one frame transaction, against
     12.91 s in section 1, which has no burst.
   - It cost 2548436099100288.50 wei a transfer from an account and
     1611456233423642.25 as one frame transaction: the frame committee
     cannot pipeline, so it made fewer and fuller settlements (121, of 6.04
     intents each) and re-priced one at a time (148 versions against 548).

**Answer to the question.** A committee that settles every block meets the
one-block floor, and pays for it in gas a transfer, which a full-batch rule
recovers at a delay of minutes when demand is light and of a block or two
when it is heavy. Rounds longer than the slot cost one block from an
account and more from a frame transaction under one key, which cannot
pipeline. A burst stops any committee that does not re-price, and a
committee with a nonce key for each batch then pays for reverted
settlements block after block; re-pricing settles everything, and one frame
transaction at a time is the cheaper way through, at a slightly longer
tail.

## What it does not show

- **What a short batch really costs.** Its padding writes no storage, so it
  costs less than a full one by an amount nobody has measured, and the gas
  a transfer saves by waiting for a fuller batch is at most what section 1
  reports.
- **An abort or a slow party.** Any one of Merces's three servers can stop
  the computation, and the holder of `mpcAddress` can stop posting.
  The queue records what is unprocessed; what a stall costs the users is
  the stuck rows of section 3 for a reason other than price.
- **Bytes.** The MPC study's floor counts rounds only, because Merces's paper
  does not state the witness extension's bytes; a batch's bandwidth would
  lengthen every round trip here.
- **Intents through a relayer, deposits and withdrawals.** Every intent is
  sent from its user's own account.
- **A threshold signature.** A committee that signs a frame transaction
  with a threshold BLS signature is above EIP-8141's verification cap, at
  least 114,275 gas by the MPC study's count, where experiments 08 and 09
  measured what reaches a block. The frame
  committees here verify one key.
- **A builder that censors the committee**, which experiment 09 prices for
  spends.
