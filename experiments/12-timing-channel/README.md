# 12. Propagation as a timing channel

**Question.** How well do observers in the gossip network find the node a
spend was handed to, how soon do they hear of it, and how long do they hold
it before a block includes it? It is asked against the share of nodes that
observe, the peer count, the arrive timeout, the network's size, and
builders that filter spends with and without inclusion lists.

**Clauses exercised.**

- Gossip follows `sim/emem_sim/network.py`, which is go-ethereum's
  broadcast and fetcher (decision record 0004) and is not specified in
  `docs/spec/`.
- FP-7 and FP-12: spends from one shared sender, each on a nonce key of its
  own, under `hegota-testnet`'s `disjoint-keys`.
- In section 4, IL-2 to IL-4, IL-6 and IL-8 of `docs/spec/07-focil.md`
  under `eip-8369`.

An earlier design study argues that a funder who runs a node learns a
funded transaction's first-seen time to sub-second precision, and the peer
it came from. An earlier analysis says a nullifier that is an EIP-8250
nonce key is visible before inclusion, and keeps one way out open, a test.
The test asks whether the window before inclusion under FOCIL is short
enough, and the observer's added context thin enough, that seeing the
nullifier in the mempool joins nothing the block does not. This experiment
measures both halves.

## Setup

- **Network:** 50 nodes, each dialling random peers until it has 8
  (section 2: 4, 8 or 16), one-way link latency uniform in 20 to 100 ms,
  and an arrive timeout of 0.5 s (section 2: 0.1, 0.5 or 2.0 s). Section 3
  has 25 to 200 nodes. A block every 12 s from a proposer that rotates
  through the nodes, gas limit 30,000,000. 720 s a run, and each row pools
  five runs, seeds 1 to 5.
- **Spends:** from 12 s to 420 s, users send spends from one shared sender,
  three a slot, each with a 1 gwei tip, to a random node, as experiment 11's
  single copy. Pools are `hegota-testnet`, so spends do not queue behind
  each other (decision record 0021).
- **Observers** (decision record 0021):
  - a *spy*, a node connected to every other node that relays nothing and
    takes no part in the random topology;
  - a share of the ordinary nodes, 2% to 50%, drawn at random. They relay
    as every node does and log what they hear. Users never hand a spend to
    the spy; a spend handed to an observer is counted apart.
- **Estimator:** for each spend, the observers take the earliest time any
  of them heard of it, by a push, an announcement or a fetch's answer. They
  guess that the peer it came from is the node the user handed it to.
- **Builders that filter** (section 4): 10 nodes build every block in turn.
  Without filtering, or with 9 of them leaving every spend out and yielding
  the slot, as in experiment 09. That is measured without inclusion lists
  and under `eip-8369`, whose committee lists spends as Profile 2
  candidates.

## Run

```
python3 experiments/12-timing-channel/run.py > experiments/12-timing-channel/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

Section 1, 50 nodes and 8 peers. Origin found is the share of spends whose
entry node the guess names; chance is one over the nodes it could be.
Heard after runs from the hand-over to the observers' first hearing. Held
runs from then until inclusion. Both are in seconds.

| observer | at an observer | spends | origin found | origin or a peer of it | chance | heard after p50 | p90 | max | held p50 | p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| spy | 0 | 522 | 0.80 | 1.00 | 0.02 | 0.06 | 0.08 | 0.10 | 5.94 | 10.98 |
| 2% of nodes | 13 | 509 | 0.21 | 0.62 | 0.02 | 0.11 | 0.16 | 0.22 | 5.96 | 10.90 |
| 10% of nodes | 55 | 467 | 0.57 | 0.95 | 0.02 | 0.06 | 0.10 | 0.15 | 6.02 | 10.95 |
| 20% of nodes | 104 | 418 | 0.84 | 1.00 | 0.03 | 0.05 | 0.08 | 0.12 | 6.03 | 10.98 |
| 50% of nodes | 261 | 261 | 0.97 | 1.00 | 0.04 | 0.03 | 0.06 | 0.07 | 6.08 | 11.00 |

What the block tells, for the same 522 spends: delay from the hand-over to
the block, p50 6.01 s, p90 11.02 s, at most 12.12 s.

Section 2, origin found, at an arrive timeout of 0.5 s. The rows at 0.1 s
and 2.0 s differ from these by at most 0.01.

| observer | 4 peers | 8 peers | 16 peers |
| --- | --- | --- | --- |
| spy | 0.85 | 0.80 | 0.77 |
| 10% of nodes | 0.42 | 0.57 | 0.71 |

Section 3, origin found against the network's size.

| observer | 25 nodes | 50 | 100 | 200 |
| --- | --- | --- | --- | --- |
| spy | 0.80 | 0.80 | 0.83 | 0.79 |
| 10% of nodes | 0.65 | 0.57 | 0.59 | 0.61 |

Section 4, the spy, with 10 builders.

| inclusion lists | builders that filter | origin found | held p50 | p90 | max |
| --- | --- | --- | --- | --- | --- |
| off | 0.00 | 0.80 | 6.02 | 11.01 | 12.16 |
| off | 0.90 | 0.81 | 52.46 | 106.36 | 119.90 |
| eip-8369 | 0.90 | 0.80 | 6.77 | 11.56 | 16.03 |

The other rows and columns are in `results.md`.

## What it shows

- **A spy at every node names the entry node four times in five.** It
  finds 0.80 of spends, where chance is 0.02. It names the entry node or one
  of its peers for 1.00 of them. The entry node is the spy's peer like every
  other node, and it tells the spy first unless a path through another node
  is faster than their own link. The network's size does not change this:
  0.79 to 0.83 from 25 to 200 nodes. More peers lower it a little, from
  0.85 at 4 to 0.77 at 16, because there are more paths that can beat the
  direct link.
- **Ordinary nodes that observe get there from a fifth of the network.**
  One observing node in 50 finds 0.21 of spends, ten times chance. At 10%
  of the nodes the share is 0.57, and 0.95 for the node or a peer of it; at
  20% it is 0.84, and at 50% it is 0.97. Here more peers help the observers,
  0.42 at 4 and 0.71 at 16, because a node with more peers is more likely
  to have an observer among them. At a fixed share the network's size
  changes little, 0.57 to 0.65.
- **They hear within a tenth of a second, whatever the arrive timeout.**
  The spy hears p50 0.06 s after the hand-over and at most 0.10 s. The
  arrive timeout, at 0.1, 0.5 or 2.0 s, moves no row. A node announces a
  hash to every peer it does not push to as soon as it holds the
  transaction, so an observer learns that the spend exists, and from whom,
  one link's latency later. The timeout only delays when the content is
  fetched, and the content is bound to the hash already heard. The study's bound
  of the order of the 500 ms arrive timeout is the time to hold a
  transaction. For the timing channel the bound is the link latency.
- **The block tells much less.** Someone who reads only blocks places the
  hand-over within the 12.12 s before the block, p50 6.01 s. The spy places
  it within 0.10 s. With $\lambda$ hand-overs a second, the study's count of
  candidates is $k \approx \lambda w$ for a user who spreads their timing
  over a window $w$. Reading blocks adds about twelve seconds to $w$, and
  the spy adds a tenth of one. A user who does not spread their timing is
  one of about $12\lambda$ candidates to a reader of blocks, and one of
  about $0.1\lambda$ to the spy.
- **Inclusion lists bound the window and leave the join.** With nine in
  ten builders leaving spends out, the spy holds a spend p50 52.46 s and up
  to 119.90 s before a block includes it. Under `eip-8369` that falls to
  p50 6.77 s and at most 16.03 s, close to the 12.16 s with no filtering.
  The spy finds the entry node 0.80 or 0.81 of the time in every case. The
  analysis's test has two halves. The window half holds under FOCIL: about a
  slot, which is short. The context half fails: in that slot an observer joins
  the nullifier to the node it entered by and the moment it entered, which the
  block does not carry. In this model the test does not retire the problem.

## What it does not show

- **A better estimator.** The first spy uses neither the topology nor the
  hearings after the first, so an adversary placed the same way that uses
  either finds at least as many. These numbers are what the simplest guess
  gets.
- **A real spy's limits.** A node accepts a bounded number of peers, so a
  spy must win a slot at every node, and real links are not uniform in 20
  to 100 ms. A spy close to everyone does better; one that reaches only some
  nodes is between the spy and the observer rows.
- **Who stands behind a node.** The guess names a node. A user who sends
  through their own node is that node. A user who sends through an RPC
  service is hidden behind it from the network, and seen by the service,
  which changes the audience, not the exposure.
- **Defences.** Relaying through one peer at a time before broadcasting,
  random delays, and sending through several nodes at once are not
  modelled, and no source read here proposes one for the frame pool. An
  EIP-8184 sealed transaction hides its content and not its timing or
  entry node, so it is not one.
- **Bandwidth and batching.** A client that batches announcements adds its
  batching interval to every hearing, and the model has none.
