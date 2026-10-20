# 09. Inclusion lists and builders that filter

**Question.** When a share of the builders leaves a set of senders out,
how long do those senders' transactions wait, without inclusion lists and
with them? What does filtering cost a builder under EIP-7805, when blocks
have room and when they are full? What changes when includers filter too,
and for private spends, whose validation only EIP-8369's Profile 2 can
enforce?

**Clauses exercised.**

- IL-2 to IL-8: what includers list, which frame transactions can be
  enforced, when a block satisfies its lists, what a builder appends, and
  the slot a block that does not satisfy them loses.
- BB-1 to BB-3: what a builder takes from its own pool, before IL-7 appends.
- FP-3 to FP-6 and FP-16: what the frame pool admits and what an includer
  sees of it, in section 4.

Nothing obliges a block to carry a given transaction, so inclusion through
the public mempool is a market outcome. EIP-7805, in Draft at `258836f9`,
makes it a duty. A committee of 16 lists what it sees, and attesters do not
vote for a block that leaves a listed transaction out while it "could be
validly included" and fits. It excuses a block whose gas is used up. An
earlier analysis argues that this excuse is free at full blocks: there the
builder manufactures nothing, but promotes the next transaction in the queue
and forgoes only the difference in priority fee. EIP-7805 checks only "the
nonce and balance of `T.origin`". So a frame transaction is enforceable only
under EIP-8369's Profile 2, an Informational Draft, which the `eip-8369`
profile specifies as a proposal (`docs/spec/07-focil.md`).

## Setup

- **Network** (decision record 0018):
  - 100 nodes, 8 peers each, go-ethereum's gossip as in every experiment.
  - A block every 12 s, gas limit 30,000,000.
  - Blocks are built by 10 of the nodes, drawn at random, in turn, which
    stands in for a builder market in which each wins a share of the slots.
    The share of them that filters is drawn at random.
  - Each row pools three runs, seeds 1 to 3, each with its own topology,
    latencies, placement and committees.
- **Loads.** Every wallet draws its tip from 0.001 to 3 gwei, caps its fee at
  twice the next base fee plus the tip, sends to a random node, and sends
  once.
  - Background: 1,000,000-gas transfers at 15 a slot for the whole 900 s
    run, the gas target on average, so that the base fee stays where blocks
    are half full. On a chain at rest it would fall toward zero, and stuffing
    a block would cost nothing.
  - Honest: 21,000-gas transfers at 6 a slot.
  - Filtered: 21,000-gas transfers at 2 a slot from senders that every
    filtering builder leaves out.
  - Honest and filtered transfers are sent for the first 450 s.
  - Section 3 adds 1,000,000-gas transfers at 36 a slot from 240 s to 390 s,
    and varies the filtered transfers' tip and gas.
  - Section 4 replaces the filtered transfers with experiment 08's spends:
    self-paying frame transactions with a rule 6 budget of 211,828, at the
    same rate.
- **Inclusion lists** (`eip-7805`, and `eip-8369` in section 4):
  - Each slot, 16 nodes are drawn from a random stream of their own.
  - 8 s into the slot, each lists what its pool would put in a block, by fee
    (IL-2), or by age in one row of section 3.
  - The lists reach the next builder and every attester.
- **A filtering builder** (decision record 0018). It leaves the filtered
  senders out of its block. When that block would leave a listed
  transaction out (IL-6), it follows its strategy:
  - *stuff*: it appends a transfer of its own that uses enough gas to excuse
    the omission, at the base fee and no tip;
  - *miss*: it proposes the block anyway, and the slot has no block;
  - *yield*: the next builder in turn that does not filter builds the slot,
    which is how a proposer under proposer-builder separation would take the
    best bid that satisfies the lists; it is *miss* if every builder
    filters;
  - *cheapest*: it stuffs if the stuffed block's priority fees cover the
    base fee it burns, and yields otherwise.

  What filtering cost it is the priority fees of the block it would have
  built honestly from the same pool and lists, less those it was paid, plus
  the base fee it burned. Builders are funded so that money never stops
  them stuffing.

## Run

```
python3 experiments/09-focil/run.py > experiments/09-focil/results.md
```

It runs its simulations in parallel, as many at once as there are
processors (`EMEM_JOBS` overrides it), and the output does not depend on how
many. Every figure below is from `results.md`.

## Results

Section 1, the share of builders that filter, selected columns. Delays are
in seconds; cost is what filtering cost the filtering builders over the
slots they were due in three runs, and its share of the priority fees honest
blocks would have paid them; base fee peak is in gwei.

| profile | share | strategy | included of 234 | delay p50 | max | honest p50 | background included | cost, ETH | cost share | base fee peak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| off | 0.00 | | 234 | 6.24 | 12.30 | 6.12 | 1.00 | 0 | n/a | 1.72 |
| eip-7805 | 0.00 | | 234 | 6.24 | 12.30 | 6.12 | 1.00 | 0 | n/a | 1.72 |
| off | 0.90 | | 234 | 62.81 | 119.52 | 6.12 | 1.00 | 0.033 | 0.01 | 1.72 |
| eip-7805 | 0.90 | stuff | 184 | 46.52 | 119.35 | 6.12 | 1.00 | 28.8 | 6.08 | 104 |
| eip-7805 | 0.90 | miss | 232 | 64.36 | 400.32 | 40.33 | 0.59 | 5.99 | 0.64 | 7.7 |
| eip-7805 | 0.90 | yield | 234 | 7.41 | 15.88 | 6.03 | 1.00 | 2.02 | 0.43 | 1.72 |
| eip-7805 | 0.90 | cheapest | 234 | 8.79 | 56.95 | 6.03 | 1.00 | 1.78 | 0.38 | 4.04 |
| off | 1.00 | | 0 | n/a | n/a | 6.12 | 1.00 | 0.427 | 0.07 | 1.7 |
| eip-7805 | 1.00 | stuff | 0 | n/a | n/a | 6.12 | 1.00 | 61.5 | 11.56 | 208 |
| eip-7805 | 1.00 | miss | 0 | n/a | n/a | 47.09 | 0.25 | 14.8 | 0.89 | 8.54 |
| eip-7805 | 1.00 | cheapest | 0 | n/a | n/a | 9.45 | 1.00 | 2.39 | 0.35 | 44.1 |

The share 0.50 rows, sections 2 to 4 and every column are in `results.md`.

## What it shows

- **With nobody filtering, inclusion lists change nothing measured.** The
  `off` and `eip-7805` rows at share 0 are identical: the lists name what
  builders include anyway.
- **Without lists, a filtered transaction waits for a builder that does not
  filter.** At share 0.9 its delay p50 is 62.81 s against 6.24 s, and at
  share 1.0 none of 234 is included. Filtering costs the builders almost
  nothing: 0.033 ETH at share 0.9, a cost share of 0.01, because blocks have
  room and the filtered transfers' tips are all they give up.
- **With lists, what filtering costs depends on what a filtering builder can
  do instead.** When the slot can go to a builder that does not filter
  (*yield*, a proposer taking the best bid that satisfies the lists), the
  filtered transfers wait about as long as anyone's: delay p50 7.41 s at
  share 0.9, and 6.99 s at 0.5. The filtering builders then give up 0.43 of
  the priority fees of the slots they were due, 2.02 ETH. Doing the cheaper
  of stuffing and yielding cuts that to 1.78 ETH and a share of 0.38, for a
  delay p50 of 8.79 s.
- **When every builder filters, the lists include nothing, and the cost
  lands elsewhere.** At share 1.0 no filtered transfer is included under any
  strategy.
  - *Stuff* buys the excuse with gas. It costs the builders 61.5 ETH, 11.56
    times the fees they would have earned, and it raises the base fee to a
    peak of 208 gwei.
  - *Miss* costs honest users. 197 of 225 slots have no block (section 1 of
    `results.md`), the honest delay p50 rises from 6.12 s to 47.09 s, and
    0.25 of the background transfers are included by the end of the run.
  - *Cheapest* costs 2.39 ETH and moves the honest delay p50 to 9.45 s.

  So EIP-7805 makes filtering expensive or visible. It forces inclusion only
  where a builder that does not filter can take the slot.
- **Stuffing prices out the transactions it is aimed at.** At share 0.9,
  *stuff* includes 184 of 234 filtered transfers, against all 234 under
  *yield*, with a base fee peak of 104 gwei against 1.72. The wallets cap
  their fee at twice the base fee when they send and never raise it, and
  IL-5's fee check excuses leaving out a transaction whose cap the base fee
  has passed. The model does not separate these exclusions from others, so
  this is the mechanism the numbers are consistent with, not one they
  isolate.
- **The committee needs few honest includers.** With half of all nodes
  filtering as includers, section 2's row is identical to none filtering.
  At 0.9 the delay p50 is 7.94 s. At 0.97 every
  filtered transfer is still included, with delay p50 12.17 s and max
  65.76 s against 7.41 s and 15.88 s.
- **At full blocks the excuse is free only when the block is full to within
  the transaction's gas** (section 3, the slots a filtering builder was due
  from 240 s to 450 s, with *cheapest*).
  - For transfers as large as the extra demand's, 1,000,000 gas, the
    builder's own block was that full in 0.94 of the slots. Filtering then
    cost a share of 0.08 of the fees, against 0.74 before the demand. Only
    34 of the 86 sent during the demand were included. This is the earlier
    analysis's result.
  - For 21,000-gas transfers, the blocks of 1,000,000-gas transactions left
    that much unused in all but 0.04 of the slots, so the excuse rarely
    applied. But the gap was cheap to stuff: a share of 0.12 against 0.69
    before, with 38 of 49 slots stuffed. The transfers fared about as
    without lists, 74 of 86 included with delay p50 38.40 s, against 81 and
    54.44 s under `off`.
  - Paying a 10 gwei tip, above any other, raised the builders' cost from
    0.319 to 0.399 ETH. It got every transfer included, but with delay p50
    57.04 s.
  - Listing by age instead of by fee included the same 74 transfers.
- **EIP-7805 does nothing for private spends, and EIP-8369's Profile 2
  does** (section 4). Under `eip-7805` filtered spends wait exactly as under
  `off`, delay p50 59.04 s, because no includer lists a frame transaction.
  Under `eip-8369` the delay p50 is 6.95 s.
- **Profile 2 restores what experiment 08 found missing.** Experiment 08
  measured spends above the 100,000 floor whose builders lack headroom: none
  was included. That regime includes 0 of 253 here without lists, and all
  253 under `eip-8369`, with delay p50 16.59 s. The builder appends what an
  includer with headroom lists, whatever its own pool would admit. This is
  the guarantee an earlier revision of ethereum/EIPs pull request 12301
  named and its head drops (decision record 0016).

## What it does not show

- **A builder market.** Builders take turns, and bids, MEV and a builder's
  own order flow are not modelled. *Yield* assumes that a builder that does
  not filter bids in every slot, for its honest block.
- **Enshrined proposer-builder separation** (EIP-7732), under which
  EIP-8369 says Profile 2's check must move or the profile stay disabled.
- **The lists' gossip and deadlines, and equivocation.** Every list reaches
  every builder and attester here (`docs/spec/07-focil.md`, Not modelled).
- **Wallets that re-price.** A transfer priced out by stuffing would be sent
  again at a higher fee, and the background demand here does not fall as
  the base fee rises.
- **Block composition.** Whether the excuse is free depends on how close to
  full a block is, measured in the filtered transaction's gas. The extra
  demand here is all 1,000,000-gas transfers. A deep pool of small
  transactions would close the gap that made stuffing necessary for a
  21,000-gas transfer.
- **What includers are paid and what they must do.** FOCIL pays the
  committee nothing, and under EIP-8288 an includer would have to prove.
- **Flow that never reaches the public pool**, lists of sealed
  transactions, and MATCHA's draining with lists as its deterrent
  (experiment 02). These are left for later in the plan.
