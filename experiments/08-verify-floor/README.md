# 08. The verification gas floor

**Question.** ethereum/EIPs pull request 12301 makes EIP-8141's
`MAX_VERIFY_GAS` a floor that every node admits, with headroom of each node's
own above it. Under that floor, how far does a private spend above 100,000
gas reach, and how long does it wait? How does that depend on the share of
nodes with headroom and on where they sit? And what does a budget carried in
announcements save, and what does it let a liar do?

**Clauses exercised.**

- FP-6: the budget, set per node (decision record 0016).
- FP-3 to FP-8: the rest of a frame transaction's admission, at every node
  that is handed one.
- BB-1 to BB-3: a builder takes what its own pool holds.

The pull request (open, read at its head `f3538f20`, 2026-09-29) keeps the
value at 100,000. It says a node "MUST NOT reject a frame transaction, or
decline to propagate it, solely because of its validation work while the
validation-prefix budget of structural rule 6 ... is at or below
`MAX_VERIFY_GAS`". It also says a node "MAY additionally admit transactions
whose validation-prefix budget exceeds the floor when its own capacity
allows". It describes what happens above the floor: "the heavier its
validation work the fewer nodes carry it and the slower it diffuses, without
ever being dropped network-wide. This is a natural gradient rather than a
cutoff".

ethresear.ch topic 25889 measures what a privacy pool needs from the budget.
Its cheapest spend, one nullifier, is 211,828, and "Nothing fits in 100,000".
The consequence is that every private spend travels where the floor's
guarantee does not reach. This experiment measures that regime.

## Setup

- **Network** (decision record 0016):
  - 100 nodes, 8 peers each, go-ethereum's gossip as in every experiment.
  - A block every 12 s, gas limit 30,000,000. The proposer rotates through
    every node, except in section 2's rows where 10 builders build every
    block.
  - Each row pools three runs, seeds 1 to 3, each with its own topology,
    latencies and placement.
- **Pools:** `eip-8141`, with `max_verify_gas` at the floor, 100,000, except
  at the nodes a row gives headroom:
  - 250,000 in sections 1, 2 and 4, topic 25889's recommended value;
  - in section 3, tiers at topic 25889's values: 10% of nodes at 525,000,
    20% at 400,000, 40% at 250,000, and 30% at the floor. The shares are
    this experiment's choice.
- **Spends** (`WalletLoad` with `fresh` senders):
  - Self-paying frame transactions whose rule 6 budget is topic 25889's for
    the nullifier count, or 100,000 for a spend at the floor.
  - The proof sits in an ARBITRARY signature entry of 256 bytes, which
    go-ethereum pushes in full to some peers. Section 4 adds 6,000-byte
    entries, over its 4,096-byte `txMaxBroadcastSize`, which it only
    announces. The sizes are choices on either side of that limit.
  - Each spend comes from a sender of its own. Spends are sent at 2 a slot
    for the first 1,200 s of a 2,400 s run.
  - Each is sent once, to a random node that admits it. That stands for a
    wallet that tries random nodes until one accepts.
  - Section 1 also has wallets that send again, after every block that
    leaves the spend out, to another such node.
- **Hints** (section 4, `NetworkConfig.announce_budget`):
  - Every announcement carries the spend's rule 6 budget, and a node does
    not fetch one above its own bound. A push carries no hint.
  - Liars are drawn from the nodes at the floor. They admit nothing, so
    they relay nothing and their blocks carry no spend.
  - With hints, a liar announces every spend it hears of as over any bound.
    A node that hears the lie forgets it, or remembers it for 300 s, as
    go-ethereum's fetcher remembers an underpriced transaction.

## Run

```
python3 experiments/08-verify-floor/run.py > experiments/08-verify-floor/results.md
```

About four minutes. Every figure below is from `results.md`.

## Results

**The share of nodes with headroom** (section 1). Every node proposes. The
spend has one nullifier, a budget of 211,828, and headroom is 250,000.
*Reached* is the mean share of the nodes with headroom that held a spend
pending, and *refused copies* the mean number of times a floor node was
handed a spend and refused it. Delays are in seconds.

| share | delay p50 | p90 | max | reached | reached all | refused copies |
| --- | --- | --- | --- | --- | --- | --- |
| 0.05 | 409.25 | 997.80 | 1199.95 | 0.35 | 0.00 | 15.01 |
| 0.10 | 318.41 | 939.59 | 1196.46 | 0.26 | 0.00 | 20.90 |
| 0.20 | 67.54 | 521.71 | 1166.93 | 0.65 | 0.00 | 84.08 |
| 0.30 | 30.13 | 147.61 | 1188.99 | 0.84 | 0.00 | 119.85 |
| 0.50 | 12.17 | 40.47 | 107.60 | 1.00 | 0.98 | 142.59 |
| 1.00 | 5.88 | 11.18 | 12.19 | 1.00 | 0.98 | 0.00 |

Spends at the floor, in the same runs, waited a median of 5.84 s at every
share. Wallets that send again after every missed block cut the median at a
share of 0.05 from 409.25 s to 167.54 s, and the reach from 0.35 to 0.95.

**Where the headroom sits** (section 2):

| headroom | blocks built by | share | included of 592 | delay p50 | p90 | reached |
| --- | --- | --- | --- | --- | --- | --- |
| random | every node | 0.10 | 592 | 318.41 | 939.59 | 0.26 |
| one cluster | every node | 0.10 | 592 | 79.54 | 227.28 | 1.00 |
| random, not at builders | 10 builders | 0.10 | 0 | n/a | n/a | 0.30 |
| at the builders alone | 10 builders | 0.10 | 592 | 33.22 | 96.37 | 0.21 |
| random | every node | 0.30 | 592 | 30.13 | 147.61 | 0.84 |
| one cluster | every node | 0.30 | 592 | 23.76 | 69.18 | 1.00 |
| random, not at builders | 10 builders | 0.30 | 0 | n/a | n/a | 0.96 |
| at builders first | 10 builders | 0.30 | 557 | 7.28 | 12.17 | 0.89 |

**A gradient** (section 3), 1 to 16 nullifiers with topic 25889's budgets:

| nullifiers | budget | nodes that admit it | delay p50 | p90 | max | reached |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 211828 | 70 | 8.59 | 23.69 | 82.45 | 1.00 |
| 2 | 231828 | 70 | 8.23 | 25.24 | 77.89 | 1.00 |
| 8 | 351828 | 30 | 31.60 | 104.12 | 1182.15 | 0.93 |
| 16 | 511828 | 10 | 361.99 | 980.87 | 1198.21 | 0.26 |

**Budget hints** (section 4), at a share of 0.5. With hints, refused copies
per spend fell from 142.35 to 88.84 for a pushed spend above the floor, and
from 117.05 to 0.00 for an announced one. The median delays stayed at 12.53
s and 13.49 s. Against liars, *reached* is the share of the honest nodes
that admit the spend:

| liars | they | spend | sent as | delay p50 | p90 | reached |
| --- | --- | --- | --- | --- | --- | --- |
| 0.10 | keep quiet | at the floor | announced | 8.20 | 13.72 | 0.99 |
| 0.10 | lie, forgotten | at the floor | announced | 8.20 | 13.72 | 0.99 |
| 0.10 | lie, remembered | above the floor | announced | 25.33 | 89.68 | 0.55 |
| 0.10 | lie, remembered | at the floor | announced | 12.38 | 38.68 | 0.61 |
| 0.30 | keep quiet | at the floor | announced | 10.32 | 23.71 | 1.00 |
| 0.30 | lie, remembered | above the floor | pushed | 16.26 | 50.86 | 0.81 |
| 0.30 | lie, remembered | above the floor | announced | 112.70 | 398.27 | 0.14 |
| 0.30 | lie, remembered | at the floor | pushed | 9.06 | 24.28 | 0.94 |
| 0.30 | lie, remembered | at the floor | announced | 85.46 | 262.54 | 0.15 |

## What it shows

- **Above the floor, a spend reaches its own cluster, not the network.**
  - The nodes with headroom form a subnetwork, and a spend reaches the part
    of it that its first node belongs to.
  - At a share of 0.30 or less, no spend reached every node with headroom.
    At 0.10 a spend reached a mean of 0.26 of them.
  - At 0.50 and above, 0.97 to 0.98 of spends reached every one. The rest
    were included before they had.
- **It is a cutoff, not a gradient.**
  - From a share of 0.30 to 0.10, the median delay rose from 30.13 s to
    318.41 s.
  - In section 3 the same happens to the heavier spends. An 8-nullifier
    spend that 30 nodes admit reached 0.93 of them, with a median of
    31.60 s. A 16-nullifier spend that 10 nodes admit reached 0.26, with a
    median of 361.99 s. One- and two-nullifier spends, which 70 nodes
    admit, waited a median of 8.59 s and 8.23 s.
  - Where the nodes that admit a spend stop being connected, the gradient
    the pull request describes becomes a wait for a turn to propose.
- **"Never dropped network-wide" holds only because every node proposes.**
  - Every spend in section 1 was included, because its first node had a
    turn within 100 slots. The maximum delays below a share of 0.50, near
    1,200 s, are that turn.
  - When 10 builders build every block and have no headroom, none of 592
    spends was included, at a share of 0.10 or 0.30. At 0.30 the spends
    still reached 0.96 of the nodes with headroom.
  - Headroom at the builders first included 557 of 592 at 0.30, with a
    median of 7.28 s. The rest never reached a builder.
- **Placement matters as much as share.** At a share of 0.10, one cluster
  reached every node with headroom and cut the median from 318.41 s to
  79.54 s. What it waits for then is a proposer with headroom.
- **Above the floor, every node without headroom keeps being handed the
  spend.**
  - At a share of 0.50, a spend was refused 142.59 times on average,
    because each node without headroom is handed it by each peer that has
    some.
  - A hint saves the fetched copies and not the pushed ones: 88.84 refused
    copies remain for a pushed spend, and none for an announced one.
- **A remembered lie breaks the floor's guarantee, for spends at the floor
  too.**
  - A node cannot tell a liar's hint from an honest one without fetching.
    If it remembers the hint, it ignores later honest announcements.
  - With 30% liars, an announced spend at the floor reached 0.15 of the
    honest nodes, with a median of 85.46 s, against 1.00 and 10.32 s when
    the same liars only keep quiet.
  - The pull request says a spend within the floor "is propagated whether or
    not an announcement carries such a value". A node that acts on a hint
    cannot keep that promise, because it never sees the transaction.
  - If the node forgets the lie, every row matches the liars keeping quiet.
    It fetches from the next honest announcer.
  - go-ethereum's direct push defends small spends: pushed at the floor,
    they reached 0.94 even against 30% liars.
- **Whether a lie can suppress a spend.** One inflated hint does not suppress a
  pushed transaction in this model. A remembered hint suppresses an announced
  one, above the floor or at it. Binding the hint, by checking it on fetch,
  would not reach the case that matters: a node that acts on a lie never
  fetches.

## What it does not show

- **Validation in time.** Headroom is meant to be sized from each client's
  measured worst-case validation cost. The model counts budgets, not
  seconds. Refused copies are counts, not bandwidth.
- **Where headroom actually sits.** No measurement of deployed headroom
  exists. The shares, tiers and placements are choices.
- **Most nodes not proposing.** In sections 1, 3 and 4 every node
  proposes, which is the most favourable case for inclusion. Section 2's
  builders are the other end.
- **Inclusion lists.** An earlier revision of the pull request called the
  floor the "inclusion-list eligibility guarantee", and its head does not.
  FOCIL is not modelled.
- **A shared sender.** Each spend here has a sender of its own. A privacy
  pool's spends from one shared sender meet experiment 01's ceiling first.
- **Retries and peer scoring.** A node here never retries a failed fetch
  from another announcer. Under the pull request, no node penalises a peer
  over a transaction above the floor.
- **A real wire format.** The pull request leaves hints to a future eth
  wire protocol. Both readings of a hint here are this experiment's.
