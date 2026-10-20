# 0029. A committee that clears every block takes its orders from a block, or from the pool at a cutoff

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 23 takes an earlier study's requirement for per-block
computation: per-block order matching, a private market maker, or any batch
auction that clears every block must finish inside one slot, because the
next batch arrives with the next block. Its budget is $\le 150$ committee
rounds for a 12 s slot at 80 ms RTT and $\le 50$ for a 4 s slot at 80 ms
RTT, and the study records which protocols meet it: the tree tournament
(49 rounds) and garbling (2), PRAC's heap insert for an order book (17), and
not the running maximum (4,096). With the chain checking the result through
a collaborative proof, the floor is $\max(61, 49) + 2 = 63$ rounds. Its
inputs are delivered through the chain as Merces delivers amounts.

The budget is the slot divided by the round trip: it prices the computation
and leaves out the network on either side of it, the inputs reaching the
committee and the result reaching the next proposer. The plan's item asks for
the batches settled in time and the orders that make the batch they were
sent for, against the round count and slots of 12, 8 and 4 s, and needs no
clause.

## Decision

1. **No clause changes.** An order is a type 2 transaction and a settlement
   a type 2 transaction from the committee's account, which the pools
   already specify. The committee is a load of the simulator's, `Clearing`.
2. **Three members in the gossip network.** The committee is three nodes,
   as Merces's three servers are, that never propose. Their rounds run over
   direct links at that study's round trips, not through the gossip
   network, and take the rounds times the round trip; bytes are not
   modelled, as its budget does not price them.
3. **A batch starts only when the last one has ended.** *Interpretation:*
   the book a batch matches, or the quotes a market maker updates, are the
   ones the last batch left, which is why that study says a batch must finish
   before the next arrives. So the committee does not run two batches at
   once.
4. **Two ways for orders to reach it.**
   - *From the chain*, as Merces takes its intents: batch $b$ is the orders
     that block $b - 1$ carried, and it starts once every member has
     imported that block, since each needs its own shares. Its settlement is
     meant for block $b$.
   - *From the pool*, as a batch auction that settles signed orders before
     they land would: orders travel the gossip network as transactions do,
     no builder includes them, and they reach the chain only through the
     settlement. Batch $b$ is the orders every member has held pending since
     before its cutoff, which the committee sets at its rounds and a margin
     before block $b$ is due, and that no earlier batch took.
     *Interpretation:* the members agree on the set at no cost; the round
     that would take is left out, as is what the contract checks the batch
     against.
5. **The settlement is Merces's**: 1,125,950 gas, a proof the chain checks,
   sent by the first member from an account at its next nonce, for every
   batch whether or not it holds an order, as a market maker that quotes
   every block would.
6. **The network is the simulator's**, the same at every slot time: a hop
   takes 20 to 100 ms, and a node imports a block 0.1 to 1.0 s after it is
   built. A shorter slot does not make a block travel faster, and the
   simulator has no attestation deadline that would hold the block's
   arrival under one. The gas limit stays 60,000,000 a block, so a shorter
   slot carries more gas a second, and orders arrive at 0.5 a second.
7. **Not modelled**: an abort or a slow member, which that study asks of
   every design and finds any one member can cause here; the round to agree on
   a batch from the pool; bytes; a proposer that delays its block or leaves
   the settlement out; and whether an order that misses its batch is still
   wanted in the next.

## Consequences

- `Clearing` and `Batch` in `sim/emem_sim/workload.py`, with tests.
- Experiment 20.
