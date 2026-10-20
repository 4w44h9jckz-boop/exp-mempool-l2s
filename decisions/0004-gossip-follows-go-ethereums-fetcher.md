# 0004. Gossip follows go-ethereum's broadcast and fetcher, and loads roll their own dice

Date: 2026-10-07. Status: accepted.

## Context

The simulator's first gossip model, written for experiment 00, pushed a new
transaction to the square root of the peers that lacked it, chosen at random,
and never fetched a hash the node had received before, whether it had admitted
it or refused it. Experiment 01 needs a shared sender under FP-12's `one`, where
a node that has not yet imported the block holding a sender's last transaction
refuses the next one as `ErrFrameSenderBusy`. Whether that node ever gets the
next transaction decides whether the following block carries one, so the rule
for fetching a refused transaction decides the experiment's answer.

go-ethereum at the commit `docs/spec/README.md` pins does neither of the old
model's things. In `eth/handler.go`, `BroadcastTransactions` sends a
transaction directly to the peers `choosePeers` returns: the
$\lceil\sqrt{n}\rceil$ of all $n$ peers with the lowest keyed hash of the node,
the peer and the transaction's sender, so one sender's transactions always take
the same first hops; a peer known to have the transaction is skipped even if it
is in that set; a transaction over `txMaxBroadcastSize` (4096 bytes) is only
announced. In `eth/fetcher/tx_fetcher.go`, `Notify` drops an announcement only
if the pool has the transaction, if it was in an imported block
(`txOnChainCache`), or if it is in the underpriced set, which `handleAddErrors`
fills from `ErrUnderpriced`, `ErrReplaceUnderpriced` and `ErrTxGasPriceTooLow`
and `isKnownUnderpriced` expires after `maxTxUnderpricedTimeout`, five minutes.
Any other refusal is forgotten, and a later announcement from another peer
fetches the transaction again.

Separately, every random draw came from one stream, so two runs that differed
only in a pool profile drew different arrival times as soon as the profile
changed what the network did, and a comparison between them mixed the rule's
effect with the dice's.

## Decision

1. **The network does what go-ethereum does**, as `sim/emem_sim/network.py`
   describes: direct peers per sender by a keyed hash (BLAKE2b keyed with a
   per-node key drawn from the seed, standing in for SipHash), announcement only
   above 4096 bytes, and the fetcher's three filters with the five-minute
   expiry. Local submission goes straight to the pool, as
   `eth_sendRawTransaction` does.
2. **Each load draws from two streams of its own**, seeded from the scenario's
   seed and the load's name: one for what is asked (arrival times, senders,
   tips) and one for where it is sent. The network and the chain keep the
   simulation's stream. Runs that differ only in a profile or a submission rule
   are offered identical demand.
3. **Experiment 00 is regenerated** under both changes in the same commit, and
   its README is corrected to the new numbers. Its findings stand.

## Consequences

- A refused transaction gets a second chance, which is what makes the rate of
  experiment 01 nearly one spend per slot instead of something lower. The
  simulator's tests pin both the second chance and its absence for an
  underpriced refusal.
- Still not modelled: retrying a failed fetch from another announcer, request
  batching, bandwidth and peer scoring. Experiment 06 (propagation as a timing
  channel) is the one most likely to need them.
