# 0021. The timing channel is measured with a spy at every node and observers that guess the first peer

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 6 asks how well observers locate where a transaction
entered the network. An earlier account abstraction study, read on
2026-10-09, argues that a funder who runs a node learns a funded
transaction's first-seen time to sub-second precision, and the peer it came
from, because a transaction pushed to a few peers and announced to the rest
reaches a well-connected node in the order of the arrive timeout. An earlier
problem record, that a nullifier used as a nonce key is visible before
inclusion, keeps one way out open in one of its falsification tests: that
the window before inclusion under FOCIL is short enough, and the observer's
added context thin enough, that seeing a nullifier in the mempool joins
nothing the block does not.

The simulator recorded when each node first held a transaction pending. An
observer learns more, and sooner: an announcement tells it that a
transaction exists, and which peer has it, one link's latency after that
peer has it, and the fetch that brings the content comes later.

## Decision

1. **Two observers.** A *spy* is a node connected to every other node that
   relays nothing. It takes no part in the random topology, so it fills no
   node's dialled peers, and it is connected once the topology is drawn.
   *Observers* are a share of the ordinary nodes, drawn at random, which
   relay as every node does and log what they hear. Several shares are read
   off one run, and a smaller share is a subset of a larger one.
2. **What is logged is the first hearing.** With `record_heard`, every node
   records, for each hash, the first time it heard of it and from which
   peer, whether by a push, an announcement or a fetch's answer, or that a
   local client submitted it. An announcement carries only the hash, but it
   is when and from whom an observer learns of the transaction; the content
   follows with the fetch and moves neither.
3. **The estimator is the first spy.** The observers take the earliest
   hearing among them and guess that the peer it came from is the node the
   user handed the spend to. It is the simplest guess, and it uses neither
   the topology nor the other hearings, so an adversary placed the same way
   that uses either does at least as well. The experiment reports how often
   the guess names that node, and how often it names the node or one of its
   peers.
4. **Users hand spends only to ordinary nodes.** `SharedSenderLoad` takes
   `targets`. A spend handed to an observer is known for certain and is
   counted apart, not in the share found.
5. **"Topology" is the random topology's size and peer count.** The
   experiment varies the share that observes, the peer count, the arrive
   timeout and the number of nodes. No other shape of graph is modelled.
6. **The window is measured where that record states it.** For that test,
   the time from the spy's first hearing to inclusion is measured with
   experiment 09's builders, nine in ten of which leave spends out and yield,
   without inclusion lists and under `eip-8369`. `eip-7805` lists no frame
   transaction, and experiment 09 showed it does nothing for spends.
7. **The spends are experiment 11's, sent once.** They come from one shared
   sender under `hegota-testnet`, so they do not queue behind each other;
   queueing is experiment 01's subject.

## Consequences

- `sim/emem_sim/network.py` gains `record_heard` and `spies`, and
  `SharedSenderLoad` in `sim/emem_sim/workload.py` gains `targets`. Neither
  moves a number of an earlier experiment.
- Experiment 12 reports the share found, how soon the observers hear, and
  how long they hold a spend before a block includes it. No clause changes:
  gossip is the simulator's (decision record 0004), not the specification's.
- Not modelled: a spy's own latency advantage or its reconnecting; the peer
  limit that makes a spy compete for a slot at every node; clients that
  delay or batch announcements; relaying through one peer at a time before
  broadcasting; and anything that joins a node to the person behind it.
