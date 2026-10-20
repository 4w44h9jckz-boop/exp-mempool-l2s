# 0013. Aggregation is measured on a larger network, with proofs only in wrappers

Date: 2026-10-08. Status: accepted.

## Context

The plan's item 9 asks what EIP-8288's in-mempool aggregation does to the delay
and the capacity of transactions that carry a proof or a signature as a
dependency. Decision record 0012 specified the layer and kept two readings
apart: whether the wrapper limits bind an aggregate (`cap_aggregates`), and
whether a node relays a user's wrapper at once (`forward_wrappers`).
Experiment 06 measures both against ordinary gossip, and the simulator needs
choices the specification does not make: where wrappers go, when a node
proves, and what a wallet does when its transaction is left out.

## Decision

1. **A transaction with dependencies travels only in wrappers.** The EIP says
   such transactions "are wrapped in wrapper objects that are broadcast once
   per `AGGREGATION_INTERVAL`" (Mempool Rules, at `258836f9`), and a pool that
   has not proven a dependency refuses the transaction alone (AG-6). The
   simulator's broadcast and announcement skip them, so the only routes to a
   builder are a user's wrapper sent to it, a peer's aggregate and, under
   `forward_wrappers`, a relayed user's wrapper.
2. **An aggregate goes to every peer.** The EIP's node forwards "this wrapper
   object to their peers" (Mempool Rules), not to go-ethereum's square root
   of them, and there is one aggregate per node per interval whatever it
   holds, so announcing it instead would only add a round trip.
3. **Every node aggregates every interval, at a phase of its own.** Ticks in
   step would make every node choose at the same instant from the same
   information. A phase is drawn per node, uniform over the interval, from a
   random stream keyed on the seed and kept apart from the simulation's, so
   that adding aggregation leaves the chain's and the network's draws as they
   were.
4. **Proving takes a fixed delay, bracketed by 0 and the interval.** The EIP
   gives no proving time; it orders what a node aggregates for when it "will
   not have enough proving time" (Mempool Rules). A node that took longer
   than the interval could not send one aggregate every interval, so 0 and
   the interval are the two ends a conforming node can be at. The delay holds
   the aggregate back from every peer; nothing else changes.
5. **Every transaction has a dependency of its own.** Two transactions that
   share a triple share its proof, so the cap counts triples, not
   transactions. A private transfer's proof is its own, which is the case
   experiment 06 is about, and the one where the cap binds hardest: under one
   leanSTARK per wrapper, an aggregate carries one transaction.
6. **The network is 30 nodes, with 100-node rows.** Experiments 00 to 05 use
   10, where at degree 8 nearly every node is every other's peer, and a route
   that costs an interval a hop cannot show. At 30 most nodes are not each
   other's peers; the 100-node rows check that what the uncapped reading
   costs grows with the hops, as it should, against gossip on the same
   network.
7. **The gas limit is 6,300,000, so that gas does not bind.** A leanSTARK
   transaction takes 133,849 of a block's gas with AG-8's charge, so a block
   holds 47 of them, above the 32 a slot the experiment goes to. A delay is
   then a propagation delay, not a queue.
8. **Wallets resend, and a variant sends once.** The simulator's wallets send
   a transaction again, to a random node, after every block that leaves it
   out, as they do in every experiment. Under the cap that resend is itself a
   route, because the next proposer may be the node it reaches. The send-once
   variant takes it away, so that what aggregation alone delivers is visible.
9. **What is measured, beyond delay.**
   - *Route*: how the block's proposer first admitted each transaction it
     included (a user's wrapper, a peer's aggregate, a forwarded wrapper, or
     gossip). It separates what aggregation delivers from what the resend
     does.
   - *Carried*: per slot, the distinct transactions listed in any node's
     aggregate. It is the network's aggregation capacity, the figure an
     earlier design study put at about 12 a slot.
   - *Reach*: when a transaction became pending at half the nodes and at all
     of them.
   - *What nodes send*: wrappers, recursive STARKs, direct proofs and bytes.
     A recursive STARK is priced at 128 kB, the least the EIP gives a STARK
     ("all take over 128 kB", Motivation), so the figure is a floor; the
     model sizes no proof (AG, Not modelled).

## Consequences

- Experiment 06 can say how much of the inclusion it reports each route
  delivered, and in particular how much of it is the wallets' own resend.
- The simulator's `Node` gains an `Aggregator`, and `NetworkConfig` a
  `prove_delay`; a scenario without dependency frames runs as before, and
  experiments 00 to 05 reproduce.
- A shared dependency, a proving time that depends on what is proven, a
  proof's size and the bandwidth it takes are left out, and experiment 06's
  README names them.
